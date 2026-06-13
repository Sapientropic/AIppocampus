from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.continuity_domain_salience_adapter import (  # noqa: E402
    adapt_salience_sidecar_to_continuity_domains,
    salience_rows_to_continuity_domain_events,
)
from aippocampus_runtime.recall.continuity_domains import (  # noqa: E402
    load_continuity_domain_events,
    load_continuity_domains_snapshot,
)


def _source_ref(index: int = 1) -> dict[str, object]:
    return {
        "thread_key": "salience-thread",
        "message_id": f"msg-{index}",
        "turn_id": f"turn-{index}",
        "turn_index": index,
        "source_line": index,
        "role": "user",
    }


def _salience_row(
    event_kind: str,
    *,
    index: int = 1,
    refs: list[dict[str, object]] | None = None,
    reason_codes: list[str] | None = None,
    score: float = 0.8,
) -> dict[str, object]:
    return {
        "schema_version": "aippocampus.event_salience.v1",
        "event_id": f"evt-sal-{event_kind}-{index}",
        "authority": "navigation_intake_metadata",
        "event_kind": event_kind,
        "candidate_action": "select",
        "salience_score": score,
        "salience_bucket": "high",
        "reason_codes": reason_codes or [f"{event_kind}_cue"],
        "source_refs": refs if refs is not None else [_source_ref(index)],
    }


def _write_clean_source(root: Path, *, message_count: int = 6) -> Path:
    clean = root / "clean-source"
    clean.mkdir(parents=True, exist_ok=True)
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for index in range(1, message_count + 1):
            fh.write(
                json.dumps(
                    {
                        "message_id": f"msg-{index}",
                        "turn_id": f"turn-{index}",
                        "turn_index": index,
                        "source_line": index,
                        "role": "user",
                        "text": f"public fixture source row {index}",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    (clean / "turns.jsonl").write_text("", encoding="utf-8")
    return clean


class ContinuityDomainSalienceAdapterTests(unittest.TestCase):
    def test_salience_rows_map_conservative_event_families_and_defer_unsafe_rows(self) -> None:
        rows = [
            _salience_row("explicit_user_correction", index=1),
            _salience_row("failed_command_or_test", index=2),
            _salience_row("rejected_route_or_failed_assumption", index=3),
            _salience_row("unresolved_frontier_or_blocker", index=4),
            _salience_row("scope_boundary_clarification", index=5),
            _salience_row(
                "durable_preference_or_style",
                index=6,
                refs=[_source_ref(6), _source_ref(7)],
            ),
            _salience_row("supersession_or_currentness", index=8),
            _salience_row("explicit_user_correction", index=9, refs=[]),
        ]

        report = salience_rows_to_continuity_domain_events(rows)

        event_kinds = [event["event_kind"] for event in report["candidate_events"]]
        self.assertEqual(
            event_kinds,
            [
                "correction_source_added",
                "correction_source_added",
                "counter_source_added",
                "boundary_pinned",
                "boundary_pinned",
                "domain_created",
            ],
        )
        self.assertEqual(report["metrics"]["candidate_event_count"], 6)
        self.assertEqual(report["metrics"]["deferred_event_count"], 2)
        self.assertEqual(
            report["candidate_events"][0]["producer_event_kind"],
            "explicit_user_correction",
        )
        self.assertIn("producer_score", report["candidate_events"][0])
        self.assertIn(
            "explicit_user_correction_cue",
            report["candidate_events"][0]["producer_reason_codes"],
        )
        self.assertIn("currentness_target_domain_unresolved", report["deferred_reason_counts"])
        self.assertIn("missing_source_refs", report["deferred_reason_counts"])
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("public fixture source row", serialized)
        self.assertIn("source_reopen_required_before_claim", serialized)

    def test_report_mode_and_disabled_write_do_not_mutate_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = _write_clean_source(root)
            sidecar = root / "subconscious_event_salience.jsonl"
            events_path = clean / "continuity-domain-events.jsonl"
            snapshot_dir = root / "continuity-domain-snapshots"
            row = _salience_row("failed_command_or_test", index=1)
            sidecar.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            report = adapt_salience_sidecar_to_continuity_domains(
                sidecar,
                events_path=events_path,
                snapshot_dir=snapshot_dir,
                clean_source_dir=clean,
                mode="report",
                enabled=False,
                publish=True,
            )
            disabled = adapt_salience_sidecar_to_continuity_domains(
                sidecar,
                events_path=events_path,
                snapshot_dir=snapshot_dir,
                clean_source_dir=clean,
                mode="write_when_enabled",
                enabled=False,
                publish=True,
            )

        self.assertTrue(report["ok"])
        self.assertEqual(report["mode"], "report")
        self.assertEqual(report["write_report"]["status"], "not_requested")
        self.assertEqual(disabled["write_report"]["status"], "disabled_by_policy")
        self.assertFalse(events_path.exists())

    def test_enabled_write_appends_dedupes_and_publishes_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = _write_clean_source(root)
            sidecar = root / "subconscious_event_salience.jsonl"
            events_path = clean / "continuity-domain-events.jsonl"
            snapshot_dir = root / "continuity-domain-snapshots"
            row = _salience_row("rejected_route_or_failed_assumption", index=1)
            sidecar.write_text(
                "\n".join(
                    [
                        json.dumps(row, ensure_ascii=False),
                        json.dumps(row, ensure_ascii=False),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            first = adapt_salience_sidecar_to_continuity_domains(
                sidecar,
                events_path=events_path,
                snapshot_dir=snapshot_dir,
                clean_source_dir=clean,
                mode="write_when_enabled",
                enabled=True,
                publish=True,
            )
            second = adapt_salience_sidecar_to_continuity_domains(
                sidecar,
                events_path=events_path,
                snapshot_dir=snapshot_dir,
                clean_source_dir=clean,
                mode="write_when_enabled",
                enabled=True,
                publish=True,
            )
            events = load_continuity_domain_events(events_path, clean_source_dir=clean)
            snapshot = load_continuity_domains_snapshot(snapshot_dir / "latest.json")

        self.assertEqual(first["write_report"]["appended_event_count"], 1)
        self.assertEqual(first["write_report"]["duplicate_event_count"], 1)
        self.assertEqual(second["write_report"]["appended_event_count"], 0)
        self.assertEqual(second["write_report"]["duplicate_event_count"], 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_kind"], "counter_source_added")
        self.assertIsNotNone(snapshot)
        self.assertEqual(len((snapshot or {}).get("domains") or []), 1)


if __name__ == "__main__":
    unittest.main()
