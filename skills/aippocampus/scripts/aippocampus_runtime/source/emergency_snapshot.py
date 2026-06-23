#!/usr/bin/env python3
"""Pre-compaction emergency snapshots for visible thread tails.

This module writes a small private bridge before lifecycle maintenance tries to
refresh clean source. It deliberately does not become another truth layer:
clean source still owns source-backed recall, while this artifact only gives a
post-compaction agent enough local coordinates and bounded visible text to
recover the last turns if the normal rebuild did not catch up in time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.artifacts.publish import artifact_lease
from aippocampus_runtime.core import (
    codex_home,
    codex_provider,
    default_thread_clean_source_dir,
    default_thread_store_dir,
    now_utc,
    stable_json_id,
)
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows, write_json_atomic

EMERGENCY_SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_MAX_MESSAGES = 12
DEFAULT_MAX_BYTES = 24_000
SNAPSHOT_DIR_NAME = "emergency-snapshots"
LATEST_POINTER_NAME = "latest.json"
LEASE_NAME = ".emergency-snapshot.lock"


def _rollout_ref_hash(path: Path, stat: os.stat_result) -> str:
    """Hash local source coordinates without rereading the whole raw rollout.

    The emergency snapshot already scans normalized visible messages. A second
    full-file hash would make the PreCompact hook slower on exactly the large
    threads where this bridge matters. This hash is a private source coordinate,
    not content-proof evidence; clean source remains the proof-bearing layer.
    """

    material = f"{path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}"
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()


def _clean_source_keys(clean_source_dir: Path) -> set[tuple[str, str, str]]:
    keys, _ = _clean_source_keys_with_loss(clean_source_dir)
    return keys


def _clean_source_keys_with_loss(
    clean_source_dir: Path,
) -> tuple[set[tuple[str, str, str]], dict[str, Any]]:
    path = clean_source_dir / "messages.jsonl"
    if not path.exists():
        return set(), load_jsonl_dict_rows(path).loss
    keys: set[tuple[str, str, str]] = set()
    result = load_jsonl_dict_rows(path)
    for item in result.rows:
        role = str(item.get("role") or "")
        source_line = str(item.get("source_line") or "")
        text_sha1 = str(item.get("text_sha1") or item.get("sha1") or "")
        source_ref = str(item.get("source_ref") or "")
        if role and (source_line or source_ref or text_sha1):
            keys.add((role, source_ref or source_line, text_sha1))
    return keys, result.loss


def _message_key(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("role") or ""),
        str(item.get("source_ref") or item.get("line") or ""),
        str(item.get("sha1") or ""),
    )


def _turn_tail_messages(
    messages: Iterable[Mapping[str, Any]],
    *,
    represented_keys: set[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    by_turn: dict[int, list[Mapping[str, Any]]] = {}
    for message in messages:
        turn_index = message.get("turn_index")
        if isinstance(turn_index, int):
            by_turn.setdefault(turn_index, []).append(message)

    selected: list[dict[str, Any]] = []
    for turn_index in sorted(by_turn):
        items = by_turn[turn_index]
        user = next((item for item in items if item.get("role") == "user"), None)
        final = next((item for item in items if item.get("is_final")), None)
        kept = [item for item in (user, final) if item]
        if not kept:
            continue
        # Include the whole visible pair when any message in the turn is newer
        # than clean source. That repeats the already-clean user in a partially
        # indexed turn, but it preserves the user/final relationship after
        # compaction without admitting routine commentary or tool payload text.
        if represented_keys and all(_message_key(item) in represented_keys for item in kept):
            continue
        selected.extend(dict(item) for item in kept)
    return selected


def _utf8_prefix(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", errors="ignore")


def _apply_caps(messages: list[dict[str, Any]], *, max_messages: int, max_bytes: int) -> list[dict]:
    if max_messages <= 0 or max_bytes <= 0:
        return []
    capped: list[dict[str, Any]] = []
    remaining_bytes = max(0, int(max_bytes))
    for message in reversed(messages[-int(max_messages) :]):
        if remaining_bytes <= 0:
            break
        text = _utf8_prefix(str(message.get("text") or ""), remaining_bytes)
        if not text:
            continue
        item = dict(message)
        item["text"] = text
        capped.append(item)
        remaining_bytes -= len(text.encode("utf-8"))
    return list(reversed(capped))


def _public_message(
    item: Mapping[str, Any],
    *,
    source_id: str,
    thread_key: str,
) -> dict[str, Any]:
    text = str(item.get("text") or "")
    line = item.get("line")
    role = str(item.get("role") or "")
    phase = str(item.get("phase") or "")
    text_sha1 = str(item.get("sha1") or "")
    message_id = stable_json_id("emsg", thread_key, line, role, phase, text_sha1, length=20)
    return {
        "id": message_id,
        "message_id": message_id,
        "source_id": source_id,
        "source_ref": item.get("source_ref"),
        "source_line": line,
        "raw_start_line": item.get("raw_start_line") or line,
        "raw_end_line": item.get("raw_end_line") or line,
        "timestamp": item.get("timestamp"),
        "role": role,
        "kind": item.get("kind"),
        "phase": phase,
        "turn_index": item.get("turn_index"),
        "is_final": bool(item.get("is_final")),
        "text_sha1": text_sha1,
        "text_bytes": len(text.encode("utf-8")),
        "text": text,
    }


def _line_span(messages: Sequence[Mapping[str, Any]]) -> dict[str, int | None]:
    lines: list[int] = []
    for item in messages:
        line = item.get("source_line")
        if isinstance(line, int):
            lines.append(line)
    return {"start_line": min(lines) if lines else None, "end_line": max(lines) if lines else None}


def _snapshot_paths(store_dir: Path, snapshot_id: str) -> tuple[Path, Path]:
    snapshot_dir = store_dir / SNAPSHOT_DIR_NAME
    return snapshot_dir / f"{snapshot_id}.json", snapshot_dir / LATEST_POINTER_NAME


def public_snapshot_diagnostic(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return count-only lifecycle diagnostics; never include message text or paths."""

    allowed = {
        "ok",
        "status",
        "snapshot_id",
        "schema_version",
        "created_at",
        "message_count",
        "turn_count",
        "text_bytes",
        "artifact",
        "line_span",
        "source",
        "error_type",
        "clean_source_jsonl_loss",
    }
    diagnostic = {key: result[key] for key in allowed if key in result}
    if result.get("error") and not diagnostic.get("error_type"):
        diagnostic["error_type"] = type(result.get("error")).__name__
    return diagnostic


