from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.io_integrity import prepared_atomic_replace


class IoIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_interleaved_atomic_replace_writers_use_distinct_tmp_paths(self) -> None:
        path = self.root / "state.json"

        with prepared_atomic_replace(path) as first_tmp:
            first_tmp.write_text("first", encoding="utf-8")
            with prepared_atomic_replace(path) as second_tmp:
                second_tmp.write_text("second", encoding="utf-8")
                self.assertNotEqual(first_tmp, second_tmp)
            self.assertEqual(path.read_text(encoding="utf-8"), "second")
        self.assertEqual(path.read_text(encoding="utf-8"), "first")

        leftovers = list(self.root.glob(".*.aippocampus-*.tmp"))
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
