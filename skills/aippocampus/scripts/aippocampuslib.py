#!/usr/bin/env python3
"""Shared helpers for Codex Desktop thread-memory indexing scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env)
    return Path.home() / ".codex"


def safe_path_name(value: str, fallback: str = "item") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value)).strip()
    value = re.sub(r"\s+", "-", value)
    value = value.rstrip(".- ")
    return value[:120] or fallback


def aippocampus_registry_dir(home: Path | None = None) -> Path:
    env = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
    if env:
        return Path(env)
    legacy_env = os.environ.get("THREAD_MEMORY_REGISTRY_DIR")
    if legacy_env:
        return Path(legacy_env)
    return (home or codex_home()) / "aippocampus-registry"


def norm_path(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def iter_rollouts(home: Path) -> Iterable[Path]:
    sessions = home / "sessions"
    if sessions.exists():
        yield from sessions.rglob("rollout-*.jsonl")


def read_session_meta(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
        item = json.loads(first)
    except Exception:
        return None
    if item.get("type") == "session_meta":
        return item.get("payload", {})
    return None


def public_session_meta(meta: dict | None) -> dict:
    if not meta:
        return {}
    keys = [
        "id",
        "timestamp",
        "cwd",
        "originator",
        "cli_version",
        "source",
        "thread_source",
        "model_provider",
    ]
    return {key: meta[key] for key in keys if key in meta}


def locate_rollout(cwd: str | Path, home: Path | None = None, latest: bool = False) -> Path:
    home = home or codex_home()
    target = norm_path(cwd)
    matches: list[tuple[float, Path]] = []
    latest_seen: tuple[float, Path] | None = None

    for path in iter_rollouts(home):
        try:
            stat = path.stat()
        except OSError:
            continue
        if latest_seen is None or stat.st_mtime > latest_seen[0]:
            latest_seen = (stat.st_mtime, path)
        meta = read_session_meta(path)
        if meta and meta.get("cwd") and norm_path(meta["cwd"]) == target:
            matches.append((stat.st_mtime, path))

    if matches:
        matches.sort(reverse=True, key=lambda x: x[0])
        return matches[0][1]
    if latest and latest_seen:
        return latest_seen[1]
    raise FileNotFoundError(f"no rollout found for cwd: {cwd}")


def thread_key_from_rollout(rollout: str | Path, meta: dict | None = None) -> str:
    rollout_path = Path(rollout)
    session_meta = meta if meta is not None else public_session_meta(read_session_meta(rollout_path))
    session_id = (session_meta or {}).get("id")
    if session_id:
        return f"session:{session_id}"
    digest = hashlib.sha1(str(rollout_path.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return f"rollout:{digest}"


def workspace_thread_key(cwd: str | Path) -> str:
    cwd_path = Path(cwd).resolve()
    digest = hashlib.sha1(str(cwd_path).casefold().encode("utf-8")).hexdigest()[:12]
    return f"workspace:{safe_path_name(cwd_path.name, 'workspace')}:{digest}"


def default_thread_store_dir(
    cwd: str | Path,
    rollout: str | Path | None = None,
    *,
    home: Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    """Return the machine-wide artifact store for a thread.

    AIppocampus is a cross-project continuity layer, so generated recall
    artifacts should not default to the active repository. A workspace-local
    `.aippocampus` path is still valid when explicitly requested, but the
    implicit default is the registry thread store under CODEX_HOME.
    """

    cwd_path = Path(cwd).resolve()
    rollout_path: Path | None = Path(rollout) if rollout else None
    if rollout_path is None:
        try:
            rollout_path = locate_rollout(cwd_path, home or codex_home())
        except Exception:
            rollout_path = None
    thread_key = thread_key_from_rollout(rollout_path) if rollout_path else workspace_thread_key(cwd_path)
    root = (registry_dir or aippocampus_registry_dir(home)).resolve()
    return root / "threads" / safe_path_name(thread_key, "thread")


def default_thread_index_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_store_dir(cwd, rollout) / "index"


def default_thread_clean_source_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_store_dir(cwd, rollout) / "clean-source"


def default_thread_segments_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "segments"


def default_thread_graphify_corpus_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "graphify-corpus"


def default_thread_checkpoint_state_path(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "checkpoint_state.json"


def default_thread_retention_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "retention"


def default_thread_cold_archive_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "cold-archives"


def resolve_artifact_path(value: str | Path | None, cwd: str | Path, default_path: Path) -> Path:
    if value is None:
        return default_path
    path = Path(value)
    return path if path.is_absolute() else Path(cwd).resolve() / path


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError:
                continue


def message_phase(payload: dict) -> str:
    phase = payload.get("phase")
    return str(phase or "")


def extract_message(item: dict, include_tools: bool = False) -> dict | None:
    payload = item.get("payload") or {}
    typ = item.get("type")

    if typ == "event_msg":
        ptype = payload.get("type")
        if ptype == "user_message":
            return {"role": "user", "kind": "user_message", "phase": message_phase(payload), "text": payload.get("message") or ""}
        if ptype == "agent_message":
            return {"role": "assistant", "kind": "agent_message", "phase": message_phase(payload), "text": payload.get("message") or ""}
        if include_tools:
            return {"role": "event", "kind": ptype or "event_msg", "phase": message_phase(payload), "text": json.dumps(payload, ensure_ascii=False)}

    if typ == "response_item":
        ptype = payload.get("type")
        if ptype == "message":
            role = payload.get("role") or "message"
            if role not in {"user", "assistant"}:
                return None
            texts = []
            for part in payload.get("content") or []:
                if isinstance(part, dict):
                    texts.append(part.get("text") or "")
                    texts.append(part.get("input_text") or "")
                    texts.append(part.get("output_text") or "")
            text = "\n".join(t for t in texts if t)
            return {"role": role, "kind": "message", "phase": message_phase(payload), "text": text}
        if include_tools and ptype in {"function_call", "function_call_output", "web_search_call"}:
            return {"role": "tool", "kind": ptype, "phase": "tool", "text": json.dumps(payload, ensure_ascii=False)}

    return None


def tool_payload_kind(item: dict) -> str | None:
    if item.get("type") != "response_item":
        return None
    payload = item.get("payload") or {}
    ptype = payload.get("type")
    if ptype in {"function_call", "function_call_output", "web_search_call"}:
        return str(ptype)
    return None


def empty_turn(turn_index: int, line_no: int, timestamp: str | None) -> dict:
    return {
        "id": turn_index,
        "user_line": line_no,
        "user_timestamp": timestamp,
        "final_line": None,
        "final_timestamp": None,
        "fallback_assistant_line": None,
        "fallback_assistant_timestamp": None,
        "commentary_count": 0,
        "tool_call_count": 0,
        "tool_output_count": 0,
        "start_line": line_no,
        "end_line": line_no,
    }


INJECTED_INSTRUCTION_PREFIXES = (
    "# AGENTS.md instructions",
    "<skill>",
    "<permissions instructions>",
    "<environment_context>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<app-context>",
    "WECHAT SESSION INSTRUCTIONS",
    "WECHAT THREAD CONTINUITY REFRESH",
    "WECHAT SESSION INSTRUCTIONS REFRESH",
)


def is_injected_instruction_text(text: str) -> bool:
    """Return True for known runtime carrier blocks, not topical user prose.

    Full-machine onboarding makes any repeated carrier text show up hundreds of
    times. If these blocks enter clean source or registry search as normal user
    messages, they outrank the real project evidence. Keep this structural and
    prefix-based; do not turn it into a user-facing topic filter.
    """

    stripped = str(text or "").lstrip()
    if any(stripped.startswith(prefix) for prefix in INJECTED_INSTRUCTION_PREFIXES):
        return True
    if re.match(r"^<developer(?:\s|>)", stripped, flags=re.IGNORECASE):
        return True
    return False


def normalize_rollout(rollout: Path, include_tools: bool = False) -> tuple[list[dict], list[dict]]:
    """Return deduped visible messages plus turn summaries.

    Codex Desktop writes a user request as a stream of raw events: commentary,
    tool calls/outputs, and finally a final_answer. Long-term recall should
    prefer the user request plus final_answer, while audit/provenance tools can
    still inspect raw tool lines. For that reason this normalizer records tool
    counts and raw line spans in turns, but it does not put tool payload text in
    the default message index unless include_tools is explicitly requested.
    """

    seen: set[str] = set()
    messages: list[dict] = []
    turns: dict[int, dict] = {}
    current_turn = 0

    for line_no, item in iter_jsonl(rollout):
        timestamp = item.get("timestamp")
        tool_kind = tool_payload_kind(item)
        if current_turn and current_turn in turns:
            turns[current_turn]["end_line"] = line_no
            if tool_kind == "function_call":
                turns[current_turn]["tool_call_count"] += 1
            elif tool_kind in {"function_call_output", "web_search_call"}:
                turns[current_turn]["tool_output_count"] += 1

        msg = extract_message(item, include_tools=include_tools)
        if not msg or not msg.get("text"):
            continue
        text = msg["text"].lstrip()
        if msg["role"] == "user" and is_injected_instruction_text(text):
            continue

        phase = str(msg.get("phase") or "")
        digest = hashlib.sha1((msg["role"] + "\0" + phase + "\0" + msg["text"]).encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)

        if msg["role"] == "user":
            current_turn += 1
            turns[current_turn] = empty_turn(current_turn, line_no, timestamp)
        elif current_turn and current_turn in turns:
            turns[current_turn]["end_line"] = line_no

        turn_index = current_turn if current_turn else None
        is_final = msg["role"] == "assistant" and phase == "final_answer"

        if turn_index and turn_index in turns and msg["role"] == "assistant":
            turns[turn_index]["fallback_assistant_line"] = line_no
            turns[turn_index]["fallback_assistant_timestamp"] = timestamp
            if phase == "commentary":
                turns[turn_index]["commentary_count"] += 1
            if is_final:
                turns[turn_index]["final_line"] = line_no
                turns[turn_index]["final_timestamp"] = timestamp

        messages.append({
            "line": line_no,
            "timestamp": timestamp,
            "role": msg["role"],
            "kind": msg["kind"],
            "phase": phase,
            "turn_index": turn_index,
            "is_final": is_final,
            "sha1": digest,
            "text": msg["text"],
        })

    return messages, list(turns.values())


def iter_messages(rollout: Path, include_tools: bool = False) -> Iterable[dict]:
    messages, _ = normalize_rollout(rollout, include_tools=include_tools)
    yield from messages


def compact_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + " ... " + text[-half:].lstrip()


KEY_BLOCK_BOUNDARY = "-----"
GENERIC_PRIVATE_KEY_BLOCK = (
    rf"{KEY_BLOCK_BOUNDARY}BEGIN [A-Z ]*PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
    rf".*?"
    rf"{KEY_BLOCK_BOUNDARY}END [A-Z ]*PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
)
OPENSSH_PRIVATE_KEY_BLOCK = (
    rf"{KEY_BLOCK_BOUNDARY}BEGIN OPENSSH PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
    rf".*?"
    rf"{KEY_BLOCK_BOUNDARY}END OPENSSH PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
)

EXTERNAL_MODEL_HARD_SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in [
        GENERIC_PRIVATE_KEY_BLOCK,
        OPENSSH_PRIVATE_KEY_BLOCK,
    ]
]

EXTERNAL_MODEL_REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "openai_api_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
        "<redacted:api-key>",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
        "Bearer <redacted:bearer-token>",
    ),
    (
        "credential_url",
        re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)[^@\s:/]+:[^@\s]+@"),
        r"\1<redacted:credentials>@",
    ),
    (
        "secret_assignment",
        re.compile(
            r"\b(api[_-]?key|secret|token|password|passwd|cookie|authorization)\b\s*[:=]\s*"
            r"(\"[^\"]*\"|'[^']*'|(?!(?:<redacted:))[^\s,;&]+)",
            re.IGNORECASE,
        ),
        r"\1=<redacted:secret>",
    ),
    (
        "json_escaped_windows_local_path",
        re.compile(r"(?<![\w])(?:[A-Za-z]:\\\\[^\"'\s<>]+)"),
        "<redacted:local-path>",
    ),
    (
        "windows_local_path",
        re.compile(r"(?<![\w])(?:[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n\t ]+\\?)+[^\\/:*?\"<>|\r\n\t ]*)"),
        "<redacted:local-path>",
    ),
    (
        "posix_local_path",
        re.compile(r"(?<![\w:/])/(?:Users|home|root|tmp|var|mnt|Volumes|private)/(?:[^\s\"'<>]+)"),
        "<redacted:local-path>",
    ),
]


def sanitize_external_model_text(text: str) -> tuple[str, dict[str, Any]]:
    """Redact likely secrets before automatic external-model calls.

    Clean source can include pasted credentials or machine-local paths. This
    helper is intentionally shared by all DeepSeek-compatible routes so new
    workers do not accidentally bypass the prompt-hook privacy boundary.
    """

    original = str(text or "")
    hard_matches = [pattern.pattern for pattern in EXTERNAL_MODEL_HARD_SECRET_PATTERNS if pattern.search(original)]
    if hard_matches:
        return "", {
            "redacted": True,
            "redaction_count": 0,
            "redaction_types": ["private_key_block"],
            "hard_block": True,
            "reason": "private key block detected",
        }

    sanitized = original
    redaction_types: list[str] = []
    redaction_count = 0
    for label, pattern, replacement in EXTERNAL_MODEL_REDACTION_PATTERNS:
        sanitized, count = pattern.subn(replacement, sanitized)
        if count:
            redaction_types.append(label)
            redaction_count += count

    remaining = re.sub(r"<redacted:[^>]+>", " ", sanitized)
    remaining = re.sub(r"\s+", " ", remaining).strip()
    hard_block = bool(redaction_count and len(remaining) < 12)
    return sanitized, {
        "redacted": bool(redaction_count),
        "redaction_count": redaction_count,
        "redaction_types": list(dict.fromkeys(redaction_types))[:8],
        "hard_block": hard_block,
        "reason": "prompt mostly secret/credential material after redaction" if hard_block else "",
    }


def sanitize_external_model_payload(value: Any) -> Any:
    if isinstance(value, str):
        sanitized, _ = sanitize_external_model_text(value)
        return sanitized
    if isinstance(value, list):
        return [sanitize_external_model_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_external_model_payload(item) for item in value)
    if isinstance(value, dict):
        return {key: sanitize_external_model_payload(item) for key, item in value.items()}
    return value


def cli_error_code_from_message(message: str) -> str:
    low = str(message or "").casefold()
    if "missing deepseek api key" in low or "missing api key" in low:
        return "missing_api_key"
    if "no such file" in low or "cannot find the file" in low or "filenotfounderror" in low:
        return "missing_file"
    if "jsondecodeerror" in low or "invalid json" in low:
        return "invalid_json"
    return "runtime_error"


def cli_exit_code_for_error_code(code: str) -> int:
    return 2 if code in {"missing_api_key", "missing_file", "invalid_json"} else 1


def cli_error_payload(exc: BaseException) -> dict[str, Any]:
    message = compact_text(f"{type(exc).__name__}: {exc}", 800)
    code = cli_error_code_from_message(message)
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
        "data": None,
    }


def cli_error_payload_from_message(message: str) -> dict[str, Any]:
    clean_message = compact_text(str(message or ""), 800)
    return {
        "ok": False,
        "error": {
            "code": cli_error_code_from_message(clean_message),
            "message": clean_message,
        },
        "data": None,
    }


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_anchor_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    anchors: list[dict] = []
    current: dict | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if current:
                anchors.append(current)
            current = {"title": line[3:].strip(), "keywords": [], "notes": [], "quotes": [], "sources": []}
            continue
        if not current or not line.startswith("- "):
            continue
        body = line[2:]
        key, sep, value = body.partition(":")
        value = value.strip() if sep else body.strip()
        low = key.strip().casefold()
        if low == "keywords":
            current["keywords"].extend([x.strip() for x in re.split(r"[,，]", value) if x.strip()])
        elif low == "note":
            current["notes"].append(value)
        elif low == "preserved phrase":
            current["quotes"].append(value)
        elif low == "source":
            current["sources"].append(value)
        else:
            current.setdefault("fields", {})[key.strip()] = value

    if current:
        anchors.append(current)
    return anchors


def build_anchor_graph(anchors: list[dict], session_id: str | None = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    thread_id = f"thread:{session_id or 'unknown'}"
    nodes[thread_id] = {"id": thread_id, "type": "thread", "label": session_id or "unknown thread"}

    def add_node(node_id: str, node_type: str, label: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label})

    def add_edge(src: str, dst: str, rel: str) -> None:
        edges.append({"source": src, "target": dst, "type": rel})

    for idx, anchor in enumerate(anchors, start=1):
        title = anchor.get("title") or f"Anchor {idx}"
        topic_id = f"topic:{hashlib.sha1(title.encode('utf-8')).hexdigest()[:12]}"
        add_node(topic_id, "topic", title)
        add_edge(thread_id, topic_id, "HAS_TOPIC")
        for keyword in anchor.get("keywords", []):
            key_id = f"keyword:{hashlib.sha1(keyword.casefold().encode('utf-8')).hexdigest()[:12]}"
            add_node(key_id, "keyword", keyword)
            add_edge(topic_id, key_id, "HAS_KEYWORD")
        for source in anchor.get("sources", []):
            src_id = f"source:{hashlib.sha1(source.encode('utf-8')).hexdigest()[:12]}"
            add_node(src_id, "source", source)
            add_edge(topic_id, src_id, "CITES")
        for quote in anchor.get("quotes", []):
            quote_id = f"quote:{hashlib.sha1(quote.encode('utf-8')).hexdigest()[:12]}"
            add_node(quote_id, "quote", compact_text(quote, 120))
            add_edge(topic_id, quote_id, "PRESERVES")

    return {"nodes": list(nodes.values()), "edges": edges}
