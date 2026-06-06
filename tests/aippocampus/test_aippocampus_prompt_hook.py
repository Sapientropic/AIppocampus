from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.dream import live_shadow_ab as dream_shadow  # noqa: E402
from aippocampus_runtime.hooks import prompt as hook  # noqa: E402
from aippocampus_runtime.navigation import concept_graph as concept_graph  # noqa: E402
from aippocampus_runtime.recall import ambient_cache as thread_cache  # noqa: E402
from aippocampus_runtime.recall import prompt_cues as recall_cues  # noqa: E402
from aippocampus_runtime.recall import semantic_cue_cache as cue_cache  # noqa: E402
from tests.aippocampus.redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)


class AmbientRecallHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_semantic_gate = os.environ.get("AIPPOCAMPUS_SEMANTIC_GATE")
        os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = "off"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.old = self.root / "old-thread"
        self.index_dir = self.old / ".aippocampus"
        self.index_dir.mkdir(parents=True)
        self.sqlite = self.index_dir / "source_index.sqlite"
        self._write_sqlite()
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self._write_registry()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_semantic_gate is None:
            os.environ.pop("AIPPOCAMPUS_SEMANTIC_GATE", None)
        else:
            os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = self.old_semantic_gate

    def test_prompt_hook_keeps_decision_and_rendering_in_split_modules(self) -> None:
        self.assertEqual(
            hook.assess_prompt.__module__,
            "aippocampus_runtime.recall.prompt_recall_decision",
        )
        self.assertEqual(
            hook.context_for_hook.__module__,
            "aippocampus_runtime.recall.prompt_context_render",
        )
        self.assertEqual(
            hook.hook_stdout_payload.__module__,
            "aippocampus_runtime.recall.prompt_context_render",
        )

    def test_hook_input_from_stdin_reads_codex_json_after_split(self) -> None:
        old_stdin = sys.stdin
        payload = {"prompt": "hook smoke 测试", "cwd": str(self.workspace)}
        try:
            sys.stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
            parsed = hook.hook_input_from_stdin()
        finally:
            sys.stdin = old_stdin

        self.assertEqual(parsed["prompt"], payload["prompt"])
        self.assertEqual(parsed["cwd"], payload["cwd"])

    def test_debug_log_records_semantic_budget_diagnostics_for_skip(self) -> None:
        log_path = self.root / "prompt_hook_debug.jsonl"
        local_path = fake_test_windows_path("prompt-hook-secret.txt")
        result = {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY, local_path],
            "concept_expansions": [],
            "cognitive_map": [],
            "candidates": [
                {
                    "thread_key": "thread:private",
                    "title": f"candidate Bearer {FAKE_TEST_BEARER_TOKEN}",
                    "score": 0.5,
                }
            ],
            "working_memory": [],
            "evidence": [],
            "semantic_gate": {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "cached": False,
                "query_aliases": [local_path],
                "availability_reason": "foreground_budget_timeout",
                "diagnostic": "semantic_timed_out_under_foreground_budget",
                "elapsed_ms": 1949.33,
                "timeout": 0.87,
                "budget": {"requested_timeout": 20.0, "effective_timeout": 0.87},
                "error_buckets": {"read_timeout": 3},
            },
            "elapsed_ms": 4232.23,
        }

        hook.write_debug_log(result, log_path=log_path, include_skip=True)

        event = json.loads(log_path.read_text(encoding="utf-8").strip())
        semantic = event["semantic_gate"]
        self.assertFalse(semantic["available"])
        self.assertEqual(semantic["availability_reason"], "foreground_budget_timeout")
        self.assertEqual(semantic["diagnostic"], "semantic_timed_out_under_foreground_budget")
        self.assertEqual(semantic["error_buckets"], {"read_timeout": 3})
        encoded = json.dumps(event, ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, encoded)
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)
        self.assertIn("<redacted:api-key>", encoded)
        self.assertIn("<redacted:bearer-token>", encoded)
        self.assertIn("<redacted:local-path>", encoded)

    def test_prompt_hook_audit_status_projects_last_debug_event_without_raw_context(self) -> None:
        log_path = self.root / "prompt_hook_debug.jsonl"
        local_path = fake_test_windows_path("prompt-hook-audit.txt")
        result = {
            "decision": "scent",
            "score": 0.82,
            "confidence": "medium",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY, local_path],
            "concept_expansions": [],
            "cognitive_map": [],
            "candidates": [{"thread_key": "session:private", "title": "private source title"}],
            "working_memory": [],
            "evidence": [{"thread_key": "session:old", "line": 42, "phase": "final"}],
            "ambient_recall": {
                "mode": "source_backed_recall_card",
                "confidence": "high",
                "cache_status": {"status": "hit", "topic_epoch": "epoch-a"},
                "warm_background": {"status": "queued", "spawned": True},
                "cards": [
                    {
                        "card_id": "route-card",
                        "theme": "private wayfinding theme",
                        "support_level": "scent",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cognitive_map_route",
                        "source_refs": [],
                    },
                    {
                        "card_id": "source-card",
                        "theme": "private source theme",
                        "support_level": "evidence",
                        "visibility": "source_backed_recall_card",
                        "provenance_class": "source_backed_reopen",
                        "source_reopen_required": True,
                        "source_validation": {"status": "supported"},
                        "source_refs": [{"thread_key": "session:old", "line": 42}],
                    },
                ],
            },
            "elapsed_ms": 48.5,
        }

        hook.write_debug_log(
            result,
            hook_input={
                "session_id": "session-secret",
                "turn_id": "turn-secret",
                "prompt": FAKE_TEST_OPENAI_API_KEY,
            },
            log_path=log_path,
        )

        status = hook.prompt_hook_audit_status(log_path=log_path)

        self.assertEqual(status["status"], "found")
        self.assertEqual(status["last_prompt_hook"]["memory_surface"], "source_backed_evidence")
        self.assertEqual(status["last_prompt_hook"]["source_backed_count"], 1)
        self.assertEqual(status["last_prompt_hook"]["wayfinding_count"], 1)
        self.assertEqual(status["last_prompt_hook"]["cache"]["status"], "hit")
        self.assertTrue(status["last_prompt_hook"]["cache"]["topic_epoch_present"])
        self.assertEqual(status["last_prompt_hook"]["warm_background"]["status"], "queued")
        self.assertFalse(status["privacy_boundary"]["raw_cards_emitted"])
        self.assertFalse(status["privacy_boundary"]["raw_prompt_text_emitted"])
        encoded = json.dumps(status, ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, encoded)
        self.assertNotIn("epoch-a", encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)
        self.assertNotIn("private source title", encoded)
        self.assertNotIn("private source theme", encoded)
        self.assertNotIn("session-secret", encoded)
        self.assertNotIn("turn-secret", encoded)

    def test_default_skip_telemetry_records_aggregate_without_raw_prompt(self) -> None:
        telemetry_path = self.root / "prompt_hook_skip_telemetry.json"
        local_path = fake_test_windows_path("prompt-hook-secret.txt")
        result = {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY, local_path],
            "reasons": ["no ambient recall cue"],
            "ambient_recall": {
                "cache_status": {"status": "miss"},
                "warm_background": {"status": "skipped", "spawned": False},
            },
            "semantic_gate": {
                "available": False,
                "decision": "skip",
                "availability_reason": "foreground_budget_timeout",
                "diagnostic": "semantic_timed_out_under_foreground_budget",
                "cached": False,
                "timeout": 0.87,
                "budget": {"requested_timeout": 20.0, "effective_timeout": 0.87},
                "error_buckets": {"read_timeout": 3},
            },
            "elapsed_ms": 4232.23,
        }

        hook.write_skip_telemetry(
            result,
            hook_input={"session_id": "test-session", "prompt": FAKE_TEST_OPENAI_API_KEY},
            telemetry_path=telemetry_path,
            hook_budget_ms=4300,
            semantic_timeout=2.5,
        )

        telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
        self.assertEqual(telemetry["skip_events"], 1)
        self.assertEqual(telemetry["skip_reason_counts"]["foreground_budget_timeout"], 1)
        self.assertEqual(telemetry["semantic_diagnostic_counts"]["semantic_timed_out_under_foreground_budget"], 1)
        self.assertEqual(telemetry["cache_status_counts"]["miss"], 1)
        self.assertIn("startup_import_io", telemetry["latency_ms"]["buckets"])
        encoded = json.dumps(telemetry, ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)
        self.assertNotIn("test-session", encoded)

    def test_prompt_hook_main_writes_skip_telemetry_by_default_without_log_skip(self) -> None:
        telemetry_path = self.root / "main-skip-telemetry.json"
        result = {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY],
            "reasons": ["suppressed ordinary code-surface prompt"],
            "candidates": [],
            "evidence": [],
            "working_memory": [],
            "semantic_gate": None,
            "ambient_recall": {"cache_status": {"status": "disabled"}},
            "elapsed_ms": 12.5,
        }
        runtime = {
            "assess_prompt": lambda *args, **kwargs: result,
            "apply_dream_delivery_boundary": lambda value, **kwargs: value,
            "public_hook_debug_payload": lambda value: {"decision": value["decision"], "elapsed_ms": value["elapsed_ms"]},
            "hook_stdout_payload": lambda value: None,
            "hook_input_from_stdin": lambda: {},
        }

        stdout = io.StringIO()
        with (
            patch.object(hook, "_load_runtime", return_value=runtime),
            patch.object(
                hook,
                "_prepare_dream_delivery",
                return_value={
                    "mode": "off",
                    "event": None,
                    "allow_dream": False,
                    "dream_hypothesis_limit": 0,
                    "reason": "off",
                },
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = hook.main(
                [
                    "--prompt",
                    f"fix hover style {FAKE_TEST_OPENAI_API_KEY}",
                    "--cwd",
                    str(self.workspace),
                    "--json",
                    "--skip-telemetry-path",
                    str(telemetry_path),
                ]
            )

        self.assertEqual(code, 0)
        telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
        self.assertEqual(telemetry["skip_events"], 1)
        self.assertEqual(telemetry["skip_reason_counts"]["suppressed_code_surface"], 1)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, telemetry_path.read_text(encoding="utf-8"))

    def test_prompt_hook_main_writes_default_audit_status_without_debug_log(self) -> None:
        status_path = self.root / "prompt-hook-last-status.json"
        local_path = fake_test_windows_path("prompt-hook-status.txt")
        private_marker = "do-not-log-status-marker"
        result = {
            "decision": "scent",
            "score": 0.72,
            "confidence": "medium",
            "query_terms": [private_marker, local_path],
            "concept_expansions": [],
            "cognitive_map": [],
            "candidates": [{"thread_key": "session:private", "title": "private candidate title"}],
            "working_memory": [],
            "evidence": [],
            "semantic_gate": None,
            "ambient_recall": {
                "mode": "active_gentle_nudge",
                "confidence": "medium",
                "cards": [
                    {
                        "card_id": "cached-card",
                        "theme": "private cached theme",
                        "support_level": "candidate",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cached_warm_card",
                        "source_refs": [],
                    }
                ],
                "cache_status": {"status": "hit", "card_count": 1},
            },
            "elapsed_ms": 12.5,
        }
        runtime = {
            "assess_prompt": lambda *args, **kwargs: result,
            "apply_dream_delivery_boundary": lambda value, **kwargs: value,
            "public_hook_debug_payload": lambda value: {"decision": value["decision"]},
            "hook_stdout_payload": lambda value: None,
            "hook_input_from_stdin": lambda: {},
        }

        stdout = io.StringIO()
        with (
            patch.object(hook, "_load_runtime", return_value=runtime),
            patch.object(
                hook,
                "_prepare_dream_delivery",
                return_value={
                    "mode": "off",
                    "event": None,
                    "allow_dream": False,
                    "dream_hypothesis_limit": 0,
                    "reason": "off",
                },
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = hook.main(
                [
                    "--prompt",
                    f"继续 ambient recall {private_marker}",
                    "--cwd",
                    str(self.workspace),
                    "--json",
                    "--no-skip-telemetry",
                    "--audit-status-path",
                    str(status_path),
                ]
            )

        self.assertEqual(code, 0)
        status = hook.prompt_hook_audit_status(status_path=status_path)
        self.assertEqual(status["status"], "found")
        self.assertEqual(status["source"], "last_status")
        self.assertEqual(status["last_prompt_hook"]["memory_surface"], "candidate")
        self.assertEqual(status["last_prompt_hook"]["candidate_count"], 1)
        self.assertEqual(status["last_prompt_hook"]["cache"]["status"], "hit")
        encoded = status_path.read_text(encoding="utf-8")
        self.assertNotIn(private_marker, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)
        self.assertNotIn("private candidate title", encoded)
        self.assertNotIn("private cached theme", encoded)

    def test_prompt_hook_skip_telemetry_can_be_disabled(self) -> None:
        telemetry_path = self.root / "disabled-skip-telemetry.json"
        result = {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "query_terms": [],
            "reasons": ["no ambient recall cue"],
            "semantic_gate": None,
            "elapsed_ms": 1.0,
        }

        hook.write_skip_telemetry(
            result,
            telemetry_path=telemetry_path,
            enabled=False,
        )

        self.assertFalse(telemetry_path.exists())

    def test_prompt_hook_telemetry_failure_fails_open(self) -> None:
        result = {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "query_terms": [],
            "reasons": ["no ambient recall cue"],
            "candidates": [],
            "evidence": [],
            "working_memory": [],
            "semantic_gate": None,
            "ambient_recall": {"cache_status": {"status": "disabled"}},
            "elapsed_ms": 1.25,
        }
        runtime = {
            "assess_prompt": lambda *args, **kwargs: result,
            "apply_dream_delivery_boundary": lambda value, **kwargs: value,
            "public_hook_debug_payload": lambda value: {"decision": value["decision"], "elapsed_ms": value["elapsed_ms"]},
            "hook_stdout_payload": lambda value: None,
            "hook_input_from_stdin": lambda: {},
        }

        stdout = io.StringIO()
        with (
            patch.object(hook, "_load_runtime", return_value=runtime),
            patch.object(
                hook,
                "_prepare_dream_delivery",
                return_value={
                    "mode": "off",
                    "event": None,
                    "allow_dream": False,
                    "dream_hypothesis_limit": 0,
                    "reason": "off",
                },
            ),
            patch.object(hook, "write_skip_telemetry", side_effect=RuntimeError("telemetry disk gone")),
            contextlib.redirect_stdout(stdout),
        ):
            code = hook.main(
                [
                    "--prompt",
                    "普通 hover 样式微调",
                    "--cwd",
                    str(self.workspace),
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["decision"], "skip")

    def test_prompt_hook_can_write_opt_in_dream_shadow_event(self) -> None:
        working_memory = self.root / "working_memory.jsonl"
        working_memory.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_continuity",
                    "title": "Continuity route bridge",
                    "summary": "Use only as a route hint.",
                    "trigger_terms": ["continuity"],
                    "source_finding_ids": ["dreamfinding_continuity"],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "sensitive_use_gate": {"state": "allowed"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        shadow_log = self.root / "shadow.jsonl"

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-shadow-ab",
                "--dream-shadow-log",
                str(shadow_log),
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        self.assertIn('"decision"', proc.stdout)
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        encoded = json.dumps(event, ensure_ascii=False)
        self.assertTrue(event["eligible_exposure"])
        self.assertEqual(event["dream"]["match_count"], 1)
        self.assertNotIn("continuity 这条线", encoded)

    def test_prompt_hook_default_filters_dream_from_foreground(self) -> None:
        working_memory = self._write_dream_working_memory()

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["decision"], "skip")
        self.assertEqual(payload["working_memory"], [])
        self.assertNotIn("Dream hypothesis", encoded)

    def test_prompt_hook_json_redacts_prompt_derived_secret_query_terms(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                f"Can you remember the API key {FAKE_TEST_OPENAI_API_KEY} from earlier?",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--semantic-gate",
                "off",
                "--max-elapsed-ms",
                "4300",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, encoded)
        self.assertIn("<redacted:api-key>", encoded)
        self.assertIn("<redacted:api-key>", payload["query_terms"])

    def test_public_hook_debug_payload_is_allowlisted(self) -> None:
        private_result = {
            "decision": "scent",
            "score": 0.88,
            "confidence": "medium",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY],
            "candidates": [{"title": "private title", "thread_key": "session:private"}],
            "evidence": [{"snippet": "private source wording"}],
            "semantic_gate": {
                "available": True,
                "decision": "scent",
                "confidence": 0.82,
                "cached": False,
                "query_aliases": [f"alias {FAKE_TEST_OPENAI_API_KEY}"],
                "workers": [{"raw": "private worker output"}],
                "errors": ["private semantic error"],
            },
            "scent_threshold_policy": {
                "base_threshold": 5.0,
                "effective_threshold": 4.25,
                "adjustments": [
                    {
                        "reason": "same_thread_decision_continuation",
                        "delta": -0.75,
                        "raw_prompt": "private prompt text",
                    },
                    {"reason": "private prompt text", "delta": -1.0},
                ],
                "risk_boundary": "normal",
                "raw_prompt": "private prompt text",
            },
            "ambient_recall": {"mode": "scent", "card_count": 1},
            "hot_path_funnel": {
                "decision": "scent",
                "candidate_count": 1,
                "candidate_ids": ["session:private"],
                "source_reopen_promotion_count": 0,
                "stages": [
                    {
                        "stage": "bounded_trigram_fts",
                        "status": "hit",
                        "candidate_count": 1,
                        "fallback_reason": "",
                        "elapsed_ms": 3.4,
                        "raw_prompt": "private prompt text",
                    }
                ],
            },
            "route_delivery_diagnostic": {
                "foreground_profile": "ambient_hot_path",
                "semantic_gate_cache_hit_but_no_source_bridge": True,
                "semantic_reuse_source": "exact_semantic_cache",
                "hot_path_candidates_after_merge": 1,
                "final_candidate_count": 2,
                "cold_semantic_shadowed": False,
                "raw_prompt": "private prompt text",
                "query_aliases": ["private prompt text"],
                "candidate_ids": ["session:private"],
            },
            "elapsed_ms": 123.4,
        }

        public = hook.public_hook_debug_payload(private_result)

        encoded = json.dumps(public, ensure_ascii=False)
        self.assertEqual(public["decision"], "scent")
        self.assertIn("<redacted:api-key>", encoded)
        self.assertNotIn("candidates", public)
        self.assertNotIn("evidence", public)
        self.assertNotIn("private title", encoded)
        self.assertNotIn("private source wording", encoded)
        self.assertNotIn("private worker output", encoded)
        self.assertEqual(public["scent_threshold_policy"]["effective_threshold"], 4.25)
        self.assertEqual(
            public["scent_threshold_policy"]["adjustments"][0]["reason"],
            "same_thread_decision_continuation",
        )
        self.assertEqual(public["hot_path_funnel"]["decision"], "scent")
        self.assertEqual(public["hot_path_funnel"]["candidate_count"], 1)
        self.assertEqual(public["hot_path_funnel"]["source_reopen_promotion_count"], 0)
        self.assertEqual(public["hot_path_funnel"]["stages"][0]["stage"], "bounded_trigram_fts")
        self.assertNotIn("candidate_ids", public["hot_path_funnel"])
        self.assertEqual(
            public["route_delivery_diagnostic"]["foreground_profile"],
            "ambient_hot_path",
        )
        self.assertTrue(
            public["route_delivery_diagnostic"][
                "semantic_gate_cache_hit_but_no_source_bridge"
            ]
        )
        self.assertEqual(
            public["route_delivery_diagnostic"]["semantic_reuse_source"],
            "exact_semantic_cache",
        )
        self.assertEqual(
            public["route_delivery_diagnostic"]["hot_path_candidates_after_merge"], 1
        )
        self.assertNotIn("candidate_ids", public["route_delivery_diagnostic"])
        self.assertNotIn("private prompt text", encoded)
        private_result["route_delivery_diagnostic"][
            "semantic_reuse_source"
        ] = "semantic_provider_timeout"
        timeout_public = hook.public_hook_debug_payload(private_result)
        self.assertEqual(
            timeout_public["route_delivery_diagnostic"]["semantic_reuse_source"],
            "semantic_provider_timeout",
        )

    def test_prompt_hook_dry_run_logs_would_deliver_without_foreground_dream(self) -> None:
        working_memory = self._write_dream_working_memory()
        shadow_log = self.root / "dry-run-shadow.jsonl"

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-delivery-mode",
                "dry_run",
                "--dream-shadow-log",
                str(shadow_log),
                "--session-id",
                "session-secret",
                "--topic-epoch",
                "epoch-dream",
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        self.assertEqual(payload["decision"], "skip")
        self.assertIn(event["would_deliver_arm"], {"control", "dream"})
        self.assertIsNone(event["delivered_arm"])
        self.assertEqual(event["delivery_mode"], "dry_run")
        self.assertEqual(event["assignment_unit"], "thread_topic_epoch")

    def test_prompt_hook_delivered_control_is_holdback_without_context(self) -> None:
        working_memory = self._write_dream_working_memory()
        shadow_log = self.root / "control-shadow.jsonl"
        salt = self._salt_for_arm("control")

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-delivery-mode",
                "delivered",
                "--dream-shadow-log",
                str(shadow_log),
                "--dream-shadow-salt",
                salt,
                "--session-id",
                "session-secret",
                "--topic-epoch",
                "epoch-dream",
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        self.assertEqual(payload["decision"], "skip")
        self.assertEqual(event["delivered_arm"], "control")
        self.assertEqual(event["delivery_decision"], "delivered_control_holdback")

    def test_prompt_hook_delivered_dream_inserts_one_private_context(self) -> None:
        working_memory = self._write_dream_working_memory(include_second=True)
        shadow_log = self.root / "dream-shadow.jsonl"
        salt = self._salt_for_arm("dream")

        proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.hooks.prompt",
                "--prompt",
                "AIppocampus continuity 这条线下一步怎么收？",
                "--cwd",
                str(self.workspace),
                "--registry",
                str(self.registry),
                "--working-memory",
                str(working_memory),
                "--dream-delivery-mode",
                "delivered",
                "--dream-shadow-log",
                str(shadow_log),
                "--dream-shadow-salt",
                salt,
                "--session-id",
                "session-secret",
                "--topic-epoch",
                "epoch-dream",
                "--no-semantic-gate",
                "--no-warm-background",
                "--search-budget",
                "0",
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        payload = json.loads(proc.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        event = json.loads(shadow_log.read_text(encoding="utf-8").strip())
        self.assertEqual(event["delivered_arm"], "dream")
        self.assertEqual(event["delivery_decision"], "delivered_dream_treatment")
        self.assertEqual(context.count("Dream hypothesis, not source fact"), 1)
        self.assertIn("reopen source", context)

    def _salt_for_arm(self, arm: str) -> str:
        for index in range(1000):
            salt = f"unit-delivery-{index}"
            if (
                dream_shadow.assigned_arm_for(
                    "thread_topic_epoch",
                    "session-secret",
                    "epoch-dream",
                    salt=salt,
                )
                == arm
            ):
                return salt
        raise AssertionError(f"could not find salt for {arm}")

    def _write_dream_working_memory(self, *, include_second: bool = False) -> Path:
        working_memory = self.root / f"working_memory_dream_{include_second}.jsonl"
        rows = [
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "dream_hypothesis",
                "candidate_key": "wm_dream_continuity",
                "title": "Continuity route bridge",
                "summary": "Use only as a route hint.",
                "trigger_terms": ["continuity"],
                "source_finding_ids": ["dreamfinding_continuity"],
                "confidence": 0.7,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "sensitive_use_gate": {"state": "allowed"},
                "foreground_use": {"strong_claim_requires_source_reopen": True},
            }
        ]
        if include_second:
            rows.append(
                {
                    **rows[0],
                    "candidate_key": "wm_dream_continuity_second",
                    "title": "Second continuity bridge",
                    "source_finding_ids": ["dreamfinding_continuity_second"],
                }
            )
        working_memory.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        return working_memory

    def _write_sqlite(self) -> None:
        con = sqlite3.connect(self.sqlite)
        try:
            con.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    line INTEGER,
                    timestamp TEXT,
                    role TEXT,
                    kind TEXT,
                    phase TEXT,
                    turn_index INTEGER,
                    is_final INTEGER,
                    text TEXT
                )
                """
            )
            rows = [
                (
                    1,
                    190,
                    "2026-05-25T01:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    7,
                    1,
                    "生命还能变成什么，而我能不能在变化后仍然是我。",
                ),
                (
                    2,
                    999,
                    "2026-05-25T01:30:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    11,
                    1,
                    "这只是一个包含之前和还是的普通收尾，不应该被当成那句生命问题的证据。",
                ),
                (
                    3,
                    356,
                    "2026-05-25T02:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    19,
                    1,
                    "raw history 明明在本地，但压缩后的我不知道该找什么，所以需要外置海马体和触发式召回。",
                ),
            ]
            con.executemany(
                """
                INSERT INTO messages
                (id, line, timestamp, role, kind, phase, turn_index, is_final, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            con.commit()
        finally:
            con.close()

    def _write_registry(self) -> None:
        entry = {
            "thread_key": "session:test-old",
            "title": "old-thread",
            "workspace_name": "old-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "message_count": 2,
            "rollout_size": 1024,
            "anchor_count": 2,
            "anchor_titles": [
                "Active recall and retrieval optimization checkpoint",
                "LLM self-continuity and external hippocampus",
            ],
            "keywords": [
                "active recall",
                "ambient recall",
                "hook",
                "Codex",
                "联想",
                "触发式召回",
                "外置海马体",
                "self-continuity",
                "生命还能变成什么",
            ],
            "summary": "旧线程讨论过 UserPromptSubmit hook、联想式记忆、小海马体、以及自我连续性的原话。",
            "paths": {
                "workspace": str(self.old),
                "sqlite": str(self.sqlite),
                "anchors": None,
            },
        }
        self.registry.write_text(
            json.dumps(
                {"schema_version": 1, "updated_at": "2026-05-25T19:00:00Z", "threads": [entry]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_single_thread_registry(
        self,
        *,
        title: str,
        keywords: list[str],
        summary: str,
    ) -> Path:
        registry_path = self.root / f"{title.lower().replace(' ', '-')}-registry" / "threads.json"
        registry_path.parent.mkdir()
        entry = {
            "thread_key": "session:single-thread",
            "title": title,
            "workspace_name": "single-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "anchor_titles": [title],
            "keywords": keywords,
            "summary": summary,
            "paths": {"workspace": str(self.old), "sqlite": str(self.sqlite)},
        }
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": [entry]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def _write_clean_thread(self, thread_key: str, timestamp: str, text: str) -> Path:
        clean_dir = self.root / thread_key.replace(":", "-") / "clean-source"
        clean_dir.mkdir(parents=True)
        messages = clean_dir / "messages.jsonl"
        message = {
            "message_id": f"msg-{thread_key}",
            "turn_id": f"turn-{thread_key}",
            "source_line": 42,
            "timestamp": timestamp,
            "role": "assistant",
            "phase": "final_answer",
            "turn_index": 3,
            "is_final": True,
            "text": text,
        }
        messages.write_text(json.dumps(message, ensure_ascii=False) + "\n", encoding="utf-8")
        return messages

    def _write_clean_thread_rows(self, thread_key: str, rows: list[dict]) -> Path:
        clean_dir = self.root / thread_key.replace(":", "-") / "clean-source"
        clean_dir.mkdir(parents=True)
        messages = clean_dir / "messages.jsonl"
        normalized = []
        for index, row in enumerate(rows, start=1):
            normalized.append(
                {
                    "message_id": row.get("message_id") or f"msg-{thread_key}-{index}",
                    "turn_id": row.get("turn_id") or f"turn-{thread_key}-{index}",
                    "source_line": row.get("source_line", 40 + index),
                    "timestamp": row.get("timestamp", "2026-05-25T00:00:00Z"),
                    "role": row.get("role", "assistant"),
                    "phase": row.get("phase", "final_answer"),
                    "turn_index": row.get("turn_index", index),
                    "is_final": row.get("is_final", row.get("phase", "final_answer") == "final_answer"),
                    "text": row.get("text", ""),
                }
            )
        messages.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in normalized) + "\n",
            encoding="utf-8",
        )
        return messages

    def _write_clean_registry(
        self,
        *,
        thread_key: str,
        title: str,
        keywords: list[str],
        summary: str,
        messages_path: Path,
        project_label: str = "AIppocampus",
    ) -> Path:
        registry_path = self.root / f"{thread_key.replace(':', '-')}-registry" / "threads.json"
        registry_path.parent.mkdir()
        entry = {
            "thread_key": thread_key,
            "title": title,
            "project_label": project_label,
            "workspace_name": project_label,
            "updated_at": "2026-05-25T19:00:00Z",
            "anchor_titles": [title],
            "keywords": keywords,
            "summary": summary,
            "paths": {
                "workspace": str(self.workspace),
                "clean_source_messages_jsonl": str(messages_path),
            },
        }
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": [entry]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def test_code_only_prompt_stays_silent(self) -> None:
        result = hook.assess_prompt(
            "把 dashboard 的按钮 hover 样式改一下，顺手跑测试",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(hook.context_for_hook(result))

    def test_code_surface_prompt_does_not_call_semantic_gate_for_generic_association(self) -> None:
        associations = self.registry.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "dashboard": {
                            "term": "dashboard",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 5,
                            "threads": [{"thread_key": "session:test-old"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("semantic gate should not run for ordinary code surface prompts")

        result = hook.assess_prompt(
            "把 dashboard 的按钮 hover 样式改一下，顺手跑测试",
            cwd=self.workspace,
            registry_path=self.registry,
            associations_path=associations,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(result["semantic_gate"])

    def test_short_latin_accent_daily_question_does_not_call_semantic_gate(self) -> None:
        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("semantic gate should not run for short daily questions")

        result = hook.assess_prompt(
            "¿Qué tiempo hará mañana?",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(result["semantic_gate"])

    def test_explicit_recall_with_local_association_skips_foreground_semantic_gate(self) -> None:
        associations = self.root / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "terms": {
                        "外置海马体": {
                            "term": "外置海马体",
                            "status": "verified",
                            "confidence": 0.95,
                            "hit_count": 3,
                            "threads": [{"thread_key": "session:test-old"}],
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("local association should avoid foreground semantic spend")

        result = hook.assess_prompt(
            "还记得外置海马体这件事吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            associations_path=associations,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])

    def test_associative_prompt_emits_scent_without_evidence(self) -> None:
        result = hook.assess_prompt(
            "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertGreaterEqual(result["score"], hook.SCENT_THRESHOLD)
        self.assertTrue(result["candidates"])
        self.assertEqual(result["ambient_recall"]["mode"], "active_gentle_nudge")
        self.assertEqual(
            result["ambient_recall"]["cards"][0]["visibility"], "active_gentle_nudge"
        )
        context = hook.context_for_hook(result)
        self.assertIsNotNone(context)
        self.assertIn("Ambient recall scent", context)
        self.assertIn("Ambient recall private context", context)
        self.assertIn("Use only if it helps", context)
        self.assertNotIn("line 190", context)

    def test_chinese_hook_cue_emits_scent(self) -> None:
        result = hook.assess_prompt(
            "我重启了一下 Codex，你看看实测钩子效果如何",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIn(
            "associative cue",
            " ".join(str(reason) for reason in result["reasons"]),
        )

    def test_generic_codex_overlap_without_memory_cue_stays_silent(self) -> None:
        result = hook.assess_prompt(
            "我重启了一下 Codex，看看状态",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(hook.context_for_hook(result))

    def test_profile_recall_uses_cross_lingual_aliases_without_semantic_gate(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Professional profile and job search history",
            keywords=["CV", "LinkedIn", "job search", "professional profile"],
            summary=(
                "Prior records discuss the user's resume, CV, LinkedIn profile, "
                "and job-search materials."
            ),
        )

        result = hook.assess_prompt(
            "你知道我的简历和领英资料吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIn("resume", result["query_terms"])
        self.assertIn("LinkedIn", result["query_terms"])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["candidates"][0]["title"], "Professional profile and job search history")

    def test_recent_work_friction_prompt_uses_life_wide_timeline_route(self) -> None:
        registry_dir = self.root / "life-wide-registry"
        registry_dir.mkdir()
        registry_path = registry_dir / "threads.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:work-friction",
                            "title": "Product workflow friction",
                            "workspace_name": "OtherProject",
                            "project_label": "OtherProject",
                            "updated_at": "2026-05-24T12:00:00Z",
                            "anchor_titles": ["Workflow friction and product pressure"],
                            "keywords": ["workflow friction", "product pressure"],
                            "summary": (
                                "Old English and Russian project notes about product "
                                "workflow friction and pressure."
                            ),
                            "paths": {"workspace": str(self.old)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_dir / "project_timeline.json").write_text(
            json.dumps(
                {
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "latest_turns": [
                                    {
                                        "thread_key": "session:work-friction",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["workflow friction", "product pressure"],
                                        "source_refs": [
                                            {"thread_key": "session:work-friction", "source_line": 91}
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近工作上那些摩擦和困扰，我们后来怎么处理比较好？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["title"], "Product workflow friction")
        self.assertTrue(result["candidates"][0]["life_wide_timeline_source"])
        self.assertEqual(result["evidence"], [])

    def test_vague_life_wide_prompt_returns_multiple_timeline_routes(self) -> None:
        registry_dir = self.root / "life-wide-multilingual-registry"
        registry_dir.mkdir()
        registry_path = registry_dir / "threads.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:english-friction",
                            "title": "English workflow friction",
                            "project_label": "Ops",
                            "updated_at": "2026-05-25T12:00:00Z",
                            "keywords": ["workflow friction", "product pressure"],
                            "summary": "English notes about product workflow friction.",
                            "paths": {"workspace": str(self.old)},
                        },
                        {
                            "thread_key": "session:russian-burnout",
                            "title": "Russian burnout notes",
                            "project_label": "Journal",
                            "updated_at": "2026-05-24T12:00:00Z",
                            "keywords": ["рабочее давление", "burnout"],
                            "summary": "Russian notes about work pressure and burnout.",
                            "paths": {"workspace": str(self.root / "journal")},
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_dir / "project_timeline.json").write_text(
            json.dumps(
                {
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "latest_turns": [
                                    {
                                        "thread_key": "session:english-friction",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["workflow friction", "product pressure"],
                                        "source_refs": [
                                            {
                                                "thread_key": "session:english-friction",
                                                "source_line": 91,
                                            }
                                        ],
                                    },
                                    {
                                        "thread_key": "session:russian-burnout",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["рабочее давление", "burnout"],
                                        "source_refs": [
                                            {
                                                "thread_key": "session:russian-burnout",
                                                "source_line": 52,
                                            }
                                        ],
                                    },
                                ]
                            }
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近工作上那些摩擦和压力，我们后来怎么处理比较好？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        candidate_keys = [candidate["thread_key"] for candidate in result["candidates"]]
        self.assertIn("session:english-friction", candidate_keys)
        self.assertIn("session:russian-burnout", candidate_keys)
        self.assertTrue(all(candidate["life_wide_timeline_source"] for candidate in result["candidates"][:2]))
        self.assertEqual(result["evidence"], [])

    def test_vague_continuation_without_semantic_stays_silent_despite_overlap(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Python list.sort None",
            keywords=["Python", "list.sort", "None", "missing keys"],
            summary="Prior coding conversation about list.sort returning None.",
        )

        result = hook.assess_prompt(
            "继续刚才这个编程问题，重点是 list.sort None",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertGreaterEqual(result["score"], hook.SCENT_THRESHOLD)
        self.assertFalse(result["evidence"])

    def test_weaker_vague_continuation_needs_semantic_positive_to_scent(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Python list.sort None",
            keywords=["Python", "list.sort", "None", "missing keys"],
            summary="Prior coding conversation about list.sort returning None.",
        )

        local_result = hook.assess_prompt(
            "这个问题后面怎么接，重点是 list.sort None",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(local_result["decision"], "skip")

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.86,
                "intent": "continuation",
                "query_aliases": ["list.sort", "None"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["vague continuation with source overlap"],
                "workers": [],
                "errors": [],
                "cached": False,
                "model_route": {"provider": "test-provider", "model": "test-model"},
                "cache_diagnostics": {"lookup": "disabled"},
            }

        semantic_result = hook.assess_prompt(
            "这个问题后面怎么接，重点是 list.sort None",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(semantic_result["decision"], "scent")
        self.assertIn("semantic gate", " ".join(str(reason) for reason in semantic_result["reasons"]))

    def test_semantic_positive_can_bridge_to_sqlite_when_registry_metadata_misses(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Unlabeled external project handoff",
            keywords=["handoff"],
            summary="A sparse registry row whose clean source has richer recall terms.",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.9,
                "intent": "recall",
                "query_aliases": ["raw history", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["semantic route found source terms absent from metadata"],
                "workers": [],
                "errors": [],
                "cached": False,
                "model_route": {"provider": "test-provider", "model": "test-model"},
                "cache_diagnostics": {"lookup": "disabled"},
            }

        result = hook.assess_prompt(
            "那个外部项目后来到底卡在哪里？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertTrue(result["candidates"])
        self.assertTrue(result["candidates"][0]["fallback"])
        self.assertGreater(result["candidates"][0]["probe_score"], 0)
        self.assertIn("semantic gate", " ".join(str(reason) for reason in result["reasons"]))

    def test_short_english_associative_cues_require_token_boundaries(self) -> None:
        matches = recall_cues.matched_terms(
            "Rewrite the paragraphs while leveraging the background examples.",
            recall_cues.ASSOCIATIVE_CUES,
        )

        self.assertNotIn("rag", matches)
        self.assertNotIn("hook", recall_cues.matched_terms("Handle this webhook payload.", {"hook"}))
        self.assertNotIn(
            "hook",
            recall_cues.matched_terms(
                "Write a Header Hook for this course.", recall_cues.ASSOCIATIVE_CUES
            ),
        )
        self.assertNotIn(
            "evidence",
            recall_cues.matched_terms(
                "Summarize the evidence in these articles.", recall_cues.ASSOCIATIVE_CUES
            ),
        )
        self.assertIn("rag", recall_cues.matched_terms("Use RAG-lite for recall.", {"rag"}))

    def test_dynamic_association_can_emit_scent_without_hardcoded_cue(self) -> None:
        associations = self.registry.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "associations.json": {
                            "term": "associations.json",
                            "status": "staging",
                            "confidence": 0.7,
                            "related_terms": ["小海马体", "ambient recall"],
                            "threads": [
                                {
                                    "thread_key": "session:test-old",
                                    "title": "old-thread",
                                    "line": 356,
                                    "phase": "final_answer",
                                    "turn_index": 19,
                                }
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "这个 associations.json 的动态联想层还要再收一下",
            cwd=self.workspace,
            registry_path=self.registry,
            associations_path=associations,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIn(
            "dynamic association",
            " ".join(str(reason) for reason in result["reasons"]),
        )
        self.assertNotIn("ambient recall", result["query_terms"])

    def test_cognitive_map_route_emits_scent_without_direct_registry_match(self) -> None:
        cognitive_map_path = self.registry.parent / "cognitive_map.json"
        cognitive_map_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_cognitive_map",
                    "status": "active",
                    "routes": [
                        {
                            "route_id": "cmr_test",
                            "kind": "cognitive_map_route",
                            "source": "deepseek_subconscious_jobs",
                            "landmark_ids": ["lm_aippocampus"],
                            "landmark_labels": ["AIppocampus", "外置海马体"],
                            "region_ids": ["region_architecture"],
                            "region_labels": ["memory architecture"],
                            "route_cues": ["心理地图", "位置细胞", "网格细胞"],
                            "query_terms": ["外置海马体", "触发式召回"],
                            "thread_keys": ["session:test-old"],
                            "confidence": 0.9,
                            "source_refs": [{"thread_key": "session:test-old", "line": 356}],
                        }
                    ],
                    "landmarks": [
                        {
                            "landmark_id": "lm_aippocampus",
                            "label": "AIppocampus",
                            "aliases": ["外置海马体", "认知地图"],
                            "thread_keys": ["session:test-old"],
                            "confidence": 0.9,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("cognitive map route should avoid foreground semantic spend")

        result = hook.assess_prompt(
            "咱们继续心理地图和位置细胞这条升级",
            cwd=self.workspace,
            registry_path=self.registry,
            cognitive_map_path=cognitive_map_path,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:test-old")
        self.assertIn("外置海马体", result["query_terms"])
        self.assertIn("cognitive map route", " ".join(result["reasons"]))

    def test_semantic_gate_alias_can_emit_scent_without_hardcoded_cue(self) -> None:
        registry_path = self.root / "semantic-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "海马体记忆", "working memory"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.88,
                "intent": "continuation",
                "query_aliases": ["AIppocampus", "海马体记忆", "working memory"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["paraphrase of the memory-system thread"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")
        self.assertIn("AIppocampus", result["query_terms"])
        self.assertIn("semantic gate", " ".join(result["reasons"]))

    def test_semantic_gate_alias_hits_are_recorded_as_reusable_cues(self) -> None:
        registry_path = self.root / "semantic-cue-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa", "внешний гиппокамп"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "semantic_cues.jsonl"

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.9,
                "intent": "continuation",
                "query_aliases": ["memoria externa", "внешний гиппокамп"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["multilingual paraphrase of the memory-system thread"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Podemos continuar esa memoria externa para mantener la continuidad?",
        ):
            result = hook.assess_prompt(
                prompt,
                cwd=self.workspace,
                registry_path=registry_path,
                semantic_gate_fn=fake_semantic_gate,
                semantic_cues_path=cues_path,
                search_budget=0,
            )
            self.assertEqual(result["decision"], "scent")

        triggers = cue_cache.semantic_cue_triggers(cues_path)
        aliases = {alias for trigger in triggers for alias in trigger.get("aliases") or []}
        self.assertIn("memoria externa", aliases)
        self.assertIn("внешний гиппокамп", aliases)

    def test_background_only_semantic_alias_hits_can_warm_reusable_cues(self) -> None:
        registry_path = self.root / "semantic-background-cue-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa", "внешний гиппокамп"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "background_semantic_cues.jsonl"

        def background_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "background_only",
                "confidence": 0.9,
                "intent": "continuation",
                "query_aliases": ["memoria externa", "внешний гиппокамп"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["high-confidence aliases, but scent not needed for this run"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        cue_updates = []
        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Puedes continuar esa memoria externa para mantener la continuidad?",
        ):
            result = hook.assess_prompt(
                prompt,
                cwd=self.workspace,
                registry_path=registry_path,
                semantic_gate_fn=background_semantic_gate,
                semantic_cues_path=cues_path,
                search_budget=0,
            )
            self.assertEqual(result["semantic_gate"]["decision"], "background_only")
            cue_updates.append(result["semantic_cue_cache"])

        self.assertEqual(cue_updates[0]["active_count"], 0)
        self.assertGreater(cue_updates[1]["active_count"], 0)

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active background semantic cues should avoid live semantic spend")

        result = hook.assess_prompt(
            "¿Seguimos con esa memoria externa de continuidad?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fail_semantic_gate,
            semantic_cues_path=cues_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("memoria externa", result["query_terms"])
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_active_semantic_cue_cache_can_emit_scent_without_semantic_gate(self) -> None:
        registry_path = self.root / "active-semantic-cue-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "active_semantic_cues.jsonl"
        semantic_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.9,
            "query_aliases": ["memoria externa"],
        }
        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Podemos continuar esa memoria externa para mantener la continuidad?",
        ):
            cue_cache.record_semantic_cue_hits(
                cues_path,
                prompt=prompt,
                semantic_result=semantic_result,
                source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
                route="semantic_gate",
            )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active semantic cue cache should avoid live semantic spend")

        result = hook.assess_prompt(
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_cues_path=cues_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("memoria externa", result["query_terms"])
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_living_cue_cache_default_hook_emits_scent_without_leaking_private_cue(self) -> None:
        living_cues = self.registry.parent / "living_cue_cache.jsonl"
        living_cues.write_text(
            json.dumps(
                {
                    "cue": "private canonical tree bridge",
                    "aliases": ["tree problem"],
                    "source_refs": [
                        {
                            "source_id": "clean:tree:m7",
                            "thread_key": "session:test-old",
                            "message_id": "m7",
                            "line": 14,
                            "snippet": "raw private source text must not leak",
                            "path": fake_test_windows_path("private-tree-messages.jsonl"),
                        }
                    ],
                    "confidence": 0.94,
                    "sensitivity": "safe",
                    "freshness": "current",
                    "status": "current",
                    "last_helpful_count": 2,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "Can we continue that tree problem from before?",
            cwd=self.workspace,
            registry_path=self.registry,
            use_semantic_gate=False,
            search_budget=0,
        )
        public = hook.public_hook_debug_payload(result)
        encoded_public = json.dumps(public, ensure_ascii=False, sort_keys=True)
        context = hook.context_for_hook(result) or ""
        encoded_context = json.dumps(context, ensure_ascii=False)

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("living cue cache", " ".join(result["reasons"]))
        self.assertEqual(result["candidates"][0]["thread_key"], "session:test-old")
        self.assertEqual(
            result["hot_path_funnel"]["living_cue_cache"]["diagnostics"]["live_llm_call_count"],
            0,
        )
        self.assertEqual(
            public["hot_path_funnel"]["living_cue_cache"]["selected_count"],
            1,
        )
        self.assertIn("Ambient recall scent", context)
        self.assertNotIn("private canonical tree bridge", encoded_public + encoded_context)
        self.assertNotIn("raw private source text", encoded_public + encoded_context)
        self.assertNotIn("private-tree", encoded_public + encoded_context)

    def test_active_semantic_cue_hit_skips_cold_foreground_semantic_call(self) -> None:
        registry_path = self.root / "semantic-cue-skip-live-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa", "conversation continuity"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.old), "sqlite": str(self.sqlite)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "semantic_cue_skip_live.jsonl"
        semantic_result = {
            "available": True,
            "decision": "background_only",
            "confidence": 0.9,
            "query_aliases": ["memoria externa"],
            "memory_scope": ["registered_threads"],
        }
        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Puedes continuar esa memoria externa para mantener la continuidad?",
        ):
            cue_cache.record_semantic_cue_hits(
                cues_path,
                prompt=prompt,
                semantic_result=semantic_result,
                source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
                route="semantic_gate",
            )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active semantic cue hit should avoid a cold foreground model call")

        result = hook.assess_prompt(
            "¿Seguimos con esa memoria externa de continuidad?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_cues_path=cues_path,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertEqual(result["semantic_gate_reuse"]["source"], "semantic_cue_cache")
        self.assertTrue(result["semantic_gate_reuse"]["semantic_cue_hit"])
        self.assertFalse(result["semantic_gate_reuse"]["cold_model_call"])
        self.assertIn("memoria externa", result["query_terms"])

    def test_active_non_latin_semantic_cues_emit_scent_without_live_semantic(self) -> None:
        registry_path = self.root / "nonlatin-semantic-cue-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["external hippocampus", "conversation continuity"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "nonlatin_semantic_cues.jsonl"
        semantic_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.9,
            "query_aliases": [
                "внешний гиппокамп",
                "الحُصين الخارجي",
                "外部海馬",
                "외부 해마",
                "ฮิปโปแคมปัสภายนอก",
            ],
        }
        for _ in range(2):
            cue_cache.record_semantic_cue_hits(
                cues_path,
                prompt="synthetic multilingual continuity cue",
                semantic_result=semantic_result,
                source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
                route="semantic_gate",
            )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active semantic cues should avoid live semantic spend")

        prompts = [
            "Как там мой внешний гиппокамп памяти и продолжение разговоров?",
            "كيف حال الحُصين الخارجي للذاكرة واستمرار المحادثات؟",
            "外部海馬みたいな記憶システムの進捗はどう？",
            "외부 해마 같은 기억 시스템은 지금 어떻게 되고 있어?",
            "ระบบความจำแบบฮิปโปแคมปัสภายนอกตอนนี้เป็นอย่างไรบ้าง",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = hook.assess_prompt(
                    prompt,
                    cwd=self.workspace,
                    registry_path=registry_path,
                    semantic_cues_path=cues_path,
                    semantic_gate_fn=fail_semantic_gate,
                    use_semantic_gate=False,
                    search_budget=0,
                )

                self.assertEqual(result["decision"], "scent")
                self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")
                self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_reviewed_semantic_trigger_can_emit_scent_without_hardcoded_cue(self) -> None:
        registry_path = self.root / "reviewed-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "reviewed_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "External memory continuation",
                    "aliases": ["memoria externa"],
                    "confidence": 0.91,
                    "when_to_use": "Use when the user asks in Spanish about the external memory thread.",
                    "source_refs": [{"thread_key": "session:aippocampus", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("reviewed semantic trigger should avoid live semantic spend")

        result = hook.assess_prompt(
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("memoria externa", result["query_terms"])
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_reviewed_semantic_trigger_source_refs_wake_sparse_registry_candidate(self) -> None:
        registry_path = self.root / "source-ref-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:friction",
                            "title": "Recovered sidecar-backed source thread",
                            "project_label": "Life-wide continuity",
                            "anchor_titles": [],
                            "keywords": [],
                            "summary": "No lexical overlap with the natural prompt or trigger aliases.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "source_ref_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Subconscious friction recall route",
                    "aliases": [
                        "最近让我很烦",
                        "recent personal friction",
                        "что меня раздражало недавно",
                    ],
                    "confidence": 0.93,
                    "when_to_use": "Use when subconscious review linked a natural annoyance/friction prompt to this source thread.",
                    "source_refs": [
                        {
                            "thread_key": "session:friction",
                            "title": "Recovered sidecar-backed source thread",
                            "message_id": "m-friction",
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("reviewed source refs should provide a local sidecar route")

        result = hook.assess_prompt(
            "最近让我很烦的那个点后来怎么处理来着？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:friction")
        self.assertTrue(result["candidates"][0]["semantic_trigger_source"])
        self.assertIn("最近让我很烦", result["query_terms"])

    def test_reviewed_semantic_trigger_ignores_generic_source_ref_issue_prompt_terms(self) -> None:
        registry_path = self.root / "generic-spillover-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:detached-alias",
                            "title": "Garden planning notebook",
                            "project_label": "Home planning",
                            "anchor_titles": [],
                            "keywords": ["balcony planting"],
                            "summary": "A sparse row for unrelated household planning notes.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "generic_spillover_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Source ref issue route",
                    "aliases": ["detached alias"],
                    "confidence": 0.9,
                    "when_to_use": (
                        "Use when the user asks about source refs, candidate issues, "
                        "or route context."
                    ),
                    "source_refs": [{"thread_key": "session:detached-alias", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("generic trigger prompt terms should not require live semantic spend")

        result = hook.assess_prompt(
            "候选 source refs 的中间层和过度保守这个问题，是不是已经有 issue 了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(result["semantic_gate"])
        self.assertFalse(result["candidates"])
        self.assertIsNone(hook.context_for_hook(result))
        public = hook.public_hook_debug_payload(result)
        delivery = public["route_delivery_diagnostic"]
        self.assertEqual(delivery["foreground_route_profile"], "generic_recall_meta")
        self.assertGreater(delivery["generic_prompt_term_count"], 0)
        self.assertEqual(
            delivery["semantic_trigger_generic_term_suppressed_count"],
            delivery["generic_prompt_term_count"],
        )
        self.assertIn("generic_meta_terms_only", delivery["foreground_suppression_reasons"])

    def test_reviewed_semantic_trigger_does_not_turn_plain_code_task_into_recall(self) -> None:
        registry_path = self.root / "code-surface-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:dashboard",
                            "title": "Dashboard design memory",
                            "project_label": "Product UI",
                            "anchor_titles": ["Dashboard hover behavior"],
                            "keywords": ["dashboard", "hover"],
                            "summary": "Prior source-backed dashboard decisions.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "code_surface_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Dashboard memory",
                    "aliases": ["dashboard"],
                    "confidence": 0.91,
                    "when_to_use": "Use when the user asks to recall the dashboard decision.",
                    "source_refs": [{"thread_key": "session:dashboard", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("plain code-surface tasks should stay local and quiet")

        result = hook.assess_prompt(
            "Fix the dashboard hover test and update the CSS.",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["semantic_gate"], None)

    def test_reviewed_semantic_trigger_can_scent_code_surface_continuation(self) -> None:
        registry_path = self.root / "code-surface-continuation-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:atlas",
                            "title": "Atlas dashboard memory",
                            "project_label": "Atlas dashboard",
                            "anchor_titles": ["Atlas dashboard layout sprint"],
                            "keywords": ["Atlas dashboard", "layout", "sprint"],
                            "summary": "Prior source-backed dashboard layout context.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "code_surface_continuation_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Atlas dashboard continuation",
                    "aliases": ["Atlas dashboard", "layout sprint"],
                    "confidence": 0.91,
                    "when_to_use": "Use when the user asks to continue the Atlas dashboard context.",
                    "when_not_to_use": "Do not use for plain implementation tasks.",
                    "source_refs": [{"thread_key": "session:atlas", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("reviewed trigger should provide local continuation scent")

        result = hook.assess_prompt(
            "Fix Atlas dashboard layout, but only continue that context; do not implement.",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertTrue(
            any(
                "atlas" in str(term).casefold() and "dashboard" in str(term).casefold()
                for term in result["query_terms"]
            )
        )
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_foreground_budget_caps_semantic_gate_timeout(self) -> None:
        registry_path = self.root / "semantic-budget-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        seen: dict[str, float | bool] = {}

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            seen["timeout"] = float(kwargs["timeout"])
            seen["deadline_seconds"] = float(kwargs["deadline_seconds"])
            seen["foreground"] = bool(kwargs["foreground"])
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "memory_scope": [],
                "reasons": ["test"],
                "workers": [],
                "errors": [],
                "cached": False,
                "model_route": {"provider": "test-provider", "model": "test-model"},
                "cache_diagnostics": {"lookup": "disabled"},
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=3000,
            search_budget=0,
        )

        self.assertIn("timeout", seen)
        self.assertLessEqual(seen["timeout"], 1.8)
        self.assertEqual(seen["deadline_seconds"], result["semantic_gate"]["budget"]["overall_deadline_seconds"])
        self.assertTrue(seen["foreground"])
        self.assertEqual(result["semantic_gate"]["available"], False)
        self.assertEqual(result["semantic_gate"]["budget"]["requested_timeout"], 3)
        self.assertEqual(result["semantic_gate"]["budget"]["effective_timeout"], seen["timeout"])
        self.assertTrue(result["semantic_gate"]["budget"]["budget_clipped"])
        self.assertEqual(result["semantic_gate"]["model_route"]["provider"], "test-provider")
        self.assertEqual(result["semantic_gate"]["cache_diagnostics"]["lookup"], "disabled")

    def test_foreground_budget_timeout_gets_specific_semantic_diagnostic(self) -> None:
        registry_path = self.root / "semantic-timeout-diagnostic-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "memory_scope": [],
                "reasons": ["gate: The read operation timed out"],
                "workers": [],
                "errors": ["gate: The read operation timed out"],
                "error_buckets": {"read_timeout": 1},
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=3000,
            search_budget=0,
        )

        self.assertEqual(
            result["semantic_gate"]["availability_reason"],
            "foreground_budget_timeout",
        )
        self.assertEqual(
            result["semantic_gate"]["diagnostic"],
            "semantic_timed_out_under_foreground_budget",
        )
        self.assertEqual(result["semantic_gate"]["error_buckets"], {"read_timeout": 1})

    def test_tiny_foreground_budget_skips_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-budget-skip-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError(
                "semantic gate should be skipped when no foreground budget remains"
            )

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fail_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=1,
            search_budget=0,
        )

        self.assertEqual(result["semantic_gate"]["available"], False)
        self.assertIn("foreground budget", " ".join(result["semantic_gate"]["reasons"]))
        self.assertEqual(
            result["semantic_gate"]["availability_reason"],
            "foreground_budget_skipped",
        )
        self.assertEqual(
            result["semantic_gate"]["diagnostic"],
            "semantic_skipped_under_foreground_budget",
        )
        self.assertEqual(result["semantic_gate"]["error_buckets"], {"foreground_budget": 1})
        self.assertEqual(result["semantic_gate"]["budget"]["requested_timeout"], 3)
        self.assertIsNone(result["semantic_gate"]["budget"]["effective_timeout"])
        self.assertTrue(result["semantic_gate"]["budget"]["budget_clipped"])

    def test_multilingual_natural_language_can_reach_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-registry-ru" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "海马体记忆", "working memory"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.87,
                "intent": "continuation",
                "query_aliases": ["AIppocampus", "海马体记忆", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Russian paraphrase of external hippocampus memory"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "Как там мой внешний гиппокамп памяти и продолжение разговоров?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")
        self.assertIn("AIppocampus", result["query_terms"])

    def test_space_less_japanese_prompt_can_reach_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-registry-ja" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "海马体记忆", "working memory"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.87,
                "intent": "continuation",
                "query_aliases": ["AIppocampus", "海马体记忆"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Japanese paraphrase"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "外部海馬みたいな記憶システムの進捗はどう？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")

    def test_latin_language_long_exact_question_can_reach_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-registry-es" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "external hippocampus"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.87,
                "intent": "recall",
                "query_aliases": ["AIppocampus", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Spanish exact-recall paraphrase"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "¿Puedes recuperar la frase exacta que dijiste sobre el hipocampo externo?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")

    def test_semantic_gate_evidence_is_guarded_for_fuzzy_status_prompt(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "high",
                "reasons": ["model wants evidence"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])

    def test_semantic_context_can_upgrade_fuzzy_status_to_evidence_when_risk_is_low(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["subconscious context says this is a specific recall, not personalization"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("semantic-context evidence upgrade", " ".join(result["reasons"]))

    def test_negative_evidence_intent_keeps_semantic_evidence_as_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "continuation",
                "query_aliases": ["raw history", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model wants evidence"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "raw history 明明在本地这条线继续，但先只给 scent，不要引用原话。",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("evidence withheld", " ".join(result["reasons"]))

    def test_without_cited_row_keeps_unsupported_memory_pain_prompt_as_scent(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:memory-pain-negative",
            [
                {
                    "source_line": 51,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Structured extraction discussed Neon City as a deliberately fake "
                        "memory-pain example, not a source-backed user fact."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:memory-pain-negative",
            title="Memory pain structured extraction",
            keywords=["structured extraction", "Neon City", "memory-pain"],
            summary="Neon City was only a fake memory-pain example.",
            messages_path=messages,
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["structured extraction", "Neon City"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model sees a source word but misses the negation"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        prompt = (
            "Could you keep the structured extraction about Neon City unsupported "
            "without a cited row?"
        )
        result = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertTrue(recall_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("evidence withheld", " ".join(result["reasons"]))

    def test_russian_without_source_keeps_semantic_evidence_as_scent(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:memory-pain-negative-ru",
            [
                {
                    "source_line": 51,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Structured extraction discussed Neon City as a deliberately fake "
                        "memory-pain example, not a source-backed user fact."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:memory-pain-negative-ru",
            title="Memory pain structured extraction",
            keywords=["structured extraction", "Neon City", "memory-pain"],
            summary="Neon City was only a fake memory-pain example.",
            messages_path=messages,
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["structured extraction", "Neon City"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model sees a source word but misses the Russian negation"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        prompt = (
            "Оставь структурированное извлечение про Neon City неподтвержденным "
            "без строки источника."
        )
        result = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertTrue(recall_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("evidence withheld", " ".join(result["reasons"]))

    def test_semantic_evidence_bridge_survives_semantic_budget_spend(self) -> None:
        def slow_semantic_gate(prompt: str, **kwargs) -> dict:
            time.sleep(1.05)
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["bounded recall request"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=slow_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=1900,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("semantic-context evidence upgrade", " ".join(result["reasons"]))
        self.assertIn("semantic budget spend", " ".join(result["reasons"]))

    def test_semantic_evidence_without_source_bridge_gets_diagnostic(self) -> None:
        registry_path = self.root / "semantic-bridge-miss-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["missing clean-source topic"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["semantic evidence but no local source rows"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertEqual(
            result["semantic_bridge_diagnostic"],
            "semantic_evidence_without_source_bridge",
        )
        self.assertIn("semantic evidence did not bridge", " ".join(result["reasons"]))
        payload = hook.hook_stdout_payload(result)
        self.assertIsNotNone(payload)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Semantic recall route", context)
        self.assertIn("missing clean-source topic", context)
        self.assertIn("direction_only", context)
        self.assertIn("reopen clean source", context)

    def test_vague_cross_project_semantic_evidence_stays_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model picked a source for a vague referent"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "上次我们讨论的那个方案怎么说来着？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("vague cross-project referent", " ".join(result["reasons"]))

    def test_russian_vague_cross_project_semantic_evidence_stays_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model picked a source for a vague Russian referent"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "Как мы в прошлый раз описывали тот план?",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("vague cross-project referent", " ".join(result["reasons"]))

    def test_semantic_continuation_does_not_upgrade_to_evidence_without_source_intent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "continuation",
                "query_aliases": ["raw history", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model over-eagerly wants evidence"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "external hippocampus hook 那条线先继续推进。",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertTrue(result["semantic_source_reopen_route"])
        packet = result["ambient_recall"]["fresh_thread_packet"]
        self.assertEqual(packet["support_level"], "source_required")
        self.assertEqual(packet["action_grammar"], "reopenable_route")
        self.assertEqual(packet["reopen_plan"]["status"], "ready")
        self.assertFalse(packet["reopen_plan"]["manual_query_invention_expected"])

    def test_exact_wording_topic_continuation_stays_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.85,
                "intent": "continuation",
                "query_aliases": ["self-continuity", "生命还能变成什么"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["continue the theme only"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "self-continuity 那句 quote 还要怎么处理?",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])

    def test_english_cite_prompt_requests_source_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:atlas-evidence",
            [
                {
                    "source_line": 41,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "AIppocampus Atlas recall gate should stay project-scoped "
                        "and only scent ambiguous continuation."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:atlas-evidence",
            title="AIppocampus Atlas recall gate",
            keywords=["AIppocampus", "Atlas", "recall gate", "project-scoped"],
            summary="Atlas recall gate should stay project-scoped.",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "Can you cite AIppocampus Atlas recall gate should stay project-scoped?",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertEqual(result["evidence"][0]["thread_key"], "session:atlas-evidence")

    def test_source_backed_evidence_prompt_requests_source_evidence(self) -> None:
        result = hook.assess_prompt(
            "请给 source-backed evidence：raw history 明明在本地。",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])

    def test_current_checkout_fact_prompt_does_not_use_old_project_source_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:old-project-test-command",
            [
                {
                    "source_line": 58,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "OldProject 的测试命令是 pytest -q；这只适用于旧仓库。",
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:old-project-test-command",
            title="OldProject test command",
            keywords=["source-backed evidence", "测试命令", "pytest"],
            summary="OldProject used pytest -q as its test command.",
            messages_path=messages,
            project_label="OldProject",
        )

        result = hook.assess_prompt(
            "请给这个 repo 的 source-backed evidence：测试命令是什么？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["evidence"])
        self.assertIn("current checkout required", " ".join(result["reasons"]))
        self.assertIsNone(hook.context_for_hook(result))

    def test_russian_natural_recall_can_recover_source_evidence_without_semantic_gate(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:russian-natural-evidence",
            [
                {
                    "source_line": 73,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Мы описали внешний гиппокамп как trigger recall: "
                        "память всплывает только когда текущий вопрос дает устойчивый якорь."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:russian-natural-evidence",
            title="Внешний гиппокамп trigger recall",
            keywords=["внешний гиппокамп", "trigger recall", "устойчивый якорь"],
            summary="Русская формулировка про внешний гиппокамп и trigger recall.",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "Найди, как мы раньше формулировали внешний гиппокамп и trigger recall.",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("внешний гиппокамп", result["evidence"][0]["snippet"])

    def test_russian_prior_wording_recall_can_recover_source_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:russian-prior-wording",
            [
                {
                    "source_line": 91,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Прежняя формулировка про raw history после сжатия: "
                        "история уже локальна, но после сжатия агент не знает, что искать."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:russian-prior-wording",
            title="Прежняя формулировка raw history",
            keywords=["raw history", "прежняя формулировка", "сжатия"],
            summary="Русская формулировка про raw history после сжатия.",
            messages_path=messages,
        )
        prompt = "Найди прежнюю формулировку про raw history после сжатия."

        result = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertTrue(recall_cues.natural_evidence_intent(prompt))
        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("raw history", result["evidence"][0]["snippet"])

    def test_explicit_personal_pressure_recall_uses_source_evidence_boundary(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:pressure-prior-wording",
            [
                {
                    "source_line": 97,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "之前压力那段的结论：开源发布前先收窄验收口径，"
                        "保留一个可执行的下一步，不要把所有焦虑都变成待办。"
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:pressure-prior-wording",
            title="压力那段怎么说",
            keywords=["压力", "开源发布", "验收口径"],
            summary="之前压力那段说要收窄验收口径并保留可执行下一步。",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "我之前压力那段到底怎么说的？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertEqual(result["scent_threshold_policy"]["risk_boundary"], "personal_continuity")
        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("开源发布前先收窄验收口径", result["evidence"][0]["snippet"])

    def test_scent_only_topic_can_be_explicitly_retrieved(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:scent-boundary",
            [
                {
                    "source_line": 41,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "AIppocampus Atlas recall gate should stay project-scoped "
                        "and only scent ambiguous continuation."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:scent-boundary",
            title="AIppocampus Atlas recall gate",
            keywords=["recall gate", "scent-only", "project-scoped"],
            summary="Prior work discussed the recall gate scent-only boundary.",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "recall gate 的 scent-only 边界找回。",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertFalse(recall_cues.negative_evidence_intent("recall gate 的 scent-only 边界找回。"))

    def test_natural_evidence_intent_upgrades_strong_scent_to_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:life-evidence",
            [
                {
                    "source_line": 88,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "结论：life-wide evidence 当前不够，应该写成 honest readiness gate，"
                        "不能把 semantic sidecar 命中当成已经证实。"
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:life-evidence",
            title="AIppocampus life-wide evidence",
            keywords=["life-wide evidence", "honest readiness gate", "semantic sidecar"],
            summary="Stage 2 life-wide evidence 不够，需要 honest readiness gate。",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "上次关于 life-wide evidence 不够的结论是什么？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertEqual(result["evidence"][0]["phase"], "final_answer")
        self.assertIn("honest readiness gate", result["evidence"][0]["snippet"])
        self.assertIn("natural evidence intent", " ".join(result["reasons"]))

    def test_evidence_quality_prefers_final_answer_over_subagent_process_noise(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:ambient-loop",
            [
                {
                    "source_line": 41,
                    "role": "user",
                    "phase": "",
                    "is_final": False,
                    "text": (
                        "<subagent_notification> ambient recall ambient recall ambient recall "
                        "闭环 闭环 hook cache evidence process details only </subagent_notification>"
                    ),
                },
                {
                    "source_line": 120,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "ambient recall 闭环是 UserPromptSubmit hook 到 cache 再到 evidence 的运行链路。",
                },
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:ambient-loop",
            title="Ambient recall loop",
            keywords=["ambient recall", "闭环", "hook", "cache", "evidence"],
            summary="讨论 ambient recall hook/cache/evidence 闭环。",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "找一下之前说 ambient recall 闭环的那段",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=1,
            use_semantic_gate=False,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertEqual(result["evidence"][0]["line"], 120)
        self.assertNotIn("<subagent_notification>", result["evidence"][0]["snippet"])

    def test_association_boost_counts_each_thread_once(self) -> None:
        entry = {
            "thread_key": "session:dup",
            "title": "Duplicate source thread",
            "updated_at": "2026-05-25T01:00:00Z",
            "paths": {},
        }
        match = {
            "term": "T-Sense",
            "status": "staging",
            "confidence": 0.62,
            "hit_count": 3,
            "matched_terms": ["T-Sense"],
            "threads": [
                {"thread_key": "session:dup", "line": 1},
                {"thread_key": "session:dup", "line": 2},
                {"thread_key": "session:dup", "line": 3},
            ],
        }

        merged = hook.merge_association_candidates([], {"threads": [entry]}, [match], ["T-Sense"])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["score"], hook.association_boost(match, 1))

    def test_clean_source_probe_can_rerank_specific_thread_above_broad_project_scent(self) -> None:
        old_messages = self._write_clean_thread(
            "session:old-project",
            "2026-05-20T00:00:00Z",
            "这里讨论过 T-Sense 的普通项目背景，但没有具体的新搜索方案。",
        )
        exact_messages = self._write_clean_thread(
            "session:exact-search",
            "2026-05-25T00:00:00Z",
            "T-Sense 可以评估 WukongVector WukongVector WukongVector WukongVector WukongVector 搜索层，先做小范围 spike。",
        )
        registry_path = self.root / "probe-registry" / "threads.json"
        registry_path.parent.mkdir()
        entries = [
            {
                "thread_key": "session:old-project",
                "title": "T-Sense · 2026-05-20",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-20T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(old_messages)},
            },
            {
                "thread_key": "session:exact-search",
                "title": "T-Sense · 2026-05-25",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-25T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(exact_messages)},
            },
        ]
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        associations = registry_path.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "T-Sense": {
                            "term": "T-Sense",
                            "status": "staging",
                            "confidence": 0.62,
                            "hit_count": 40,
                            "related_terms": [],
                            "threads": [
                                {
                                    "thread_key": "session:old-project",
                                    "title": "T-Sense · 2026-05-20",
                                }
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "T-SENSE 现在是不是应该采用 WukongVector 搜索？",
            cwd=self.workspace,
            registry_path=registry_path,
            associations_path=associations,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:exact-search")
        self.assertTrue(result["evidence"])
        self.assertIn("evidence-lite", " ".join(result["reasons"]))

    def test_project_timeline_recency_cue_can_add_latest_project_thread(self) -> None:
        old_messages = self._write_clean_thread(
            "session:timeline-old",
            "2026-05-20T00:00:00Z",
            "T-Sense 的旧讨论。",
        )
        latest_messages = self._write_clean_thread(
            "session:timeline-latest",
            "2026-05-25T00:00:00Z",
            "T-Sense 最新关心的是 Go runtime spike。",
        )
        registry_path = self.root / "timeline-registry" / "threads.json"
        registry_path.parent.mkdir()
        entries = [
            {
                "thread_key": "session:timeline-old",
                "title": "T-Sense old",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-20T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(old_messages)},
            },
            {
                "thread_key": "session:timeline-latest",
                "title": "T-Sense latest",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-25T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(latest_messages)},
            },
        ]
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        (registry_path.parent / "associations.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "T-Sense": {
                            "term": "T-Sense",
                            "status": "staging",
                            "confidence": 0.62,
                            "hit_count": 2,
                            "threads": [{"thread_key": "session:timeline-old"}],
                        },
                        "当前线程": {
                            "term": "当前线程",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 20,
                            "threads": [{"thread_key": "session:timeline-old"}],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "projects": {
                        "project:t-sense": {
                            "project_key": "project:t-sense",
                            "project_label": "T-Sense",
                            "project_tags": ["T-Sense"],
                            "latest_turns": [{"thread_key": "session:timeline-latest"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "关于T-SENSE，我在当前线程之外最后关心的主题是什么？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:timeline-latest")
        self.assertIn("project timeline", " ".join(result["reasons"]))

    def test_life_wide_timeline_recency_cue_can_add_quiet_scent(self) -> None:
        registry_path = self.root / "life-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "session_meta": {"timestamp": "2026-05-24T00:00:00Z"},
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "scope_label": "personal_reflection",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "title": "Life continuity notes",
                                        "timestamp": "2026-05-24T00:00:00Z",
                                        "turn_id": "turn-life-1",
                                        "scope_labels": ["personal_reflection", "open_question"],
                                        "topic_terms": ["焦虑", "问题"],
                                        "source_refs": [
                                            {
                                                "thread_key": "session:life-wide",
                                                "message_id": "msg-life-1",
                                                "turn_id": "turn-life-1",
                                                "clean_ordinal": 4,
                                                "source_line": 77,
                                                "role": "user",
                                                "phase": "",
                                            }
                                        ],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近那个焦虑问题我后来有推进吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:life-wide")
        self.assertTrue(result["candidates"][0]["life_wide_timeline_source"])
        self.assertIn("personal_reflection", result["candidates"][0]["scope_labels"])
        self.assertNotIn("source_refs", result["candidates"][0])
        self.assertEqual(result["candidates"][0]["source_ref_count"], 1)
        self.assertIn("life-wide timeline", " ".join(result["reasons"]))

    def test_life_wide_timeline_does_not_trigger_for_ordinary_code_prompt(self) -> None:
        registry_path = self.root / "life-code-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "scope_label": "personal_reflection",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["焦虑"],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近帮我修 TypeScript build error，顺手跑测试",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_life_wide_timeline_does_not_trigger_for_generic_status_prompt(self) -> None:
        registry_path = self.root / "life-status-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "scope_label": "personal_reflection",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "scope_labels": ["personal_reflection", "open_question"],
                                        "topic_terms": ["焦虑", "问题"],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近这个问题的状态怎么样？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_life_wide_timeline_does_not_substring_match_lifecycle(self) -> None:
        registry_path = self.root / "life-english-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "life_context": {
                                "scope_label": "life_context",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "scope_labels": ["life_context"],
                                        "topic_terms": ["life"],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "latest lifecycle hook status",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_working_memory_can_emit_soft_scent_without_manual_review_queue(self) -> None:
        registry_path = self.root / "working-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:app",
                            "title": "T-Sense-App",
                            "project_label": "T-Sense",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        working = registry_path.parent / "working_memory.jsonl"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "confirm_when_relevant",
                    "ask_policy": "ask_only_when_current_action_would_depend_on_this_or_sources_conflict",
                    "risk": "high",
                    "candidate_type": "contradiction_review",
                    "title": "Jackie mutation consent gate",
                    "summary": "Jackie tool bridge mutations should require explicit user consent before Review card writes.",
                    "recommendation": "Ask only if implementing mutation behavior.",
                    "confidence": 0.7,
                    "project_label": "T-Sense",
                    "trigger_terms": ["Jackie", "mutation", "consent gate", "Review card"],
                    "source_refs": [
                        {"thread_key": "session:app", "title": "T-Sense-App", "line": 149}
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "Jackie mutation flow 现在怎么处理？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertTrue(result["working_memory"])
        context = hook.context_for_hook(result)
        self.assertIn("Soft working memory", context)
        self.assertIn("Ask the user only if", context)

    def test_same_thread_continuation_can_lower_scent_threshold_for_weak_route(self) -> None:
        registry_path = self.root / "threshold-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:threshold",
                            "title": "Quiet support",
                            "summary": "qa",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "qa 现在怎么看，这个很重要",
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-123",
            topic_epoch="epoch-stable",
            use_thread_cache=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertLess(
            result["scent_threshold_policy"]["effective_threshold"],
            result["scent_threshold_policy"]["base_threshold"],
        )
        self.assertEqual(
            result["scent_threshold_policy"]["adjustments"][0]["reason"],
            "same_thread_decision_continuation",
        )

    def test_topic_signal_accumulator_can_surface_later_weak_route(self) -> None:
        registry_path = self.root / "topic-signal-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:topic-signal",
                            "title": "Quiet support",
                            "summary": "qa",
                            "keywords": ["qa"],
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cache_path = self.root / "topic-signal-cache.json"
        prompt = "qa 现在怎么看"

        baseline = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-123",
            topic_epoch="epoch-signal",
            ambient_cache_path=cache_path,
            use_thread_cache=False,
            use_semantic_gate=False,
            search_budget=0,
        )
        signal_path = thread_cache.signal_accumulator_path_for_cache(cache_path)
        for _ in range(2):
            thread_cache.record_topic_signal(
                signal_path,
                thread_id="thread-123",
                workspace=str(self.workspace),
                topic_epoch="epoch-signal",
                terms=recall_cues.expand_query_terms(prompt),
                outcome="weak_signal",
                reason_codes=["below_threshold"],
            )

        later = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-123",
            topic_epoch="epoch-signal",
            ambient_cache_path=cache_path,
            use_thread_cache=False,
            use_semantic_gate=False,
            search_budget=0,
        )
        raw = signal_path.read_text(encoding="utf-8")

        self.assertEqual(baseline["decision"], "skip")
        self.assertEqual(later["decision"], "scent")
        self.assertIn(
            "topic_signal_accumulator_eased",
            {
                item["reason"]
                for item in later["scent_threshold_policy"]["adjustments"]
            },
        )
        self.assertIn("same-topic recall signal crossed routing threshold", later["reasons"])
        self.assertGreaterEqual(
            later["scent_threshold_policy"]["topic_signal_accumulator"]["weak_signal_count"],
            3,
        )
        self.assertNotIn(prompt, raw)
        self.assertNotIn(str(self.workspace).replace("\\", "/"), raw.replace("\\", "/"))

    def test_broad_fresh_personal_prompt_uses_continuity_boundary(self) -> None:
        registry_path = self.root / "fresh-personal-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:threshold",
                            "title": "Quiet support",
                            "summary": "qa",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "我压力有点大，qa 很重要",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(
            result["scent_threshold_policy"]["effective_threshold"],
            result["scent_threshold_policy"]["base_threshold"],
        )
        self.assertEqual(result["scent_threshold_policy"]["risk_boundary"], "personal_continuity")

    def test_dream_hypothesis_working_memory_renders_uncertainty_boundary(self) -> None:
        registry_path = self.root / "dream-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:dream",
                            "title": "Dream bridge",
                            "project_label": "AIppocampus",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        working = registry_path.parent / "working_memory.jsonl"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "ask_policy": "do_not_ask_unless_contradicted_or_action_depends_on_uncertain_scope",
                    "risk": "medium",
                    "candidate_type": "dream_hypothesis",
                    "title": "Continuity dream bridge",
                    "summary": "A dream hypothesis about continuity and source refs.",
                    "recommendation": "Use quietly; reopen source before strong claims.",
                    "confidence": 0.66,
                    "project_label": "AIppocampus",
                    "trigger_terms": ["continuity", "source refs"],
                    "source_refs": [
                        {
                            "thread_key": "session:dream",
                            "title": "Dream bridge",
                            "message_id": "msg-dream",
                            "line": 12,
                        }
                    ],
                    "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                    "review_state": "agent_adjudicated",
                    "foreground_use": {
                        "default_action": "quiet_substrate",
                        "strong_claim_requires_source_reopen": True,
                    },
                    "sensitive_use_gate": {"state": "allowed"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "AIppocampus continuity source refs 这条线索还在吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            search_budget=0,
        )

        context = hook.context_for_hook(result)
        self.assertIn("Dream hypothesis, not source fact", context)
        self.assertIn("reopen source", context)
        self.assertIn("Use quietly", context)

    def test_working_memory_question_scent_obeys_cap_and_stop_tracking(self) -> None:
        registry_path = self.root / "question-working-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:alignment",
                            "title": "Alignment thread",
                            "project_label": "AIppocampus",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        working = registry_path.parent / "working_memory.jsonl"
        policy_path = registry_path.parent / "ambient_recall_policy.jsonl"
        cache_path = registry_path.parent / "ambient_cache.json"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "ask_policy": "do_not_ask_unless_contradicted_or_action_depends_on_uncertain_scope",
                    "risk": "medium",
                    "candidate_key": "wm_alignment_question",
                    "candidate_type": "question_link",
                    "title": "Agent alignment drift",
                    "summary": "Recurring question about agent output drifting from user intent.",
                    "recommendation": "Use as quiet question scent only when alignment drift is relevant.",
                    "confidence": 0.82,
                    "project_label": "AIppocampus",
                    "trigger_terms": ["alignment drift", "agent intent"],
                    "source_finding_ids": ["sf_a", "sf_b"],
                    "source_refs": [
                        {"thread_key": "session:alignment", "title": "Alignment thread", "line": 77}
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        first = hook.assess_prompt(
            "alignment drift 这条 recurring question 要怎么处理？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            ambient_policy_path=policy_path,
            ambient_cache_path=cache_path,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )
        second = hook.assess_prompt(
            "alignment drift 这条 recurring question 要怎么处理？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            ambient_policy_path=policy_path,
            ambient_cache_path=cache_path,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )
        stop = hook.assess_prompt(
            "stop tracking this",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            ambient_policy_path=policy_path,
            ambient_cache_path=cache_path,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )

        self.assertEqual(first["decision"], "scent")
        self.assertTrue(first["ambient_recall"]["cards"][0]["ambient_policy"]["target_keys"])
        self.assertEqual(second["decision"], "skip")
        self.assertEqual(second["ambient_policy"]["frequency_capped"], 1)
        self.assertEqual(stop["ambient_policy_update"]["action"], "dismiss")
        self.assertEqual(stop["ambient_policy_update"]["target_count"], 1)

    def test_concept_graph_expansion_can_surface_indirect_memory_scent(self) -> None:
        messages = self._write_clean_thread(
            "session:runtime-memory",
            "2026-05-25T00:00:00Z",
            "T-Sense 的 Go runtime spike 应该先验证 gotd，再决定是否迁移本地核心。",
        )
        registry_path = self.root / "concept-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:runtime-memory",
                            "title": "T-Sense Go runtime",
                            "project_label": "T-Sense",
                            "session_meta": {"timestamp": "2026-05-25T00:00:00Z"},
                            "paths": {"clean_source_messages_jsonl": str(messages)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        associations = registry_path.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["Go runtime"],
                            "threads": [],
                        },
                        "Go runtime": {
                            "term": "Go runtime",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["gotd"],
                            "threads": [],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        concept_graph_path = concept_graph.default_concept_graph_path(registry_path=registry_path)
        concept_graph.build_concept_graph(associations, concept_graph_path)

        without_graph = hook.assess_prompt(
            "本地底座换语言是不是更好？",
            cwd=self.workspace,
            registry_path=registry_path,
            associations_path=associations,
            use_concept_graph=False,
            search_budget=0,
        )
        with_graph = hook.assess_prompt(
            "本地底座换语言是不是更好？",
            cwd=self.workspace,
            registry_path=registry_path,
            associations_path=associations,
            concept_graph_path=concept_graph_path,
            search_budget=0,
        )

        self.assertEqual(without_graph["decision"], "skip")
        self.assertEqual(with_graph["decision"], "scent")
        self.assertEqual(with_graph["candidates"][0]["thread_key"], "session:runtime-memory")
        self.assertIn("Go runtime", with_graph["query_terms"])
        self.assertIn("concept graph expansion", " ".join(with_graph["reasons"]))

    def test_weak_deictic_reviewed_trigger_does_not_force_evidence(self) -> None:
        triggers_path = self.root / "weak_deictic_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "External hippocampus recall continuity",
                    "aliases": ["外置海马体", "external hippocampus"],
                    "confidence": 0.9,
                    "when_to_use": "Use for AIppocampus external hippocampus continuation.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        result = hook.assess_prompt(
            "这个外置海马体还要再收一下",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_triggers_path=triggers_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "scent")

    def test_goal_injection_prompt_stays_silent_even_with_registry_overlap(self) -> None:
        result = hook.assess_prompt(
            "Current goal for this thread: status ACTIVE, token budget remaining",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_explicit_memory_prompt_emits_evidence(self) -> None:
        result = hook.assess_prompt(
            "你还能找回之前那句生命还能变成什么，而我能不能还是我吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        context = hook.context_for_hook(result)
        self.assertIsNotNone(context)
        self.assertIn("Ambient recall evidence", context)
        self.assertIn("line 190", context)
        self.assertNotIn("line 999", context)
        self.assertIn("final_answer", context)
        self.assertIn("bounded source-backed evidence", context)
        self.assertNotIn("search the source thread before relying on exact wording", context)
        self.assertFalse(result["ambient_recall"]["cards"][0]["source_reopen_required"])
        self.assertEqual(
            result["ambient_recall"]["cards"][0]["authority_state"],
            "bounded_evidence_ready",
        )
        ambient_summary = hook.ambient_debug_summary(result)
        self.assertEqual(ambient_summary["source_reopen_required_count"], 0)
        self.assertEqual(ambient_summary["authority_counts"]["bounded_evidence_ready"], 1)
        self.assertEqual(ambient_summary["reopen_required_before_claim_count"], 0)
        self.assertEqual(ambient_summary["reopen_recommended_for_exact_quote_count"], 1)

    def test_original_wording_prompt_uses_deep_archival_recall(self) -> None:
        result = hook.assess_prompt(
            "你还能找回之前那句生命还能变成什么的原话吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["deep_archival_requested"])
        self.assertEqual(result["ambient_recall"]["mode"], "deep_archival_recall")
        context = hook.context_for_hook(result)
        self.assertIsNotNone(context)
        self.assertIn("deep archival", context.casefold())

    def test_hook_json_uses_user_prompt_submit_additional_context(self) -> None:
        result = hook.assess_prompt(
            "你之前说过外置海马体为什么重要吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )
        payload = hook.hook_stdout_payload(result)

        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"],
            "UserPromptSubmit",
        )
        self.assertIn(
            "additionalContext",
            payload["hookSpecificOutput"],
        )

    def test_prompt_hook_can_enqueue_background_warm_job_on_cache_miss(self) -> None:
        scheduled: list[dict] = []

        def fake_schedule(prompt: str, **kwargs):
            scheduled.append({"prompt": prompt, **kwargs})
            return {"status": "queued", "job_id": "job-test", "spawned": False}

        with patch(
            "aippocampus_runtime.recall.prompt_recall_ambient.schedule_warm_ambient_recall",
            fake_schedule,
        ):
            result = hook.assess_prompt(
                "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-test",
                warm_background=True,
                search_budget=0,
            )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0]["thread_id"], "thread-a")
        self.assertEqual(scheduled[0]["current_thread_key"], "session:thread-a")
        self.assertEqual(scheduled[0]["prompt_trace"][0]["thread_key"], "session:thread-a")
        self.assertEqual(scheduled[0]["prompt_trace"][0]["phase"], "current_prompt")
        self.assertEqual(scheduled[0]["topic_epoch"], "epoch-test")
        self.assertFalse(scheduled[0]["wait_all_foreground"])
        self.assertEqual(result["ambient_recall"]["warm_background"]["status"], "queued")
        self.assertEqual(result["ambient_recall"]["warm_background"]["job_id"], "job-test")
        self.assertTrue(result["route_delivery_diagnostic"]["background_scheduled"])

    def test_prompt_hook_creates_navigation_only_active_recall_lock(self) -> None:
        cache_path = self.root / "ambient-cache-lock.json"
        raw_prompt = "hook 机制就像人类的触发式联想，DO NOT STORE THIS PROMPT"

        result = hook.assess_prompt(
            raw_prompt,
            cwd=self.workspace,
            registry_path=self.registry,
            thread_id="thread-a",
            topic_epoch="epoch-lock",
            ambient_cache_path=cache_path,
            warm_background=False,
            search_budget=0,
        )
        lock_path = cache_path.parent / "active_recall_locks.json"
        raw_lock = lock_path.read_text(encoding="utf-8")
        lock = result["ambient_recall"]["active_recall_lock"]

        self.assertEqual(result["decision"], "scent")
        self.assertIn(lock["state"], {"pending", "ready"})
        self.assertEqual(lock["support_level"], "scent")
        self.assertTrue(lock["source_reopen_required"])
        self.assertNotIn("DO NOT STORE THIS PROMPT", raw_lock)
        self.assertNotIn(str(self.workspace).replace("\\", "/"), raw_lock.replace("\\", "/"))
        self.assertNotIn("snippet", raw_lock.casefold())

    def test_prompt_hook_prioritizes_warm_thread_cache_and_exposes_metadata(self) -> None:
        cache_path = self.root / "ambient-cache.json"
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-cache",
            cards=[
                {
                    "card_id": "cached-card",
                    "theme": "cached warm context",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["ambient recall"],
                }
            ],
            mode="active_gentle_nudge",
            confidence="medium",
            query_aliases=["cached alias"],
            topic_epoch_decision={"action": "reuse", "label": "ambient", "confidence": 0.7},
            visibility_bias="active_gentle_nudge",
        )

        result = hook.assess_prompt(
            "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            cwd=self.workspace,
            registry_path=self.registry,
            thread_id="thread-a",
            topic_epoch="epoch-cache",
            ambient_cache_path=cache_path,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        self.assertEqual(ambient["cache_status"]["status"], "hit")
        self.assertEqual(ambient["cache_status"]["query_aliases"], ["cached alias"])
        self.assertEqual(ambient["cache_status"]["topic_epoch_decision"]["action"], "reuse")
        self.assertEqual(ambient["cache_status"]["visibility_bias"], "active_gentle_nudge")
        self.assertEqual(ambient["cards"][0]["card_id"], "cached-card")
        self.assertEqual(ambient["cards"][0]["provenance_class"], "cached_warm_card")
        self.assertEqual(ambient["cards"][0]["cached_origin"], "unknown")
        context = hook.context_for_hook(result)
        self.assertIn("cached warm candidate", context.casefold())

    def test_prompt_hook_uses_related_cache_after_paraphrase_epoch_miss(self) -> None:
        cache_path = self.root / "ambient-cache-related.json"
        registry_path = self._write_single_thread_registry(
            title="Ambient recall design",
            keywords=["ambient recall", "associative cache"],
            summary="Prior notes about warm ambient recall cards and associative cache behavior.",
        )
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-first-phrasing",
            cards=[
                {
                    "card_id": "cached-related-card",
                    "theme": "Ambient recall design: ambient recall",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["ambient recall"],
                }
            ],
            mode="active_gentle_nudge",
            confidence="medium",
            related_fingerprints=thread_cache.related_signal_fingerprints(
                candidates=[{"thread_key": "session:single-thread"}],
            ),
            topic_epoch_decision={
                "action": "reuse",
                "label": "ambient recall cache continuity",
            },
        )

        result = hook.assess_prompt(
            "ambient associative cache 这个暖启动还能再顺一点吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-a",
            ambient_cache_path=cache_path,
            warm_background=True,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        self.assertEqual(ambient["cache_status"]["status"], "related_hit")
        self.assertEqual(ambient["cache_status"]["matched_topic_epoch"], "epoch-first-phrasing")
        self.assertEqual(ambient["cards"][0]["card_id"], "cached-related-card")
        self.assertNotIn("warm_background", ambient)

    def test_prompt_hook_next_turn_reads_detached_warm_cache_without_rescheduling(self) -> None:
        cache_path = self.root / "ambient-cache-next-turn.json"
        scheduled: list[dict] = []

        def fake_schedule(prompt: str, **kwargs):
            scheduled.append({"prompt": prompt, **kwargs})
            thread_cache.write_thread_cache(
                kwargs["cache_path"],
                thread_id=kwargs["thread_id"],
                workspace=str(kwargs["cwd"]),
                topic_epoch=kwargs["topic_epoch"],
                cards=[
                    {
                        "card_id": "detached-card",
                        "theme": "detached warm result",
                        "support_level": "candidate",
                        "visibility": "active_gentle_nudge",
                        "matched_terms": ["ambient recall"],
                    }
                ],
                mode="active_gentle_nudge",
                confidence="medium",
                query_aliases=["detached alias"],
                topic_epoch_decision={"action": "reuse", "label": "ambient", "confidence": 0.8},
            )
            return {"status": "scheduled", "job_id": "job-detached", "spawned": False}

        with patch(
            "aippocampus_runtime.recall.prompt_recall_ambient.schedule_warm_ambient_recall",
            fake_schedule,
        ):
            first = hook.assess_prompt(
                "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-next",
                ambient_cache_path=cache_path,
                warm_background=True,
                search_budget=0,
            )
            second = hook.assess_prompt(
                "继续这个 ambient recall 方向",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-next",
                ambient_cache_path=cache_path,
                warm_background=True,
                search_budget=0,
            )

        self.assertEqual(first["ambient_recall"]["warm_background"]["status"], "scheduled")
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(second["ambient_recall"]["cache_status"]["status"], "hit")
        self.assertEqual(second["ambient_recall"]["cards"][0]["card_id"], "detached-card")
        self.assertEqual(second["ambient_recall"]["cards"][0]["provenance_class"], "cached_warm_card")
        self.assertEqual(second["ambient_recall"]["cards"][0]["cached_origin"], "unknown")
        self.assertNotIn("warm_background", second["ambient_recall"])

    def test_prompt_hook_debug_log_summarizes_ambient_cache_without_raw_prompt(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.7,
            "confidence": "medium",
            "query_terms": ["ambient"],
            "concept_expansions": [],
            "cognitive_map": [],
            "candidates": [],
            "working_memory": [],
            "semantic_gate": None,
            "evidence": [],
            "elapsed_ms": 12.0,
            "ambient_recall": {
                "mode": "active_gentle_nudge",
                "confidence": "medium",
                "cards": [
                    {
                        "card_id": "card-a",
                        "theme": "ambient",
                        "visibility": "active_gentle_nudge",
                        "support_level": "candidate",
                        "provenance_class": "cached_warm_card",
                        "source_validation": {"status": "supported"},
                    }
                ],
                "cache_status": {
                    "status": "hit",
                    "topic_epoch": "epoch-debug",
                    "card_count": 1,
                },
                "warm_background": {"status": "queued", "spawned": False},
            },
        }
        log_path = self.root / "debug.jsonl"

        hook.write_debug_log(
            result,
            hook_input={"prompt": "DO NOT LOG THIS PROMPT", "session_id": "thread-a"},
            log_path=log_path,
        )
        event = json.loads(log_path.read_text(encoding="utf-8"))
        raw = log_path.read_text(encoding="utf-8")

        self.assertNotIn("DO NOT LOG THIS PROMPT", raw)
        self.assertEqual(event["ambient_recall"]["cache"]["status"], "hit")
        self.assertEqual(event["ambient_recall"]["warm_background"]["status"], "queued")
        self.assertEqual(event["ambient_recall"]["source_validation_statuses"]["supported"], 1)
        self.assertEqual(event["ambient_recall"]["provenance_counts"]["cached_warm_card"], 1)
        self.assertEqual(event["ambient_recall"]["support_level_counts"]["candidate"], 1)


if __name__ == "__main__":
    unittest.main()
