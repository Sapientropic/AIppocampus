from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.aippocampus.path_assertions import (
    assert_path_flag_points_to,
    assert_path_list_contains,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import amemgym_official_local_provider as local_provider  # noqa: E402
import benchmark_amemgym_official as benchmark  # noqa: E402

RAW_QUERY = "RAW AMEMGYM QUERY MUST NOT LEAK"
LOCAL_PATH_SENTINEL = "LOCAL_PRIVATE_PATH_SENTINEL\\amemgym-official"
AMEMGYM_AUTH_CONFIG_FIELD = "_".join(("api", "key"))
FAKE_PROVIDER_VALUE = "".join(("s", "k", "-", "FAKE_TEST_OPENROUTER_123456"))


class AMemGymOfficialBridgeTests(unittest.TestCase):
    def test_missing_outputs_emit_plan_without_claiming_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"

            payload = benchmark.build_official_bridge_report(
                upstream_root=upstream,
                env_data_path=env_data,
                agent_config_path=agent_config,
                overall_output_dir=root / "missing-overall",
                upperbound_output_dir=root / "missing-upperbound",
                random_output_file=root / "missing-random.json",
            )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "runner_plan_ready_missing_outputs")
        self.assertEqual(payload["claim_boundary"]["official_amemgym_score"], "not_claimed")
        self.assertIn("amemgym.eval.overall", payload["runner_plan"]["entrypoints"])
        self.assertIn("amemgym.eval.upperbound", payload["runner_plan"]["entrypoints"])
        self.assertIn("amemgym.eval.random", payload["runner_plan"]["entrypoints"])
        self.assertIn("official_overall_missing", payload["cannot_claim"])
        self.assertNotIn("official_overall", payload["metrics"])

    def test_missing_env_data_reports_blocker_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            missing_env_data = root / "missing-data.json"
            agent_config = upstream / "configs" / "agent" / "native.json"

            payload = benchmark.build_official_bridge_report(
                upstream_root=upstream,
                env_data_path=missing_env_data,
                agent_config_path=agent_config,
                overall_output_dir=root / "missing-overall",
                upperbound_output_dir=root / "missing-upperbound",
                random_output_file=root / "missing-random.json",
            )

        self.assertEqual(payload["status"], "runner_plan_ready_missing_outputs")
        self.assertEqual(payload["score_summary_error_type"], "FileNotFoundError")
        self.assertEqual(payload["fixed_arm_execution"]["dataset"]["status"], "env_data_unavailable")
        self.assertIn("amemgym_env_data_unavailable", payload["cannot_claim"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(root), dumped)

    def test_score_summary_computes_official_compatible_memory_score_without_raw_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "outputs" / LOCAL_PATH_SENTINEL
            self._write_official_outputs(output_root)

            payload = benchmark.build_official_bridge_report(
                upstream_root=upstream,
                env_data_path=env_data,
                agent_config_path=agent_config,
                overall_output_dir=output_root / "overall",
                upperbound_output_dir=output_root / "upperbound",
                random_output_file=output_root / "random_metrics.json",
            )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "official_score_summary")
        self.assertAlmostEqual(payload["metrics"]["official_overall"], 0.5)
        self.assertAlmostEqual(payload["metrics"]["official_upperbound"], 1.0)
        self.assertAlmostEqual(payload["metrics"]["official_random"], 0.25)
        self.assertAlmostEqual(payload["metrics"]["official_normalized_memory_score"], 1 / 3)
        self.assertEqual(payload["metrics"]["score_sample_count"], 8)
        self.assertEqual(payload["metrics"]["below_random_sample_count"], 0)
        self.assertEqual(payload["metrics"]["negative_memory_sample_count"], 0)
        self.assertFalse(payload["score_interpretation"]["normalized_memory_score_negative"])
        self.assertEqual(payload["metrics"]["memory_score_denominator_zero_count"], 0)
        self.assertEqual(payload["claim_boundary"]["official_amemgym_score"], "official_output_summary")
        self.assertEqual(payload["claim_boundary"]["source_backed_overlay"], "separate_not_merged")

        dumped = json.dumps(payload, ensure_ascii=False)
        for forbidden in (RAW_QUERY, LOCAL_PATH_SENTINEL, str(output_root), FAKE_PROVIDER_VALUE):
            self.assertNotIn(forbidden, dumped)
        self.assertNotIn("api_key", dumped)

    def test_score_summary_marks_negative_memory_when_overall_is_below_random(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "negative"
            self._write_official_outputs(output_root)
            for overall_path in (output_root / "overall").rglob("overall_metrics.json"):
                overall_path.write_text(json.dumps({"accuracy": [[0.0, 0.0], [0.0, 0.0]]}), encoding="utf-8")

            payload = benchmark.build_official_bridge_report(
                upstream_root=upstream,
                env_data_path=env_data,
                agent_config_path=agent_config,
                overall_output_dir=output_root / "overall",
                upperbound_output_dir=output_root / "upperbound",
                random_output_file=output_root / "random_metrics.json",
            )

        self.assertAlmostEqual(payload["metrics"]["official_normalized_memory_score"], -1 / 3)
        self.assertEqual(payload["metrics"]["below_random_sample_count"], 8)
        self.assertEqual(payload["metrics"]["negative_memory_sample_count"], 8)
        self.assertTrue(payload["score_interpretation"]["normalized_memory_score_negative"])
        self.assertTrue(
            any(note.startswith("negative_normalized_memory") for note in payload["score_interpretation"]["notes"])
        )

    def test_partial_official_outputs_report_progress_without_claiming_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "partial"
            item_dir = output_root / "overall" / "native-gpt-4.1-mini" / "user-a"
            item_dir.mkdir(parents=True)
            (item_dir / "overall_metrics.json").write_text(
                json.dumps({"accuracy": [[0.5, 0.5]]}),
                encoding="utf-8",
            )
            (item_dir / "overall_results.json").write_text(
                json.dumps([[{"scores": {"accuracy": 0.5}}, None]]),
                encoding="utf-8",
            )
            upper_dir = output_root / "upperbound" / "openai" / "gpt-4.1-mini"
            upper_dir.mkdir(parents=True)
            (upper_dir / "utilization_results.json").write_text(
                json.dumps([[[{"scores": {"accuracy": 1.0}}, None]]]),
                encoding="utf-8",
            )

            payload = benchmark.build_official_bridge_report(
                upstream_root=upstream,
                env_data_path=env_data,
                agent_config_path=agent_config,
                overall_output_dir=output_root / "overall",
                upperbound_output_dir=output_root / "upperbound",
                random_output_file=output_root / "missing-random.json",
            )

        self.assertEqual(payload["status"], "partial_official_outputs")
        self.assertEqual(payload["official_outputs"]["overall"]["status"], "partial")
        self.assertEqual(payload["official_outputs"]["upperbound"]["status"], "partial")
        self.assertEqual(payload["official_outputs"]["overall"]["progress"]["completed_item_count"], 1)
        self.assertEqual(payload["official_outputs"]["overall"]["progress"]["expected_item_count"], 2)
        self.assertEqual(payload["official_outputs"]["overall"]["progress"]["completed_score_leaf_count"], 1)
        self.assertEqual(payload["official_outputs"]["upperbound"]["progress"]["completed_choice_eval_count"], 1)
        self.assertEqual(payload["claim_boundary"]["official_amemgym_score"], "not_claimed")
        self.assertIn("official_normalized_memory_score_missing", payload["cannot_claim"])
        self.assertIn("full_local_official_runner_execution", payload["cannot_claim"])

    def test_bounded_subset_report_writes_public_safe_checkpoint_without_score_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "outputs" / LOCAL_PATH_SENTINEL
            checkpoint_path = root / "private-checkpoints" / "amemgym-state.json"
            self._write_official_outputs(output_root)
            (output_root / "upperbound" / "openai" / "gpt-4.1-mini" / "utilization_metrics.json").write_text(
                json.dumps({"accuracy": [[[1.0, 1.0], [1.0, 1.0]]]}),
                encoding="utf-8",
            )
            (output_root / "random_metrics.json").write_text(
                json.dumps({"accuracy": [[[0.25, 0.25], [0.25, 0.25]]]}),
                encoding="utf-8",
            )

            with mock.patch.object(benchmark, "DEFAULT_OFFICIAL_OUTPUT_ROOT", root / "generated"):
                payload = benchmark.build_official_bridge_report(
                    upstream_root=upstream,
                    env_data_path=env_data,
                    agent_config_path=agent_config,
                    overall_output_dir=output_root / "overall",
                    upperbound_output_dir=output_root / "upperbound",
                    random_output_file=output_root / "random_metrics.json",
                    max_cases=1,
                    checkpoint_path=checkpoint_path,
                )
                checkpoint_exists = checkpoint_path.exists()
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "bounded_subset_score_summary")
        self.assertEqual(
            payload["claim_boundary"]["official_amemgym_score"],
            "bounded_subset_summary_not_full_v1_base",
        )
        self.assertEqual(payload["fixed_arm_execution"]["status"], "complete_bounded_subset_outputs_not_full_v1_base")
        self.assertEqual(payload["fixed_arm_execution"]["dataset"]["full_item_count"], 2)
        self.assertEqual(payload["fixed_arm_execution"]["dataset"]["run_item_count"], 1)
        self.assertTrue(payload["fixed_arm_execution"]["dataset"]["bounded_subset"])
        self.assertIn("progressive_subset_debug_only", payload["fixed_arm_execution"]["dataset"]["boundary"])
        self.assertEqual(
            payload["fixed_arm_execution"]["cost_latency"]["provider_cost_status"],
            "unavailable",
        )
        self.assertEqual(
            payload["fixed_arm_execution"]["cost_latency"]["unavailable_reason"],
            "provider_usage_metadata_not_extracted_from_official_outputs",
        )
        self.assertEqual(payload["fixed_arm_execution"]["checkpoint"]["status"], "written")
        self.assertTrue(checkpoint_exists)
        self.assertEqual(checkpoint["kind"], "aippocampus_amemgym_official_runner_checkpoint")
        self.assertEqual(checkpoint["phase_states"]["overall"]["status"], "complete")
        self.assertEqual(checkpoint["phase_states"]["overall"]["completed_item_count"], 1)
        self.assertEqual(checkpoint["phase_states"]["random"]["completed_file_count"], 1)
        self.assertEqual(checkpoint["cost_latency"]["provider_cost_status"], "unavailable")
        dumped = json.dumps({"payload": payload, "checkpoint": checkpoint}, ensure_ascii=False)
        for forbidden in (RAW_QUERY, LOCAL_PATH_SENTINEL, str(output_root), str(checkpoint_path), FAKE_PROVIDER_VALUE):
            self.assertNotIn(forbidden, dumped)
        self.assertNotIn("api_key", dumped)
        self.assertIn("full_public_v1_base_fixed_arm_score_from_bounded_subset", payload["cannot_claim"])

    def test_resume_skips_completed_surfaces_and_reports_missing_phase_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "resume"
            self._write_official_outputs(output_root)
            shutil.rmtree(output_root / "upperbound")

            def fake_run(surface: str, **_kwargs: object) -> dict[str, object]:
                return {
                    "surface": surface,
                    "returncode": 0,
                    "ok": True,
                    "stdout_sha1": None,
                    "stderr_sha1": None,
                    "stdout_line_count": 0,
                    "stderr_line_count": 0,
                    "provider": {"provider": "default"},
                    "elapsed_ms": 12.5,
                }

            with mock.patch.object(benchmark, "run_official_surface", side_effect=fake_run) as run_mock:
                payload = benchmark.build_official_bridge_report(
                    upstream_root=upstream,
                    env_data_path=env_data,
                    agent_config_path=agent_config,
                    overall_output_dir=output_root / "overall",
                    upperbound_output_dir=output_root / "upperbound",
                    random_output_file=output_root / "random_metrics.json",
                    run_surfaces=("overall", "upperbound", "random"),
                    resume=True,
                )

        self.assertEqual([call.args[0] for call in run_mock.call_args_list], ["upperbound"])
        self.assertEqual(payload["fixed_arm_execution"]["resume"]["skipped_surfaces"], ["overall", "random"])
        self.assertEqual(payload["fixed_arm_execution"]["phase_states"]["overall"]["status"], "complete")
        self.assertEqual(payload["fixed_arm_execution"]["phase_states"]["random"]["status"], "complete")
        self.assertEqual(payload["fixed_arm_execution"]["phase_states"]["upperbound"]["status"], "missing")
        self.assertEqual(
            payload["fixed_arm_execution"]["phase_states"]["upperbound"]["incomplete_reason"],
            "official_upperbound_output_missing",
        )
        self.assertEqual(payload["fixed_arm_execution"]["phase_states"]["upperbound"]["elapsed_ms"], 12.5)
        self.assertEqual(payload["run_results"][0]["status"], "skipped_complete")
        self.assertEqual(payload["run_results"][0]["surface"], "overall")
        self.assertEqual(payload["run_results"][2]["surface"], "random")
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(RAW_QUERY, dumped)
        self.assertNotIn(str(output_root), dumped)

    def test_run_surface_uses_python_module_from_local_upstream_without_emitting_secret_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            output_file = root / "random_metrics.json"

            completed = mock.Mock(returncode=0, stdout="RAW " + RAW_QUERY, stderr="")
            with mock.patch.object(benchmark.subprocess, "run", return_value=completed) as run_mock:
                result = benchmark.run_official_surface(
                    "random",
                    upstream_root=upstream,
                    env_data_path=root / "data.json",
                    env_config_path=upstream / "configs" / "env" / "v1.base.json",
                    agent_config_path=upstream / "configs" / "agent" / "native.json",
                    overall_output_dir=root / "overall",
                    upperbound_output_dir=root / "upperbound",
                    random_output_file=output_file,
                    reset=False,
                )

        self.assertEqual(result["surface"], "random")
        self.assertEqual(result["returncode"], 0)
        self.assertNotIn(RAW_QUERY, json.dumps(result, ensure_ascii=False))
        argv = run_mock.call_args.args[0]
        self.assertIn("-m", argv)
        self.assertIn("amemgym.eval.random", argv)
        assert_path_flag_points_to(self, argv, "--env_data", root / "data.json")
        assert_path_flag_points_to(self, argv, "--output_file", output_file)
        env = run_mock.call_args.kwargs["env"]
        assert_path_list_contains(self, env["PYTHONPATH"], upstream / "src")

    def test_openrouter_provider_maps_open_router_alias_for_subprocess_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")

            completed = mock.Mock(returncode=0, stdout="", stderr="")
            with (
                mock.patch.object(benchmark.subprocess, "run", return_value=completed) as run_mock,
                mock.patch.object(
                    benchmark,
                    "external_env_value",
                    side_effect=lambda name: FAKE_PROVIDER_VALUE if name == "Open_Router" else None,
                ),
            ):
                result = benchmark.run_official_surface(
                    "random",
                    upstream_root=upstream,
                    env_data_path=root / "data.json",
                    env_config_path=upstream / "configs" / "env" / "v1.base.json",
                    agent_config_path=upstream / "configs" / "agent" / "native.json",
                    overall_output_dir=root / "overall",
                    upperbound_output_dir=root / "upperbound",
                    random_output_file=root / "random_metrics.json",
                    provider="openrouter",
                )

        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["OPENAI_API_KEY"], FAKE_PROVIDER_VALUE)
        self.assertEqual(env["OPENAI_BASE_URL"], benchmark.OPENROUTER_BASE_URL)
        self.assertEqual(result["provider"]["credential_status"], "set_redacted")
        self.assertEqual(result["provider"]["credential_alias"], "Open_Router")
        self.assertNotIn(FAKE_PROVIDER_VALUE, json.dumps(result, ensure_ascii=False))

    def test_local_scripted_provider_reports_protocol_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"

            with mock.patch.object(benchmark, "DEFAULT_PROVIDER_OVERLAY_ROOT", root / "provider-overlays"):
                payload = benchmark.build_official_bridge_report(
                    upstream_root=upstream,
                    env_data_path=env_data,
                    agent_config_path=agent_config,
                    overall_output_dir=root / "overall",
                    upperbound_output_dir=root / "upperbound",
                    random_output_file=root / "random_metrics.json",
                    provider=benchmark.LOCAL_SCRIPTED_PROVIDER,
                )

        self.assertEqual(payload["provider"]["provider"], benchmark.LOCAL_SCRIPTED_PROVIDER)
        self.assertEqual(payload["provider"]["credential_status"], "not_required")
        self.assertEqual(payload["provider"]["model"], local_provider.LOCAL_SCRIPTED_MODEL)
        self.assertEqual(payload["provider_runtime"]["status"], "ready")
        self.assertTrue(payload["provider_runtime"]["local_scripted_overlay"])
        self.assertEqual(payload["agent"]["agent_name"], "native-local-scripted")
        self.assertEqual(payload["agent"]["llm_model"], local_provider.LOCAL_SCRIPTED_MODEL)
        self.assertEqual(
            payload["runner_plan"]["environment"]["provider_mode"],
            "local scripted call_llm patch; no provider credentials or live model calls",
        )
        self.assertEqual(
            payload["claim_boundary"]["provider_score_kind"],
            "official_protocol_full_output_not_llm_quality",
        )
        self.assertIn(
            "real_llm_memory_quality_or_provider_model_score_from_local_scripted_provider",
            payload["cannot_claim"],
        )
        self.assertNotIn(FAKE_PROVIDER_VALUE, json.dumps(payload, ensure_ascii=False))

    def test_local_scripted_sitecustomize_patches_amemgym_call_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            overlay = local_provider.write_local_scripted_provider_overlay(root / "provider-overlays")
            code = (
                "import json, time\n"
                "import amemgym.utils as utils\n"
                "before = time.perf_counter()\n"
                "time.sleep(9)\n"
                "elapsed = time.perf_counter() - before\n"
                "content, usage = utils.call_llm(\n"
                "    [{'role':'user','content':'Please select the most suitable answer\\n1: A\\n2: B\\n'}],\n"
                "    {}, json=True, return_token_usage=True,\n"
                ")\n"
                "print(json.dumps({'content': content, 'usage': usage, 'elapsed_lt_one': elapsed < 1}))\n"
            )
            env = os.environ.copy()
            env.update(local_provider.local_scripted_provider_env(choice_index=2))
            env["PYTHONPATH"] = os.pathsep.join([str(overlay["pythonpath"]), str(upstream / "src")])
            completed = subprocess.run(
                [sys.executable, "-c", code],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(json.loads(payload["content"]), {"answer": 2})
        self.assertEqual(payload["usage"]["provider"], "local-scripted")
        self.assertTrue(payload["elapsed_lt_one"])

    def test_aippocampus_clean_source_arm_registers_adapter_but_only_claims_file_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "outputs"
            clean_agent_name = benchmark.agent_name_for_arm(
                benchmark.AIPPOCAMPUS_CLEAN_SOURCE_ARM,
                "gpt-4.1-mini",
            )
            self._write_official_outputs(output_root, agent_name="native-gpt-4.1-mini", overall_value=0.0)
            self._write_official_outputs(output_root, agent_name=clean_agent_name, overall_value=0.5)

            with (
                mock.patch.object(benchmark, "DEFAULT_OFFICIAL_OUTPUT_ROOT", root / "generated"),
                mock.patch.object(benchmark, "DEFAULT_ADAPTER_OVERLAY_ROOT", root / "adapter-overlays"),
            ):
                payload = benchmark.build_official_bridge_report(
                    upstream_root=upstream,
                    env_data_path=env_data,
                    agent_config_path=agent_config,
                    overall_output_dir=output_root / "overall",
                    upperbound_output_dir=output_root / "upperbound",
                    random_output_file=output_root / "random_metrics.json",
                    arm=benchmark.AIPPOCAMPUS_CLEAN_SOURCE_ARM,
                )
                generated_configs = sorted((root / "generated" / "agent-configs").glob("*.json"))
                generated_dump = generated_configs[0].read_text(encoding="utf-8")

        self.assertEqual(payload["agent"]["agent_type"], "aippocampus-clean-source")
        self.assertEqual(payload["configuration"]["expected_overall_agent_name"], clean_agent_name)
        self.assertAlmostEqual(payload["metrics"]["official_overall"], 0.5)
        self.assertTrue(payload["aippocampus_agent_adapter"]["requested"])
        self.assertEqual(payload["aippocampus_agent_adapter"]["status"], "ready")
        self.assertTrue(payload["aippocampus_agent_adapter"]["official_factory_overlay"])
        self.assertEqual(
            payload["claim_boundary"]["aippocampus_memory_layer"],
            "clean_source_only_file_retrieval_baseline",
        )
        self.assertIn("aippocampus_full_semantic_worker_capability", payload["cannot_claim"])
        protocol = payload["aippocampus_official_adapter_protocol"]
        self.assertTrue(protocol["arms"][benchmark.AIPPOCAMPUS_CLEAN_SOURCE_ARM]["not_full_aippocampus"])
        self.assertIn("benchmarks/aippocampus", payload["runner_plan"]["environment"]["pythonpath_add"])
        self.assertIn("skills/aippocampus/scripts", payload["runner_plan"]["environment"]["pythonpath_add"])

        self.assertEqual(len(generated_configs), 1)
        self.assertNotIn(FAKE_PROVIDER_VALUE, generated_dump)
        self.assertNotIn(LOCAL_PATH_SENTINEL, generated_dump)

    def test_semantic_sidecar_arm_requires_prepared_worker_state_before_full_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            env_data = root / "data.json"
            self._write_env_data(env_data)
            agent_config = upstream / "configs" / "agent" / "native.json"
            output_root = root / "outputs"
            semantic_agent_name = benchmark.agent_name_for_arm(
                benchmark.AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM,
                "gpt-4.1-mini",
            )
            self._write_official_outputs(output_root, agent_name=semantic_agent_name)
            agent_dir = output_root / "overall" / semantic_agent_name
            for item_id in ("user-a", "user-b"):
                self._write_adapter_metadata(
                    agent_dir / item_id / "agent_states" / "period_1",
                    semantic_worker_status="missing_degraded_to_clean_source",
                    working_memory="missing",
                    semantic_sidecar="missing",
                )

            with (
                mock.patch.object(benchmark, "DEFAULT_OFFICIAL_OUTPUT_ROOT", root / "generated"),
                mock.patch.object(benchmark, "DEFAULT_ADAPTER_OVERLAY_ROOT", root / "adapter-overlays"),
            ):
                payload = benchmark.build_official_bridge_report(
                    upstream_root=upstream,
                    env_data_path=env_data,
                    agent_config_path=agent_config,
                    overall_output_dir=output_root / "overall",
                    upperbound_output_dir=output_root / "upperbound",
                    random_output_file=output_root / "random_metrics.json",
                    arm=benchmark.AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM,
                )

        self.assertEqual(payload["agent"]["agent_type"], "aippocampus-semantic-sidecar")
        self.assertEqual(
            payload["claim_boundary"]["aippocampus_memory_layer"],
            "prepared_semantic_worker_required",
        )
        self.assertEqual(payload["aippocampus_agent_state"]["semantic_worker_state"], "missing_or_degraded")
        self.assertIn(
            "semantic_worker_materialization_unless_agent_state_sidecars_are_present",
            payload["cannot_claim"],
        )
        self.assertEqual(
            payload["aippocampus_official_adapter_protocol"]["arms"][benchmark.AIPPOCAMPUS_SEMANTIC_SIDECAR_ARM][
                "missing_worker_degrades_to"
            ],
            benchmark.AIPPOCAMPUS_CLEAN_SOURCE_ARM,
        )

    def test_semantic_worker_state_is_prepared_only_when_precache_surfaces_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_dir = root / "overall" / "aippocampus-semantic"
            for item_id in ("user-a", "user-b"):
                self._write_adapter_metadata(
                    agent_dir / item_id / "agent_states" / "period_1",
                    semantic_worker_status="prepared",
                    working_memory="present",
                    semantic_sidecar="present",
                )

            state = benchmark.inspect_aippocampus_agent_states(agent_dir)

        self.assertEqual(state["status"], "observed")
        self.assertEqual(state["adapter_metadata_count"], 2)
        self.assertEqual(state["semantic_worker_state"], "prepared")
        self.assertEqual(state["surface_counts"]["working_memory"]["present"], 2)
        self.assertEqual(state["surface_counts"]["semantic_sidecar"]["present"], 2)

    def test_adapter_overlay_patches_only_generated_factory_not_upstream_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = self._write_upstream_stub(root / "amemgym-upstream")
            upstream_init = upstream / "src" / "amemgym" / "assistants" / "__init__.py"
            original = upstream_init.read_text(encoding="utf-8")

            overlay = benchmark.write_aippocampus_adapter_overlay(
                upstream,
                output_root=root / "adapter-overlays",
            )
            upstream_after = upstream_init.read_text(encoding="utf-8")
            overlay_init = Path(overlay["pythonpath"]) / "amemgym" / "assistants" / "__init__.py"
            overlay_text = overlay_init.read_text(encoding="utf-8")

        self.assertEqual(overlay["status"], "ready")
        self.assertEqual(upstream_after, original)
        self.assertIn("aippocampus-clean-source", overlay_text)
        self.assertIn("aippocampus-semantic-sidecar", overlay_text)
        self.assertIn("AIppocampusOfficialAgent", overlay_text)
        self.assertNotIn("aippocampus-clean-source", original)

    @staticmethod
    def _write_upstream_stub(path: Path) -> Path:
        (path / "src" / "amemgym" / "eval").mkdir(parents=True)
        (path / "src" / "amemgym" / "assistants").mkdir(parents=True)
        (path / "src" / "amemgym" / "utils").mkdir(parents=True)
        (path / "configs" / "agent").mkdir(parents=True)
        (path / "configs" / "env").mkdir(parents=True)
        (path / "pyproject.toml").write_text(
            '[project]\nname = "amemgym"\nrequires-python = ">=3.13"\n',
            encoding="utf-8",
        )
        for name in ("overall", "upperbound", "random"):
            (path / "src" / "amemgym" / "eval" / f"{name}.py").write_text("# stub\n", encoding="utf-8")
        (path / "src" / "amemgym" / "assistants" / "__init__.py").write_text(
            "def create_agent(agent_config, output_dir, item=None):\n"
            "    if agent_config['type'] == 'native':\n"
            "        return NaiveAgent(agent_config['llm_config'])\n"
            "    raise ValueError(agent_config['type'])\n",
            encoding="utf-8",
        )
        for name, body in {
            "awi": "class InContextMemAgent: pass\n",
            "native": "class NaiveAgent:\n    def __init__(self, *_args, **_kwargs): pass\n",
            "mem0": "class Mem0Agent: pass\n",
            "evolvable": "class EvolvableInContextAgent: pass\nclass EvolvableMem0Agent: pass\n",
            "base": "class BaseAgent: pass\n",
        }.items():
            (path / "src" / "amemgym" / "assistants" / f"{name}.py").write_text(body, encoding="utf-8")
        (path / "src" / "amemgym" / "utils" / "llm_utils.py").write_text(
            "def call_llm(*_args, **_kwargs):\n"
            "    raise RuntimeError('upstream call_llm should be patched')\n",
            encoding="utf-8",
        )
        (path / "src" / "amemgym" / "utils" / "__init__.py").write_text(
            "from .llm_utils import call_llm\n",
            encoding="utf-8",
        )
        (path / "configs" / "agent" / "native.json").write_text(
            json.dumps(
                {
                    "type": "native",
                    "name": "native-gpt-4.1-mini",
                    "llm_config": {
                        "base_url": LOCAL_PATH_SENTINEL,
                        AMEMGYM_AUTH_CONFIG_FIELD: FAKE_PROVIDER_VALUE,
                        "llm_model": "gpt-4.1-mini",
                        "temperature": 0.0,
                        "max_tokens": 8192,
                    },
                }
            ),
            encoding="utf-8",
        )
        (path / "configs" / "env" / "v1.base.json").write_text(
            json.dumps(
                {
                    "llm_config_low_temp": {"llm_model": "gpt-4.1", "temperature": 0.2},
                    "llm_config_high_temp": {"llm_model": "gpt-4.1", "temperature": 1.0},
                    "seed": 42,
                }
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _write_env_data(path: Path) -> None:
        path.write_text(
            json.dumps(
                [
                    {"id": "user-a", "query": RAW_QUERY},
                    {"id": "user-b", "query": RAW_QUERY},
                ]
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_official_outputs(root: Path, *, agent_name: str = "native-gpt-4.1-mini", overall_value: float | None = None) -> None:
        overall_agent_dir = root / "overall" / agent_name
        default_matrices = {
            "user-a": [[0.25, 0.50], [0.75, 0.25]],
            "user-b": [[0.50, 0.25], [0.75, 0.75]],
        }
        matrices = (
            {item_id: [[overall_value, overall_value], [overall_value, overall_value]] for item_id in default_matrices}
            if overall_value is not None
            else default_matrices
        )
        for item_id, matrix in matrices.items():
            item_dir = overall_agent_dir / item_id
            item_dir.mkdir(parents=True, exist_ok=True)
            (item_dir / "overall_metrics.json").write_text(
                json.dumps({"accuracy": matrix}),
                encoding="utf-8",
            )
        ub_dir = root / "upperbound" / "openai" / "gpt-4.1-mini"
        ub_dir.mkdir(parents=True, exist_ok=True)
        (ub_dir / "utilization_metrics.json").write_text(
            json.dumps({"accuracy": [[[1.0, 1.0], [1.0, 1.0]], [[1.0, 1.0], [1.0, 1.0]]]}),
            encoding="utf-8",
        )
        (root / "random_metrics.json").write_text(
            json.dumps({"accuracy": [[[0.25, 0.25], [0.25, 0.25]], [[0.25, 0.25], [0.25, 0.25]]]}),
            encoding="utf-8",
        )

    @staticmethod
    def _write_adapter_metadata(
        period_dir: Path,
        *,
        semantic_worker_status: str,
        working_memory: str,
        semantic_sidecar: str,
    ) -> None:
        period_dir.mkdir(parents=True)
        (period_dir / "adapter_metadata.json").write_text(
            json.dumps(
                {
                    "kind": "aippocampus_amemgym_agent_state",
                    "artifact_status": {
                        "clean_source": "built",
                        "source_index": "built",
                        "working_memory": working_memory,
                        "semantic_sidecar": semantic_sidecar,
                        "semantic_triggers": "missing",
                        "semantic_cues": "missing",
                        "semantic_worker_status": semantic_worker_status,
                    },
                }
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
