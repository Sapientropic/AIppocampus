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
                    "--include-private-paths",
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
                Path(result["diagnostics"]["sqlite_current"]).resolve(),
                (dest / "imported" / "index" / "versions" / "source_index-current.sqlite").resolve(),
            )
            self.assertTrue(result["privacy_boundary"]["local_paths_included"])

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
                    "--include-private-paths",
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
                Path(result["diagnostics"]["sqlite_current"]).resolve(),
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
                    [
                        str(bundle),
                        "--dest",
                        str(dest),
                        "--name",
                        "direct",
                        "--no-anchor",
                        "--include-private-paths",
                    ]
                )

            self.assertEqual(code, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(
                Path(result["diagnostics"]["extracted_to"]).resolve(),
                (dest / "direct").resolve(),
            )

    def test_default_import_output_is_action_card_with_redacted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle.zip"
            dest = root / "workspace"
            dest.mkdir()
            with zipfile.ZipFile(bundle, "w") as zf:
                zf.writestr(
                    "bundle_manifest.json",
                    json.dumps(
                        {
                            "message_count": 2,
                            "cwd": "source-device",
                            "raw_rollout_included": True,
                            "redaction_profile": "raw-private",
                        },
                        ensure_ascii=False,
                    ),
                )
                zf.writestr("index/messages.jsonl", "{}\n")

            with patch("sys.stdout", new=StringIO()) as stdout:
                code = packaged_import_bundle.main(
                    [str(bundle), "--dest", str(dest), "--name", "direct"]
                )

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_bundle_import_summary")
        self.assertTrue(payload["summary"]["anchor_written"])
        self.assertEqual(payload["summary"]["message_count"], 2)
        self.assertEqual(payload["diagnostics"]["extracted_to"], "<local-path-redacted>")
        self.assertNotIn(str(dest), json.dumps(payload, ensure_ascii=False))
        self.assertIn("aippocampus search", payload["summary"]["next_command"])

    def test_missing_bundle_accepts_json_and_redacts_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("sys.stdout", new=StringIO()) as stdout:
            missing = Path(tmp) / "missing-aippo-bundle.zip"
            code = packaged_import_bundle.main([str(missing), "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "bundle_not_found")
        self.assertIn("<local-path-redacted>", payload["error"]["message"])
        self.assertNotIn(str(missing.parent), encoded)


if __name__ == "__main__":
    unittest.main()
