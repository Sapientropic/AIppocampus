"""Typed cache-read diagnostics for recall-local JSON caches.

Cache files are navigation state, not source truth. When a cache read fails, the
runtime should degrade to a fresh recall/search path while preserving a small
operator-readable reason. Returning an empty dict directly makes a corrupt cache
look identical to a legitimate miss, which is exactly the blind spot this owner
prevents.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CacheReadStatus = Literal["ok", "missing", "malformed", "unreadable", "unsupported_schema"]


@dataclass(frozen=True)
class CacheReadDiagnostic:
    cache_name: str
    status: CacheReadStatus
    reason_code: str
    message: str
    path_label: str
    warning_count: int = 0
    loss: Mapping[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def has_loss(self) -> bool:
        return self.status in {"malformed", "unreadable", "unsupported_schema"} or self.warning_count > 0

    def public_detail(self, *, include_missing: bool = False) -> dict[str, Any] | None:
        if self.status == "ok":
            return None
        if self.status == "missing" and not include_missing:
            return None
        detail: dict[str, Any] = {
            "cache_name": self.cache_name,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "path_label": self.path_label,
            "warning_count": self.warning_count,
            "local_path_redacted": True,
        }
        if self.loss:
            detail["loss"] = dict(self.loss)
        return detail


@dataclass(frozen=True)
class CacheReadResult:
    data: dict[str, Any]
    diagnostic: CacheReadDiagnostic

    @property
    def ok(self) -> bool:
        return self.diagnostic.ok


def ok_diagnostic(cache_name: str, *, path_label: str) -> CacheReadDiagnostic:
    return CacheReadDiagnostic(
        cache_name=cache_name,
        status="ok",
        reason_code="ok",
        message="cache read succeeded",
        path_label=path_label,
    )


def cache_read_result(
    *,
    data: dict[str, Any],
    cache_name: str,
    status: CacheReadStatus,
    reason_code: str,
    message: str,
    path_label: str,
    warning_count: int = 0,
    loss: Mapping[str, Any] | None = None,
) -> CacheReadResult:
    return CacheReadResult(
        data=data,
        diagnostic=CacheReadDiagnostic(
            cache_name=cache_name,
            status=status,
            reason_code=reason_code,
            message=message,
            path_label=path_label,
            warning_count=warning_count,
            loss=loss,
        ),
    )


def read_json_cache(
    path: Path,
    *,
    cache_name: str,
    default_factory: Callable[[], dict[str, Any]],
    path_label: str,
) -> CacheReadResult:
    target = Path(path)
    if not target.exists():
        return cache_read_result(
            data=default_factory(),
            cache_name=cache_name,
            status="missing",
            reason_code="cache_missing",
            message="cache file is missing",
            path_label=path_label,
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return cache_read_result(
            data=default_factory(),
            cache_name=cache_name,
            status="malformed",
            reason_code="invalid_json",
            message="cache JSON is malformed; treat cache misses as degraded",
            path_label=path_label,
            warning_count=1,
        )
    except (OSError, UnicodeDecodeError):
        return cache_read_result(
            data=default_factory(),
            cache_name=cache_name,
            status="unreadable",
            reason_code="cache_unreadable",
            message="cache file could not be read; treat cache misses as degraded",
            path_label=path_label,
            warning_count=1,
        )
    if not isinstance(raw, dict):
        return cache_read_result(
            data=default_factory(),
            cache_name=cache_name,
            status="unsupported_schema",
            reason_code="non_object_json",
            message="cache JSON is not an object; treat cache misses as degraded",
            path_label=path_label,
            warning_count=1,
        )
    return CacheReadResult(
        data=raw,
        diagnostic=ok_diagnostic(cache_name, path_label=path_label),
    )
