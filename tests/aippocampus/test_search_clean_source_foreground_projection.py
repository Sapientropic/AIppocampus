from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime import core
from aippocampus_runtime.contracts import foreground_action_contract_violations
from aippocampus_runtime.source import search


class SearchCleanSourceForegroundProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.source = core.default_thread_clean_source_dir(self.cwd)
        self.source.mkdir(parents=True)
        messages = [
            {
                "id": "msg_user",
                "source_line": 10,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "为什么我们要做 AIppocampus？",
            },
            {
                "id": "msg_final",
                "source_line": 13,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "AIppocampus 是清洗后的原文记忆库。",
            },
        ]
        with (self.source / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for message in messages:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_search_json_detail_full_keeps_operator_diagnostics(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "AIppocampus",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                    "--detail",
                    "full",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["entry_state"], "explicit_search_invoked")
        self.assertEqual(payload["route_state"], "source_refs_available")
        self.assertEqual(payload["claim_permission"], "bounded_search_receipt_requires_reopen")
        self.assertEqual(payload["source_boundary"]["authority"], "bounded_evidence")
        self.assertIn("query_match_profile", payload["matches"][0])
        self.assertIn("source_window_command", payload["matches"][0])

    def test_current_thread_search_suppresses_low_coverage_phrase_hits(self) -> None:
        with (self.source / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "id": "msg_generic_noise",
                        "source_line": 72,
                        "role": "assistant",
                        "phase": "final_answer",
                        "text": (
                            "No such source-backed route should be opened from "
                            "unrelated phrase fragments."
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "no such phrase zzzzz",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_phrase_like_matches")
        self.assertEqual(payload["match_count"], 0)
        self.assertGreaterEqual(payload["suppressed_low_coverage_match_count"], 1)
        self.assertEqual(payload["foreground_action"]["id"], "refine_or_recall")
        self.assertNotIn("source_boundary", payload)
        self.assertNotIn("recovery_actions", payload)
        self.assertNotIn("suppression_boundary", payload)
        self.assertEqual(foreground_action_contract_violations(payload), [])
