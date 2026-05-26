#!/usr/bin/env python3
"""Build an AIppocampus clean-source corpus from a Codex rollout.

Clean source is original visible conversation text, not a summary. It removes
raw rollout envelopes, tool payloads, injected workspace instructions, and
routine commentary when a turn has a final answer. Raw rollout remains the
audit source, but day-to-day recall can use this smaller source-backed corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from aippocampuslib import (
    codex_home,
    default_thread_clean_source_dir,
    file_sha256,
    locate_rollout,
    normalize_rollout,
    now_utc,
    public_session_meta,
    read_session_meta,
    resolve_artifact_path,
)


LEGACY_OUTPUT_DIR = ".aippocampus/clean-source"
CLEAN_SOURCE_SCHEMA_VERSION = 2
SIGNATURE_CONTRACT_VERSION = "aippocampus-signature-sidecar-v1"


def _stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    material = "\0".join(str(part or "") for part in parts)
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _semantic_key(role: str, phase: str, text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return _stable_id("sem", role, phase, normalized, length=20)


def _clean_messages(messages: list[dict], turns: list[dict], source_id: str) -> tuple[list[dict], list[dict]]:
    by_turn: dict[int, list[dict]] = {}
    for message in messages:
        turn_index = message.get("turn_index")
        if isinstance(turn_index, int):
            by_turn.setdefault(turn_index, []).append(message)

    clean_messages: list[dict] = []
    clean_turns: list[dict] = []

    for turn in turns:
        turn_id = int(turn["id"])
        items = by_turn.get(turn_id, [])
        user = next((item for item in items if item.get("role") == "user"), None)
        final = next((item for item in items if item.get("is_final")), None)
        assistant = final
        assistant_phase = "final_answer"
        if assistant is None:
            fallback_line = turn.get("fallback_assistant_line")
            assistant = next((item for item in items if item.get("line") == fallback_line), None)
            assistant_phase = "commentary_fallback" if assistant else ""

        turn_uid = _stable_id("turn", source_id, turn_id, turn.get("user_line"), turn.get("start_line"), length=20)
        kept: list[dict] = []
        for item in (user, assistant):
            if not item:
                continue
            phase = item.get("phase") or ""
            text = item.get("text") or ""
            content_sha256 = _content_sha256(text)
            message_id = _stable_id(
                "msg",
                source_id,
                item.get("line"),
                item.get("role"),
                phase,
                content_sha256,
                length=20,
            )
            kept_item = {
                "id": message_id,
                "message_id": message_id,
                "turn_id": turn_uid,
                "source_id": source_id,
                "source_line": item.get("line"),
                "raw_start_line": item.get("line"),
                "raw_end_line": item.get("line"),
                "timestamp": item.get("timestamp"),
                "role": item.get("role"),
                "kind": item.get("kind"),
                "phase": phase,
                "turn_index": turn_id,
                "is_final": bool(item.get("is_final")),
                "text_sha1": item.get("sha1"),
                "content_sha256": content_sha256,
                "semantic_key": _semantic_key(str(item.get("role") or ""), phase, text),
                "signature_key": message_id,
                "text": text,
            }
            kept.append(kept_item)
            clean_messages.append(kept_item)

        user_message = next((item for item in kept if item.get("role") == "user"), None)
        assistant_message = next((item for item in kept if item.get("role") == "assistant"), None)
        clean_ordinals = [len(clean_messages) - len(kept) + idx for idx in range(len(kept))]
        clean_turns.append(
            {
                "turn_id": turn_uid,
                "source_id": source_id,
                "turn_index": turn_id,
                "user_line": user.get("line") if user else None,
                "assistant_line": assistant.get("line") if assistant else None,
                "user_message_id": user_message.get("message_id") if user_message else None,
                "assistant_message_id": assistant_message.get("message_id") if assistant_message else None,
                "message_ids": [item["message_id"] for item in kept],
                "assistant_phase": assistant_phase,
                "start_line": turn.get("start_line"),
                "end_line": turn.get("end_line"),
                "raw_start_line": turn.get("start_line"),
                "raw_end_line": turn.get("end_line"),
                "clean_start_ordinal": clean_ordinals[0] if clean_ordinals else None,
                "clean_end_ordinal": clean_ordinals[-1] if clean_ordinals else None,
                "message_count": len(kept),
            }
        )

    return clean_messages, clean_turns


def build_clean_source(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    output_dir: str | Path | None = None,
    hash_source: bool = False,
) -> dict:
    cwd = Path(cwd).resolve()
    rollout_path = Path(rollout) if rollout else locate_rollout(cwd, codex_home())
    if not rollout_path.is_absolute():
        rollout_path = cwd / rollout_path

    out = resolve_artifact_path(output_dir, cwd, default_thread_clean_source_dir(cwd, rollout_path))
    out.mkdir(parents=True, exist_ok=True)

    raw_meta = read_session_meta(rollout_path) or {}
    meta = public_session_meta(raw_meta)
    messages, turns = normalize_rollout(rollout_path, include_tools=False)

    source_key = meta.get("id") or str(rollout_path.resolve())
    source_id = _stable_id("src", source_key, length=20)
    clean_messages, clean_turns = _clean_messages(messages, turns, source_id)
    for ordinal, item in enumerate(clean_messages):
        item["clean_ordinal"] = ordinal
        item["source_session_id"] = meta.get("id")

    messages_path = out / "messages.jsonl"
    with messages_path.open("w", encoding="utf-8", newline="\n") as f:
        for item in clean_messages:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    turns_path = out / "turns.jsonl"
    with turns_path.open("w", encoding="utf-8", newline="\n") as f:
        for item in clean_turns:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    stat = rollout_path.stat()
    manifest = {
        "schema_version": CLEAN_SOURCE_SCHEMA_VERSION,
        "kind": "aippocampus_clean_source",
        "created_at": now_utc(),
        "cwd": str(cwd),
        "artifact_scope": "global_thread_store" if output_dir is None else "explicit_output_dir",
        "storage_policy": {
            "default": "CODEX_HOME/aippocampus-registry/threads/<thread>/clean-source",
            "legacy_project_local": LEGACY_OUTPUT_DIR,
            "why": "Clean source is private cross-project memory; project-local output is explicit compatibility, not the default.",
        },
        "source_id": source_id,
        "source_rollout": str(rollout_path),
        "source_rollout_size": stat.st_size,
        "source_rollout_mtime": stat.st_mtime,
        "source_rollout_sha256": file_sha256(rollout_path) if hash_source else None,
        "session_meta": meta,
        "message_count": len(clean_messages),
        "turn_count": len(clean_turns),
        "outputs": {
            "messages_jsonl": str(messages_path),
            "turns_jsonl": str(turns_path),
        },
        "identity_policy": {
            "stable_join_keys": ["source_id", "turn_id", "message_id", "content_sha256"],
            "message_id": "Stable over rebuilds for the same source, raw line, role, phase, and exact text.",
            "turn_id": "Stable over rebuilds for the same source and inferred user turn boundary.",
            "semantic_key": "Deterministic normalized-text key for lightweight sidecars; it is not a semantic embedding.",
            "source_id": "Opaque hash of the session id when available, otherwise the resolved rollout path.",
        },
        "upgrade_contract": {
            "principle": "approximate_locate_then_exact_reconstruct",
            "signature_sidecar": {
                "version": SIGNATURE_CONTRACT_VERSION,
                "status": "reserved",
                "default_dir": "signature-sidecar",
                "join_key": "message_id",
                "source_fields": ["semantic_key", "content_sha256", "text"],
                "expected_outputs": ["manifest.json", "signatures.jsonl"],
            },
            "compressed_content_store": {
                "status": "reserved",
                "join_key": "message_id",
                "source_fields": ["raw_start_line", "raw_end_line", "content_sha256"],
            },
        },
        "cleaning_policy": {
            "keeps": ["user_message", "assistant final_answer", "last assistant commentary only when no final_answer exists"],
            "drops": ["tool payload text", "duplicate visible messages", "injected AGENTS instructions", "routine commentary when final_answer exists"],
            "rewrites_text": False,
        },
    }
    manifest_path = out / "manifest.json"
    manifest["outputs"]["manifest_json"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the CODEX_HOME global thread store; pass .aippocampus/clean-source for project-local output.",
    )
    parser.add_argument("--hash-source", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    manifest = build_clean_source(
        args.cwd,
        rollout=args.rollout,
        output_dir=args.output_dir,
        hash_source=args.hash_source,
    )
    if args.json_output:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"clean source: {manifest['outputs']['manifest_json']}")
        print(f"messages: {manifest['outputs']['messages_jsonl']} ({manifest['message_count']} messages)")
        print(f"turns: {manifest['outputs']['turns_jsonl']} ({manifest['turn_count']} turns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
