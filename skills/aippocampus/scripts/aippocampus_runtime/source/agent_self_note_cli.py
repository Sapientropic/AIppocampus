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

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.agent_self_note_actions import (
    append_error_payload as build_append_error_payload,
)
from aippocampus_runtime.source.agent_self_note_actions import (
    empty_notes_state as _empty_notes_state,
)
from aippocampus_runtime.source.agent_self_note_actions import (
    format_action_for_human,
)
from aippocampus_runtime.source.agent_self_note_actions import (
    self_note_lookup_actions as _self_note_lookup_actions,
)
from aippocampus_runtime.source.agent_self_notes import (
    VALID_TRIGGERS,
    AgentSelfNoteRejected,
    append_agent_self_note,
    default_agent_self_notes_path,
    load_agent_self_notes,
    project_scope_id,
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
    public["agent_next_action"] = (
        "Treat this as direction-only atmosphere; reopen attached source before any "
        "user, world, or source factual claim."
    )
    return public


def _privacy_boundary() -> dict[str, Any]:
    return {
        "raw_local_path_emitted": False,
        "raw_rollout_id_emitted": False,
        "raw_prompt_emitted": False,
        "clean_source_mutation_allowed": False,
        "output_shape": "public_agent_self_note_append",
    }


def _write_boundary() -> dict[str, Any]:
    return {
        "written": False,
        "no_write_happened": True,
        "clean_source_mutation_allowed": False,
    }


def _self_note_recovery_payload() -> dict[str, Any]:
    choices: list[dict[str, Any]] = [
        {
            "id": "list_direction_only_notes",
            "label": "list",
            "command": "aippocampus self-note list --json",
            "mutation_risk": "read_only",
            "claim_boundary": "direction_only_not_source_truth",
            "when": "Review recent scoped notes without treating them as evidence.",
        },
        {
            "id": "search_direction_only_notes",
            "label": "search",
            "command_template": 'aippocampus self-note search "{cue}" --json',
            "requires": ["cue"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "direction_only_not_source_truth",
            "when": "Find direction-only atmosphere for the current workspace.",
        },
        {
            "id": "append_direction_only_note",
            "label": "append",
            "command_template": 'aippocampus self-note append --current-thread "{note_text}"',
            "requires": ["note_text"],
            "template_only": True,
            "mutation_risk": "explicit_direction_only_note_write",
            "claim_boundary": "direction_only_not_source_truth",
            "when": "Write only after the user or foreground task explicitly asks to leave a note.",
        },
        {
            "id": "read_direction_only_note",
            "label": "read",
            "command_template": "aippocampus self-note read {note_id} --json",
            "requires": ["note_id"],
            "template_only": True,
            "mutation_risk": "read_only",
            "claim_boundary": "direction_only_not_source_truth",
            "when": "Inspect one known note id with the weak-memory boundary visible.",
        },
    ]
    primary = choices[0]
    return {
        "kind": "aippocampus_agent_self_note_recovery",
        "ok": False,
        "error": {
            "code": "self_note_command_required",
            "message": "self-note defaults to read-only list/search; append only after an explicit write request.",
        },
        "choices": choices,
        **canonical_foreground_action_fields(primary, safe_next_actions=choices),
        "source_boundary": {
            "authority": "direction_only",
            "direction_only_is_not_source_truth": True,
            "source_reopen_required_before_claim": True,
        },
        "write_boundary": _write_boundary(),
        "privacy_boundary": _privacy_boundary(),
    }


def _print_self_note_recovery_card(payload: Mapping[str, Any]) -> None:
    print("AIppocampus self-note")
    print("decision: choose append, search, list, or read")
    print("boundary: direction_only notes are weak scent, not source truth")
    print("")
    print("Choices:")
    for choice in payload.get("choices") or []:
        if not isinstance(choice, Mapping):
            continue
        command = choice.get("command") or choice.get("command_template")
        print(f"  {choice.get('label')}: {command}")
    print("")
    print("Use source-backed memory instead:")
    print('  aippocampus agent recall "old decision or handoff cue" --json')
    print('  aippocampus search "exact phrase" --json')


def _scope_card(args: argparse.Namespace) -> dict[str, Any]:
    if args.registry_wide:
        return {
            "mode": "registry_wide",
            "why": "Explicit operator read across all agent self-notes.",
            "project_scope_id": None,
        }
    if args.notes_path:
        return {
            "mode": "explicit_notes_path",
            "why": "The caller supplied a notes file, so the file itself is the read scope.",
            "project_scope_id": None,
        }
    scope_id = project_scope_id(args.cwd)
    return {
        "mode": "current_workspace",
        "why": "Default list/search stays scoped so an unrelated cwd does not dump registry-wide notes.",
        "project_scope_id": scope_id,
    }


def _apply_read_scope(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    scope = _scope_card(args)
    if scope["mode"] in {"registry_wide", "explicit_notes_path"}:
        return rows
    scope_id = str(scope.get("project_scope_id") or "")
    return [row for row in rows if str(row.get("project_scope_id") or "") == scope_id]


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
    return build_append_error_payload(
        code,
        privacy_boundary=_privacy_boundary(),
        details=details,
    )


def _append_receipt_boundary(row: Mapping[str, Any]) -> dict[str, Any]:
    source_ref_count = int(row.get("source_ref_count") or 0)
    return {
        "authority": str(row.get("authority") or "direction_only"),
        "support_level": str(row.get("support_level") or "scent"),
        "truth_boundary": str(row.get("truth_boundary") or "agent_self_note_not_source_fact"),
        "source_boundary": {
            "self_note_is_not_source_fact": True,
            "source_refs_are_reopen_routes_not_proof_of_note": True,
            "source_reopen_required_before_claim": True,
            "source_ref_count": source_ref_count,
            "source_less_direction_only": source_ref_count == 0,
        },
        "agent_next_action": (
            "A source route was attached; reopen it before any factual claim."
            if source_ref_count
            else (
                "This is source-less scent. Use --current-thread or --source-ref-json when a "
                "reopenable route exists; use search/agent recall for source-backed facts."
            )
        ),
    }


def _read_not_found_payload(note_id: str) -> dict[str, Any]:
    actions = _self_note_lookup_actions()
    return {
        "kind": "aippocampus_agent_self_note_read",
        "ok": False,
        "error": {
            "code": "agent_self_note_not_found",
            "message": "No scoped agent self-note matched that note_id.",
            "note_id": note_id,
        },
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "privacy_boundary": _privacy_boundary(),
    }


def _read_missing_id_payload() -> dict[str, Any]:
    actions = _self_note_lookup_actions()
    return {
        "kind": "aippocampus_agent_self_note_read",
        "ok": False,
        "error": {
            "code": "needs_note_id",
            "message": "self-note read needs a note_id.",
        },
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "write_boundary": _write_boundary(),
        "privacy_boundary": _privacy_boundary(),
    }


def _read_success_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    action = {
        "id": "use_direction_only_note",
        "label": "Use direction-only note carefully",
        "why": "A self-note can orient attention but is not source evidence.",
        "mutation_risk": "read_only",
        "claim_boundary": "direction_only_not_source_truth",
        "continue_without_command": True,
    }
    return {
        "kind": "aippocampus_agent_self_note_read",
        "ok": True,
        "note": public_agent_self_note_surface(row),
        **canonical_foreground_action_fields(
            action,
            safe_next_actions=[action, *_self_note_lookup_actions()],
        ),
        "source_boundary": {
            "self_note_is_not_source_fact": True,
            "source_reopen_required_before_claim": True,
        },
        "privacy_boundary": _privacy_boundary(),
    }


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
        **_append_receipt_boundary(row),
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
        "read": "example: aippocampus self-note read <note_id> --json",
    }
    boundary_epilog = f"""{examples[command]}

When to use:
  short voluntary foreground-agent margin notes after an explicit decision
  handoff atmosphere or posture that should stay weak/direction-only

When not to use:
  facts, user profile claims, durable lessons, or source replacement
  repeated engineering lessons that belong in source-backed learning / AIppo / continuity domains

Prefer --current-thread or --source-ref-json when a reopenable source route exists."""
    parser = argparse.ArgumentParser(
        prog=f"aippocampus self-note {command}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "direction-only self-notes: do not use them as source-backed facts. "
            "Use them for agent posture, "
            "handoff atmosphere, or decision breadcrumbs; never treat them as "
            "user profile claims or a shortcut around reopening source."
        ),
        epilog=boundary_epilog,
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
    parser.add_argument(
        "--registry-wide",
        "--all-threads",
        action="store_true",
        dest="registry_wide",
        help="Operator read across all self-notes; default list/search is current-workspace scoped.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.print_help()


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] in {"append", "search", "list", "read"} and any(
        item in {"-h", "--help"} for item in raw_args[1:]
    ):
        _print_command_help(raw_args[0])
        return 0
    if not raw_args or raw_args == ["--json"]:
        payload = _self_note_recovery_payload()
        if "--json" in raw_args:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        else:
            _print_self_note_recovery_card(payload)
        return 0

    parser = argparse.ArgumentParser(
        prog="aippocampus self-note",
        usage="aippocampus self-note {append,search,list,read} [text] [--json]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Weak-memory decision card.

Self-notes are `direction_only` foreground-agent margin notes: useful for a
short posture handoff, a decision breadcrumb, or a reminder to reopen a source.
They are weak scent, not clean source, user-profile memory, source-backed
lessons, AIppo clauses, or continuity-domain events.

Use:
  append  write a short low-authority note after an explicit decision
  search  find note atmosphere for the current workspace/thread scope
  list    review recent scoped notes without treating them as evidence
  read    inspect one note by id with the direction-only boundary first

Do not use self-notes for factual claims. For source-backed continuity, run
`aippocampus search`, `aippocampus agent recall`, or reopen the cited source
before quoting or deciding from memory.""",
    )
    parser.add_argument("command", choices=["append", "search", "list", "read"])
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
    parser.add_argument(
        "--registry-wide",
        "--all-threads",
        action="store_true",
        dest="registry_wide",
        help="Operator read across all self-notes; default list/search is current-workspace scoped.",
    )
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
    scope = _scope_card(args)
    all_rows = load_agent_self_notes(notes_path)
    scoped_rows = _apply_read_scope(all_rows, args)
    if args.command == "read":
        note_id = text
        if not note_id:
            payload = _read_missing_id_payload()
            if args.json_output:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("self-note read needs a note_id", file=sys.stderr)
                formatted = format_action_for_human(payload.get("agent_next_action"))
                print("Next: " + (formatted[0] if formatted else ""), file=sys.stderr)
            return 2
        row = next(
            (
                item
                for item in scoped_rows
                if str(item.get("note_id") or "") == note_id
            ),
            None,
        )
        payload = _read_success_payload(row) if row is not None else _read_not_found_payload(note_id)
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif row is not None:
            note = payload["note"]
            print("agent self-note: " + str(note.get("note_id") or ""))
            print("authority: direction_only; reopen source before factual claims")
            print("note: " + str(note.get("note_text") or ""))
            print("next: " + str(payload.get("agent_next_action") or ""))
        else:
            print("self-note not found", file=sys.stderr)
            formatted = format_action_for_human(payload.get("agent_next_action"))
            print("Next: " + (formatted[0] if formatted else ""), file=sys.stderr)
        return 0 if row is not None else 1
    if args.command == "search":
        if not text:
            actions = _self_note_lookup_actions()
            payload = {
                "kind": "aippocampus_agent_self_note_search_recovery",
                "ok": False,
                "status": "needs_cue",
                "error": {
                    "code": "needs_cue",
                    "message": "self-note search needs a cue.",
                },
                **canonical_foreground_action_fields(actions[1], safe_next_actions=actions),
                "write_boundary": _write_boundary(),
                "privacy_boundary": _privacy_boundary(),
            }
            if args.json_output:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("self-note search needs a cue", file=sys.stderr)
                print("Next: " + str(actions[1]["command_template"]), file=sys.stderr)
            return 2
        rows = search_agent_self_notes(text, scoped_rows, limit=args.max)
        actions = _self_note_lookup_actions()
        payload = {
            "kind": "aippocampus_agent_self_note_search",
            "query": text,
            "count": len(rows),
            "scope": scope,
            "rows": [public_agent_self_note_surface(row) for row in rows],
            **canonical_foreground_action_fields(actions[1], safe_next_actions=actions),
        }
        if not rows:
            payload["empty_state"] = _empty_notes_state("search", text)
    else:
        rows = scoped_rows[: max(0, int(args.max or 0))]
        actions = _self_note_lookup_actions()
        payload = {
            "kind": "aippocampus_agent_self_notes",
            "scope": scope,
            "count": len(rows),
            "rows": [public_agent_self_note_surface(row) for row in rows],
            **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        }
        if not rows:
            payload["empty_state"] = _empty_notes_state("list")

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        payload_rows = payload.get("rows")
        if isinstance(payload_rows, list):
            scope_payload = payload.get("scope")
            scope_mode = (
                scope_payload.get("mode") if isinstance(scope_payload, Mapping) else "unknown"
            )
            print("agent self-notes: direction_only atmosphere; reopen source before factual claims")
            print("scope: " + str(scope_mode or "unknown"))
            for payload_row in payload_rows:
                if isinstance(payload_row, dict):
                    route_count = len(payload_row.get("source_refs") or [])
                    print(f"- {payload_row.get('created_at')} {payload_row.get('note_text')}")
                    print(
                        "  boundary: direction_only; "
                        f"{route_count} reopen route(s) available"
                    )
        empty_state = payload.get("empty_state")
        if not payload_rows and isinstance(empty_state, dict):
            print(str(empty_state.get("message") or ""))
            formatted = format_action_for_human(empty_state.get("agent_next_action"))
            print("Next: " + (formatted[0] if formatted else ""))
    return 0


def _run_append(args: argparse.Namespace, *, text: str, notes_path: Path) -> int:
    if not text:
        payload = _append_error_payload("agent_self_note_empty")
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("self-note append needs a short note.", file=sys.stderr)
            formatted = format_action_for_human(payload.get("agent_next_action"))
            if formatted:
                print("Next: " + formatted[0], file=sys.stderr)
                for line in formatted[1:]:
                    print(line, file=sys.stderr)
        return 2
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
            **_append_receipt_boundary(row),
            "privacy_boundary": _privacy_boundary(),
        }
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        payload_row = payload.get("row") or payload.get("note")
        note_id = payload_row.get("note_id") if isinstance(payload_row, dict) else ""
        source_ref_count = (
            int(payload_row.get("source_ref_count") or 0)
            if isinstance(payload_row, dict)
            else 0
        )
        print(f"agent self-note: {note_id}")
        print("authority: direction_only; reopen source before factual claims")
        print(
            f"source refs: {source_ref_count} attached; "
            + ("reopen route available" if source_ref_count else "not source-backed")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
