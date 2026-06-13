import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall.continuity_domains import (  # noqa: E402
    load_continuity_domain_events,
    load_continuity_domains_snapshot,
)
from aippocampus_runtime.subconscious import event_salience_gate as salience  # noqa: E402
from aippocampus_runtime.subconscious import jobs  # noqa: E402


def fixture_turn(
    user: str,
    *,
    assistant: str = "",
    index: int,
) -> dict[str, object]:
    return {
        "turn_ref": f"t{index}",
        "thread_key": "session:salience",
        "turn_id": f"turn_{index}",
        "turn_index": index,
        "user": user,
        "assistant": assistant,
        "source_refs": [
            {
                "thread_key": "session:salience",
                "message_id": f"msg_{index}",
                "turn_id": f"turn_{index}",
                "source_line": index,
                "role": "user",
            }
        ],
    }


class SubconsciousEventSalienceGateTests(unittest.TestCase):
    def test_event_salience_schema_covers_signal_and_noise_families(self) -> None:
        turns = [
            fixture_turn("Correction: I meant the Rust adapter, not the TS client.", index=0),
            fixture_turn("We are blocked until external evidence confirms this claim.", index=1),
            fixture_turn("Default to Chinese replies and short paragraphs for me.", index=2),
            fixture_turn("The old route is superseded; use the current registry path now.", index=3),
            fixture_turn(
                "Run the smoke again.",
                assistant="pytest failed with exit code 1 after the red test.",
                index=4,
            ),
            fixture_turn("Only implement the no-write report mode; do not promote memory.", index=5),
            fixture_turn("收到", index=6),
        ]

        selected, report = salience.filter_salient_turns(turns)
        rows = report["sidecar_rows"]
        by_kind = {row["event_kind"]: row for row in rows}

        self.assertEqual(report["input_turn_count"], 7)
        self.assertEqual(report["selected_turn_count"], 6)
        self.assertEqual(report["candidate_reduction_count"], 1)
        self.assertEqual(report["missed_high_signal_count"], 0)
        self.assertEqual(report["skipped_by_reason"], {"low_information_noise": 1})
        self.assertEqual([turn["turn_ref"] for turn in selected], [f"t{index}" for index in range(6)])
        self.assertIn("explicit_user_correction", by_kind)
        self.assertIn("unresolved_frontier_or_blocker", by_kind)
        self.assertIn("durable_preference_or_style", by_kind)
        self.assertIn("supersession_or_currentness", by_kind)
        self.assertIn("failed_command_or_test", by_kind)
        self.assertIn("scope_boundary_clarification", by_kind)
        self.assertEqual(by_kind["low_information_noise"]["candidate_action"], "skip")
        self.assertEqual(by_kind["explicit_user_correction"]["schema_version"], salience.SCHEMA_VERSION)
        self.assertEqual(
            by_kind["explicit_user_correction"]["source_refs"][0]["message_id"], "msg_0"
        )
        self.assertNotIn("Correction: I meant", json.dumps(report, ensure_ascii=False))

    def test_event_salience_sidecar_is_rebuildable_and_source_ref_backed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "event-salience.jsonl"
            turns = [
                fixture_turn("I prefer concise Chinese summaries by default.", index=0),
                fixture_turn("ok", index=1),
            ]

            _, report = salience.filter_salient_turns(turns)
            salience.write_event_salience_sidecar(output_path, report["sidecar_rows"])

            rows = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_kind"], "durable_preference_or_style")
        self.assertEqual(rows[0]["authority"], "navigation_intake_metadata")
        self.assertEqual(rows[0]["source_refs"][0]["turn_ref"], "t0")
        self.assertNotIn("I prefer concise", json.dumps(rows, ensure_ascii=False))

    def test_jobs_can_opt_into_event_salience_gate_before_model_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:salience",
                                        "turn_index": 2,
                                        "user": "Correction: use the Rust adapter, not the TS client.",
                                        "assistant": "Noted.",
                                    },
                                    {
                                        "thread_key": "session:salience",
                                        "turn_index": 1,
                                        "user": "收到",
                                        "assistant": "OK.",
                                    },
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            calls: list[list[dict[str, str]]] = []

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, object]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                calls.append(messages)
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "action": "final",
                                        "findings": [
                                            {
                                                "kind": "concept_edge",
                                                "title": "Rust adapter preference",
                                                "summary": "The source corrects the adapter route to Rust.",
                                                "src": "Rust adapter",
                                                "dst": "TS client",
                                                "edge_type": "preferred_over",
                                                "confidence": 0.9,
                                                "source_refs": ["t0"],
                                            }
                                        ],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["concept_edges"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                event_salience_output_path=root / "event-salience.jsonl",
                project="AIppocampus",
                objective="extract route corrections",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                event_salience_gate=True,
                chat_fn=fake_chat,
            )
            sidecar_exists = Path(result["event_salience_output"]).exists()

        prompt = calls[0][1]["content"]
        gate = result["event_salience_gate"]

        self.assertEqual(gate["input_turn_count"], 2)
        self.assertEqual(gate["selected_turn_count"], 1)
        self.assertEqual(gate["candidate_reduction_count"], 1)
        self.assertEqual(gate["missed_high_signal_count"], 0)
        self.assertIn("Rust adapter", prompt)
        self.assertNotIn("收到", prompt)
        self.assertTrue(sidecar_exists)

    def test_jobs_can_opt_into_continuity_domain_salience_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean-source"
            clean.mkdir(parents=True, exist_ok=True)
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg-correction",
                        "turn_id": "turn-correction",
                        "turn_index": 1,
                        "source_line": 10,
                        "role": "user",
                        "text": "Correction: use the Rust adapter, not the TS client.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (clean / "turns.jsonl").write_text("", encoding="utf-8")
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:salience",
                                        "turn_id": "turn-correction",
                                        "turn_index": 1,
                                        "user": "Correction: use the Rust adapter, not the TS client.",
                                        "assistant": "Noted.",
                                        "source_refs": [
                                            {
                                                "thread_key": "session:salience",
                                                "message_id": "msg-correction",
                                                "turn_id": "turn-correction",
                                                "source_line": 10,
                                                "role": "user",
                                            }
                                        ],
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            events_path = clean / "continuity-domain-events.jsonl"
            snapshot_dir = root / "continuity-domain-snapshots"

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, object]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                return {
                    "choices": [{"message": {"content": json.dumps({"action": "final", "findings": []})}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["concept_edges"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                event_salience_output_path=root / "event-salience.jsonl",
                project="AIppocampus",
                objective="extract route corrections",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                event_salience_gate=True,
                continuity_domain_salience_mode="write_when_enabled",
                continuity_domain_events_path=events_path,
                continuity_domain_snapshot_dir=snapshot_dir,
                continuity_domain_clean_source_dir=clean,
                continuity_domain_publish=True,
                concurrency=1,
                samples_per_job=1,
                chat_fn=fake_chat,
            )
            public = jobs.public_jobs_payload(result)
            events = load_continuity_domain_events(events_path, clean_source_dir=clean)
            snapshot = load_continuity_domains_snapshot(snapshot_dir / "latest.json")

        self.assertEqual(result["continuity_domain_salience_adapter"]["mode"], "write_when_enabled")
        self.assertEqual(
            result["continuity_domain_salience_adapter"]["write_report"]["appended_event_count"],
            1,
        )
        self.assertEqual(events[0]["event_kind"], "correction_source_added")
        self.assertIsNotNone(snapshot)
        serialized_public = json.dumps(public, ensure_ascii=False)
        self.assertEqual(
            public["continuity_domain_salience_adapter"]["candidate_event_count"],
            1,
        )
        self.assertNotIn("msg-correction", serialized_public)
        self.assertNotIn("Rust adapter", serialized_public)

    def test_public_jobs_payload_reports_salience_without_source_text_or_refs(self) -> None:
        result = {
            "ok": True,
            "job_count": 1,
            "successful_job_count": 1,
            "failure_count": 0,
            "partial_failure": False,
            "requested_job_count": 1,
            "samples_per_job": 1,
            "concurrency": 1,
            "finding_count": 0,
            "edge_count": 0,
            "wrote": False,
            "dry_run": True,
            "event_salience_gate": {
                "enabled": True,
                "input_turn_count": 2,
                "selected_turn_count": 1,
                "candidate_reduction_count": 1,
                "missed_high_signal_count": 0,
                "selected_by_bucket": {"high": 1},
                "skipped_by_reason": {"low_information_noise": 1},
                "sidecar_rows": [
                    {
                        "event_kind": "explicit_user_correction",
                        "source_refs": [{"message_id": "msg_private"}],
                        "source_preview": "private text should not leak",
                    }
                ],
            },
        }

        public = jobs.public_jobs_payload(result)
        serialized = json.dumps(public, ensure_ascii=False)

        self.assertEqual(public["event_salience_gate"]["candidate_reduction_count"], 1)
        self.assertNotIn("msg_private", serialized)
        self.assertNotIn("private text", serialized)


if __name__ == "__main__":
    unittest.main()
