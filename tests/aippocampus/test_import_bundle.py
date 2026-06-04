from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORT_BUNDLE_MODULE = "aippocampus_runtime.artifacts.import_bundle"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.artifacts import import_bundle as import_bundle  # noqa: E402
from aippocampus_runtime.artifacts import import_bundle as packaged_import_bundle  # noqa: E402


class ImportBundleTests(unittest.TestCase):
    def test_package_module_is_the_artifact_import_owner(self) -> None:
        self.assertIs(import_bundle.safe_extract, packaged_import_bundle.safe_extract)
        self.assertIs(import_bundle.append_import_anchor, packaged_import_bundle.append_import_anchor)
        self.assertIs(import_bundle.main, packaged_import_bundle.main)

    def test_import_reports_pointer_resolved_current_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle.zip"
            dest = root / "workspace"
            dest.mkdir()
            with zipfile.ZipFile(bundle, "w") as zf:
                zf.writestr(
                    "bundle_manifest.json",
                    json.dumps({"message_count": 1, "cwd": "source-device"}, ensure_ascii=False),
                )
                zf.writestr("index/versions/source_index-current.sqlite", b"sqlite cache")
                zf.writestr(
                    "index/source_index.pointer.json",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "aippocampus_sqlite_index_pointer",
                            "stable": "source_index.sqlite",
                            "current": "versions/source_index-current.sqlite",
                            "last_known_good": "source_index.sqlite",
                        },
                        ensure_ascii=False,
                    ),
                )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    IMPORT_BUNDLE_MODULE,
                    str(bundle),
                    "--dest",
                    str(dest),
                    "--name",
                    "imported",
                    "--no-anchor",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env={
                    **os.environ,
                    "PYTHONPATH": str(SCRIPTS)
                    if not os.environ.get("PYTHONPATH")
                    else str(SCRIPTS) + os.pathsep + os.environ["PYTHONPATH"],
                },
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(
                Path(result["sqlite_current"]).resolve(),
                (dest / "imported" / "index" / "versions" / "source_index-current.sqlite").resolve(),
            )

    def test_import_reports_generation_pointer_resolved_current_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle.zip"
            dest = root / "workspace"
            dest.mkdir()
            generation = "gen_20260605T010203_123_456"
            with zipfile.ZipFile(bundle, "w") as zf:
                zf.writestr(
                    "bundle_manifest.json",
                    json.dumps({"message_count": 1, "cwd": "source-device"}, ensure_ascii=False),
                )
                zf.writestr(f"index/generations/{generation}/source_index.sqlite", b"sqlite cache")
                zf.writestr(
                    "index/source_index.pointer.json",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "aippocampus_sqlite_index_pointer",
                            "stable": "source_index.sqlite",
                            "current": f"generations/{generation}/source_index.sqlite",
                            "last_known_good": f"generations/{generation}/source_index.sqlite",
                            "current_generation": generation,
                            "last_known_good_generation": generation,
                            "compatibility_path": "source_index.sqlite",
                        },
                        ensure_ascii=False,
                    ),
                )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    IMPORT_BUNDLE_MODULE,
                    str(bundle),
                    "--dest",
                    str(dest),
                    "--name",
                    "imported",
                    "--no-anchor",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env={
                    **os.environ,
                    "PYTHONPATH": str(SCRIPTS)
                    if not os.environ.get("PYTHONPATH")
                    else str(SCRIPTS) + os.pathsep + os.environ["PYTHONPATH"],
                },
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(
                Path(result["sqlite_current"]).resolve(),
                (
                    dest
                    / "imported"
                    / "index"
                    / "generations"
                    / generation
                    / "source_index.sqlite"
                ).resolve(),
            )

    def test_package_main_imports_bundle_without_spawning_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle.zip"
            dest = root / "workspace"
            dest.mkdir()
            with zipfile.ZipFile(bundle, "w") as zf:
                zf.writestr(
                    "bundle_manifest.json",
                    json.dumps({"message_count": 1, "cwd": "source-device"}, ensure_ascii=False),
                )
                zf.writestr("index/messages.jsonl", "{}\n")

            with (
                patch("subprocess.run", side_effect=AssertionError("import should not spawn")),
                patch("sys.stdout", new=StringIO()) as stdout,
            ):
                code = packaged_import_bundle.main(
                    [str(bundle), "--dest", str(dest), "--name", "direct", "--no-anchor"]
                )

            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(Path(result["extracted_to"]).resolve(), (dest / "direct").resolve())


if __name__ == "__main__":
    unittest.main()
