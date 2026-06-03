from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "aippocampus" / "docs"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import compat_shim_inventory as inventory  # noqa: E402


def write_fixture_script(repo_root: Path, script_name: str, source: str) -> None:
    scripts_dir = repo_root / "skills" / "aippocampus" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    path = scripts_dir / script_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


BATCH_DELETED_PACKAGE_ONLY_SHIMS = {
    "question_feedback_policy.py",
    "question_vector_index.py",
    "vault_notes.py",
    "vault_sync_utils.py",
    "warm_ambient_prompting.py",
    "warm_ambient_scout_profiles.py",
    "warm_ambient_source_validation.py",
}


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

    def test_public_hooks_and_former_legacy_bridges_are_not_delete_now(self) -> None:
        report = inventory.build_inventory(ROOT)
        keep_cli = {item.script: item for item in report.keep_cli}
        legacy_bridge = {item.script: item for item in report.legacy_bridge}
        delete_now = {item.script for item in report.delete_now}
        temporary_compat = {item.script: item for item in report.temporary_compat}

        for script in (
            "aippocampus_cli.py",
            "aippocampus_prompt_hook.py",
            "aippocampus_lifecycle_hook.py",
            "aippocampus_mcp_server.py",
        ):
            self.assertIn(script, keep_cli)
            self.assertTrue(keep_cli[script].removal_condition)
            self.assertNotIn(script, delete_now)

        self.assertEqual(set(legacy_bridge), set())
        self.assertIn("encrypted_sync_admin.py", keep_cli)
        self.assertIn("semantic_scope_suppressed_recovery.py", temporary_compat)
        self.assertIn("subconscious_review.py", temporary_compat)

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

    def test_temporary_compat_shims_do_not_keep_long_manual_export_surfaces(self) -> None:
        report = inventory.build_inventory(ROOT)

        self.assertEqual(report.manual_export_surfaces, [])

    def test_package_only_helper_shims_are_removed_after_deletion_batch(self) -> None:
        report = inventory.build_inventory(ROOT)
        top_level_scripts = set(report.top_level_scripts)
        delete_now = {item.script for item in report.delete_now}

        self.assertFalse(BATCH_DELETED_PACKAGE_ONLY_SHIMS & top_level_scripts)
        self.assertFalse(BATCH_DELETED_PACKAGE_ONLY_SHIMS & delete_now)

    def test_unreferenced_package_owner_shim_is_delete_now_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_fixture_script(
                repo_root,
                "unused_helper.py",
                '''#!/usr/bin/env python3
"""Compatibility shim for packaged unused helper."""

from __future__ import annotations

import sys

from aippocampus_runtime.unused import helper as _impl

sys.modules[__name__] = _impl
''',
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/unused/helper.py",
                "def main() -> int:\n    return 0\n",
            )
            (repo_root / "pyproject.toml").write_text(
                '[tool.setuptools]\npy-modules = ["unused_helper"]\n',
                encoding="utf-8",
            )

            report = inventory.build_inventory(repo_root)
            delete_now = {item.script: item for item in report.delete_now}

            self.assertIn("unused_helper.py", delete_now)
            self.assertIn("only remaining flat-module exposure", delete_now["unused_helper.py"].reason)

    def test_first_party_import_keeps_package_owner_shim_temporary(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_fixture_script(
                repo_root,
                "shared_helper.py",
                '''#!/usr/bin/env python3
"""Compatibility shim for packaged shared helper."""

from __future__ import annotations

import sys

from aippocampus_runtime.shared import helper as _impl

sys.modules[__name__] = _impl
''',
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/shared/helper.py",
                "def value() -> int:\n    return 1\n",
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/consumer.py",
                "import shared_helper\n\nVALUE = shared_helper.value()\n",
            )

            report = inventory.build_inventory(repo_root)
            temporary = {item.script: item for item in report.temporary_compat}

            self.assertIn("shared_helper.py", temporary)
            self.assertIn("first-party import", temporary["shared_helper.py"].reason)

    def test_dynamic_first_party_import_keeps_package_owner_shim_temporary(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_fixture_script(
                repo_root,
                "dynamic_helper.py",
                '''#!/usr/bin/env python3
"""Compatibility shim for packaged dynamic helper."""

from __future__ import annotations

import sys

from aippocampus_runtime.dynamic import helper as _impl

sys.modules[__name__] = _impl
''',
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/dynamic/helper.py",
                "def value() -> int:\n    return 1\n",
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/consumer.py",
                'import importlib\n\nVALUE = importlib.import_module("dynamic_helper").value()\n',
            )

            report = inventory.build_inventory(repo_root)
            temporary = {item.script: item for item in report.temporary_compat}

            self.assertIn("dynamic_helper.py", temporary)
            self.assertIn("first-party import", temporary["dynamic_helper.py"].reason)

    def test_documented_direct_invocation_keeps_package_owner_shim_temporary(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_fixture_script(
                repo_root,
                "documented_helper.py",
                '''#!/usr/bin/env python3
"""Compatibility shim for packaged documented helper."""

from __future__ import annotations

import sys

from aippocampus_runtime.documented import helper as _impl

sys.modules[__name__] = _impl
''',
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/documented/helper.py",
                "def main() -> int:\n    return 0\n",
            )
            docs_dir = repo_root / "docs"
            docs_dir.mkdir(parents=True)
            (docs_dir / "guide.md").write_text(
                "Use `documented_helper.py` for local diagnostics.\n",
                encoding="utf-8",
            )

            report = inventory.build_inventory(repo_root)
            temporary = {item.script: item for item in report.temporary_compat}

            self.assertIn("documented_helper.py", temporary)
            self.assertIn("documented direct invocation", temporary["documented_helper.py"].reason)

    def test_skill_entrypoint_direct_invocation_keeps_shim_temporary(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_fixture_script(
                repo_root,
                "skill_documented_helper.py",
                '''#!/usr/bin/env python3
"""Compatibility shim for a helper documented by the installable skill."""

from __future__ import annotations

import sys

from aippocampus_runtime.skill_documented import helper as _impl

sys.modules[__name__] = _impl
''',
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/skill_documented/helper.py",
                "def main() -> int:\n    return 0\n",
            )
            skill_path = repo_root / "skills" / "aippocampus" / "SKILL.md"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(
                "Use `skill_documented_helper.py` for runtime recovery.\n",
                encoding="utf-8",
            )

            report = inventory.build_inventory(repo_root)
            temporary = {item.script: item for item in report.temporary_compat}

            self.assertIn("skill_documented_helper.py", temporary)
            self.assertIn(
                "documented direct invocation",
                temporary["skill_documented_helper.py"].reason,
            )


if __name__ == "__main__":
    unittest.main()
