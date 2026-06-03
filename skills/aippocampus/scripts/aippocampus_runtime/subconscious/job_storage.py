#!/usr/bin/env python3
"""Append-only storage helpers for subconscious job findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import now_utc, sanitize_external_model_payload
from aippocampus_runtime.subconscious.job_circuits import PROMPT_VERSION
from aippocampus_runtime.subconscious.staging_maintenance import (
    StagingPressureThresholds,
    queue_pressure,
)


def public_model_route(route: Any) -> dict[str, str]:
    if not isinstance(route, Mapping):
        return {}
    provider = str(route.get("provider") or "").strip()
    safe = "".join(char for char in provider[:48] if char.isalnum() or char in {"_", "-", "."})
    return {"provider": safe or "unknown"}


def append_job_findings(
    path: Path,
    findings: list[dict[str, Any]],
    *,
    model: str,
    batch_id: str,
    usage: dict[str, Any],
    source: str = "deepseek_subconscious_jobs",
    model_route: dict[str, Any] | None = None,
    pressure_thresholds: StagingPressureThresholds | None = None,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for finding in findings:
            payload = dict(finding)
            payload["finding_kind"] = payload.pop("kind", "")
            event = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_job_finding",
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": public_model_route(model_route),
                "usage": usage or {},
                **payload,
            }
            # Staging findings remain local-private because source refs are needed for
            # later review. Persist only a redacted event so model echoes cannot turn
            # this audit trail into a secret or machine-path sink.
            safe_event = sanitize_external_model_payload(event)
            fh.write(json.dumps(safe_event, ensure_ascii=False) + "\n")
    pressure = queue_pressure(path, thresholds=pressure_thresholds)
    return {"staging_pressure": pressure}


def concept_findings_to_edges(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("job") != "concept_edges":
            continue
        edges.append(
            {
                "src": finding.get("src"),
                "dst": finding.get("dst"),
                "edge_type": finding.get("edge_type") or "related",
                "confidence": finding.get("confidence"),
                "why": finding.get("why") or finding.get("summary") or finding.get("title"),
                "source_refs": finding.get("source_refs") or [],
            }
        )
    return edges
