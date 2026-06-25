from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
DEBT_REPORT = REPO_ROOT / "tools" / "aippocampus" / "docs" / "debt_report.py"

spec = importlib.util.spec_from_file_location("debt_report", DEBT_REPORT)
assert spec is not None and spec.loader is not None
debt_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(debt_report)

class DebtReportTests(unittest.TestCase):
    def test_headroom_summary_counts_exact_near_and_over_budget_runtime(self) -> None:
        system_weight = debt_report.build_system_weight(
            [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/exact.py",
                    "current_count": 100,
                    "guard_budget": 100,
                    "margin": 0,
                    "over_budget": False,
                },
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/near.py",
                    "current_count": 99,
                    "guard_budget": 100,
                    "margin": 1,
                    "over_budget": False,
                },
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/over.py",
                    "current_count": 101,
                    "guard_budget": 100,
                    "margin": -1,
                    "over_budget": True,
                },
            ],
            split_boundaries={},
        )

        summary = system_weight["guard_headroom_summary"]
        self.assertEqual(summary["runtime_exact_zero_count"], 1)
        self.assertEqual(summary["runtime_near_zero_count"], 1)
        self.assertEqual(summary["runtime_over_budget_count"], 1)
        warnings = debt_report.report_warnings(
            headroom_summary=summary,
            count_drifts=[
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/exact.py",
                    "registered_current_count": 99,
                    "current_count": 100,
                    "drift": 1,
                }
            ],
            stale_allowances=[],
        )
        self.assertEqual(
            [warning["code"] for warning in warnings],
            [
                "runtime_exact_zero_headroom",
                "runtime_near_zero_headroom",
                "architecture_debt_register_count_drift",
            ],
        )
        drift_warning = next(
            warning
            for warning in warnings
            if warning["code"] == "architecture_debt_register_count_drift"
        )
        self.assertEqual(
            drift_warning["refresh_command"],
            "python tools\\aippocampus\\docs\\debt_report.py --refresh-register-counts --write",
        )

    def test_clean_headroom_does_not_emit_nonfatal_warnings(self) -> None:
        system_weight = debt_report.build_system_weight(
            [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/healthy.py",
                    "current_count": 80,
                    "guard_budget": 120,
                    "margin": 40,
                    "over_budget": False,
                }
            ],
            split_boundaries={},
        )

        warnings = debt_report.report_warnings(
            headroom_summary=system_weight["guard_headroom_summary"],
            count_drifts=[],
            stale_allowances=[],
        )
        self.assertEqual(warnings, [])

    def test_single_digit_guard_pressure_is_explicitly_owned_or_warned(self) -> None:
        system_weight = debt_report.build_system_weight(
            [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py",
                    "current_count": 856,
                    "guard_budget": 860,
                    "margin": 4,
                    "over_budget": False,
                },
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/new_owner.py",
                    "current_count": 92,
                    "guard_budget": 100,
                    "margin": 8,
                    "over_budget": False,
                },
            ],
            split_boundaries={
                "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py": (
                    "Split seed-family builders before adding new dream-pack families."
                )
            },
        )

        pressure = system_weight["single_digit_guard_pressure"]
        by_path = {row["path"]: row for row in pressure}

        self.assertEqual(len(pressure), 2)
        self.assertEqual(
            by_path["skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py"][
                "owner_issue"
            ],
            "#2548",
        )
        self.assertTrue(
            by_path["skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py"][
                "tracked_owner_issue"
            ]
        )
        self.assertFalse(
            by_path["skills/aippocampus/scripts/aippocampus_runtime/new_owner.py"][
                "tracked_owner_issue"
            ]
        )
        self.assertEqual(
            system_weight["guard_headroom_summary"][
                "unowned_single_digit_guard_pressure_count"
            ],
            1,
        )
        archive_target = next(
            row
            for row in system_weight["archive_or_split_targets"]
            if row["path"]
            == "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py"
        )
        self.assertEqual(archive_target["owner_issue"], "#2548")

        warnings = debt_report.report_warnings(
            headroom_summary=system_weight["guard_headroom_summary"],
            count_drifts=[],
            stale_allowances=[],
            single_digit_guard_pressure=pressure,
        )
        pressure_warning = next(
            warning
            for warning in warnings
            if warning["code"] == "architecture_debt_single_digit_guard_pressure"
        )
        self.assertEqual(pressure_warning["count"], 2)
        self.assertEqual(pressure_warning["unowned_count"], 1)

    def test_count_drift_classifies_small_positive_and_stale_allowance(self) -> None:
        self.assertEqual(
            debt_report.drift_class(
                registered_count=100,
                current_count=103,
                guard_budget=140,
            ),
            "harmless_small_drift",
        )
        self.assertEqual(
            debt_report.drift_class(
                registered_count=100,
                current_count=130,
                guard_budget=140,
            ),
            "positive_drift",
        )
        self.assertEqual(
            debt_report.drift_class(
                registered_count=2400,
                current_count=120,
                guard_budget=2500,
            ),
            "large_stale_allowance_after_shrink",
        )

    def test_stale_allowance_rows_are_actionable(self) -> None:
        rows = [
            {
                "path": "tests/aippocampus/test_split_owner.py",
                "current_count": 32,
                "guard_budget": 4300,
                "margin": 4268,
                "over_budget": False,
            },
            {
                "path": "tests/aippocampus/test_normal_owner.py",
                "current_count": 1200,
                "guard_budget": 1500,
                "margin": 300,
                "over_budget": False,
            },
        ]

        stale = debt_report.stale_allowance_entries(rows)

        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["path"], "tests/aippocampus/test_split_owner.py")
        self.assertEqual(
            stale[0]["drift_class"],
            "large_stale_allowance_after_shrink",
        )
        self.assertEqual(
            stale[0]["recommended_action"],
            "lower_guard_budget_or_archive_row_with_dated_owner_rationale",
        )
        warnings = debt_report.report_warnings(
            headroom_summary={
                "runtime_exact_zero_count": 0,
                "runtime_near_zero_count": 0,
            },
            count_drifts=[],
            stale_allowances=stale,
        )
        self.assertIn(
            "architecture_debt_stale_allowance",
            [warning["code"] for warning in warnings],
        )

    def test_refresh_register_count_rows_updates_only_current_count_column(self) -> None:
        text = (
            "| Path | Current `script_line_count()` | Guard budget | Owner |\n"
            "| --- | ---: | ---: | --- |\n"
            "| `skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py` | 674 | 700 | #2483 |\n"
            "| `tests/aippocampus/test_update_sync.py` | 2126 | 2290 | #1307 |\n"
        )

        refreshed, changes = debt_report.refresh_register_count_rows(
            text,
            {
                "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py": 798,
                "tests/aippocampus/test_update_sync.py": 2126,
            },
        )

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["old_current_count"], 674)
        self.assertEqual(changes[0]["current_count"], 798)
        self.assertIn(
            "| `skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py` | 798 | 700 | #2483 |",
            refreshed,
        )
        self.assertIn("| `tests/aippocampus/test_update_sync.py` | 2126 | 2290 | #1307 |", refreshed)

    def test_debt_report_emits_code_debt_inventories(self) -> None:
        report = debt_report.build_report()

        self.assertIn("helper_duplication", report)
        self.assertIn("direct_jsonl_io", report)
        self.assertIn("broad_exception_debt", report)
        self.assertIn("compact_debug_field_leaks", report)
        self.assertIn("instruction_surface_debt", report)
        self.assertIn("giant_hot_path_functions", report)
        self.assertIn("test_debt_indicators", report)
        helper_families = {
            family["family"]
            for family in report["helper_duplication"]["families"]
        }
        self.assertIn("jsonl_read", helper_families)
        self.assertGreaterEqual(
            report["broad_exception_debt"]["summary"]["broad_total"],
            report["broad_exception_debt"]["summary"]["pure_silent_broad_except_total"],
        )
        self.assertEqual(
            report["direct_jsonl_io"]["ordinary_json_object_reads"],
            "excluded",
        )

    def test_direct_jsonl_inventory_classifies_runtime_line_parsers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = (
                root
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "source"
                / "io_kernel.py"
            )
            bad = (
                root
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "recall"
                / "local_jsonl_parser.py"
            )
            host_protocol_owner = (
                root
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "update"
                / "plugin_installer.py"
            )
            ordinary = (
                root
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "recall"
                / "json_config.py"
            )
            for path in (approved, bad, host_protocol_owner, ordinary):
                path.parent.mkdir(parents=True, exist_ok=True)
            approved.write_text("import json\n\ndef parse(line):\n    return json.loads(line)\n", encoding="utf-8")
            bad.write_text("import json\n\ndef parse(line):\n    return json.loads(line)\n", encoding="utf-8")
            host_protocol_owner.write_text(
                "import json\n\ndef parse(line):\n    return json.loads(line)\n",
                encoding="utf-8",
            )
            ordinary.write_text(
                "import json\n\ndef parse(path):\n    return json.loads(path.read_text())\n",
                encoding="utf-8",
            )

            def clear_debt_caches() -> None:
                debt_report.scan_python_files.cache_clear()
                debt_report.parse_python.cache_clear()

            clear_debt_caches()
            try:
                with mock.patch.object(debt_report, "REPO_ROOT", root):
                    clear_debt_caches()
                    inventory = debt_report.direct_jsonl_io_inventory(
                        debt_report.scan_python_files(),
                        repo_root=root,
                        detail=True,
                    )
                    changed = debt_report.changed_surface_debt(
                        [
                            "skills/aippocampus/scripts/aippocampus_runtime/recall/local_jsonl_parser.py"
                        ]
                    )
            finally:
                clear_debt_caches()

        sites = inventory["sites"]
        by_path = {item["path"]: item for item in sites}
        self.assertEqual(inventory["summary"]["line_json_parse_site_count"], 3)
        self.assertTrue(
            by_path[
                "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"
            ]["approved_owner"]
        )
        self.assertTrue(
            by_path[
                "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py"
            ]["approved_owner"]
        )
        self.assertEqual(
            by_path[
                "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py"
            ]["classification"],
            "codex_app_server_ndjson_protocol_owner",
        )
        self.assertEqual(
            by_path[
                "skills/aippocampus/scripts/aippocampus_runtime/recall/local_jsonl_parser.py"
            ]["classification"],
            "unapproved_runtime",
        )
        self.assertNotIn(
            "skills/aippocampus/scripts/aippocampus_runtime/recall/json_config.py",
            by_path,
        )
        self.assertEqual(changed["status"], "fail")
        self.assertIn(
            "changed_surface_direct_jsonl_parse",
            {warning["code"] for warning in changed["warnings"]},
        )

    def test_hot_path_pure_silent_broad_exceptions_stay_zero(self) -> None:
        inventory = debt_report.broad_exception_inventory()

        self.assertEqual(
            inventory["summary"]["hot_path_pure_silent_total"],
            0,
            "hot-path broad exceptions must degrade visibly instead of silently continuing",
        )

    def test_changed_surface_debt_is_acceptance_bearing_only_for_touched_files(self) -> None:
        clean = debt_report.changed_surface_debt(["docs/guides/install-guide.md"])
        self.assertEqual(clean["status"], "pass")

        projection_owner = debt_report.changed_surface_debt(
            ["skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py"]
        )
        self.assertEqual(projection_owner["status"], "pass")
        self.assertEqual(
            projection_owner["instruction_surface"]["classified_file_count"],
            1,
        )

        changed = debt_report.changed_surface_debt(
            ["skills/aippocampus/scripts/aippocampus_runtime/ops/recall_navigation_attention.py"]
        )
        self.assertGreater(changed["acceptance_bearing_warning_count"], 0)
        self.assertTrue(
            all(warning["acceptance_bearing"] for warning in changed["warnings"])
        )
        self.assertIn(
            "changed_surface_duplicate_helper",
            {warning["code"] for warning in changed["warnings"]},
        )

if __name__ == "__main__":
    unittest.main()
