from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.source import source_intake_health as intake  # noqa: E402


class SourceIntakeHealthTests(unittest.TestCase):
    def test_degraded_fixture_reports_intake_drift_without_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message_id": "m1",
                                "role": "assistant",
                                "tool_payload": {"secret": "sk-testfixture123456"},
                            }
                        ),
                        json.dumps({"message_id": "m1", "role": "assistant"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (clean / "turns.jsonl").write_text(
                json.dumps({"turn_id": "t1", "path_hint": "C:\\Users\\Example\\secret.txt"})
                + "\n",
                encoding="utf-8",
            )
            manifest = {
                "message_count": 1,
                "turn_count": 1,
                "registry_entry_count": 3,
                "materialized_source_count": 2,
                "derived_summary_count": 1,
                "user_facing_summary_count": 0,
                "final_answer_count": 0,
                "expected_final_answer_count": 1,
                "user_turn_count": 0,
                "expected_user_turn_count": 1,
                "source_refs": [{"source_ref_hash": "ref_broken", "path_exists": False}],
                "source_intake": {
                    "hook": {"available": False, "version_status": "stale_versioned_path"},
                    "restart_durability_status": "degraded",
                },
            }

            report = intake.source_intake_health_summary(
                clean,
                manifest,
                registry_path=Path(tmp) / "registry" / "threads.json",
                expected_message_count=4,
                expected_turn_count=2,
            )

        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        metrics = report["metrics"]
        self.assertEqual(report["source_quality_status"], "degraded")
        self.assertEqual(metrics["hook_available"], False)
        self.assertEqual(metrics["hook_version_status"], "stale_versioned_path")
        self.assertEqual(metrics["stale_hook_path_count"], 1)
        self.assertEqual(metrics["source_truncation_detected_count"], 1)
        self.assertEqual(metrics["duplicated_source_event_count"], 1)
        self.assertEqual(metrics["polluted_source_event_count"], 1)
        self.assertEqual(metrics["local_path_leak_count"], 1)
        self.assertEqual(metrics["secret_like_leak_count"], 1)
        self.assertEqual(metrics["broken_source_ref_count"], 1)
        self.assertEqual(metrics["registry_clean_source_mismatch_count"], 1)
        self.assertEqual(metrics["derived_summary_mismatch_count"], 1)
        self.assertEqual(metrics["missing_final_answer_count"], 1)
        self.assertEqual(metrics["missing_user_turn_count"], 1)
        self.assertIn("generic_import_fallback", report["fallback_posture"])
        self.assertIn("source_backed_claims_safe_when_intake_degraded", report["cannot_claim"])
        self.assertNotIn("sk-testfixture123456", encoded)
        self.assertNotIn("C:\\Users\\Example", encoded)
        self.assertFalse(report["privacy_boundary"]["raw_tool_payload_emitted"])

    def test_clean_fixture_reports_ok_with_generic_import_fallback_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "m1",
                        "role": "final_answer",
                        "content_sha256": "sha",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (clean / "turns.jsonl").write_text(
                json.dumps({"turn_id": "t1", "role": "user"}) + "\n",
                encoding="utf-8",
            )
            manifest = {
                "message_count": 1,
                "turn_count": 1,
                "registry_entry_count": 1,
                "materialized_source_count": 1,
                "final_answer_count": 1,
                "expected_final_answer_count": 1,
                "user_turn_count": 1,
                "expected_user_turn_count": 1,
                "source_intake": {
                    "hook": {"available": True, "version_status": "current"},
                    "restart_durability_status": "ok",
                },
            }

            report = intake.source_intake_health_summary(
                clean,
                manifest,
                expected_message_count=1,
                expected_turn_count=1,
            )

        self.assertEqual(report["source_quality_status"], "ok")
        self.assertEqual(report["degraded_reasons"], [])
        self.assertEqual(report["metrics"]["generic_import_fallback_available"], True)
        self.assertEqual(report["cannot_claim"], [])


if __name__ == "__main__":
    unittest.main()
