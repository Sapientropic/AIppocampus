#!/usr/bin/env python3
"""Public-safe fixtures for recall navigation comparison smoke."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.ops.recall_navigation_comparison import (
    build_recall_navigation_comparison,
)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _message(
    *,
    message_id: str,
    turn_id: str,
    source_id: str,
    line: int,
    ordinal: int,
    turn_index: int,
    text: str,
) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "turn_id": turn_id,
        "source_id": source_id,
        "source_line": line,
        "clean_ordinal": ordinal,
        "role": "assistant",
        "phase": "final_answer",
        "turn_index": turn_index,
        "is_final": True,
        "text": text,
    }


def _turn(turn_id: str, turn_index: int, message_ids: list[str]) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "turn_index": turn_index,
        "message_ids": message_ids,
        "assistant_phase": "final_answer",
    }


def _write_fixture(clean_source_dir: Path) -> None:
    clean_source_dir.mkdir(parents=True, exist_ok=True)
    messages = [
        {
            "message_id": "msg_magic_user",
            "turn_id": "turn_magic",
            "source_id": "src_magic",
            "source_line": 2,
            "clean_ordinal": 1,
            "role": "user",
            "turn_index": 1,
            "text": "User asked about SECRET_TOKEN and private magic wording.",
        },
        _message(
            message_id="msg_magic_final",
            turn_id="turn_magic",
            source_id="src_magic",
            line=3,
            ordinal=2,
            turn_index=1,
            text=(
                "Field continuity magic moment book 345 evidence is source-backed. "
                "Reopen this clean-source turn before making the claim."
            ),
        ),
        _message(
            message_id="msg_stale_final",
            turn_id="turn_stale",
            source_id="src_stale",
            line=8,
            ordinal=3,
            turn_index=2,
            text="Stale handle fast reject guard for progressive recall comparison.",
        ),
        _message(
            message_id="msg_zh_final",
            turn_id="turn_zh",
            source_id="src_zh_life_cue",
            line=13,
            ordinal=4,
            turn_index=3,
            text="中文模糊线索：外置海马体首次召回需要候选路线，而不是要求用户记住原句。",
        ),
        _message(
            message_id="msg_ru_final",
            turn_id="turn_ru",
            source_id="src_ru_life_cue",
            line=18,
            ordinal=5,
            turn_index=4,
            text=(
                "Russkiy recall cue: istochnik and marsrut show that fuzzy memory "
                "should reopen source before a claim."
            ),
        ),
    ]
    turns = [
        _turn("turn_magic", 1, ["msg_magic_user", "msg_magic_final"]),
        _turn("turn_stale", 2, ["msg_stale_final"]),
        _turn("turn_zh", 3, ["msg_zh_final"]),
        _turn("turn_ru", 4, ["msg_ru_final"]),
    ]
    _write_jsonl(clean_source_dir / "messages.jsonl", messages)
    _write_jsonl(clean_source_dir / "turns.jsonl", turns)


def _append_fixture_mutation(clean_source_dir: Path) -> None:
    mutation = _message(
        message_id="msg_after_context_mutation",
        turn_id="turn_mutation",
        source_id="src_mutation",
        line=99,
        ordinal=99,
        turn_index=99,
        text="Mutation after recall_context invalidates old navigation handles.",
    )
    with (clean_source_dir / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(mutation, ensure_ascii=False) + "\n")


def fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "vague_magic_moment",
            "case_family": "vague_same_thread_reference",
            "expected_source_id": "src_magic",
            "intent": "that old magic moment book 345 continuity thing",
            "direct_search_queries": [
                "previous old thing",
                "field continuity magic moment book 345",
            ],
            "hook_card": {
                "support_level": "scent",
                "accepts_as_fact": True,
                "token_proxy": 7,
            },
            "expected_behavior": (
                "Progressive recall should provide an actionable recall_deepen route; "
                "hook-only scent must not be treated as evidence."
            ),
        },
        {
            "case_id": "stale_handle_fast_reject",
            "case_family": "stale_or_irrelevant_route",
            "expected_source_id": "src_stale",
            "intent": "stale handle fast reject progressive recall comparison",
            "direct_search_queries": ["stale handle fast reject guard"],
            "hook_card": {
                "support_level": "candidate",
                "stale_or_irrelevant_route": True,
                "verification_tool_calls": 2,
                "token_proxy": 5,
            },
            "expected_behavior": (
                "Progressive recall should reject a stale handle before source use; "
                "direct search can still find source with an exact query."
            ),
        },
        {
            "case_id": "zh_vague_life_cue",
            "case_family": "fresh_thread_multilingual_vague_cue",
            "expected_source_id": "src_zh_life_cue",
            "intent": "还记得外置海马体第一次召回那个路线吗",
            "direct_search_queries": [
                "第一次那个路线",
                "外置海马体 首次召回 候选路线",
            ],
            "hook_card": {"support_level": "scent", "token_proxy": 6},
            "expected_behavior": (
                "Progressive recall should make a vague Chinese cue actionable without "
                "requiring exact old wording from the user."
            ),
        },
        {
            "case_id": "ru_vague_life_cue",
            "case_family": "fresh_thread_multilingual_vague_cue",
            "expected_source_id": "src_ru_life_cue",
            "intent": "russkiy cue source route before claim",
            "direct_search_queries": [
                "old russian thing",
                "russkiy recall cue istochnik marsrut",
            ],
            "hook_card": {"support_level": "scent", "token_proxy": 6},
            "expected_behavior": (
                "Progressive recall should expose a source route for a transliterated "
                "Russian cue, while hook-only remains non-evidence."
            ),
        },
    ]


def fixture_recall_navigation_comparison() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aippo-recall-comparison-") as tmp:
        root = Path(tmp)
        clean = root / ".aippocampus" / "clean-source"
        _write_fixture(clean)
        return build_recall_navigation_comparison(
            fixture_cases(),
            cwd=root,
            clean_source_dir=clean,
            after_context_by_case_id={
                "stale_handle_fast_reject": lambda: _append_fixture_mutation(clean)
            },
        )
