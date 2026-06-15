from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import (
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    AmbientRecallHookCase,
    contextlib,
    fake_test_windows_path,
    hook,
    io,
    json,
    patch,
    subprocess,
    sys,
)


class PromptHookTelemetryAuditTests(AmbientRecallHookCase):
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

    def test_last_prompt_hook_status_projects_skip_reason_and_next_action(self) -> None:
        status_path = self.root / "prompt-hook-skip-status.json"
        hook.write_prompt_hook_audit_status(
            {
                "decision": "skip",
                "score": 0.0,
                "confidence": "low",
                "candidates": [],
                "working_memory": [],
                "evidence": [],
                "cognitive_map": [],
                "ambient_recall": {
                    "cache_status": {"status": "miss", "card_count": 0},
                },
                "elapsed_ms": 42.0,
            },
            status_path=status_path,
        )

        status = hook.prompt_hook_audit_status(status_path=status_path)
        latest = status["last_prompt_hook"]

        self.assertEqual(latest["decision"], "skip")
        self.assertEqual(latest["memory_surface"], "no_memory")
        self.assertEqual(latest["skip_reason"], "cache_miss_no_relevant_route")
        self.assertEqual(latest["next_diagnostic"], "aippocampus why-not-recall <cue> --json")
        self.assertEqual(latest["next_repair"], "aippocampus health")

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
