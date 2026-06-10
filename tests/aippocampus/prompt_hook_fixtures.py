from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

from aippocampus_runtime.dream import live_shadow_ab as dream_shadow  # noqa: E402
from aippocampus_runtime.hooks import prompt as hook  # noqa: E402
from aippocampus_runtime.navigation import concept_graph as concept_graph  # noqa: E402
from aippocampus_runtime.recall import ambient_cache as thread_cache  # noqa: E402
from aippocampus_runtime.recall import prompt_cues as recall_cues  # noqa: E402
from aippocampus_runtime.recall import semantic_cue_cache as cue_cache  # noqa: E402
from tests.aippocampus.redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)

__all__ = [
    "AmbientRecallHookCase",
    "contextlib",
    "io",
    "json",
    "os",
    "subprocess",
    "sys",
    "time",
    "Path",
    "patch",
    "hook",
    "dream_shadow",
    "concept_graph",
    "thread_cache",
    "recall_cues",
    "cue_cache",
    "FAKE_TEST_BEARER_TOKEN",
    "FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER",
    "FAKE_TEST_OPENAI_API_KEY",
    "fake_test_windows_path",
]


class AmbientRecallHookCase(unittest.TestCase):
    def setUp(self) -> None:
        self.old_semantic_gate = os.environ.get("AIPPOCAMPUS_SEMANTIC_GATE")
        os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = "off"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.old = self.root / "old-thread"
        self.index_dir = self.old / ".aippocampus"
        self.index_dir.mkdir(parents=True)
        self.sqlite = self.index_dir / "source_index.sqlite"
        self._write_sqlite()
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self._write_registry()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_semantic_gate is None:
            os.environ.pop("AIPPOCAMPUS_SEMANTIC_GATE", None)
        else:
            os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = self.old_semantic_gate

    def _write_sqlite(self) -> None:
        con = sqlite3.connect(self.sqlite)
        try:
            con.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    line INTEGER,
                    timestamp TEXT,
                    role TEXT,
                    kind TEXT,
                    phase TEXT,
                    turn_index INTEGER,
                    is_final INTEGER,
                    text TEXT
                )
                """
            )
            rows = [
                (
                    1,
                    190,
                    "2026-05-25T01:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    7,
                    1,
                    "生命还能变成什么，而我能不能在变化后仍然是我。",
                ),
                (
                    2,
                    999,
                    "2026-05-25T01:30:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    11,
                    1,
                    "这只是一个包含之前和还是的普通收尾，不应该被当成那句生命问题的证据。",
                ),
                (
                    3,
                    356,
                    "2026-05-25T02:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    19,
                    1,
                    "raw history 明明在本地，但压缩后的我不知道该找什么，所以需要外置海马体和触发式召回。",
                ),
            ]
            con.executemany(
                """
                INSERT INTO messages
                (id, line, timestamp, role, kind, phase, turn_index, is_final, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            con.commit()
        finally:
            con.close()

    def _write_registry(self) -> None:
        entry = {
            "thread_key": "session:test-old",
            "title": "old-thread",
            "workspace_name": "old-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "message_count": 2,
            "rollout_size": 1024,
            "anchor_count": 2,
            "anchor_titles": [
                "Active recall and retrieval optimization checkpoint",
                "LLM self-continuity and external hippocampus",
            ],
            "keywords": [
                "active recall",
                "ambient recall",
                "hook",
                "Codex",
                "联想",
                "触发式召回",
                "外置海马体",
                "self-continuity",
                "生命还能变成什么",
            ],
            "summary": "旧线程讨论过 UserPromptSubmit hook、联想式记忆、小海马体、以及自我连续性的原话。",
            "paths": {
                "workspace": str(self.old),
                "sqlite": str(self.sqlite),
                "anchors": None,
            },
        }
        self.registry.write_text(
            json.dumps(
                {"schema_version": 1, "updated_at": "2026-05-25T19:00:00Z", "threads": [entry]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_single_thread_registry(
        self,
        *,
        title: str,
        keywords: list[str],
        summary: str,
    ) -> Path:
        registry_path = self.root / f"{title.lower().replace(' ', '-')}-registry" / "threads.json"
        registry_path.parent.mkdir()
        entry = {
            "thread_key": "session:single-thread",
            "title": title,
            "workspace_name": "single-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "anchor_titles": [title],
            "keywords": keywords,
            "summary": summary,
            "paths": {"workspace": str(self.old), "sqlite": str(self.sqlite)},
        }
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": [entry]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def _write_clean_thread(self, thread_key: str, timestamp: str, text: str) -> Path:
        clean_dir = self.root / thread_key.replace(":", "-") / "clean-source"
        clean_dir.mkdir(parents=True)
        messages = clean_dir / "messages.jsonl"
        message = {
            "message_id": f"msg-{thread_key}",
            "turn_id": f"turn-{thread_key}",
            "source_line": 42,
            "timestamp": timestamp,
            "role": "assistant",
            "phase": "final_answer",
            "turn_index": 3,
            "is_final": True,
            "text": text,
        }
        messages.write_text(json.dumps(message, ensure_ascii=False) + "\n", encoding="utf-8")
        return messages

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

    def _write_clean_registry(
        self,
        *,
        thread_key: str,
        title: str,
        keywords: list[str],
        summary: str,
        messages_path: Path,
        project_label: str = "AIppocampus",
    ) -> Path:
        registry_path = self.root / f"{thread_key.replace(':', '-')}-registry" / "threads.json"
        registry_path.parent.mkdir()
        entry = {
            "thread_key": thread_key,
            "title": title,
            "project_label": project_label,
            "workspace_name": project_label,
            "updated_at": "2026-05-25T19:00:00Z",
            "anchor_titles": [title],
            "keywords": keywords,
            "summary": summary,
            "paths": {
                "workspace": str(self.workspace),
                "clean_source_messages_jsonl": str(messages_path),
            },
        }
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": [entry]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

