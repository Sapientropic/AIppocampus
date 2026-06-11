from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_recall_degradation_audit as benchmark  # noqa: E402


class RecallDegradationAuditBenchmarkTests(unittest.TestCase):
    def test_clean_source_routes_derive_distinct_safe_triage_without_prefilled_labels(self) -> None:
        report = benchmark.build_recall_degradation_audit_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["kind"], "aippocampus_recall_degradation_audit_fixture")
        self.assertIn("supports", report)
        self.assertIn("material_limits", report)

        metrics = report["metrics"]
        self.assertGreaterEqual(metrics["clean_source_reopenable_route_count"], 3)
        self.assertGreaterEqual(metrics["same_phase_title_route_count"], 3)
        self.assertEqual(metrics["input_prefilled_route_label_count"], 0)
        self.assertEqual(metrics["generic_reopen_hint_count"], 0)
        self.assertEqual(metrics["packet_triage_collision_count"], 0)
        self.assertEqual(metrics["blind_deepen_required_count"], 0)
        self.assertEqual(metrics["ask_light_question_with_reopenable_candidate_count"], 0)
        self.assertEqual(metrics["manual_search_fallback_count"], 0)
        self.assertEqual(metrics["cannot_verify_without_next_safe_action_count"], 0)
        self.assertEqual(metrics["foreground_packet_budget_violation_count"], 0)

        clean_case = report["cases"][0]
        route_labels = {
            route["route_label"]
            for route in clean_case["route_summaries"]
            if route.get("route_label")
        }
        packet_labels = {
            packet["route_label"]
            for packet in clean_case["memory_packets"]
            if packet.get("output_mode") == "reopenable_route"
        }
        self.assertGreaterEqual(len(route_labels), 3)
        self.assertTrue(route_labels.issubset(packet_labels))

        source_thin = report["cases"][1]
        self.assertEqual(source_thin["deepen_status"], "cannot_verify")
        self.assertTrue(source_thin["next_safe_action_present"])
        self.assertFalse(source_thin["manual_terms_invented"])

        for name, value in report["red_lines"].items():
            with self.subTest(red_line=name):
                self.assertEqual(value, 0)

        for forbidden in (
            "source_handles",
            "source_refs",
            "source_id",
            "message_id",
            "turn_id",
            "PRIVATE_DEGRADATION_SENTINEL",
            "C:\\",
            "/Users/",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
