from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORT_BUNDLE = REPO_ROOT / "skills" / "aippocampus" / "scripts" / "import_bundle.py"


class ImportBundleTests(unittest.TestCase):
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
                    str(IMPORT_BUNDLE),
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
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(
                Path(result["sqlite_current"]).resolve(),
                (dest / "imported" / "index" / "versions" / "source_index-current.sqlite").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
