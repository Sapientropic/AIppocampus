from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime import core
from aippocampus_runtime.mcp.current_source_route_policy import (
    primary_deepen_followthrough_reopenable,
)
from aippocampus_runtime.source import search
from aippocampus_runtime.source.current_source_window import open_current_thread_source_window
from tests.aippocampus.product_probe_helpers import call_mcp_tool_payload


class RouteNoteRecallPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.registry_root = self.cwd / "registry-default"
        self.env_patch = patch.dict(
            os.environ,
            {"AIPPOCAMPUS_REGISTRY_DIR": str(self.registry_root)},
        )
        self.env_patch.start()
        self.clean = core.default_thread_clean_source_dir(self.cwd)
        self.clean.mkdir(parents=True)
        (self.clean / "messages.jsonl").write_text("", encoding="utf-8")
        (self.clean / "turns.jsonl").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmp.cleanup()

    def _append_message(self, row: dict[str, object]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": row.get("turn_id"),
                        "turn_index": row.get("turn_index"),
                        "message_ids": [row.get("message_id") or row.get("id")],
                        "assistant_phase": row.get("phase") or row.get("role"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def _write_route_note_fixture(self, *, final_text: str) -> str:
        self._append_message(
            {
                "id": "msg_route_note_final",
                "message_id": "msg_route_note_final",
                "turn_id": "turn_route_note",
                "source_id": "src_route_note",
                "source_line": 80,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 8,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": final_text,
            }
        )
        raw_commentary = (
            "I will first check old source, then decide whether to change source_texture "
            "with C:\\private\\trace and api_key=sk-private."
        )
        source_ref = {
            "source_id": "src_route_note",
            "message_id": "msg_route_note_final",
            "turn_id": "turn_route_note",
            "turn_index": 8,
            "line": 80,
        }
        (self.clean / "route-notes.jsonl").write_text(
            json.dumps(
                {
                    "route_id": "route_note_source_texture",
                    "origin": "route_note",
                    "status": "ready",
                    "readiness_class": "source_reopen_ready",
                    "note_type": "decision_breadcrumb",
                    "title": "Commentary route note: decision breadcrumb",
                    "why_lit": "A process note records a route decision.",
                    "navigation_only": True,
                    "source_reopen_required_before_claim": True,
                    "route_anchor_terms": ["source_texture", "old", "source", "decide"],
                    "source_refs": [source_ref],
                    "joined_evidence_refs": [
                        {
                            "evidence_kind": "final_answer",
                            "message_id": "msg_route_note_final",
                            "source_ref": source_ref,
                        }
                    ],
                    "reason_codes": [
                        "route_note",
                        "decision_breadcrumb",
                        "joined_to_adjacent_evidence",
                    ],
                    "diagnostic_commentary": raw_commentary,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return raw_commentary

    def test_search_finds_joined_route_note_without_exposing_commentary(self) -> None:
        raw_commentary = self._write_route_note_fixture(
            final_text="I checked the old source and kept source_texture as a sidecar."
        )

        result = search.search_clean_source(
            self.cwd,
            ["previous agent decided to check old source before changing source_texture"],
            limit=5,
        )

        match = result["matches"][0]
        self.assertEqual(match["source"], "route_note")
        self.assertEqual(match["message_id"], "msg_route_note_final")
        self.assertEqual(match["source_line"], 80)
        encoded = json.dumps(match, ensure_ascii=False)
        self.assertNotIn(raw_commentary, encoded)
        self.assertNotIn("C:\\private", encoded)
        self.assertNotIn("sk-private", encoded)
        self.assertNotIn("api_key", encoded)
        window = open_current_thread_source_window(
            cwd=self.cwd,
            clean_source_dir=self.clean,
            message_id=match["message_id"],
            context_lines=0,
        )
        self.assertTrue(window["ok"], window)
        self.assertIn("kept source_texture as a sidecar", window["source_window"][0]["text"])

    def test_mcp_recall_deepens_joined_route_note_source_anchor(self) -> None:
        raw_commentary = self._write_route_note_fixture(
            final_text=(
                "Joined final anchor RN-42 confirms the previous agent decided "
                "to check old source before changing source_texture, then kept "
                "source_texture as the sidecar."
            )
        )
        cache_path = self.cwd / "route-note-last-recall.json"
        recall_payload = call_mcp_tool_payload(
            "agent_recall",
            {
                "query": "previous agent decided to check old source before changing source_texture",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "last_recall_path": str(cache_path),
                "detail": "compact",
            },
        )

        action = recall_payload["foreground_action"]
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertIn("recall_selector", action["arguments"])
        encoded = json.dumps(recall_payload, ensure_ascii=False)
        self.assertNotIn(raw_commentary, encoded)
        self.assertNotIn("C:\\private", encoded)
        self.assertNotIn("sk-private", encoded)

        deepen_payload = call_mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": action["arguments"]["request_index"],
                "recall_selector": action["arguments"]["recall_selector"],
                "last_recall_path": str(cache_path),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "detail": "full",
            },
        )

        self.assertEqual(deepen_payload["status"], "ok")
        self.assertEqual(
            deepen_payload["result"]["source_refs"][0]["message_id"],
            "msg_route_note_final",
        )
        window_text = "\n".join(
            str(message.get("text") or "")
            for message in deepen_payload["result"]["source_window"]["messages"]
            if isinstance(message, dict)
        )
        self.assertIn("Joined final anchor RN-42", window_text)

    def test_route_note_primary_deepen_rejects_malformed_source_ref_containers(self) -> None:
        for packet in (
            {
                "output_mode": "reopenable_route",
                "route_kind": "route_note",
                "source_refs": [{}],
            },
            {
                "output_mode": "reopenable_route",
                "route_kind": "route_note",
                "joined_evidence_refs": [{"kind": "not_a_source"}],
            },
            {
                "output_mode": "reopenable_route",
                "route_kind": "route_note",
                "source_refs": [{"line": 12}],
            },
        ):
            self.assertFalse(primary_deepen_followthrough_reopenable([packet]))

        self.assertTrue(
            primary_deepen_followthrough_reopenable(
                [
                    {
                        "output_mode": "reopenable_route",
                        "route_kind": "route_note",
                        "joined_evidence_refs": [
                            {
                                "source_ref": {
                                    "thread_key": "session:route-note",
                                    "message_id": "msg-route-note",
                                }
                            }
                        ],
                    }
                ]
            )
        )
        self.assertTrue(
            primary_deepen_followthrough_reopenable(
                [
                    {
                        "output_mode": "reopenable_route",
                        "route_kind": "route_note",
                        "source_refs": [
                            {
                                "source_id": "clean:route-note",
                                "message_id": "msg-route-note",
                            }
                        ],
                    }
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
