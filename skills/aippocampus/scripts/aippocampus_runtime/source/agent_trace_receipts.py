"""Receipt adapters for trace admission producer/consumer joins."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.source import agent_trace_families
from aippocampus_runtime.source.io_kernel import normalize_source_refs

SOURCE_REF_INLINE_FIELDS = (
    "thread_key",
    "thread_id",
    "message_id",
    "turn_id",
    "turn_index",
    "source_ref",
    "source_id",
    "source_line",
    "line",
)
ACCEPTED_RECEIPT_FIELDS = ("receipt_refs", "receipt_state")
RECEIPT_FIELD_CONTRACT = {
    "receipt_refs": {
        "status": "adapter_produced",
        "adapter": "adapt_trace_rows_with_receipts",
        "consumer": "_has_receipt",
    },
    "receipt_state": {
        "status": "adapter_produced",
        "adapter": "adapt_trace_rows_with_receipts",
        "accepted_value": "matched",
        "consumer": "_has_receipt",
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _inline_ref_has_anchor(ref: Mapping[str, Any]) -> bool:
    return any(
        ref.get(key) not in (None, "", [])
        for key in (
            "message_id",
            "turn_id",
            "turn_index",
            "source_line",
            "line",
            "source_id",
        )
    )


def _behavior_source_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_refs: list[Mapping[str, Any]] = []
    refs = row.get("source_refs")
    if isinstance(refs, list):
        raw_refs.extend(ref for ref in refs if isinstance(ref, Mapping))
    inline = {
        key: row.get(key)
        for key in SOURCE_REF_INLINE_FIELDS
        if row.get(key) not in (None, "", [])
    }
    if inline and _inline_ref_has_anchor(inline):
        raw_refs.append(inline)
    normalized = normalize_source_refs(
        raw_refs,
        limit=8,
        require_anchor=True,
        require_thread=False,
        identity_key=True,
        allow_string_ref=False,
    )
    return [dict(ref) for ref in normalized]


def adapt_trace_row(row: Mapping[str, Any]) -> dict[str, Any]:
    adapted = dict(row)
    source_refs = _behavior_source_refs(row)
    if source_refs:
        adapted["source_refs"] = source_refs
        adapted["source_ref_count"] = len(source_refs)
    return adapted


def _has_refs(row: Mapping[str, Any], key: str = "source_refs") -> bool:
    refs = row.get(key)
    return isinstance(refs, list) and any(isinstance(item, Mapping) for item in refs)


def _has_receipt(row: Mapping[str, Any]) -> bool:
    return _has_refs(row, "receipt_refs") or bool(row.get("receipt_state") == "matched")


def _success(row: Mapping[str, Any]) -> bool:
    status = _text(row.get("status") or row.get("outcome")).casefold()
    if status in {"ok", "pass", "passed", "success", "succeeded"}:
        return True
    exit_code = row.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code == 0
    if isinstance(exit_code, str):
        try:
            return int(exit_code) == 0
        except ValueError:
            return False
    return False


def _source_ref_digest(row: Mapping[str, Any]) -> str:
    refs = row.get("source_refs")
    if not isinstance(refs, list) or not refs:
        return ""
    safe_refs = []
    for ref in refs[:8]:
        if not isinstance(ref, Mapping):
            continue
        safe_refs.append(
            {
                "message_id": _text(ref.get("message_id"))[:80],
                "turn_id": _text(ref.get("turn_id"))[:80],
                "thread_key": _text(ref.get("thread_key"))[:120],
                "line": ref.get("line") or ref.get("source_line"),
            }
        )
    return (
        stable_json_join_id("src", safe_refs, ensure_ascii=False, default_str=False, length=20)
        if safe_refs
        else ""
    )


def _source_ref_keys(row: Mapping[str, Any]) -> set[str]:
    refs = row.get("source_refs")
    if not isinstance(refs, list):
        return set()
    keys: set[str] = set()
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        identity = {
            "thread_key": _text(ref.get("thread_key"))[:120],
            "message_id": _text(ref.get("message_id"))[:80],
            "turn_id": _text(ref.get("turn_id"))[:80],
            "turn_index": _text(ref.get("turn_index"))[:40],
            "line": _text(ref.get("line") or ref.get("source_line"))[:40],
            "source_id": _text(ref.get("source_id"))[:120],
        }
        if any(identity.values()):
            keys.add(
                stable_json_join_id(
                    "source_ref_key",
                    identity,
                    ensure_ascii=False,
                    default_str=False,
                    length=20,
                )
            )
    return keys


def _receipt_ref_for(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        "receipt_trace_id": _text(row.get("trace_id") or row.get("id"))[:120],
        "trace_family": agent_trace_families.normalized_family(row),
        "source_ref_digest": _source_ref_digest(row),
    }


def _is_receipt_producer(row: Mapping[str, Any]) -> bool:
    family = agent_trace_families.normalized_family(row)
    if family in agent_trace_families.SOURCE_OPEN_FAMILIES and _has_refs(row):
        return True
    return family in agent_trace_families.CHECK_RECEIPT_FAMILIES and _success(row) and _has_refs(row)


def _dedupe_receipt_refs(refs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    clean: list[dict[str, Any]] = []
    for ref in refs:
        item = {str(key): str(value) for key, value in ref.items() if value not in (None, "", [])}
        key = tuple(sorted(item.items()))
        if not item or key in seen:
            continue
        seen.add(key)
        clean.append(item)
    return clean[:8]


def adapt_trace_rows_with_receipts(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Join final closeout self-reports to behavior/source receipts in one batch."""

    adapted = [adapt_trace_row(row) for row in rows if isinstance(row, Mapping)]
    receipts_by_source_key: dict[str, list[dict[str, str]]] = {}
    for row in adapted:
        if not _is_receipt_producer(row):
            continue
        receipt_ref = _receipt_ref_for(row)
        for key in _source_ref_keys(row):
            receipts_by_source_key.setdefault(key, []).append(receipt_ref)

    joined: list[dict[str, Any]] = []
    for row in adapted:
        current = dict(row)
        family = agent_trace_families.normalized_family(current)
        if (
            family in agent_trace_families.FINAL_CLOSEOUT_FAMILIES
            and _has_refs(current)
            and not _has_receipt(current)
        ):
            receipt_refs: list[dict[str, str]] = []
            for key in _source_ref_keys(current):
                receipt_refs.extend(receipts_by_source_key.get(key, []))
            clean_refs = _dedupe_receipt_refs(receipt_refs)
            if clean_refs:
                current["receipt_refs"] = clean_refs
                current["receipt_state"] = "matched"
        joined.append(current)
    return joined


__all__ = [
    "ACCEPTED_RECEIPT_FIELDS",
    "RECEIPT_FIELD_CONTRACT",
    "adapt_trace_row",
    "adapt_trace_rows_with_receipts",
]
