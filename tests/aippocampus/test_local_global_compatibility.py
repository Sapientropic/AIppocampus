from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]

def _compat_module() -> ModuleType:
    try:
        return importlib.import_module(
            "aippocampus_runtime.navigation.local_global_compatibility"
        )
    except ModuleNotFoundError as exc:
        raise AssertionError("missing local/global compatibility helper") from exc

def _source_shape_section(
    case_id: str,
    *,
    scope: str,
    source_id: str = "issue:#1551",
    topic_epoch: str = "2026w25",
    **updates: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "case_id": case_id,
        "kind": "memory_packet",
        "scope": scope,
        "source_ids": [source_id] if source_id else [],
        "topic_epoch": topic_epoch,
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "source_coverage_time": {
            "start": "2026-06-15T00:00:00Z",
            "end": "2026-06-15T01:00:00Z",
        },
    }
    payload.update(updates)
    return payload

class LocalGlobalCompatibilityTests(unittest.TestCase):
    def test_fixture_covers_glue_partial_obstruction_and_blocked_boundaries(self) -> None:
        compat = _compat_module()
        report = compat.build_local_global_compatibility_report()
        by_case = {item["case_id"]: item for item in report["compatibility_rows"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["kind"], "aippocampus_local_global_compatibility_report")
        self.assertEqual(report["runtime_boundary"], "explain_deepen_or_campus_first")
        self.assertFalse(report["default_foreground"])
        self.assertEqual(report["claim_permission"], "navigation_only_not_fact")
        self.assertEqual(report["authority_level"], "navigation_only")
        self.assertEqual(report["metrics"]["glued_route_count"], 1)
        self.assertEqual(report["metrics"]["partial_glue_count"], 2)
        self.assertEqual(report["metrics"]["obstruction_count"], 6)
        self.assertEqual(report["metrics"]["blocked_boundary_count"], 2)
        self.assertEqual(report["metrics"]["authority_upgrade_blocked_count"], 1)
        self.assertEqual(report["metrics"]["claim_permission_upgrade_count"], 0)
        self.assertEqual(report["metrics"]["foreground_projection_count"], 0)
        self.assertEqual(report["metrics"]["useful_obstruction_later_used_count"], 1)
        self.assertEqual(report["metrics"]["false_glue_regression_count"], 1)
        self.assertEqual(report["metrics"]["ambiguous_correlation_only_count"], 1)

        self.assertEqual(by_case["successful_macro_telepathy_glue"]["result"], "glued_route")
        self.assertEqual(by_case["dream_topology_partial_glue"]["result"], "partial_glue")
        self.assertEqual(by_case["stale_topology_obstruction"]["result"], "obstruction")
        self.assertEqual(by_case["privacy_blocked_boundary"]["result"], "blocked_boundary")
        self.assertEqual(by_case["authority_escalation_attempt"]["result"], "blocked_boundary")
        self.assertEqual(by_case["shared_vocabulary_only"]["result"], "obstruction")
        self.assertEqual(
            by_case["broad_obstruction_with_narrowed_glue"]["restriction_narrowing"][
                "narrowed_result"
            ],
            "glued_route",
        )

        for row in report["compatibility_rows"]:
            self.assertEqual(row["claim_permission"], "navigation_only_not_fact")
            self.assertEqual(row["authority_level"], "navigation_only")
            self.assertTrue(row["source_reopen_required_before_claim"])
            self.assertFalse(row["foreground_projection_allowed"])
            self.assertTrue(row["glue_never_upgrades_authority"])
            self.assertTrue(row["failed_glue_is_obstruction_not_assignment"])
            self.assertIn("obstruction_kind", row)

    def test_overlap_basis_requires_source_or_scope_not_shared_vocabulary(self) -> None:
        compat = _compat_module()
        row = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "vocab_memory",
                    "kind": "memory_packet",
                    "scope": "project:AIppocampus",
                    "route_topic": "dream topology bridge",
                    "source_ids": [],
                    "authority_level": "navigation_only",
                },
                {
                    "case_id": "vocab_dream",
                    "kind": "dream_topology_candidate",
                    "scope": "project:Different",
                    "route_topic": "dream topology bridge",
                    "source_anchors": [],
                    "authority": "dream_synthesized_candidate_not_fact",
                },
            ],
            case_id="shared_words_without_source_scope",
        )

        self.assertEqual(row["result"], "obstruction")
        self.assertIn("shared_vocabulary_without_source_scope_support", row["reason_codes"])
        self.assertFalse(row["overlap_basis"]["shared_vocabulary_counts_as_overlap"])
        self.assertEqual(row["overlap_basis"]["source_overlap_count"], 0)
        self.assertFalse(row["overlap_basis"]["scope_overlap"])

    def test_typed_section_restriction_and_time_window_contract(self) -> None:
        compat = _compat_module()
        row = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "macro_local",
                    "kind": "macro_router_context",
                    "scope": "project:AIppocampus#thread:alpha",
                    "restriction_path": [
                        "project:AIppocampus",
                        "project:AIppocampus#thread_family:runtime",
                        "project:AIppocampus#thread:alpha",
                    ],
                    "source_ids": ["src:shared"],
                    "section_time_window": {
                        "start": "2026-06-13T00:00:00Z",
                        "end": "2026-06-13T01:00:00Z",
                    },
                    "created_at": "2026-06-13T01:05:00Z",
                    "valid_until": "2026-06-14T00:00:00Z",
                    "claim_permission": "navigation_only_not_fact",
                    "requested_claim_permission": "source_open",
                },
                {
                    "case_id": "dream_local",
                    "kind": "dream_topology_candidate",
                    "scope": "project:AIppocampus#thread:alpha",
                    "restriction_path": [
                        "project:AIppocampus",
                        "project:AIppocampus#thread_family:runtime",
                        "project:AIppocampus#thread:alpha",
                    ],
                    "source_ids": ["src:shared"],
                    "source_coverage_time": {
                        "start": "2026-06-13T02:00:00Z",
                        "end": "2026-06-13T03:00:00Z",
                    },
                    "packet_created_at": "2026-06-13T03:05:00Z",
                },
            ],
            case_id="typed_section_time_mismatch",
        )

        section = row["section_contracts"][0]
        self.assertEqual(section["section_contract_version"], 1)
        self.assertEqual(
            section["restriction_path"],
            [
                "project:AIppocampus",
                "project:AIppocampus#thread_family:runtime",
                "project:AIppocampus#thread:alpha",
            ],
        )
        self.assertEqual(section["time_semantics"]["source_coverage_time"]["start"], "2026-06-13T00:00:00Z")
        self.assertEqual(section["time_semantics"]["packet_created_at"], "2026-06-13T01:05:00Z")
        self.assertFalse(row["overlap_basis"]["source_coverage_time_overlap"])
        self.assertEqual(row["result"], "blocked_boundary")
        self.assertIn("authority_or_claim_permission_upgrade_attempt", row["reason_codes"])
        self.assertTrue(row["restriction_policy"]["transitive"])
        self.assertFalse(row["restriction_policy"]["may_raise_authority"])
        self.assertFalse(row["restriction_policy"]["may_raise_claim_permission"])

    def test_time_window_mismatch_blocks_otherwise_matching_sections(self) -> None:
        compat = _compat_module()
        row = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "old",
                    "kind": "memory_packet",
                    "scope": "project:AIppocampus#thread:alpha",
                    "source_ids": ["src:shared"],
                    "section_time_window": {
                        "start": "2026-06-13T00:00:00Z",
                        "end": "2026-06-13T01:00:00Z",
                    },
                },
                {
                    "case_id": "new",
                    "kind": "macro_router_context",
                    "scope": "project:AIppocampus#thread:alpha",
                    "source_ids": ["src:shared"],
                    "source_coverage_time": {
                        "start": "2026-06-14T00:00:00Z",
                        "end": "2026-06-14T01:00:00Z",
                    },
                },
            ],
            case_id="time_window_mismatch",
        )

        self.assertEqual(row["result"], "obstruction")
        self.assertEqual(row["obstruction_kind"], "time_window_mismatch")
        self.assertIn("source_coverage_time_mismatch_blocks_glue", row["reason_codes"])

    def test_restriction_narrowing_records_local_glue_without_broad_overclaim(self) -> None:
        compat = _compat_module()
        narrowed = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "dream_broad",
                    "kind": "dream_topology_candidate",
                    "scope": "project:AIppocampus#area:dream",
                    "restriction_path": [
                        "project:AIppocampus",
                        "project:AIppocampus#thread_family:runtime",
                    ],
                    "source_ids": ["src:shared"],
                },
                {
                    "case_id": "macro_broad",
                    "kind": "macro_router_context",
                    "scope": "project:AIppocampus#area:macro",
                    "restriction_path": [
                        "project:AIppocampus",
                        "project:AIppocampus#thread_family:runtime",
                    ],
                    "source_ids": ["src:shared"],
                },
            ],
            case_id="narrowed_glue",
        )
        failed = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "a",
                    "kind": "memory_packet",
                    "scope": "project:AIppocampus#area:a",
                    "restriction_path": ["project:AIppocampus#area:a"],
                    "source_ids": ["src:a"],
                },
                {
                    "case_id": "b",
                    "kind": "macro_router_context",
                    "scope": "project:AIppocampus#area:b",
                    "restriction_path": ["project:AIppocampus#area:b"],
                    "source_ids": ["src:b"],
                },
            ],
            case_id="narrowing_failed",
        )

        self.assertEqual(narrowed["result"], "partial_glue")
        self.assertEqual(narrowed["restriction_narrowing"]["broad_result"], "obstruction")
        self.assertEqual(narrowed["restriction_narrowing"]["narrowed_result"], "glued_route")
        self.assertEqual(
            narrowed["restriction_narrowing"]["narrowed_scope"],
            "project:AIppocampus#thread_family:runtime",
        )
        self.assertFalse(narrowed["restriction_narrowing"]["raises_authority"])
        self.assertFalse(narrowed["restriction_narrowing"]["raises_claim_permission"])
        self.assertEqual(failed["restriction_narrowing"]["narrowed_result"], "not_glued")
        self.assertIn("no_safe_common_restriction_scope", failed["reason_codes"])

    def test_topology_shape_and_obstruction_kind_are_separate_axes(self) -> None:
        compat = _compat_module()
        stale = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "stale_cut",
                    "kind": "dream_topology_candidate",
                    "scope": "project:AIppocampus#thread:alpha",
                    "shape": "cut_point",
                    "source_ids": ["src:shared"],
                    "status": "stale",
                },
                {
                    "case_id": "memory",
                    "kind": "memory_packet",
                    "scope": "project:AIppocampus#thread:alpha",
                    "shape": "cut_point",
                    "source_ids": ["src:shared"],
                },
            ],
            case_id="stale_cut_point",
        )
        missing_middle = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "missing_cut",
                    "kind": "dream_topology_candidate",
                    "scope": "project:AIppocampus#thread:alpha",
                    "shape": "cut_point",
                    "source_ids": [],
                },
                {
                    "case_id": "memory",
                    "kind": "memory_packet",
                    "scope": "project:Different#thread:beta",
                    "shape": "cut_point",
                    "source_ids": [],
                },
            ],
            case_id="missing_cut_point",
        )

        self.assertEqual(stale["topology_shape"], "cut_point")
        self.assertEqual(missing_middle["topology_shape"], "cut_point")
        self.assertEqual(stale["obstruction_kind"], "stale_boundary")
        self.assertEqual(missing_middle["obstruction_kind"], "missing_middle")

    def test_adjudicated_metric_report_separates_lift_from_correlation(self) -> None:
        compat = _compat_module()
        report = compat.build_local_global_adjudication_report(
            [
                {"diagnostic_result": "obstruction", "adjudication_label": "useful_obstruction"},
                {"diagnostic_result": "glued_route", "adjudication_label": "false_glue"},
                {"diagnostic_result": "obstruction", "adjudication_label": "no_help"},
                {"diagnostic_result": "partial_glue", "adjudication_label": "ambiguous_correlation"},
            ]
        )

        self.assertEqual(report["kind"], "aippocampus_local_global_adjudication_report")
        self.assertEqual(report["metrics"]["useful_obstruction_later_used_count"], 1)
        self.assertEqual(report["metrics"]["false_glue_regression_count"], 1)
        self.assertEqual(report["metrics"]["no_help_count"], 1)
        self.assertEqual(report["metrics"]["ambiguous_correlation_only_count"], 1)
        self.assertFalse(report["claims"]["live_product_lift_claimed"])

    def test_shi_ying_restriction_edges_stay_v0_navigation_only(self) -> None:
        compat = _compat_module()
        report = compat.build_local_global_compatibility_report()
        row = compat.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "shi",
                    "kind": "macro_router_context",
                    "scope": "project:AIppocampus#thread:alpha",
                    "source_ids": ["src:shared"],
                    "relation_position": {
                        "situation_role": "世",
                        "current_agent_default_role": "应",
                    },
                },
                {
                    "case_id": "ying",
                    "kind": "telepathy_coordination_packet",
                    "scope": "project:AIppocampus#thread:alpha",
                    "source_ids": ["src:shared"],
                    "relation_position": {"handoff_role": "应"},
                },
            ],
            case_id="shi_ying_v0",
        )

        self.assertEqual(
            report["contract"]["shi_ying_restriction_edge_policy"],
            "v0_project_scoped_navigation_hint",
        )
        self.assertIn("shi_ying_v0_project_role_hint", row["restriction_edges"])
        self.assertFalse(row["restriction_policy"]["classical_bagua_positions_enabled"])
        self.assertFalse(row["restriction_policy"]["may_change_source_truth"])

    def test_scope_equivalence_glues_explicit_aliases_with_distinct_reason_code(self) -> None:
        compat = _compat_module()
        result = compat.evaluate_local_global_compatibility(
            [
                _source_shape_section(
                    "canonical",
                    scope="project:AIppocampus#canonical:runtime",
                    scope_aliases=["project:AIppocampus#thread_family:runtime"],
                ),
                _source_shape_section(
                    "display_label",
                    scope="Runtime continuity thread family",
                    canonical_scope_id="project:AIppocampus#canonical:runtime",
                ),
            ],
            case_id="explicit_scope_alias",
        )

        self.assertEqual(result["result"], "glued_route")
        self.assertIn("normalized_equivalent_scope_match", result["reason_codes"])
        self.assertEqual(result["overlap_basis"]["scope_match_kind"], "equivalent")
        self.assertFalse(result["overlap_basis"]["shared_vocabulary_counts_as_overlap"])
        self.assertEqual(result["authority_level"], "navigation_only")
        self.assertEqual(result["claim_permission"], "navigation_only_not_fact")

    def test_shared_vocabulary_still_obstructs_without_source_or_scope_equivalence(self) -> None:
        compat = _compat_module()
        result = compat.evaluate_local_global_compatibility(
            [
                _source_shape_section(
                    "vocab_a",
                    scope="project:AIppocampus#area:a",
                    source_id="",
                    route_topic="macro topology navigation",
                ),
                _source_shape_section(
                    "vocab_b",
                    scope="project:AIppocampus#area:b",
                    source_id="",
                    route_topic="macro topology navigation",
                ),
            ],
            case_id="shared_vocab_no_glue",
        )

        self.assertEqual(result["result"], "obstruction")
        self.assertIn("shared_vocabulary_without_source_scope_support", result["reason_codes"])
        self.assertEqual(result["overlap_basis"]["scope_match_kind"], "none")

    def test_private_or_stale_sections_are_not_rescued_by_scope_normalization(self) -> None:
        compat = _compat_module()
        private = compat.evaluate_local_global_compatibility(
            [
                _source_shape_section(
                    "private",
                    scope="private-runtime",
                    canonical_scope_id="project:AIppocampus#canonical:runtime",
                    privacy_domain="private",
                ),
                _source_shape_section(
                    "public",
                    scope="project:AIppocampus#display:runtime",
                    canonical_scope_id="project:AIppocampus#canonical:runtime",
                ),
            ],
            case_id="private_alias_not_rescued",
        )
        stale = compat.evaluate_local_global_compatibility(
            [
                _source_shape_section(
                    "stale",
                    scope="old-runtime",
                    canonical_scope_id="project:AIppocampus#canonical:runtime",
                    status="stale",
                ),
                _source_shape_section(
                    "current",
                    scope="new-runtime",
                    canonical_scope_id="project:AIppocampus#canonical:runtime",
                ),
            ],
            case_id="stale_alias_not_rescued",
        )

        self.assertEqual(private["result"], "blocked_boundary")
        self.assertEqual(private["obstruction_kind"], "privacy_boundary")
        self.assertEqual(stale["result"], "obstruction")
        self.assertEqual(stale["obstruction_kind"], "stale_boundary")
        self.assertEqual(private["overlap_basis"]["scope_match_kind"], "equivalent")
        self.assertEqual(stale["overlap_basis"]["scope_match_kind"], "equivalent")

    def test_live_local_global_producer_feeds_source_shape_and_degrades_on_obstruction(self) -> None:
        from aippocampus_runtime.navigation.local_global_source_shape import (
            build_local_global_source_shape_descriptor,
        )

        descriptor = build_local_global_source_shape_descriptor(
            [
                _source_shape_section("good_a", scope="project:AIppocampus#issue:1549"),
                _source_shape_section("good_b", scope="project:AIppocampus#issue:1549"),
            ],
            producer="local_global_route_bundle",
            created_at="2026-06-15T01:02:00Z",
        )
        obstructed = build_local_global_source_shape_descriptor(
            [
                _source_shape_section(
                    "cut_a",
                    scope="project:AIppocampus#thread:a",
                    source_id="",
                    route_topic="source shape compatibility",
                ),
                _source_shape_section(
                    "cut_b",
                    scope="project:AIppocampus#thread:b",
                    source_id="",
                    route_topic="source shape compatibility",
                ),
            ],
            producer="local_global_route_bundle",
            created_at="2026-06-15T01:02:00Z",
        )

        self.assertTrue(descriptor["compatibility_diagnostics_present"])
        self.assertEqual(descriptor["descriptor_state"], "complete")
        self.assertTrue(descriptor["projection"]["projection_allowed"])
        self.assertTrue(obstructed["compatibility_diagnostics_present"])
        self.assertEqual(obstructed["descriptor_state"], "diagnostic_only")
        self.assertEqual(obstructed["dominant_guard"]["guard"], "source_availability")
        self.assertEqual(obstructed["signals"]["compatibility"]["status"], "obstruction")
        self.assertEqual(obstructed["authority_level"], "direction_only")
        self.assertEqual(obstructed["claim_permission"], "none")

    def test_fixture_links_macro_dream_telepathy_aippo_and_topology_surfaces(self) -> None:
        compat = _compat_module()
        report = compat.build_local_global_compatibility_report()

        self.assertTrue(report["contract"]["macro_yi_fixture_connected"])
        self.assertTrue(report["contract"]["dream_topology_fixture_connected"])
        self.assertTrue(report["contract"]["telepathy_fixture_connected"])
        self.assertTrue(report["contract"]["aippo_fixture_connected"])
        self.assertTrue(report["contract"]["packet_topology_fixture_connected"])
        self.assertIn("macro_router_context", report["connected_section_kinds"])
        self.assertIn("dream_topology_candidate", report["connected_section_kinds"])
        self.assertIn("telepathy_coordination_packet", report["connected_section_kinds"])
        self.assertIn("aippocampus_aippo_activation_packet", report["connected_section_kinds"])
        self.assertIn("aippocampus_packet_topology_row", report["connected_section_kinds"])

    def test_cli_sanitizes_private_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "local-global-private.json"
            rows = [
                {
                    "case_id": "private_route",
                    "kind": "memory_packet",
                    "scope": str(root / "private-rollout.jsonl"),
                    "source_ids": ["source://private/raw-handle"],
                    "raw_source_text": "PRIVATE_LOCAL_GLOBAL_TEXT must not leave diagnostics",
                    "claim_permission": "source_open",
                    "privacy_domain": "private",
                },
                {
                    "case_id": "public_route",
                    "kind": "telepathy_coordination_packet",
                    "scope": "project:AIppocampus",
                    "source_ids": ["source://private/raw-handle"],
                    "boundary_flags": ["no_private_source"],
                    "claim_permission": "navigation_only_not_fact",
                    "privacy_domain": "public",
                },
            ]
            input_path.write_text(json.dumps(rows), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.navigation.local_global_compatibility",
                    "--input",
                    str(input_path),
                    "--json",
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=REPO_ROOT,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["safety_gate_ok"])
        self.assertEqual(payload["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertEqual(payload["metrics"]["blocked_boundary_count"], 1)
        self.assertNotIn("PRIVATE_LOCAL_GLOBAL_TEXT", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)

if __name__ == "__main__":
    unittest.main()
