from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_state_bench_agent_learning as benchmark  # noqa: E402

RAW_USER_TEXT = "SECRET STATEBENCH USER TEXT SHOULD NOT LEAK"
RAW_ASSISTANT_TEXT = "SECRET STATEBENCH ASSISTANT TEXT SHOULD NOT LEAK"
LOCAL_PATH_SENTINEL = "C:\\PRIVATE\\state-bench\\outputs"


class StateBenchAgentLearningTests(unittest.TestCase):
    def test_missing_checkout_reports_no_go_without_claiming_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = benchmark.build_state_bench_agent_learning_report(
                state_bench_root=Path(tmp) / "missing-state-bench",
                domain="customer_support",
            )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_state_bench_agent_learning_feasibility")
        self.assertEqual(payload["status"], "skipped_missing_state_bench_checkout")
        self.assertEqual(payload["official_submission_decision"], "no_go_missing_state_bench_checkout")
        self.assertEqual(payload["metrics"]["observed_train_trajectory_count"], 0)
        self.assertEqual(payload["comparison"]["comparison_kind"], "not_run")
        self.assertIn("official_state_bench_score", payload["cannot_claim"])
        self.assertIn("agent_learning_track_lift", payload["cannot_claim"])

    def test_public_train_fixture_generates_adapter_plan_without_raw_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_bench_root = root / "STATE-Bench"
            self._write_train_fixture(state_bench_root)
            adapter_dir = root / "agents"
            learnings_path = root / "learnings.json"

            payload = benchmark.build_state_bench_agent_learning_report(
                state_bench_root=state_bench_root,
                domain="customer_support",
                max_train_files=5,
                adapter_output_dir=adapter_dir,
                learnings_output=learnings_path,
                write_adapter=True,
                official_commit="83cb96de5429c43adfdb5cb9b6785439e937a3ca",
            )
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            adapter_exists = (adapter_dir / "aippocampus_state_bench_agent.py").exists()
            learnings_exists = learnings_path.exists()
            learning_rows = json.loads(learnings_path.read_text(encoding="utf-8"))

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "adapter_dry_run_ready")
        self.assertEqual(payload["official_submission_decision"], "no_go_adapter_only_no_official_run")
        self.assertEqual(payload["metrics"]["observed_train_trajectory_count"], 2)
        self.assertEqual(payload["metrics"]["extracted_learning_count"], 2)
        self.assertEqual(payload["metrics"]["retrieve_learnings_top_k"], 3)
        self.assertEqual(payload["comparison"]["comparison_kind"], "adapter_retrieval_contract")
        self.assertEqual(payload["comparison"]["no_memory"]["retrieved_learning_count"], 0)
        self.assertGreater(payload["comparison"]["aippocampus"]["retrieved_learning_count"], 0)
        source_arm = payload["arms"]["aippocampus_source_backed_learning"]
        self.assertEqual(source_arm["status"], "train_only_runtime_projection")
        self.assertIn("source_backed_lesson_candidate", source_arm["input_layers"])
        self.assertGreaterEqual(source_arm["guidance_count"], 1)
        self.assertGreaterEqual(source_arm["source_ref_preserved_count"], 1)
        self.assertTrue(
            source_arm["training_correction_projection"]["learned_guidance_can_affect_projection"]
        )
        self.assertEqual(source_arm["claim_boundary"]["agent_learning_track_lift"], "not_measured")
        self.assertTrue(payload["artifacts"]["adapter_file_written"])
        self.assertTrue(payload["artifacts"]["learnings_file_written"])
        self.assertTrue(adapter_exists)
        self.assertTrue(learnings_exists)
        self.assertIsInstance(learning_rows[0], dict)
        self.assertTrue(learning_rows[0]["source_refs"])
        self.assertEqual(learning_rows[0]["claim_permission"], "working_guidance_only_not_fact")
        self.assertEqual(payload["official_requirements"]["state_bench_commit"], "83cb96de5429c43adfdb5cb9b6785439e937a3ca")
        self.assertFalse(payload["privacy_boundary"]["raw_trajectory_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertIn("leaderboard_submission_ready", payload["cannot_claim"])
        for forbidden in (
            RAW_USER_TEXT,
            RAW_ASSISTANT_TEXT,
            LOCAL_PATH_SENTINEL,
            str(state_bench_root),
            str(adapter_dir),
            str(learnings_path),
        ):
            self.assertNotIn(forbidden, encoded)

    def test_generated_adapter_exposes_read_only_retrieve_learnings_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learnings_path = root / "learnings.json"
            learnings_path.write_text(
                json.dumps(
                    [
                        "customer_support warranty policy: paid repair after claim limit",
                        "customer_support return policy: defective items may waive return window",
                        "travel change policy: fare difference only for selected ticket",
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            adapter_path = benchmark.write_state_bench_adapter(
                output_dir=root / "agents",
                learnings_path=learnings_path,
            )

            self._install_fake_state_bench()
            old_env = os.environ.get("AIPPOCAMPUS_STATE_BENCH_LEARNINGS")
            os.environ["AIPPOCAMPUS_STATE_BENCH_LEARNINGS"] = str(learnings_path)
            try:
                spec = importlib.util.spec_from_file_location("generated_state_bench_agent", adapter_path)
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                agent = module.AIppocampusStateBenchAgent()
                matches = agent.retrieve_learnings("warranty claim limit return", top_k=2)
            finally:
                if old_env is None:
                    os.environ.pop("AIPPOCAMPUS_STATE_BENCH_LEARNINGS", None)
                else:
                    os.environ["AIPPOCAMPUS_STATE_BENCH_LEARNINGS"] = old_env
                self._remove_fake_state_bench()

        self.assertIsInstance(matches, list)
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(isinstance(item, str) for item in matches))
        self.assertIn("warranty", matches[0])

    def test_matched_run_preflight_reports_missing_locked_eval_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_bench_root = root / "STATE-Bench"
            self._write_train_fixture(state_bench_root)
            adapter_dir = root / "agents"

            payload = benchmark.build_state_bench_agent_learning_report(
                state_bench_root=state_bench_root,
                domain="customer_support",
                adapter_output_dir=adapter_dir,
                learnings_output=adapter_dir / "learnings.json",
                write_adapter=True,
                prepare_matched_run=True,
                matched_run_output_dir=root / "outputs",
                matched_task_ids=["1-return_partial_order"],
                agent_model_name="gpt-5.4-mini",
                env={
                    "STATE_BENCH_AGENT_PROVIDER": "openai",
                    "STATE_BENCH_AGENT_API_KEY": "SECRET_AGENT_KEY",
                    "STATE_BENCH_AGENT_MODEL": "gpt-5.4-mini",
                },
            )
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            no_memory_adapter_exists = (adapter_dir / "no_memory_state_bench_agent.py").exists()

        preflight = payload["matched_one_domain_preflight"]
        self.assertEqual(payload["official_submission_decision"], "no_go_missing_locked_eval_client")
        self.assertEqual(preflight["status"], "blocked_missing_locked_eval_client")
        self.assertIn("missing_state_bench_eval_endpoint", preflight["blockers"])
        self.assertIn("missing_state_bench_eval_deployments", preflight["blockers"])
        self.assertEqual(preflight["planned_num_runs"], 5)
        self.assertEqual(preflight["planned_task_ids"], ["1-return_partial_order"])
        self.assertEqual(
            {arm["agent_class"] for arm in preflight["arms"]},
            {"AIppocampusStateBenchAgent", "NoMemoryStateBenchAgent"},
        )
        self.assertIn("NoMemoryStateBenchAgent", preflight["commands"]["no_memory_run_batch"])
        self.assertIn("AIppocampusStateBenchAgent", preflight["commands"]["aippocampus_run_batch"])
        self.assertTrue(no_memory_adapter_exists)
        self.assertTrue(payload["artifacts"]["no_memory_adapter_file_written"])
        self.assertFalse(preflight["env_readiness"]["locked_eval_endpoint_configured"])
        self.assertTrue(preflight["env_readiness"]["agent_client_configured"])
        self.assertNotIn("SECRET_AGENT_KEY", encoded)
        self.assertNotIn(str(adapter_dir), encoded)

    def test_matched_fixture_run_records_both_arms_without_official_score_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_bench_root = root / "STATE-Bench"
            self._write_train_fixture(state_bench_root)

            payload = benchmark.build_state_bench_agent_learning_report(
                state_bench_root=state_bench_root,
                domain="customer_support",
                max_train_files=5,
                run_matched_fixture=True,
                matched_task_ids=["fixture-warranty", "fixture-return"],
            )
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        matched = payload["matched_task_run"]
        self.assertEqual(matched["status"], "fixture_matched_task_run_completed")
        self.assertEqual(matched["official_score_claimable"], False)
        self.assertEqual(matched["matched_task_count"], 2)
        self.assertEqual(matched["arms"]["no_memory"]["task_run_count"], 2)
        self.assertEqual(matched["arms"]["aippocampus"]["task_run_count"], 2)
        self.assertGreater(
            matched["arms"]["aippocampus"]["retrieved_learning_count"],
            matched["arms"]["no_memory"]["retrieved_learning_count"],
        )
        self.assertEqual(
            payload["official_submission_decision"],
            "adapter_fixture_matched_run_no_go_official_score",
        )
        self.assertFalse(payload["official_score_claimable"])
        self.assertIn("official_state_bench_score", matched["cannot_claim"])
        self.assertNotIn(RAW_USER_TEXT, encoded)
        self.assertNotIn(str(state_bench_root), encoded)

    def test_runner_writes_report_without_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_bench_root = root / "STATE-Bench"
            output = root / "report.json"
            self._write_train_fixture(state_bench_root)

            code = benchmark.main(
                [
                    "--state-bench-root",
                    str(state_bench_root),
                    "--domain",
                    "customer_support",
                    "--output",
                    str(output),
                    "--json",
                ]
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            encoded = output.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "adapter_dry_run_ready")
        self.assertNotIn(str(state_bench_root), encoded)
        self.assertNotIn(RAW_USER_TEXT, encoded)

    @staticmethod
    def _write_train_fixture(state_bench_root: Path) -> None:
        train_dir = state_bench_root / "datasets" / "train_task_trajectories" / "customer_support"
        train_dir.mkdir(parents=True)
        rows = [
            {
                "name": "warranty maxed",
                "local_path": LOCAL_PATH_SENTINEL,
                "conversation": [
                    {"role": "user", "content": RAW_USER_TEXT},
                    {
                        "role": "assistant",
                        "content": RAW_ASSISTANT_TEXT,
                        "tool_calls": [
                            {
                                "name": "get_policies",
                                "arguments": {"topic": "warranty"},
                                "result": {
                                    "topic": "warranty",
                                    "rules": {
                                        "claim_limit": "Max claims reached: paid repair only.",
                                        "repair_vs_replace": "Repair expensive items first.",
                                    },
                                },
                            },
                            {
                                "name": "get_warranty_status",
                                "arguments": {"item_id": "ITEM-SECRET"},
                                "result": {"claim_count": 3, "max_claims": 3},
                            },
                        ],
                    },
                ],
            },
            {
                "conversation": [
                    {"role": "user", "content": "raw fixture return text"},
                    {
                        "role": "assistant",
                        "content": "raw fixture return response",
                        "tool_calls": [
                            {
                                "name": "get_policies",
                                "arguments": {"topic": "return"},
                                "result": {
                                    "topic": "return",
                                    "rules": {
                                        "defective": "Defective item may allow no-cost return.",
                                        "agent_computes_amount": "Use preview component breakdown.",
                                    },
                                },
                            }
                        ],
                    },
                ],
            },
        ]
        for index, row in enumerate(rows):
            (train_dir / f"{index}-fixture.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    @staticmethod
    def _install_fake_state_bench() -> None:
        state_bench = types.ModuleType("state_bench")
        agents = types.ModuleType("state_bench.agents")
        state_bench_agent = types.ModuleType("state_bench.agents.state_bench")

        class StateBenchAgent:  # noqa: D401 - fake upstream base class.
            """Fake upstream base class for adapter import tests."""

        state_bench_agent.StateBenchAgent = StateBenchAgent
        sys.modules["state_bench"] = state_bench
        sys.modules["state_bench.agents"] = agents
        sys.modules["state_bench.agents.state_bench"] = state_bench_agent

    @staticmethod
    def _remove_fake_state_bench() -> None:
        for name in (
            "state_bench.agents.state_bench",
            "state_bench.agents",
            "state_bench",
        ):
            sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
