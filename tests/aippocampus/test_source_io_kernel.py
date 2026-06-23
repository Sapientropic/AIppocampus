from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.source import io_kernel


class SourceIoKernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_jsonl_reader_counts_malformed_rows_without_retaining_payload(self) -> None:
        path = self.root / "rows.jsonl"
        path.write_text(
            '{"kind":"ok","value":1}\n'
            'not-json\n'
            '[]\n'
            '\n',
            encoding="utf-8",
        )

        result = io_kernel.load_jsonl_dict_rows(path)
        warning = io_kernel.jsonl_loss_warning(
            result.loss,
            stage="unit",
            path_label="rows.jsonl",
        )

        self.assertEqual(result.rows, [{"kind": "ok", "value": 1}])
        self.assertEqual(result.loss["invalid_json_line_count"], 1)
        self.assertEqual(result.loss["non_object_line_count"], 1)
        self.assertEqual(result.loss["skipped_empty_line_count"], 1)
        self.assertEqual(result.loss["total_loss_count"], 2)
        self.assertEqual(warning["code"], "jsonl_read_degraded")
        self.assertNotIn("not-json", str(warning))

    def test_jsonl_writer_round_trips_through_reader(self) -> None:
        path = self.root / "nested" / "rows.jsonl"

        io_kernel.write_jsonl_dict_rows(path, [{"b": 2, "a": "字"}], sort_keys=True)
        result = io_kernel.load_jsonl_dict_rows(path)

        self.assertEqual(result.rows, [{"a": "字", "b": 2}])
        self.assertEqual(result.loss["total_loss_count"], 0)

    def test_source_ref_key_normalizes_historical_field_variants(self) -> None:
        self.assertEqual(
            io_kernel.source_ref_key(
                {
                    "thread_id": "thread-a",
                    "message_id": "msg-1",
                    "turn_index": 7,
                    "assistant_line": 42,
                }
            ),
            ("thread-a", "msg-1", "7", "42"),
        )
        self.assertEqual(
            io_kernel.source_ref_key(
                {
                    "thread_key": "thread-a",
                    "message_id": "msg-1",
                    "turn_id": "turn-7",
                    "source_line": 42,
                }
            ),
            ("thread-a", "msg-1", "turn-7", "42"),
        )

    def test_clean_source_ref_requires_thread_and_anchor_by_default(self) -> None:
        self.assertIsNone(io_kernel.clean_source_ref({"thread_key": "thread-a"}))
        self.assertEqual(
            io_kernel.clean_source_ref({"thread_id": "thread-a", "source_id": "src-1"}),
            {"thread_key": "thread-a", "source_id": "src-1"},
        )


if __name__ == "__main__":
    unittest.main()
