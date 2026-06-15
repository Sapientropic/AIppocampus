from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.coding import (
    episode_arc_private_adjudication as private_arcs,  # noqa: E402
)

PRIVATE_SENTINEL = "PRIVATE_EPISODE_ARC_TEXT_MUST_NOT_SURFACE"


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def registry_entry(root: Path, thread_key: str, *, rows: list[dict[str, object]], events: list[dict[str, object]]) -> dict[str, object]:
    slug = thread_key.replace(":", "-")
    messages_path = root / slug / "clean-source" / "messages.jsonl"
    events_path = root / slug / "clean-source" / "events.jsonl"
    write_jsonl(messages_path, rows)
    write_jsonl(events_path, events)
    return {
        "thread_key": thread_key,
        "workspace_name": "fixture-workspace",
        "paths": {
            "clean_source_messages_jsonl": str(messages_path),
            "clean_source_events_jsonl": str(events_path),
        },
    }


def rejected_message(line: int, *, thread_key: str, text: str) -> dict[str, object]:
    return {
        "message_id": f"msg-{line}",
        "turn_id": f"turn-{line}",
        "source_id": f"src-{line}",
        "source_line": line,
        "role": "user",
        "kind": "message",
        "turn_index": line,
        "is_final": False,
        "text": text,
        "thread_key": thread_key,
    }


def behavior_event(
    line: int,
    *,
    event_id: str,
    call_ref: str,
    event_kind: str,
    hard_event_kind: str,
    status: str,
    exit_code: int | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "event_id": event_id,
        "source_line": line,
        "turn_index": line,
        "event_kind": event_kind,
        "hard_event_kind": hard_event_kind,
        "status": status,
        "tool_name": "shell_command",
        "call_ref": call_ref,
        "command_class": "test",
        "target_class": "focused_test_path",
        "failure_family": "assertion_failure" if status == "failed" else "none",
        "text": PRIVATE_SENTINEL,
    }
    if exit_code is not None:
        row["exit_code"] = exit_code
    return row


class EpisodeArcPrivateAdjudicationTests(unittest.TestCase):
    def test_private_history_adjudication_reports_aggregate_without_private_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            thread_complete = "session:complete-private-arc"
            thread_gappy = "session:gappy-private-arc"
            registry = {
                "threads": [
                    registry_entry(
                        root,
                        thread_complete,
                        rows=[
                            rejected_message(
                                20,
                                thread_key=thread_complete,
                                text=(
                                    "Do not repeat the rejected parser route; "
                                    f"{PRIVATE_SENTINEL}"
                                ),
                            )
                        ],
                        events=[
                            behavior_event(
                                10,
                                event_id="event-attempt",
                                call_ref="call-a",
                                event_kind="tool_call_requested",
                                hard_event_kind="tool_call_requested",
                                status="requested",
                            ),
                            behavior_event(
                                11,
                                event_id="event-failed",
                                call_ref="call-a",
                                event_kind="tool_call_observed",
                                hard_event_kind="tool_call_failed",
                                status="failed",
                                exit_code=1,
                            ),
                        ],
                    ),
                    registry_entry(
                        root,
                        thread_gappy,
                        rows=[
                            rejected_message(
                                30,
                                thread_key=thread_gappy,
                                text="Do not repeat the old route without the missing middle event.",
                            )
                        ],
                        events=[],
                    ),
                ]
            }

            report = private_arcs.build_private_history_episode_arc_adjudication_report(registry)
            encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], private_arcs.REPORT_KIND)
        self.assertEqual(report["status"], "measured_public_safe_aggregate")
        self.assertEqual(report["metrics"]["episode_arc_count"], 2)
        self.assertEqual(report["metrics"]["complete_rejected_route_arc_count"], 1)
        self.assertEqual(report["metrics"]["gappy_arc_count"], 1)
        self.assertEqual(report["sequence_gap_counts"]["single_point_trap"], 1)
        self.assertTrue(report["privacy_boundary"]["aggregate_only"])
        self.assertFalse(report["privacy_boundary"]["source_refs_emitted"])
        self.assertFalse(report["privacy_boundary"]["thread_ids_emitted"])
        self.assertFalse(report["issue_readouts"]["github_663"]["closeout_eligible"])
        self.assertNotIn(PRIVATE_SENTINEL, encoded)
        self.assertNotIn(thread_complete, encoded)
        self.assertNotIn(thread_gappy, encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertNotIn('"source_refs": [', encoded)
        self.assertNotIn('"source_ref_hashes": [', encoded)

    def test_cli_facade_runs_episode_arc_readout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            thread_key = "session:cli-private-arc"
            registry = {
                "schema_version": 1,
                "threads": [
                    registry_entry(
                        root,
                        thread_key,
                        rows=[
                            rejected_message(
                                18,
                                thread_key=thread_key,
                                text="Do not repeat the CLI route after the failing check.",
                            )
                        ],
                        events=[
                            behavior_event(
                                12,
                                event_id="event-cli-attempt",
                                call_ref="call-cli",
                                event_kind="tool_call_requested",
                                hard_event_kind="tool_call_requested",
                                status="requested",
                            ),
                            behavior_event(
                                13,
                                event_id="event-cli-failed",
                                call_ref="call-cli",
                                event_kind="tool_call_observed",
                                hard_event_kind="tool_call_failed",
                                status="failed",
                                exit_code=1,
                            ),
                        ],
                    )
                ],
            }
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

            result = facade.run_command(
                ["episode-arcs", "--registry", str(registry_path), "--json"],
                capture_output=True,
            )
            human = facade.run_command(
                ["episode-arcs", "--registry", str(registry_path)],
                capture_output=True,
            )

        self.assertTrue(result.ok, result.stderr)
        self.assertTrue(human.ok, human.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], private_arcs.REPORT_KIND)
        self.assertEqual(payload["metrics"]["complete_rejected_route_arc_count"], 1)
        self.assertNotIn("session:cli-private-arc", result.stdout)
        self.assertIn("AIppocampus episode-arcs", human.stdout)
        self.assertIn("episode arcs: 1", human.stdout)
        self.assertNotIn('"metrics"', human.stdout)
        self.assertNotIn("session:cli-private-arc", human.stdout)


if __name__ == "__main__":
    unittest.main()
