from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

diff = import_benchmark_module("benchmark_run_history_diff")

def suite_payload(
    *,
    profile: str = "release-evidence",
    effective_tracks: list[str] | None = None,
    metric: float = 0.95,
    lower_bound: float = 0.9,
    denominator: int = 100,
    quality_gate_ok: bool = True,
    raw_text_emitted: bool = False,
    elapsed_ms: float = 1000.0,
    include_live_semantic: bool = False,
) -> dict:
    effective_tracks = effective_tracks or [
        "gate_decision",
        "payload_fidelity",
        "source_evidence_retrieval",
    ]
    numerator = round(metric * denominator)
    return {
        "schema_version": 1,
        "kind": "aippocampus_benchmark_suite",
        "generated_at": "2026-06-01T00:00:00Z",
        "status": "quality_gate_passed" if quality_gate_ok else "baseline_captured_with_known_gaps",
        "ok": True,
        "quality_gate_ok": quality_gate_ok,
        "config": {
            "profile": profile,
            "include_track_b": "source_evidence_retrieval" in effective_tracks,
            "include_track_d": "compaction_continuity" in effective_tracks,
            "include_private_text": False,
            "include_live_semantic": include_live_semantic,
            "source_ranking": "dynamic_source",
            "source_top_k": 5,
            "source_min_hit_rate": 0.85,
            "fts5_seed": 20260527,
            "fts5_top_k": 10,
            "standard_dataset": "locomo",
            "standard_top_k": 10,
        },
        "profile_metadata": {
            "selected_profile": {"name": profile},
            "effective_surface": {
                "included_tracks": effective_tracks,
                "optional_surfaces": [],
                "private_text_enabled": False,
                "live_semantic_enabled": include_live_semantic,
                "registry_path_provided": False,
            },
        },
        "threshold_metadata": {
            "source_min_hit_rate": {
                "value": 0.85,
                "claim_boundary": "bounded retrieval diagnostic",
            }
        },
        "track_statuses": {
            name: "sufficient" for name in effective_tracks
        },
        "rate_estimates": {
            "source_evidence_retrieval.source_evidence.top_k_hit_rate": {
                "name": "top_k_hit_rate",
                "numerator": numerator,
                "denominator": denominator,
                "point_estimate": metric,
                "confidence_interval": {
                    "method": "wilson_score",
                    "lower": lower_bound,
                    "upper": 0.99,
                    "defined": True,
                },
                "gate": {
                    "threshold": 0.85,
                    "passes_point_estimate": metric >= 0.85,
                    "lower_bound": lower_bound,
                    "passes_lower_bound": lower_bound >= 0.85,
                },
            }
        },
        "privacy_boundary": {
            "raw_text_emitted": raw_text_emitted,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["real_history_gate_quality"],
        "elapsed_ms": elapsed_ms,
    }

class BenchmarkRunHistoryDiffTests(unittest.TestCase):
    def test_comparable_runs_with_stable_metrics_report_no_regression(self) -> None:
        baseline = suite_payload(metric=0.95, lower_bound=0.9)
        current = suite_payload(metric=0.94, lower_bound=0.89)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "no_regression")
        self.assertTrue(payload["comparison"]["comparable"])
        self.assertEqual(payload["regressions"], [])
        self.assertEqual(payload["warnings"], [])

    def test_pass_threshold_material_drop_reports_regression(self) -> None:
        baseline = suite_payload(metric=0.95, lower_bound=0.9, quality_gate_ok=True)
        current = suite_payload(metric=0.88, lower_bound=0.86, quality_gate_ok=True)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "regression")
        self.assertTrue(payload["quality_gate_context"]["current_quality_gate_ok"])
        self.assertEqual(payload["regressions"][0]["reason_code"], "metric_drop")
        self.assertEqual(
            payload["regressions"][0]["metric"],
            "source_evidence_retrieval.source_evidence.top_k_hit_rate",
        )
        self.assertEqual(payload["regressions"][0]["baseline_point_estimate"], 0.95)
        self.assertEqual(payload["regressions"][0]["current_point_estimate"], 0.88)

    def test_incomparable_profile_or_surface_returns_warning_not_metric_regression(self) -> None:
        baseline = suite_payload(profile="release-evidence")
        current = suite_payload(profile="public-fast", effective_tracks=["gate_decision", "payload_fidelity"])

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["comparison"]["comparable"])
        self.assertIn("profile_changed", payload["comparison"]["incomparable_reasons"])
        self.assertIn("effective_surface_changed", payload["comparison"]["incomparable_reasons"])
        self.assertEqual(payload["metric_deltas"], [])

    def test_config_surface_change_returns_warning_not_metric_regression(self) -> None:
        baseline = suite_payload()
        current = suite_payload()
        baseline["config"]["standard_max_questions"] = 20
        current["config"]["standard_max_questions"] = 40

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["comparison"]["comparable"])
        self.assertIn("config_subset_changed", payload["comparison"]["incomparable_reasons"])
        self.assertEqual(payload["metric_deltas"], [])

    def test_public_adapter_corpus_signature_change_is_incomparable_without_path_leak(self) -> None:
        baseline = suite_payload(effective_tracks=["gate_decision", "source_evidence_retrieval"])
        current = suite_payload(effective_tracks=["gate_decision", "source_evidence_retrieval"])
        adapter = {
            "kind": "standard_public_retrieval_qa_source_evidence",
            "ok": True,
            "status": "sufficient",
            "config": {
                "dataset": "locomo",
                "corpus_path_sha1": "safe-old",
                "standard_corpus_path": r"C:\synthetic-leak\private\locomo.json",
            },
            "corpus": {"dataset": "locomo", "corpus_path_sha1": "safe-old"},
            "metrics": {"question_count": 20},
            "skip_reason": r"C:\synthetic-leak\private\messages.jsonl was not found",
        }
        baseline["tracks"] = {
            "source_evidence_retrieval": {
                "tracks": {"standard_public_retrieval_qa": adapter}
            }
        }
        changed_adapter = json.loads(json.dumps(adapter))
        changed_adapter["config"]["corpus_path_sha1"] = "safe-new"
        changed_adapter["corpus"]["corpus_path_sha1"] = "safe-new"
        current["tracks"] = {
            "source_evidence_retrieval": {
                "tracks": {"standard_public_retrieval_qa": changed_adapter}
            }
        }

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["comparison"]["comparable"])
        self.assertIn("public_adapter_signature_changed", payload["comparison"]["incomparable_reasons"])
        serialized = json.dumps(payload)
        self.assertNotIn("synthetic-leak", serialized)
        self.assertNotIn("locomo.json", serialized)
        self.assertNotIn("messages.jsonl", serialized)

    def test_threshold_change_is_incomparable_not_no_regression(self) -> None:
        baseline = suite_payload(metric=0.9)
        current = suite_payload(metric=0.9)
        baseline["threshold_metadata"]["source_min_hit_rate"]["value"] = 0.85
        current["threshold_metadata"]["source_min_hit_rate"]["value"] = 0.9
        metric_name = "source_evidence_retrieval.source_evidence.top_k_hit_rate"
        baseline["rate_estimates"][metric_name]["gate"] = {"threshold": 0.85}
        current["rate_estimates"][metric_name]["gate"] = {"threshold": 0.9}

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["comparison"]["comparable"])
        self.assertIn("thresholds_changed", payload["comparison"]["incomparable_reasons"])
        self.assertEqual(payload["metric_deltas"], [])

    def test_metric_missing_in_current_is_warning(self) -> None:
        baseline = suite_payload()
        current = suite_payload()
        current["rate_estimates"] = {}

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertIn(
            {
                "reason_code": "metric_missing_in_current",
                "metric": "source_evidence_retrieval.source_evidence.top_k_hit_rate",
            },
            payload["warnings"],
        )
        self.assertEqual(payload["summary"]["missing_metric_count"], 1)

    def test_live_semantic_metric_drop_is_warning_only(self) -> None:
        baseline = suite_payload(include_live_semantic=True)
        current = suite_payload(include_live_semantic=True)
        baseline["rate_estimates"] = {
            "live_semantic_gate.surface_recall": {
                "name": "surface_recall",
                "numerator": 9,
                "denominator": 10,
                "point_estimate": 0.9,
                "confidence_interval": {"lower": 0.6, "upper": 0.98},
            }
        }
        current["rate_estimates"] = {
            "live_semantic_gate.surface_recall": {
                "name": "surface_recall",
                "numerator": 7,
                "denominator": 10,
                "point_estimate": 0.7,
                "confidence_interval": {"lower": 0.4, "upper": 0.9},
            }
        }

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["regressions"], [])
        self.assertEqual(payload["warnings"][0]["reason_code"], "live_metric_drop_warning")

    def test_lower_bound_only_drop_is_warning(self) -> None:
        baseline = suite_payload(metric=0.9, lower_bound=0.85)
        current = suite_payload(metric=0.9, lower_bound=0.78)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["warnings"][0]["reason_code"], "metric_drop_warning")
        self.assertEqual(payload["regressions"], [])

    def test_quality_gate_false_is_context_not_trend_regression(self) -> None:
        baseline = suite_payload(metric=0.9, quality_gate_ok=False)
        current = suite_payload(metric=0.9, quality_gate_ok=False)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "no_regression")
        self.assertFalse(payload["quality_gate_context"]["current_quality_gate_ok"])

    def test_privacy_boundary_regression_is_separate_from_rate_deltas(self) -> None:
        baseline = suite_payload(raw_text_emitted=False)
        current = suite_payload(raw_text_emitted=True)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "regression")
        self.assertIn(
            {
                "reason_code": "privacy_boundary_regression",
                "field": "raw_text_emitted",
                "baseline": False,
                "current": True,
            },
            payload["regressions"],
        )

    def test_sample_size_drop_is_warning_when_rate_is_stable(self) -> None:
        baseline = suite_payload(metric=0.95, denominator=100)
        current = suite_payload(metric=0.95, denominator=40)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["warnings"][0]["reason_code"], "sample_size_drop")
        self.assertEqual(
            payload["warnings"][0]["metric"],
            "source_evidence_retrieval.source_evidence.top_k_hit_rate",
        )

    def test_lower_is_better_metric_regresses_when_it_increases(self) -> None:
        baseline = suite_payload()
        current = suite_payload()
        baseline["rate_estimates"] = {
            "gate_decision.evidence_false_positive_rate": {
                "name": "evidence_false_positive_rate",
                "numerator": 1,
                "denominator": 100,
                "point_estimate": 0.01,
                "confidence_interval": {"lower": 0.0, "upper": 0.04},
            }
        }
        current["rate_estimates"] = {
            "gate_decision.evidence_false_positive_rate": {
                "name": "evidence_false_positive_rate",
                "numerator": 8,
                "denominator": 100,
                "point_estimate": 0.08,
                "confidence_interval": {"lower": 0.04, "upper": 0.14},
            }
        }

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "regression")
        self.assertEqual(payload["metric_deltas"][0]["direction"], "lower_is_better")
        self.assertEqual(payload["regressions"][0]["reason_code"], "metric_drop")

    def test_elapsed_time_increase_is_warning_not_regression(self) -> None:
        baseline = suite_payload(elapsed_ms=1000.0)
        current = suite_payload(elapsed_ms=1800.0)

        payload = diff.compare_benchmark_runs(baseline, current)

        self.assertEqual(payload["status"], "warning")
        self.assertIn(
            {
                "reason_code": "elapsed_time_increase",
                "baseline_elapsed_ms": 1000.0,
                "current_elapsed_ms": 1800.0,
                "increase_ratio": 0.8,
            },
            payload["warnings"],
        )

    def test_cli_compares_saved_json_files(self) -> None:
        baseline = suite_payload(metric=0.95)
        current = suite_payload(metric=0.88)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline_path = tmp_path / "baseline.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "diff.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = diff.main(
                    [
                        "--baseline",
                        str(baseline_path),
                        "--current",
                        str(current_path),
                        "--output",
                        str(output_path),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "regression")

if __name__ == "__main__":
    unittest.main()
