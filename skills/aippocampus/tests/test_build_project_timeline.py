from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_project_timeline as timeline  # noqa: E402


class ProjectTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_source(
        self,
        name: str,
        timestamp: str,
        user: str,
        assistant: str,
        *,
        user_scope_labels: list[str] | None = None,
        assistant_scope_labels: list[str] | None = None,
    ) -> tuple[Path, Path]:
        clean = self.root / name / "clean-source"
        clean.mkdir(parents=True)
        messages = clean / "messages.jsonl"
        turns = clean / "turns.jsonl"
        rows = [
            {
                "message_id": f"{name}-u",
                "turn_id": f"{name}-turn",
                "source_line": 10,
                "timestamp": timestamp,
                "role": "user",
                "phase": "",
                "turn_index": 4,
                "scope_labels": user_scope_labels or [],
                "text": user,
            },
            {
                "message_id": f"{name}-a",
                "turn_id": f"{name}-turn",
                "source_line": 12,
                "timestamp": timestamp,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 4,
                "is_final": True,
                "scope_labels": assistant_scope_labels or [],
                "text": assistant,
            },
        ]
        messages.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
        turns.write_text(
            json.dumps(
                {
                    "turn_id": f"{name}-turn",
                    "turn_index": 4,
                    "user_line": 10,
                    "assistant_line": 12,
                    "message_ids": [f"{name}-u", f"{name}-a"],
                    "assistant_phase": "final_answer",
                    "scope_labels": sorted(
                        set((user_scope_labels or []) + (assistant_scope_labels or []))
                    ),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return messages, turns

    def test_build_project_timeline_uses_latest_clean_turns(self) -> None:
        old_messages, old_turns = self._write_clean_source(
            "old",
            "2026-05-20T00:00:00Z",
            "旧问题",
            "旧回答",
        )
        new_messages, new_turns = self._write_clean_source(
            "new",
            "2026-05-25T00:00:00Z",
            "现在 T-Sense 是否该重写 Go runtime？",
            "推向市场前做 Go runtime spike 有意义，但不要重写整个 app。",
        )
        entries = [
            {
                "thread_key": "session:old",
                "title": "T-Sense old",
                "project_key": "project:t-sense",
                "project_label": "T-Sense",
                "project_tags": ["tg-channel-scanner"],
                "paths": {
                    "clean_source_messages_jsonl": str(old_messages),
                    "clean_source_turns_jsonl": str(old_turns),
                },
            },
            {
                "thread_key": "session:new",
                "title": "T-Sense new",
                "project_key": "project:t-sense",
                "project_label": "T-Sense",
                "project_tags": ["tg-channel-scanner"],
                "paths": {
                    "clean_source_messages_jsonl": str(new_messages),
                    "clean_source_turns_jsonl": str(new_turns),
                },
            },
        ]
        self.registry.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )

        result = timeline.build_project_timeline(self.registry, max_per_project=5)
        project = result["projects"]["project:t-sense"]

        self.assertEqual(project["thread_count"], 2)
        self.assertEqual(project["latest_turns"][0]["thread_key"], "session:new")
        self.assertIn("Go runtime", project["latest_turns"][0]["assistant"])
        self.assertIn("T-Sense", project["project_tags"])

    def test_life_wide_timeline_groups_scope_labeled_turns_across_projects(self) -> None:
        first_messages, first_turns = self._write_clean_source(
            "reading",
            "2026-05-21T00:00:00Z",
            "我读到一篇文章，又开始问：为什么这个焦虑总是回来？",
            "这是一条可以回源的个人反思，不应该被项目边界吞掉。",
            user_scope_labels=["personal_reflection", "reading_notes", "open_question"],
            assistant_scope_labels=["personal_reflection"],
        )
        second_messages, second_turns = self._write_clean_source(
            "spark",
            "2026-05-26T00:00:00Z",
            "今天又出现同一个焦虑，但它变成了一个新点子。",
            "保留这种 casual-important turn，后面才能看到问题如何演化。",
            user_scope_labels=["personal_reflection", "idea_seed", "life_context"],
            assistant_scope_labels=["relationship_continuity"],
        )
        entries = [
            {
                "thread_key": "session:reading",
                "title": "Reading thread",
                "project_key": "project:reading-notes",
                "project_label": "Reading Notes",
                "project_tags": ["essay"],
                "paths": {
                    "clean_source_messages_jsonl": str(first_messages),
                    "clean_source_turns_jsonl": str(first_turns),
                },
            },
            {
                "thread_key": "session:spark",
                "title": "Casual idea thread",
                "project_key": "project:life-chat",
                "project_label": "Life Chat",
                "project_tags": ["casual"],
                "paths": {
                    "clean_source_messages_jsonl": str(second_messages),
                    "clean_source_turns_jsonl": str(second_turns),
                },
            },
        ]
        self.registry.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )

        result = timeline.build_project_timeline(
            self.registry, max_per_project=5, max_per_life_label=5
        )
        personal = result["life_wide"]["labels"]["personal_reflection"]

        self.assertEqual(personal["thread_count"], 2)
        self.assertEqual(personal["latest_turns"][0]["thread_key"], "session:spark")
        self.assertEqual(personal["latest_turns"][1]["thread_key"], "session:reading")
        self.assertIn("idea_seed", personal["latest_turns"][0]["scope_labels"])
        self.assertEqual(personal["latest_turns"][0]["source_refs"][0]["message_id"], "spark-u")
        self.assertEqual(personal["latest_turns"][0]["source_refs"][0]["source_line"], 10)
        self.assertEqual(personal["latest_turns"][0]["turn_id"], "spark-turn")
        self.assertIn("焦虑", {item["term"] for item in personal["recurring_terms"]})

        open_question = result["life_wide"]["labels"]["open_question"]
        self.assertEqual(open_question["thread_count"], 1)
        self.assertEqual(open_question["latest_turns"][0]["thread_key"], "session:reading")

    def test_life_wide_timeline_uses_semantic_scope_label_sidecar(self) -> None:
        messages, turns = self._write_clean_source(
            "metaphor",
            "2026-05-26T00:00:00Z",
            "This is not a project task, but I keep circling back to the lighthouse metaphor; it feels like a pivot.",
            "That casual image is worth keeping as source-backed continuity.",
        )
        (messages.parent / "semantic-scope-labels.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "metaphor-u",
                    "source": "deepseek_subconscious_scope_labels",
                    "scope_labels": ["personal_reflection", "idea_seed", "life_context"],
                    "confidence": 0.94,
                    "label_evidence": [
                        {
                            "label": "personal_reflection",
                            "reason": "The source says the metaphor feels personally pivotal.",
                            "confidence": 0.88,
                        },
                        {
                            "label": "idea_seed",
                            "reason": "The source identifies the lighthouse metaphor as a pivot.",
                            "confidence": 0.86,
                        },
                        {
                            "label": "life_context",
                            "reason": "The source frames the metaphor as recurring lived context.",
                            "confidence": 0.94,
                        },
                    ],
                    "source_refs": [
                        {"message_id": "metaphor-u", "source_line": 10, "role": "user"}
                    ],
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
                            "thread_key": "session:metaphor",
                            "title": "Casual metaphor thread",
                            "project_key": "project:life-chat",
                            "project_label": "Life Chat",
                            "paths": {
                                "clean_source_messages_jsonl": str(messages),
                                "clean_source_turns_jsonl": str(turns),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = timeline.build_project_timeline(self.registry)

        personal = result["life_wide"]["labels"]["personal_reflection"]
        self.assertEqual(personal["latest_turns"][0]["thread_key"], "session:metaphor")
        self.assertEqual(
            personal["latest_turns"][0]["semantic_scope_labels"],
            ["personal_reflection", "idea_seed", "life_context"],
        )
        self.assertEqual(personal["latest_turns"][0]["source_refs"][0]["message_id"], "metaphor-u")

    def test_timeline_resolves_public_bundle_paths_relative_to_registry_parent(self) -> None:
        bundle = self.root / "bundle"
        registry_dir = bundle / "registry"
        clean = bundle / "clean-source"
        registry_path = registry_dir / "threads.json"
        registry_dir.mkdir(parents=True)
        clean.mkdir()
        (clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_public",
                    "turn_id": "turn_public",
                    "clean_ordinal": 0,
                    "source_line": 8,
                    "timestamp": "2026-05-27T00:00:00Z",
                    "role": "user",
                    "phase": "",
                    "turn_index": 1,
                    "scope_labels": ["idea_seed"],
                    "text": "The archive should remember casual sparks too.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (clean / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": "turn_public",
                    "turn_index": 1,
                    "message_ids": ["msg_public"],
                    "scope_labels": ["idea_seed"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        registry_path.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "public-example-thread",
                            "project_label": "Public Demo",
                            "paths": {
                                "clean_source_messages_jsonl": "clean-source/messages.jsonl",
                                "clean_source_turns_jsonl": "clean-source/turns.jsonl",
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = timeline.build_project_timeline(registry_path)

        idea = result["life_wide"]["labels"]["idea_seed"]
        self.assertEqual(idea["latest_turns"][0]["thread_key"], "public-example-thread")
        self.assertEqual(idea["latest_turns"][0]["project_key"], "project:Public Demo")
        self.assertEqual(idea["project_count"], 1)
        self.assertEqual(idea["latest_turns"][0]["source_refs"][0]["message_id"], "msg_public")
        self.assertEqual(
            idea["latest_turns"][0]["source_refs"][0]["thread_key"], "public-example-thread"
        )
        self.assertEqual(idea["latest_turns"][0]["source_refs"][0]["clean_ordinal"], 0)

    def test_timeline_rejects_relative_registry_paths_that_escape_bundle(self) -> None:
        bundle = self.root / "bundle"
        registry_dir = bundle / "registry"
        registry_path = registry_dir / "threads.json"
        private_dir = self.root / "private"
        registry_dir.mkdir(parents=True)
        private_dir.mkdir()
        (private_dir / "raw.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "private",
                    "turn_id": "private-turn",
                    "source_line": 1,
                    "role": "user",
                    "turn_index": 1,
                    "text": "should not be read",
                    "scope_labels": ["idea_seed"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (private_dir / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": "private-turn",
                    "turn_index": 1,
                    "message_ids": ["private"],
                    "scope_labels": ["idea_seed"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        registry_path.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:escape",
                            "project_label": "Bad Export",
                            "paths": {
                                "clean_source_messages_jsonl": "../../private/raw.jsonl",
                                "clean_source_turns_jsonl": "../../private/turns.jsonl",
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = timeline.build_project_timeline(registry_path)

        self.assertEqual(result["life_wide"]["label_count"], 0)
        self.assertEqual(result["projects"]["project:Bad Export"]["latest_turns"], [])


if __name__ == "__main__":
    unittest.main()
