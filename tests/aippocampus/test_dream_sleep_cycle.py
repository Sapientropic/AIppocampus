from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.dream import sleep_cycle as dream_sleep_cycle
from aippocampus_runtime.dream import working_memory_publication
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    ChatClientConfig,
)


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
    def test_config_from_args_uses_deepseek_thinking_contract_by_default(self) -> None:
        class Args:
            model_route = None
            model = dream_sleep_cycle.flash_model()
            base_url = dream_sleep_cycle.deepseek_base_url()
            api_key_env = "AIPPOCAMPUS_DEEPSEEK_API_KEY"
            max_tokens = None
            timeout = 5.0
            dream_model_thinking = "auto"
            dream_model_reasoning_effort = "auto"

        with patch.dict(os.environ, {"AIPPOCAMPUS_DEEPSEEK_API_KEY": "test"}, clear=False):
            config = dream_sleep_cycle.config_from_args(Args())

        self.assertEqual(config.thinking, "enabled")
        self.assertEqual(config.reasoning_effort, "high")

    def test_config_from_args_omits_deepseek_fields_for_conservative_route(self) -> None:
        class Args:
            model_route = "local_sleep"
            model = dream_sleep_cycle.flash_model()
            base_url = dream_sleep_cycle.deepseek_base_url()
            api_key_env = "AIPPOCAMPUS_DEEPSEEK_API_KEY"
            max_tokens = None
            timeout = 5.0
            dream_model_thinking = "auto"
            dream_model_reasoning_effort = "auto"

        with patch.dict(
            os.environ,
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_sleep",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-model",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_SLEEP_KEY",
                "LOCAL_SLEEP_KEY": "test",
            },
            clear=True,
        ):
            config = dream_sleep_cycle.config_from_args(Args())

        self.assertIsNone(config.thinking)
        self.assertIsNone(config.reasoning_effort)

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
        card = summary["dream_output_status_card"]
        self.assertEqual(card["status"], "no_foreground_output")
        self.assertEqual(card["reason_buckets"]["no_write_mode"], 1)
        self.assertEqual(card["primary_next_action"], "rerun_with_write_or_publish_when_operator_intends_persistence")
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
                "usage": {
                    "prompt_cache_hit_tokens": 6,
                    "prompt_cache_miss_tokens": 4,
                },
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
        completed = next(row for row in queue_rows if row["status"] == "completed")
        self.assertEqual(completed["usage"]["prompt_cache_hit_tokens"], 6)
        self.assertEqual(completed["usage"]["prompt_cache_miss_tokens"], 4)
        self.assertEqual(completed["cache"]["kind"], "deepseek_prefix")
        self.assertEqual(completed["cache"]["hit_tokens"], 6)
        self.assertEqual(completed["cache"]["miss_tokens"], 4)
        self.assertTrue(payload["write_lock"]["used"])
        self.assertTrue(payload["write_lock"]["owner_token_matched_on_release"])
        self.assertFalse(payload["write_lock"]["foreground_readers_wait"])
        self.assertEqual(len(finding_rows), 1)
        self.assertEqual(finding_rows[0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(len(working_rows), 1)
        self.assertEqual(working_rows[0]["candidate_type"], "dream_hypothesis")

    def test_sleep_cycle_staging_write_persists_findings_without_working_memory_projection(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del call_config
            dream_function = json.loads(messages[-1]["content"])["dream_function"]
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
                max_items=1,
                no_write=False,
                write_working_memory=False,
                run_ready=True,
                queue_output_path=root / "dream_queue.jsonl",
                findings_output_path=root / "dream_findings.jsonl",
                working_memory_output_path=root / "working_memory.jsonl",
            )
            queue_rows = [json.loads(line) for line in (root / "dream_queue.jsonl").read_text().splitlines()]
            finding_rows = [json.loads(line) for line in (root / "dream_findings.jsonl").read_text().splitlines()]
            working_memory_path = root / "working_memory.jsonl"

        self.assertEqual(payload["write_mode"], "staging")
        self.assertEqual(payload["counts"]["written_queue_rows"], 1)
        self.assertEqual(payload["counts"]["written_findings"], 1)
        self.assertEqual(payload["counts"]["written_working_memory"], 0)
        self.assertEqual(len(payload["dream_working_memory_rows"]), 1)
        self.assertEqual(len(queue_rows), 1)
        self.assertEqual(len(finding_rows), 1)
        self.assertFalse(working_memory_path.exists())

    def test_default_write_output_uses_dream_working_memory_trust_domain_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            self.assertEqual(
                dream_sleep_cycle.default_dream_working_memory_output(root, None),
                root / "dream_working_memory.jsonl",
            )

    def test_sleep_cycle_can_publish_reader_safe_working_memory_snapshot(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del call_config
            dream_function = json.loads(messages[-1]["content"])["dream_function"]
            return {
                "choices": [{"message": {"content": accepted_content(dream_function)}}],
                "usage": {},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            working_memory_path = root / "working_memory.jsonl"
            payload = dream_sleep_cycle.run_sleep_cycle(
                [ready_pack()],
                now="2026-05-30T00:00:00Z",
                config=config(),
                model_call=fake_model_call,
                max_items=1,
                no_write=False,
                publish_working_memory=True,
                run_ready=True,
                queue_output_path=root / "dream_queue.jsonl",
                findings_output_path=root / "dream_findings.jsonl",
                working_memory_output_path=working_memory_path,
            )
            rows, diagnostic = working_memory_publication.load_working_memory_with_diagnostics(
                working_memory_path
            )

        self.assertEqual(payload["counts"]["written_working_memory"], 1)
        self.assertEqual(payload["working_memory_publication"]["status"], "published")
        self.assertEqual(diagnostic["status"], "published_generation_loaded")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["candidate_type"], "dream_hypothesis")

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
        card = payload["dream_output_status_card"]
        self.assertEqual(card["reason_buckets"]["adjudication_parked"], 1)
        self.assertEqual(card["retention_lifecycle_actions"]["park_for_review"]["action"], "revisit_on_review_horizon")
        self.assertEqual({row["status"] for row in payload["queue_lifecycle_rows"]}, {"completed", "parked"})
        self.assertEqual(len(payload["dream_working_memory_rows"]), 1)

    def test_public_sleep_cycle_summary_explains_no_queue_without_raw_refs(self) -> None:
        payload = dream_sleep_cycle.run_sleep_cycle(
            [],
            now="2026-05-30T00:00:00Z",
            config=config(),
            no_write=True,
            run_ready=True,
        )
        summary = dream_sleep_cycle.public_sleep_cycle_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["dream_output_status_card"]["reason_buckets"]["no_queue"], 1)
        self.assertEqual(summary["dream_output_status_card"]["primary_next_action"], "wait_for_due_queue_or_run_ready")
        self.assertNotIn("thread_key", encoded)
        self.assertNotIn("message_id", encoded)

    def test_sleep_cycle_lock_recovers_stale_owner_and_reports_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "dream_sleep_cycle_write.lock"
            lock_path.write_text('{"owner_token": "old", "pid": 999999}', encoding="utf-8")
            os.utime(lock_path, (1, 1))

            lock = dream_sleep_cycle.FileLock(lock_path, stale_seconds=1)
            with lock:
                payload = json.loads(lock_path.read_text(encoding="utf-8"))

            diagnostic = lock.diagnostic()

        self.assertNotEqual(payload["owner_token"], "old")
        self.assertTrue(diagnostic["recovered_stale_lock"])
        self.assertEqual(diagnostic["stale_recovery"]["stale_owner_token"], "old")
        self.assertTrue(diagnostic["owner_token_matched_on_release"])

    def test_old_sleep_cycle_lock_owner_does_not_unlink_new_owner_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "dream_sleep_cycle_write.lock"
            new_lock = dream_sleep_cycle.FileLock(lock_path, stale_seconds=60)
            with new_lock:
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
                old_lock = dream_sleep_cycle.FileLock(lock_path, stale_seconds=60)
                old_lock.owner_token = "old-owner-token"
                old_lock.__exit__(None, None, None)
                still_current = json.loads(lock_path.read_text(encoding="utf-8"))

            release = old_lock.diagnostic()["release"]

        self.assertEqual(still_current["owner_token"], payload["owner_token"])
        self.assertFalse(release["released"])
        self.assertEqual(release["reason"], "owner_token_changed")

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
