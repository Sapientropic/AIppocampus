from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LOCAL_REOPEN_TOKEN_ENCODING = "utf8_xor_v1_not_encryption"
_LOCAL_REOPEN_TOKEN_MASK = 0xA5


def encode_local_reopen_token(value: Any) -> dict[str, Any]:
    """Encode a local reopen token so it is not stored as ordinary text.

    This is an accidental-disclosure guard for a same-machine cache, not a
    cryptographic promise. The handle remains local-private navigation material;
    public output should keep using `--public` / `--compact-json`.
    """

    raw_text = (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if isinstance(value, Mapping)
        else str(value or "")
    )
    raw = raw_text.encode("utf-8")
    return {
        "encoding": LOCAL_REOPEN_TOKEN_ENCODING,
        "bytes": [byte ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw],
    }


def decode_local_reopen_token(value: Any) -> str:
    if isinstance(value, Mapping) and value.get("encoding") == LOCAL_REOPEN_TOKEN_ENCODING:
        raw_bytes = value.get("bytes")
        if not isinstance(raw_bytes, list):
            return ""
        try:
            return bytes(int(byte) ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw_bytes).decode(
                "utf-8"
            )
        except (TypeError, ValueError, UnicodeDecodeError):
            return ""
    return ""


def local_reopen_context_token(
    *,
    cwd: str | Path | None,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    macro_state_path: str | Path | None,
) -> dict[str, Any] | None:
    context: dict[str, str] = {}
    if cwd:
        context["cwd"] = str(Path(cwd).resolve())
    if clean_source_dir:
        context["clean_source_dir"] = str(Path(clean_source_dir).resolve())
    if registry_dir:
        context["registry_dir"] = str(Path(registry_dir).resolve())
    if macro_state_path:
        context["macro_state_jsonl"] = str(Path(macro_state_path).resolve())
    return encode_local_reopen_token(context) if context else None


def decode_local_reopen_context(value: Any) -> dict[str, Any]:
    raw = decode_local_reopen_token(value)
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}
