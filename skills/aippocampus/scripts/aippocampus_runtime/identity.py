"""Low-level stable identity helpers with no runtime graph dependencies."""

from __future__ import annotations

import hashlib
import json


def stable_digest(text: str, *, length: int) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def stable_json_id(prefix: str, *parts: object, length: int = 18) -> str:
    """Return a stable id for local structural metadata, not proof of content truth."""

    raw = "\0".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{stable_digest(raw, length=length)}"


def stable_json_digest(
    value: object,
    *,
    length: int = 16,
    ensure_ascii: bool = True,
    separators: tuple[str, str] | None = None,
    default_str: bool = True,
) -> str:
    """Return a digest for one canonical JSON value."""

    if default_str:
        raw = json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            sort_keys=True,
            separators=separators,
            default=str,
        )
    else:
        raw = json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=separators)
    return stable_digest(raw, length=length)


def stable_json_join_id(
    prefix: str,
    *parts: object,
    sep: str = "\n",
    length: int = 18,
    ensure_ascii: bool = True,
    default_str: bool = True,
) -> str:
    """Return a prefixed id for legacy joined JSON part material."""

    if default_str:
        raw = sep.join(
            json.dumps(part, ensure_ascii=ensure_ascii, sort_keys=True, default=str)
            for part in parts
        )
    else:
        raw = sep.join(json.dumps(part, ensure_ascii=ensure_ascii, sort_keys=True) for part in parts)
    return f"{prefix}_{stable_digest(raw, length=length)}"


def stable_json_lines_id(
    prefix: str,
    *parts: object,
    length: int = 18,
    ensure_ascii: bool = True,
    default_str: bool = True,
) -> str:
    """Return a prefixed id for legacy newline-separated JSON identity rows."""

    if default_str:
        raw = "\n".join(
            json.dumps(part, ensure_ascii=ensure_ascii, sort_keys=True, default=str)
            for part in parts
        )
    else:
        raw = "\n".join(json.dumps(part, ensure_ascii=ensure_ascii, sort_keys=True) for part in parts)
    return f"{prefix}_{stable_digest(raw, length=length)}"


def stable_json_tuple_digest(
    *parts: object,
    length: int = 16,
    ensure_ascii: bool = True,
) -> str:
    """Return a digest for legacy tuple-JSON identity material."""

    raw = json.dumps(parts, ensure_ascii=ensure_ascii, sort_keys=True, default=str)
    return stable_digest(raw, length=length)


def stable_json_tuple_id(
    prefix: str,
    *parts: object,
    length: int = 16,
    ensure_ascii: bool = True,
) -> str:
    """Return a prefixed id for legacy tuple-JSON identity material."""

    return f"{prefix}_{stable_json_tuple_digest(*parts, length=length, ensure_ascii=ensure_ascii)}"
