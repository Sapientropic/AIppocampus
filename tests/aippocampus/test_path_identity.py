from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime import core  # noqa: E402
from aippocampus_runtime.registry import common as registry_common  # noqa: E402
from aippocampus_runtime.registry import provider as registry_provider  # noqa: E402


class PathIdentityTests(unittest.TestCase):
    def test_workspace_identity_preserves_plain_project_labels(self) -> None:
        self.assertEqual(core.workspace_identity("Project Alpha"), "Project Alpha")
        self.assertEqual(core.workspace_identity_key("Project Alpha"), "project alpha")
        self.assertEqual(
            core.workspace_fingerprint("Project Alpha"),
            "workspace_" + hashlib.sha256("project alpha".encode("utf-8")).hexdigest()[:16],
        )

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

    @unittest.skipIf(os.name != "nt", "Windows UNC and drive spelling smoke")
    def test_path_identity_key_canonicalizes_unc_and_drive_spelling(self) -> None:
        self.assertEqual(
            core.path_identity_key(r"\\SERVER\Share\Project"),
            core.path_identity_key(r"\\server\share\Project\."),
        )
        self.assertEqual(
            core.path_identity_key(r"C:\Repo\Project"),
            core.path_identity_key(r"c:\repo\Project\."),
        )

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

    def test_registry_keys_reuse_canonical_workspace_identity(self) -> None:
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
                registry_common.project_key_for(workspace),
                registry_common.project_key_for(alias),
            )
            self.assertEqual(
                registry_provider.thread_key_for(workspace, {}, None),
                registry_provider.thread_key_for(alias, {}, None),
            )

    def test_registry_project_key_uses_sha256_identity_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            digest = registry_common.project_key_for(workspace).rsplit(":", 1)[-1]
            identity = core.workspace_identity_key(workspace)

        self.assertEqual(digest, hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16])
        self.assertEqual(len(digest), 16)
        self.assertTrue(
            registry_common.project_key_for(None, "Unknown").endswith(
                ":" + hashlib.sha256("unknown".encode("utf-8")).hexdigest()[:16]
            )
        )

    def test_path_identity_contract_doc_links_broader_regression_family(self) -> None:
        doc = REPO_ROOT / "docs" / "architecture" / "source" / "path-identity.md"
        text = doc.read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")

        for term in (
            "#404",
            "#589",
            "identity key",
            "display path",
            "privacy-safe public path",
            "UNC",
            "symlink",
            "bind mount",
        ):
            self.assertIn(term, text)
        self.assertIn("architecture/source/path-identity.md", readme)
        self.assertIn("path-identity.md", docs_index)


if __name__ == "__main__":
    unittest.main()