def _failure_diagnostic(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "snapshot_error",
        "schema_version": EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        "error_type": type(exc).__name__,
    }


def create_emergency_snapshot(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    cwd_path = Path(cwd).resolve()
    provider = codex_provider(codex_home())
    source_path = Path(rollout) if rollout else provider.locate_current(cwd_path).path
    source_path = source_path if source_path.is_absolute() else cwd_path / source_path
    meta = provider.read_metadata(source_path) or {}
    thread_key = provider.thread_key(source_path, meta)
    messages, turns = provider.read_normalized_messages(source_path, include_tools=False)
    represented, clean_source_jsonl_loss = _clean_source_keys_with_loss(
        default_thread_clean_source_dir(cwd_path, source_path)
    )
    selected = _apply_caps(
        _turn_tail_messages(messages, represented_keys=represented),
        max_messages=max_messages,
        max_bytes=max_bytes,
    )
    stat = source_path.stat()
    source_id = stable_json_id("esrc", thread_key, length=20)
    snapshot_messages = [
        _public_message(item, source_id=source_id, thread_key=thread_key) for item in selected
    ]
    created_at = now_utc()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_id = stable_json_id("precompact", thread_key, stamp, time.time_ns(), length=16)
    store_dir = default_thread_store_dir(cwd_path, source_path)
    snapshot_path, latest_path = _snapshot_paths(store_dir, snapshot_id)
    text_bytes = sum(int(item.get("text_bytes") or 0) for item in snapshot_messages)
    line_span = _line_span(snapshot_messages)
    source_diagnostic = {
        "provider": provider.name,
        "thread_key": thread_key,
        "session_id": meta.get("id"),
        "rollout_ref_sha256": _rollout_ref_hash(source_path, stat),
        "rollout_size": stat.st_size,
        "message_count": len(messages),
        "turn_count": len(turns),
    }
    payload: dict[str, Any] = {
        "schema_version": EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        "kind": "aippocampus_precompact_emergency_snapshot",
        "authority": "emergency_bridge_not_clean_source",
        "created_at": created_at,
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "source": source_diagnostic,
        "capture_policy": {
            "keeps": ["visible user messages", "assistant final_answer messages"],
            "drops": ["tool payloads", "attachments", "routine commentary", "raw envelopes"],
            "clean_source_filter": "capture turns not fully represented in clean source",
            "max_messages": int(max_messages),
            "max_bytes": int(max_bytes),
        },
        "line_span": line_span,
        "message_count": len(snapshot_messages),
        "turn_count": len({item.get("turn_index") for item in snapshot_messages}),
        "text_bytes": text_bytes,
        "clean_source_jsonl_loss": clean_source_jsonl_loss,
        "messages": snapshot_messages,
    }
    pointer = {
        "schema_version": EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        "kind": "aippocampus_precompact_emergency_snapshot_pointer",
        "created_at": created_at,
        "snapshot_id": snapshot_id,
        "artifact": snapshot_path.name,
        "message_count": payload["message_count"],
        "turn_count": payload["turn_count"],
        "text_bytes": text_bytes,
        "line_span": line_span,
        "source": source_diagnostic,
        "clean_source_jsonl_loss": clean_source_jsonl_loss,
    }
    with artifact_lease(snapshot_path.parent, LEASE_NAME, wait_timeout_seconds=0.0):
        write_json_atomic(snapshot_path, payload)
        write_json_atomic(latest_path, pointer)

    result = {
        "ok": True,
        "status": "written",
        "schema_version": EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        "created_at": created_at,
        "snapshot_id": snapshot_id,
        "snapshot_path": str(snapshot_path),
        "latest_path": str(latest_path),
        "artifact": snapshot_path.name,
        "message_count": payload["message_count"],
        "turn_count": payload["turn_count"],
        "text_bytes": text_bytes,
        "line_span": line_span,
        "source": source_diagnostic,
        "clean_source_jsonl_loss": clean_source_jsonl_loss,
    }
    if not snapshot_messages:
        result["status"] = "no_unrepresented_visible_tail"
    return result


def latest_emergency_snapshot_diagnostic(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
) -> dict[str, Any]:
    cwd_path = Path(cwd).resolve()
    provider = codex_provider(codex_home())
    source_path = Path(rollout) if rollout else provider.locate_current(cwd_path).path
    source_path = source_path if source_path.is_absolute() else cwd_path / source_path
    latest_path = default_thread_store_dir(cwd_path, source_path) / SNAPSHOT_DIR_NAME / LATEST_POINTER_NAME
    if not latest_path.exists():
        return {
            "ok": False,
            "status": "not_found",
            "schema_version": EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        }
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        diagnostic = _failure_diagnostic(exc)
        diagnostic["status"] = "latest_pointer_error"
        return diagnostic
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "latest_pointer_invalid",
            "schema_version": EMERGENCY_SNAPSHOT_SCHEMA_VERSION,
        }
    diagnostic = public_snapshot_diagnostic({**payload, "ok": True, "status": "found"})
    diagnostic.setdefault("schema_version", EMERGENCY_SNAPSHOT_SCHEMA_VERSION)
    return diagnostic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    try:
        if args.latest:
            result = latest_emergency_snapshot_diagnostic(args.cwd, rollout=args.rollout)
        else:
            result = create_emergency_snapshot(
                args.cwd,
                rollout=args.rollout,
                max_messages=args.max_messages,
                max_bytes=args.max_bytes,
            )
            result = public_snapshot_diagnostic(result)
    except Exception as exc:
        result = _failure_diagnostic(exc)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
