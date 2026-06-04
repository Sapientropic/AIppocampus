#!/usr/bin/env python3
"""Public-safe fixtures for recall navigation comparison smoke."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.ops.recall_navigation_comparison import (
    build_recall_navigation_comparison,
)
from aippocampus_runtime.recall.prompt_context_render import context_for_hook
from aippocampus_runtime.recall.prompt_recall_decision import assess_prompt


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


def _write_foreground_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, line INTEGER, timestamp TEXT, role TEXT, kind TEXT, "
            "phase TEXT, turn_index INTEGER, is_final INTEGER, text TEXT)"
        )
        rows = [
            (
                1,
                10,
                "2026-06-03T00:00:00Z",
                "user",
                "message",
                "",
                1,
                0,
                "We discussed whether Phonics Lab Books 3 4 5 were complete.",
            ),
            (
                2,
                20,
                "2026-06-03T00:01:00Z",
                "assistant",
                "message",
                "final_answer",
                1,
                1,
                "Images were complete, but audio and lesson-loop closure still needed source reopen.",
            ),
        ]
        con.executemany(
            "INSERT INTO messages "
            "(id, line, timestamp, role, kind, phase, turn_index, is_final, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(text, tokenize='trigram')")
        con.executemany(
            "INSERT INTO messages_fts (rowid, text) VALUES (?, ?)",
            [(row[0], row[8]) for row in rows],
        )
        con.commit()
    finally:
        con.close()


def _write_foreground_registry(path: Path, *, workspace: Path, index: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "thread_key": "session:foreground-books",
        "title": "Phonics Lab Books boundary",
        "workspace_name": "foreground-books",
        "updated_at": "2026-06-03T00:02:00Z",
        "keywords": ["Phonics", "Books 3 4 5", "completion boundary", "lesson loop"],
        "summary": "Public fixture for Books 3/4/5 completion-boundary recall.",
        "representative_message_ids": [1, 2],
        "paths": {"workspace": str(workspace), "sqlite": str(index)},
    }
    path.write_text(
        json.dumps({"schema_version": 1, "threads": [entry]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _semantic_timeout_gate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "available": False,
        "decision": "skip",
        "confidence": 0.0,
        "cached": False,
        "query_aliases": ["Books 3/4/5 completion boundary"],
        "availability_reason": "semantic_worker_timeout",
        "diagnostic": "semantic_provider_read_timeout",
        "error_buckets": {"read_timeout": 1},
        "elapsed_ms": 2500,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _foreground_card_count(result: Mapping[str, Any], *, provenance: str | None = None) -> int:
    ambient = _as_dict(result.get("ambient_recall"))
    count = 0
    for card in ambient.get("cards") or []:
        if not isinstance(card, dict):
            continue
        if provenance and card.get("provenance_class") != provenance:
            continue
        count += 1
    return count


def _cards_are_navigation_only(result: Mapping[str, Any]) -> bool:
    ambient = _as_dict(result.get("ambient_recall"))
    for card in ambient.get("cards") or []:
        if not isinstance(card, dict):
            continue
        if card.get("support_level") == "evidence":
            return False
    return True


def _foreground_source_reopen_after_packet(
    result: Mapping[str, Any],
    *,
    registry_path: Path,
) -> dict[str, Any]:
    ambient = _as_dict(result.get("ambient_recall"))
    packet = _as_dict(ambient.get("fresh_thread_packet"))
    candidate_refs = [ref for ref in packet.get("candidate_refs") or [] if isinstance(ref, dict)]
    selected_ref = next((ref for ref in candidate_refs if ref.get("thread_key")), None)
    # This follow-through intentionally uses the packet ref, not a text query;
    # otherwise the fixture would hide the manual-query invention #201 tracks.
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    threads = [entry for entry in registry.get("threads") or [] if isinstance(entry, dict)]
    matched_threads = [
        entry for entry in threads if entry.get("thread_key") == (selected_ref or {}).get("thread_key")
    ]
    source_rows_checked = 0
    expected_source_found = False
    if matched_threads:
        sqlite_path = Path(str(_as_dict(matched_threads[0].get("paths")).get("sqlite") or ""))
        if sqlite_path.exists():
            con = sqlite3.connect(sqlite_path)
            try:
                rows = con.execute(
                    "SELECT text FROM messages WHERE is_final = 1 ORDER BY id"
                ).fetchall()
            finally:
                con.close()
            source_rows_checked = len(rows)
            expected_source_found = any(
                "audio and lesson-loop closure" in str(row[0])
                and "source reopen" in str(row[0])
                for row in rows
            )
    return {
        "measured": True,
        "candidate_ref_count": len(candidate_refs),
        "candidate_ref_consumed": bool(selected_ref),
        "selected_ref_kind": "thread_key" if selected_ref else "",
        "selected_next_action": "reopen_registry_thread_source_index" if selected_ref else "",
        "registry_match_count": len(matched_threads),
        "source_rows_checked": source_rows_checked,
        "source_reopen_attempted": bool(selected_ref),
        "source_reopen_follow_through": expected_source_found,
        "manual_query_invention_count": 0,
        "source_boundary_preserved": len(result.get("evidence") or []) == 0,
        "raw_source_snippet_serialized": False,
        "local_paths_serialized": False,
    }


def fixture_foreground_lift_measurement(root: Path) -> dict[str, Any]:
    """Run a public-safe two-turn prompt-hook measurement for #201.

    This is intentionally a deterministic fixture, not a live quality claim.
    The semantic provider path is simulated as a timeout so the measurement can
    assert that local hot-path routing and ambient cache reuse remain available
    without external model calls or source-backed fact promotion.
    """

    workspace = root / "foreground-workspace"
    old_thread = root / "foreground-old-thread"
    workspace.mkdir(exist_ok=True)
    old_thread.mkdir(exist_ok=True)
    sqlite_path = old_thread / ".aippocampus" / "source_index.sqlite"
    registry_path = root / "foreground-registry" / "threads.json"
    cache_path = root / "foreground-cache.json"
    _write_foreground_sqlite(sqlite_path)
    _write_foreground_registry(registry_path, workspace=old_thread, index=sqlite_path)

    first = assess_prompt(
        "之前说 Books 3/4/5 完成了吗，继续那个",
        cwd=workspace,
        registry_path=registry_path,
        semantic_gate_mode="on",
        semantic_gate_fn=_semantic_timeout_gate,
        use_semantic_gate=True,
        max_elapsed_ms=4300,
        semantic_timeout=2.5,
        thread_id="thread-201-foreground",
        topic_epoch="epoch-books",
        ambient_cache_path=cache_path,
        warm_background=False,
        search_budget=0,
    )
    second = assess_prompt(
        "继续这个 Books 3/4/5 边界",
        cwd=workspace,
        registry_path=registry_path,
        semantic_gate_mode="off",
        use_semantic_gate=False,
        thread_id="thread-201-foreground",
        topic_epoch="epoch-books",
        ambient_cache_path=cache_path,
        warm_background=True,
        search_budget=0,
    )

    first_hot_path = _as_dict(first.get("hot_path_funnel"))
    first_route = _as_dict(first.get("route_delivery_diagnostic"))
    first_ambient = _as_dict(first.get("ambient_recall"))
    first_cache = _as_dict(first_ambient.get("cache_status"))
    second_ambient = _as_dict(second.get("ambient_recall"))
    second_cache = _as_dict(second_ambient.get("cache_status"))
    first_context = context_for_hook(first)
    second_context = context_for_hook(second)
    first_route_actionable = bool(
        first.get("decision") == "scent"
        and first_hot_path.get("decision") == "scent"
        and int(first_hot_path.get("candidate_count") or 0) > 0
        and int(first_route.get("hot_path_candidates_after_merge") or 0) > 0
        and first_context
    )
    semantic_timeout_route = bool(
        first_route_actionable
        and first_route.get("semantic_reuse_source") == "semantic_provider_timeout"
    )
    second_cache_reuse = bool(
        second.get("decision") == "scent"
        and second_cache.get("status") == "hit"
        and _foreground_card_count(second, provenance="cached_warm_card") > 0
        and second_context
    )
    source_boundary_preserved = bool(
        len(first.get("evidence") or []) == 0
        and len(second.get("evidence") or []) == 0
        and _cards_are_navigation_only(first)
        and _cards_are_navigation_only(second)
    )
    source_reopen_after_packet = _foreground_source_reopen_after_packet(
        first,
        registry_path=registry_path,
    )
    return {
        "measured": True,
        "case_id": "foreground_semantic_timeout_books_cache_lift",
        "first_turn_lift": (
            "measured_route_hint_under_semantic_timeout"
            if semantic_timeout_route
            else "not_measured"
        ),
        "second_turn_lift": "measured_cache_reuse" if second_cache_reuse else "not_measured",
        "semantic_timeout_but_route_available": semantic_timeout_route,
        "source_boundary_preserved": source_boundary_preserved,
        "first_turn": {
            "decision": str(first.get("decision") or ""),
            "route_actionable": first_route_actionable,
            "semantic_reuse_source": str(first_route.get("semantic_reuse_source") or ""),
            "hot_path_candidate_count": int(first_hot_path.get("candidate_count") or 0),
            "hot_path_stage": str(
                ((_as_dict((first_hot_path.get("stages") or [{}])[0])).get("stage"))
                or ""
            ),
            "evidence_count": len(first.get("evidence") or []),
            "ambient_card_count": _foreground_card_count(first),
            "cache_status": str(first_cache.get("status") or ""),
            "cache_write_status": str(first_cache.get("write_status") or ""),
            "context_delivered": bool(first_context),
        },
        "second_turn": {
            "decision": str(second.get("decision") or ""),
            "route_actionable": bool(second_context and second.get("decision") != "skip"),
            "cache_status": str(second_cache.get("status") or ""),
            "cached_card_count": _foreground_card_count(second, provenance="cached_warm_card"),
            "evidence_count": len(second.get("evidence") or []),
            "reschedule_avoided": "warm_background" not in second_ambient,
            "context_delivered": bool(second_context),
        },
        "source_reopen_after_packet": source_reopen_after_packet,
        "boundary": {
            "deterministic_fixture_only": True,
            "semantic_provider_simulated_timeout": True,
            "no_external_model_calls": True,
            "navigation_only_until_source_reopen": True,
            "packet_reopen_uses_candidate_ref_not_manual_query": True,
        },
    }


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
        foreground_lift = fixture_foreground_lift_measurement(root)
        return build_recall_navigation_comparison(
            fixture_cases(),
            cwd=root,
            clean_source_dir=clean,
            after_context_by_case_id={
                "stale_handle_fast_reject": lambda: _append_fixture_mutation(clean)
            },
            foreground_lift=foreground_lift,
        )
