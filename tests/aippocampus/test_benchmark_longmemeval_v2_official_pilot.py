from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (REPO_ROOT, BENCHMARKS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import benchmark_longmemeval_v2_official_pilot as decision  # noqa: E402
from benchmarks.aippocampus.adapters import longmemeval_v2_aippocampus_adapter as adapter  # noqa: E402


class LongMemEvalV2OfficialPilotTests(unittest.TestCase):
    def test_adapter_returns_official_memory_context_items_without_metadata_text(self) -> None:
        memory = adapter.AippocampusContextProviderMemory(
            {
                "max_context_items": 2,
                "max_context_chars": 80,
            }
        )
        memory.insert(
            {
                "id": "trajectory-1",
                "goal": "The refund workflow uses the blue action button.",
                "states": [
                    {
                        "accessibility_tree": "Refund page has a compact status panel.",
                        "screenshot": "C:\\Users\\Administrator\\secret-shot.png",
                        "url": "https://example.invalid/raw",
                    }
                ],
            }
        )
        memory.insert(
            {
                "id": "trajectory-2",
                "goal": "Shipping setup uses the green button.",
            }
        )

        rows = memory.query("Which refund workflow action should be used?")
        metadata = memory.post_query_hook(
            query="Which refund workflow action should be used?",
            query_image=None,
            memory_context=rows,
        )

        self.assertEqual(adapter.AippocampusContextProviderMemory.memory_type, "aippocampus_context_provider")
        self.assertTrue(rows)
        self.assertTrue(all(row["type"] == "text" for row in rows))
        joined = json.dumps(rows, ensure_ascii=False)
        self.assertIn("refund workflow", joined)
        self.assertNotIn("secret-shot", joined)
        self.assertNotIn("https://example.invalid/raw", joined)
        self.assertEqual(metadata["memory_type"], "aippocampus_context_provider")
        self.assertFalse(metadata["raw_text_emitted_in_metadata"])
        self.assertGreaterEqual(metadata["candidate_record_count"], 1)

    def test_adapter_save_and_load_preserves_queryable_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = adapter.AippocampusContextProviderMemory({})
            memory.insert({"id": "t1", "goal": "The tax module lives under admin tools."})
            memory._save_backend(root)

            restored = adapter.AippocampusContextProviderMemory({})
            restored._load_backend(root)
            rows = restored.query("Where is the tax module?")

        self.assertTrue(rows)
        self.assertIn("tax module", rows[0]["value"])

    def test_decision_report_selects_tiny_official_pilot_without_claiming_score(self) -> None:
        config = decision.PilotConfig(
            pilot_questions=5,
            max_pilot_questions=20,
            reader_model="Qwen/Qwen3.5-9B",
            reader_base_url_env="READER_BASE_URL",
            reader_api_key_env="OPENAI_API_KEY",
            evaluator_model="gpt-5.2",
            evaluator_reasoning_effort="medium",
            memory_context_max_tokens=200_000,
            query_latency_budget_seconds=120.0,
            total_cost_budget_usd=10.0,
        )

        payload = decision.build_report(config)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "official_pilot_plan_ready")
        self.assertEqual(
            payload["decision"]["decision"],
            "move_to_tiny_official_answer_latency_pilot",
        )
        self.assertEqual(
            payload["adapter_contract"]["memory_type"],
            "aippocampus_context_provider",
        )
        self.assertIn("insert", payload["official_harness_contract"]["official_memory_api"]["required_methods"])
        self.assertIn("query_latency", payload["metric_separation"])
        self.assertIn("answer_accuracy", payload["metric_separation"])
        self.assertIn("reader_evaluator_dependency", payload["metric_separation"])
        budget = payload["provider_execution_budget"]
        self.assertTrue(budget["ok_to_start"])
        self.assertFalse(budget["live_mode"])
        self.assertEqual(
            budget["no_provider_budget_required_reason"],
            "decision_report_only_no_official_reader_execution",
        )
        self.assertTrue(budget["planned_live_pilot_requires_budget_before_run"])
        self.assertIn("longmemeval_v2_answer_accuracy", payload["cannot_claim"])
        self.assertIn("longmemeval_v2_lafs_gain", payload["cannot_claim"])
        self.assertTrue(payload["sanitized_report_validation"]["ok"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(REPO_ROOT), dumped)
        self.assertNotIn("sk-", dumped)

    def test_sanitized_report_validator_rejects_paths_and_credentials(self) -> None:
        payload = {
            "path": "C:\\Users\\Administrator\\secret\\official-run",
            "token": "sk-" + ("a" * 30),
        }

        result = decision.validate_sanitized_report(payload)

        self.assertFalse(result["ok"])
        kinds = {error["kind"] for error in result["errors"]}
        self.assertIn("absolute_path_leak", kinds)
        self.assertIn("credential_like_string", kinds)


if __name__ == "__main__":
    unittest.main()
