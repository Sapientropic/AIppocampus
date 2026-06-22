from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from aippocampus_runtime import core
from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp.clean_source_resolution import resolve_mcp_clean_source_dir


class McpDefaultCleanSourceResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.old_registry_dir = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
        os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = str(self.cwd / "default-registry")
        self.clean = core.default_thread_clean_source_dir(self.cwd)
        self.clean.mkdir(parents=True)
        self._write_message(
            self.clean,
            {
                "message_id": "msg-seed",
                "turn_id": "turn-seed",
                "turn_index": 1,
                "source_id": "src-seed",
                "source_line": 1,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "Seed source row.",
            },
        )

    def tearDown(self) -> None:
        if self.old_registry_dir is None:
            os.environ.pop("AIPPOCAMPUS_REGISTRY_DIR", None)
        else:
            os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = self.old_registry_dir
        self.tmp.cleanup()

    def _write_message(self, clean: Path, row: dict[str, object]) -> None:
        clean.mkdir(parents=True, exist_ok=True)
        with (clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        turn_row = {
            "turn_id": row["turn_id"],
            "turn_index": row["turn_index"],
            "message_ids": [row["message_id"]],
            "assistant_phase": row.get("phase") or "",
        }
        with (clean / "turns.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(turn_row, ensure_ascii=False) + "\n")

    def _call_tool_payload(self, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": f"call-{name}",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        text = response["result"]["content"][0]["text"]
        return json.loads(text)

    def _write_manifest_clean_source(
        self,
        clean: Path,
        *,
        cwd: Path,
        source_transcript_mtime: float,
        text: str = "seed",
    ) -> None:
        self._write_message(
            clean,
            {
                "message_id": f"msg-{clean.parent.name}",
                "turn_id": f"turn-{clean.parent.name}",
                "turn_index": 1,
                "source_id": f"src-{clean.parent.name}",
                "source_line": 1,
                "role": "user",
                "text": text,
            },
        )
        manifest = {
            "kind": "aippocampus_clean_source",
            "cwd": str(cwd),
            "source_transcript_mtime": source_transcript_mtime,
            "source_thread_key": f"session:{clean.parent.name}",
        }
        (clean / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
            newline="\n",
        )

    def test_mcp_default_resolution_prefers_fresher_same_cwd_registry_clean_source(
        self,
    ) -> None:
        threads = self.cwd / "registry" / "threads"
        stale = threads / "session-stale" / "clean-source"
        fresh = threads / "session-fresh" / "clean-source"
        other_cwd = threads / "session-other-cwd" / "clean-source"
        self._write_manifest_clean_source(
            stale,
            cwd=self.cwd,
            source_transcript_mtime=1,
            text="stale same cwd should lose",
        )
        self._write_manifest_clean_source(
            fresh,
            cwd=self.cwd,
            source_transcript_mtime=3,
            text="fresh same cwd should win",
        )
        self._write_manifest_clean_source(
            other_cwd,
            cwd=self.cwd / "other",
            source_transcript_mtime=5,
            text="newer different cwd should not win",
        )

        with mock.patch(
            "aippocampus_runtime.source.clean_source_resolver.core.default_thread_clean_source_dir",
            return_value=stale,
        ):
            resolved = resolve_mcp_clean_source_dir(
                cwd=self.cwd,
                clean_source_dir=None,
            )

        self.assertEqual(resolved, fresh.resolve())

    def test_mcp_default_resolution_keeps_explicit_clean_source_dir(self) -> None:
        threads = self.cwd / "registry" / "threads"
        explicit = threads / "session-explicit" / "clean-source"
        fresh = threads / "session-fresh" / "clean-source"
        self._write_manifest_clean_source(
            explicit,
            cwd=self.cwd,
            source_transcript_mtime=1,
            text="explicit should stay selected",
        )
        self._write_manifest_clean_source(
            fresh,
            cwd=self.cwd,
            source_transcript_mtime=3,
            text="fresh default candidate should not override explicit",
        )

        with mock.patch(
            "aippocampus_runtime.source.clean_source_resolver.core.default_thread_clean_source_dir",
            return_value=explicit,
        ):
            resolved = resolve_mcp_clean_source_dir(
                cwd=self.cwd,
                clean_source_dir=explicit,
            )

        self.assertEqual(resolved, explicit)

    def test_mcp_default_resolution_preserves_explicit_symlink_spelling(self) -> None:
        target_root = self.cwd / "private" / "var"
        symlink_root = self.cwd / "var"
        target_clean = target_root / "session-explicit" / "clean-source"
        try:
            target_root.mkdir(parents=True)
            os.symlink(target_root, symlink_root, target_is_directory=True)
        except (AttributeError, NotImplementedError, OSError) as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")

        explicit = symlink_root / "session-explicit" / "clean-source"
        self._write_manifest_clean_source(
            target_clean,
            cwd=self.cwd,
            source_transcript_mtime=1,
            text="explicit symlink spelling should stay selected",
        )

        with mock.patch(
            "aippocampus_runtime.source.clean_source_resolver.core.default_thread_clean_source_dir",
            return_value=target_clean,
        ):
            resolved = resolve_mcp_clean_source_dir(
                cwd=self.cwd,
                clean_source_dir=explicit,
            )

        self.assertEqual(resolved, explicit)
        self.assertEqual(core.path_identity_key(resolved), core.path_identity_key(target_clean))
        self.assertNotEqual(str(resolved), str(target_clean.resolve()))

    def test_mcp_default_apw_followthrough_ignores_project_local_legacy_clean_source(self) -> None:
        legacy_clean = self.cwd / ".aippocampus" / "clean-source"
        self._write_message(
            legacy_clean,
            {
                "message_id": "msg-legacy-trap-apw",
                "turn_id": "turn-legacy-trap-apw",
                "turn_index": 99,
                "source_id": "src-legacy-trap-apw",
                "source_line": 99,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "legacy trap smooth contributor workflow role partition anchor should not win default MCP.",
            },
        )
        self._write_message(
            self.clean,
            {
                "message_id": "msg-current-default-apw",
                "turn_id": "turn-current-default-apw",
                "turn_index": 12,
                "source_id": "src-current-default-apw",
                "source_line": 42,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "current registry smooth contributor workflow role partition anchor is the MCP default APW source.",
            },
        )

        recall_payload = self._call_tool_payload(
            "agent_recall",
            {
                "query": "smooth contributor workflow role partition anchor",
                "cwd": str(self.cwd),
                "registry_dir": str(self.cwd / "registry"),
                "apw_fallback": True,
                "last_recall_path": str(self.cwd / "mcp-default-last-recall.json"),
                "detail": "full",
            },
        )

        self.assertTrue(recall_payload["associative_path_policy"]["apw_candidate_input_available"])
        self.assertEqual(recall_payload["associative_path_fallback"]["status"], "route_candidate")
        request_index = recall_payload["associative_path_fallback"]["request_index"]
        recall_selector = recall_payload["recall_selector_id"]
        self.assertEqual(request_index, 2)
        self.assertTrue(str(recall_selector).startswith("sel_"))

        deepen_payload = self._call_tool_payload(
            "agent_deepen",
            {
                "request_index": request_index,
                "recall_selector": recall_selector,
                "last_recall_path": str(self.cwd / "mcp-default-last-recall.json"),
                "cwd": str(self.cwd),
                "detail": "full",
            },
        )
        window_text = "\n".join(
            str(message.get("text") or "")
            for message in deepen_payload["result"]["source_window"]["messages"]
            if isinstance(message, dict)
        )
        self.assertIn("current registry smooth contributor workflow role partition anchor", window_text)
        self.assertNotIn("legacy trap smooth contributor workflow role partition anchor", window_text)


if __name__ == "__main__":
    unittest.main()
