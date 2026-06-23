"""Compatibility import surface for the canonical source IO kernel."""

from __future__ import annotations

from aippocampus_runtime.source.io_kernel import (
    JsonlReadResult,
    empty_jsonl_loss,
    iter_jsonl_dict_rows,
    jsonl_loss_warning,
    load_jsonl_dict_rows,
)

__all__ = [
    "JsonlReadResult",
    "empty_jsonl_loss",
    "iter_jsonl_dict_rows",
    "jsonl_loss_warning",
    "load_jsonl_dict_rows",
]
