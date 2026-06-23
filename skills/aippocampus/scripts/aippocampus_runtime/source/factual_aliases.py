"""Local source-side factual alias materialization.

The rows produced here are navigation handles for local continuity memory. They
must not become public evidence, answer caches, or source truth: a foreground
agent still has to reopen the referenced clean-source row before making any
factual claim. The point is to preserve enough factual scent locally that
privacy-shaped public reports do not starve ordinary fact lookup.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.privacy import OPENAI_KEY_RE, SENSITIVE_ASSIGNMENT_RE
from aippocampus_runtime.source.io_kernel import write_json_atomic, write_jsonl_dict_rows
from aippocampus_runtime.source.jsonl_reader import load_jsonl_dict_rows

SOURCE_FACTUAL_ALIASES_FILENAME = "source-factual-aliases.jsonl"
SOURCE_FACTUAL_ALIASES_MANIFEST_FILENAME = "source-factual-aliases.manifest.json"
SOURCE_FACTUAL_ALIASES_POLICY_VERSION = "local-source-factual-aliases-v1"
SOURCE_FACTUAL_ALIASES_BUILDER_ID = "aippocampus-local-source-factual-aliases-v1"

_TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,48}|[\u4e00-\u9fff]{2,12}")
_SECRETISH_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization|bearer)\b|"
    r"sk-[A-Za-z0-9._-]{6,}"
)
_RELATION_ALIASES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(r"(?i)\b(called|named|means|known as|codename|nickname)\b|叫|名叫"),
        ("name", "called", "named", "identity", "alias"),
    ),
    (
        re.compile(
            r"(?i)\b(stored|kept|located|found|drawer|shelf|room|address|place|"
            r"location|sits|lives)\b|抽屉|位置|放在|存放|位于"
        ),
        ("where", "kept", "stored", "located", "location", "place"),
    ),
    (
        re.compile(r"(?i)\b(prefer|prefers|favorite|favourite|uses?|adopted?)\b|偏好|喜欢|采用"),
        ("preferred", "preference", "favorite", "choice", "uses"),
    ),
    (
        re.compile(r"(?i)\b(number|code|email|phone|contact)\b|号码|邮箱|电话|代码"),
        ("number", "code", "contact", "email", "phone"),
    ),
    (
        re.compile(r"(?i)\b(date|time|schedule|deadline|appointment|meeting)\b|日期|时间|截止"),
        ("date", "time", "schedule", "deadline"),
    ),
    (
        re.compile(r"(?i)\b(current|currently|latest|status|switched|updated?)\b|当前|最新|状态"),
        ("latest", "status", "currentness", "now"),
    ),
)
_NOUN_ALIASES: dict[str, tuple[str, ...]] = {
    "souvenir": ("keepsake", "memento"),
    "keepsake": ("souvenir", "memento"),
    "memento": ("souvenir", "keepsake"),
    "drawer": ("where", "location", "place", "stored", "kept"),
    "shelf": ("where", "location", "place", "stored", "kept"),
    "room": ("where", "location", "place"),
    "address": ("where", "location", "place"),
    "phone": ("contact", "number"),
    "email": ("contact", "address"),
    "nickname": ("name", "alias"),
    "codename": ("name", "alias", "code"),
    "favorite": ("preferred", "choice"),
    "favourite": ("preferred", "choice"),
}
_STOP_TERMS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "for",
    "from",
    "into",
    "belongs",
}


def _json_sha1(value: Any, *, length: int = 16) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:length]


def _read_messages(path: Path) -> list[dict[str, Any]]:
    return load_jsonl_dict_rows(path).rows


def _messages_fingerprint(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    write_json_atomic(path, payload, indent=None, sort_keys=True)


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    write_jsonl_dict_rows(path, rows, sort_keys=True)


def _safe_term(term: str) -> str:
    value = str(term or "").strip().casefold()
    if not value or value in _STOP_TERMS:
        return ""
    if _SECRETISH_RE.search(value) or OPENAI_KEY_RE.search(value):
        return ""
    if "\\" in value or "/" in value or re.match(r"^[a-z]:", value):
        return ""
    return value


def source_factual_terms(text: str) -> set[str]:
    redacted = SENSITIVE_ASSIGNMENT_RE.sub("", str(text or ""))
    redacted = OPENAI_KEY_RE.sub("", redacted)
    terms = {_safe_term(match.group(0)) for match in _TERM_RE.finditer(redacted)}
    return {term for term in terms if term}


def source_factual_alias_terms(text: str) -> set[str]:
    lowered = str(text or "").casefold()
    terms = source_factual_terms(text)
    aliases: set[str] = set()
    for pattern, values in _RELATION_ALIASES:
        if pattern.search(lowered):
            aliases.update(values)
    for term in terms:
        aliases.update(_NOUN_ALIASES.get(term, ()))
    return {_safe_term(alias) for alias in aliases if _safe_term(alias)}


def _source_ref(row: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {}
    for key in ("thread_key", "message_id", "turn_id", "phase", "role"):
        value = row.get(key)
        if value not in (None, "", []):
            ref[key] = str(value)
    raw_line = row.get("source_line") if row.get("source_line") is not None else row.get("line")
    if raw_line is not None:
        try:
            ref["line"] = int(raw_line)
        except (TypeError, ValueError):
            pass
    return ref


def factual_alias_row(row: dict[str, Any]) -> dict[str, Any] | None:
    text = str(row.get("text") or "")
    aliases = sorted(source_factual_alias_terms(text))
    source_terms = sorted(source_factual_terms(text))[:24]
    if not aliases and not source_terms:
        return None
    ref = _source_ref(row)
    if not ref:
        return None
    route_terms = sorted({*aliases, *source_terms})[:32]
    return {
        "schema_version": 1,
        "kind": "aippocampus_source_factual_alias",
        "row_id": "sfa_" + _json_sha1([ref, aliases, route_terms], length=20),
        "authority": "navigation_only",
        "claim_permission": "none",
        "source_reopen_required": True,
        "query_aliases": aliases[:16],
        "route_terms": route_terms,
        "source_refs": [ref],
    }


def materialize_source_factual_aliases(
    clean_source_dir: Path | str,
    *,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    clean_dir = Path(clean_source_dir)
    messages_path = clean_dir / "messages.jsonl"
    out_path = Path(output_path) if output_path else clean_dir / SOURCE_FACTUAL_ALIASES_FILENAME
    read_result = load_jsonl_dict_rows(messages_path)
    rows = [row for message in read_result.rows if (row := factual_alias_row(message))]
    _write_jsonl_atomic(out_path, rows)
    manifest = {
        "schema_version": 1,
        "kind": "aippocampus_source_factual_aliases_manifest",
        "policy_version": SOURCE_FACTUAL_ALIASES_POLICY_VERSION,
        "builder_id": SOURCE_FACTUAL_ALIASES_BUILDER_ID,
        "generated_at": now_utc(),
        "source_messages_sha1": _messages_fingerprint(messages_path),
        "artifact_sha1": _messages_fingerprint(out_path),
        "row_count": len(rows),
        "source_messages_jsonl_loss": read_result.loss,
        "query_alias_term_count": sum(len(row.get("query_aliases") or []) for row in rows),
        "route_term_count": sum(len(row.get("route_terms") or []) for row in rows),
        "provider_call_count": 0,
        "hot_query_provider_call_count": 0,
        "authority": "navigation_only",
        "source_reopen_required_for_claims": True,
        "raw_source_text_emitted": False,
        "public_report_safe": False,
    }
    _write_json_atomic(out_path.with_name(SOURCE_FACTUAL_ALIASES_MANIFEST_FILENAME), manifest)
    return {
        "ok": True,
        "artifact": str(out_path),
        "manifest": str(out_path.with_name(SOURCE_FACTUAL_ALIASES_MANIFEST_FILENAME)),
        "row_count": len(rows),
        "source_messages_jsonl_loss": read_result.loss,
        "provider_call_count": 0,
        "hot_query_provider_call_count": 0,
        "raw_source_text_emitted": False,
    }
