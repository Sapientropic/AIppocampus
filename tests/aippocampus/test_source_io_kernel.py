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

    def test_io_kernel_counts_malformed_rows_without_retaining_payload(self) -> None:
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

    def test_jsonl_writer_does_not_reuse_fixed_stale_tmp_path(self) -> None:
        path = self.root / "rows.jsonl"
        stale_fixed_tmp = path.with_suffix(path.suffix + ".tmp")
        stale_fixed_tmp.write_text('{"kind":"stale"}\n', encoding="utf-8")

        io_kernel.write_jsonl_dict_rows(path, [{"kind": "fresh"}])

        self.assertEqual(io_kernel.load_jsonl_dict_rows(path).rows, [{"kind": "fresh"}])
        self.assertEqual(stale_fixed_tmp.read_text(encoding="utf-8"), '{"kind":"stale"}\n')

    def test_strict_jsonl_loader_reports_line_context(self) -> None:
        path = self.root / "strict.jsonl"
        path.write_text('{"kind":"ok"}\n[]\n', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "line 2 is not a JSON object"):
            io_kernel.load_jsonl_dict_rows_strict(path)

    def test_jsonl_line_field_loader_attaches_audit_line_numbers(self) -> None:
        path = self.root / "lined.jsonl"
        path.write_text('{"kind":"first"}\nnot-json\n{"kind":"third"}\n', encoding="utf-8")

        result = io_kernel.load_jsonl_dict_rows_with_line_field(
            path,
            line_field="_line",
        )

        self.assertEqual(
            result.rows,
            [{"kind": "first", "_line": 1}, {"kind": "third", "_line": 3}],
        )
        self.assertEqual(result.loss["invalid_json_line_count"], 1)
        self.assertEqual(result.loss["invalid_json_line_numbers"], [2])

    def test_jsonl_append_writer_returns_row_count_and_preserves_existing_rows(self) -> None:
        path = self.root / "nested" / "events.jsonl"
        io_kernel.write_jsonl_dict_rows(path, [{"kind": "first"}])

        written = io_kernel.append_jsonl_dict_rows(
            path,
            [{"kind": "second", "value": 2}, {"kind": "third"}],
            sort_keys=True,
        )
        result = io_kernel.load_jsonl_dict_rows(path)

        self.assertEqual(written, 2)
        self.assertEqual(
            result.rows,
            [{"kind": "first"}, {"kind": "second", "value": 2}, {"kind": "third"}],
        )
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
        self.assertEqual(
            io_kernel.source_ref_key_set(
                [
                    {"thread_id": "thread-a", "message_id": "msg-1", "assistant_line": 42},
                    {"thread_key": "thread-a", "message_id": "msg-1", "source_line": 42},
                    {"ignored": ""},
                ]
            ),
            {("thread-a", "msg-1", "", "42")},
        )

    def test_source_ref_identity_key_preserves_source_id_and_line_anchor(self) -> None:
        self.assertEqual(
            io_kernel.source_ref_identity_key(
                {
                    "source_id": "src-1",
                    "thread_key": "thread-a",
                    "message_id": "msg-1",
                    "turn_id": "turn-7",
                    "line": 42,
                }
            ),
            ("src-1", "thread-a", "msg-1", "turn-7", "42"),
        )
        self.assertEqual(
            io_kernel.source_ref_key(
                {
                    "source_id": "src-1",
                    "thread_key": "thread-a",
                    "message_id": "msg-1",
                    "turn_id": "turn-7",
                    "line": 42,
                }
            ),
            ("thread-a", "msg-1", "turn-7", "src-1"),
        )
        self.assertEqual(
            io_kernel.source_ref_identity_key(
                {
                    "source_ref": "clean-source/messages.jsonl:2",
                    "thread_key": "thread-a",
                }
            ),
            ("clean-source/messages.jsonl:2", "thread-a", "", "", ""),
        )

    def test_clean_source_ref_requires_thread_and_anchor_by_default(self) -> None:
        self.assertIsNone(io_kernel.clean_source_ref({"thread_key": "thread-a"}))
        self.assertEqual(
            io_kernel.clean_source_ref({"thread_id": "thread-a", "source_id": "src-1"}),
            {"thread_key": "thread-a", "source_id": "src-1"},
        )


if __name__ == "__main__":
    unittest.main()
