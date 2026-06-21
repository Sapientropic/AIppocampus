from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import apw_route_identity
from aippocampus_runtime.recall import why_diagnostics as why
from aippocampus_runtime.recall.associative_path_inputs import (
    build_associative_path_diagnostic,
    build_associative_path_input_pack,
)


class AssociativePathInputPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sidecars = self.root / ".aippocampus"
        self.sidecars.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_jsonl(self, name: str, rows: list[dict[str, object]], *, malformed: bool = False) -> Path:
        path = self.sidecars / name
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if malformed:
                fh.write("{not-json\n")
        return path

    def _write_clean_messages(self, rows: list[dict[str, object]]) -> Path:
        clean = self.sidecars / "clean-source"
        clean.mkdir(parents=True, exist_ok=True)
        path = clean / "messages.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return clean

    def test_builds_read_only_pack_from_sidecars_without_raw_paths(self) -> None:
        self._write_jsonl(
            "semantic-bridges.jsonl",
            [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            malformed=True,
        )
        self._write_jsonl(
            "navigation-potential.jsonl",
            [
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                },
                {
                    "route_id": "route:private",
                    "route_terms": ["private route"],
                    "source_refs": [{"thread_key": "thread:private", "message_id": "msg-9"}],
                    "scope_bucket": "user_private",
                },
            ],
        )
        self._write_jsonl(
            "route-feedback.jsonl",
            [
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "user_private",
                }
            ],
        )

        pack = build_associative_path_input_pack(query="黏菌 联想回忆 探索算法", cwd=self.root)
        encoded = json.dumps(pack, ensure_ascii=False)

        self.assertEqual(pack["kind"], "aippocampus_associative_path_input_pack")
        self.assertFalse(pack["boundary"]["writes_files"])
        self.assertFalse(pack["boundary"]["changes_default_recall_ranking"])
        self.assertEqual(pack["metrics"]["candidate_count"], 2)
        self.assertEqual(pack["metrics"]["semantic_bridge_row_count"], 1)
        self.assertEqual(pack["metrics"]["feedback_row_count"], 1)
        self.assertGreaterEqual(pack["metrics"]["malformed_row_count"], 1)
        self.assertGreaterEqual(pack["metrics"]["private_or_stale_row_count"], 1)
        self.assertIn("malformed_sidecar_rows_ignored", pack["reason_codes"])
        self.assertNotIn(str(self.root), encoded)

    def test_diagnostic_blocks_cross_scope_positive_feedback_but_keeps_route(self) -> None:
        private_feedback = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            candidates=[
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [
                        {"thread_key": "thread:apw", "message_id": "msg-1", "source_line": 12}
                    ],
                    "scope_bucket": "project",
                }
            ],
            semantic_bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [
                        {"thread_key": "thread:apw", "message_id": "msg-1", "source_line": 12}
                    ],
                    "scope_bucket": "project",
                }
            ],
            feedback_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "user_private",
                }
            ],
        )
        project_feedback = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            candidates=[
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            semantic_bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            feedback_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "project",
                }
            ],
        )

        self.assertEqual(private_feedback["decision"], "route_candidates")
        self.assertFalse(private_feedback["applied_to_default_ranking"])
        self.assertIn("cross_scope_positive_feedback_ignored", private_feedback["reason_codes"])
        action = private_feedback["next_actions"][0]
        self.assertEqual(action["id"], "open_apw_source_candidate_1")
        self.assertEqual(action["tool_name"], "search_memory")
        self.assertIn("aippocampus search --open-source", action["command"])
        self.assertEqual(
            action["source_reopen_args"],
            {"thread_key": "thread:apw", "message_id": "msg-1", "line": 12},
        )
        self.assertNotIn(
            "positive_feedback_same_scope",
            private_feedback["top_candidates"][0]["reason_codes"],
        )
        self.assertIn(
            "positive_feedback_same_scope",
            project_feedback["top_candidates"][0]["reason_codes"],
        )

    def test_current_clean_source_filters_goal_context_unless_explicitly_requested(self) -> None:
        clean = self._write_clean_messages(
            [
                {
                    "message_id": "msg-goal-control",
                    "turn_id": "turn-shared",
                    "turn_index": 7,
                    "source_id": "src-goal-control",
                    "source_line": 20,
                    "role": "developer",
                    "phase": "commentary",
                    "source_use_class": "control_only",
                    "text": "<goal_context> 黏菌 联想回忆 探索算法 is control scaffolding, not the memory route.",
                },
                {
                    "message_id": "msg-real-cue",
                    "turn_id": "turn-shared",
                    "turn_index": 7,
                    "source_id": "src-real-cue",
                    "source_line": 21,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "公开 fixture 锚点：黏菌 联想回忆 探索算法，真实可打开的连续性来源。",
                },
            ]
        )

        diagnostic = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=clean,
        )

        self.assertEqual(diagnostic["decision"], "route_candidates")
        top_ref = diagnostic["top_candidates"][0]["source_refs"][0]
        self.assertEqual(top_ref["message_id"], "msg-real-cue")
        self.assertEqual(diagnostic["metrics"]["goal_context_filtered_count"], 1)
        self.assertEqual(diagnostic["metrics"]["control_source_filtered_count"], 1)
        self.assertIn(
            "control_source_filtered_from_foreground_apw",
            diagnostic["reason_codes"],
        )

        explicit = build_associative_path_diagnostic(
            query="goal_context 黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=clean,
        )
        explicit_refs = [
            ref.get("message_id")
            for candidate in explicit["top_candidates"]
            for ref in candidate.get("source_refs", [])
        ]

        self.assertIn("msg-goal-control", explicit_refs)
        self.assertEqual(explicit["metrics"]["control_source_explicitly_allowed_count"], 1)

    def test_current_clean_source_filters_task_echo_without_enough_anchors(self) -> None:
        clean = self._write_clean_messages(
            [
                {
                    "message_id": "msg-cn-echo",
                    "turn_id": "turn-echo",
                    "turn_index": 11,
                    "source_id": "src-cn-echo",
                    "source_line": 40,
                    "role": "user",
                    "text": "继续开 source-shape issues，下一阶段验收一下就好。",
                },
                {
                    "message_id": "msg-en-echo",
                    "turn_id": "turn-echo",
                    "turn_index": 12,
                    "source_id": "src-en-echo",
                    "source_line": 41,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "Done; please verify the narrative issue in the next stage.",
                },
                {
                    "message_id": "msg-real-apw",
                    "turn_id": "turn-real",
                    "turn_index": 2,
                    "source_id": "src-real-apw",
                    "source_line": 9,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "The source-shape narrative mesh slime mold pathlet route "
                        "is the real APW continuity source."
                    ),
                },
            ]
        )

        diagnostic = build_associative_path_diagnostic(
            query="source-shape narrative mesh slime mold pathlet",
            cwd=self.root,
            clean_source_dir=clean,
        )

        self.assertEqual(diagnostic["decision"], "route_candidates")
        self.assertEqual(diagnostic["top_candidates"][0]["source_refs"][0]["message_id"], "msg-real-apw")
        self.assertEqual(diagnostic["metrics"]["same_thread_task_echo_filtered_count"], 2)
        self.assertIn("same_thread_task_echo_no_anchor", diagnostic["reason_codes"])

    def test_current_clean_source_keeps_tasky_source_when_anchors_are_real(self) -> None:
        clean = self._write_clean_messages(
            [
                {
                    "message_id": "msg-current-real",
                    "turn_id": "turn-current-real",
                    "turn_index": 13,
                    "source_id": "src-current-real",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Verification note: source-shape narrative mesh slime mold pathlet "
                        "is a genuine current-source APW route, not issue chatter."
                    ),
                }
            ]
        )

        diagnostic = build_associative_path_diagnostic(
            query="source-shape narrative mesh slime mold pathlet",
            cwd=self.root,
            clean_source_dir=clean,
        )

        self.assertEqual(diagnostic["decision"], "route_candidates")
        self.assertEqual(diagnostic["top_candidates"][0]["source_refs"][0]["message_id"], "msg-current-real")
        self.assertEqual(diagnostic["metrics"]["same_thread_task_echo_filtered_count"], 0)

    def test_wrong_route_feedback_aliases_suppress_same_apw_identity(self) -> None:
        source_refs = [
            {
                "source_id": "src-shared-apw",
                "message_id": "msg-shared-apw",
                "turn_id": "turn-shared-apw",
                "turn_index": 3,
            }
        ]
        digest = apw_route_identity.source_ref_digest(source_refs)
        candidate = {
            "route_id": "current-clean-source:msg-shared-apw",
            "candidate_id": "candidate:shared-apw",
            "route_terms": ["source-shape", "narrative", "mesh", "slime", "mold", "pathlet"],
            "source_refs": source_refs,
            "scope_bucket": "project",
        }

        for alias in (
            "apw:current-clean-source:msg-shared-apw",
            "current-clean-source:msg-shared-apw",
            "candidate:shared-apw",
            "src-shared-apw",
            digest,
        ):
            with self.subTest(alias=alias):
                diagnostic = build_associative_path_diagnostic(
                    query="source-shape narrative mesh slime mold pathlet",
                    candidates=[candidate],
                    feedback_rows=[{"route_id": alias, "signal": "wrong_route_drag"}],
                )

                self.assertEqual(diagnostic["decision"], "abstain")
                self.assertEqual(diagnostic["candidate_count"], 0)
                self.assertIn("negative_feedback_evaporated", diagnostic["reason_codes"])

    def test_diagnostic_emits_repair_action_for_blocked_or_source_free_routes(self) -> None:
        cases = [
            (
                "private",
                {
                    "route_id": "route:private",
                    "route_terms": ["associative path walker"],
                    "source_refs": [{"thread_key": "thread:private", "message_id": "msg-1"}],
                    "scope_bucket": "user_private",
                },
                ["private_or_stale_rows_visible_to_guard", "path_blocked_private_or_stale"],
            ),
            (
                "stale",
                {
                    "route_id": "route:stale",
                    "route_terms": ["associative path walker"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                    "freshness": "stale",
                },
                ["private_or_stale_rows_visible_to_guard", "path_blocked_private_or_stale"],
            ),
            (
                "source-free",
                {
                    "route_terms": ["slime mold", "associative path walker"],
                    "scope_bucket": "project",
                },
                ["source_free_candidates_will_evaporate", "source_free_path_evaporated"],
            ),
        ]

        for label, candidate, reason_codes in cases:
            with self.subTest(label=label):
                diagnostic = build_associative_path_diagnostic(
                    query="slime mold exploratory recall",
                    candidates=[candidate],
                    semantic_bridge_rows=[
                        {
                            "candidate_id": f"bridge:{label}",
                            "from_terms": ["slime mold", "exploratory recall"],
                            "to_terms": ["associative path walker"],
                            "scope_bucket": candidate.get("scope_bucket", "project"),
                            "source_refs": candidate.get("source_refs", []),
                        }
                    ],
                )

                self.assertEqual(diagnostic["candidate_count"], 0)
                self.assertEqual(diagnostic["next_actions"][0]["id"], "tighten_cue_or_continue_without_apw")
                self.assertFalse(
                    any(
                        str(action.get("id", "")).startswith("open_apw_source_candidate")
                        for action in diagnostic["next_actions"]
                    )
                )
                for reason_code in reason_codes:
                    self.assertIn(reason_code, diagnostic["reason_codes"])
                if label == "source-free":
                    self.assertNotIn("path_blocked_private_or_stale", diagnostic["reason_codes"])
                self.assertGreaterEqual(diagnostic["metrics"]["blocked_or_evaporated_count"], 1)

    def test_diagnostic_does_not_count_materialized_navigation_sidecar_twice(self) -> None:
        bridge = {
            "candidate_id": "bridge:apw-cn",
            "from_terms": ["黏菌", "联想回忆", "探索算法"],
            "to_terms": ["associative path walker", "routing exploration"],
            "source_refs": [{"thread_key": "fixture:path-walker", "source_id": "src-apw"}],
            "scope_bucket": "project",
        }
        navigation = {
            "route_id": "route:apw-cn",
            "candidate_id": "bridge:apw-cn",
            "route_terms": ["associative path walker", "routing exploration"],
            "thread_key": "thread:apw",
            "source_refs": [{"thread_key": "fixture:path-walker", "source_id": "src-apw"}],
            "scope_bucket": "project",
        }
        pack = build_associative_path_input_pack(
            query="黏菌 联想回忆 探索算法",
            semantic_bridge_rows=[bridge],
            navigation_rows=[navigation],
        )

        diagnostic = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            input_pack=pack,
        )

        self.assertEqual(pack["metrics"]["candidate_count"], 1)
        self.assertEqual(pack["metrics"]["navigation_row_count"], 1)
        self.assertEqual(diagnostic["candidate_count"], 1)
        self.assertEqual(
            [candidate.get("route_id") for candidate in diagnostic["top_candidates"]],
            ["route:apw-cn"],
        )

    def test_current_clean_source_candidates_feed_diagnostic_direct_reopen_action(self) -> None:
        clean = self._write_clean_messages(
            [
                {
                    "message_id": "msg-clean-apw",
                    "turn_id": "turn-clean-apw",
                    "turn_index": 7,
                    "source_id": "src-clean-apw",
                    "source_line": 31,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "那条黏菌联想回忆探索算法路线需要通过 APW reopen clean source 才能使用。",
                }
            ]
        )

        diagnostic = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=clean,
        )
        encoded = json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)

        self.assertEqual(diagnostic["decision"], "route_candidates")
        self.assertEqual(diagnostic["metrics"]["source_reopenable_candidate_count"], 1)
        self.assertEqual(
            diagnostic["metrics"]["candidate_source_counts"]["current_clean_source"],
            1,
        )
        candidate = diagnostic["top_candidates"][0]
        self.assertEqual(candidate["candidate_source_kind"], "current_clean_source")
        self.assertEqual(candidate["matched_terms"], ["黏菌", "联想回忆", "探索算法"])
        action = diagnostic["next_actions"][0]
        self.assertEqual(action["id"], "open_apw_source_candidate_1")
        self.assertEqual(action["tool_name"], "get_turn_context")
        self.assertIn("aippocampus search --open-current-source", action["command"])
        self.assertEqual(
            action["source_reopen_args"],
            {
                "message_id": "msg-clean-apw",
                "turn_id": "turn-clean-apw",
                "turn_index": 7,
                "line": 31,
            },
        )
        self.assertNotIn("thread_key", action["source_reopen_args"])
        self.assertNotIn(str(self.root), encoded)

    def test_private_current_clean_source_candidates_stay_guarded(self) -> None:
        clean = self._write_clean_messages(
            [
                {
                    "message_id": "msg-private-apw",
                    "turn_id": "turn-private-apw",
                    "source_line": 11,
                    "scope_labels": ["user_private"],
                    "text": "黏菌 联想回忆 探索算法 private note",
                }
            ]
        )

        diagnostic = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=clean,
        )

        self.assertEqual(diagnostic["decision"], "abstain")
        self.assertEqual(diagnostic["candidate_count"], 0)
        self.assertIn("path_blocked_private_or_stale", diagnostic["reason_codes"])
        self.assertEqual(diagnostic["next_actions"][0]["id"], "tighten_cue_or_continue_without_apw")

    def test_why_recall_apw_sidecar_is_opt_in(self) -> None:
        pack = build_associative_path_input_pack(
            query="黏菌 联想回忆 探索算法",
            candidates=[
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            semantic_bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌"],
                    "to_terms": ["associative path walker"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
        )
        default_payload = why.recall_diagnostic_report(
            cue="黏菌 联想回忆 探索算法",
            mode="why-recall",
            cwd=self.root,
            clean_source_dir=self.root / "missing-clean-source",
            associative_path_input_pack=pack,
        )
        opt_in = why.recall_diagnostic_report(
            cue="黏菌 联想回忆 探索算法",
            mode="why-recall",
            cwd=self.root,
            clean_source_dir=self.root / "missing-clean-source",
            include_associative_path_diagnostics=True,
            associative_path_input_pack=pack,
        )

        self.assertNotIn("associative_path_diagnostics", default_payload)
        self.assertIn("associative_path_walker", opt_in["searched_surfaces"])
        self.assertEqual(opt_in["associative_path_diagnostics"]["decision"], "route_candidates")
        self.assertFalse(opt_in["privacy_boundary"]["associative_path_walker_changed_default_ranking"])

if __name__ == "__main__":
    unittest.main()
