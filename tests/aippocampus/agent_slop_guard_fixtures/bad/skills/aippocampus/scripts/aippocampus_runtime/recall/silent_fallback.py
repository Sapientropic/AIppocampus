from __future__ import annotations

from typing import Any


def load_cache(rows: list[str]) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for row in rows:
        try:
            loaded.append({"row": row})
        except Exception:
            continue
    return loaded
