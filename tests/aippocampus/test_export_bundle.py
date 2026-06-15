from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.artifacts import export_bundle as export_bundle  # noqa: E402
from aippocampus_runtime.artifacts import export_bundle as packaged_export_bundle  # noqa: E402


class ExportBundleTests(unittest.TestCase):
    def test_top_level_script_is_compatibility_shim_for_package_owner(self) -> None:
        self.assertIs(export_bundle.write_handoff, packaged_export_bundle.write_handoff)
        self.assertIs(export_bundle.run_build_index, packaged_export_bundle.run_build_index)
        self.assertIs(export_bundle.main, packaged_export_bundle.main)

    def test_handoff_points_search_to_extracted_index_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "handoff.md"

            export_bundle.write_handoff(
                handoff,
                {
                    "created_at": "2026-05-30T00:00:00Z",
                    "cwd": "source-device",
                    "message_count": 1,
                    "anchor_count": 0,
                    "graph": {"node_count": 0},
                },
                include_raw=False,
            )

            text = handoff.read_text(encoding="utf-8")
            self.assertIn("<extracted>\\index\\source_index.sqlite", text)
            self.assertIn("resolves the generation pointer", text)

    def test_run_build_index_uses_package_api_without_subprocess(self) -> None:
        seen: dict[str, list[str]] = {}

        def fake_index_main(argv: list[str] | None = None) -> int:
            seen["argv"] = list(argv or [])
            print('{"message_count": 1, "anchor_count": 0, "graph": {"node_count": 0}}')
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(
                    packaged_export_bundle.index_builder,
                    "main",
                    side_effect=fake_index_main,
                ),
                patch("subprocess.run", side_effect=AssertionError("export should not spawn")),
                patch("sys.stdout", new=StringIO()) as stdout,
            ):
                result = packaged_export_bundle.run_build_index(
                    root,
                    root / "rollout.jsonl",
                    root / "index",
                    root / "thread-anchors.md",
                    hash_source=True,
                    redaction_profile="raw-private",
                )

        self.assertEqual(result["message_count"], 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            seen["argv"],
            [
                "--cwd",
                str(root),
                "--rollout",
                str(root / "rollout.jsonl"),
                "--output-dir",
                str(root / "index"),
                "--anchors",
                str(root / "thread-anchors.md"),
                "--json",
                "--redaction-profile",
                "raw-private",
                "--hash-source",
            ],
        )

    def test_public_export_profile_is_metadata_only_and_excludes_raw_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_resolved = root.resolve()
            rollout = root / "rollout.jsonl"
            anchors = root / "thread-anchors.md"
            work_dir = root / "work"
            rollout.write_text(
                '{"type":"event_msg","payload":{"type":"user_message","message":"token=secret"}}\n',
                encoding="utf-8",
            )
            anchors.write_text("# Anchors\n", encoding="utf-8")

            def fake_build_index(
                cwd: Path,
                rollout_path: Path,
                index_dir: Path,
                anchors_path: Path,
                hash_source: bool,
                redaction_profile: str,
            ) -> dict:
                self.assertEqual(cwd, root_resolved)
                self.assertEqual(rollout_path, rollout)
                self.assertEqual(anchors_path, anchors)
                self.assertFalse(hash_source)
                self.assertEqual(redaction_profile, "public-metadata")
                index_dir.mkdir(parents=True, exist_ok=True)
                (index_dir / "messages.jsonl").write_text(
                    json.dumps(
                        {
                            "message_id": "msg-private",
                            "turn_id": "turn-private",
                            "line": 3,
                            "role": "user",
                            "text": "private clean-source text should not ship",
                            "source_ref": "codex:session:session-private#L3",
                            "source_id": "session-private",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (index_dir / "turns.jsonl").write_text(
                    '{"turn_id":"turn-private","turn_index":1,"message_ids":["msg-private"]}\n',
                    encoding="utf-8",
                )
                (index_dir / "source_index.sqlite").write_bytes(
                    b"sqlite private clean-source text should not ship"
                )
                (index_dir / "source_index.pointer.json").write_text(
                    '{"current":"source_index.sqlite"}',
                    encoding="utf-8",
                )
                return {
                    "created_at": "2026-06-03T00:00:00Z",
                    "cwd": str(root),
                    "message_count": 1,
                    "anchor_count": 0,
                    "graph": {"node_count": 0},
                    "redaction_profile": "public-metadata",
                    "source_thread_key": "codex:session:session-private",
                    "source_rollout": str(rollout),
                    "session_meta": {
                        "id": "session-private",
                        "base_instructions": {"text": "host base instructions"},
                    },
                }

            args = Namespace(
                cwd=str(root),
                rollout=str(rollout),
                anchors=str(anchors),
                output=str(root / "bundle.zip"),
                work_dir=str(work_dir),
                no_raw=True,
                hash_source=False,
                redaction_profile="public-export",
            )

            with patch.object(packaged_export_bundle, "run_build_index", side_effect=fake_build_index):
                result = packaged_export_bundle.export_bundle(args)

            self.assertTrue(Path(result["bundle"]).exists())
            bundle_root = work_dir / "bundle"
            encoded = "\n".join(
                file.read_text(encoding="utf-8")
                for file in bundle_root.rglob("*")
                if file.is_file() and file.suffix not in {".zip", ".sqlite"}
            )
            with zipfile.ZipFile(result["bundle"]) as zf:
                names = set(zf.namelist())

            bundle_manifest = (bundle_root / "bundle_manifest.json").read_text(encoding="utf-8")
            self.assertIn('"redaction_profile": "public-export"', bundle_manifest)
            self.assertIn('"public_share_safe": true', bundle_manifest)
            self.assertIn('"private_clean_source_text_included": false', bundle_manifest)
            self.assertIn('"raw_rollout_included": false', bundle_manifest)
            self.assertIn('"search_index_included": false', bundle_manifest)
            self.assertIn('"search_index": null', bundle_manifest)
            self.assertIn('"source_texture_policy"', bundle_manifest)
            self.assertIn('"projection": "omitted"', bundle_manifest)
            self.assertIn('"reason": "private_interpretation_sidecar"', bundle_manifest)
            self.assertNotIn("private clean-source text", encoded)
            self.assertNotIn("session-private", encoded)
            self.assertNotIn("host base instructions", encoded)
            self.assertNotIn("codex:session", encoded)
            self.assertNotIn("thread-anchors.md", names)
            self.assertNotIn("index/source_index.sqlite", names)
            self.assertNotIn("index/source_index.pointer.json", names)
            self.assertIn("index/search_index_omitted.json", names)
            self.assertTrue(
                all(
                    str(row["source_ref"]).startswith("source_hash:")
                    for row in [
                        json.loads(line)
                        for line in (bundle_root / "index" / "messages.jsonl")
                        .read_text(encoding="utf-8")
                        .splitlines()
                    ]
                )
            )
            self.assertFalse((bundle_root / "rollout.jsonl").exists())
            self.assertFalse((bundle_root / "source-texture.jsonl").exists())

    def test_public_metadata_profile_omits_clean_text_and_session_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_resolved = root.resolve()
            rollout = root / "rollout.jsonl"
            anchors = root / "thread-anchors.md"
            work_dir = root / "work"
            rollout.write_text(
                '{"type":"session_meta","payload":{"id":"session-private","base_instructions":{"text":"host base instructions"}}}\n',
                encoding="utf-8",
            )
            anchors.write_text("# Private Anchor\n", encoding="utf-8")

            def fake_build_index(
                cwd: Path,
                rollout_path: Path,
                index_dir: Path,
                anchors_path: Path,
                hash_source: bool,
                redaction_profile: str,
            ) -> dict:
                self.assertEqual(cwd, root_resolved)
                self.assertEqual(rollout_path, rollout)
                self.assertEqual(anchors_path, anchors)
                self.assertEqual(redaction_profile, "public-metadata")
                index_dir.mkdir(parents=True, exist_ok=True)
                (index_dir / "messages.jsonl").write_text(
                    '{"text":"","source_ref":"source_hash:abc#L1"}\n',
                    encoding="utf-8",
                )
                (index_dir / "graph.json").write_text(
                    '{"nodes":[{"label":"Private Anchor"}],"edges":[]}',
                    encoding="utf-8",
                )
                return {
                    "created_at": "2026-06-03T00:00:00Z",
                    "cwd": str(root),
                    "message_count": 1,
                    "anchor_count": 1,
                    "graph": {"node_count": 1, "edge_count": 0},
                    "redaction_profile": "public-metadata",
                    "source_thread_key": "codex:session:session-private",
                    "source_rollout": str(rollout),
                    "session_meta": {
                        "id": "session-private",
                        "base_instructions": {"text": "host base instructions"},
                    },
                }

            args = Namespace(
                cwd=str(root),
                rollout=str(rollout),
                anchors=str(anchors),
                output=str(root / "bundle.zip"),
                work_dir=str(work_dir),
                no_raw=True,
                hash_source=False,
                redaction_profile="public-metadata",
            )

            with patch.object(packaged_export_bundle, "run_build_index", side_effect=fake_build_index):
                result = packaged_export_bundle.export_bundle(args)

            bundle_root = work_dir / "bundle"
            encoded = "\n".join(
                file.read_text(encoding="utf-8")
                for file in bundle_root.rglob("*")
                if file.is_file()
            )

            self.assertTrue(Path(result["bundle"]).exists())
            self.assertEqual(result["public_sharing_boundary"]["public_share_safe"], True)
            self.assertNotIn("session-private", encoded)
            self.assertNotIn("host base instructions", encoded)
            self.assertNotIn("Private Anchor", encoded)
            self.assertIn('"public_share_safe": true', encoded)
            self.assertIn('"source_refs_hashed": true', encoded)
            self.assertFalse((bundle_root / "thread-anchors.md").exists())

    def test_public_export_profile_rejects_raw_rollout_inclusion(self) -> None:
        args = Namespace(
            cwd=".",
            rollout="rollout.jsonl",
            anchors="thread-anchors.md",
            output=None,
            work_dir=None,
            no_raw=False,
            hash_source=False,
            redaction_profile="public-export",
        )

        with self.assertRaisesRegex(ValueError, "public-export.*--no-raw"):
            packaged_export_bundle.export_bundle(args)

    def test_public_metadata_profile_rejects_raw_rollout_inclusion(self) -> None:
        args = Namespace(
            cwd=".",
            rollout="rollout.jsonl",
            anchors="thread-anchors.md",
            output=None,
            work_dir=None,
            no_raw=False,
            hash_source=False,
            redaction_profile="public-metadata",
        )

        with self.assertRaisesRegex(ValueError, "public-metadata.*--no-raw"):
            packaged_export_bundle.export_bundle(args)


if __name__ == "__main__":
    unittest.main()
