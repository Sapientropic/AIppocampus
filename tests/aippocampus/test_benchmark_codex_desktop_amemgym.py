from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_codex_desktop_amemgym as benchmark  # noqa: E402


class CodexDesktopAMemGymStyleBenchmarkTests(unittest.TestCase):
    def test_report_defines_three_desktop_arms_without_base_agent_adapter(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], benchmark.KIND)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "contract_preview_live_desktop_not_run")
        self.assertEqual(
            payload["arms"],
            [
                "codex_native_no_aippocampus",
                "aippocampus_clean_source_no_semantic_sidecar",
                "aippocampus_semantic_sidecar",
            ],
        )
        self.assertEqual(payload["config"]["model_id"], "openai/gpt-4.1-mini")
        self.assertEqual(payload["config"]["target_temperature"], 0.0)
        self.assertEqual(
            payload["config"]["answer_choice_style"],
            "personalized_natural_language_recommendation",
        )
        self.assertFalse(payload["config"]["uses_official_amemgym_base_agent"])
        self.assertFalse(payload["desktop_live_protocol"]["amemgym_official_base_agent_adapter"])
        self.assertEqual(payload["claim_boundary"]["score_layer"], "contract_preview_only")
        self.assertEqual(payload["claim_boundary"]["temperature_comparability"], "not_measured")

    def test_metrics_compare_native_no_sidecar_and_semantic_sidecar_against_random_and_oracle(self) -> None:
        payload = benchmark.run_benchmark()
        metrics = payload["metrics"]
        by_arm = metrics["by_arm"]

        self.assertEqual(metrics["case_count"], 6)
        self.assertEqual(metrics["random_choice_baseline_accuracy"], 0.25)
        self.assertEqual(metrics["oracle_upper_bound_accuracy"], 1.0)
        self.assertGreater(
            by_arm["aippocampus_clean_source_no_semantic_sidecar"]["accuracy"],
            by_arm["codex_native_no_aippocampus"]["accuracy"],
        )
        self.assertGreater(
            by_arm["aippocampus_semantic_sidecar"]["accuracy"],
            by_arm["aippocampus_clean_source_no_semantic_sidecar"]["accuracy"],
        )
        self.assertEqual(by_arm["aippocampus_semantic_sidecar"]["accuracy"], 1.0)
        self.assertEqual(by_arm["aippocampus_semantic_sidecar"]["normalized_memory_score"], 1.0)
        self.assertGreater(metrics["deltas"]["semantic_sidecar_lift_over_no_sidecar"], 0.0)

    def test_semantic_sidecar_improves_bridge_cases_and_negative_controls(self) -> None:
        payload = benchmark.run_benchmark()
        by_arm = payload["metrics"]["by_arm"]

        self.assertLess(
            by_arm["aippocampus_clean_source_no_semantic_sidecar"]["semantic_bridge_case_accuracy"],
            by_arm["aippocampus_semantic_sidecar"]["semantic_bridge_case_accuracy"],
        )
        self.assertLess(
            by_arm["aippocampus_clean_source_no_semantic_sidecar"]["negative_control_accuracy"],
            by_arm["aippocampus_semantic_sidecar"]["negative_control_accuracy"],
        )
        self.assertIn(
            "Semantic sidecar output is navigation until clean source is reopened; it is not source truth.",
            payload["interpretation_notes"],
        )

    def test_fixture_cases_use_natural_advice_choices_not_raw_state_recall(self) -> None:
        cases = benchmark.fixture_cases()
        forbidden_question_kinds = {
            "exact_current_state",
            "semantic_current_state",
            "host_summary_supported",
        }

        self.assertTrue(cases)
        for case in cases:
            self.assertEqual(
                case.answer_choice_style,
                benchmark.REQUIRED_ANSWER_CHOICE_STYLE,
            )
            self.assertEqual(case.state_exposure_style, benchmark.REQUIRED_SETUP_EXPOSURE_STYLE)
            self.assertEqual(case.measurement_topology, benchmark.REQUIRED_MEASUREMENT_TOPOLOGY)
            self.assertNotIn(case.question_kind, forbidden_question_kinds)
            self.assertNotIn("route-code", case.case_id)

        payload = benchmark.run_benchmark()
        for row in payload["rows"]:
            self.assertEqual(row["answer_choice_style"], benchmark.REQUIRED_ANSWER_CHOICE_STYLE)
            self.assertEqual(row["state_exposure_style"], benchmark.REQUIRED_SETUP_EXPOSURE_STYLE)
            self.assertEqual(row["measurement_topology"], benchmark.REQUIRED_MEASUREMENT_TOPOLOGY)
            self.assertIn("evidence_path", row)
            self.assertNotIn("route", row)

    def test_live_environment_gate_rejects_dirty_or_skill_polluted_desktop_runs(self) -> None:
        dirty_env = {
            "model_id": "openai/gpt-4.1-mini",
            "workspace_dirty": True,
            "isolated_codex_home": False,
            "loaded_skill_names": ["aippocampus", "other-skill"],
            "loaded_plugin_names": ["Browser"],
            "loaded_skill_names_verified_by": "manual_claim",
            "skills_list_force_reloaded": False,
            "skill_catalog_errors": [{"path": "bad-skill/SKILL.md", "message": "invalid"}],
            "aippocampus_enabled": True,
            "semantic_sidecar_enabled": True,
        }

        validation = benchmark.validate_desktop_environment(
            "aippocampus_semantic_sidecar",
            dirty_env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("workspace_not_confirmed_clean", validation["blockers"])
        self.assertIn("codex_home_not_isolated", validation["blockers"])
        self.assertIn("unexpected_plugins_loaded", validation["blockers"])
        self.assertIn("loaded_skill_names_not_host_verified", validation["blockers"])
        self.assertIn("skills_list_not_force_reloaded", validation["blockers"])
        self.assertIn("skill_catalog_errors_present", validation["blockers"])
        self.assertIn("aippocampus_arm_loaded_unexpected_skills", validation["blockers"])

    def test_live_environment_gate_rejects_scoring_turn_state_pollution(self) -> None:
        env = self._valid_native_environment()
        env["scoring_state_policy"] = "single_thread_append_answers"
        env["scored_turn_writes_discarded"] = False
        env["scoring_from_same_post_compaction_checkpoint"] = False

        validation = benchmark.validate_desktop_environment(
            "codex_native_no_aippocampus",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("scored_turn_state_isolation_missing", validation["blockers"])
        self.assertIn("scored_turn_writes_not_discarded", validation["blockers"])
        self.assertIn("scoring_not_restarted_from_same_checkpoint", validation["blockers"])

    def test_live_environment_gate_rejects_explicit_state_setup_or_raw_answer_options(self) -> None:
        env = self._valid_native_environment()
        env["setup_exposure_style"] = "explicit_state_bullets"
        env["explicit_state_bullets_present"] = True
        env["raw_state_labels_exposed"] = True
        env["answer_choice_style"] = "raw_state_key_value"
        env["raw_state_answer_options_present"] = True

        validation = benchmark.validate_desktop_environment(
            "codex_native_no_aippocampus",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("setup_not_implicit_natural_session", validation["blockers"])
        self.assertIn("explicit_state_update_bullets_present", validation["blockers"])
        self.assertIn("raw_state_labels_exposed", validation["blockers"])
        self.assertIn("answer_choices_not_personalized_natural_language", validation["blockers"])
        self.assertIn("raw_state_answer_options_present", validation["blockers"])

    def test_live_environment_gate_rejects_same_thread_or_visible_setup_context(self) -> None:
        env = self._valid_native_environment()
        env["measurement_topology"] = "same_thread_full_context"
        env["scoring_thread_id_sha1"] = env["setup_thread_id_sha1"]
        env["setup_context_visible_to_scoring_thread"] = True
        env["native_context_window_contains_setup_history"] = True

        validation = benchmark.validate_desktop_environment(
            "codex_native_no_aippocampus",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("measurement_not_cross_thread_cold_start", validation["blockers"])
        self.assertIn("setup_and_scoring_thread_not_separate", validation["blockers"])
        self.assertIn("setup_context_visible_to_scoring_thread", validation["blockers"])
        self.assertIn("native_context_window_contains_setup_history", validation["blockers"])

    def test_live_environment_gate_requires_temperature_zero_or_variance_report(self) -> None:
        env = self._valid_native_environment()
        env["temperature_control"] = "unknown"
        env["temperature"] = None
        env["temperature_verified_by"] = None

        validation = benchmark.validate_desktop_environment(
            "codex_native_no_aippocampus",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("temperature_control_unverified", validation["blockers"])

        variance_env = self._valid_native_environment()
        variance_env.update(
            {
                "temperature_control": benchmark.TEMPERATURE_CONTROL_VARIANCE_REPORTED,
                "temperature": None,
                "temperature_verified_by": None,
                "temperature_configurable": False,
                "temperature_variance_run_count": benchmark.MIN_TEMPERATURE_VARIANCE_RUNS,
                "temperature_variance_reported": True,
            }
        )
        variance_validation = benchmark.validate_desktop_environment(
            "codex_native_no_aippocampus",
            variance_env,
        )

        self.assertTrue(variance_validation["claimable"], variance_validation)
        self.assertFalse(variance_validation["temperature_same_param_as_official_native"])

    def test_live_environment_gate_rejects_manual_loaded_skill_claims(self) -> None:
        env = {
            "model_id": "openai/gpt-4.1-mini",
            "workspace_dirty": False,
            "isolated_codex_home": True,
            "loaded_skill_names": [],
            "loaded_plugin_names": [],
            "aippocampus_enabled": False,
            "semantic_sidecar_enabled": False,
            "aippocampus_hooks_installed": False,
            "observed_hook_events": [],
            "trusted_hook_events": [],
            "skill_catalog_errors": [],
        }

        validation = benchmark.validate_desktop_environment(
            "codex_native_no_aippocampus",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("loaded_skill_names_not_host_verified", validation["blockers"])
        self.assertIn("skills_list_not_force_reloaded", validation["blockers"])

    def test_live_environment_gate_rejects_untrusted_or_unobserved_aippocampus_hooks(self) -> None:
        env = {
            "model_id": "openai/gpt-4.1-mini",
            "workspace_dirty": False,
            "isolated_codex_home": True,
            "loaded_skill_names": ["aippocampus"],
            "loaded_plugin_names": [],
            "loaded_skill_names_verified_by": "codex_app_server_skills_list",
            "skills_list_force_reloaded": True,
            "skill_catalog_errors": [],
            "aippocampus_enabled": True,
            "semantic_sidecar_enabled": True,
            "aippocampus_hooks_installed": True,
            "hook_trust_status_by_event": {
                "sessionStart": "trusted",
                "userPromptSubmit": "untrusted",
                "stop": "trusted",
            },
            "observed_hook_events": ["sessionStart"],
            "cache_preparation_completed": True,
            "measured_after_cache_warmup": True,
            "prepared_cache_surfaces": [
                "clean_source",
                "source_index",
                "ambient_route_cache",
                "semantic_sidecar",
            ],
            "hook_completed_status_by_event": {"userPromptSubmit": "completed"},
            "hook_duration_ms_by_event": {"userPromptSubmit": 300},
            "foreground_hook_timeout_observed": False,
        }

        validation = benchmark.validate_desktop_environment(
            "aippocampus_semantic_sidecar",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("aippocampus_hooks_not_trusted", validation["blockers"])
        self.assertIn("aippocampus_hook_notifications_missing", validation["blockers"])

    def test_live_environment_gate_rejects_missing_precache_or_slow_warmup(self) -> None:
        env = {
            "model_id": "openai/gpt-4.1-mini",
            "workspace_dirty": False,
            "isolated_codex_home": True,
            "loaded_skill_names": ["aippocampus"],
            "loaded_plugin_names": [],
            "loaded_skill_names_verified_by": "codex_app_server_skills_list",
            "skills_list_force_reloaded": True,
            "skill_catalog_errors": [],
            "aippocampus_enabled": True,
            "semantic_sidecar_enabled": True,
            "aippocampus_hooks_installed": True,
            "aippocampus_hooks_trusted": True,
            "observed_hook_events": ["sessionStart", "userPromptSubmit", "stop"],
            "trusted_hook_events": ["sessionStart", "userPromptSubmit", "stop"],
            "cache_preparation_completed": False,
            "measured_after_cache_warmup": False,
            "prepared_cache_surfaces": ["clean_source", "source_index"],
            "hook_completed_status_by_event": {"userPromptSubmit": "completed"},
            "hook_duration_ms_by_event": {"userPromptSubmit": 5000},
            "foreground_hook_timeout_observed": True,
        }

        validation = benchmark.validate_desktop_environment(
            "aippocampus_semantic_sidecar",
            env,
        )

        self.assertFalse(validation["claimable"])
        self.assertIn("cache_preparation_not_completed", validation["blockers"])
        self.assertIn("cache_preparation_missing_required_surfaces", validation["blockers"])
        self.assertIn("measured_before_cache_warmup", validation["blockers"])
        self.assertIn("user_prompt_submit_hook_exceeded_foreground_budget", validation["blockers"])
        self.assertIn("foreground_hook_timeout_observed", validation["blockers"])

    def test_live_environment_gate_allows_only_expected_skills_per_arm(self) -> None:
        native = self._valid_native_environment()
        trusted_events = ["sessionStart", "userPromptSubmit", "stop"]
        no_sidecar_surfaces = ["clean_source", "source_index", "ambient_route_cache"]
        no_sidecar = {
            **native,
            "loaded_skill_names": ["aippocampus"],
            "aippocampus_enabled": True,
            "semantic_sidecar_enabled": False,
            "aippocampus_hooks_installed": True,
            "aippocampus_hooks_trusted": True,
            "observed_hook_events": trusted_events,
            "trusted_hook_events": trusted_events,
            "cache_preparation_completed": True,
            "measured_after_cache_warmup": True,
            "prepared_cache_surfaces": no_sidecar_surfaces,
            "hook_completed_status_by_event": {"userPromptSubmit": "completed"},
            "hook_duration_ms_by_event": {"userPromptSubmit": 300},
            "foreground_hook_timeout_observed": False,
        }
        semantic = {
            **no_sidecar,
            "semantic_sidecar_enabled": True,
            "prepared_cache_surfaces": [*no_sidecar_surfaces, "semantic_sidecar"],
        }

        environments = {
            "codex_native_no_aippocampus": native,
            "aippocampus_clean_source_no_semantic_sidecar": no_sidecar,
            "aippocampus_semantic_sidecar": semantic,
        }
        payload = benchmark.run_benchmark(live_environment_by_arm=environments)

        self.assertEqual(payload["status"], "live_desktop_evidence_ready")
        self.assertEqual(payload["claim_boundary"]["score_layer"], "live_desktop_evidence")
        self.assertEqual(
            payload["claim_boundary"]["scored_turn_state_isolation"],
            "claimable",
        )
        self.assertEqual(
            payload["claim_boundary"]["temperature_comparability"],
            "official_native_temperature_matched",
        )
        self.assertTrue(payload["desktop_live_environment"]["all_arms_claimable"])
        self.assertEqual(
            payload["desktop_live_environment"]["by_arm"]["codex_native_no_aippocampus"][
                "observed_loaded_skill_names"
            ],
            [],
        )
        self.assertEqual(
            payload["desktop_live_environment"]["by_arm"]["aippocampus_semantic_sidecar"][
                "observed_loaded_skill_names"
            ],
            ["aippocampus"],
        )
        self.assertEqual(
            payload["desktop_live_environment"]["by_arm"]["aippocampus_semantic_sidecar"][
                "observed_hook_events"
            ],
            sorted(trusted_events),
        )
        self.assertEqual(
            payload["desktop_live_environment"]["by_arm"]["aippocampus_semantic_sidecar"][
                "prepared_cache_surfaces"
            ],
            sorted([*no_sidecar_surfaces, "semantic_sidecar"]),
        )

    def test_live_environment_with_temperature_variance_is_not_reported_as_same_param(self) -> None:
        native = self._valid_native_environment(
            temperature_control=benchmark.TEMPERATURE_CONTROL_VARIANCE_REPORTED,
        )
        no_sidecar = {
            **native,
            "loaded_skill_names": ["aippocampus"],
            "aippocampus_enabled": True,
            "semantic_sidecar_enabled": False,
            "aippocampus_hooks_installed": True,
            "aippocampus_hooks_trusted": True,
            "observed_hook_events": ["sessionStart", "userPromptSubmit", "stop"],
            "trusted_hook_events": ["sessionStart", "userPromptSubmit", "stop"],
            "cache_preparation_completed": True,
            "measured_after_cache_warmup": True,
            "prepared_cache_surfaces": ["clean_source", "source_index", "ambient_route_cache"],
            "hook_completed_status_by_event": {"userPromptSubmit": "completed"},
            "hook_duration_ms_by_event": {"userPromptSubmit": 300},
            "foreground_hook_timeout_observed": False,
        }
        semantic = {
            **no_sidecar,
            "semantic_sidecar_enabled": True,
            "prepared_cache_surfaces": [
                "clean_source",
                "source_index",
                "ambient_route_cache",
                "semantic_sidecar",
            ],
        }

        payload = benchmark.run_benchmark(
            live_environment_by_arm={
                "codex_native_no_aippocampus": native,
                "aippocampus_clean_source_no_semantic_sidecar": no_sidecar,
                "aippocampus_semantic_sidecar": semantic,
            }
        )

        self.assertEqual(payload["status"], "live_desktop_evidence_ready")
        self.assertEqual(
            payload["claim_boundary"]["temperature_comparability"],
            "variance_bounded_not_official_same_param",
        )
        self.assertFalse(
            payload["desktop_live_environment"]["by_arm"]["codex_native_no_aippocampus"][
                "temperature_same_param_as_official_native"
            ]
        )

    def test_public_report_does_not_emit_raw_prompts_paths_or_credentials(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["privacy_boundary"]["raw_case_prompts_in_report"])
        self.assertFalse(payload["privacy_boundary"]["raw_model_outputs_in_report"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_in_report"])
        self.assertFalse(payload["privacy_boundary"]["provider_auth_material_in_report"])
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("api_key", encoded.lower())
        self.assertNotIn("Bearer ", encoded)
        for row in payload["rows"]:
            self.assertIn("case_id_sha1", row)
            self.assertNotIn("case_id", row)
            self.assertNotIn("prompt", row)
            self.assertNotIn("source_text", row)

    def test_cli_emits_json_payload(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_codex_desktop_amemgym.py"),
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["kind"], benchmark.KIND)
        self.assertEqual(payload["config"]["model_id"], "openai/gpt-4.1-mini")

    @staticmethod
    def _valid_native_environment(
        *,
        temperature_control: str = benchmark.TEMPERATURE_CONTROL_CONFIGURED_ZERO,
    ) -> dict[str, object]:
        env: dict[str, object] = {
            "model_id": "openai/gpt-4.1-mini",
            "answer_choice_style": benchmark.REQUIRED_ANSWER_CHOICE_STYLE,
            "raw_state_answer_options_present": False,
            "setup_exposure_style": benchmark.REQUIRED_SETUP_EXPOSURE_STYLE,
            "explicit_state_bullets_present": False,
            "raw_state_labels_exposed": False,
            "measurement_topology": benchmark.REQUIRED_MEASUREMENT_TOPOLOGY,
            "setup_thread_id_sha1": "setup-thread-hash",
            "scoring_thread_id_sha1": "scoring-thread-hash",
            "setup_context_visible_to_scoring_thread": False,
            "native_context_window_contains_setup_history": False,
            "scoring_state_policy": "restart_from_post_compaction_checkpoint",
            "scored_turn_writes_discarded": True,
            "scoring_from_same_post_compaction_checkpoint": True,
            "scoring_checkpoint_id_sha1": "post-compaction-checkpoint-hash",
            "workspace_dirty": False,
            "isolated_codex_home": True,
            "loaded_skill_names": [],
            "loaded_plugin_names": [],
            "loaded_skill_names_verified_by": "codex_app_server_skills_list",
            "skills_list_force_reloaded": True,
            "skill_catalog_errors": [],
            "aippocampus_enabled": False,
            "semantic_sidecar_enabled": False,
            "aippocampus_hooks_installed": False,
            "observed_hook_events": [],
            "trusted_hook_events": [],
        }
        if temperature_control == benchmark.TEMPERATURE_CONTROL_VARIANCE_REPORTED:
            env.update(
                {
                    "temperature_control": benchmark.TEMPERATURE_CONTROL_VARIANCE_REPORTED,
                    "temperature": None,
                    "temperature_verified_by": None,
                    "temperature_configurable": False,
                    "temperature_variance_run_count": benchmark.MIN_TEMPERATURE_VARIANCE_RUNS,
                    "temperature_variance_reported": True,
                }
            )
        else:
            env.update(
                {
                    "temperature_control": benchmark.TEMPERATURE_CONTROL_CONFIGURED_ZERO,
                    "temperature": 0.0,
                    "temperature_verified_by": "codex_app_server_request_log",
                    "temperature_configurable": True,
                    "temperature_variance_run_count": 1,
                    "temperature_variance_reported": False,
                }
            )
        return env


if __name__ == "__main__":
    unittest.main()
