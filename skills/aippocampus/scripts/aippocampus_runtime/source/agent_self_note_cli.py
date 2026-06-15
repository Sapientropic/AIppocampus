#!/usr/bin/env python3
"""Public CLI for low-authority foreground-agent self-notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.agent_self_notes import (
    VALID_TRIGGERS,
    AgentSelfNoteRejected,
    append_agent_self_note,
    default_agent_self_notes_path,
    load_agent_self_notes,
    public_agent_self_note_route_refs,
    public_agent_self_note_surface,
    search_agent_self_notes,
)

CURRENT_THREAD_SOURCE_REF = "current_thread_neighborhood"
CURRENT_THREAD_ENV_KEYS = (
    "AIPPOCAMPUS_CURRENT_THREAD_KEY",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
)


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def current_thread_self_note_route(
    *,
    cwd: str | Path,
    rollout: str | Path | None = None,
) -> dict[str, Any]:
    """Build a public-safe current-thread route for a self-note.

    Raw Codex rollout paths and session ids are good private reopen anchors but
    poor public CLI output. The current-thread append path therefore stores a
    stable route handle derived from the available raw identity while only
    exposing the compact handle. Do not replace this with the raw `session:<id>`
    thread key in JSON output; #893 depends on foreground agents being able to
    prove the note is atmosphere without leaking local source identifiers.
    """

    from aippocampus_runtime.core import (
        codex_home,
        locate_rollout,
        public_session_meta,
        read_session_meta,
        thread_key_from_rollout,
        workspace_thread_key,
    )

    cwd_path = Path(cwd).resolve()
    raw_identity = ""
    source = "workspace_fallback"
    current_thread_available = False
    if rollout:
        try:
            rollout_path = Path(rollout).resolve()
            meta = public_session_meta(read_session_meta(rollout_path))
            raw_identity = thread_key_from_rollout(rollout_path, meta)
            source = "explicit_rollout"
            current_thread_available = True
        except Exception:
            raw_identity = ""
    if not raw_identity:
        try:
            rollout_path = locate_rollout(cwd_path, codex_home())
            meta = public_session_meta(read_session_meta(rollout_path))
            raw_identity = thread_key_from_rollout(rollout_path, meta)
            source = "codex_rollout"
            current_thread_available = True
        except Exception:
            raw_identity = ""
    if not raw_identity:
        for key in CURRENT_THREAD_ENV_KEYS:
            value = os.environ.get(key)
            if value:
                raw_identity = f"{key}:{value}"
                source = key
                current_thread_available = True
                break
    if not raw_identity:
        raw_identity = workspace_thread_key(cwd_path)

    public_thread_key = _stable_id("current_thread", raw_identity, cwd_path.name)
    source_ref = {
        "thread_key": public_thread_key,
        "source_id": (
            "codex_current_thread" if current_thread_available else "workspace_current_thread"
        ),
        "source_ref": CURRENT_THREAD_SOURCE_REF,
        "phase": "agent_self_note_append",
        "title": "Current thread neighborhood",
    }
    return {
        "thread_key": public_thread_key,
        "source_refs": [source_ref],
        "current_thread_available": current_thread_available,
        "source": source,
        "raw_rollout_path_serialized": False,
        "raw_thread_id_serialized": False,
        "local_path_serialized": False,
    }


def _parse_source_ref_json(values: list[str] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for value in values or []:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid --source-ref-json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit("--source-ref-json must decode to an object")
        refs.append(parsed)
    return refs


def _registry_path_from_args(args: argparse.Namespace) -> Path | None:
    if args.registry:
        return Path(args.registry).resolve()
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    return registry_paths(registry_dir)[0]


def _notes_path_from_args(args: argparse.Namespace, registry_path: Path | None) -> Path:
    if args.notes_path:
        return Path(args.notes_path).resolve()
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    return default_agent_self_notes_path(registry_path, registry_dir)


def _public_append_note(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "note_id",
        "created_at",
        "note_text",
        "author_role",
        "trigger",
        "authority",
        "support_level",
        "trust_level",
        "action_grammar",
        "trust_contract",
        "memory_surface",
        "use_boundary",
        "truth_boundary",
        "claims_user_fact",
        "claims_world_fact",
        "claims_source_fact",
        "source_reopen_required_before_claim",
        "clean_source_mutation_allowed",
        "formal_memory_eligible",
        "foreground_default_visible",
        "source_ref_count",
        "foreground_projection_max_chars",
        "note_body_private_available",
        "note_body_private_chars",
        "note_body_private_max_chars",
        "note_body_private_default_visible",
        "note_body_private_reopen_required",
    )
    public = {key: row.get(key) for key in keys if row.get(key) not in (None, "", [])}
    public["source_boundary"] = {
        "self_note_is_not_source_fact": True,
        "source_refs_are_reopen_routes_not_proof_of_note": True,
        "source_reopen_required_before_claim": True,
    }
    return public


def _privacy_boundary() -> dict[str, Any]:
    return {
        "raw_local_path_emitted": False,
        "raw_rollout_id_emitted": False,
        "raw_prompt_emitted": False,
        "clean_source_mutation_allowed": False,
        "output_shape": "public_agent_self_note_append",
    }


def _source_reopen_routes(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        for route in public_agent_self_note_route_refs(row, limit=4):
            if not route:
                continue
            route["source_reopen_required_before_claim"] = True
            marker = tuple(sorted((key, str(value)) for key, value in route.items()))
            if marker in seen:
                continue
            seen.add(marker)
            routes.append(route)
            if len(routes) >= limit:
                return routes
    return routes


def _agent_self_note_round_trip_preview(
    *,
    note_text: str,
    notes_path: Path,
    max_matches: int = 1,
) -> dict[str, Any]:
    matches = search_agent_self_notes(
        note_text,
        load_agent_self_notes(notes_path),
        limit=max_matches,
    )
    memory_atmosphere = [public_agent_self_note_surface(row) for row in matches]
    routes = _source_reopen_routes(matches, limit=max_matches)
    return {
        "kind": "aippocampus_agent_initiated_recall_context",
        "schema_version": 1,
        "decision": "context" if memory_atmosphere or routes else "empty",
        "agent_initiated_recall": True,
        "memory_atmosphere": memory_atmosphere,
        "working_continuity_brief": [],
        "source_reopen_routes": routes,
        "surface_counts": {
            "agent_self_notes": len(memory_atmosphere),
            "working_memory": 0,
            "dream": 0,
            "atmosphere": len(memory_atmosphere),
        },
        "source_boundary": {
            "passive_hook_required": False,
            "hook_auto_injection_unchanged": True,
            "direction_only_is_not_evidence": True,
            "source_reopen_required_for_facts": True,
            "raw_prompt_serialized": False,
            "local_paths_serialized": False,
        },
        "suggested_next": "reopen_source" if routes else "search_clean_source",
    }


def _append_error_payload(code: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code}
    payload = {
        "kind": "aippocampus_agent_self_note_append",
        "ok": False,
        "error": error,
        "privacy_boundary": _privacy_boundary(),
    }
    if details:
        error["details"] = {
            key: value
            for key, value in details.items()
            if isinstance(value, (str, int, float, bool))
        }
    return payload


def _append_success_payload(
    *,
    row: Mapping[str, Any],
    current_thread: Mapping[str, Any] | None,
    notes_path: Path,
    note_text: str,
) -> dict[str, Any]:
    preview = (
        _agent_self_note_round_trip_preview(
            note_text=note_text,
            notes_path=notes_path,
            max_matches=1,
        )
        if current_thread is not None
        else None
    )
    payload = {
        "kind": "aippocampus_agent_self_note_append",
        "ok": True,
        "note": _public_append_note(row),
        "source_ref_attached": bool(row.get("source_ref_count")),
        "current_thread": (
            {
                "available": bool(current_thread.get("current_thread_available")),
                "source": current_thread.get("source"),
                "raw_rollout_path_serialized": False,
                "raw_thread_id_serialized": False,
                "local_path_serialized": False,
            }
            if current_thread is not None
            else None
        ),
        "round_trip_preview": preview,
        "privacy_boundary": _privacy_boundary(),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _print_command_help(command: str) -> None:
    examples = {
        "append": 'example: aippocampus self-note append --current-thread "short note"',
        "search": 'example: aippocampus self-note search "thread atmosphere" --json',
        "list": "example: aippocampus self-note list --max 4 --json",
    }
    parser = argparse.ArgumentParser(
        prog=f"aippocampus self-note {command}",
        description="Manage low-authority foreground-agent self-notes.",
    )
    parser.add_argument("text", nargs="*", help="Note text for append or query text for search.")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--notes-path")
    parser.add_argument("--thread-key", default="unknown-thread")
    parser.add_argument("--current-thread", action="store_true")
    parser.add_argument("--rollout")
    parser.add_argument("--trigger", choices=sorted(VALID_TRIGGERS))
    parser.add_argument("--source-ref-json", action="append")
    parser.add_argument("--max", type=int, default=4)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.epilog = examples[command]
    parser.print_help()


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] in {"append", "search", "list"} and any(
        item in {"-h", "--help"} for item in raw_args[1:]
    ):
        _print_command_help(raw_args[0])
        return 0

    parser = argparse.ArgumentParser(prog="aippocampus self-note")
    parser.add_argument("command", choices=["append", "search", "list"])
    parser.add_argument("text", nargs="*", help="Note text for append or query text for search.")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--notes-path")
    parser.add_argument("--thread-key", default="unknown-thread")
    parser.add_argument("--current-thread", action="store_true")
    parser.add_argument("--rollout")
    parser.add_argument(
        "--trigger",
        default="explicit_agent_reflection",
        choices=sorted(VALID_TRIGGERS),
    )
    parser.add_argument("--source-ref-json", action="append")
    parser.add_argument("--max", type=int, default=4)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(raw_args)

    registry_path = _registry_path_from_args(args)
    notes_path = _notes_path_from_args(args, registry_path)

    text_parts = list(args.text or [])
    if args.stdin:
        text_parts.append(sys.stdin.read())
    text = " ".join(text_parts).strip()

    if args.command == "append":
        return _run_append(args, text=text, notes_path=notes_path)
    if args.command == "search":
        rows = search_agent_self_notes(text, load_agent_self_notes(notes_path), limit=args.max)
        payload = {
            "kind": "aippocampus_agent_self_note_search",
            "query": text,
            "count": len(rows),
            "rows": [public_agent_self_note_surface(row) for row in rows],
        }
    else:
        rows = load_agent_self_notes(notes_path)[: max(0, int(args.max or 0))]
        payload = {
            "kind": "aippocampus_agent_self_notes",
            "rows": [public_agent_self_note_surface(row) for row in rows],
        }

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        payload_rows = payload.get("rows")
        if isinstance(payload_rows, list):
            for payload_row in payload_rows:
                if isinstance(payload_row, dict):
                    print(f"- {payload_row.get('created_at')} {payload_row.get('note_text')}")
    return 0


def _run_append(args: argparse.Namespace, *, text: str, notes_path: Path) -> int:
    if not text:
        payload = _append_error_payload("agent_self_note_empty")
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("agent_self_note_empty", file=sys.stderr)
        return 1
    cwd_path = Path(args.cwd).resolve()
    current_thread = (
        current_thread_self_note_route(cwd=cwd_path, rollout=args.rollout)
        if args.current_thread
        else None
    )
    thread_key = (
        str(current_thread["thread_key"])
        if current_thread is not None
        else args.thread_key
    )
    source_refs = (
        list(current_thread["source_refs"])
        if current_thread is not None
        else _parse_source_ref_json(args.source_ref_json)
    )
    try:
        row = append_agent_self_note(
            notes_path,
            note_text=text,
            thread_key=thread_key,
            source_refs=source_refs,
            trigger=args.trigger,
            project_root=cwd_path,
        )
    except AgentSelfNoteRejected as exc:
        payload = _append_error_payload(exc.code, exc.details)
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(exc.code, file=sys.stderr)
        return 1
    payload = (
        _append_success_payload(
            row=row,
            current_thread=current_thread,
            notes_path=notes_path,
            note_text=text,
        )
        if args.current_thread
        else {
            "kind": "aippocampus_agent_self_note_append",
            "ok": True,
            "note": _public_append_note(row),
            "source_ref_attached": bool(row.get("source_ref_count")),
            "privacy_boundary": _privacy_boundary(),
        }
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        payload_row = payload.get("row") or payload.get("note")
        note_id = payload_row.get("note_id") if isinstance(payload_row, dict) else ""
        print(f"agent self-note: {note_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
