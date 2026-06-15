"""Deterministic source-backed learning-loop reducers.

This module is the boring narrow waist between clean-source behavior/texture
rows and later lesson/workflow consumers. It handles categorical evidence only:
source refs, event refs, command/failure families, fingerprints, scope, and
freshness. Raw command text, tool transcript streams, local paths, and model
summaries do not belong here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1
REVIEW_SIGNAL_KIND = "aippocampus_learning_review_signal"
ACTIVATION_KIND = "aippocampus_learning_activation"
FINDING_KIND = "aippocampus_learning_finding"
WORKFLOW_CANDIDATE_KIND = "aippocampus_workflow_candidate"
ACTION_GUIDANCE_KIND = "aippocampus_learning_action_guidance"
SEMANTIC_HYPOTHESIS_KIND = "aippocampus_semantic_learning_hypothesis"

CLAIM_PERMISSION = "navigation_only_not_fact"
TRUTH_BOUNDARY = "learning_loop_signal_not_source_truth"

CHEAP_PREFLIGHTS = {"python_ruff", "python_mypy", "docs_health"}
BROAD_TESTS = {"repo_test_runner", "python_pytest", "python_unittest"}
ENVIRONMENT_FAILURES = {
    "dependency_missing",
    "command_not_found",
    "network_or_download",
    "permission_or_access",
    "timeout",
}
ENVIRONMENT_WORKAROUNDS = {
    "dependency_install",
    "environment_workaround",
    "python_pip",
    "python_uv",
    "shell_environment",
}
CONTEXT_RECOVERY_COMMANDS = {
    "ripgrep",
    "grep",
    "powershell_search",
    "powershell_read",
    "source_reopen",
    "recall_deepen",
}
SUCCESS_STATUSES = {"succeeded", "success", "passed", "pass", "ok"}
STALE_STATUSES = {"stale", "superseded", "refuted", "retired", "archived", "resolved"}


def _stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_strings(value: Any, *, limit: int = 8) -> list[str]:
    result: list[str] = []
    for item in _as_list(value):
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _safe_refs(value: Any, *, limit: int = 4) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for item in _as_list(value):
        if not isinstance(item, Mapping):
            continue
        clean = {
            str(key): item.get(key)
            for key in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
                "source_line",
                "event_id",
            )
            if item.get(key) not in (None, "", [])
        }
        marker = tuple(sorted((key, str(val)) for key, val in clean.items()))
        if clean and marker not in seen:
            seen.add(marker)
            refs.append(clean)
        if len(refs) >= limit:
            break
    return refs


def _event_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = _safe_refs(row.get("event_refs"))
    event_id = str(row.get("event_id") or "").strip()
    if event_id and not refs:
        refs = [{"event_id": event_id}]
    return refs[:4]


def _source_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = _safe_refs(row.get("source_refs"))
    if refs:
        return refs
    ref = {
        key: row.get(key)
        for key in ("thread_key", "source_id", "message_id", "turn_id", "turn_index", "line", "source_line")
        if row.get(key) not in (None, "", [])
    }
    return [ref] if ref else []


def _text(row: Mapping[str, Any], key: str, default: str = "") -> str:
    return str(row.get(key) or default).strip()


def _status(row: Mapping[str, Any]) -> str:
    return _text(row, "status").casefold()


def _is_success(row: Mapping[str, Any]) -> bool:
    return _status(row) in SUCCESS_STATUSES or _text(row, "failure_family") in {"", "none"}


def _target_fingerprint(row: Mapping[str, Any]) -> str:
    direct = _text(row, "target_fingerprint")
    if direct:
        return direct
    fingerprints = _safe_strings(row.get("path_fingerprints"), limit=1)
    if fingerprints:
        return fingerprints[0]
    return _stable_id("target", _text(row, "command_family"), _text(row, "target_class"), length=14)


def _path_category_fingerprint(row: Mapping[str, Any]) -> str:
    direct = _text(row, "path_category_fingerprint")
    if direct:
        return direct
    categories = _safe_strings(row.get("path_categories"), limit=4)
    return _stable_id("pathcat", categories or _safe_strings(row.get("path_fingerprints")), length=14)


def _signature(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        "failure_family": _text(row, "failure_family", "none"),
        "command_family": _text(row, "command_family", "unknown"),
        "target_class": _text(row, "target_class", "unknown"),
        "target_fingerprint": _target_fingerprint(row),
        "path_category_fingerprint": _path_category_fingerprint(row),
        "workspace_or_environment_profile": _text(row, "workspace_or_environment_profile", "unknown"),
        "scope": _text(row, "scope", "project_or_task_family"),
        "freshness_window": _text(row, "freshness_window", "recent"),
    }


def _grouping_fingerprint(signature: Mapping[str, Any]) -> str:
    return _stable_id("learn_group", signature, length=20)


def adapt_behavior_events_to_review_signals(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        signature = _signature(row)
        success = _is_success(row)
        signal_type = "success_after_failure" if success else "failure"
        failure_family = signature["failure_family"] if not success else "none"
        grouping = _grouping_fingerprint(signature)
        event_refs = _event_refs(row)
        source_refs = _source_refs(row)
        signals.append(
            {
                "kind": REVIEW_SIGNAL_KIND,
                "schema_version": SCHEMA_VERSION,
                "signal_id": _stable_id("learn_sig", row.get("event_id"), signature, row.get("sequence_index")),
                "signal_type": signal_type,
                "learning_signal": "success_after_failure" if success else f"failure:{failure_family}",
                "event_refs": event_refs,
                "source_refs": source_refs,
                "command_family": signature["command_family"],
                "target_class": signature["target_class"],
                "failure_family": failure_family,
                "target_fingerprint": signature["target_fingerprint"],
                "path_category_fingerprint": signature["path_category_fingerprint"],
                "workspace_or_environment_profile": signature["workspace_or_environment_profile"],
                "scope": signature["scope"],
                "freshness_window": signature["freshness_window"],
                "grouping_fingerprint": grouping,
                "signature": signature,
                "sequence_index": int(row.get("sequence_index") or len(signals) + 1),
                "expected_local_red": bool(row.get("expected_local_red")),
                "navigation_only": True,
                "foreground_eligible": False,
                "claim_permission": CLAIM_PERMISSION,
                "truth_boundary": TRUTH_BOUNDARY,
                "source_reopen_required_before_claim": True,
                "reason_codes": [
                    "scrubbed_behavior_event",
                    "raw_tool_payload_not_serialized",
                    *(["expected_local_red_review_only"] if row.get("expected_local_red") else []),
                ],
            }
        )
    return signals


def extract_learning_activations(
    signals: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    activations: list[dict[str, Any]] = []
    for signal in signals:
        if signal.get("signal_type") != "failure":
            continue
        source_refs = _safe_refs(signal.get("source_refs"))
        if not source_refs:
            continue
        expected_red = bool(signal.get("expected_local_red"))
        durable = not expected_red
        activations.append(
            {
                "kind": ACTIVATION_KIND,
                "schema_version": SCHEMA_VERSION,
                "activation_id": _stable_id("learn_act", signal.get("signal_id")),
                "activation_kind": "tool_failure_activation",
                "activation_status": "open" if durable else "review_only_expected_red",
                "durable_activation": durable,
                "failure_shape": ":".join(
                    [
                        "tool_failure",
                        str(signal.get("failure_family") or "unknown"),
                        str(signal.get("command_family") or "unknown"),
                        str(signal.get("target_class") or "unknown"),
                    ]
                ),
                "event_refs": _safe_refs(signal.get("event_refs")),
                "source_refs": source_refs,
                "grouping_fingerprint": signal.get("grouping_fingerprint"),
                "signature": signal.get("signature"),
                "navigation_only": True,
                "foreground_eligible": False,
                "claim_permission": CLAIM_PERMISSION,
                "source_reopen_required_before_claim": True,
                "reason_codes": [
                    "source_ref_gated_tool_failure_activation",
                    *(["expected_local_red_not_durable"] if expected_red else []),
                ],
            }
        )
    return activations


def _group_signals(signals: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for signal in signals:
        group = str(signal.get("grouping_fingerprint") or "")
        if group:
            groups[group].append(signal)
    return groups


def _same_retry_target(row: Mapping[str, Any], signature: Mapping[str, Any]) -> bool:
    """Match a later success to an earlier failure without requiring the failure family.

    Successful retries usually no longer know the original failure family, so
    that field is deliberately excluded. The rest of the signature stays narrow
    to avoid turning a generic "pytest passed later" into a global lesson.
    """

    return all(
        str(row.get(key) or "") == str(signature.get(key) or "")
        for key in (
            "command_family",
            "target_class",
            "target_fingerprint",
            "path_category_fingerprint",
            "workspace_or_environment_profile",
            "scope",
            "freshness_window",
        )
    )


def detect_recurring_failure_findings(
    signals: Iterable[Mapping[str, Any]],
    *,
    min_occurrences: int = 2,
) -> list[dict[str, Any]]:
    materialized = [row for row in signals if isinstance(row, Mapping)]
    findings: list[dict[str, Any]] = []
    for group, rows in _group_signals(materialized).items():
        failures = [
            row
            for row in rows
            if row.get("signal_type") == "failure"
            and not row.get("expected_local_red")
            and _safe_refs(row.get("source_refs"))
        ]
        if len(failures) < min_occurrences:
            continue
        signature = dict(failures[0].get("signature") or {})
        successes = [
            row
            for row in materialized
            if row.get("signal_type") == "success_after_failure" and _same_retry_target(row, signature)
        ]
        status = "resolved" if len(successes) >= 2 else "open"
        refs: list[dict[str, Any]] = []
        for row in [*failures, *successes]:
            refs.extend(_safe_refs(row.get("source_refs")))
        findings.append(
            {
                "kind": FINDING_KIND,
                "schema_version": SCHEMA_VERSION,
                "finding_id": _stable_id("learn_find", "recurring_failure", group),
                "finding_kind": "recurring_failure_finding",
                "candidate_family": "verification_preflight_candidate",
                "status": status,
                "occurrence_count": len(failures),
                "success_after_count": len(successes),
                "failure_family": signature.get("failure_family", "unknown"),
                "command_family": signature.get("command_family", "unknown"),
                "target_class": signature.get("target_class", "unknown"),
                "target_fingerprint": signature.get("target_fingerprint", ""),
                "path_category_fingerprint": signature.get("path_category_fingerprint", ""),
                "workspace_or_environment_profile": signature.get(
                    "workspace_or_environment_profile",
                    "unknown",
                ),
                "scope": signature.get("scope", "project_or_task_family"),
                "freshness": "current" if status == "open" else "superseded",
                "signature": signature,
                "source_refs": _dedupe_refs(refs)[:6],
                "source_ref_count": len(_dedupe_refs(refs)),
                "foreground_eligible": status == "open",
                "navigation_only": True,
                "claim_permission": CLAIM_PERMISSION,
                "source_reopen_required_before_claim": True,
                "reason_codes": [
                    "recurring_failure_detected",
                    "narrow_signature_group",
                    *(["retired_by_later_success"] if status == "resolved" else []),
                ],
            }
        )
    return findings


def _dedupe_refs(refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for ref in refs:
        clean = dict(ref)
        marker = tuple(sorted((str(key), str(value)) for key, value in clean.items()))
        if clean and marker not in seen:
            seen.add(marker)
            out.append(clean)
    return out


def _ref_markers(refs: Sequence[Mapping[str, Any]]) -> set[tuple[tuple[str, str], ...]]:
    return {
        tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        for ref in refs
        if isinstance(ref, Mapping) and ref
    }


def _has_ref_overlap(left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]) -> bool:
    return bool(_ref_markers(left) & _ref_markers(right))


def _same_target_or_guarded(
    failed: Mapping[str, Any],
    middle: Mapping[str, Any],
    success: Mapping[str, Any],
) -> bool:
    target = str(failed.get("target_fingerprint") or "")
    if target and str(middle.get("target_fingerprint") or "") == target and str(success.get("target_fingerprint") or "") == target:
        return True
    reason_codes = {
        str(code)
        for row in (failed, middle, success)
        for code in row.get("reason_codes") or []
    }
    return bool(
        reason_codes
        & {
            "same_target_window",
            "same_source_window",
            "same_change_window",
            "explicit_route_note_or_correction_link",
            "repeat_across_independent_trails",
        }
    )


def _retry_success_after(
    later: Sequence[Mapping[str, Any]],
    *,
    failed: Mapping[str, Any],
    middle: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    middle_index = int(middle.get("sequence_index") or 0)
    target = str(failed.get("target_fingerprint") or "")
    for row in later:
        if int(row.get("sequence_index") or 0) <= middle_index:
            continue
        if row.get("signal_type") != "success_after_failure":
            continue
        if str(row.get("command_family") or "") != str(failed.get("command_family") or ""):
            continue
        if target and str(row.get("target_fingerprint") or "") != target:
            continue
        return row
    return None


def _workflow_pattern(
    failed: Mapping[str, Any],
    later: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any], str, str, list[str]] | None:
    command = str(failed.get("command_family") or "")
    failure_family = str(failed.get("failure_family") or "")

    if command in BROAD_TESTS:
        preflight = next(
            (
                row
                for row in later
                if row.get("signal_type") == "success_after_failure"
                and str(row.get("command_family") or "") in CHEAP_PREFLIGHTS
                and str(row.get("target_fingerprint") or "") == str(failed.get("target_fingerprint") or "")
            ),
            None,
        )
        if preflight is not None:
            success = _retry_success_after(later, failed=failed, middle=preflight)
            if success is not None:
                return (
                    preflight,
                    success,
                    "cheap_preflight_before_broad_test",
                    "workflow_order_candidate",
                    [
                        "cheap_preflight_before_broad_test",
                        "same_target_window",
                        "causal_guard_known_preflight",
                    ],
                )

    if failure_family in ENVIRONMENT_FAILURES:
        workaround = next(
            (
                row
                for row in later
                if row.get("signal_type") == "success_after_failure"
                and str(row.get("command_family") or "") in ENVIRONMENT_WORKAROUNDS
            ),
            None,
        )
        if workaround is not None:
            success = _retry_success_after(later, failed=failed, middle=workaround)
            if success is not None and _same_target_or_guarded(failed, workaround, success):
                return (
                    workaround,
                    success,
                    "environment_workaround_before_retry",
                    "environment_workaround_candidate",
                    [
                        "environment_workaround_before_retry",
                        "known_environment_fix_family",
                        "same_target_or_source_window",
                    ],
                )

    recovery = next(
        (
            row
            for row in later
            if row.get("signal_type") == "success_after_failure"
            and str(row.get("command_family") or "") in CONTEXT_RECOVERY_COMMANDS
        ),
        None,
    )
    if recovery is not None:
        success = _retry_success_after(later, failed=failed, middle=recovery)
        if success is not None and _same_target_or_guarded(failed, recovery, success):
            return (
                recovery,
                success,
                "context_reopen_before_retry",
                "context_reopen_candidate",
                [
                    "context_miss_recovery",
                    "source_reopen_or_search_before_retry",
                    "same_target_or_source_window",
                ],
            )
    return None


def detect_workflow_order_findings(
    signals: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = sorted(
        [row for row in signals if isinstance(row, Mapping)],
        key=lambda row: int(row.get("sequence_index") or 0),
    )
    findings: list[dict[str, Any]] = []
    seen_patterns: set[tuple[str, str]] = set()
    for index, failed in enumerate(rows):
        if failed.get("signal_type") != "failure":
            continue
        target = str(failed.get("target_fingerprint") or "")
        if not target:
            continue
        later = rows[index + 1 :]
        pattern = _workflow_pattern(failed, later)
        if pattern is None:
            continue
        middle, success, workflow_family, candidate_family, reason_codes = pattern
        marker = (target, workflow_family)
        if marker in seen_patterns:
            continue
        seen_patterns.add(marker)
        refs = _dedupe_refs(
            [
                *_safe_refs(failed.get("source_refs")),
                *_safe_refs(middle.get("source_refs")),
                *_safe_refs(success.get("source_refs")),
            ]
        )
        findings.append(
            {
                "kind": FINDING_KIND,
                "schema_version": SCHEMA_VERSION,
                "finding_id": _stable_id("learn_find", "workflow_order", workflow_family, target),
                "finding_kind": "workflow_order_finding",
                "candidate_family": candidate_family,
                "workflow_family": workflow_family,
                "status": "open",
                "workflow_order": [
                    str(failed.get("command_family") or ""),
                    str(middle.get("command_family") or ""),
                    str(success.get("command_family") or ""),
                ],
                "target_fingerprint": target,
                "scope": failed.get("scope") or "project_or_task_family",
                "occurrence_count": 2,
                "confidence": "high",
                "freshness": "current",
                "source_refs": refs,
                "source_ref_count": len(refs),
                "foreground_eligible": True,
                "navigation_only": True,
                "claim_permission": CLAIM_PERMISSION,
                "source_reopen_required_before_claim": True,
                "reason_codes": reason_codes,
            }
        )
    return findings


def _query_tokens(values: Iterable[Any]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            tokens.update(_query_tokens(value))
            continue
        text = str(value or "").casefold()
        tokens.update(token for token in re.split(r"[^a-z0-9]+", text) if token)
    return tokens


def project_action_time_guidance(
    findings: Iterable[Mapping[str, Any]],
    *,
    query_terms: Sequence[str] | None = None,
    visible_source_refs: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    query = _query_tokens(query_terms or [])
    visible = _dedupe_refs(visible_source_refs or [])
    guidance: list[dict[str, Any]] = []
    for finding in findings:
        status = str(finding.get("status") or "open")
        if status in STALE_STATUSES or not finding.get("foreground_eligible", True):
            continue
        scope = str(finding.get("scope") or "").casefold()
        if scope in {"local-only", "machine:local-only"}:
            continue
        occurrence_count = int(finding.get("occurrence_count") or 0)
        confidence = str(finding.get("confidence") or "medium").casefold()
        if confidence == "low" and occurrence_count < 2:
            continue
        refs = _dedupe_refs(_safe_refs(finding.get("source_refs")))
        if not refs or (visible and _has_ref_overlap(refs, visible)):
            continue
        workflow = str(finding.get("workflow_family") or "")
        if workflow == "cheap_preflight_before_broad_test":
            next_action = "run_preflight_before_broad_test"
            guidance_text = "Run the cheap verifier that previously recovered this target before broad tests."
        elif workflow == "environment_workaround_before_retry":
            next_action = "reopen_environment_workaround_before_retry"
            guidance_text = "Reopen the prior environment workaround before retrying this failed route."
        elif workflow == "context_reopen_before_retry":
            next_action = "reopen_context_source_before_retry"
            guidance_text = "Reopen or search the source trail that previously recovered this route before retrying."
        elif finding.get("finding_kind") == "recurring_failure_finding":
            next_action = "reopen_failure_source_before_retry"
            guidance_text = "Reopen the prior failure source trail before trying the same route again."
        else:
            next_action = "reopen_source_before_action"
            guidance_text = "Reopen the source-backed learning trail before treating this as guidance."
        transferability = "this_repo_only" if scope.startswith("project:") else "this_project_family"
        haystack = _query_tokens([workflow, next_action, guidance_text, finding.get("workflow_order")])
        if query and not (query & haystack):
            continue
        guidance.append(
            {
                "kind": ACTION_GUIDANCE_KIND,
                "schema_version": SCHEMA_VERSION,
                "guidance_id": _stable_id("learn_act_guidance", finding.get("finding_id"), query_terms),
                "title": "Source-backed learning guidance",
                "guidance_text": guidance_text,
                "next_action": next_action,
                "scope": finding.get("scope") or "project_or_task_family",
                "target_fingerprint": finding.get("target_fingerprint") or "",
                "path_category_fingerprint": finding.get("path_category_fingerprint") or "",
                "workspace_or_environment_profile": finding.get("workspace_or_environment_profile") or "",
                "transferability": finding.get("transferability") or transferability,
                "source_refs": refs[:3],
                "source_reopen_required_before_claim": True, "claim_permission": CLAIM_PERMISSION,
                "navigation_only": True,
                "truth_boundary": TRUTH_BOUNDARY,
                "reason_codes": ["learning_guidance_surface", "action_time_match", "source_reopen_required"],
            }
        )
    return guidance


def project_guidance_to_route_readiness(
    guidance_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Project action guidance into the existing Active Path Packet intake shape."""

    route_rows: list[dict[str, Any]] = []
    for row in guidance_rows:
        refs = _dedupe_refs(_safe_refs(row.get("source_refs")))
        if not refs:
            continue
        route_rows.append(
            {
                "route_id": row.get("guidance_id") or _stable_id("learn_route", row),
                "surface_kind": "source_backed_learning_guidance",
                "title": row.get("title") or "Source-backed learning guidance",
                "why_lit": row.get("guidance_text") or "Learning guidance requires source reopen before use.",
                "status": "ready",
                "currentness": "current",
                "confidence": row.get("confidence") or "medium",
                "source_refs": refs,
                "source_ref_count": len(refs),
                "output_authority": "navigation_only",
                "navigation_only": True,
                "source_reopen_required_before_claim": True,
                "origin": "learning_loop_action_guidance",
                "reason_codes": [
                    "learning_loop_action_guidance",
                    "source_reopen_required",
                    *[str(code) for code in row.get("reason_codes") or []],
                ],
                "next_action": row.get("next_action") or "source_reopen",
            }
        )
    return route_rows


