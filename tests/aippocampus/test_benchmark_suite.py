from __future__ import annotations

import json
import sys
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

import benchmark_suite as suite  # noqa: E402


def fake_gate_payload() -> dict:
    return {
        "kind": "aippocampus_memory_decision_gate_benchmark",
        "ok": True,
        "metrics": {"total_cases": 2, "accuracy": 1.0, "macro_f1": 1.0},
        "cases": [{"case_id": "gate-a", "prompt_sha1": "abc"}],
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["real_history_gate_quality"],
    }


def fake_payload_payload() -> dict:
    return {
        "kind": "aippocampus_payload_fidelity_benchmark",
        "ok": True,
        "metrics": {
            "total_cases": 2,
            "payload_correct_rate": 1.0,
            "privacy_breach_count": 0,
        },
        "cases": [{"case_id": "payload-a", "context_sha1": "def"}],
        "privacy_boundary": {
            "raw_context_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["real_history_payload_fidelity"],
    }


def fake_retrieval_payload(*, ok: bool = False) -> dict:
    return {
        "kind": "aippocampus_source_evidence_retrieval_benchmark",
        "ok": ok,
        "status": "sufficient" if ok else "diagnostic_only",
        "tracks": {
            "fts5_source_line": {
                "kind": "aippocampus_fts5_recall_benchmark",
                "ok": True,
                "total_cases": 2,
                "hit_rate_top_k": 1.0,
            },
            "source_evidence": {
                "kind": "selected_source_evidence_recall_eval",
                "ok": ok,
                "status": "sufficient" if ok else "insufficient_recall_hits",
                "case_count": 2,
                "top_k_hit_rate": 0.5,
            },
        },
        "cases": {"fts5": [{"case_id": "fts-a"}], "source_evidence": []},
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["selected_source_evidence_recall"],
    }


def fake_live_semantic_payload() -> dict:
    return {
        "kind": "aippocampus_live_semantic_gate_benchmark",
        "ok": True,
        "quality_gate_ok": True,
        "status": "sufficient",
        "metrics": {"total_cases": 3, "accuracy": 1.0, "semantic_model_call_count": 2},
        "cases": [{"case_id": "semantic-a", "prompt_sha1": "ghi"}],
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "semantic_aliases_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["all_future_semantic_prompts_correct"],
    }


def fake_compaction_payload() -> dict:
    return {
        "kind": "aippocampus_compaction_continuity_benchmark",
        "ok": True,
        "quality_gate_ok": True,
        "status": "sufficient",
        "metrics": {"total_cases": 8, "correction_anchor_recall": 1.0},
        "cases": [{"case_id_sha1": "trackd-a"}],
        "privacy_boundary": {
            "raw_correction_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["runtime_correction_event_capture"],
    }


class BenchmarkSuiteTests(unittest.TestCase):
    def test_suite_config_factory_maps_parser_args(self) -> None:
        parser = suite.build_arg_parser()
        args = parser.parse_args(
            [
                "--skip-track-b",
                "--skip-track-d",
                "--include-live-semantic",
                "--live-semantic-workers",
                "deepseek,openai",
                "--source-max-cases",
                "7",
                "--track-d-cases",
                "4",
                "--standard-dataset",
                "locomo",
            ]
        )

        config = suite.benchmark_suite_config_from_args(args)

        self.assertFalse(config.include_track_b)
        self.assertFalse(config.include_track_d)
        self.assertTrue(config.include_live_semantic)
        self.assertEqual(config.live_semantic_workers, ("deepseek", "openai"))
        self.assertEqual(config.source_max_cases, 7)
        self.assertEqual(config.track_d_case_limit, 4)
        self.assertEqual(config.standard_dataset, "locomo")

    def test_public_fast_profile_forces_fresh_clone_deterministic_surface(self) -> None:
        parser = suite.build_arg_parser()
        args = parser.parse_args(
            [
                "--profile",
                "public-fast",
                "--include-private-text",
                "--include-live-semantic",
                "--include-sharegpt-public-track-b",
                "--include-standard-public-track-b",
                "--registry",
                "private-registry.json",
            ]
        )

        config = suite.benchmark_suite_config_from_args(args)

        self.assertEqual(config.profile, "public-fast")
        self.assertIsNone(config.registry_path)
        self.assertFalse(config.include_private_text)
        self.assertFalse(config.include_track_b)
        self.assertFalse(config.include_deterministic_source_labels)
        self.assertFalse(config.include_live_semantic)
        self.assertFalse(config.include_sharegpt_public_track_b)
        self.assertFalse(config.include_standard_public_track_b)

    def test_public_fast_profile_runs_only_deterministic_a_c_d_tracks(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.compaction_benchmark,
                "run_benchmark",
                return_value=fake_compaction_payload(),
            ),
            patch.object(
                suite.retrieval_benchmark,
                "run_source_evidence_retrieval_benchmark",
                return_value=fake_retrieval_payload(ok=True),
            ) as retrieval_run,
            patch.object(
                suite.live_semantic_benchmark,
                "run_live_semantic_eval",
                return_value=fake_live_semantic_payload(),
            ) as live_run,
        ):
            payload = suite.run_benchmark_suite(
                profile="public-fast",
                include_private_text=True,
                include_track_b=True,
                include_live_semantic=True,
            )

        self.assertEqual(payload["config"]["profile"], "public-fast")
        self.assertEqual(set(payload["tracks"]), {"gate_decision", "payload_fidelity", "compaction_continuity"})
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        self.assertIn("public_fast_profile_track_b_quality", payload["cannot_claim"])
        self.assertIn("public_fast_profile_live_semantic_quality", payload["cannot_claim"])
        retrieval_run.assert_not_called()
        live_run.assert_not_called()

    def test_suite_includes_track_d_by_default(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.compaction_benchmark,
                "run_benchmark",
                return_value=fake_compaction_payload(),
            ) as compaction_run,
        ):
            payload = suite.run_benchmark_suite(
                include_track_b=False,
                track_d_case_limit=4,
            )

        self.assertIn("compaction_continuity", payload["tracks"])
        self.assertEqual(payload["track_statuses"]["compaction_continuity"], "sufficient")
        self.assertIn("runtime_correction_event_capture", payload["cannot_claim"])
        compaction_run.assert_called_once_with(
            include_private_text=False,
            case_limit=4,
        )

    def test_suite_can_skip_track_d(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.compaction_benchmark,
                "run_benchmark",
                return_value=fake_compaction_payload(),
            ) as compaction_run,
        ):
            payload = suite.run_benchmark_suite(
                include_track_b=False,
                include_track_d=False,
            )

        self.assertNotIn("compaction_continuity", payload["tracks"])
        compaction_run.assert_not_called()

    def test_suite_track_d_case_limit_is_diagnostic_not_capture_failure(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
        ):
            payload = suite.run_benchmark_suite(
                include_track_b=False,
                track_d_case_limit=4,
            )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "baseline_captured_with_known_gaps")
        self.assertEqual(
            payload["track_statuses"]["compaction_continuity"],
            "diagnostic_subset",
        )

    def test_suite_captures_baseline_even_when_track_b_is_diagnostic(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ) as gate_run,
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ) as payload_run,
            patch.object(
                suite.retrieval_benchmark,
                "run_source_evidence_retrieval_benchmark",
                return_value=fake_retrieval_payload(ok=False),
            ) as retrieval_run,
        ):
            payload = suite.run_benchmark_suite(
                include_deterministic_source_labels=False,
            )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "baseline_captured_with_known_gaps")
        self.assertEqual(
            payload["track_statuses"]["source_evidence_retrieval"],
            "diagnostic_only",
        )
        self.assertIn("selected_source_evidence_recall", payload["cannot_claim"])
        self.assertIn("source_evidence_retrieval", payload["known_gaps"])
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        self.assertNotIn("FAKE_TEST_PRIVATE", json.dumps(payload))
        gate_run.assert_called_once()
        payload_run.assert_called_once()
        retrieval_run.assert_called_once()

    def test_suite_can_add_deterministic_source_label_diagnostic_slice(self) -> None:
        deterministic_payload = {
            "ok": False,
            "status": "insufficient_recall_hits",
            "claim_level": "diagnostic_only",
            "cannot_claim": ["selected_semantic_source_evidence"],
            "case_count": 3,
            "passed_count": 2,
            "failed_count": 1,
            "top_k": 5,
            "top_k_hit_rate": 0.6667,
            "min_cases": 1,
            "min_hit_rate": 0.85,
            "label_coverage": ["personal_reflection"],
            "warning_count": 0,
            "ranking": "dynamic_source",
            "prompt_kind": "fuzzy_life_wide_source_evidence",
            "failure_diagnostics": {"failed_count": 1},
        }
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.retrieval_benchmark,
                "run_source_evidence_retrieval_benchmark",
                return_value=fake_retrieval_payload(ok=False),
            ),
            patch.object(
                suite.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=deterministic_payload,
            ) as source_run,
        ):
            payload = suite.run_benchmark_suite(
                include_deterministic_source_labels=True,
            )

        self.assertIn("source_evidence_deterministic_labels", payload["tracks"])
        self.assertEqual(
            payload["track_statuses"]["source_evidence_deterministic_labels"],
            "insufficient_recall_hits",
        )
        source_run.assert_called_once()
        self.assertFalse(source_run.call_args.kwargs["require_semantic_sidecar"])

    def test_suite_can_include_optional_live_semantic_track(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.live_semantic_benchmark,
                "run_live_semantic_eval",
                return_value=fake_live_semantic_payload(),
            ) as live_run,
        ):
            payload = suite.run_benchmark_suite(
                include_track_b=False,
                include_live_semantic=True,
                live_semantic_conversations=1,
                live_semantic_case_workers=4,
            )

        self.assertIn("live_semantic_gate", payload["tracks"])
        self.assertEqual(payload["track_statuses"]["live_semantic_gate"], "sufficient")
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        live_run.assert_called_once()
        self.assertEqual(live_run.call_args.kwargs["sharegpt_conversations"], 1)
        self.assertEqual(live_run.call_args.kwargs["case_workers"], 4)

    def test_suite_can_opt_into_sharegpt_public_track_b_slice(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.retrieval_benchmark,
                "run_source_evidence_retrieval_benchmark",
                return_value=fake_retrieval_payload(ok=True),
            ) as retrieval_run,
        ):
            payload = suite.run_benchmark_suite(
                include_deterministic_source_labels=False,
                include_sharegpt_public_track_b=True,
                sharegpt_public_conversations=20,
                sharegpt_public_max_cases=40,
                sharegpt_public_min_cases=12,
            )

        self.assertEqual(payload["track_statuses"]["source_evidence_retrieval"], "sufficient")
        retrieval_run.assert_called_once()
        self.assertEqual(retrieval_run.call_args.kwargs["include_sharegpt_public"], True)
        self.assertEqual(retrieval_run.call_args.kwargs["sharegpt_public_conversations"], 20)
        self.assertEqual(retrieval_run.call_args.kwargs["sharegpt_public_max_cases"], 40)
        self.assertEqual(retrieval_run.call_args.kwargs["sharegpt_public_min_cases"], 12)

    def test_suite_can_opt_into_standard_public_track_b_slice(self) -> None:
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=fake_gate_payload(),
            ),
            patch.object(
                suite.payload_benchmark,
                "run_benchmark",
                return_value=fake_payload_payload(),
            ),
            patch.object(
                suite.retrieval_benchmark,
                "run_source_evidence_retrieval_benchmark",
                return_value=fake_retrieval_payload(ok=True),
            ) as retrieval_run,
        ):
            payload = suite.run_benchmark_suite(
                include_deterministic_source_labels=False,
                include_standard_public_track_b=True,
                standard_dataset="longmemeval-v1-oracle",
                standard_max_questions=10,
                standard_min_questions=5,
                standard_top_k=10,
                standard_context_radius=5,
                standard_line_reranker_mode="semantic",
                standard_line_reranker_workers=4,
            )

        self.assertEqual(payload["track_statuses"]["source_evidence_retrieval"], "sufficient")
        retrieval_run.assert_called_once()
        self.assertEqual(retrieval_run.call_args.kwargs["include_standard_public"], True)
        self.assertEqual(
            retrieval_run.call_args.kwargs["standard_dataset"],
            "longmemeval-v1-oracle",
        )
        self.assertEqual(retrieval_run.call_args.kwargs["standard_max_questions"], 10)
        self.assertEqual(retrieval_run.call_args.kwargs["standard_min_questions"], 5)
        self.assertEqual(retrieval_run.call_args.kwargs["standard_context_radius"], 5)
        self.assertEqual(
            retrieval_run.call_args.kwargs["standard_line_reranker_mode"],
            "semantic",
        )
        self.assertEqual(retrieval_run.call_args.kwargs["standard_line_reranker_workers"], 4)


if __name__ == "__main__":
    unittest.main()
