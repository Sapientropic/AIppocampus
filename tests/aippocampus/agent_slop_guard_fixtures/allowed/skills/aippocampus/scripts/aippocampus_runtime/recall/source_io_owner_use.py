from __future__ import annotations

from pathlib import Path

from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows


def rewrite_rows(path: Path, output: Path) -> None:
    rows = load_jsonl_dict_rows(path).rows
    atomic_write_json(output, {"row_count": len(rows)})