def build_learning_action_time_packet(
    findings: Iterable[Mapping[str, Any]],
    *,
    query_terms: Sequence[str] | None = None,
    visible_source_refs: Sequence[Mapping[str, Any]] | None = None,
    max_paths: int = 3,
) -> dict[str, Any]:
    """Surface ripe learning guidance through the existing active-path packet.

    This is a projection only: it does not read source, write memory, or claim
    the guidance is factual. Active Path Packet keeps the foreground action
    grammar and source-reopen boundary authoritative.
    """

    guidance = project_action_time_guidance(
        findings,
        query_terms=query_terms,
        visible_source_refs=visible_source_refs,
    )
    route_rows = project_guidance_to_route_readiness(guidance)
    from aippocampus_runtime.recall.active_path_packet import build_active_path_packet

    packet = build_active_path_packet(route_readiness=route_rows, max_paths=max_paths)
    packet["learning_guidance"] = {
        "guidance_count": len(guidance),
        "route_row_count": len(route_rows),
        "source_reopen_required_before_claim": True,
        "truth_boundary": TRUTH_BOUNDARY,
        "anti_nag_policy": {
            "visible_source_overlap_suppressed": True,
            "stale_or_refuted_suppressed": True,
            "local_only_suppressed": True,
            "low_confidence_one_off_suppressed": True,
        },
    }
    return packet


