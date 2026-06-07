from __future__ import annotations

import inspect
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import active_recall as active_recall  # noqa: E402
from aippocampus_runtime.recall import active_recall as packaged_active_recall  # noqa: E402
from aippocampus_runtime.recall import active_recall_lock  # noqa: E402
from aippocampus_runtime.recall import retrieval as retrieval  # noqa: E402


class ActiveRecallTests(unittest.TestCase):
    def test_main_uses_package_apis_without_health_or_search_script_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            old_argv = sys.argv[:]
            sys.argv = [
                "active_recall.py",
                "继续刚才那个状态",
                "--cwd",
                str(cwd),
                "--search",
                "always",
                "--json",
            ]
            try:
                with mock.patch.object(
                    packaged_active_recall,
                    "health_report",
                    return_value={
                        "status": "ok",
                        "index": {"stale": False},
                        "segments": {"exists": False, "needed": False},
                        "checkpoint": {"due": False},
                        "graphify": {"stale": False},
                        "recommended_actions": [],
                    },
                ) as health, mock.patch.object(
                    packaged_active_recall,
                    "search_rollout_payload",
                    return_value={"source": "package-api", "matches": []},
                ) as rollout_search, mock.patch.object(
                    packaged_active_recall, "search_segments_payload"
                ) as segment_search:
                    with mock.patch("sys.stdout") as stdout:
                        code = packaged_active_recall.main()
            finally:
                sys.argv = old_argv

        self.assertEqual(code, 0)
        health.assert_called_once_with(cwd)
        rollout_search.assert_called_once()
        options = rollout_search.call_args.args[0]
        self.assertEqual(options.cwd, cwd)
        self.assertTrue(options.build_index)
        segment_search.assert_not_called()
        self.assertFalse(hasattr(packaged_active_recall, "run_json"))
        output = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertTrue(json.loads(output)["searched"])

    def test_segment_search_needed_does_not_trigger_foreground_segment_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            with mock.patch.object(
                packaged_active_recall,
                "health_report",
                return_value={
                    "status": "ok",
                    "index": {"stale": False},
                    "segments": {"exists": False, "needed": True, "stale": False},
                    "checkpoint": {"due": False},
                    "graphify": {"stale": False},
                    "recommended_actions": [],
                },
            ), mock.patch.object(
                packaged_active_recall,
                "search_segments_payload",
                return_value={
                    "ok": False,
                    "status": "segments_unavailable",
                    "query_terms": [],
                    "matched_anchors": [],
                    "rag_context": [],
                    "matches": [],
                    "segment_errors": [],
                },
            ) as segment_search, mock.patch.object(
                packaged_active_recall, "search_rollout_payload"
            ) as rollout_search:
                with mock.patch("sys.stdout"):
                    code = packaged_active_recall.main(
                        [
                            "继续刚才那个状态",
                            "--cwd",
                            str(cwd),
                            "--search",
                            "always",
                            "--json",
                        ]
                    )

        self.assertEqual(code, 0)
        segment_search.assert_called_once()
        options = segment_search.call_args.args[0]
        self.assertFalse(options.build_segments)
        rollout_search.assert_not_called()

    def test_profile_prompt_searches_with_stale_checkpoint_and_alias_terms(self) -> None:
        prompt = "你知道我的简历和领英资料吗？"
        health = {
            "index": {"stale": True},
            "checkpoint": {"due": True},
            "recommended_actions": [],
        }

        decision = retrieval.active_recall_decision(prompt, [], health)
        query_terms = active_recall.active_recall_query_terms(prompt)
        search_terms = active_recall.search_terms_from_query(query_terms, prompt)

        self.assertEqual(decision["decision"], "search")
        self.assertIn("personal-profile recall cue", " ".join(decision["reasons"]))
        self.assertIn("resume", query_terms)
        self.assertIn("LinkedIn", query_terms)
        self.assertIn("resume", search_terms)
        self.assertIn("LinkedIn", search_terms)

    def test_life_wide_work_prompt_searches_with_stale_checkpoint_and_alias_terms(self) -> None:
        prompt = "最近工作上那些摩擦和压力，我们后来怎么处理比较好？"
        health = {
            "index": {"stale": True},
            "checkpoint": {"due": True},
            "recommended_actions": [],
        }

        decision = retrieval.active_recall_decision(prompt, [], health)
        query_terms = active_recall.active_recall_query_terms(prompt)
        search_terms = active_recall.search_terms_from_query(query_terms, prompt)

        self.assertEqual(decision["decision"], "search")
        self.assertIn("life-wide recall cue", " ".join(decision["reasons"]))
        self.assertIn("workflow friction", query_terms)
        self.assertIn("work pressure", query_terms)
        self.assertIn("burnout", query_terms)
        self.assertIn("workflow friction", search_terms)
        self.assertIn("work pressure", search_terms)

    def test_recent_work_status_alone_does_not_become_life_wide_route(self) -> None:
        prompt = "最近工作进度怎么样？"
        health = {
            "index": {"stale": False},
            "checkpoint": {"due": False},
            "recommended_actions": [],
        }

        decision = retrieval.active_recall_decision(prompt, [], health)
        query_terms = active_recall.active_recall_query_terms(prompt)

        self.assertEqual(decision["decision"], "skip")
        self.assertNotIn("workflow friction", query_terms)
        self.assertNotIn("work pressure", query_terms)

    def test_probe_read_lock_is_navigation_only_and_reopen_is_source_backed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry" / "threads.json"
            messages = root / "clean-source" / "messages.jsonl"
            registry.parent.mkdir()
            messages.parent.mkdir()
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:old",
                                "paths": {"clean_source_messages_jsonl": str(messages)},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            messages.write_text(
                json.dumps(
                    {
                        "message_id": "msg-1",
                        "turn_id": "turn-1",
                        "source_line": 9,
                        "role": "assistant",
                        "phase": "final_answer",
                        "text": "Only reopen may reveal this sourced sentence.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            lock_path = root / "active_recall_locks.json"
            prompt = "继续那个 SECRET_TOKEN=abc123 的语义判断"

            probe = packaged_active_recall.active_recall_probe(
                prompt=prompt,
                cwd=root,
                lock_path=lock_path,
                registry_path=registry,
                thread_id="thread-a",
                topic_epoch="epoch-a",
                use_lock=True,
            )
            lock_id = str((probe.get("lock") or {}).get("lock_id") or "")
            ready = active_recall_lock.enrich_recall_lock(
                lock_path,
                lock_id=lock_id,
                candidate_refs=[{"thread_key": "session:old", "message_id": "msg-1"}],
                route_reasons=["background semantic route"],
                state="ready",
            )
            read = packaged_active_recall.active_recall_read_lock(
                lock_path=lock_path,
                lock_id=lock_id,
                topic_epoch="epoch-a",
                registry_path=registry,
            )
            reopened = packaged_active_recall.active_recall_reopen_lock(
                lock_path=lock_path,
                lock_id=lock_id,
                registry_path=registry,
                max_matches=3,
            )
            raw_read = json.dumps(read, ensure_ascii=False)

        self.assertEqual(probe["support_level"], "scent")
        self.assertEqual(ready["support_level"], "scent")
        self.assertEqual(read["lock"]["state"], "ready")
        self.assertEqual(read["lock"]["lock_version"], ready["lock_version"])
        self.assertEqual(read["lock"]["enrichment_generation"], ready["enrichment_generation"])
        self.assertEqual(read["consumer_metrics"]["read_count"], 1)
        self.assertTrue(read["source_reopen_required"])
        self.assertNotIn("SECRET_TOKEN", raw_read)
        self.assertNotIn("abc123", raw_read)
        self.assertNotIn("Only reopen may reveal", raw_read)
        self.assertEqual(reopened["support_level"], "evidence")
        self.assertEqual(
            reopened["matches"][0]["text"],
            "Only reopen may reveal this sourced sentence.",
        )

    def test_metrics_mode_reports_public_safe_lock_roi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_path = root / "active_recall_locks.json"
            lock = active_recall_lock.start_or_update_recall_lock(
                lock_path,
                prompt="继续 SECRET_TOKEN=abc123 的旧判断",
                thread_id="thread-a",
                workspace=root,
                topic_epoch="epoch-a",
                registry_path=None,
                state="pending",
            )
            active_recall_lock.read_recall_lock(lock_path, str(lock["lock_id"]))

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = packaged_active_recall.main(
                    ["--mode", "metrics", "--lock-path", str(lock_path), "--json"]
                )
            payload = json.loads(stdout.getvalue())
            raw_payload = stdout.getvalue()

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_active_recall_lock_roi")
        self.assertEqual(payload["lock_count"], 1)
        self.assertEqual(payload["lock_pull_count"], 1)
        self.assertTrue(payload["source_boundary"]["aggregate_counts_only"])
        self.assertNotIn("SECRET_TOKEN", raw_payload)
        self.assertNotIn("abc123", raw_payload)
        self.assertNotIn(str(root), raw_payload)

    def test_context_mode_surfaces_agent_self_notes_without_hook_autoinjection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            notes_path.write_text(
                json.dumps(
                    {
                        "kind": "agent_self_note",
                        "schema_version": 1,
                        "note_id": "asn-test",
                        "created_at": "2026-06-07T00:00:00Z",
                        "thread_key": "session:old",
                        "source_refs": [
                            {
                                "thread_key": "session:old",
                                "message_id": "msg-stance",
                                "line": 19,
                            }
                        ],
                        "note_text": "这次的状态是先找设计意图，再动手。",
                        "support_level": "scent",
                        "action_grammar": "direction_only",
                        "memory_surface": "memory_atmosphere",
                        "source_reopen_required_before_claim": True,
                        "claims_user_fact": False,
                        "claims_world_fact": False,
                        "claims_source_fact": False,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            context_fn = getattr(packaged_active_recall, "active_recall_context", None)
            self.assertIsNotNone(context_fn, "active_recall_context API should exist")
            assert context_fn is not None
            result = context_fn(
                prompt="我想找回上次我在这个问题前的状态",
                cwd=root,
                agent_self_notes_path=notes_path,
                max_matches=3,
            )

        self.assertTrue(result["agent_initiated_recall"])
        self.assertEqual(result["decision"], "context")
        self.assertFalse(result["source_boundary"]["passive_hook_required"])
        self.assertTrue(result["source_boundary"]["source_reopen_required_for_facts"])
        self.assertEqual(result["surface_counts"]["agent_self_notes"], 1)
        self.assertEqual(result["memory_atmosphere"][0]["active_recall_surface"], "agent_self_note")
        self.assertEqual(result["memory_atmosphere"][0]["action_grammar"], "direction_only")
        self.assertFalse(result["memory_atmosphere"][0]["trust_contract"]["treat_as_fact"])
        self.assertEqual(result["source_reopen_routes"][0]["message_id"], "msg-stance")

    def test_context_mode_cli_is_public_safe_and_omits_raw_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            notes_path.write_text(
                json.dumps(
                    {
                        "kind": "agent_self_note",
                        "schema_version": 1,
                        "note_id": "asn-secret-test",
                        "created_at": "2026-06-07T00:00:00Z",
                        "thread_key": "session:old",
                        "source_refs": [{"thread_key": "session:old", "message_id": "msg-safe"}],
                        "note_text": "这次我先守住 source boundary。",
                        "support_level": "scent",
                        "action_grammar": "direction_only",
                        "memory_surface": "memory_atmosphere",
                        "source_reopen_required_before_claim": True,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                try:
                    code = packaged_active_recall.main(
                        [
                            "--mode",
                            "context",
                            "我想找回状态 SECRET_TOKEN=abc123",
                            "--cwd",
                            str(root),
                            "--agent-self-notes",
                            str(notes_path),
                            "--json",
                        ]
                    )
                except SystemExit as exc:
                    code = int(exc.code or 0)
            raw = stdout.getvalue()
            payload = json.loads(raw) if raw.strip() else {}

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_agent_initiated_recall_context")
        self.assertTrue(payload["agent_initiated_recall"])
        self.assertEqual(payload["surface_counts"]["agent_self_notes"], 1)
        self.assertNotIn("SECRET_TOKEN", raw)
        self.assertNotIn("abc123", raw)
        self.assertNotIn(str(root), raw)
        self.assertNotIn("prompt", payload)

    def test_context_mode_redacts_preexisting_self_note_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            notes_path.write_text(
                json.dumps(
                    {
                        "kind": "agent_self_note",
                        "schema_version": 1,
                        "note_id": "asn-manual-secret",
                        "created_at": "2026-06-07T00:00:00Z",
                        "thread_key": "session:old",
                        "source_refs": [{"thread_key": "session:old", "message_id": "msg-safe"}],
                        "note_text": r"token=abc123 and E:\private\workspace\note.md",
                        "support_level": "scent",
                        "action_grammar": "direction_only",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = packaged_active_recall.active_recall_context(
                prompt="我想找回上次状态",
                cwd=root,
                agent_self_notes_path=notes_path,
                max_matches=3,
            )
            raw = json.dumps(result, ensure_ascii=False)

        self.assertEqual(result["surface_counts"]["agent_self_notes"], 1)
        self.assertNotIn("abc123", raw)
        self.assertNotIn(r"E:\private\workspace\note.md", raw)
        self.assertIn("<redacted:secret>", raw)
        self.assertIn("<redacted:local-path>", raw)

    def test_context_mode_surfaces_dream_working_memory_as_candidate_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            working_memory_path = root / "working_memory.jsonl"
            working_memory_path.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_working_memory",
                        "status": "active",
                        "route": "use_with_source",
                        "candidate_key": "wm-dream-stance",
                        "candidate_type": "dream_hypothesis",
                        "review_state": "source_adjudicated",
                        "title": "Foreground stance source boundary",
                        "summary": "Dream hypothesis only; the agent should reopen source before claims.",
                        "recommendation": "Use as route direction only.",
                        "confidence": 0.82,
                        "trigger_terms": ["状态", "source boundary"],
                        "source_refs": [
                            {
                                "thread_key": "session:dream",
                                "message_id": "msg-dream",
                                "line": 55,
                            }
                        ],
                        "truth_boundary": "dream_hypothesis_not_source_fact",
                        "foreground_use": {"strong_claim_requires_source_reopen": True},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            context_fn = getattr(packaged_active_recall, "active_recall_context", None)
            self.assertIsNotNone(context_fn, "active_recall_context API should exist")
            assert context_fn is not None
            self.assertIn("working_memory_path", inspect.signature(context_fn).parameters)

            result = context_fn(
                prompt="我想找回上次这个 source boundary 状态",
                cwd=root,
                working_memory_path=working_memory_path,
                max_matches=3,
            )

        self.assertEqual(result["surface_counts"]["working_memory"], 1)
        self.assertEqual(result["surface_counts"]["dream"], 1)
        self.assertEqual(result["working_continuity_brief"][0]["candidate_type"], "dream_hypothesis")
        self.assertEqual(result["working_continuity_brief"][0]["action_grammar"], "direction_with_ref")
        self.assertFalse(result["working_continuity_brief"][0]["trust_contract"]["treat_as_fact"])
        self.assertEqual(result["source_reopen_routes"][0]["message_id"], "msg-dream")


if __name__ == "__main__":
    unittest.main()
