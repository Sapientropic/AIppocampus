from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import dream_sleep_cycle  # noqa: E402
from model_client import DEEPSEEK_PREFIX_CACHE_CONTRACT, ChatClientConfig  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def ready_pack() -> dict[str, object]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    return {
        "schema_version": 1,
        "kind": "aippocampus_dream_input_pack",
        "pack_id": "dream_pack_cycle",
        "pack_kind": "cross_thread_resonance_pack",
        "status": "ready_for_dream_worker",
        "selection": {"resonance_term": "continuity"},
        "themes": ["continuity", "source refs"],
        "source_seed_ids": ["seed-a", "seed-b"],
        "source_seed_kinds": ["question_link", "working_memory"],
        "source_refs": refs,
        "source_ref_audit": {
            "status": "clean_source_refs_present",
            "source_ref_count": 2,
            "source_thread_count": 2,
        },
        "eligible_dream_functions": ["compensatory", "amplification"],
    }


def config() -> ChatClientConfig:
    return ChatClientConfig(
        api_key="test",
        model="deepseek-v4-flash",
        base_url="https://example.invalid",
        cache_contract=DEEPSEEK_PREFIX_CACHE_CONTRACT,
        timeout=11,
    )


def accepted_content(dream_function: str) -> str:
    if dream_function == "amplification":
        candidate_kind = "cross_thread_resonance"
        title = "Continuity resonates across selected source handles"
    else:
        candidate_kind = "blind_spot"
        title = "Continuity may be too route-centric"
    return json.dumps(
        {
            "findings": [
                {
                    "candidate_kind": candidate_kind,
                    "title": title,
                    "summary": "The source pack can seed a bounded dream hypothesis.",
                    "activation_cues": ["continuity source refs", "cross-thread continuity"],
                    "confidence": 0.69,
                    "source_ref_ids": ["sr0", "sr1"],
                    "bridge_claims": [
                        {
                            "claim": "Both source handles point at continuity work.",
                            "source_ref_ids": ["sr0", "sr1"],
                        }
                    ],
                }
            ]
        }
    )


