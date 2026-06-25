from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from aippocampus_runtime.local_file_lock import (
    OwnerCheckedFileLease,
    OwnerCheckedLeaseBusyError,
)


class OwnerCheckedFileLeaseTests(unittest.TestCase):
    def test_recovers_stale_lock_and_releases_own_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".writer.lock"
            lock_path.write_text(
                json.dumps({"owner_token": "old-owner", "pid": 999999}),
                encoding="utf-8",
            )
            stale_time = time.time() - 30
            os.utime(lock_path, (stale_time, stale_time))

            with OwnerCheckedFileLease(
                lock_path,
                lock_kind="unit_test_writer",
                stale_after_seconds=1,
            ) as lease:
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["owner_token"], lease.owner_token)
                self.assertTrue(payload["recovered_stale_lock"])

            self.assertFalse(lock_path.exists())

    def test_active_lock_reports_busy_without_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".writer.lock"
            with OwnerCheckedFileLease(
                lock_path,
                lock_kind="unit_test_writer",
                stale_after_seconds=60,
            ):
                with self.assertRaises(OwnerCheckedLeaseBusyError):
                    with OwnerCheckedFileLease(
                        lock_path,
                        lock_kind="unit_test_writer",
                        stale_after_seconds=60,
                        wait_timeout_seconds=0.01,
                    ):
                        self.fail("second active lock should not acquire")

    def test_release_preserves_replaced_owner_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".writer.lock"
            lease = OwnerCheckedFileLease(
                lock_path,
                lock_kind="unit_test_writer",
                stale_after_seconds=60,
            )
            lease.__enter__()
            try:
                assert lease.fd is not None
                os.close(lease.fd)
                lease.fd = None
                lock_path.write_text(
                    json.dumps({"owner_token": "fresh-owner", "pid": 123}),
                    encoding="utf-8",
                )
            finally:
                lease.__exit__(None, None, None)

            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["owner_token"], "fresh-owner")
            self.assertEqual(lease.release_diagnostic["reason"], "owner_token_changed")


if __name__ == "__main__":
    unittest.main()
