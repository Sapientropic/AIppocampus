from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.core import default_thread_clean_source_dir
from aippocampus_runtime.recall.agent_recall_cache import (
    write_last_recall_cache,
    write_recall_selector_snapshot,
)
from aippocampus_runtime.recall.continuity_domains import clean_source_fingerprint
from tests.aippocampus.product_probe_helpers import call_mcp_tool_payload


class McpSearchMemoryLastRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = default_thread_clean_source_dir(self.cwd)
        self.clean.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_messages(self, clean_dir: Path, rows: list[dict[str, object]]) -> None:
        clean_dir.mkdir(parents=True, exist_ok=True)
        with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_cache(self, requests: list[dict[str, object]], *, query: str) -> Path:
        cache_path = self.cwd / "last-recall.json"
        ok = write_last_recall_cache(
            requests,
            query=query,
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.cwd,
            macro_state_path=None,
            project="fixture",
            max_matches=5,
            schema_version="agent-continuity-path-v1",
            path=cache_path,
        )
        self.assertTrue(ok)
        return cache_path

    def test_search_memory_last_recall_scope_searches_cached_route_set(self) -> None:
        route_clean = self.cwd / "route-thread" / "clean-source"
        self._write_messages(
            route_clean,
            [
                {
                    "id": "msg_route",
                    "message_id": "msg_route",
                    "source_line": 5,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 3,
                    "is_final": True,
                    "text": "The MCP last recall exact phrase lives in the remembered route.",
                }
            ],
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:last-recall",
                            "title": "Last recall route",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    route_clean / "messages.jsonl"
                                )
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_last",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:last-recall",
                        "route_id": "route_last",
                    },
                }
            ],
            query="last recall route",
        )
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        payload = call_mcp_tool_payload(
            "search_memory",
            {
                "query": "last recall exact phrase",
                "cwd": str(self.cwd),
                "last_recall_path": str(cache_path),
                "recall_selector": selector,
                "scope": "last_recall_candidates",
            },
        )
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_last_recall_source_search")
        self.assertEqual(payload["mcp_search_scope"], "last_recall_candidates")
        self.assertEqual(payload["match_count"], 1)
        self.assertNotIn("matches", payload)
        self.assertEqual(payload["source_hits"][0]["request_index"], 1)
        self.assertIn(
            "aippocampus search --open-source --thread-key session:last-recall "
            "--message-id msg_route --line 5 --json",
            encoded,
        )
        self.assertNotIn("aippocampus agent deepen --request 1", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_search_memory_last_recall_source_ref_can_open_exact_source_hit(self) -> None:
        self._write_messages(
            self.clean,
            [
                {
                    "id": "msg_final",
                    "message_id": "msg_final",
                    "source_line": 13,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "text": "The MCP source-ref open exact anchor lives in current clean source.",
                }
            ],
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_current_source_ref",
                    "handle": {
                        "kind": "source_ref",
                        "route_id": "route_current_source_ref",
                        "source_refs": [{"message_id": "msg_final", "line": 13}],
                        "source_fingerprint": clean_source_fingerprint(self.clean),
                    },
                }
            ],
            query="MCP source-ref open exact anchor",
        )
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        search_payload = call_mcp_tool_payload(
            "search_memory",
            {
                "query": "MCP source-ref open exact anchor",
                "cwd": str(self.cwd),
                "last_recall_path": str(cache_path),
                "recall_selector": selector,
                "scope": "last_recall_candidates",
            },
        )
        self.assertEqual(
            search_payload["foreground_action"]["id"],
            "open_last_recall_search_hit_source_window",
        )

        open_payload = call_mcp_tool_payload(
            "search_memory",
            {
                "query": "MCP source-ref open exact anchor",
                "cwd": str(self.cwd),
                "last_recall_path": str(cache_path),
                "recall_selector": selector,
                "scope": "last_recall_candidates",
                "open_source": True,
                "request_index": 1,
                "message_id": "msg_final",
                "line": 13,
                "detail": "full",
            },
        )
        opened_text = json.dumps(open_payload["source_window"], ensure_ascii=False)

        self.assertEqual(open_payload["kind"], "aippocampus_last_recall_source_window")
        self.assertEqual(open_payload["status"], "source_open")
        self.assertEqual(open_payload["source_boundary"]["authority"], "source_open")
        self.assertIn("MCP source-ref open exact anchor", opened_text)
        self.assertTrue(open_payload["source_anchor_profile"]["exact_phrase_match"])
        self.assertGreaterEqual(open_payload["source_anchor_profile"]["matched_anchor_count"], 1)
        self.assertGreaterEqual(len(open_payload["anchor_hits"]), 1)
        self.assertNotIn(str(self.cwd), json.dumps(open_payload, ensure_ascii=False))

    def test_search_memory_last_recall_prefers_exact_hit_over_loud_partial_hit(self) -> None:
        route_clean = self.cwd / "mcp-ranking-thread" / "clean-source"
        exact_phrase = "amber cedar lantern"
        self._write_messages(
            route_clean,
            [
                {
                    "id": "msg_partial_loud",
                    "message_id": "msg_partial_loud",
                    "source_line": 6,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "amber amber amber cedar cedar cedar "
                        "nearby route text without the requested adjacent phrase"
                    ),
                },
                {
                    "id": "msg_exact",
                    "message_id": "msg_exact",
                    "source_line": 32,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": f"The remembered source says {exact_phrase} clearly.",
                },
            ],
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:mcp-ranking",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    route_clean / "messages.jsonl"
                                )
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_mcp_ranking",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:mcp-ranking",
                        "route_id": "route_mcp_ranking",
                    },
                }
            ],
            query=exact_phrase,
        )
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        search_payload = call_mcp_tool_payload(
            "search_memory",
            {
                "query": exact_phrase,
                "cwd": str(self.cwd),
                "last_recall_path": str(cache_path),
                "recall_selector": selector,
                "scope": "last_recall_candidates",
            },
        )
        encoded = json.dumps(search_payload, ensure_ascii=False)

        self.assertEqual(
            search_payload["foreground_action"]["id"],
            "open_last_recall_search_hit_source_window",
        )
        self.assertIn("--message-id msg_exact", search_payload["foreground_action"]["command"])
        self.assertNotIn("matches", search_payload)
        self.assertNotIn("msg_partial_loud", encoded)

        open_payload = call_mcp_tool_payload(
            "search_memory",
            {
                "query": exact_phrase,
                "cwd": str(self.cwd),
                "last_recall_path": str(cache_path),
                "recall_selector": selector,
                "scope": "last_recall_candidates",
                "open_source": True,
                "request_index": 1,
                "message_id": "msg_exact",
                "line": 32,
                "detail": "full",
            },
        )

        self.assertEqual(open_payload["source_boundary"]["authority"], "source_open")
        self.assertTrue(open_payload["source_anchor_profile"]["exact_phrase_match"])
        self.assertIn(exact_phrase, json.dumps(open_payload["source_window"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
