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
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _compat_module() -> ModuleType:
    try:
        return importlib.import_module(
            "aippocampus_runtime.navigation.local_global_compatibility"
        )
    except ModuleNotFoundError as exc:
        raise AssertionError("missing local/global compatibility helper") from exc


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
        self.assertEqual(report["metrics"]["partial_glue_count"], 1)
        self.assertEqual(report["metrics"]["obstruction_count"], 2)
        self.assertEqual(report["metrics"]["blocked_boundary_count"], 2)
        self.assertEqual(report["metrics"]["authority_upgrade_blocked_count"], 1)
        self.assertEqual(report["metrics"]["claim_permission_upgrade_count"], 0)
        self.assertEqual(report["metrics"]["foreground_projection_count"], 0)

        self.assertEqual(by_case["successful_macro_telepathy_glue"]["result"], "glued_route")
        self.assertEqual(by_case["dream_topology_partial_glue"]["result"], "partial_glue")
        self.assertEqual(by_case["stale_topology_obstruction"]["result"], "obstruction")
        self.assertEqual(by_case["privacy_blocked_boundary"]["result"], "blocked_boundary")
        self.assertEqual(by_case["authority_escalation_attempt"]["result"], "blocked_boundary")
        self.assertEqual(by_case["shared_vocabulary_only"]["result"], "obstruction")

        for row in report["compatibility_rows"]:
            self.assertEqual(row["claim_permission"], "navigation_only_not_fact")
            self.assertEqual(row["authority_level"], "navigation_only")
            self.assertTrue(row["source_reopen_required_before_claim"])
            self.assertFalse(row["foreground_projection_allowed"])
            self.assertTrue(row["glue_never_upgrades_authority"])
            self.assertTrue(row["failed_glue_is_obstruction_not_assignment"])

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
