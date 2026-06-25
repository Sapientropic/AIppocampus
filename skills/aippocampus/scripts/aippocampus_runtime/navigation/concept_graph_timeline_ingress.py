"""Project timeline ingress for the navigation concept graph."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation.concept_graph_term_quality import (
    ConceptTermQualityTracker,
    TermQualityContext,
)
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.source.io_kernel import load_json_dict

AddBidirectionalEdge = Callable[..., None]


def load_timeline_payload(path: Path) -> dict[str, Any]:
    return load_json_dict(path).data


def collect_timeline_edges(
    con: sqlite3.Connection,
    timeline_path: Path | None,
    *,
    term_quality: ConceptTermQualityTracker,
    add_bidirectional_edge: AddBidirectionalEdge,
) -> int:
    if not timeline_path or not timeline_path.exists():
        return 0
    timeline = load_timeline_payload(timeline_path)
    edge_count = 0
    for project in (timeline.get("projects") or {}).values():
        if not isinstance(project, dict):
            continue
        project_label = str(project.get("project_label") or "").strip()
        project_terms = term_quality.filter_terms(
            [project_label, *list(project.get("project_tags") or [])],
            TermQualityContext(
                ingress="timeline",
                static_anchor=True,
                source_backed=True,
                hit_count=1,
                thread_count=1,
            ),
            limit=8,
        )
        for turn in project.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            turn_terms = term_quality.filter_terms(
                list(turn.get("topic_terms") or []),
                TermQualityContext(
                    ingress="timeline",
                    source_backed=bool(turn.get("source_refs")),
                    hit_count=max(1, len(turn.get("source_refs") or [])),
                    thread_count=1 if turn.get("thread_key") else 0,
                ),
                limit=12,
            )
            topic_terms = unique_preserve(project_terms + turn_terms, limit=18)
            if len(topic_terms) < 2:
                continue
            source_thread_key = turn.get("thread_key")
            for idx, term in enumerate(topic_terms):
                for related in topic_terms[idx + 1 :]:
                    add_bidirectional_edge(
                        con,
                        term,
                        related,
                        edge_type="project_topic",
                        confidence=0.9,
                        status="staging",
                        evidence_count=1,
                        source_thread_key=source_thread_key,
                    )
                    edge_count += 2
    return edge_count


__all__ = ["collect_timeline_edges", "load_timeline_payload"]
