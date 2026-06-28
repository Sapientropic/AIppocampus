from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def write_jsonl_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write small test JSONL fixtures without cloning local writer helpers."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
