from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.recall import (
    agent_continuity,
    agent_continuity_cli_support,
    associative_path_fallback,
)
from aippocampus_runtime.recall.associative_path_inputs import build_associative_path_diagnostic


class AgentRecallApwFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(
            os.environ,
            {associative_path_fallback.PROMOTION_MODE_ENV: "semi_default_recovery"},
        )
        self.env_patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clean = self.root / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self.registry = self.root / "registry"
        self.registry.mkdir()
        message = {
            "message_id": "msg-apw",
            "turn_id": "turn-apw",
            "turn_index": 4,
            "source_id": "src-apw",
            "source_line": 12,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "Runtime notes: associative path walker can reopen a guarded source route.",
        }
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(message, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "turn_id": "turn-apw",
                        "turn_index": 4,
                        "message_ids": ["msg-apw"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write_jsonl(self, name: str, rows: list[dict[str, object]]) -> None:
        path = self.root / ".aippocampus" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _append_clean_message(self, row: dict[str, object]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "turn_id": row.get("turn_id"),
                        "turn_index": row.get("turn_index"),
                        "message_ids": [row.get("message_id") or row.get("id")],
                        "assistant_phase": row.get("phase") or row.get("role"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def _write_apw_sidecars(
        self,
        *,
        with_source_refs: bool = True,
        freshness: str = "current",
    ) -> None:
        refs = (
            [
                {
                    "source_id": "src-apw",
                    "message_id": "msg-apw",
                    "turn_id": "turn-apw",
                    "turn_index": 4,
                }
            ]
            if with_source_refs
            else []
        )
        self._write_jsonl(
            "semantic-bridges.jsonl",
            [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker"],
                    "source_refs": refs,
                    "scope_bucket": "project",
                }
            ],
        )
        self._write_jsonl(
            "navigation-potential.jsonl",
            [
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker"],
                    "source_refs": refs,
                    "scope_bucket": "project",
                    "freshness": freshness,
                }
            ],
        )

    def _recall(self, *, include_apw: bool) -> dict[str, object]:
        return agent_continuity.recall(
            "黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            include_associative_fallback=include_apw,
            associative_path_sidecar_dir=self.root / ".aippocampus",
        )

    def _assert_opened_message(
        self,
        deepened: dict[str, object],
        *,
        message_id: str,
        required_text: str,
    ) -> None:
        self.assertEqual(deepened["status"], "ok")
        result = deepened["result"]
        self.assertEqual(result["source_refs"][0]["message_id"], message_id)
        window_text = "\n".join(
            str(message.get("text") or "")
            for message in result["source_window"]["messages"]
            if isinstance(message, dict)
        )
        self.assertIn(required_text, window_text)

    def test_semidefault_apw_recovery_runs_for_no_route_when_candidate_input_exists(self) -> None:
        self._write_apw_sidecars()

        payload = self._recall(include_apw=False)

        self.assertEqual(payload["status"], "no_routes")
        policy = payload["associative_path_policy"]
        self.assertEqual(policy["current_build_posture"], "semi_default_recovery")
        self.assertTrue(policy["run_fallback"])
        self.assertEqual(policy["run_reason"], "apw_semi_default_recovery")
        fallback = payload["associative_path_fallback"]
        self.assertIsInstance(fallback, dict)
        self.assertEqual(fallback["status"], "route_candidate")
        self.assertFalse(fallback["opt_in_required"])
        self.assertFalse(fallback["applied_to_default_ranking"])
        self.assertEqual(fallback["route_choice_posture"], "associative_path_semi_default_recovery")
        self.assertEqual(len(payload["deepen_requests"]), 1)
        self.assertTrue(payload["metrics"]["associative_path_fallback_semidefault_attempted"])

    def test_semidefault_apw_recovery_stays_quiet_without_candidate_input(self) -> None:
        payload = self._recall(include_apw=False)

        self.assertEqual(payload["status"], "no_routes")
        policy = payload["associative_path_policy"]
        self.assertEqual(policy["current_build_posture"], "semi_default_recovery")
        self.assertFalse(policy["apw_candidate_input_available"])
        self.assertFalse(policy["run_fallback"])
        self.assertEqual(policy["run_reason"], "apw_candidate_input_missing")
        self.assertIsNone(payload.get("associative_path_fallback"))
        self.assertEqual(payload["deepen_requests"], [])

    def test_opt_in_policy_rolls_back_semidefault_recovery(self) -> None:
        self._write_apw_sidecars()
        with patch.dict(
            os.environ,
            {associative_path_fallback.PROMOTION_MODE_ENV: "opt_in"},
        ):
            default_payload = self._recall(include_apw=False)
            opt_in_payload = self._recall(include_apw=True)

        self.assertEqual(default_payload["associative_path_policy"]["promotion_mode"], "opt_in")
        self.assertEqual(
            default_payload["associative_path_policy"]["run_reason"],
            "apw_fallback_requires_explicit_opt_in",
        )
        self.assertIsNone(default_payload.get("associative_path_fallback"))
        fallback = opt_in_payload["associative_path_fallback"]
        self.assertEqual(fallback["status"], "route_candidate")
        self.assertTrue(fallback["opt_in_required"])
        self.assertEqual(fallback["route_choice_posture"], "associative_path_opt_in_fallback")

    def test_opt_in_apw_fallback_becomes_request_index_source_reopen_action(self) -> None:
        self._write_apw_sidecars()

        payload = self._recall(include_apw=True)

        self.assertEqual(payload["status"], "no_routes")
        fallback = payload["associative_path_fallback"]
        self.assertIsInstance(fallback, dict)
        self.assertEqual(fallback["status"], "route_candidate")
        self.assertTrue(fallback["opt_in_required"])
        self.assertEqual(fallback["request_index"], 1)
        self.assertEqual(len(payload["deepen_requests"]), 1)

        cache_path = self.root / "last-recall.json"
        cache_written = agent_continuity_cli_support.write_last_recall_cache(
            payload["deepen_requests"],
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            macro_state_path=None,
            project="AIppocampus",
            max_matches=5,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )
        selector_id = agent_continuity_cli_support.write_recall_selector_snapshot(cache_path)
        payload["last_recall_cache_available"] = cache_written
        payload["recall_selector_id"] = selector_id

        public = agent_continuity_cli_support.public_recall_projection(
            payload,
            query="黏菌 联想回忆 探索算法",
        )
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)

        self.assertEqual(public["foreground_action"]["id"], "deepen_associative_path_fallback")
        self.assertEqual(public["foreground_action"]["tool_name"], "agent_deepen")
        self.assertEqual(public["foreground_action"]["arguments"]["request_index"], 1)
        self.assertEqual(public["foreground_action"]["arguments"]["recall_selector"], selector_id)
        self.assertIn("--recall-selector", public["foreground_action"]["command"])
        self.assertIn("associative_path_opt_in_fallback", public["foreground_action"]["route_choice_posture"])
        self.assertEqual(public["associative_path_policy"]["current_build_posture"], "semi_default_recovery")
        self.assertTrue(public["associative_path_fallback"]["opt_in_required"])
        self.assertIn("search_registry_sources_for_original_cue_anchors", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg-apw", encoded)
        self.assertEqual(executable_command_violations(public), [])

        handle, _context = agent_continuity_cli_support.handle_from_last_recall_cache(
            request_index=1,
            path=cache_path,
        )
        deepened = agent_continuity.deepen(
            handle,
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
        )
        self._assert_opened_message(
            deepened,
            message_id="msg-apw",
            required_text="associative path walker",
        )

    def test_current_clean_source_apw_parity_reaches_compact_fallback_action(self) -> None:
        self._append_clean_message(
            {
                "message_id": "msg-clean-control",
                "turn_id": "turn-clean-apw",
                "turn_index": 8,
                "source_id": "src-clean-control",
                "source_line": 20,
                "role": "developer",
                "phase": "commentary",
                "source_use_class": "control_only",
                "text": "<goal_context> 黏菌 联想回忆 探索算法 should not be selected as APW foreground source.",
            }
        )
        self._append_clean_message(
            {
                "message_id": "msg-clean-apw",
                "turn_id": "turn-clean-apw",
                "turn_index": 8,
                "source_id": "src-clean-apw",
                "source_line": 21,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "公开 fixture 锚点：黏菌 联想回忆 探索算法，供 APW parity gate 追踪。",
            }
        )

        diagnostic = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=self.clean,
        )
        self.assertEqual(diagnostic["decision"], "route_candidates")
        self.assertEqual(
            diagnostic["metrics"]["candidate_source_counts"]["current_clean_source"],
            1,
        )
        self.assertEqual(diagnostic["metrics"]["goal_context_filtered_count"], 1)
        self.assertEqual(diagnostic["top_candidates"][0]["source_refs"][0]["message_id"], "msg-clean-apw")

        payload = self._recall(include_apw=True)
        policy = payload["associative_path_policy"]
        self.assertTrue(policy["run_fallback"])
        self.assertTrue(policy["apw_candidate_input_available"])
        self.assertNotEqual(policy["run_reason"], "apw_candidate_input_missing")
        fallback = payload["associative_path_fallback"]
        self.assertEqual(fallback["status"], "route_candidate")
        self.assertEqual(fallback["candidate_source_kind"], "current_clean_source")
        self.assertEqual(fallback["matched_cue_anchors"], ["黏菌", "联想回忆", "探索算法"])
        self.assertEqual(fallback["source_ref_digest"], payload["deepen_requests"][-1]["source_ref_digest"])
        self.assertEqual(
            fallback["apw_route_identity"]["source_ref_digest"],
            payload["deepen_requests"][-1]["apw_route_identity"]["source_ref_digest"],
        )
        self.assertIn("APW source route", fallback["label"])
        self.assertNotIn("associative_path_input_pack_empty", fallback["reason_codes"])

        cache_path = self.root / "last-recall-clean-source.json"
        cache_written = agent_continuity_cli_support.write_last_recall_cache(
            payload["deepen_requests"],
            query="黏菌 联想回忆 探索算法",
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
            macro_state_path=None,
            project="AIppocampus",
            max_matches=5,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )
        selector_id = agent_continuity_cli_support.write_recall_selector_snapshot(cache_path)
        payload["last_recall_cache_available"] = cache_written
        payload["recall_selector_id"] = selector_id

        public = agent_continuity_cli_support.public_recall_projection(
            payload,
            query="黏菌 联想回忆 探索算法",
        )
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        action = public["foreground_action"]
        self.assertEqual(action["id"], "deepen_associative_path_fallback")
        self.assertIn("APW source route", action["label"])
        self.assertIn("黏菌 / 联想回忆 / 探索算法", action["why"])
        self.assertEqual(
            action["apw_route_identity"]["source_ref_digest"],
            fallback["source_ref_digest"],
        )
        self.assertEqual(public["associative_path_fallback"]["candidate_source_kind"], "current_clean_source")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg-clean-apw", encoded)
        self.assertEqual(executable_command_violations(public), [])

        handle, context = agent_continuity_cli_support.handle_from_last_recall_cache(
            request_index=int(fallback["request_index"]),
            path=cache_path,
        )
        self.assertEqual(
            context["apw_route_identity"]["source_ref_digest"],
            fallback["source_ref_digest"],
        )
        deepened = agent_continuity.deepen(
            handle,
            cwd=self.root,
            clean_source_dir=self.clean,
            registry_dir=self.registry,
        )
        deepened["apw_route_identity"] = context["apw_route_identity"]
        deepened["result"]["apw_route_identity"] = context["apw_route_identity"]
        self._assert_opened_message(
            deepened,
            message_id="msg-clean-apw",
            required_text="黏菌 联想回忆 探索算法",
        )
        compact_deepened = compact_agent_deepen_payload(
            deepened,
            request_index=int(fallback["request_index"]),
            last_recall=True,
        )
        self.assertEqual(
            compact_deepened["apw_route_identity"]["source_ref_digest"],
            fallback["source_ref_digest"],
        )
        self.assertIn("黏菌 联想回忆 探索算法", compact_deepened["primary_source_snippet"]["text"])
        self.assertNotIn("<goal_context>", compact_deepened["primary_source_snippet"]["text"])

    def test_opt_in_apw_fallback_preserves_shadowed_source_shape_posture(self) -> None:
        self._write_apw_sidecars(freshness="unknown")

        payload = self._recall(include_apw=True)

        fallback = payload["associative_path_fallback"]

        self.assertEqual(fallback["status"], "route_candidate")
        self.assertEqual(fallback["route_posture"], "shadowed")
        self.assertEqual(fallback["action_grammar"], "direction_with_ref")
        self.assertIn("freshness_unknown", fallback["source_shape_guard_reasons"])
        self.assertIn("check_currentness", fallback["risk_flags"])

    def test_cli_apw_fallback_flag_returns_compact_action(self) -> None:
        self._write_apw_sidecars()
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.root / "cli-last-recall.json"),
            associative_path_fallback.PROMOTION_MODE_ENV: "semi_default_recovery",
        }

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "黏菌 联想回忆 探索算法",
                "--cwd",
                str(self.root),
                "--clean-source-dir",
                str(self.clean),
                "--registry-dir",
                str(self.registry),
                "--apw-fallback",
                "--apw-sidecar-dir",
                str(self.root / ".aippocampus"),
                "--json",
            ],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["foreground_action"]["id"], "deepen_associative_path_fallback")
        self.assertEqual(payload["associative_path_fallback"]["status"], "route_candidate")
        self.assertNotIn("source_refs", encoded)
        self.assertEqual(executable_command_violations(payload), [])

    def test_cli_semidefault_apw_fallback_returns_compact_action_without_flag(self) -> None:
        self._write_apw_sidecars()
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.root / "cli-last-recall.json"),
            associative_path_fallback.PROMOTION_MODE_ENV: "semi_default_recovery",
        }

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "黏菌 联想回忆 探索算法",
                "--cwd",
                str(self.root),
                "--clean-source-dir",
                str(self.clean),
                "--registry-dir",
                str(self.registry),
                "--apw-sidecar-dir",
                str(self.root / ".aippocampus"),
                "--json",
            ],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["foreground_action"]["id"], "deepen_associative_path_fallback")
        self.assertEqual(
            payload["foreground_action"]["route_choice_posture"],
            "associative_path_semi_default_recovery",
        )
        self.assertEqual(payload["associative_path_policy"]["promotion_mode"], "semi_default_recovery")
        self.assertFalse(payload["associative_path_fallback"]["opt_in_required"])
        self.assertEqual(executable_command_violations(payload), [])

    def test_cli_current_clean_source_apw_fallback_uses_diagnostic_candidates(self) -> None:
        self._append_clean_message(
            {
                "message_id": "msg-cli-clean-apw",
                "turn_id": "turn-cli-clean-apw",
                "turn_index": 9,
                "source_id": "src-cli-clean-apw",
                "source_line": 27,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "公开 fixture 锚点：黏菌 联想回忆 探索算法，供 CLI APW parity gate 追踪。",
            }
        )
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.root / "cli-clean-last-recall.json"),
            associative_path_fallback.PROMOTION_MODE_ENV: "semi_default_recovery",
        }

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "黏菌 联想回忆 探索算法",
                "--cwd",
                str(self.root),
                "--clean-source-dir",
                str(self.clean),
                "--registry-dir",
                str(self.registry),
                "--apw-fallback",
                "--json",
            ],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertTrue(payload["associative_path_policy"]["apw_candidate_input_available"])
        self.assertNotEqual(payload["associative_path_policy"]["run_reason"], "apw_candidate_input_missing")
        self.assertEqual(payload["associative_path_fallback"]["status"], "route_candidate")
        self.assertEqual(payload["associative_path_fallback"]["candidate_source_kind"], "current_clean_source")
        self.assertEqual(payload["foreground_action"]["id"], "deepen_associative_path_fallback")
        self.assertIn("黏菌 / 联想回忆 / 探索算法", payload["foreground_action"]["why"])
        self.assertNotIn("source_refs", encoded)
        self.assertEqual(executable_command_violations(payload), [])

        deepen_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "deepen",
                "--request",
                str(payload["foreground_action"]["arguments"]["request_index"]),
                "--recall-selector",
                str(payload["foreground_action"]["arguments"]["recall_selector"]),
                "--json",
                "--detail",
                "full",
            ],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(deepen_proc.returncode, 0, deepen_proc.stderr)
        deepened = json.loads(deepen_proc.stdout)
        self._assert_opened_message(
            deepened,
            message_id="msg-cli-clean-apw",
            required_text="黏菌 联想回忆 探索算法",
        )

    def test_source_free_apw_bridge_abstains_instead_of_emitting_fake_action(self) -> None:
        self._write_apw_sidecars(with_source_refs=False)

        payload = self._recall(include_apw=True)

        fallback = payload["associative_path_fallback"]
        self.assertIsInstance(fallback, dict)
        self.assertEqual(fallback["status"], "abstained")
        self.assertIn("apw_no_route_candidate", fallback["reason_codes"])
        self.assertIn("source_free_candidates_will_evaporate", fallback["reason_codes"])
        self.assertEqual(payload["deepen_requests"], [])

if __name__ == "__main__":
    unittest.main()
