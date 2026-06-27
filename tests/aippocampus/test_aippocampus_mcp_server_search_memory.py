from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.product_probe_helpers import call_mcp_tool_payload


class AippocampusMcpServerSearchMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_registry_thread(self, *, anchor: str) -> None:
        clean = self.cwd / "registry-thread" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_mcp_open_source",
                    "message_id": "msg_mcp_open_source",
                    "source_line": 515,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 9,
                    "is_final": True,
                    "text": f"The opened MCP source window contains {anchor}.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:mcp-open-source",
                            "title": "MCP open source",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    clean / "messages.jsonl"
                                )
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_search_memory_open_source_compact_returns_bounded_source_snippet(self) -> None:
        anchor = "MCP compact open-source anchor 明明还在本地"
        self._write_registry_thread(anchor=anchor)

        search_payload = call_mcp_tool_payload(
            "search_memory",
            {
                "query": anchor,
                "scope": "all_registered_sources",
                "registry_dir": str(self.cwd),
                "cwd": str(self.cwd),
            },
        )
        action = search_payload["foreground_action"]

        self.assertEqual(action["id"], "open_registry_search_source_window")
        self.assertEqual(action["tool_name"], "search_memory")
        self.assertTrue(action["arguments"]["open_source"])

        open_payload = call_mcp_tool_payload(
            "search_memory",
            {
                **action["arguments"],
                "registry_dir": str(self.cwd),
                "cwd": str(self.cwd),
            },
        )

        self.assertEqual(open_payload["kind"], "aippocampus_registry_source_window")
        self.assertEqual(open_payload["source_boundary"]["authority"], "source_open")
        self.assertEqual(
            open_payload["primary_source_snippet"]["message_id"],
            action["arguments"]["message_id"],
        )
        self.assertIn(anchor, open_payload["primary_source_snippet"]["text"])
        self.assertIn(anchor, json.dumps(open_payload["source_window_preview"], ensure_ascii=False))
        self.assertNotIn("source_window", open_payload)
        self.assertNotIn(str(self.cwd), json.dumps(open_payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
