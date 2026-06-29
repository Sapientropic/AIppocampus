from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.source import search
from aippocampus_runtime.source.io_kernel import write_jsonl_dict_rows

FORBIDDEN_COMPACT_POLICY_FIELDS = (
    "claim_boundary",
    "source_reopen_boundary",
    "source_boundary",
    "policy_boundary",
    "output_boundary",
)


class SearchCompactPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.source = self.cwd / "clean-source"
        self.source.mkdir()
        write_jsonl_dict_rows(
            self.source / "messages.jsonl",
            [
                {
                    "message_id": "msg_final",
                    "turn_id": "turn_1",
                    "turn_index": 1,
                    "source_line": 1,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "AIppocampus 是清洗后的 source-backed continuity route.",
                    "scope_labels": ["technical_work"],
                }
            ],
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:compact-policy",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    self.source / "messages.jsonl"
                                ),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _search_json(self, *args: str) -> tuple[int, dict]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    *args,
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )
        return code, json.loads(stdout.getvalue())

    def _registry_search_json(self, *args: str) -> tuple[int, dict]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    *args,
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        return code, json.loads(stdout.getvalue())

    def test_compact_search_strips_policy_fields_but_full_keeps_diagnostics(self) -> None:
        hit_code, hit = self._search_json("AIppocampus")
        miss_code, miss = self._search_json("zzzz-no-match-aippocampus-probe")
        full_hit_code, full_hit = self._search_json("AIppocampus", "--detail", "full")
        full_miss_code, full_miss = self._search_json(
            "zzzz-no-match-aippocampus-probe",
            "--detail",
            "full",
        )

        self.assertEqual(hit_code, 0)
        self.assertEqual(miss_code, 1)
        self.assertEqual(hit["foreground_action"]["id"], "reopen_search_match_source")
        self.assertEqual(miss["foreground_action"]["id"], "refine_or_recall")
        encoded_compact = json.dumps({"hit": hit, "miss": miss}, ensure_ascii=False)
        for field in FORBIDDEN_COMPACT_POLICY_FIELDS:
            self.assertNotIn(field, encoded_compact)

        self.assertEqual(full_hit_code, 0)
        self.assertEqual(full_miss_code, 1)
        self.assertEqual(full_hit["claim_permission"], "bounded_search_receipt_requires_reopen")
        self.assertEqual(full_hit["source_boundary"]["authority"], "bounded_evidence")
        self.assertEqual(
            full_hit["foreground_action"]["claim_boundary"],
            "source_reopen_required_before_claim",
        )
        self.assertEqual(full_miss["claim_permission"], "no_claim_before_source_match")
        self.assertTrue(full_miss["source_boundary"]["search_miss_is_not_absence_of_memory"])
        self.assertEqual(full_miss["foreground_action"]["claim_boundary"], "no_claim_before_reopen")

    def test_public_registry_source_open_omits_local_selectors_and_source_text(self) -> None:
        query = "source-backed continuity route"
        public_open_code, public_open = self._registry_search_json(
            "--open-source",
            "--thread-key",
            "session:compact-policy",
            "--message-id",
            "msg_final",
            "--line",
            "1",
            "--public",
        )
        encoded = json.dumps(public_open, ensure_ascii=False)

        self.assertEqual(public_open_code, 0)
        self.assertEqual(public_open["kind"], "aippocampus_registry_source_public_receipt")
        self.assertTrue(public_open["public_output"])
        self.assertTrue(public_open["source_text_omitted"])
        self.assertEqual(public_open["foreground_action"]["id"], "rerun_registry_search_locally")
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("source_window", encoded)
        self.assertNotIn("--open-source", encoded)
        self.assertNotIn(query, encoded)


if __name__ == "__main__":
    unittest.main()
