#!/usr/bin/env python3
"""Optional local vector index boundary for future question tracking.

Vector neighbors are navigation hints only.  Every result must carry a stable
source id so callers can re-open clean-source evidence before treating a match
as continuity, a question link, or memory truth.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VectorRecord:
    source_id: str
    vector: tuple[float, ...]
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "vector": list(self.vector),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class VectorSearchResult:
    source_id: str
    score: float
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "score": self.score,
            "metadata": self.metadata,
        }


class QuestionVectorIndex(Protocol):
    dimensions: int | None

    def add(
        self, source_id: str, vector: Iterable[float], metadata: Mapping[str, Any] | None = None
    ) -> None:
        """Add or replace a vector for a stable source id."""

    def remove(self, source_id: str) -> bool:
        """Remove a source id, returning whether it existed."""

    def search(
        self,
        vector: Iterable[float],
        *,
        top_k: int = 10,
        allow_source_ids: Iterable[str] | None = None,
    ) -> list[VectorSearchResult]:
        """Return scored neighbors that still require source-backed verification."""

    def write(self, path: Path) -> None:
        """Persist the local index as a rebuildable cache."""

    @classmethod
    def load(cls, path: Path) -> "QuestionVectorIndex":
        """Load an index implementation from a rebuildable cache."""


def normalize_vector(vector: Iterable[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if not values:
        raise ValueError("vector must not be empty")
    return values


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class LocalQuestionVectorIndex:
    """Small deterministic implementation used for tests and local smokes."""

    def __init__(self, *, dimensions: int | None = None) -> None:
        self.dimensions = dimensions
        self._records: dict[str, VectorRecord] = {}

    def add(
        self, source_id: str, vector: Iterable[float], metadata: Mapping[str, Any] | None = None
    ) -> None:
        stable_id = source_id.strip()
        if not stable_id:
            raise ValueError("source_id must be a non-empty stable id")
        values = normalize_vector(vector)
        self._ensure_dimensions(values)
        self._records[stable_id] = VectorRecord(stable_id, values, dict(metadata or {}))

    def remove(self, source_id: str) -> bool:
        return self._records.pop(source_id, None) is not None

    def search(
        self,
        vector: Iterable[float],
        *,
        top_k: int = 10,
        allow_source_ids: Iterable[str] | None = None,
    ) -> list[VectorSearchResult]:
        query = normalize_vector(vector)
        self._ensure_dimensions(query)
        allowed = set(allow_source_ids) if allow_source_ids is not None else None
        results = [
            VectorSearchResult(
                source_id=record.source_id,
                score=round(cosine_similarity(query, record.vector), 6),
                metadata=dict(record.metadata),
            )
            for record in self._records.values()
            if allowed is None or record.source_id in allowed
        ]
        results.sort(key=lambda item: (-item.score, item.source_id))
        return results[: max(0, int(top_k))]

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_question_vector_index",
            "dimensions": self.dimensions,
            "records": [record.as_dict() for record in self._records.values()],
            "truth_boundary": "vector_neighbors_are_hints_requiring_clean_source_verification",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LocalQuestionVectorIndex":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
            raise ValueError("unsupported question vector index schema_version")
        index = cls(dimensions=payload.get("dimensions"))
        for item in payload.get("records") or []:
            if not isinstance(item, dict):
                continue
            index.add(
                str(item.get("source_id") or ""),
                item.get("vector") or (),
                item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
        return index

    def _ensure_dimensions(self, vector: tuple[float, ...]) -> None:
        if self.dimensions is None:
            self.dimensions = len(vector)
        if len(vector) != self.dimensions:
            raise ValueError(
                f"vector dimensions do not match index dimensions: {len(vector)} != {self.dimensions}"
            )
