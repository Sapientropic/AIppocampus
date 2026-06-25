from __future__ import annotations

from typing import Any


def load_cache(rows: list[str]) -> dict[str, Any]:
    loaded: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for row in rows:
        try:
            loaded.append({"row": row})
        except Exception as exc:
            warnings.append({"code": "row_unavailable", "reason": type(exc).__name__})
    return {"status": "degraded" if warnings else "ok", "rows": loaded, "warnings": warnings}