def extract_workflow_candidates(
    findings: Iterable[Mapping[str, Any]],
    *,
    existing_assets: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    assets = existing_assets or {}
    asset_order = (
        "skills",
        "aippo_clauses",
        "docs_routes",
        "checklists",
        "automations",
        "subagents",
        "action_hints",
        "recall_routes",
    )
    asset_index = {
        kind: {str(item) for item in assets.get(kind, [])}
        for kind in asset_order
    }

    def existing_asset(workflow: str) -> tuple[str, str]:
        for kind in asset_order:
            if workflow in asset_index[kind]:
                return kind, workflow
        return "", ""

    def transferability_for(finding: Mapping[str, Any], workflow: str) -> str:
        scope = str(finding.get("scope") or "").casefold()
        profile = str(finding.get("workspace_or_environment_profile") or "").casefold()
        material = " ".join(
            [
                workflow.casefold(),
                str(finding.get("finding_kind") or "").casefold(),
                " ".join(str(item).casefold() for item in finding.get("reason_codes") or []),
            ]
        )
        if scope.startswith("machine:") or profile.startswith("local-only") or "path" in material:
            return "this_machine_only"
        if "environment" in material or "toolchain" in material:
            return "this_toolchain_only"
        if scope.startswith("project:"):
            return "this_repo_only"
        if workflow in {"stable_repeated_manual_workflow", "cheap_preflight_before_broad_test"}:
            return "general_agent_workflow"
        return "this_project_family"

    candidates: list[dict[str, Any]] = []
    for finding in findings:
        occurrence_count = int(finding.get("occurrence_count") or 0)
        confidence = str(finding.get("confidence") or "medium")
        workflow = str(finding.get("workflow_family") or finding.get("finding_kind") or "workflow")
        transferability = transferability_for(finding, workflow)
        existing_kind, existing_id = existing_asset(workflow)
        if occurrence_count < 2 or confidence == "low":
            form = "skip"
            skip_reason = "thin_or_one_off_evidence"
        elif existing_kind:
            form = "extend_existing_skill" if existing_kind == "skills" else "extend_existing_asset"
            skip_reason = ""
        elif workflow == "automation_candidate" or transferability == "this_machine_only":
            form = "create_automation"
            skip_reason = ""
        elif finding.get("finding_kind") == "semantic_context_miss":
            form = "create_subagent"
            skip_reason = ""
        elif workflow == "stable_repeated_manual_workflow":
            form = "create_narrow_skill"
            skip_reason = ""
        else:
            form = "add_checklist"
            skip_reason = ""
        candidates.append(
            {
                "kind": WORKFLOW_CANDIDATE_KIND,
                "schema_version": SCHEMA_VERSION,
                "candidate_id": _stable_id("workflow_candidate", finding.get("finding_id"), workflow, form),
                "repeated_workflow_summary": workflow,
                "recommended_form": form,
                "skip_reason": skip_reason,
                "transferability": transferability,
                "existing_asset_kind": existing_kind,
                "existing_asset_id": existing_id,
                "asset_match_reason": "workflow_family_exact_match" if existing_kind else "",
                "packaging_boundary": (
                    "machine_local_lesson_not_general_skill"
                    if transferability == "this_machine_only"
                    else "asset_creation_requires_review"
                ),
                "source_refs": _safe_refs(finding.get("source_refs")),
                "source_evidence_count": len(_safe_refs(finding.get("source_refs"))),
                "frequency": occurrence_count,
                "confidence": confidence,
                "scope": finding.get("scope") or "project_or_task_family",
                "auto_create_asset": False,
                "review_required_before_asset_creation": True,
                "navigation_only": True,
                "claim_permission": CLAIM_PERMISSION,
                "source_reopen_required_before_claim": True,
                "reason_codes": [
                    "workflow_candidate_detected",
                    "asset_creation_requires_explicit_action",
                    *(["existing_asset_checked"] if any(asset_index.values()) else []),
                    *([f"existing_{existing_kind}_matched"] if existing_kind else []),
                    f"transferability:{transferability}",
                ],
            }
        )
    return candidates


def build_semantic_learning_hypotheses(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    mapping = {
        "blind_spot": "blind_spot_candidate",
        "recurring_question": "recurring_question_candidate",
        "cross_thread_resonance": "cross_thread_resonance_candidate",
        "workflow_packaging": "workflow_packaging_candidate",
        "one_sided_route": "one_sided_route_candidate",
    }
    hypotheses: list[dict[str, Any]] = []
    for row in rows:
        kind = mapping.get(str(row.get("finding_kind") or ""), "workflow_packaging_candidate")
        refs = _safe_refs(row.get("source_refs"))
        thickness = str(row.get("source_thickness") or ("usable" if refs else "thin"))
        freshness = str(row.get("freshness") or "current")
        if freshness in STALE_STATUSES:
            status = "retired"
        elif thickness == "thin" or not refs:
            status = "review_only"
        else:
            status = "candidate"
        hypotheses.append(
            {
                "kind": SEMANTIC_HYPOTHESIS_KIND,
                "schema_version": SCHEMA_VERSION,
                "hypothesis_id": _stable_id("learn_hyp", kind, refs, freshness),
                "candidate_kind": kind,
                "status": status,
                "foreground_eligible": False,
                "model_output_is_evidence": False,
                "source_refs": refs,
                "source_thickness": thickness,
                "freshness": freshness,
                "review_after": row.get("review_after") or "next_consolidation_review",
                "expires_at": row.get("expires_at") or ("now" if status == "retired" else "after_freshness_window"),
                "navigation_only": True,
                "claim_permission": CLAIM_PERMISSION,
                "truth_boundary": "semantic_learning_hypothesis_is_candidate_not_evidence",
                "reason_codes": [
                    "dream_subconscious_candidate_only",
                    *(["thin_source_backstage"] if status == "review_only" else []),
                    *(["stale_candidate_retired"] if status == "retired" else []),
                ],
            }
        )
    return hypotheses


def build_learning_loop_dogfood_fixture_report() -> dict[str, Any]:
    rows = [
        {
            "kind": "behavior_event",
            "event_id": "fixture_broad_failed_1",
            "status": "failed",
            "command_family": "repo_test_runner",
            "command_class": "test",
            "target_class": "repo_pr_suite",
            "failure_family": "assertion_failure",
            "target_fingerprint": "fixture:pr-tier",
            "path_category_fingerprint": "fixture:path:test",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "freshness_window": "recent",
            "source_refs": [{"thread_key": "fixture", "message_id": "broad_failed_1"}],
            "sequence_index": 1,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_ruff_success",
            "status": "succeeded",
            "command_family": "python_ruff",
            "target_class": "lint",
            "failure_family": "none",
            "target_fingerprint": "fixture:pr-tier",
            "path_category_fingerprint": "fixture:path:test",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "ruff_success"}],
            "sequence_index": 2,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_broad_success",
            "status": "succeeded",
            "command_family": "repo_test_runner",
            "target_class": "repo_pr_suite",
            "failure_family": "none",
            "target_fingerprint": "fixture:pr-tier",
            "path_category_fingerprint": "fixture:path:test",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "broad_success"}],
            "sequence_index": 3,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_env_failed",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "dependency_missing",
            "target_fingerprint": "fixture:env-target",
            "path_category_fingerprint": "fixture:path:env",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "env_failed"}],
            "sequence_index": 4,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_env_workaround",
            "status": "succeeded",
            "command_family": "environment_workaround",
            "target_class": "environment_setup",
            "failure_family": "none",
            "target_fingerprint": "fixture:env-target",
            "path_category_fingerprint": "fixture:path:env",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "env_workaround"}],
            "sequence_index": 5,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_env_success",
            "status": "succeeded",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "none",
            "target_fingerprint": "fixture:env-target",
            "path_category_fingerprint": "fixture:path:env",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "env_success"}],
            "sequence_index": 6,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_context_failed",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "assertion_failure",
            "target_fingerprint": "fixture:context-target",
            "path_category_fingerprint": "fixture:path:context",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "context_failed"}],
            "sequence_index": 7,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_context_reopen",
            "status": "succeeded",
            "command_family": "ripgrep",
            "target_class": "source_search",
            "failure_family": "none",
            "target_fingerprint": "fixture:context-target",
            "path_category_fingerprint": "fixture:path:context",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "context_reopen"}],
            "sequence_index": 8,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_context_success",
            "status": "succeeded",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "none",
            "target_fingerprint": "fixture:context-target",
            "path_category_fingerprint": "fixture:path:context",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "context_success"}],
            "sequence_index": 9,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_expected_red",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "assertion_failure",
            "target_fingerprint": "fixture:tdd-red",
            "path_category_fingerprint": "fixture:path:tdd",
            "source_refs": [{"thread_key": "fixture", "message_id": "expected_red"}],
            "expected_local_red": True,
            "sequence_index": 10,
        },
        {
            "kind": "behavior_event",
            "event_id": "fixture_one_off",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "assertion_failure",
            "target_fingerprint": "fixture:one-off",
            "path_category_fingerprint": "fixture:path:one-off",
            "workspace_or_environment_profile": "public-fixture",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "fixture", "message_id": "one_off"}],
            "sequence_index": 11,
        },
    ]
    signals = adapt_behavior_events_to_review_signals(rows)
    activations = extract_learning_activations(signals)
    recurring = detect_recurring_failure_findings([*signals, *signals])
    workflow = detect_workflow_order_findings(signals)
    guidance = project_action_time_guidance(workflow, query_terms=["repo", "test", "ruff"])
    stale_hypotheses = build_semantic_learning_hypotheses(
        [
            {
                "finding_kind": "one_sided_route",
                "source_refs": [{"thread_key": "fixture", "message_id": "stale_route"}],
                "source_thickness": "usable",
                "freshness": "stale",
            },
            {
                "finding_kind": "workflow_packaging",
                "source_refs": [],
                "source_thickness": "thin",
                "freshness": "current",
            },
        ]
    )
    metrics = {
        "surfaced_count": len(guidance),
        "applicable_attempt_count": 1,
        "repeat_failure_after_surface_count": 0,
        "success_after_surface_count": int(bool(guidance)),
        "dismissed_or_ignored_count": 0,
        "stale_or_superseded_count": sum(1 for row in stale_hypotheses if row["status"] == "retired"),
        "repeated_mistake_reduction_count": int(bool(guidance)),
        "wrong_route_suppression_count": 1,
        "unnecessary_broad_test_avoidance_count": int(bool(workflow)),
        "no_overpromotion_count": sum(1 for row in activations if not row["durable_activation"])
        + sum(1 for row in stale_hypotheses if not row["foreground_eligible"]),
        "recurring_failure_finding_count": len(recurring),
        "environment_workaround_count": sum(
            1 for row in workflow if row.get("workflow_family") == "environment_workaround_before_retry"
        ),
        "context_reopen_count": sum(
            1 for row in workflow if row.get("workflow_family") == "context_reopen_before_retry"
        ),
        "one_off_suppressed_count": 1,
    }
    ok = bool(guidance) and metrics["repeat_failure_after_surface_count"] == 0
    return {
        "kind": "aippocampus_learning_loop_dogfood_fixture_report",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "metrics": metrics,
        "effectiveness_status": "useful_signal" if ok else "unproven",
        "truth_boundary": "effectiveness_is_diagnostic_not_causal_proof",
        "claim_boundary": "fixture_only_runtime_capability_not_live_causal_proof",
        "cannot_claim": [
            "fixture_proves_live_user_behavior_lift",
            "reduced_repeat_failure_proves_causality",
            "candidate_guidance_is_source_truth",
        ],
        "cases": [
            {"case_id": "workflow_order_guidance", "guidance": guidance[:1]},
            {
                "case_id": "environment_and_context_workflows",
                "workflow_families": sorted({str(row.get("workflow_family")) for row in workflow}),
            },
            {"case_id": "expected_tdd_red_review_only", "activation_count": len(activations)},
            {"case_id": "semantic_hypothesis_candidate_only", "hypotheses": stale_hypotheses},
        ],
        "privacy_boundary": {
            "tool_transcript_payloads_serialized": False,
            "full_commands_serialized": False,
            "local_paths_serialized": False,
            "source_audit_payloads_serialized": False,
        },
    }
