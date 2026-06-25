from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from hypothesis import given, note, settings
    from hypothesis import strategies as st
except ModuleNotFoundError:
    HAVE_HYPOTHESIS = False

    def _skip_hypothesis(*_args: object, **_kwargs: object):
        def decorate(func: object) -> object:
            return unittest.skip(
                'Install the opt-in ".[test-quality]" extra to run the Hypothesis pilot.'
            )(func)

        return decorate

    def _identity_decorator(*_args: object, **_kwargs: object):
        def decorate(func: object) -> object:
            return func

        return decorate

    given = _skip_hypothesis
    settings = _identity_decorator

    def note(_message: object) -> None:
        return None

    st = None
else:
    HAVE_HYPOTHESIS = True

from aippocampus_runtime.local_file_lock import (
    OwnerCheckedFileLease,
    OwnerCheckedLeaseBusyError,
)

if HAVE_HYPOTHESIS:
    LOCK_KINDS = st.sampled_from(
        [
            "unit_test_writer",
            "sync_writer",
            "registry_writer",
            "semantic_cache_writer",
        ]
    )
    OWNER_TOKENS = st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters=["\x00", "\r", "\n"],
        ),
        min_size=1,
        max_size=40,
    ).map(lambda value: f"hypothesis_owner_{value}")
    STALE_AFTER_SECONDS = st.integers(min_value=1, max_value=10)
    STALE_EXTRA_AGE_SECONDS = st.integers(min_value=5, max_value=90)
    ACTIVE_AGE_SECONDS = st.integers(min_value=0, max_value=3)
    ACTIVE_STALE_AFTER_SECONDS = st.integers(min_value=30, max_value=120)
else:
    LOCK_KINDS = None
    OWNER_TOKENS = None
    STALE_AFTER_SECONDS = None
    STALE_EXTRA_AGE_SECONDS = None
    ACTIVE_AGE_SECONDS = None
    ACTIVE_STALE_AFTER_SECONDS = None


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

    @settings(max_examples=20, deadline=None)
    @given(
        lock_kind=LOCK_KINDS,
        stale_after_seconds=STALE_AFTER_SECONDS,
        stale_extra_age_seconds=STALE_EXTRA_AGE_SECONDS,
        old_owner=OWNER_TOKENS,
    )
    def test_property_recovers_stale_generation_and_releases_only_new_owner(
        self,
        lock_kind: str,
        stale_after_seconds: int,
        stale_extra_age_seconds: int,
        old_owner: str,
    ) -> None:
        note(
            f"lock_kind={lock_kind!r} stale_after={stale_after_seconds} "
            f"extra_age={stale_extra_age_seconds} old_owner={old_owner!r}"
        )
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".writer.lock"
            lock_path.write_text(
                json.dumps({"owner_token": old_owner, "pid": 999999}, ensure_ascii=False),
                encoding="utf-8",
            )
            stale_time = time.time() - stale_after_seconds - stale_extra_age_seconds
            os.utime(lock_path, (stale_time, stale_time))

            with OwnerCheckedFileLease(
                lock_path,
                lock_kind=lock_kind,
                stale_after_seconds=stale_after_seconds,
                payload_extra={"property_probe": True},
            ) as lease:
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["owner_token"], lease.owner_token)
                self.assertNotEqual(payload["owner_token"], old_owner)
                self.assertEqual(payload["lock_kind"], lock_kind)
                self.assertTrue(payload["recovered_stale_lock"])
                self.assertTrue(payload["property_probe"])
                self.assertGreaterEqual(
                    payload["stale_age_seconds"],
                    stale_after_seconds,
                )

            self.assertFalse(lock_path.exists())

    @settings(max_examples=20, deadline=None)
    @given(
        lock_kind=LOCK_KINDS,
        active_age_seconds=ACTIVE_AGE_SECONDS,
        stale_after_seconds=ACTIVE_STALE_AFTER_SECONDS,
        active_owner=OWNER_TOKENS,
    )
    def test_property_active_generation_stays_busy_until_stale_threshold(
        self,
        lock_kind: str,
        active_age_seconds: int,
        stale_after_seconds: int,
        active_owner: str,
    ) -> None:
        note(
            f"lock_kind={lock_kind!r} active_age={active_age_seconds} "
            f"stale_after={stale_after_seconds} active_owner={active_owner!r}"
        )
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".writer.lock"
            lock_path.write_text(
                json.dumps({"owner_token": active_owner, "pid": 12345}, ensure_ascii=False),
                encoding="utf-8",
            )
            active_time = time.time() - active_age_seconds
            os.utime(lock_path, (active_time, active_time))

            with self.assertRaises(OwnerCheckedLeaseBusyError):
                with OwnerCheckedFileLease(
                    lock_path,
                    lock_kind=lock_kind,
                    stale_after_seconds=stale_after_seconds,
                    wait_timeout_seconds=0.0,
                ):
                    self.fail("active lock should not be recovered before stale threshold")

            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["owner_token"], active_owner)

    @settings(max_examples=20, deadline=None)
    @given(lock_kind=LOCK_KINDS, fresh_owner=OWNER_TOKENS)
    def test_property_release_never_unlinks_replaced_owner_generation(
        self,
        lock_kind: str,
        fresh_owner: str,
    ) -> None:
        note(f"lock_kind={lock_kind!r} fresh_owner={fresh_owner!r}")
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / ".writer.lock"
            lease = OwnerCheckedFileLease(
                lock_path,
                lock_kind=lock_kind,
                stale_after_seconds=60,
            )
            lease.__enter__()
            try:
                acquired_owner = lease.owner_token
                assert lease.fd is not None
                os.close(lease.fd)
                lease.fd = None
                lock_path.write_text(
                    json.dumps({"owner_token": fresh_owner, "pid": 123}, ensure_ascii=False),
                    encoding="utf-8",
                )
            finally:
                lease.__exit__(None, None, None)

            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertNotEqual(acquired_owner, fresh_owner)
            self.assertEqual(payload["owner_token"], fresh_owner)
            self.assertEqual(lease.release_diagnostic["reason"], "owner_token_changed")


if __name__ == "__main__":
    unittest.main()
