"""Current clean-source candidates for the Associative Path Walker."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.recall.apw_anchor_coverage import (
    low_actual_anchor_coverage_reason,
    matched_terms_from_text,
    query_anchor_terms,
    source_anchor_gate,
)
from aippocampus_runtime.recall.query_policy import unique_preserve
from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir
from aippocampus_runtime.source.search import process_noise_reason
from aippocampus_runtime.source.search_core import iter_clean_messages, score_message
from aippocampus_runtime.source.search_terms import search_query_terms

MAX_CLEAN_SOURCE_SCAN_ROWS = 2500

PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}
CONTROL_QUERY_MARKERS = (
    "goal_context",
    "<goal_context",
    "goal context",
    "thread_state",
    "<thread_state",
    "thread control",
    "control message",
    "compaction",
    "commentary",
    "developer message",
    "system message",
    "控制消息",
    "线程控制",
    "目标上下文",
    "压缩上下文",
)
CONTROL_SOURCE_CLASSES = {
    "audit_or_commentary_source",
    "operator_control",
    "control_only",
    "thread_control",
    "goal_context",
}
CONTROL_PHASES = {"commentary", "analysis", "tool", "debug"}
CONTROL_ROLES = {"system", "developer", "tool", "operator"}
TASK_ECHO_MARKERS = (
    "issue",
    "issues",
    "pr",
    "ci",
    "test",
    "tests",
    "agent",
    "review",
    "verify",
    "continue",
    "next step",
    "next stage",
    "done",
    "finished",
    "closeout",
    "验收",
    "继续",
    "开 issue",
    "开issues",
    "提 issue",
    "提issues",
    "下一步",
    "下一阶段",
    "完成了",
    "修 issue",
    "关 issue",
)
VALIDATION_REPORT_MARKERS = (
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
    "验收没通过",
    "验收失败",
    "关闭 issue",
)
def _compact(value: Any, limit: int = 120) -> str:
    sanitized, _ = core.sanitize_external_model_text(str(value or ""))
    return core.compact_text(sanitized, limit)


def _component(name: str, *, status: str, row_count: int, malformed_count: int = 0) -> dict[str, Any]:
    result = {
        "component": name,
        "status": status,
        "row_count": int(row_count),
        "malformed_row_count": int(malformed_count),
        "authority": "navigation_only_not_source_truth",
    }
    if status == "missing":
        result["next_action"] = "continue without this sidecar or pass an explicit path for local diagnostics"
    return result


def _clean_source_root(cwd: str | Path | None, clean_source_dir: str | Path | None) -> Path:
    return resolve_clean_source_dir(cwd, clean_source_dir)


def _message_scope_bucket(message: Mapping[str, Any]) -> str:
    labels = [
        str(label).strip().casefold()
        for value in (
            message.get("scope_labels"),
            message.get("semantic_scope_labels"),
            message.get("privacy_partition"),
            message.get("privacy_domain"),
            message.get("scope_bucket"),
        )
        for label in (value if isinstance(value, Sequence) and not isinstance(value, str) else [value])
        if str(label or "").strip()
    ]
    if any(label in PRIVATE_BUCKETS for label in labels):
        return "user_private"
    if labels:
        return _compact(labels[0], 80)
    return "project"


def _query_explicitly_targets_control_context(query: str) -> bool:
    raw = str(query or "").casefold()
    return any(marker in raw for marker in CONTROL_QUERY_MARKERS)


def _message_metadata_values(message: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "source_use_class",
        "phase",
        "role",
        "kind",
        "type",
        "category",
        "scope_bucket",
        "source_category",
    ):
        value = message.get(key)
        if value not in (None, "", []):
            values.append(str(value))
    for key in ("scope_labels", "semantic_scope_labels", "labels", "tags"):
        value = message.get(key)
        rows = value if isinstance(value, Sequence) and not isinstance(value, str) else [value]
        values.extend(str(item) for item in rows if str(item or "").strip())
    return values


def _control_message_reason(message: Mapping[str, Any], text: str) -> str:
    """Classify clean-source plumbing that should not become foreground APW memory.

    These rows remain valid audit/source material; this filter only keeps
    ordinary APW continuity recall from binding a polished foreground action to
    lifecycle/control scaffolding. Explicit control-context queries bypass the
    filter in `clean_source_candidate_rows`.
    """

    snippet = str(text or "").lstrip().casefold()
    if snippet.startswith("<goal_context") or snippet.startswith("&lt;goal_context"):
        return "goal_context_candidate_filtered"
    if snippet.startswith("<thread_state") or snippet.startswith("&lt;thread_state"):
        return "control_source_filtered_from_foreground_apw"
    if process_noise_reason(text):
        return "control_source_filtered_from_foreground_apw"
    source_class = str(message.get("source_use_class") or "").strip().casefold()
    if source_class in CONTROL_SOURCE_CLASSES:
        if source_class == "audit_or_commentary_source":
            return "commentary_only_candidate_filtered"
        if source_class == "goal_context":
            return "goal_context_candidate_filtered"
        return "control_source_filtered_from_foreground_apw"
    phase = str(message.get("phase") or "").strip().casefold()
    role = str(message.get("role") or "").strip().casefold()
    if phase in CONTROL_PHASES:
        return "commentary_only_candidate_filtered"
    if role in CONTROL_ROLES:
        return "control_source_filtered_from_foreground_apw"
    metadata = " ".join(_message_metadata_values(message)).casefold()
    if any(marker in metadata for marker in ("goal_context", "thread_state", "control", "operator", "compaction")):
        return "control_source_filtered_from_foreground_apw"
    return ""


def _task_echo_reason(
    message: Mapping[str, Any],
    text: str,
    *,
    matched_terms: Sequence[str],
    anchor_terms: Sequence[str],
) -> str:
    """Filter same-thread work-management chatter from foreground APW recall.

    A recent user/assistant instruction like "continue opening issues" is valid
    source, but it is usually not the old route a continuity cue is trying to
    reopen. Keep it out of foreground APW only when it looks like task
    management and does not carry enough of the advertised cue anchors. Detail
    and explicit control/source queries can still inspect these rows.
    """

    haystack = " ".join([str(text or ""), " ".join(_message_metadata_values(message))]).casefold()
    marker_count = sum(1 for marker in TASK_ECHO_MARKERS if marker in haystack)
    if marker_count <= 0:
        return ""
    anchors = [str(term).strip() for term in anchor_terms if str(term).strip()]
    matched = [str(term).strip() for term in matched_terms if str(term).strip()]
    if not anchors:
        return ""
    required = min(3, max(2, (len(anchors) + 1) // 2))
    coverage = len(set(term.casefold() for term in matched)) / max(1, len(set(term.casefold() for term in anchors)))
    if len(matched) >= required or coverage >= 0.5:
        return ""
    return "same_thread_task_echo_no_anchor"


def _self_referential_validation_reason(
    message: Mapping[str, Any],
    text: str,
    *,
    matched_terms: Sequence[str],
    anchor_terms: Sequence[str],
) -> str:
    """Demote command replay and validation chatter from foreground APW routes.

    These rows can be valuable operator diagnostics, but they are a bad source
    route for the user's remembered topic: the cue anchors often appear only
    because a previous acceptance report pasted the command and its expected
    anchors. Keep them searchable/auditable while preventing APW from claiming a
    source-open route that merely replays its own validation history.
    """

    haystack = " ".join([str(text or ""), " ".join(_message_metadata_values(message))]).casefold()
    marker_count = sum(1 for marker in VALIDATION_REPORT_MARKERS if marker in haystack)
    if marker_count < 2:
        return ""
    anchors = {str(term).strip().casefold() for term in anchor_terms if str(term).strip()}
    matched = {str(term).strip().casefold() for term in matched_terms if str(term).strip()}
    if not anchors or len(matched & anchors) < min(2, len(anchors)):
        return ""
    command_replay = (
        ("agent recall" in haystack or "aippocampus agent recall" in haystack)
        and ("agent deepen" in haystack or "aippocampus agent deepen" in haystack)
    )
    source_identity_replay = any(
        marker in haystack
        for marker in (
            "opened_anchor_hits",
            "matched_cue_anchors",
            "source_ref_digest",
            "foreground_action",
            "recall_selector",
        )
    )
    if command_replay or source_identity_replay:
        return "self_referential_validation_report_demoted"
    return ""


def _source_ref_from_current_clean_message(message: Mapping[str, Any]) -> dict[str, Any]:
    # Current clean-source refs deliberately omit thread_key. In the shared
    # deepen path, a thread_key means "look this up in the registry"; omitting it
    # keeps the reopen scoped to the caller's current clean-source directory.
    ref = {
        "source_id": message.get("source_id") or message.get("source_ref"),
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "line": message.get("line") or message.get("source_line"),
    }
    return {key: value for key, value in ref.items() if value not in (None, "", [])}


def clean_source_candidate_rows(
    *,
    query: str,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    limit: int = 8,
    max_scan_rows: int = MAX_CLEAN_SOURCE_SCAN_ROWS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive APW navigation candidates from the current clean-source surface."""

    source_dir = _clean_source_root(cwd, clean_source_dir)
    messages_path = source_dir / "messages.jsonl"
    if not messages_path.is_file():
        return [], _component("current_clean_source_candidates", status="missing", row_count=0)
    anchor_terms = query_anchor_terms(query)
    if not anchor_terms:
        return [], _component("current_clean_source_candidates", status="needs_query", row_count=0)
    search_terms = search_query_terms([query])
    explicit_control_query = _query_explicitly_targets_control_context(query)
    try:
        messages = iter_clean_messages(messages_path)
    except (OSError, UnicodeError):
        return [], _component("current_clean_source_candidates", status="unreadable", row_count=0)
    rows: list[tuple[float, int, dict[str, Any]]] = []
    control_reason_counts: Counter[str] = Counter()
    control_allowed_count = 0
    task_echo_filtered_count = 0
    self_referential_validation_filtered_count = 0
    low_actual_anchor_filtered_count = 0
    for ordinal, message in enumerate(messages[: max(0, int(max_scan_rows or 0))], start=1):
        text = str(message.get("text") or "")
        score = score_message(message, search_terms)
        if score <= 0:
            continue
        matched_terms = matched_terms_from_text(text, anchor_terms)
        if not matched_terms:
            matched_terms = matched_terms_from_text(text, search_terms)
        if not matched_terms:
            continue
        control_reason = _control_message_reason(message, text)
        if control_reason and not explicit_control_query:
            control_reason_counts[control_reason] += 1
            continue
        if control_reason:
            control_allowed_count += 1
        task_echo_reason = _task_echo_reason(
            message,
            text,
            matched_terms=matched_terms,
            anchor_terms=anchor_terms,
        )
        if task_echo_reason and not explicit_control_query:
            task_echo_filtered_count += 1
            continue
        validation_reason = _self_referential_validation_reason(
            message,
            text,
            matched_terms=matched_terms,
            anchor_terms=anchor_terms,
        )
        if validation_reason and not explicit_control_query:
            control_reason_counts[validation_reason] += 1
            self_referential_validation_filtered_count += 1
            continue
        low_anchor_reason = low_actual_anchor_coverage_reason(
            matched_terms=matched_terms,
            anchor_terms=anchor_terms,
        )
        if low_anchor_reason:
            control_reason_counts[low_anchor_reason] += 1
            low_actual_anchor_filtered_count += 1
            continue
        ref = _source_ref_from_current_clean_message(message)
        if not ref:
            continue
        route_id = _compact(
            message.get("message_id")
            or message.get("id")
            or message.get("turn_id")
            or f"line:{message.get('source_line') or ordinal}",
            100,
        )
        route_terms = unique_preserve(matched_terms, limit=12)
        reason_codes = ["control_source_explicitly_requested"] if control_reason else []
        rows.append(
            (
                float(score),
                ordinal,
                {
                    "route_id": f"current-clean-source:{route_id}",
                    "candidate_id": f"current-clean-source:{route_id}",
                    "route_terms": route_terms,
                    "query_anchor_terms": unique_preserve(anchor_terms, limit=12),
                    "actual_source_matched_terms": route_terms,
                    "source_anchor_gate": source_anchor_gate(
                        matched_terms=matched_terms,
                        anchor_terms=anchor_terms,
                    ),
                    "route_label": "APW source route: " + " / ".join(matched_terms[:3]),
                    "source_refs": [ref],
                    "scope_bucket": _message_scope_bucket(message),
                    "freshness": _compact(message.get("freshness") or message.get("status") or "current", 80),
                    "source": "current_clean_source",
                    "candidate_source_kind": "current_clean_source",
                    "source_shape_completeness": "complete",
                    "source_use_class": message.get("source_use_class"),
                    "reason_codes": reason_codes,
                },
            )
        )
    rows.sort(key=lambda item: (-item[0], item[1]))
    candidates = [row for _, _, row in rows[: max(1, int(limit or 1))]]
    status = "loaded" if candidates else "loaded_no_matches"
    component = _component(
        "current_clean_source_candidates",
        status=status,
        row_count=len(candidates),
    )
    total_filtered = sum(control_reason_counts.values())
    if (
        total_filtered
        or control_allowed_count
        or task_echo_filtered_count
        or self_referential_validation_filtered_count
        or low_actual_anchor_filtered_count
    ):
        component.update(
            {
                "control_source_filtered_count": total_filtered,
                "control_source_demoted_count": 0,
                "goal_context_filtered_count": control_reason_counts.get(
                    "goal_context_candidate_filtered",
                    0,
                ),
                "commentary_only_filtered_count": control_reason_counts.get(
                    "commentary_only_candidate_filtered",
                    0,
                ),
                "control_source_explicitly_allowed_count": control_allowed_count,
                "same_thread_task_echo_filtered_count": task_echo_filtered_count,
                "self_referential_validation_report_demoted_count": (
                    self_referential_validation_filtered_count
                ),
                "low_actual_source_anchor_coverage_filtered_count": (
                    low_actual_anchor_filtered_count
                ),
            }
        )
    if len(messages) > max_scan_rows:
        component["scan_capped_at"] = int(max_scan_rows)
    return candidates, component


def has_clean_source_candidate_input(
    *,
    query: str,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
) -> bool:
    if clean_source_dir is None:
        return False
    candidates, _component_report = clean_source_candidate_rows(
        query=query,
        cwd=cwd,
        clean_source_dir=clean_source_dir,
        limit=1,
    )
    return bool(candidates)
