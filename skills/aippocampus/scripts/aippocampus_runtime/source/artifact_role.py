"""Shared artifact-role demotion for foreground recall/search ranking."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

VALIDATION_ARTIFACT_MARKERS = (
    "<goal_context>",
    "<objective>",
    "<untrusted_",
    "active thread goal",
    "goal objective",
    "user-provided data",
    "higher-priority instructions",
    "system message",
    "developer message",
    "developer instructions",
    "AGENTS.md instructions",
    "strict acceptance",
    "acceptance failed",
    "acceptance criteria",
    "closeout",
    "fixed in https://github.com",
    "pull/",
    "issuecomment",
    "foreground_action",
    "opened_anchor_hits",
    "anchor hits",
    "source_ref_digest",
    "matched_cue_anchors",
    "recall_selector",
    "request_index",
    "agent recall",
    "agent deepen",
    "aippocampus agent recall",
    "aippocampus agent deepen",
    "readiness",
    "dogfood",
    "fixture",
    "control-only",
    "control only",
    "validation report",
    "regression probe",
    "验收没通过",
    "验收失败",
    "关闭 issue",
    "验证报告",
)

ARTIFACT_INTENT_MARKERS = (
    "acceptance",
    "closeout",
    "fixture",
    "readiness",
    "regression",
    "validation",
    "issue",
    "pr",
    "test",
    "report",
    "验收",
    "验证",
    "测试",
    "报告",
)


def _marker_hits(text: str, markers: Iterable[str]) -> list[str]:
    haystack = str(text or "").casefold()
    hits: list[str] = []
    for marker in markers:
        if marker.casefold() in haystack and marker not in hits:
            hits.append(marker)
    return hits


def query_requests_artifact_role(query_text: str) -> bool:
    """Return true when artifact/control material is probably the target."""

    return bool(_marker_hits(query_text, ARTIFACT_INTENT_MARKERS))


def artifact_role_profile(
    *,
    text: str,
    query_text: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify source snippets that repeat a cue as validation/control artifacts.

    The classifier is deliberately small and shared. It should demote fixture,
    validation, and closeout echoes when a user asks for a live historical/product
    source, while leaving those artifacts searchable when the query explicitly
    asks for validation, tests, issue closeout, or reports.
    """

    meta = metadata or {}
    haystack = " ".join(
        str(value or "")
        for value in (
            text,
            meta.get("phase"),
            meta.get("role"),
            " ".join(str(label) for label in meta.get("scope_labels") or []),
            " ".join(str(label) for label in meta.get("semantic_scope_labels") or []),
        )
    )
    hits = _marker_hits(haystack, VALIDATION_ARTIFACT_MARKERS)
    explicit_artifact_query = query_requests_artifact_role(query_text)
    demote = bool(hits) and not explicit_artifact_query
    control_hits = [
        marker
        for marker in hits
        if marker
        in {
            "<goal_context>",
            "<objective>",
            "<untrusted_",
            "active thread goal",
            "goal objective",
            "user-provided data",
            "higher-priority instructions",
            "system message",
            "developer message",
            "developer instructions",
            "AGENTS.md instructions",
        }
    ]
    role = (
        "control_or_goal_context_artifact"
        if control_hits
        else "validation_or_fixture_artifact"
        if hits
        else "topic_candidate"
    )
    return {
        key: value
        for key, value in {
            "role": role,
            "demote": demote,
            "topic_bearing": not demote,
            "reason": "artifact_marker_match" if hits else "",
            "matched_markers": hits[:6],
            "query_explicitly_requests_artifact": explicit_artifact_query,
        }.items()
        if value not in (None, "", [], {})
    }


def match_is_demoted_artifact(match: Mapping[str, Any]) -> bool:
    raw = match.get("artifact_role")
    profile = raw if isinstance(raw, Mapping) else {}
    return bool(profile.get("demote") or match.get("artifact_demoted"))


__all__ = [
    "artifact_role_profile",
    "match_is_demoted_artifact",
    "query_requests_artifact_role",
]