class DreamSleepCycleTests(unittest.TestCase):
    def test_select_runnable_queue_items_requires_due_unless_run_ready(self) -> None:
        queue_payload = dream_sleep_cycle.dream_queue.build_dream_queue(
            [ready_pack()],
            now="2026-05-30T00:00:00Z",
        )
        items = queue_payload["items"]

        not_due = dream_sleep_cycle.select_runnable_queue_items(
            items,
            now="2026-05-30T00:00:00Z",
            max_items=2,
            run_ready=False,
        )
        ready = dream_sleep_cycle.select_runnable_queue_items(
            items,
            now="2026-05-30T00:00:00Z",
            max_items=1,
            run_ready=True,
        )
        due_item = dict(items[0], review_after="2026-05-29T00:00:00Z")
        expired_item = dict(items[1], review_after="2026-05-29T00:00:00Z", expires_at="2026-05-29T01:00:00Z")
        duplicate = dict(due_item, queue_item_id="dreamq_duplicate")
        due = dream_sleep_cycle.select_runnable_queue_items(
            [due_item, expired_item, duplicate],
            now="2026-05-30T00:00:00Z",
            max_items=3,
            run_ready=False,
        )

        self.assertEqual(not_due, [])
        self.assertEqual(len(ready), 1)
        self.assertEqual([item["queue_item_id"] for item in due], [due_item["queue_item_id"]])

    def test_sleep_cycle_runs_ready_items_no_write_and_public_summary_is_sanitized(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del call_config
            dream_function = json.loads(messages[-1]["content"])["dream_function"]
            content = "{not-json" if dream_function == "amplification" else accepted_content(dream_function)
            return {
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 2},
            }

        payload = dream_sleep_cycle.run_sleep_cycle(
            [ready_pack()],
            now="2026-05-30T00:00:00Z",
            config=config(),
            model_call=fake_model_call,
            max_items=2,
            no_write=True,
            run_ready=True,
        )
        summary = dream_sleep_cycle.public_sleep_cycle_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_dream_sleep_cycle")
        self.assertEqual(payload["counts"]["queue_items"], 2)
        self.assertEqual(payload["counts"]["selected_items"], 2)
        self.assertEqual(payload["counts"]["accepted"], 1)
        self.assertEqual(payload["counts"]["worker_failure"], 0)
        self.assertEqual({run["status"] for run in payload["worker_runs"]}, {"candidate_emitted", "model_output_rejected"})
        retention = payload["adjudicated_findings"][0]["retention_policy"]
        self.assertEqual(retention["kind"], "aippocampus_dream_retention_policy")
        self.assertEqual(retention["aggregate"]["meaning"], "attention_lifecycle_not_truth")
        self.assertNotIn("confidence", retention["aggregate"])
        self.assertTrue(payload["no_write"])
        self.assertFalse(payload["foreground_eligible"])
        self.assertEqual(summary["worker_statuses"], {"candidate_emitted": 1, "model_output_rejected": 1})
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)

    def test_sleep_cycle_continues_after_worker_error_and_writes_only_when_enabled(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del call_config
            dream_function = json.loads(messages[-1]["content"])["dream_function"]
            if dream_function == "amplification":
                raise RuntimeError("provider timeout")
            return {
                "choices": [{"message": {"content": accepted_content(dream_function)}}],
                "usage": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = dream_sleep_cycle.run_sleep_cycle(
                [ready_pack()],
                now="2026-05-30T00:00:00Z",
                config=config(),
                model_call=fake_model_call,
                max_items=2,
                no_write=False,
                run_ready=True,
                queue_output_path=root / "dream_queue.jsonl",
                findings_output_path=root / "dream_findings.jsonl",
                working_memory_output_path=root / "working_memory.jsonl",
            )
            queue_rows = [json.loads(line) for line in (root / "dream_queue.jsonl").read_text().splitlines()]
            finding_rows = [json.loads(line) for line in (root / "dream_findings.jsonl").read_text().splitlines()]
            working_rows = [json.loads(line) for line in (root / "working_memory.jsonl").read_text().splitlines()]

        self.assertEqual(payload["counts"]["selected_items"], 2)
        self.assertEqual(payload["counts"]["worker_failure"], 1)
        self.assertEqual(payload["counts"]["accepted"], 1)
        self.assertEqual({row["status"] for row in queue_rows}, {"completed", "failed"})
        self.assertEqual(len(finding_rows), 1)
        self.assertEqual(finding_rows[0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(len(working_rows), 1)
        self.assertEqual(working_rows[0]["candidate_type"], "dream_hypothesis")

    def test_sleep_cycle_reports_parked_output_without_projecting_working_memory(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del call_config
            dream_function = json.loads(messages[-1]["content"])["dream_function"]
            if dream_function == "amplification":
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "findings": [
                                            {
                                                "candidate_kind": "cross_thread_resonance",
                                                "title": "Missing activation cue output",
                                                "summary": "This should park before projection.",
                                                "confidence": 0.68,
                                                "source_ref_ids": ["sr0", "sr1"],
                                                "bridge_claims": [
                                                    {
                                                        "claim": "The bridge has source refs but no cue.",
                                                        "source_ref_ids": ["sr0", "sr1"],
                                                    }
                                                ],
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {},
                }
            return {
                "choices": [{"message": {"content": accepted_content(dream_function)}}],
                "usage": {},
            }

        payload = dream_sleep_cycle.run_sleep_cycle(
            [ready_pack()],
            now="2026-05-30T00:00:00Z",
            config=config(),
            model_call=fake_model_call,
            max_items=2,
            no_write=False,
            run_ready=True,
        )

        self.assertEqual(payload["worker_statuses"], {"candidate_emitted": 1, "candidate_parked": 1})
        self.assertEqual(payload["counts"]["accepted"], 1)
        self.assertEqual(payload["counts"]["parked"], 1)
        self.assertEqual({row["status"] for row in payload["queue_lifecycle_rows"]}, {"completed", "parked"})
        self.assertEqual(len(payload["dream_working_memory_rows"]), 1)

    def test_sleep_cycle_dedups_existing_findings_before_running_workers(self) -> None:
        existing_compensatory = {
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "source_pack_id": "dream_pack_cycle",
            "review_state": "agent_adjudicated",
        }
        seen_functions: list[str] = []

        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del call_config
            dream_function = json.loads(messages[-1]["content"])["dream_function"]
            seen_functions.append(dream_function)
            return {
                "choices": [{"message": {"content": accepted_content(dream_function)}}],
                "usage": {},
            }

        payload = dream_sleep_cycle.run_sleep_cycle(
            [ready_pack()],
            existing_findings=[existing_compensatory],
            now="2026-05-30T00:00:00Z",
            config=config(),
            model_call=fake_model_call,
            max_items=2,
            no_write=True,
            run_ready=True,
        )

        self.assertEqual(seen_functions, ["amplification"])
        self.assertEqual(payload["counts"]["queue_items"], 1)
        self.assertEqual(payload["counts"]["skipped_duplicate"], 1)
        self.assertEqual(payload["counts"]["accepted"], 1)


if __name__ == "__main__":
    unittest.main()
