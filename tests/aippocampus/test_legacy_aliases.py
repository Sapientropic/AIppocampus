from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.legacy_aliases import legacy_alias_diagnostics


class LegacyAliasDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_report_remaining_path_compat_without_retired_env_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            report = legacy_alias_diagnostics(
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
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertEqual(
            active,
            {
                "CODEX_HOME/aippocampus-registry",
                ".aippocampus/",
            },
        )
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
