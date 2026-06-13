"""Minimal LongMemEval-V2 official-harness memory adapter contract.

This module is intentionally small and text-only. The official LongMemEval-V2
harness discovers memory backends through `memory_modules.memory`, so a real
pilot should copy or import this class inside an ignored official checkout and
register `memory_type="aippocampus_context_provider"` there. The adapter keeps
source refs next to returned text, but all raw trajectory text remains in the
local official-run workspace and must not be committed with AIppocampus
reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

try:  # pragma: no cover - exercised only inside an official LME-V2 checkout.
    from memory_modules.memory import Memory, register_memory
except Exception:  # pragma: no cover - local unit tests use the fallback.

    class Memory:
        def __init__(self, memory_params: dict[str, object]) -> None:
            self.memory_params = dict(memory_params)

        def _save_backend(self, output_dir: Path) -> None:
            return None

        def _load_backend(self, input_dir: Path) -> None:
            return None

    def register_memory(memory_cls: type[Memory]) -> type[Memory]:
        return memory_cls


class MemoryContextItem(TypedDict):
    type: Literal["text", "image"]
    value: str


TOKEN_RE = re.compile(r"[A-Za-z0-9_]{3,}")
DEFAULT_INCLUDE_KEYS = {
    "accessibility_tree",
    "action",
    "content",
    "goal",
    "observation",
    "outcome",
    "text",
    "thought",
    "title",
}
DEFAULT_EXCLUDE_KEYS = {
    "base64",
    "cookie",
    "image",
    "password",
    "screenshot",
    "secret",
    "token",
}


@dataclass(frozen=True)
class SourceRecord:
    trajectory_id: str
    path: str
    text: str
    token_set: frozenset[str]


def terms(text: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in TOKEN_RE.finditer(str(text or ""))
    }


def stable_ref(value: str) -> str:
    # Keep refs readable but avoid turning local absolute paths into context ids.
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "unknown"))[:96]


def iter_text_fields(
    value: Any,
    *,
    include_keys: set[str],
    exclude_keys: set[str],
    path: str = "$",
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            lowered = key_text.casefold()
            child_path = f"{path}.{key_text}"
            if any(blocked in lowered for blocked in exclude_keys):
                continue
            if isinstance(child, str):
                if lowered in include_keys and child.strip():
                    rows.append((child_path, child.strip()))
            else:
                rows.extend(
                    iter_text_fields(
                        child,
                        include_keys=include_keys,
                        exclude_keys=exclude_keys,
                        path=child_path,
                    )
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(
                iter_text_fields(
                    child,
                    include_keys=include_keys,
                    exclude_keys=exclude_keys,
                    path=f"{path}[{index}]",
                )
            )
    return rows


@register_memory
class AippocampusContextProviderMemory(Memory):
    """Small lexical source-context provider for a tiny official LME-V2 pilot."""

    memory_type = "aippocampus_context_provider"

    def __init__(self, memory_params: dict[str, object]) -> None:
        super().__init__(memory_params)
        self.max_records = int(memory_params.get("max_records") or 5000)
        self.max_context_items = int(memory_params.get("max_context_items") or 8)
        self.max_context_chars = int(memory_params.get("max_context_chars") or 1200)
        include = memory_params.get("include_keys")
        exclude = memory_params.get("exclude_key_terms")
        self.include_keys = (
            {str(item).casefold() for item in include}
            if isinstance(include, list)
            else set(DEFAULT_INCLUDE_KEYS)
        )
        self.exclude_keys = (
            {str(item).casefold() for item in exclude}
            if isinstance(exclude, list)
            else set(DEFAULT_EXCLUDE_KEYS)
        )
        self._records: list[SourceRecord] = []
        self._last_query_metadata: dict[str, object] = {}

    def insert(self, trajectory: dict[str, object]) -> None:
        trajectory_id = stable_ref(str(trajectory.get("id") or f"trajectory-{len(self._records)}"))
        for path, text in iter_text_fields(
            trajectory,
            include_keys=self.include_keys,
            exclude_keys=self.exclude_keys,
        ):
            if len(self._records) >= self.max_records:
                return
            clean = re.sub(r"\s+", " ", text).strip()
            if not clean:
                continue
            self._records.append(
                SourceRecord(
                    trajectory_id=trajectory_id,
                    path=stable_ref(path),
                    text=clean,
                    token_set=frozenset(terms(clean)),
                )
            )

    def query(
        self,
        query: str,
        query_image: str | None = None,
    ) -> list[MemoryContextItem]:
        query_terms = terms(query)
        scored: list[tuple[int, int, SourceRecord]] = []
        for index, record in enumerate(self._records):
            overlap = len(query_terms & set(record.token_set))
            if overlap <= 0:
                continue
            scored.append((overlap, index, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = scored[: max(1, self.max_context_items)]
        self._last_query_metadata = {
            "memory_type": self.memory_type,
            "candidate_record_count": len(scored),
            "returned_context_items": len(selected),
            "query_image_received": bool(query_image),
            "raw_text_emitted_in_metadata": False,
        }
        return [
            {
                "type": "text",
                "value": (
                    f"[source trajectory={record.trajectory_id} field={record.path}] "
                    f"{record.text[: self.max_context_chars]}"
                ),
            }
            for _score, _index, record in selected
        ]

    def post_query_hook(
        self,
        *,
        query: str,
        query_image: str | None,
        memory_context: list[MemoryContextItem],
    ) -> dict[str, object] | None:
        return {
            **self._last_query_metadata,
            "returned_context_items_after_validation": len(memory_context),
        }

    def _save_backend(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "trajectory_id": record.trajectory_id,
                "path": record.path,
                "text": record.text,
            }
            for record in self._records
        ]
        (output_dir / "aippocampus_context_records.json").write_text(
            json.dumps(rows, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_backend(self, input_dir: Path) -> None:
        path = input_dir / "aippocampus_context_records.json"
        if not path.exists():
            return
        rows = json.loads(path.read_text(encoding="utf-8"))
        self._records = [
            SourceRecord(
                trajectory_id=str(row.get("trajectory_id") or "unknown"),
                path=str(row.get("path") or "$"),
                text=str(row.get("text") or ""),
                token_set=frozenset(terms(str(row.get("text") or ""))),
            )
            for row in rows
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
