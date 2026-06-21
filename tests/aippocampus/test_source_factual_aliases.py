from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.source.factual_aliases import (
    SOURCE_FACTUAL_ALIASES_FILENAME,
    materialize_source_factual_aliases,
)


class SourceFactualAliasesTests(unittest.TestCase):
    def test_materializer_writes_navigation_only_factual_handles_without_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg-keepsake",
                        "turn_id": "turn-keepsake",
                        "source_line": 12,
                        "role": "user",
                        "text": "I stored the jade souvenir in the desk drawer.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = materialize_source_factual_aliases(clean)
            rows = [
                json.loads(line)
                for line in (clean / SOURCE_FACTUAL_ALIASES_FILENAME).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(rows[0]["authority"], "navigation_only")
        self.assertTrue(rows[0]["source_reopen_required"])
        self.assertEqual(rows[0]["source_refs"][0]["message_id"], "msg-keepsake")
        self.assertEqual(rows[0]["source_refs"][0]["line"], 12)
        self.assertIn("keepsake", rows[0]["query_aliases"])
        self.assertIn("location", rows[0]["route_terms"])
        dumped = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn("jade souvenir", dumped)
        self.assertNotIn("desk drawer", dumped)

    def test_materializer_filters_secret_shaped_terms_from_alias_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg-secret",
                        "source_line": 7,
                        "role": "user",
                        "text": "The token=sk-test-secret belongs in the drawer.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            materialize_source_factual_aliases(clean)
            raw = (clean / SOURCE_FACTUAL_ALIASES_FILENAME).read_text(encoding="utf-8")

        self.assertNotIn("sk-test-secret", raw)
        self.assertNotIn("token=", raw)

    def test_materializer_reports_messages_jsonl_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                "{bad-json}\n"
                + json.dumps(
                    {
                        "message_id": "msg-keepsake",
                        "source_line": 12,
                        "role": "user",
                        "text": "I kept the travel keepsake on the shelf.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = materialize_source_factual_aliases(clean)
            manifest = json.loads(
                (clean / "source-factual-aliases.manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["source_messages_jsonl_loss"]["invalid_json_line_count"], 1)
        self.assertEqual(manifest["source_messages_jsonl_loss"]["invalid_json_line_count"], 1)

if __name__ == "__main__":
    unittest.main()
