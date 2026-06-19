from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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
                ["episode-arcs", "--registry", str(registry_path), "--json", "--top", "5"],
                capture_output=True,
            )
            detail = facade.run_command(
                [
                    "episode-arcs",
                    "--registry",
                    str(registry_path),
                    "--json",
                    "--detail",
                    "full",
                    "--top",
                    "5",
                ],
                capture_output=True,
            )
            human = facade.run_command(
                ["episode-arcs", "--registry", str(registry_path)],
                capture_output=True,
            )
            summary = facade.run_command(
                ["episode-arcs", "--registry", str(registry_path), "--summary-json"],
                capture_output=True,
            )

        self.assertTrue(result.ok, result.stderr)
        self.assertTrue(detail.ok, detail.stderr)
        self.assertTrue(human.ok, human.stderr)
        self.assertTrue(summary.ok, summary.stderr)
        payload = json.loads(result.stdout)
        detail_payload = json.loads(detail.stdout)
        summary_payload = json.loads(summary.stdout)
        self.assertEqual(payload["kind"], "aippocampus_episode_arcs_summary")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertEqual(detail_payload["kind"], private_arcs.REPORT_KIND)
        self.assertEqual(detail_payload["metrics"]["complete_rejected_route_arc_count"], 1)
        self.assertEqual(summary_payload["kind"], "aippocampus_episode_arcs_summary")
        self.assertEqual(summary_payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(summary_payload["foreground_action"], summary_payload["agent_next_action"])
        self.assertEqual(summary_payload["safe_next_actions"][0], summary_payload["foreground_action"])
        self.assertEqual(summary_payload["foreground_action"]["id"], "retrieve_actionable_arc_handles")
        self.assertEqual(
            summary_payload["route_value"],
            "navigation_only_sequence_hints_need_source_reopen",
        )
        self.assertIn("summary_metrics", summary_payload)
        self.assertEqual(
            summary_payload["summary_source"],
            "bounded_registry_scan_no_private_history_aggregation",
        )
        self.assertEqual(summary_payload["summary_metrics"]["counts_status"], "deferred_to_detail")
        self.assertIsNone(summary_payload["episode_arc_count"])
        self.assertIsNone(summary_payload["complete_arc_count"])
        self.assertEqual(summary_payload["current_validity_counts"], {})
        self.assertEqual(summary_payload["safe_use_counts"], {})
        self.assertEqual(
            summary_payload["safe_next_actions"][0]["command"],
            "aippocampus episode-arcs --json --detail full --top 5",
        )
        self.assertEqual(summary_payload["what_to_do"], "retrieve_actionable_arc_handles")
        self.assertFalse(summary_payload["no_op"])
        self.assertEqual(
            summary_payload["owner_route"]["command"],
            "aippocampus episode-arcs --json --detail full --top 5",
        )
        self.assertNotIn("cannot_claim", summary_payload)
        self.assertIn("current_validity", summary_payload["claim_boundary"]["must_reopen_for"])
        self.assertEqual(
            summary_payload["claim_boundary"]["detail_available_with"],
            "aippocampus episode-arcs --json --detail full",
        )
        self.assertNotIn("top_arcs", payload)
        self.assertIn("top_arcs", detail_payload)
        self.assertEqual(detail_payload["top_arcs"][0]["current_validity"], "needs_reopen")
        self.assertIn("arc_handle", detail_payload["top_arcs"][0])
        self.assertIn("source_reopen_action", detail_payload["top_arcs"][0])
        reopen = detail_payload["top_arcs"][0]["source_reopen_action"]
        self.assertEqual(reopen["kind"], "inspect_episode_arc_sources")
        self.assertNotIn("command", reopen)
        self.assertIn("{arc_handle}", reopen["command_template"])
        self.assertEqual(reopen["requires"], ["arc_handle"])
        self.assertNotIn("source_refs", json.dumps(detail_payload["top_arcs"], ensure_ascii=False))
        self.assertNotIn("session:cli-private-arc", result.stdout)
        self.assertNotIn("session:cli-private-arc", summary.stdout)
        self.assertIn("AIppocampus episode-arcs", human.stdout)
        self.assertIn("episode arcs: 1", human.stdout)
        self.assertIn("action card:", human.stdout)
        self.assertIn("needs_reopen: 1", human.stdout)
        self.assertIn("safe use:", human.stdout)
        self.assertNotIn('"metrics"', human.stdout)
        self.assertNotIn("session:cli-private-arc", human.stdout)

    def test_compact_episode_arcs_does_not_build_full_private_history_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = {
                "schema_version": 1,
                "threads": [
                    registry_entry(
                        root,
                        "session:compact-fast",
                        rows=[
                            rejected_message(
                                18,
                                thread_key="session:compact-fast",
                                text="Do not repeat the slow full aggregation before a foreground card.",
                            )
                        ],
                        events=[],
                    )
                ],
            }
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(
                    private_arcs,
                    "build_private_history_episode_arc_adjudication_report",
                    side_effect=AssertionError("compact foreground card must not run full aggregation"),
                ),
                patch("sys.stdout", new=StringIO()) as stdout,
            ):
                code = private_arcs.main(["--registry", str(registry_path), "--json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_episode_arcs_summary")
        self.assertEqual(payload["summary_metrics"]["counts_status"], "deferred_to_detail")
        self.assertEqual(
            payload["summary_source"],
            "bounded_registry_scan_no_private_history_aggregation",
        )
        self.assertEqual(payload["foreground_action"]["id"], "retrieve_actionable_arc_handles")
        self.assertFalse(payload["no_op"])

    def test_episode_arcs_empty_summary_is_structured_no_op(self) -> None:
        summary_payload = private_arcs.summary_projection(
            {
                "ok": True,
                "status": "measured_public_safe_aggregate",
                "metrics": {
                    "episode_arc_count": 0,
                    "complete_arc_count": 0,
                    "gappy_arc_count": 0,
                },
                "current_validity_counts": {},
                "safe_use_counts": {},
                "privacy_boundary": {"aggregate_only": True},
            }
        )

        self.assertTrue(summary_payload["no_op"])
        self.assertEqual(summary_payload["what_to_do"], "no_episode_arcs_to_route")
        self.assertEqual(summary_payload["agent_next_action"]["kind"], "no_episode_arcs_to_route")
        self.assertEqual(summary_payload["safe_next_actions"], [summary_payload["agent_next_action"]])
        self.assertNotIn("cannot_claim", summary_payload)
        self.assertIn("current_validity", summary_payload["claim_boundary"]["must_reopen_for"])


if __name__ == "__main__":
    unittest.main()
