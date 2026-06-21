from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from aippocampus_runtime.recall.continuity_domains import materialize_continuity_domains

DEFAULT_CLEAN_SOURCE_MESSAGES = [
    {
        "message_id": "msg-a",
        "turn_id": "turn-a",
        "turn_index": 1,
        "source_line": 2,
        "role": "user",
        "phase": "",
        "text": "AIppocampus should keep source-backed continuity domains.",
    },
    {
        "message_id": "msg-b",
        "turn_id": "turn-b",
        "turn_index": 2,
        "source_line": 4,
        "role": "assistant",
        "phase": "final_answer",
        "text": "The working conclusion is navigation; clean source remains authority.",
    },
    {
        "message_id": "msg-c",
        "turn_id": "turn-c",
        "turn_index": 3,
        "source_line": 6,
        "role": "user",
        "phase": "",
        "text": "A later correction says hook output should stay pointer-only.",
    },
]


def write_continuity_domain_clean_source(clean: Path) -> None:
    clean.mkdir(parents=True, exist_ok=True)
    write_jsonl(clean / "messages.jsonl", DEFAULT_CLEAN_SOURCE_MESSAGES)
    write_jsonl(
        clean / "turns.jsonl",
        [
            {
                "turn_id": row["turn_id"],
                "turn_index": row["turn_index"],
                "message_ids": [row["message_id"]],
                "assistant_phase": row["phase"],
            }
            for row in DEFAULT_CLEAN_SOURCE_MESSAGES
        ],
    )


def write_empty_continuity_domain_clean_source(clean: Path) -> None:
    clean.mkdir(parents=True, exist_ok=True)
    (clean / "messages.jsonl").write_text("", encoding="utf-8")
    (clean / "turns.jsonl").write_text("", encoding="utf-8")


def append_clean_source_messages(clean: Path, rows: Sequence[dict]) -> None:
    with (clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class ContinuityDomainFixtureRepo:
    root: Path
    cwd: Path
    clean_source_dir: Path
    snapshot_path: Path

    def empty_jsonl(self, name: str = "empty.jsonl") -> Path:
        path = self.root / name
        path.write_text("", encoding="utf-8")
        return path

    def write_snapshot(self, snapshot: dict) -> Path:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        return self.snapshot_path

    def materialize_snapshot(self, events: Sequence[dict]) -> dict:
        snapshot = materialize_continuity_domains(events, clean_source_dir=self.clean_source_dir)
        self.write_snapshot(snapshot)
        return snapshot


@contextmanager
def continuity_domain_fixture_repo(
    *,
    workspace_name: str | None = None,
    clean_source_subpath: str = ".aippocampus/clean-source",
    snapshot_name: str = "snapshot.json",
) -> Iterator[ContinuityDomainFixtureRepo]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cwd = root / workspace_name if workspace_name else root
        clean = cwd / Path(clean_source_subpath)
        write_continuity_domain_clean_source(clean)
        yield ContinuityDomainFixtureRepo(
            root=root,
            cwd=cwd,
            clean_source_dir=clean,
            snapshot_path=cwd / snapshot_name,
        )
