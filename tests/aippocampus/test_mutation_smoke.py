from __future__ import annotations

import contextlib
import io
import json
import unittest

from tests.aippocampus.import_path_helpers import import_tool_root_module

mutation_smoke = import_tool_root_module("mutation_smoke")


class MutationSmokeTests(unittest.TestCase):
    def test_dry_run_reports_windows_safe_manual_lane(self) -> None:
        report = mutation_smoke.build_report(run=False)

        self.assertTrue(report["ok"])
        self.assertTrue(report["advisory"])
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(
            report["target_set"],
            "local_file_lock_and_recall_source_open_invariants",
        )
        self.assertFalse(report["platform_contract"]["uses_fork"])
        self.assertFalse(report["platform_contract"]["working_tree_mutation"])
        self.assertFalse(report["platform_contract"]["default_gate"])
        self.assertGreaterEqual(report["mutant_count"], 4)
        mutant_ids = {row["mutant_id"] for row in report["mutants"]}
        self.assertIn(
            "mcp_agent_recall_drops_recall_selector_from_deepen_arguments",
            mutant_ids,
        )
        self.assertIn(
            "cli_recall_blocked_source_anchor_route_marked_reopenable",
            mutant_ids,
        )

    def test_mutation_specs_still_match_current_sources_once_each(self) -> None:
        for mutant in mutation_smoke.MUTANTS:
            with self.subTest(mutant=mutant.mutant_id):
                target = mutation_smoke.REPO_ROOT / mutant.target
                text = target.read_text(encoding="utf-8")
                self.assertEqual(text.count(mutant.old), 1)
                self.assertNotEqual(mutant.old, mutant.new)
                self.assertTrue(mutant.expected_test_module.startswith("tests.aippocampus."))

    def test_json_cli_dry_run_is_machine_readable(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = mutation_smoke.main(["--dry-run", "--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["kind"], "aippocampus_mutation_smoke")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["survived_count"], 0)


if __name__ == "__main__":
    unittest.main()
