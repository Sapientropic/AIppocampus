#!/usr/bin/env python3
"""Build an AIppocampus clean-source corpus from a host transcript source.

Clean source is original visible conversation text, not a summary. It removes
raw host envelopes, tool payloads, injected workspace instructions, and routine
commentary when a turn has a final answer. Raw host transcripts remain the audit
source, but day-to-day recall can use this smaller source-backed corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from aippocampuslib import (
    codex_home,
    default_thread_clean_source_dir,
    file_sha256,
    locate_rollout,
    now_utc,
    resolve_artifact_path,
)
from conversation_sources import ConversationProvider, create_conversation_provider
from conversation_sources.normalized import stable_source_ref
from rollout_behavior_events import extract_rollout_behavior_events

LEGACY_OUTPUT_DIR = ".aippocampus/clean-source"
CLEAN_SOURCE_SCHEMA_VERSION = 2
SIGNATURE_CONTRACT_VERSION = "aippocampus-signature-sidecar-v1"
SCOPE_LABEL_POLICY_VERSION = "aippocampus-scope-labels-v1"

SCOPE_LABEL_ORDER = (
    "personal_reflection",
    "relationship_continuity",
    "reading_notes",
    "idea_seed",
    "preference",
    "life_context",
    "technical_work",
    "open_question",
)

# Keep this list for explicit, low-risk lexical cues only. Fuzzy judgments such
# as "this metaphor feels pivotal" or "this dissatisfaction matters" belong in
# the DeepSeek/subconscious `semantic_scope_labeling` sidecar, not here; otherwise
# the deterministic layer slowly turns into an unreviewable phrase list.
SCOPE_LABEL_RULES: dict[str, tuple[str, ...]] = {
    "personal_reflection": (
        "我在想",
        "我觉得",
        "我感觉",
        "我意识到",
        "我总是",
        "焦虑",
        "困惑",
        "害怕",
        "怀疑",
        "reflection",
        "reflecting",
        "anxiety",
        "doubt",
    ),
    "relationship_continuity": (
        "上次",
        "之前聊",
        "继续",
        "长期陪伴",
        "长期连续",
        "长期关系",
        "记得",
        "旧线程",
        "old thread",
        "continuity",
        "relationship",
        "catch up",
        "continue",
    ),
    "reading_notes": (
        "读到",
        "读了",
        "文章",
        "论文",
        "书里",
        "摘录",
        "reading",
        "read this",
        "article",
        "paper",
        "quote",
    ),
    "idea_seed": (
        "点子",
        "想法",
        "灵感",
        "可以做",
        "脑洞",
        "idea",
        "seed",
        "spark",
        "sparks",
        "prototype",
    ),
    "preference": (
        "偏好",
        "我喜欢",
        "我不喜欢",
        "更喜欢",
        "不要",
        "希望你",
        "默认",
        "prefer",
        "preference",
    ),
    "life_context": (
        "最近",
        "今天",
        "昨天",
        "生活",
        "家里",
        "睡眠",
        "身体",
        "长期问题",
        "adhd",
        "lately",
        "today",
        "yesterday",
        "life",
        "sleep",
    ),
    "technical_work": (
        "aippocampus",
        "clean source",
        "mcp",
        "plugin",
        "codex",
        "typescript",
        "rust",
        "python",
        "repo",
        "repository",
        "cli",
        "api",
        "roadmap",
        "代码",
        "测试",
        "脚本",
        "仓库",
        "插件",
        "文档",
    ),
}

ASCII_NEEDLE_RE = re.compile(r"^[a-z0-9_+-]+$")


def _stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    material = "\0".join(str(part or "") for part in parts)
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _semantic_key(role: str, phase: str, text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return _stable_id("sem", role, phase, normalized, length=20)


def _scope_needle_matches(lowered_text: str, needle: str) -> bool:
    lowered_needle = needle.casefold()
    if ASCII_NEEDLE_RE.match(lowered_needle):
        return (
            re.search(rf"(?<![a-z0-9_+-]){re.escape(lowered_needle)}(?![a-z0-9_+-])", lowered_text)
            is not None
        )
    return lowered_needle in lowered_text


def _looks_like_open_question(text: str) -> bool:
    stripped = str(text or "").strip()
    if stripped.endswith(("?", "？")):
        return True
    return (
        re.match(
            r"^(why|how|what|when|where|who|which|can i|could i|should i|do i|does|is|are|am)\b",
            stripped.casefold(),
        )
        is not None
    )


def infer_scope_labels(text: str) -> list[str]:
    """Return conservative life-wide navigation labels for visible text.

    These labels are deterministic hints for filtering and timeline sidecars,
    not model claims about the user's interior state. Keep the rules explicit
    and source-backed so future semantic classifiers can be compared against
    the same clean text instead of replacing it.
    """

    lowered = str(text or "").casefold()
    labels: list[str] = []
    for label in SCOPE_LABEL_ORDER:
        if label == "open_question":
            if _looks_like_open_question(text):
                labels.append(label)
            continue
        needles = SCOPE_LABEL_RULES.get(label, ())
        if any(_scope_needle_matches(lowered, needle) for needle in needles):
            labels.append(label)
    return labels


def _merge_scope_labels(items: list[dict]) -> list[str]:
    present = {
        label
        for item in items
        for label in item.get("scope_labels", [])
        if label in SCOPE_LABEL_ORDER
    }
    return [label for label in SCOPE_LABEL_ORDER if label in present]


def _clean_behavior_events(
    events: list[dict[str, Any]],
    *,
    source_id: str,
    source_provider: str,
    session_id: str | None,
) -> list[dict[str, Any]]:
    clean_events: list[dict[str, Any]] = []
    for event in events:
        line_no = event.get("line")
        event_kind = str(event.get("event_kind") or "")
        hard_event_kind = str(event.get("hard_event_kind") or event_kind)
        event_id = _stable_id(
            "evt",
            source_id,
            line_no,
            event_kind,
            event.get("call_ref"),
            event.get("observation_sha256") or event.get("input_sha256"),
            length=20,
        )
        status = str(event.get("status") or "observed")
        command_class = str(event.get("command_class") or "tool")
        tool_name = str(event.get("tool_name") or "tool")
        text = f"{tool_name} {status}; command_class={command_class}; event={hard_event_kind}"
        if event.get("exit_code") is not None:
            text += f"; exit_code={event.get('exit_code')}"
        row = {
            "id": event_id,
            "event_id": event_id,
            "source_id": source_id,
            "source_ref": stable_source_ref(source_provider, session_id, int(line_no))
            if isinstance(line_no, int)
            else None,
            "source_line": line_no,
            "raw_start_line": line_no,
            "raw_end_line": line_no,
            "timestamp": event.get("timestamp"),
            "turn_index": event.get("turn_index"),
            "event_kind": event_kind,
            "hard_event_kind": hard_event_kind,
            "tool_payload_kind": event.get("tool_payload_kind"),
            "tool_name": tool_name,
            "call_ref": event.get("call_ref"),
            "command_class": command_class,
            "exit_code": event.get("exit_code"),
            "status": status,
            "behavior_backed": bool(event.get("behavior_backed")),
            "input_sha256": event.get("input_sha256"),
            "observation_sha256": event.get("observation_sha256"),
            "input_field_names": event.get("input_field_names") or [],
            "text": text,
        }
        clean_events.append(
            {key: value for key, value in row.items() if value not in (None, "", [])}
        )
    return clean_events


def _clean_messages(
    messages: list[dict], turns: list[dict], source_id: str
) -> tuple[list[dict], list[dict]]:
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

        turn_uid = _stable_id(
            "turn", source_id, turn_id, turn.get("user_line"), turn.get("start_line"), length=20
        )
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
                "source_ref": item.get("source_ref"),
                "source_line": item.get("line"),
                "raw_start_line": item.get("raw_start_line") or item.get("line"),
                "raw_end_line": item.get("raw_end_line") or item.get("line"),
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
                "scope_labels": infer_scope_labels(text),
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
                "assistant_message_id": assistant_message.get("message_id")
                if assistant_message
                else None,
                "message_ids": [item["message_id"] for item in kept],
                "assistant_phase": assistant_phase,
                "start_line": turn.get("start_line"),
                "end_line": turn.get("end_line"),
                "raw_start_line": turn.get("start_line"),
                "raw_end_line": turn.get("end_line"),
                "clean_start_ordinal": clean_ordinals[0] if clean_ordinals else None,
                "clean_end_ordinal": clean_ordinals[-1] if clean_ordinals else None,
                "message_count": len(kept),
                "scope_labels": _merge_scope_labels(kept),
            }
        )

    return clean_messages, clean_turns


def build_clean_source(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    output_dir: str | Path | None = None,
    hash_source: bool = False,
    provider_name: str = "codex",
    provider: ConversationProvider | None = None,
) -> dict[str, Any]:
    cwd = Path(cwd).resolve()
    active_provider = provider or create_conversation_provider(
        provider_name,
        codex_home_dir=codex_home(),
    )
    source_path = Path(rollout) if rollout else None
    if source_path is None:
        if active_provider.name == "codex":
            source_path = locate_rollout(cwd, codex_home())
        else:
            source_path = active_provider.locate_current(cwd).path
    if not source_path.is_absolute():
        source_path = cwd / source_path

    out = resolve_artifact_path(output_dir, cwd, default_thread_clean_source_dir(cwd, source_path))
    out.mkdir(parents=True, exist_ok=True)

    meta = active_provider.read_metadata(source_path) or {}
    messages, turns = active_provider.read_normalized_messages(source_path, include_tools=False)

    source_thread_key = active_provider.thread_key(source_path, meta)
    source_key = source_thread_key or meta.get("id") or str(source_path.resolve())
    source_id = _stable_id("src", source_key, length=20)
    clean_messages, clean_turns = _clean_messages(messages, turns, source_id)
    clean_events = (
        _clean_behavior_events(
            extract_rollout_behavior_events(source_path),
            source_id=source_id,
            source_provider=active_provider.name,
            session_id=meta.get("id"),
        )
        if active_provider.name == "codex"
        else []
    )
    for ordinal, item in enumerate(clean_messages):
        item["clean_ordinal"] = ordinal
        item["source_session_id"] = meta.get("id")
    for ordinal, item in enumerate(clean_events):
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

    events_path = out / "events.jsonl"
    with events_path.open("w", encoding="utf-8", newline="\n") as f:
        for item in clean_events:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    stat = source_path.stat()
    manifest: dict[str, Any] = {
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
        "source_provider": active_provider.name,
        "source_thread_key": source_thread_key,
        "source_transcript": str(source_path),
        "source_rollout": str(source_path),
        "source_rollout_size": stat.st_size,
        "source_rollout_mtime": stat.st_mtime,
        "source_rollout_sha256": file_sha256(source_path) if hash_source else None,
        "session_meta": meta,
        "message_count": len(clean_messages),
        "turn_count": len(clean_turns),
        "event_count": len(clean_events),
        "outputs": {
            "messages_jsonl": str(messages_path),
            "turns_jsonl": str(turns_path),
            "events_jsonl": str(events_path),
        },
        "identity_policy": {
            "stable_join_keys": [
                "source_id",
                "source_ref",
                "turn_id",
                "message_id",
                "event_id",
                "content_sha256",
            ],
            "message_id": "Stable over rebuilds for the same source, raw line, role, phase, and exact text.",
            "turn_id": "Stable over rebuilds for the same source and inferred user turn boundary.",
            "source_ref": "Provider-neutral audit pointer using provider/session/line, without relying on local absolute paths as identity.",
            "semantic_key": "Deterministic normalized-text key for lightweight sidecars; it is not a semantic embedding.",
            "source_id": "Opaque hash of the provider thread key or session id when available, otherwise the resolved private source path.",
            "event_id": "Stable over rebuilds for the same source, raw line, tool event kind, call ref, and payload hash.",
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
            "keeps": [
                "user_message",
                "assistant final_answer",
                "last assistant commentary only when no final_answer exists",
                "structured tool/test behavior events in events.jsonl",
            ],
            "drops": [
                "tool payload text from messages.jsonl",
                "raw tool stdout, full command text, and full tool arguments from events.jsonl",
                "duplicate visible messages",
                "injected AGENTS instructions",
                "routine commentary when final_answer exists",
            ],
            "rewrites_text": False,
        },
        "event_lane_policy": {
            "status": "enabled_for_codex_rollouts",
            "default_file": "events.jsonl",
            "purpose": "source-backed behavior traces for tool/test failures and rollout decision shadows",
            "raw_payload_policy": "hash_only",
            "join_keys": ["source_id", "source_ref", "event_id", "turn_index", "call_ref"],
            "boundary": "events.jsonl is structured provenance; messages.jsonl remains visible conversational source.",
        },
        "scope_label_policy": {
            "version": SCOPE_LABEL_POLICY_VERSION,
            "labels": list(SCOPE_LABEL_ORDER),
            "method": "deterministic lexical hints over clean visible text",
            "boundary": "scope_labels are navigation/filtering metadata; source text remains the memory truth.",
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
        "--provider",
        default="codex",
        help="Conversation source provider: codex, claude-code, or generic-jsonl.",
    )
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
        provider_name=args.provider,
    )
    if args.json_output:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"clean source: {manifest['outputs']['manifest_json']}")
        print(
            f"messages: {manifest['outputs']['messages_jsonl']} ({manifest['message_count']} messages)"
        )
        print(f"turns: {manifest['outputs']['turns_jsonl']} ({manifest['turn_count']} turns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
