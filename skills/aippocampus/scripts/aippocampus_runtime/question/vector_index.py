#!/usr/bin/env python3
"""Optional local vector index boundary for future question tracking.

Vector neighbors are navigation hints only.  Every result must carry a stable
source id so callers can re-open clean-source evidence before treating a match
as continuity, a question link, or memory truth.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

SCHEMA_VERSION = 1
PROVIDER_CONFIG_STATUS_KIND = "aippocampus_vector_provider_config_status"

_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_LATIN_RE = re.compile(r"[A-Za-z]")


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


@dataclass(frozen=True)
class VectorProviderConfig:
    provider: str
    model: str
    dimensions: int | None = None
    supported_language_buckets: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "VectorProviderConfig | None":
        if not payload:
            return None
        dimensions = safe_dimension(payload.get("dimensions"))
        languages = tuple(
            normalize_language_bucket(str(value))
            for value in (payload.get("supported_language_buckets") or payload.get("languages") or ())
            if str(value).strip()
        )
        return cls(
            provider=str(payload.get("provider") or "unknown").strip() or "unknown",
            model=str(payload.get("model") or "unknown").strip() or "unknown",
            dimensions=dimensions,
            supported_language_buckets=languages,
        )


def safe_dimension(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        dimension = int(value)
    except (TypeError, ValueError):
        return None
    return dimension if dimension > 0 else None


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


def detect_language_bucket(text: str) -> str:
    if _CJK_RE.search(text):
        return "cjk"
    if _LATIN_RE.search(text):
        return "latin"
    return "unknown"


def normalize_language_bucket(value: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    if normalized in {"zh", "zh-cn", "zh-tw", "ja", "ko", "cjk", "chinese", "japanese", "korean"}:
        return "cjk"
    if normalized in {"en", "eng", "english", "latin", "ascii"}:
        return "latin"
    if normalized in {"multi", "multilingual", "*", "any", "all"}:
        return "multilingual"
    return normalized or "unknown"


def vector_provider_config_status(
    *,
    query_text: str,
    provider_config: Mapping[str, Any] | VectorProviderConfig | None,
    expected_dimensions: int | None = None,
) -> dict[str, Any]:
    """Report whether a vector route can be trusted as a routing hint.

    This is deliberately a local contract check, not a provider probe. A
    language or dimension mismatch must degrade to lexical/source-reopen
    routing instead of silently reporting a vector result as valid.
    """

    config = (
        provider_config
        if isinstance(provider_config, VectorProviderConfig)
        else VectorProviderConfig.from_mapping(provider_config)
    )
    language_bucket = detect_language_bucket(query_text)
    fallback = {
        "lexical_fallback_visible": True,
        "source_reopen_required_for_claims": True,
        "vector_scores_are_navigation_only": True,
    }
    if config is None:
        return {
            "kind": PROVIDER_CONFIG_STATUS_KIND,
            "status": "degraded",
            "reason": "provider_config_missing",
            "query_language_bucket": language_bucket,
            "fallback": fallback,
            "provider_checked_live": False,
        }

    supported = tuple(
        bucket
        for bucket in (normalize_language_bucket(value) for value in config.supported_language_buckets)
        if bucket and bucket != "unknown"
    )
    reasons: list[str] = []
    if (
        expected_dimensions is not None
        and config.dimensions is not None
        and int(config.dimensions) != int(expected_dimensions)
    ):
        reasons.append("embedding_dimension_mismatch")
    if (
        language_bucket != "unknown"
        and supported
        and "multilingual" not in supported
        and language_bucket not in supported
    ):
        reasons.append("embedding_language_mismatch")

    status = "supported" if not reasons else "provider_config_unsupported"
    return {
        "kind": PROVIDER_CONFIG_STATUS_KIND,
        "status": status,
        "reason": reasons[0] if len(reasons) == 1 else (";".join(reasons) if reasons else ""),
        "query_language_bucket": language_bucket,
        "provider": config.provider,
        "model": config.model,
        "expected_dimensions": expected_dimensions,
        "configured_dimensions": config.dimensions,
        "supported_language_buckets": list(supported),
        "fallback": fallback,
        "provider_checked_live": False,
        "cannot_claim": [
            "live_embedding_quality",
            "provider_output_as_source_truth",
        ],
    }


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


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
