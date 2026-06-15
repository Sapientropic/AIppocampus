"""Explicit scope equivalence helpers for local/global compatibility.

This layer only honors producer-owned ids: canonical scope ids, explicit
aliases, and explicit parent/nesting ids. It never infers equivalence from
shared vocabulary, display text, or semantic similarity, and it cannot cross
privacy or authority boundaries on its own.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_scope(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 120
        and not any(marker in text for marker in ("source://private", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return ""


def _safe_fallback_scope(value: Any) -> str:
    scope = _safe_scope(value)
    if scope:
        return scope
    digest = hashlib.sha256(_text(value).encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"scope_{digest}" if _text(value) else ""


def _scope_list(value: Any) -> list[str]:
    raw_items: Sequence[Any]
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, Mapping)):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    for item in raw_items:
        scope = _safe_scope(item)
        if scope and scope not in out:
            out.append(scope)
    return out


def scope_identity_from_row(row: Mapping[str, Any], *, scope: str) -> dict[str, Any]:
    canonical = _safe_scope(
        row.get("canonical_scope_id")
        or row.get("scope_canonical_id")
        or row.get("canonical_scope")
    )
    aliases = [
        *_scope_list(row.get("scope_aliases")),
        *_scope_list(row.get("equivalent_scopes")),
    ]
    parents = [
        *_scope_list(row.get("parent_scopes")),
        *_scope_list(row.get("scope_parents")),
    ]
    equivalent = []
    for item in (scope, canonical, *aliases):
        if item and item not in equivalent:
            equivalent.append(item)
    nesting_path = []
    for item in (*parents, scope):
        if item and item not in nesting_path:
            nesting_path.append(item)
    return {
        "scope": scope,
        "canonical_scope_id": canonical,
        "equivalent_scopes": equivalent,
        "parent_scopes": parents,
        "nesting_path": nesting_path,
        "shared_vocabulary_is_not_equivalence": True,
        "producer_owned_scope_ids_only": True,
    }


def _identity(section: Mapping[str, Any]) -> Mapping[str, Any]:
    identity = section.get("scope_identity")
    return identity if isinstance(identity, Mapping) else {}


def scope_match_diagnostic(sections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not sections or any(section.get("scope_missing") for section in sections):
        return {
            "matched": False,
            "match_kind": "none",
            "common_scope": "",
            "reason_code": "missing_scope_identity",
        }
    scopes = [str(section.get("scope") or "") for section in sections]
    if scopes and len(set(scopes)) == 1:
        return {
            "matched": True,
            "match_kind": "exact",
            "common_scope": scopes[0],
            "reason_code": "exact_scope_match",
        }

    equivalent_sets = [
        {str(item) for item in (_identity(section).get("equivalent_scopes") or []) if str(item)}
        for section in sections
    ]
    if equivalent_sets and all(equivalent_sets):
        common = set.intersection(*equivalent_sets)
        if common:
            return {
                "matched": True,
                "match_kind": "equivalent",
                "common_scope": sorted(common)[0],
                "reason_code": "normalized_equivalent_scope_match",
            }

    nesting_sets = [
        {str(item) for item in (_identity(section).get("nesting_path") or []) if str(item)}
        for section in sections
    ]
    if nesting_sets and all(nesting_sets):
        common_nested = set.intersection(*nesting_sets)
        if common_nested:
            return {
                "matched": True,
                "match_kind": "narrowed",
                "common_scope": sorted(common_nested)[0],
                "reason_code": "normalized_narrowed_scope_match",
            }

    return {
        "matched": False,
        "match_kind": "none",
        "common_scope": "",
        "reason_code": "no_explicit_scope_equivalence",
    }


__all__ = [
    "scope_identity_from_row",
    "scope_match_diagnostic",
]
