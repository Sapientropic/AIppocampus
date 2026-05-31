from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime import core  # noqa: E402


class PathIdentityTests(unittest.TestCase):
    def test_workspace_identity_preserves_plain_project_labels(self) -> None:
        self.assertEqual(core.workspace_identity("Project Alpha"), "Project Alpha")
        self.assertEqual(core.workspace_identity_key("Project Alpha"), "project alpha")

    def test_workspace_identity_canonicalizes_absolute_path_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            alternate = workspace / ".." / "workspace"

            self.assertEqual(
                core.workspace_identity_key(workspace),
                core.workspace_identity_key(alternate),
            )
            self.assertEqual(
                core.workspace_fingerprint(workspace),
                core.workspace_fingerprint(alternate),
            )
            self.assertEqual(core.norm_path(workspace), core.workspace_identity_key(workspace))

    def test_workspace_identity_canonicalizes_symlinked_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            alias = root / "workspace-alias"
            try:
                os.symlink(workspace, alias)
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")

            self.assertEqual(
                core.workspace_identity_key(workspace),
                core.workspace_identity_key(alias),
            )
            self.assertEqual(
                core.workspace_fingerprint(workspace),
                core.workspace_fingerprint(alias),
            )


if __name__ == "__main__":
    unittest.main()
