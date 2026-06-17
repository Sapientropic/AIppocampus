from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.legacy_aliases import legacy_alias_diagnostics  # noqa: E402


class LegacyAliasDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_report_aliases_without_values_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            report = legacy_alias_diagnostics(
                env={
                    "CODEX_MEMORY_VAULT": str(root / "private-vault"),
                    "AIPPOCAMPUS_STYLE_SOURCE": "canonical-style.css",
                    "CODEX_MEMORY_STYLE_SOURCE": "legacy-style.css",
                    "DEEPSEEK_API_KEY": "legacy-secret-key",
                    "DEEPSEEK_MODEL": "legacy-flash-model",
                    "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK": "0",
                },
                registry_resolution={
                    "source": "CODEX_HOME/aippocampus-registry",
                    "legacy_fallback": True,
                },
                workspace=workspace,
                project_local_paths={
                    "index": workspace / ".aippocampus" / "index",
                    "external": root / "outside" / ".aippocampus" / "index",
                },
            )

        active = {entry["alias"] for entry in report["active"]}
        shadowed = {entry["alias"] for entry in report["shadowed"]}
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertEqual(
            active,
            {
                "CODEX_MEMORY_VAULT",
                "DEEPSEEK_API_KEY",
                "DEEPSEEK_MODEL",
                "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK",
                "CODEX_HOME/aippocampus-registry",
                ".aippocampus/",
            },
        )
        self.assertEqual(shadowed, {"CODEX_MEMORY_STYLE_SOURCE"})
        self.assertFalse(report["value_printed"])
        self.assertFalse(report["local_paths_included"])
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("private-vault", encoded)
        self.assertNotIn("legacy-flash-model", encoded)
        self.assertNotIn("legacy-secret-key", encoded)
        self.assertNotIn('"0"', encoded)
        self.assertNotIn("canonical-style.css", encoded)


if __name__ == "__main__":
    unittest.main()
