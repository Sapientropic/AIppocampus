from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import warm_ambient_recall as warm  # noqa: E402


class WarmAmbientRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.cache_path = self.root / "ambient-thread-cache.json"
        self.residue_path = self.root / "ambient-residue.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_thread(self, thread_key: str, rows: list[dict]) -> Path:
        clean_dir = self.root / "clean" / thread_key.replace(":", "-")
        clean_dir.mkdir(parents=True)
        messages_path = clean_dir / "messages.jsonl"
        messages_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        return messages_path

    def _write_registry(self, entries: list[dict]) -> Path:
        registry_path = self.root / "registry" / "threads.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def test_default_scout_lanes_are_10_families_times_5_variants(self) -> None:
        calls: list[str] = []

        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            calls.append(scout)
            return {"decision": "skip", "confidence": 0.1}

        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            wait_all=True,
            no_write=True,
        )
        families = {lane.split(":", 1)[0] for lane in warm.DEFAULT_SCOUTS}
        variants = {lane.split(":", 1)[1] for lane in warm.DEFAULT_SCOUTS}

        self.assertEqual(len(warm.DEFAULT_SCOUTS), 50)
        self.assertEqual(len(families), 10)
        self.assertEqual(len(variants), 5)
        self.assertEqual(result["scout_count"], 50)
        self.assertEqual(len(calls), 50)

    def test_quorum_returns_without_waiting_for_all_scouts(self) -> None:
        calls: list[str] = []

        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            calls.append(scout)
            if scout.startswith(("query_expansion:", "life_wide_cue_classifier:")):
                return {
                    "decision": "candidate",
                    "confidence": 0.72,
                    "themes": [f"{scout} theme"],
                    "candidates": [
                        {
                            "theme": f"{scout} theme",
                            "support_level": "candidate",
                            "matched_terms": ["ambient recall"],
                        }
                    ],
                }
            time.sleep(0.25)
            return {"decision": "skip", "confidence": 0.1}

        started = time.perf_counter()
        result = warm.run_warm_ambient_recall(
            "继续 ambient recall 这条线",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            quorum=2,
            timeout=0.12,
            no_write=True,
        )
        elapsed = time.perf_counter() - started

        self.assertTrue(result["available"])
        self.assertTrue(result["quorum_met"])
        self.assertLess(elapsed, 0.2)
        self.assertEqual(result["accepted_scout_count"], 2)
        self.assertEqual(len(warm.DEFAULT_SCOUTS), 50)
        self.assertTrue(any(call.startswith("query_expansion:") for call in calls))
        self.assertTrue(any(call.startswith("life_wide_cue_classifier:") for call in calls))

    def test_malformed_scout_is_isolated(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            if scout.startswith("query_expansion:"):
                raise ValueError("not valid JSON")
            return {
                "decision": "candidate",
                "confidence": 0.8,
                "candidates": [{"theme": "warm cache", "support_level": "candidate"}],
            }

        result = warm.run_warm_ambient_recall(
            "继续 warm cache",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("query_expansion", "theme_matcher"),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["accepted_scout_count"], 1)
        self.assertEqual(result["failed_scout_count"], 1)
        self.assertEqual(result["scouts"][0]["ok"], False)
        self.assertEqual(result["scouts"][1]["ok"], True)
        self.assertEqual(result["cards"][0]["theme"], "warm cache")

    def test_warm_merge_writes_thread_cache_and_residue_without_raw_inputs(self) -> None:
        local_path = "E:" + "\\private\\notes\\ambient.md"
        prompt = f"继续 {local_path} 里的 ambient recall 方案"

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.91,
                "negative_contexts": ["do not treat unsourced scent as fact"],
                "candidates": [
                    {
                        "theme": "ambient recall cache first",
                        "support_level": "evidence",
                        "resonance": "high",
                        "suggested_use": "Use as source-backed prior only when helpful.",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["ambient recall", "cache"],
                        "source_refs": [
                            {
                                "thread_key": "session:old",
                                "title": "Ambient design",
                                "line": 42,
                                "message_id": "msg-1",
                            }
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            prompt,
            cwd=self.workspace,
            thread_id="thread-a",
            topic_epoch="epoch-test",
            cache_path=self.cache_path,
            residue_path=self.residue_path,
            residue_reason="warm_scout_unused",
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("evidence_judge",),
            quorum=1,
            timeout=0.5,
        )
        cache_raw = self.cache_path.read_text(encoding="utf-8")
        residue_rows = [
            json.loads(line)
            for line in self.residue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        joined = cache_raw + "\n" + self.residue_path.read_text(encoding="utf-8")

        self.assertEqual(result["cache_write"]["status"], "written")
        self.assertEqual(result["cache_write"]["residue_export"]["status"], "written")
        self.assertEqual(residue_rows[0]["source"], "ambient_thread_cache")
        self.assertEqual(residue_rows[0]["reason"], "warm_scout_unused")
        self.assertNotIn(str(self.workspace), joined)
        self.assertNotIn("private", joined.casefold())
        self.assertNotIn("notes", joined.casefold())
        self.assertNotIn(prompt, joined)

    def test_missing_api_key_fails_open_without_writing(self) -> None:
        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key=None,
            api_key_env="AIPPOCAMPUS_TEST_MISSING_KEY",
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "missing api key")
        self.assertFalse(self.cache_path.exists())

    def test_source_validation_downgrades_unsupported_evidence_ref(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "This source discusses unrelated registry maintenance only.",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Old ambient thread",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.9,
                "candidates": [
                    {
                        "theme": "ambient validation",
                        "support_level": "evidence",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["warm scouts"],
                        "source_refs": [
                            {"thread_key": "session:old", "message_id": "msg-1", "line": 42}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续 warm scouts",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("evidence_judge",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertEqual(result["cards"][0]["support_level"], "candidate")
        self.assertEqual(result["cards"][0]["source_validation"]["status"], "unsupported")

    def test_source_validation_keeps_supported_evidence_ref(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "The design says: Card/cache first, then warm scouts. This validates ambient recall.",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Old ambient thread",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.9,
                "candidates": [
                    {
                        "theme": "ambient validation",
                        "support_level": "evidence",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["ambient recall"],
                        "source_refs": [
                            {"thread_key": "session:old", "message_id": "msg-1", "line": 42}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("evidence_judge",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertEqual(result["cards"][0]["support_level"], "evidence")
        self.assertEqual(result["cards"][0]["source_validation"]["status"], "supported")

    def test_current_thread_echo_is_suppressed_by_default(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.9,
                "candidates": [
                    {
                        "theme": "current echo",
                        "support_level": "evidence",
                        "key_line": "This was just said in the current thread.",
                        "matched_terms": ["current thread"],
                        "source_refs": [
                            {"thread_key": "session:current", "message_id": "msg-current", "line": 7}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续当前话题",
            cwd=self.workspace,
            thread_id="thread-a",
            current_thread_key="session:current",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("current_thread_filter",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["current_thread_echo_count"], 1)

    def test_llm_topic_epoch_rotation_uses_scout_label_not_prompt_terms(self) -> None:
        label = "semantic scope sidecar calibration"

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "candidate",
                "confidence": 0.8,
                "topic_epoch_action": "rotate",
                "topic_epoch_label": label,
                "topic_epoch_reason": "The prompt trace moved to sidecar calibration.",
                "candidates": [{"theme": "epoch rotation", "support_level": "candidate"}],
            }

        result = warm.run_warm_ambient_recall(
            "unrelated deterministic prompt terms should not define the epoch",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("theme_matcher",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )
        prompt_terms_epoch = warm.topic_epoch_from_terms(
            ["unrelated deterministic prompt terms should not define the epoch"]
        )

        self.assertEqual(result["topic_epoch"], warm.topic_epoch_from_terms([label]))
        self.assertNotEqual(result["topic_epoch"], prompt_terms_epoch)
        self.assertEqual(result["topic_epoch_decision"]["action"], "rotate")

    def test_prompt_trace_is_sanitized_before_scout_payload(self) -> None:
        local_path = "C:" + "\\private\\trace\\memory.md"
        seen_payloads: list[dict] = []

        def scout_fn(scout, payload, **kwargs):
            del scout, kwargs
            seen_payloads.append(payload)
            return {"decision": "skip", "confidence": 0.1}

        warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            prompt_trace=[
                {
                    "thread_key": "session:current",
                    "role": "user",
                    "text": f"trace mentions {local_path}",
                }
            ],
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("query_expansion",),
            quorum=1,
            timeout=0.5,
            wait_all=True,
            no_write=True,
        )
        raw_payload = json.dumps(seen_payloads[0], ensure_ascii=False)

        self.assertIn("prompt_trace", seen_payloads[0])
        self.assertIn("<redacted:local-path>", raw_payload)
        self.assertNotIn(local_path.casefold(), raw_payload.casefold())
        self.assertNotIn("memory.md", raw_payload.casefold())


if __name__ == "__main__":
    unittest.main()
