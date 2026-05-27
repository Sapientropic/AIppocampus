from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import semantic_scope_suppressed_recovery as recovery  # noqa: E402


class SemanticScopeSuppressedRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self.jobs = self.registry.parent / "subconscious_jobs.jsonl"
        self.old_key = os.environ.get("FAKE_DEEPSEEK_KEY")

    def tearDown(self) -> None:
        if self.old_key is None:
            os.environ.pop("FAKE_DEEPSEEK_KEY", None)
        else:
            os.environ["FAKE_DEEPSEEK_KEY"] = self.old_key
        self.tmp.cleanup()

    def _write_fixture(self) -> None:
        clean = self.root / "thread-life" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_soft",
                    "turn_id": "turn_soft",
                    "source_line": 7,
                    "role": "user",
                    "text": "I want us to keep continuity with what we already discussed, because this question is not finished.",
                    "scope_labels": [],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.registry.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:soft",
                            "paths": {"clean_source_messages_jsonl": str(clean / "messages.jsonl")},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.jobs.write_text(
            json.dumps(
                {
                    "finding_kind": "semantic_scope_labels",
                    "job": "semantic_scope_labeling",
                    "message_id": "msg_soft",
                    "scope_labels": ["relationship_continuity", "open_question"],
                    "confidence": 0.9,
                    "summary": "Weak labels from the fast pass.",
                    "label_evidence": [
                        {
                            "label": "relationship_continuity",
                            "reason": "The source mentions continuity.",
                            "confidence": 0.86,
                        },
                        {
                            "label": "open_question",
                            "reason": "The source mentions a question.",
                            "confidence": 0.9,
                        },
                    ],
                    "source_refs": [{"message_id": "msg_soft", "source_line": 7, "role": "user"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_pro_agent_recovers_suppressed_labels_through_strict_materializer(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        calls: list[str] = []

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            calls.append(model)
            if len(calls) == 1:
                payload = json.loads(messages[1]["content"])
                self.assertEqual(payload["model_route"], "suppressed_label_recovery")
                self.assertNotIn("continuity with what", messages[1]["content"])
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "action": "tool",
                                        "tool": "inspect_suppressed_case",
                                        "args": {},
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            self.assertIn("TOOL_RESULT", messages[-1]["content"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "final",
                                    "findings": [
                                        {
                                            "kind": "semantic_scope_labels",
                                            "scope_labels": [
                                                "relationship_continuity",
                                                "open_question",
                                            ],
                                            "summary": "Recovered strict labels with stronger source-grounded evidence.",
                                            "confidence": 0.97,
                                            "label_evidence": [
                                                {
                                                    "label": "relationship_continuity",
                                                    "reason": "The source explicitly asks to keep continuity with prior discussion.",
                                                    "confidence": 0.98,
                                                },
                                                {
                                                    "label": "open_question",
                                                    "reason": "The source says the question is not finished and should continue later.",
                                                    "confidence": 0.95,
                                                },
                                            ],
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_cache_hit_tokens": 7, "prompt_cache_miss_tokens": 3},
            }

        result = recovery.run_suppressed_label_recovery_smoke(
            registry_path=self.registry,
            jobs_output_path=self.jobs,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_recovered_labels=2,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(set(calls), {"deepseek-v4-pro"})
        self.assertEqual(result["model_route"]["route"], "suppressed_label_recovery")
        self.assertEqual(result["candidate_label_count"], 2)
        self.assertEqual(result["strict_recovered_label_count"], 2)
        self.assertFalse(result["strict_gate_relaxed"])
        self.assertGreaterEqual(result["cases"][0]["tool_step_count"], 1)
        self.assertNotIn("continuity with what", rendered)
        self.assertNotIn("msg_soft", rendered)


if __name__ == "__main__":
    unittest.main()
