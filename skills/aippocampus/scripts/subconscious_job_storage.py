#!/usr/bin/env python3
"""Append-only storage helpers for subconscious job findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampuslib import now_utc
from subconscious_job_circuits import PROMPT_VERSION


def append_job_findings(
    path: Path,
    findings: list[dict[str, Any]],
    *,
    model: str,
    batch_id: str,
    usage: dict[str, Any],
    source: str = "deepseek_subconscious_jobs",
    model_route: dict[str, Any] | None = None,
) -> None:
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
                "model_route": model_route or {},
                "usage": usage or {},
                **payload,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


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
