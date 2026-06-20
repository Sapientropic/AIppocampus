from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
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

import benchmark_family_promotion_candidates as family_promotion  # noqa: E402
import benchmark_suite as suite  # noqa: E402
from shared.benchmark_outcome_router import (  # noqa: E402
    benchmark_outcome_digest,
    build_benchmark_issue_drafts,
    build_benchmark_outcome_card,
)
from shared.benchmark_report_contract import benchmark_report_contract_lint  # noqa: E402
from shared.benchmark_suite_quality import track_quality_state  # noqa: E402


def fake_gate_payload() -> dict:
    return {
        "kind": "aippocampus_memory_decision_gate_benchmark",
        "ok": True,
        "metrics": {
            "total_cases": 2,
            "accuracy": 1.0,
            "macro_f1": 1.0,
            "rate_estimates": {
                "accuracy": {
                    "numerator": 2,
                    "denominator": 2,
                    "point_estimate": 1.0,
                    "confidence_interval": {"method": "wilson_score"},
                }
            },
        },
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
                "rate_estimates": {
                    "hit_rate_top_k": {
                        "numerator": 2,
                        "denominator": 2,
                        "confidence_interval": {"method": "wilson_score"},
                    }
                },
            },
            "source_evidence": {
                "kind": "selected_source_evidence_recall_eval",
                "ok": ok,
                "status": "sufficient" if ok else "insufficient_recall_hits",
                "case_count": 2,
                "top_k_hit_rate": 0.5,
                "rate_estimates": {
                    "top_k_hit_rate": {
                        "numerator": 1,
                        "denominator": 2,
                        "confidence_interval": {"method": "wilson_score"},
                    }
                },
            },
        },
        "cases": {"fts5": [{"case_id": "fts-a"}], "source_evidence": []},
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
            "case_selection_filters_active": True,
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
            "case_selection_filters_active": True,
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
                "gate,scope",
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
        self.assertEqual(config.live_semantic_workers, ("gate", "scope"))
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

    def test_profile_ladder_is_exposed_in_cli_help(self) -> None:
        help_text = suite.build_arg_parser().format_help()

        self.assertIn("Task-first benchmark suite", help_text)
        self.assertIn("Ordinary PR confidence", help_text)
        self.assertIn("--tier benchmark-smoke --benchmark-suite-profile public-fast", help_text)
        self.assertIn("Public evidence update", help_text)
        self.assertIn("--profile release-evidence --output", help_text)
        self.assertIn("--cite-summary", help_text)
        self.assertIn("Profile cards:", help_text)
        self.assertIn("ci-deterministic", help_text)
        self.assertIn("local-calibration", help_text)
        self.assertIn("live-semantic", help_text)
        self.assertIn("private-full", help_text)
        self.assertIn("release-evidence", help_text)
        self.assertIn(
            "memory-decision-benchmark-plan.md#benchmark-suite-profiles",
            help_text,
        )
        self.assertIn("BenchmarkSuiteConfig", help_text)
        self.assertIn("run_benchmark_suite_with_config", help_text)

    def test_claimability_summary_is_compact_and_claim_bounded(self) -> None:
        payload = {
            "ok": False,
            "status": "needs-review",
            "quality_gate_ok": False,
            "track_statuses": {"gate_decision": "pass"},
            "profile_metadata": {"selected_profile": {"name": "public-fast"}},
            "cannot_claim": ["public_fast_profile_track_b_quality"],
        }

        summary = suite.claimability_summary(payload)

        self.assertEqual(
            summary["kind"],
            "aippocampus_benchmark_suite_claimability_summary",
        )
        self.assertFalse(summary["can_cite"])
        self.assertEqual(summary["cite_status"], "do_not_cite_as_quality_proof")
        self.assertEqual(summary["cannot_claim_count"], 1)
        self.assertIn("release-evidence", summary["best_next_benchmark"])

    def test_benchmark_outcome_card_routes_claim_issue_adoption_and_no_action(self) -> None:
        public_quality_report = {
            "kind": "aippocampus_public_quality_report",
            "ok": True,
            "status": "quality_gate_passed",
            "benchmark_maturity_level": "behavior_run",
            "measurement_origin": "live_agent_observed",
            "observed_agent_behavior": True,
            "contract_gate_ok": True,
            "quality_gate_ok": True,
            "public_quality_gate_ok": True,
            "runtime_policy_adoption_gate_ok": True,
            "decision_impact": "default_adoption",
            "privacy_boundary": {"raw_text_emitted": False},
            "case_count": 3,
            "metrics": {
                "case_count": 3,
                "accuracy": {"numerator": 3, "denominator": 3, "rate": 1.0},
            },
            "cannot_claim": ["unbounded_default_quality"],
            "no_action_reason": "public quality gate has no owner follow-up",
            "supports": ["bounded public quality claim"],
        }
        diagnostic_report = {
            **public_quality_report,
            "kind": "aippocampus_diagnostic_report",
            "public_quality_gate_ok": False,
            "runtime_policy_adoption_gate_ok": None,
            "decision_impact": "diagnostic_only",
            "quality_gate_kind": "diagnostic_curve",
            "cannot_claim": ["default_adoption"],
        }
        issue_report = {
            **diagnostic_report,
            "kind": "aippocampus_issue_action_report",
            "review_next_actions": [
                {
                    "id": "open_owner_gap",
                    "label": "Open owner gap",
                    "reason": "Default adoption is blocked by missing owner route.",
                    "owner_path": "benchmarks/aippocampus/benchmark_suite.py",
                    "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
                    "issue_state": "open",
                    "command": "gh issue view 2100 --comments",
                }
            ],
        }
        no_action_report = {
            **diagnostic_report,
            "kind": "aippocampus_no_action_report",
            "no_open_followup_reason": "dated diagnostic report only",
        }

        promoted = build_benchmark_outcome_card(public_quality_report, report_path="reports/public.json")
        diagnostic = build_benchmark_outcome_card(diagnostic_report, report_path="reports/diag.json")
        issue_card = build_benchmark_outcome_card(issue_report, report_path="reports/issue.json")
        no_action = build_benchmark_outcome_card(no_action_report, report_path="reports/noop.json")
        digest = benchmark_outcome_digest([promoted, diagnostic, issue_card, no_action])

        self.assertEqual(promoted["claim_action"]["decision"], "update_current_claims")
        self.assertEqual(promoted["adoption_action"]["decision"], "allow_default_adoption")
        self.assertEqual(diagnostic["claim_action"]["decision"], "dated_report_only")
        self.assertEqual(diagnostic["adoption_action"]["decision"], "diagnostic_only")
        self.assertEqual(issue_card["owner_action"]["decision"], "open_or_update_issue")
        self.assertEqual(no_action["owner_action"]["decision"], "explicit_no_action")
        self.assertEqual(digest["counts"]["public_quality_promoted"], 1)
        self.assertEqual(digest["counts"]["diagnostic_only"], 3)
        self.assertEqual(digest["counts"]["owner_action"], 1)

    def test_benchmark_issue_drafts_skip_no_action_and_group_duplicate_owner_routes(
        self,
    ) -> None:
        action = {
            "id": "review_default_adoption_blocker",
            "label": "Review default adoption blocker",
            "reason": "Default adoption is blocked until the owner route is verified.",
            "owner_path": "benchmarks/aippocampus/benchmark_suite.py",
            "doc_path": str(Path("C:/private/operator-note.md")),
            "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
            "issue_state": "open",
            "command": "gh issue view 2100 --comments",
        }
        report = {
            "kind": "aippocampus_issue_action_report",
            "ok": True,
            "status": "diagnostic_only",
            "benchmark_maturity_level": "diagnostic_suite",
            "measurement_origin": "scripted_proxy",
            "observed_agent_behavior": False,
            "contract_gate_ok": True,
            "quality_gate_ok": False,
            "public_quality_gate_ok": False,
            "default_adoption_gate_ok": False,
            "decision_impact": "diagnostic_only",
            "privacy_boundary": {"raw_text_emitted": False},
            "case_count": 2,
            "cannot_claim": ["default_adoption"],
            "supports": ["owner action routing"],
            "review_next_actions": [action],
        }
        no_action_report = {
            **report,
            "review_next_actions": [],
            "no_open_followup_reason": "diagnostic-only report already archived",
        }

        drafts = build_benchmark_issue_drafts(
            [
                ("reports/one.json", report),
                ("reports/two.json", {**report, "measured_result": "same owner"}),
                ("reports/noop.json", no_action_report),
            ]
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["title"], "Review default adoption blocker")
        self.assertEqual(
            drafts[0]["source_report_paths"],
            ["reports/one.json", "reports/two.json"],
        )
        self.assertEqual(drafts[0]["action"]["doc_path"], "operator-note.md")
        self.assertNotIn("command", drafts[0]["action"])
        self.assertIn("Source report", drafts[0]["body"])
        self.assertIn("Do not use diagnostic-only evidence", drafts[0]["body"])

    def test_benchmark_outcome_tool_emits_issue_drafts_json(self) -> None:
        report = {
            "kind": "aippocampus_issue_action_report",
            "ok": True,
            "status": "diagnostic_only",
            "benchmark_maturity_level": "diagnostic_suite",
            "measurement_origin": "scripted_proxy",
            "observed_agent_behavior": False,
            "contract_gate_ok": True,
            "quality_gate_ok": False,
            "public_quality_gate_ok": False,
            "default_adoption_gate_ok": False,
            "decision_impact": "diagnostic_only",
            "privacy_boundary": {"raw_text_emitted": False},
            "case_count": 1,
            "cannot_claim": ["default_adoption"],
            "supports": ["owner action routing"],
            "issue_actions": [
                {
                    "label": "Open benchmark blocker",
                    "reason": "Owner route exists and needs implementation.",
                    "owner_path": "benchmarks/aippocampus/benchmark_suite.py",
                    "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
                    "issue_state": "open",
                    "command": "gh issue view 2100 --comments",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "aippocampus" / "benchmark_outcomes.py"),
                    "--report",
                    str(path),
                    "--issue-drafts",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["draft_count"], 1)
        self.assertEqual(payload["drafts"][0]["title"], "Open benchmark blocker")

    def test_summary_json_with_output_does_not_duplicate_full_report_stdout(self) -> None:
        payload = {
            "kind": "aippocampus_benchmark_suite",
            "schema_version": 1,
            "ok": False,
            "status": "needs-review",
            "quality_gate_ok": False,
            "benchmark_maturity_level": "diagnostic",
            "contract_gate_ok": True,
            "public_quality_gate_ok": False,
            "observed_agent_behavior": False,
            "measurement_origin": "deterministic_contract",
            "privacy_boundary": "public_safe",
            "case_count": 1,
            "track_statuses": {"gate_decision": "sufficient"},
            "profile_metadata": {"selected_profile": {"name": "public-fast"}},
            "cannot_claim": ["public_fast_profile_track_b_quality"],
            "review_next_actions": [
                {
                    "id": "escalate_release_evidence",
                    "label": "Escalate release evidence",
                    "owner_path": "benchmarks/aippocampus/benchmark_suite.py",
                    "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
                    "command": "gh issue view 2100 --comments",
                }
            ],
            "tracks": {"large_track": {"cases": ["x" * 10_000]}},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "full-report.json"
            argv = [
                "benchmark_suite.py",
                "--profile",
                "public-fast",
                "--output",
                str(output),
                "--summary-json",
            ]
            with patch.object(sys, "argv", argv):
                with patch.object(
                    suite,
                    "run_benchmark_suite_with_config",
                    return_value=payload,
                ):
                    with patch("sys.stdout", new_callable=StringIO) as stdout:
                        code = suite.main()

            summary = json.loads(stdout.getvalue())
            full_report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(summary["kind"], "aippocampus_benchmark_suite_cli_summary")
        self.assertEqual(summary["full_report_route"], str(output))
        self.assertEqual(summary["cannot_claim_count"], 1)
        self.assertEqual(summary["followup_action_count"], 1)
        self.assertEqual(summary["owner_route_count"], 1)
        self.assertEqual(summary["no_action_reason_count"], 0)
        self.assertEqual(
            summary["outcome_digest"]["kind"],
            "aippocampus_benchmark_outcome_digest",
        )
        self.assertNotIn("tracks", summary)
        self.assertIn("tracks", full_report)

    def test_track_b_case_controls_reject_zero_values(self) -> None:
        parsers = (
            ("direct", suite.retrieval_benchmark.build_arg_parser),
            ("suite", suite.build_arg_parser),
        )
        for option in (
            "--fts5-cases",
            "--fts5-min-cases",
            "--source-max-cases",
            "--source-min-cases",
        ):
            for parser_name, parser_factory in parsers:
                with self.subTest(parser=parser_name, option=option):
                    with patch("sys.stderr", new_callable=StringIO) as stderr:
                        with self.assertRaises(SystemExit) as raised:
                            parser_factory().parse_args([option, "0"])

                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn(
                        f"{option} must be a positive integer",
                        stderr.getvalue(),
                    )
                    self.assertIn("--only-standard-public", stderr.getvalue())

    def test_release_evidence_profile_stays_public_safe_by_default(self) -> None:
        parser = suite.build_arg_parser()
        args = parser.parse_args(["--profile", "release-evidence"])

        config = suite.benchmark_suite_config_from_args(args)

        self.assertEqual(config.profile, "release-evidence")
        self.assertFalse(config.include_private_text)
        self.assertFalse(config.include_live_semantic)
        self.assertFalse(config.include_sharegpt_public_track_b)
        self.assertFalse(config.include_standard_public_track_b)
        self.assertTrue(config.include_track_b)
        self.assertTrue(config.include_deterministic_source_labels)

    def test_release_evidence_profile_allows_explicit_public_adapter_opt_in(self) -> None:
        parser = suite.build_arg_parser()
        args = parser.parse_args(
            [
                "--profile",
                "release-evidence",
                "--include-standard-public-track-b",
                "--include-private-text",
                "--include-live-semantic",
            ]
        )

        config = suite.benchmark_suite_config_from_args(args)

        self.assertEqual(config.profile, "release-evidence")
        self.assertTrue(config.include_standard_public_track_b)
        self.assertFalse(config.include_private_text)
        self.assertFalse(config.include_live_semantic)

    def test_suite_report_includes_profile_and_threshold_metadata(self) -> None:
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
        ):
            payload = suite.run_benchmark_suite(profile="public-fast")

        profile_metadata = payload["profile_metadata"]
        self.assertEqual(profile_metadata["selected_profile"]["name"], "public-fast")
        self.assertEqual(
            profile_metadata["docs"],
            "docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md"
            "#benchmark-suite-profiles",
        )
        self.assertIn(
            "ci-deterministic",
            {profile["name"] for profile in profile_metadata["profile_ladder"]},
        )
        self.assertIn("public_fast_profile_track_b_quality", payload["cannot_claim"])
        ladder_by_name = {
            profile["name"]: profile for profile in profile_metadata["profile_ladder"]
        }
        self.assertNotIn(
            "default_cannot_claim",
            ladder_by_name["ci-deterministic"],
        )
        self.assertEqual(
            ladder_by_name["ci-deterministic"]["default_cannot_claim_count"],
            3,
        )
        self.assertEqual(
            ladder_by_name["ci-deterministic"]["claim_boundary_ref"],
            profile_metadata["docs"],
        )
        self.assertIn(
            "docs/architecture/runtime/schema-field-profiles.md#cannot-claim",
            payload["claim_boundary_policy"]["canonical_rule"],
        )
        self.assertIn(
            "default_cannot_claim",
            profile_metadata["selected_profile"],
        )

        threshold_metadata = payload["threshold_metadata"]
        self.assertEqual(
            threshold_metadata["source_min_hit_rate"]["value"],
            payload["config"]["source_min_hit_rate"],
        )
        self.assertIn("rationale", threshold_metadata["source_min_hit_rate"])
        self.assertIn(
            "claim_boundary",
            threshold_metadata["standard_min_session_hit_rate"],
        )
        self.assertTrue(payload["privacy_boundary"]["case_selection_filters_active"])
        self.assertEqual(
            payload["privacy_boundary"]["case_selection_filter_policy"],
            "aippocampus_runtime.safety.benchmark_sensitive_text_policy",
        )
        self.assertEqual(
            payload["privacy_boundary"]["include_private_text_scope"],
            "local_debug_only",
        )

    def test_suite_report_preserves_track_local_cannot_claim_sources(self) -> None:
        gate_payload = fake_gate_payload()
        gate_payload["cannot_claim"] = [
            "real_history_gate_quality",
            "payload_fidelity",
        ]
        with (
            patch.object(
                suite.gate_benchmark,
                "run_benchmark",
                return_value=gate_payload,
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
        ):
            payload = suite.run_benchmark_suite(profile="public-fast")

        self.assertIn("payload_fidelity", payload["cannot_claim"])
        self.assertEqual(
            payload["cannot_claim_by_track"]["gate_decision"],
            ["payload_fidelity", "real_history_gate_quality"],
        )
        self.assertEqual(
            payload["cannot_claim_by_track"]["payload_fidelity"],
            ["real_history_payload_fidelity"],
        )
        self.assertIn(
            "public_fast_profile_track_b_quality",
            payload["suite_level_cannot_claim"],
        )
        self.assertNotIn("payload_fidelity", payload["suite_level_cannot_claim"])

    def test_suite_does_not_promote_missing_quality_metadata_to_quality_gate(self) -> None:
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
        ):
            payload = suite.run_benchmark_suite(profile="public-fast")

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["runner_ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["claim_quality_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertFalse(payload["public_quality_gate_ok"])
        self.assertEqual(payload["status"], "contract_passed_with_unmatured_tracks")
        self.assertTrue(payload["linter_required_for_public_quality_gate"])
        self.assertTrue(payload["contract_gate_status"]["ok"])
        self.assertIn(
            "does not imply benchmark contract linter",
            payload["contract_gate_status"]["meaning"],
        )
        self.assertEqual(
            payload["machine_summary"]["safe_interpretation"],
            "runner_report_available_but_not_public_quality_support",
        )
        self.assertEqual(
            payload["machine_summary"]["ok_field_meaning"],
            "runner_ok_baseline_report_available",
        )
        self.assertFalse(payload["machine_summary"]["claim_quality_ok"])
        self.assertEqual(
            payload["quality_gate_summary"]["quality_gate_status"],
            "unknown",
        )
        self.assertEqual(
            payload["quality_gate_summary"]["unknown_tracks"],
            ["gate_decision", "payload_fidelity"],
        )
        self.assertEqual(
            payload["quality_gate_summary"]["track_quality_states"]["gate_decision"][
                "metadata_source"
            ],
            "missing_quality_metadata",
        )
        self.assertIn("suite_quality_gate_passed", payload["cannot_claim"])
        self.assertFalse(payload["benchmark_contract_linter_ok"])
        self.assertIn("gate_decision", payload["benchmark_contract_lint"])
        self.assertIn(
            "boundary_only_projection_without_positive_support",
            payload["benchmark_contract_lint"]["gate_decision"]["findings"],
        )
        self.assertIn("benchmark_contract_linter_passed", payload["cannot_claim"])

    def test_benchmark_contract_linter_requires_positive_support_beside_boundaries(self) -> None:
        boundary_only = {
            "benchmark_maturity_level": "diagnostic_proxy",
            "measurement_origin": "scripted_proxy",
            "observed_agent_behavior": False,
            "contract_gate_ok": True,
            "public_quality_gate_ok": False,
            "decision_impact": "diagnostic_only",
            "case_count": 3,
            "privacy_boundary": {"raw_text_emitted": False},
            "cannot_claim": ["live_agent_behavior"],
        }
        useful = {
            **boundary_only,
            "useful_now": ["route narrows source search"],
            "agent_action": "deepen_or_reopen_source",
        }

        rejected = benchmark_report_contract_lint(boundary_only)
        accepted = benchmark_report_contract_lint(useful)

        self.assertFalse(rejected["ok"])
        self.assertTrue(rejected["boundary_only_projection"])
        self.assertIn(
            "boundary_only_projection_without_positive_support",
            rejected["findings"],
        )
        self.assertTrue(accepted["ok"])
        self.assertTrue(accepted["positive_support_present"])

    def test_benchmark_contract_linter_requires_owner_action_for_high_signal_reports(self) -> None:
        high_signal_without_followup = {
            "benchmark_maturity_level": "diagnostic_proxy",
            "measurement_origin": "scripted_proxy",
            "observed_agent_behavior": False,
            "contract_gate_ok": True,
            "public_quality_gate_ok": False,
            "quality_gate_ok": False,
            "decision_impact": "diagnostic_only",
            "case_count": 6,
            "metrics": {
                "case_count": 6,
                "route_count": 6,
                "bounded_count": 5,
                "blocked_count": 1,
                "warning_count": 0,
                "success_rate": 0.8333,
            },
            "privacy_boundary": {"raw_text_emitted": False},
            "supports": ["bounded diagnostic route triage"],
            "cannot_claim": [
                "live_agent_behavior",
                "public_quality_lift",
                "owner_status_closeout",
                "current_issue_route",
            ],
        }
        high_signal_with_followup = {
            **high_signal_without_followup,
            "review_next_actions": [
                {
                    "id": "route_owner_review",
                    "label": "Route owner review",
                    "owner_path": "benchmarks/aippocampus/example.py",
                    "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
                    "command": "python benchmarks/aippocampus/example.py --json",
                }
            ],
        }
        high_signal_with_owner_but_no_command = {
            **high_signal_without_followup,
            "review_next_actions": [
                {
                    "id": "route_owner_review",
                    "label": "Route owner review",
                    "owner_path": "benchmarks/aippocampus/example.py",
                    "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
                }
            ],
        }
        high_signal_historical_no_action = {
            **high_signal_without_followup,
            "no_open_followup_reason": (
                "Historical diagnostic retained as bounded evidence; "
                "docs/evidence/current-claims.md owns current claim posture."
            ),
        }
        high_signal_closed_issue_action = {
            **high_signal_without_followup,
            "review_next_actions": [
                {
                    "id": "closed_owner_review",
                    "label": "Closed owner review",
                    "owner_path": "benchmarks/aippocampus/example.py",
                    "issue_url": "https://github.com/Sapientropic/AIppocampus/issues/2100",
                    "issue_state": "closed_historical",
                    "command": "gh issue view 2100 --comments",
                }
            ],
        }
        high_signal_closed_issue_no_open = {
            **high_signal_closed_issue_action,
            "review_next_actions": [
                {
                    **high_signal_closed_issue_action["review_next_actions"][0],
                    "command": "",
                    "no_open_followup_reason": (
                        "Closed historical owner; current claims own the boundary until a new scoped issue opens."
                    ),
                }
            ],
        }

        rejected = benchmark_report_contract_lint(high_signal_without_followup)
        owner_only = benchmark_report_contract_lint(high_signal_with_owner_but_no_command)
        accepted = benchmark_report_contract_lint(high_signal_with_followup)
        historical = benchmark_report_contract_lint(high_signal_historical_no_action)
        closed_action = benchmark_report_contract_lint(high_signal_closed_issue_action)
        closed_no_open = benchmark_report_contract_lint(high_signal_closed_issue_no_open)

        self.assertFalse(rejected["ok"])
        self.assertIn("cannot_claim_without_followup", rejected["findings"])
        self.assertIn("metrics_without_owner_action", rejected["findings"])
        self.assertEqual(rejected["followup_action_count"], 0)
        self.assertEqual(rejected["owner_route_count"], 0)
        self.assertFalse(owner_only["ok"])
        self.assertIn("cannot_claim_without_followup", owner_only["findings"])
        self.assertEqual(owner_only["followup_action_count"], 0)
        self.assertEqual(owner_only["owner_route_count"], 1)
        self.assertTrue(accepted["ok"], accepted)
        self.assertEqual(accepted["followup_action_count"], 1)
        self.assertEqual(accepted["owner_route_count"], 1)
        self.assertTrue(historical["ok"], historical)
        self.assertEqual(historical["no_action_reason_count"], 1)
        self.assertFalse(closed_action["ok"])
        self.assertIn("closed_issue_without_open_followup", closed_action["findings"])
        self.assertEqual(closed_action["followup_action_count"], 0)
        self.assertEqual(closed_action["closed_historical_owner_route_count"], 1)
        self.assertTrue(closed_no_open["ok"], closed_no_open)
        self.assertEqual(closed_no_open["explicit_no_open_followup_route_count"], 1)
        self.assertEqual(closed_no_open["no_action_reason_count"], 1)

    def test_linter_accepts_bounded_support_fields_without_public_quality_claim(self) -> None:
        bounded = {
            "benchmark_maturity_level": "diagnostic_proxy",
            "measurement_origin": "scripted_proxy",
            "observed_agent_behavior": False,
            "contract_gate_ok": True,
            "public_quality_gate_ok": False,
            "quality_gate_ok": False,
            "decision_impact": "diagnostic_only",
            "metrics": {"case_count": 4},
            "privacy_boundary": {"raw_text_emitted": False},
            "cannot_claim": ["public_quality_lift"],
            "usefulness_metrics": {"positive_case_count": 4, "hinted_positive_count": 4},
            "promotion_gates": {"replay_fixture_gate_ok": True},
        }

        lint = benchmark_report_contract_lint(bounded)

        self.assertTrue(lint["ok"], lint)
        self.assertIn("usefulness_metrics", lint["positive_support_fields"])
        self.assertIn("promotion_gates", lint["positive_support_fields"])

    def test_linter_requires_denominator_math_for_public_quality_claims(self) -> None:
        base = {
            "benchmark_maturity_level": "public_cohort",
            "measurement_origin": "deterministic_contract",
            "observed_agent_behavior": False,
            "contract_gate_ok": True,
            "public_quality_gate_ok": True,
            "quality_gate_ok": True,
            "quality_gate_kind": "public_quality",
            "decision_impact": "not_applicable",
            "privacy_boundary": {"raw_text_emitted": False},
            "cannot_claim": ["live_host_behavior_lift"],
            "supports": ["public cohort route quality"],
        }
        missing_denominator = {**base, "case_count": 3}
        invalid_denominator = {
            **base,
            "case_count": 3,
            "metrics": {"precision": {"numerator": 4, "denominator": 3, "rate": 1.333}},
        }
        valid = {
            **base,
            "metrics": {
                "case_count": 3,
                "precision": {"numerator": 3, "denominator": 3, "rate": 1.0},
            },
        }

        self.assertIn(
            "public_quality_claim_without_reusable_denominator",
            benchmark_report_contract_lint(missing_denominator)["findings"],
        )
        self.assertIn(
            "invalid_rate_denominator_math",
            benchmark_report_contract_lint(invalid_denominator)["findings"],
        )
        self.assertTrue(benchmark_report_contract_lint(valid)["ok"])

    def test_suite_quality_interprets_diagnostic_quality_as_not_public_quality(self) -> None:
        state = track_quality_state(
            "density_curve",
            {
                "ok": True,
                "contract_gate_ok": True,
                "quality_gate_ok": True,
                "public_quality_gate_ok": False,
                "quality_gate_kind": "diagnostic_curve",
                "benchmark_maturity_level": "diagnostic_proxy",
            },
        )

        self.assertFalse(state["quality_gate_ok"])
        self.assertEqual(
            state["quality_gate_status"],
            "diagnostic_passed_not_public_quality",
        )

    def test_family_promotion_candidates_report_satisfies_benchmark_contract_linter(self) -> None:
        report = family_promotion.build_family_promotion_candidate_report()
        lint = benchmark_report_contract_lint(report)

        self.assertTrue(lint["ok"], lint)
        self.assertIn("supports", lint["positive_support_fields"])
        self.assertIn("material_limits", lint["positive_support_fields"])
        self.assertEqual(report["decision_impact"], "diagnostic_only")
        self.assertTrue(report["quality_gate_ok"])
        self.assertTrue(report["public_quality_gate_ok"])
        self.assertEqual(
            report["metrics"]["public_quality_gate_rate"],
            {
                "numerator": 3,
                "denominator": 3,
                "rate": 1.0,
                "unit": "evaluated_public_quality_family",
            },
        )

    def test_suite_report_warns_when_profile_surface_is_narrowed(self) -> None:
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
        ):
            payload = suite.run_benchmark_suite(
                profile="release-evidence",
                include_track_b=False,
            )

        self.assertNotIn("source_evidence_retrieval", payload["tracks"])
        self.assertIn(
            "profile_expected_track_b_but_effective_config_skipped_it",
            payload["claim_surface_warnings"],
        )
        self.assertNotIn(
            "source_evidence_retrieval",
            payload["profile_metadata"]["effective_surface"]["included_tracks"],
        )

    def test_suite_report_marks_optional_public_adapter_opt_in(self) -> None:
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
            ),
        ):
            payload = suite.run_benchmark_suite(
                profile="release-evidence",
                include_standard_public_track_b=True,
            )

        self.assertIn(
            "optional_public_track_b_adapter_enabled",
            payload["claim_surface_warnings"],
        )
        self.assertIn(
            "release_profile_optional_public_corpus_quality_bounded_to_adapter_run",
            payload["cannot_claim"],
        )
        self.assertNotIn(
            "release_profile_optional_public_corpus_quality_without_opt_in",
            payload["cannot_claim"],
        )
        self.assertIn(
            "standard_public_track_b",
            payload["profile_metadata"]["effective_surface"]["optional_surfaces"],
        )

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
        self.assertIn("all_benchmark_quality_targets_met", payload["cannot_claim"])
        self.assertIn(
            "all_benchmark_quality_targets_met",
            payload["suite_level_cannot_claim"],
        )
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

    def test_suite_collects_rate_estimates_for_public_readiness_review(self) -> None:
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
            ),
        ):
            payload = suite.run_benchmark_suite(
                include_deterministic_source_labels=False,
            )

        estimates = payload["rate_estimates"]
        self.assertEqual(estimates["gate_decision.accuracy"]["denominator"], 2)
        self.assertEqual(
            estimates[
                "source_evidence_retrieval.fts5_source_line.hit_rate_top_k"
            ]["confidence_interval"]["method"],
            "wilson_score",
        )
        self.assertEqual(
            estimates[
                "source_evidence_retrieval.source_evidence.top_k_hit_rate"
            ]["numerator"],
            1,
        )

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
        self.assertTrue(
            payload["tracks"]["source_evidence_deterministic_labels"]["selection"][
                "deterministic_label_fallback"
            ]
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
