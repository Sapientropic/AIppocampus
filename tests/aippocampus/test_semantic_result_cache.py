from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import semantic_result_cache


class SemanticResultCacheLockTests(unittest.TestCase):
    def test_cache_file_lock_uses_owner_checked_lease_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic-cache.json"
            lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")

            with semantic_result_cache._cache_file_lock(cache_path):
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["kind"], "aippocampus_semantic_result_cache_lock")
                self.assertEqual(payload["lock_kind"], "semantic_result_cache")
                self.assertTrue(payload["owner_token"])

            self.assertFalse(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
