from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "aippocampus" / "docs"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import compat_shim_inventory as inventory  # noqa: E402


class CompatibilityShimInventoryTests(unittest.TestCase):
    def test_inventory_buckets_every_top_level_runtime_script(self) -> None:
        report = inventory.build_inventory(ROOT)
        bucketed = {
            item.script
            for bucket in (
                report.keep_cli,
                report.temporary_compat,
                report.delete_now,
                report.legacy_bridge,
            )
            for item in bucket
        }

        self.assertEqual(bucketed, set(report.top_level_scripts))
        self.assertEqual(len(bucketed), report.top_level_script_count)
        self.assertEqual(report.unbucketed, [])

    def test_public_hooks_and_legacy_bridges_are_not_delete_now(self) -> None:
        report = inventory.build_inventory(ROOT)
        keep_cli = {item.script: item for item in report.keep_cli}
        legacy_bridge = {item.script: item for item in report.legacy_bridge}
        delete_now = {item.script for item in report.delete_now}

        for script in (
            "aippocampus_cli.py",
            "aippocampus_prompt_hook.py",
            "aippocampus_lifecycle_hook.py",
            "aippocampus_mcp_server.py",
        ):
            self.assertIn(script, keep_cli)
            self.assertTrue(keep_cli[script].removal_condition)
            self.assertNotIn(script, delete_now)

        self.assertEqual(
            set(legacy_bridge),
            {
                "encrypted_sync_admin.py",
                "semantic_scope_suppressed_recovery.py",
                "subconscious_review.py",
            },
        )

    def test_prompt_cue_reexports_are_no_longer_compat_surface(self) -> None:
        report = inventory.build_inventory(ROOT)
        reexports = {item.script: item for item in report.reexport_blocks}

        self.assertNotIn("aippocampus_runtime/recall/prompt_recall_core.py", reexports)
        core_source = (
            ROOT
            / "skills"
            / "aippocampus"
            / "scripts"
            / "aippocampus_runtime"
            / "recall"
            / "prompt_recall_core.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("CUE_COMPAT_EXPORTS", core_source)


if __name__ == "__main__":
    unittest.main()
