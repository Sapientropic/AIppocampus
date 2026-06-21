from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_doc_tool_module

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"

docs_health = import_doc_tool_module("check_docs_health")

from tests.aippocampus.docs_health_fixtures import write_legacy_alias_fixture


class DocsHealthLegacyAliasInventoryTests(unittest.TestCase):
    def test_inventory_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.legacy_alias_inventory_issues(repo_root)

        self.assertEqual(result, [])

    def test_reports_unclassified_env_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            alias = "CODEX_MEMORY_" + "NEW_THING"
            write_legacy_alias_fixture(
                repo,
                inventory_text="# Legacy Alias Inventory\n",
                script_text=f'os.environ.get("{alias}")\n',
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            "legacy/provider-specific env or path missing inventory classification: "
            f"{alias}; update docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_rejects_public_doc_first_choice_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_legacy_alias_fixture(
                repo,
                inventory_text="`CODEX_MEMORY_VAULT`\n",
                script_text="",
                public_doc_text="export CODEX_MEMORY_VAULT=/tmp/private\n",
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            "public docs present legacy alias as first-choice setup: "
            "CODEX_MEMORY_VAULT in docs/guides/install-guide.md:1; "
            "prefer canonical AIPPOCAMPUS_* docs and link "
            "docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_reports_incomplete_inventory_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            alias = "CODEX_MEMORY_" + "VAULT"
            write_legacy_alias_fixture(
                repo,
                inventory_text="\n".join(
                    [
                        "# Legacy Alias Inventory",
                        "",
                        (
                            "| Alias | Canonical replacement | Why it exists | Classification | "
                            "Diagnostic behavior | Removal stage |"
                        ),
                        "| --- | --- | --- | --- | --- | --- |",
                        f"| `{alias}` | `AIPPOCAMPUS_VAULT` | old name |  | Active only when canonical unset. |  |",
                    ]
                ),
                script_text=f'os.environ.get("{alias}")\n',
                script_name="vault.py",
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            f"legacy/provider-specific env or path inventory row incomplete: {alias} "
            "(missing classification); update docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_reports_misspelled_aippocampus_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_legacy_alias_fixture(
                repo,
                inventory_text="# Legacy Alias Inventory\n",
                script_text='os.environ.get("AIIPPOCAMPUS_SUBCONSCIOUS_HOOK")\n',
                script_name="scheduler.py",
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            "legacy/provider-specific env or path missing inventory classification: "
            "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK; "
            "update docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_ignores_deepseek_non_env_constants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            alias = "CODEX_MEMORY_" + "NEW_THING"
            write_legacy_alias_fixture(
                repo,
                inventory_text="\n".join(
                    [
                        "# Legacy Alias Inventory",
                        "",
                        (
                            "| Alias | Canonical replacement | Why it exists | Classification | "
                            "Diagnostic behavior | Removal stage |"
                        ),
                        "| --- | --- | --- | --- | --- | --- |",
                        (
                            f"| `{alias}` | `AIPPOCAMPUS_NEW_THING` | old name | "
                            "Migration-only fallback | Active when canonical unset. | Remove after migration smoke. |"
                        ),
                    ]
                ),
                script_text="\n".join(
                    [
                        f'os.environ.get("{alias}")',
                        'DEEPSEEK_PREFIX_CACHE_CONTRACT = "deepseek_prefix_v1"',
                        'DEEPSEEK_KV_CACHE_GUIDE_URL = "https://example.invalid"',
                    ]
                ),
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
