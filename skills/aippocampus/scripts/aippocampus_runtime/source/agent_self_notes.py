#!/usr/bin/env python3
"""Low-authority foreground-agent margin notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_text
from aippocampus_runtime.recall.authority import with_trust_fields
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import registry_paths, unique_preserve

AGENT_SELF_NOTE_SCHEMA_VERSION = 1
AGENT_SELF_NOTE_KIND = "agent_self_note"
AGENT_SELF_NOTES_FILE = "agent-self-notes.jsonl"
AGENT_SELF_NOTE_MAX_CHARS = 280
AGENT_SELF_NOTE_BOUNDARY = "agent_self_note_not_source_fact"

VALID_TRIGGERS = {"thread_end", "explicit_agent_reflection", "closeout"}
STATE_RECALL_TERMS = {
    "agent",
    "activation",
    "atmosphere",
    "foreground",
    "margin",
    "posture",
    "self",
    "self-note",
    "stance",
    "state",
    "thread shape",
    "找回状态",
    "前的状态",
    "上次状态",
    "姿态",
    "氛围",
    "自注",
    "边注",
}
RAW_PAYLOAD_RE = re.compile(
    r"(?i)\b(tool_use|tool_result|stdout|stderr|traceback|raw payload|"
    r"function_call|arguments_json|stack trace)\b"
)
SAFE_SOURCE_REF_FIELDS = (
    "thread_key",
    "source_id",
    "source_ref",
    "message_id",
    "turn_id",
    "turn_index",
    "line",
    "source_line",
    "raw_start_line",
    "raw_end_line",
    "phase",
    "title",
)


class AgentSelfNoteRejected(ValueError):
    """The requested self-note would serialize unsafe or empty material."""


def default_agent_self_notes_path(
    registry_path: Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / AGENT_SELF_NOTES_FILE
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / AGENT_SELF_NOTES_FILE


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_agent_self_notes(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_agent_self_notes(path: Path) -> list[dict[str, Any]]:
    return [row for row in _load_jsonl(path) if row.get("kind") == AGENT_SELF_NOTE_KIND]


def _clean_source_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in SAFE_SOURCE_REF_FIELDS:
        value = ref.get(key)
        if value in (None, "", []):
            continue
        clean["line" if key == "source_line" else key] = value
    return clean


def _clean_source_refs(refs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for ref in refs:
        clean = _clean_source_ref(ref)
        if not clean:
            continue
        marker = tuple(sorted((key, str(value)) for key, value in clean.items()))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(clean)
        if len(out) >= 4:
            break
    return out


def sanitize_agent_self_note_text(
    note_text: str,
    *,
    project_root: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    text = compact_text(str(note_text or "").strip(), AGENT_SELF_NOTE_MAX_CHARS)
    if not text:
        raise AgentSelfNoteRejected("agent_self_note_empty")
    if RAW_PAYLOAD_RE.search(text):
        raise AgentSelfNoteRejected("agent_self_note_raw_payload_rejected")
    sanitized, policy = sanitize_external_model_text(text, project_root=project_root)
    sanitized = compact_text(sanitized.strip(), AGENT_SELF_NOTE_MAX_CHARS)
    if policy.get("hard_block") or not sanitized:
        raise AgentSelfNoteRejected("agent_self_note_sensitive_material_rejected")
    return sanitized, policy


def build_agent_self_note_row(
    *,
    note_text: str,
    thread_key: str,
    source_refs: Iterable[Mapping[str, Any]],
    trigger: str = "explicit_agent_reflection",
    created_at: str | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    clean_trigger = trigger if trigger in VALID_TRIGGERS else "explicit_agent_reflection"
    cleaned_refs = _clean_source_refs(source_refs)
    sanitized_text, redaction_policy = sanitize_agent_self_note_text(
        note_text,
        project_root=project_root,
    )
    timestamp = created_at or now_utc()
    note_id = _stable_id("asn", thread_key, timestamp, sanitized_text, cleaned_refs)
    # Source refs are a route back to the surrounding source neighborhood, not
    # proof of the note's wording or any claim made by the foreground agent.
    row: dict[str, Any] = {
        "kind": AGENT_SELF_NOTE_KIND,
        "schema_version": AGENT_SELF_NOTE_SCHEMA_VERSION,
        "note_id": note_id,
        "created_at": timestamp,
        "thread_key": compact_text(str(thread_key or "unknown-thread"), 160),
        "source_refs": cleaned_refs,
        "source_ref_count": len(cleaned_refs),
        "note_text": sanitized_text,
        "author_role": "foreground_agent",
        "trigger": clean_trigger,
        "authority": "direction_only",
        "support_level": "scent",
        "memory_surface": "memory_atmosphere",
        "use_boundary": "atmosphere_only",
        "truth_boundary": AGENT_SELF_NOTE_BOUNDARY,
        "privacy_profile": "raw-private",
        "claims_user_fact": False,
        "claims_world_fact": False,
        "claims_source_fact": False,
        "source_reopen_required_before_claim": True,
        "clean_source_mutation_allowed": False,
        "formal_memory_eligible": False,
        "foreground_default_visible": False,
        "external_model_calls": False,
        "raw_tool_payload_serialized": False,
        "redaction_policy": {
            "redacted": bool(redaction_policy.get("redacted")),
            "redaction_count": int(redaction_policy.get("redaction_count") or 0),
            "redaction_types": list(redaction_policy.get("redaction_types") or [])[:8],
        },
    }
    return with_trust_fields(row)


def append_agent_self_note(
    path: Path,
    *,
    note_text: str,
    thread_key: str,
    source_refs: Iterable[Mapping[str, Any]],
    trigger: str = "explicit_agent_reflection",
    created_at: str | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    rows = load_agent_self_notes(path)
    row = build_agent_self_note_row(
        note_text=note_text,
        thread_key=thread_key,
        source_refs=source_refs,
        trigger=trigger,
        created_at=created_at,
        project_root=project_root,
    )
    rows.append(row)
    write_agent_self_notes(path, rows)
    return row


def _row_search_text(row: Mapping[str, Any]) -> str:
    ref_text = " ".join(
        str(ref.get("title") or ref.get("thread_key") or ref.get("source_ref") or "")
        for ref in row.get("source_refs") or []
        if isinstance(ref, Mapping)
    )
    return " ".join(
        str(value or "")
        for value in (
            row.get("note_text"),
            row.get("thread_key"),
            row.get("trigger"),
            ref_text,
        )
    )


def _state_recall_requested(prompt: str) -> bool:
    low = str(prompt or "").casefold()
    return any(term.casefold() in low for term in STATE_RECALL_TERMS)


def search_agent_self_notes(
    prompt: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    terms = [
        term.casefold()
        for term in split_query_terms([prompt])
        if len(term.strip()) >= 2
    ]
    state_requested = _state_recall_requested(prompt)
    scored: list[tuple[tuple[int, str], dict[str, Any]]] = []
    for row in rows:
        if row.get("kind") != AGENT_SELF_NOTE_KIND:
            continue
        text = _row_search_text(row).casefold()
        matched = unique_preserve([term for term in terms if term in text], limit=8)
        if not matched and not state_requested:
            continue
        copy = with_trust_fields(dict(row))
        copy["matched_terms"] = matched
        copy["active_recall_surface"] = "agent_self_note"
        copy["retrieval_role"] = "memory_atmosphere"
        copy["source_boundary"] = {
            "self_note_is_not_source_fact": True,
            "source_refs_are_reopen_routes_not_proof_of_note": True,
            "source_reopen_required_before_claim": True,
        }
        score = len(matched) * 2 + (1 if state_requested else 0)
        scored.append(((score, str(copy.get("created_at") or "")), copy))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[: max(0, int(limit or 0))]]


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["append", "search", "list"])
    parser.add_argument("text", nargs="*", help="Note text for append or query text for search.")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--notes-path")
    parser.add_argument("--thread-key", default="unknown-thread")
    parser.add_argument("--trigger", default="explicit_agent_reflection", choices=sorted(VALID_TRIGGERS))
    parser.add_argument("--source-ref-json", action="append")
    parser.add_argument("--max", type=int, default=4)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    registry_path = _registry_path_from_args(args)
    notes_path = _notes_path_from_args(args, registry_path)
    text_parts = list(args.text or [])
    if args.stdin:
        text_parts.append(sys.stdin.read())
    text = " ".join(text_parts).strip()

    payload: dict[str, Any]
    if args.command == "append":
        if not text:
            raise SystemExit("agent_self_notes append requires note text or --stdin")
        row = append_agent_self_note(
            notes_path,
            note_text=text,
            thread_key=args.thread_key,
            source_refs=_parse_source_ref_json(args.source_ref_json),
            trigger=args.trigger,
            project_root=Path(args.cwd).resolve(),
        )
        payload = {"ok": True, "row": row}
    elif args.command == "search":
        rows = search_agent_self_notes(text, load_agent_self_notes(notes_path), limit=args.max)
        payload = {
            "kind": "aippocampus_agent_self_note_search",
            "query": text,
            "count": len(rows),
            "rows": rows,
        }
    else:
        rows = load_agent_self_notes(notes_path)[: max(0, int(args.max or 0))]
        payload = {"kind": "aippocampus_agent_self_notes", "rows": rows}

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.command == "append":
            payload_row = payload.get("row")
            note_id = payload_row.get("note_id") if isinstance(payload_row, dict) else ""
            print(f"agent self-note: {note_id}")
        else:
            payload_rows = payload.get("rows")
            if isinstance(payload_rows, list):
                for payload_row in payload_rows:
                    if isinstance(payload_row, dict):
                        print(f"- {payload_row.get('created_at')} {payload_row.get('note_text')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AGENT_SELF_NOTE_BOUNDARY",
    "AGENT_SELF_NOTE_KIND",
    "AGENT_SELF_NOTE_MAX_CHARS",
    "AGENT_SELF_NOTES_FILE",
    "AgentSelfNoteRejected",
    "append_agent_self_note",
    "build_agent_self_note_row",
    "default_agent_self_notes_path",
    "load_agent_self_notes",
    "sanitize_agent_self_note_text",
    "search_agent_self_notes",
    "write_agent_self_notes",
]
