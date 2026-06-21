from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.hooks import prompt as hook
from aippocampus_runtime.recall import ambient_cache as thread_cache


class AmbientSourceReopenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.old_semantic_gate = os.environ.get("AIPPOCAMPUS_SEMANTIC_GATE")
        os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = "off"

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_semantic_gate is None:
            os.environ.pop("AIPPOCAMPUS_SEMANTIC_GATE", None)
        else:
            os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = self.old_semantic_gate

    def _write_clean_thread_rows(self, thread_key: str, rows: list[dict]) -> Path:
        clean_dir = self.root / thread_key.replace(":", "-") / "clean-source"
        clean_dir.mkdir(parents=True)
        messages = clean_dir / "messages.jsonl"
        normalized = []
        for index, row in enumerate(rows, start=1):
            normalized.append(
                {
                    "message_id": row.get("message_id") or f"msg-{thread_key}-{index}",
                    "turn_id": row.get("turn_id") or f"turn-{thread_key}-{index}",
                    "source_line": row.get("source_line", 40 + index),
                    "timestamp": row.get("timestamp", "2026-05-25T00:00:00Z"),
                    "role": row.get("role", "assistant"),
                    "phase": row.get("phase", "final_answer"),
                    "turn_index": row.get("turn_index", index),
                    "is_final": row.get("is_final", row.get("phase", "final_answer") == "final_answer"),
                    "text": row.get("text", ""),
                }
            )
        messages.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in normalized) + "\n",
            encoding="utf-8",
        )
        return messages

    def _write_registry(
        self,
        *,
        registry_dir: str,
        thread_key: str,
        title: str,
        messages: Path,
        keywords: list[str] | None = None,
        summary: str = "",
    ) -> Path:
        registry_path = self.root / registry_dir / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": thread_key,
                            "title": title,
                            "workspace_name": "AIppocampus",
                            "project_label": "AIppocampus",
                            "keywords": keywords or [],
                            "summary": summary,
                            "paths": {
                                "workspace": str(self.workspace),
                                "clean_source_messages_jsonl": str(messages),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return registry_path

    def test_use_with_source_working_memory_reopens_bounded_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:alignment",
            [
                {
                    "message_id": "msg-align",
                    "source_line": 77,
                    "text": (
                        "Clean source says recurring alignment drift should be handled "
                        "through bounded source reopen before foreground claims."
                    ),
                }
            ],
        )
        registry_path = self._write_registry(
            registry_dir="question-working-reopen-registry",
            thread_key="session:alignment",
            title="Alignment thread",
            messages=messages,
        )
        working = registry_path.parent / "working_memory.jsonl"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "ask_policy": "do_not_ask_unless_contradicted_or_action_depends_on_uncertain_scope",
                    "risk": "medium",
                    "candidate_key": "wm_alignment_question",
                    "candidate_type": "question_link",
                    "title": "Agent alignment drift",
                    "summary": "Recurring question about agent output drifting from user intent.",
                    "recommendation": "Use as bounded source-backed context when relevant.",
                    "confidence": 0.84,
                    "project_label": "AIppocampus",
                    "trigger_terms": ["alignment drift", "foreground claims"],
                    "source_refs": [
                        {
                            "thread_key": "session:alignment",
                            "title": "Alignment thread",
                            "message_id": "msg-align",
                            "line": 77,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "alignment drift 这条 recurring question 会影响 foreground claims 吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        evidence_cards = [
            card for card in ambient["cards"] if card.get("support_level") == "evidence"
        ]
        self.assertEqual(ambient["source_reopen"]["success_count"], 1)
        self.assertEqual(evidence_cards[0]["provenance_class"], "source_backed_reopen")
        self.assertIn("bounded source reopen", evidence_cards[0]["key_line"])
        context = hook.context_for_hook(result) or ""
        self.assertIn("source-backed refs available", context)
        self.assertIn("bounded source reopen", context)

    def test_use_with_source_working_memory_unresolvable_ref_stays_candidate(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:alignment",
            [
                {
                    "message_id": "msg-present",
                    "source_line": 77,
                    "text": "Clean source exists, but this is not the referenced message.",
                }
            ],
        )
        registry_path = self._write_registry(
            registry_dir="question-working-reopen-miss-registry",
            thread_key="session:alignment",
            title="Alignment thread",
            messages=messages,
        )
        working = registry_path.parent / "working_memory.jsonl"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "risk": "medium",
                    "candidate_key": "wm_alignment_question",
                    "candidate_type": "question_link",
                    "title": "Agent alignment drift",
                    "summary": "Recurring question about agent output drifting from user intent.",
                    "confidence": 0.84,
                    "project_label": "AIppocampus",
                    "trigger_terms": ["alignment drift"],
                    "source_refs": [
                        {
                            "thread_key": "session:alignment",
                            "title": "Alignment thread",
                            "message_id": "msg-missing",
                            "line": 404,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "alignment drift 这条线索还在吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        self.assertEqual(ambient["source_reopen"]["success_count"], 0)
        self.assertEqual(ambient["source_reopen"]["failure_count"], 1)
        self.assertFalse(
            [card for card in ambient["cards"] if card.get("support_level") == "evidence"]
        )
        self.assertEqual(ambient["cards"][0]["support_level"], "candidate")

    def test_related_cache_evidence_with_resolvable_refs_reopens_bounded_evidence(self) -> None:
        cache_path = self.root / "ambient-cache-related-evidence.json"
        messages = self._write_clean_thread_rows(
            "session:single-thread",
            [
                {
                    "message_id": "msg-related",
                    "source_line": 42,
                    "text": (
                        "Clean source says related cached evidence can become bounded "
                        "foreground context after deterministic reopen."
                    ),
                }
            ],
        )
        registry_path = self._write_registry(
            registry_dir="related-evidence-registry",
            thread_key="session:single-thread",
            title="Ambient recall design",
            messages=messages,
            keywords=["ambient recall", "associative cache"],
            summary="Prior notes about related cached evidence.",
        )
        signals = thread_cache.related_signal_fingerprints(
            candidates=[{"thread_key": "session:single-thread"}]
        )
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-first-phrasing",
            cards=[
                {
                    "card_id": "cached-related-evidence",
                    "theme": "Related cached evidence",
                    "support_level": "evidence",
                    "visibility": "source_backed_recall_card",
                    "provenance_class": "source_backed_reopen",
                    "source_refs": [
                        {
                            "thread_key": "session:single-thread",
                            "title": "Ambient recall design",
                            "message_id": "msg-related",
                            "line": 42,
                        }
                    ],
                }
            ],
            mode="source_backed_recall_card",
            confidence="high",
            related_fingerprints=signals,
        )

        result = hook.assess_prompt(
            "ambient associative cache 这个 related cached evidence 能不能直接用？",
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-a",
            ambient_cache_path=cache_path,
            warm_background=True,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        evidence_cards = [
            card for card in ambient["cards"] if card.get("support_level") == "evidence"
        ]
        self.assertEqual(ambient["cache_status"]["status"], "related_hit")
        self.assertEqual(ambient["source_reopen"]["success_count"], 1)
        self.assertEqual(evidence_cards[0]["provenance_class"], "source_backed_reopen")
        self.assertIn("bounded foreground context", evidence_cards[0]["key_line"])

if __name__ == "__main__":
    unittest.main()
