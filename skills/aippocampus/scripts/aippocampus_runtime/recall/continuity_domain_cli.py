#!/usr/bin/env python3
"""Operator CLI for explicit continuity-domain event writes.

Continuity domains are durable interpretation routes, so authoring stays an
explicit operator/agent action. Prompt hooks and ordinary MCP reads may consume
published snapshots, but they must not append domain events behind the user's
back.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_recovery_card,
    foreground_shell_action,
    shell_quote,
)
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.continuity_domain_producer import (
    DEFAULT_CONTINUITY_DOMAIN_PREVIEW_CANDIDATE_BUDGET,
    DEFAULT_CONTINUITY_DOMAIN_PREVIEW_THREAD_BUDGET,
    propose_continuity_domain_events_from_registry,
)
from aippocampus_runtime.recall.continuity_domains import (
    append_continuity_domain_event,
    continuity_domain_public_safety_report,
    default_continuity_domain_events_path,
    default_continuity_domain_snapshot_dir,
    load_continuity_domains_snapshot,
    publish_continuity_domains_snapshot,
)


def _ordinary_recall_path_action() -> dict[str, Any]:
    return {
        "id": "ordinary_recall_path",
        "label": "Use ordinary recall for a continuity cue",
        "requires": ["cue"],
        "command_template": 'aippocampus agent recall "{cue}" --json',
        "why": "Most foreground work should start from recall/deepen rather than domain backfill.",
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }


def _preview_domain_candidates_action(*, broad: bool = False) -> dict[str, object]:
    return foreground_shell_action(
        action_id="preview_domain_candidates",
        label="Preview candidate continuity domains",
        command=(
            "aippocampus continuity-domain preview --broad-scan --json"
            if broad
            else "aippocampus continuity-domain produce --preview --json"
        ),
        why="Preview is bounded and emits navigation-only candidate actions.",
        mutation_risk="read_only",
        claim_boundary="preview_not_source_truth",
    )


def _json_error(code: str, message: str) -> dict[str, Any]:
    next_action = _preview_domain_candidates_action()
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
        "agent_next_action": next_action,
        "safe_next_actions": [
            next_action,
            _ordinary_recall_path_action(),
        ],
    }


def recovery_payload() -> MappingPayload:
    return foreground_recovery_card(
        kind="aippocampus_continuity_domain_recovery",
        error_code="continuity_domain_command_required",
        message="Choose a read path, preview path, or explicit operator write path.",
        safe_next_actions=[
            _preview_domain_candidates_action(),
            foreground_shell_action(
                action_id="read_latest_snapshot",
                label="Read latest published domain snapshot",
                command="aippocampus continuity-domain latest --json",
                why="Use existing snapshots as reopenable route hints, not facts.",
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claims",
            ),
            _ordinary_recall_path_action(),
        ],
        source_boundary={
            "continuity_domains_are_routes_not_source_truth": True,
            "source_reopen_required_before_claims": True,
            "no_write_happened": True,
        },
    )


def _print_payload(payload: MappingPayload, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    status = payload.get("status") or ("ok" if payload.get("ok") else "error")
    print(f"continuity-domain: {status}")
    if payload.get("event_id"):
        print(f"event: {payload['event_id']}")
    if payload.get("snapshot_id"):
        print(f"snapshot: {payload['snapshot_id']}")
    if payload.get("summary"):
        summary = payload["summary"]
        if isinstance(summary, dict):
            print(
                "domains: "
                f"{summary.get('domain_count', 0)} | "
                f"source refs: {summary.get('source_ref_count', 0)}"
            )
    raw_metrics = payload.get("metrics")
    if isinstance(raw_metrics, dict):
        partial = bool(raw_metrics.get("scan_partial") or raw_metrics.get("scan_truncated_by_budget"))
        scanned = raw_metrics.get("scanned_thread_count", 0)
        registered = raw_metrics.get("registered_thread_count", 0)
        considered = raw_metrics.get("considered_thread_count", scanned)
        suffix = " partial" if partial else " complete"
        print(f"scan: {scanned}/{registered} threads ({considered} considered,{suffix})")
        print(
            "candidates: "
            f"{raw_metrics.get('candidate_domain_count', 0)} | "
            f"low-info suppressed: {raw_metrics.get('low_information_label_suppressed_count', 0)}"
        )
    previews = payload.get("candidate_previews")
    if isinstance(previews, list) and previews:
        print("preview:")
        for preview in previews[:5]:
            if not isinstance(preview, dict):
                continue
            title = preview.get("title") or preview.get("domain_handle") or "untitled"
            refs = preview.get("source_ref_count", 0)
            print(f"- {title} ({refs} source refs)")
        if len(previews) > 5:
            print(f"- ... {len(previews) - 5} more candidates hidden")
    raw_boundary = payload.get("preview_boundary")
    if isinstance(raw_boundary, dict) and raw_boundary.get("preview_is_not_source_truth"):
        print("boundary: preview is a route card; reopen source before claims")
    if payload.get("agent_next_action"):
        next_action = payload["agent_next_action"]
        if isinstance(next_action, dict):
            label = next_action.get("label") or next_action.get("command")
            command = next_action.get("command")
            print(f"next: {label}")
            if command and command != label:
                print(f"command: {command}")
        else:
            print(f"next: {next_action}")


MappingPayload = dict[str, Any]
GENERIC_FOREGROUND_CUE_TERMS = {
    "aippocampus",
    "aiippocampus",
    "sapientropic",
    "ai",
    "codex-hindsight-memory",
    "recall",
    "append",
    "anchor",
    "anchors",
    "锚点",
    "maintenance",
    "runtime",
    "runtime-contract",
    "continuity-domain",
    "continuity",
    "route",
    "source",
    "source-backed",
    "foreground",
    "action",
    "candidate",
    "candidates",
    "preview",
    "plugin",
    "tool",
    "issue",
    "issues",
    "用户",
    "角度",
}
GENERIC_FOREGROUND_CUE_PHRASES = {
    "runtime-contract.md",
    "old continuity cue",
    "continuity domain candidate",
    "aippocampus maintenance",
    "aippocampus 锚点",
}


def _read_event(args: argparse.Namespace) -> dict[str, Any]:
    sources = [
        bool(args.event_json),
        bool(args.event_file),
        bool(getattr(args, "stdin", False)),
    ]
    if sum(1 for item in sources if item) != 1:
        raise ValueError("append requires exactly one of --event-json, --event-file, or --stdin")
    if args.event_json:
        payload = args.event_json
    elif args.event_file:
        payload = Path(args.event_file).read_text(encoding="utf-8")
    else:
        payload = sys.stdin.read()
    event = json.loads(payload)
    if not isinstance(event, dict):
        raise ValueError("continuity-domain event payload must be a JSON object")
    return event


def _events_path(args: argparse.Namespace) -> Path:
    if args.events_path:
        return Path(args.events_path).resolve()
    return default_continuity_domain_events_path(
        Path(args.cwd).resolve(),
        registry_dir=_registry_dir_path(args),
    )


def _snapshot_dir(args: argparse.Namespace) -> Path:
    if args.snapshot_dir:
        return Path(args.snapshot_dir).resolve()
    return default_continuity_domain_snapshot_dir(
        Path(args.cwd).resolve(),
        registry_dir=_registry_dir_path(args),
    )


def _registry_dir_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "subcommand_registry_dir", None) or getattr(args, "registry_dir", None)
    return Path(raw).resolve() if raw else None


def _clean_source_dir(args: argparse.Namespace, events_path: Path) -> Path | None:
    if args.clean_source_dir:
        return Path(args.clean_source_dir).resolve()
    parent = events_path.parent
    return parent if (parent / "messages.jsonl").exists() else None


def _event_source_refs(event: MappingPayload) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key in (
        "source_refs",
        "support_refs",
        "counter_refs",
        "correction_refs",
        "boundary_refs",
        "representative_refs",
        "ordered_source_refs",
    ):
        refs.extend(safe_source_refs(event.get(key)))
    return refs


def _require_resolvable_append_refs(event: MappingPayload, clean_source_dir: Path | None) -> None:
    refs = _event_source_refs(event)
    if not refs:
        return
    if clean_source_dir is None or not (clean_source_dir / "messages.jsonl").exists():
        raise ValueError(
            "continuity-domain append needs resolvable clean-source refs; provide "
            "--clean-source-dir or use produce --preview before appending"
        )


def append_command(args: argparse.Namespace) -> MappingPayload:
    events_path = _events_path(args)
    clean_source_dir = _clean_source_dir(args, events_path)
    event = _read_event(args)
    _require_resolvable_append_refs(event, clean_source_dir)
    normalized = append_continuity_domain_event(
        events_path,
        event,
        clean_source_dir=clean_source_dir,
    )
    payload: MappingPayload = {
        "ok": True,
        "status": "ok",
        "event_id": normalized.get("event_id"),
        "event_kind": normalized.get("event_kind"),
        "events_path": str(events_path),
    }
    if args.publish:
        report = publish_continuity_domains_snapshot(
            events_path=events_path,
            snapshot_dir=_snapshot_dir(args),
            clean_source_dir=clean_source_dir,
        )
        payload["publish_report"] = report
        payload["snapshot_id"] = report.get("snapshot_id")
    return payload


def publish_command(args: argparse.Namespace) -> MappingPayload:
    events_path = _events_path(args)
    clean_source_dir = _clean_source_dir(args, events_path)
    report = publish_continuity_domains_snapshot(
        events_path=events_path,
        snapshot_dir=_snapshot_dir(args),
        clean_source_dir=clean_source_dir,
    )
    return {"ok": True, **report}


def _snapshot_summary(snapshot: MappingPayload) -> MappingPayload:
    report = continuity_domain_public_safety_report(snapshot)
    raw_metrics = report.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "generated_at": snapshot.get("generated_at"),
        "domain_count": len(snapshot.get("domains") or []),
        "event_count": metrics.get("event_count", 0),
        "source_ref_count": metrics.get("source_ref_count", 0),
        "source_reopen_required_before_claim": True,
    }


def _domain_cards(snapshot: MappingPayload, *, limit: int = 8) -> list[MappingPayload]:
    cards: list[MappingPayload] = []
    for domain in snapshot.get("domains") or []:
        if not isinstance(domain, dict):
            continue
        raw_trail = domain.get("evidence_trail")
        trail: Mapping[str, Any] = raw_trail if isinstance(raw_trail, Mapping) else {}
        source_ref_count = 0
        for refs in trail.values():
            if isinstance(refs, list):
                source_ref_count += len(refs)
        raw_lifecycle = domain.get("lifecycle")
        lifecycle: Mapping[str, Any] = (
            raw_lifecycle if isinstance(raw_lifecycle, Mapping) else {}
        )
        cards.append(
            {
                "domain_id": domain.get("domain_id"),
                "title": compact_text(str(domain.get("title") or domain.get("domain_id") or "untitled domain"), 96),
                "status": lifecycle.get("status") or "active",
                "source_ref_count": source_ref_count,
                "action_grammar": "reopenable_route",
                "source_reopen_required_before_claim": True,
            }
        )
        if len(cards) >= limit:
            break
    return redact_sensitive_values(redact_private_paths(cards))


def _no_snapshot_payload() -> MappingPayload:
    next_action = _preview_domain_candidates_action()
    return {
        "ok": True,
        "status": "empty",
        "snapshot_count": 0,
        "source_boundary": {
            "absence_is_not_absence_of_source_history": True,
            "source_reopen_required_before_claim": True,
            "local_paths_serialized": False,
        },
        "agent_next_action": next_action,
        "safe_next_actions": [
            next_action,
            _ordinary_recall_path_action(),
        ],
    }


def latest_command(args: argparse.Namespace) -> MappingPayload:
    latest_path = _snapshot_dir(args) / "latest.json"
    snapshot = load_continuity_domains_snapshot(latest_path)
    if snapshot is None:
        return _no_snapshot_payload()
    report = continuity_domain_public_safety_report(snapshot)
    return {
        "ok": True,
        "status": "ok",
        "mode": "latest",
        "snapshot_id": snapshot.get("snapshot_id"),
        "summary": _snapshot_summary(snapshot),
        "domains": _domain_cards(snapshot),
        "report": report,
        "source_boundary": report.get("contract"),
        "privacy_boundary": report.get("privacy_boundary"),
        "agent_next_action": {
            "id": "use_continuity_domain_as_route",
            "label": "Use these domains as reopenable routes only; deepen or reopen clean source before claims.",
        },
    }


def list_command(args: argparse.Namespace) -> MappingPayload:
    snapshot_dir = _snapshot_dir(args)
    summaries: list[MappingPayload] = []
    if snapshot_dir.exists():
        for path in sorted(snapshot_dir.glob("*.json"), key=lambda item: item.name):
            if path.name == "latest.json":
                continue
            snapshot = load_continuity_domains_snapshot(path)
            if snapshot is not None:
                summaries.append(_snapshot_summary(snapshot))
    if not summaries:
        return _no_snapshot_payload()
    return {
        "ok": True,
        "status": "ok",
        "mode": "list",
        "snapshot_count": len(summaries),
        "snapshots": summaries,
        "source_boundary": {
            "snapshots_are_routes_not_source_truth": True,
            "source_reopen_required_before_claim": True,
            "local_paths_serialized": False,
        },
        "agent_next_action": {
            "id": "read_latest_continuity_domain_snapshot",
            "label": "Run `aippocampus continuity-domain latest --json` for the current published route card.",
            "command": "aippocampus continuity-domain latest --json",
        },
    }


def report_command(args: argparse.Namespace) -> MappingPayload:
    snapshot_path = Path(args.snapshot).resolve() if args.snapshot else _snapshot_dir(args) / "latest.json"
    snapshot = load_continuity_domains_snapshot(snapshot_path)
    if snapshot is None:
        return _no_snapshot_payload()
    return {
        "ok": True,
        "status": "ok",
        "mode": "report",
        "snapshot_id": snapshot.get("snapshot_id"),
        "summary": _snapshot_summary(snapshot),
        "report": continuity_domain_public_safety_report(snapshot),
    }


def _strip_producer_local_detail(payload: MappingPayload) -> MappingPayload:
    clean = {key: value for key, value in payload.items() if key != "candidate_events"}
    label_rows = []
    for row in clean.get("top_domain_labels") or []:
        if isinstance(row, dict):
            label_rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"label", "thread_key"}
                }
            )
    clean["top_domain_labels"] = label_rows
    return clean


def _foreground_cue_quality(cue: str) -> tuple[str, str]:
    text = compact_text(str(cue or ""), 80).strip()
    if not text:
        return "low_information", "empty"
    low = text.strip('"`“”‘’.,;:!?，。；：！？()[]{}<>').casefold()
    if low in GENERIC_FOREGROUND_CUE_PHRASES:
        return "low_information", "generic_tool_word"
    if low.startswith("-") or re.fullmatch(r"-{1,2}[\w][\w.-]*", low):
        return "low_information", "cli_flag_or_option"
    if low.endswith((".md", ".py", ".json", ".jsonl", ".toml", ".yaml", ".yml")) and " " not in low:
        return "low_information", "file_name_only"
    tokens = [
        token.strip('"`“”‘’.,;:!?，。；：！？()[]{}<>')
        for token in re.findall(r"[\w\u4e00-\u9fff.-]+", low.replace("_", "-"))
        if token.strip('"`“”‘’.,;:!?，。；：！？()[]{}<>')
    ]
    if tokens and all(token in GENERIC_FOREGROUND_CUE_TERMS for token in tokens):
        return "low_information", "generic_tool_word"
    if low in GENERIC_FOREGROUND_CUE_TERMS:
        return "low_information", "generic_tool_word"
    return "actionable", ""


def _best_foreground_cue(cues: list[str], fallback_title: str) -> tuple[str, str, str]:
    for cue in [*cues, fallback_title]:
        quality, reason = _foreground_cue_quality(cue)
        if quality == "actionable":
            return compact_text(str(cue), 80), quality, reason
    first = cues[0] if cues else fallback_title
    quality, reason = _foreground_cue_quality(first)
    return compact_text(str(first), 80), quality, reason


def _producer_candidate_previews(payload: MappingPayload) -> list[MappingPayload]:
    previews: list[MappingPayload] = []
    for event in payload.get("candidate_events") or []:
        if not isinstance(event, dict):
            continue
        refs = event.get("source_refs") or []
        cues = [
            compact_text(str(cue), 80)
            for cue in event.get("activation_cues") or []
            if str(cue).strip()
        ][:6]
        title = compact_text(str(event.get("title") or "untitled domain"), 96)
        cue, quality, reason = _best_foreground_cue(cues, title)
        preview = {
                "domain_handle": event.get("domain_id"),
                "title": title,
                "domain_type": event.get("domain_type"),
                "scale": event.get("scale"),
                "activation_cues": cues,
                "foreground_candidate_quality": quality,
                "source_ref_count": len(refs) if isinstance(refs, list) else 0,
                "source_reopen_required_before_claim": True,
            }
        if reason:
            preview["suppression_reason"] = reason
        if quality == "actionable" and cue:
            recall_command = f"aippocampus agent recall {shell_quote(cue)} --json"
            preview["foreground_actions"] = [
                    foreground_shell_action(
                        action_id="recall_candidate_cue",
                        label="Recall this candidate cue",
                        command=recall_command,
                        why="Candidate previews are navigation only; recall/deepen before claims.",
                        mutation_risk="read_only",
                        claim_boundary="no_claim_before_reopen",
                    )
                ]
        else:
            preview["foreground_actions"] = []
        previews.append(preview)
    return previews


def _producer_agent_preview(payload: MappingPayload) -> MappingPayload:
    clean = _strip_producer_local_detail(payload)
    previews = _producer_candidate_previews(payload)
    metrics = dict(payload.get("metrics") or {})
    clean["detail"] = "agent_preview"
    clean["candidate_previews"] = previews
    clean["summary_metrics"] = {
        "registered_thread_count": metrics.get("registered_thread_count", 0),
        "considered_thread_count": metrics.get("considered_thread_count", 0),
        "scanned_thread_count": metrics.get("scanned_thread_count", 0),
        "candidate_count": metrics.get("candidate_count", len(previews)),
        "scan_partial": bool(metrics.get("scan_partial")),
    }
    clean["route_value"] = "continuity_domain_candidates_are_navigation_routes"
    clean["preview_boundary"] = {
        "candidate_events_emitted": False,
        "raw_source_refs_emitted": False,
        "local_paths_emitted": False,
        "preview_is_not_source_truth": True,
    }
    actionable_previews = [
        preview for preview in previews if preview.get("foreground_candidate_quality") == "actionable"
    ]
    if actionable_previews:
        primary = actionable_previews[0].get("foreground_actions") or []
        primary_action = primary[0] if primary and isinstance(primary[0], dict) else None
        clean["foreground_candidate_quality"] = "actionable"
        clean["agent_next_action"] = {
            "id": "use_candidate_preview_as_reopenable_route",
            "label": "Use candidate_previews as navigation only; run recall/deepen on the cue before any factual claim.",
            "command": (primary_action or {}).get("command")
            or 'aippocampus agent recall "continuity domain candidate" --json',
            "requires_operator_review": False,
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
            "why": "Continuity-domain previews can route attention, but recall/deepen must reopen source before claims.",
        }
        clean["current_uncertainty"] = "candidate_preview_requires_recall_deepen_before_claim"
        clean["operator_next_action"] = {
            "id": "append_after_reviewed_backfill",
            "label": "Only after operator review, append/publish durable continuity domains.",
            "command": "aippocampus continuity-domain produce --append --publish --json",
            "requires_operator_review": True,
            "mutation_risk": "explicit_continuity_domain_write",
            "claim_boundary": "operator_review_required_before_durable_memory",
        }
    elif previews:
        clean["foreground_candidate_quality"] = "needs_broader_scan"
        clean["agent_next_action"] = {
            "id": "needs_broader_scan_or_cue",
            "label": "Only low-information continuity-domain cues surfaced; broaden the scan or provide a user cue.",
            "command": "aippocampus continuity-domain preview --broad-scan --json",
            "requires_operator_review": False,
            "mutation_risk": "read_only",
            "claim_boundary": "preview_not_source_truth",
            "why": "Low-information candidates are not useful enough for foreground routing yet.",
        }
        clean["current_uncertainty"] = "low_information_candidates_need_broader_scan_or_user_cue"
    else:
        clean["foreground_candidate_quality"] = "needs_broader_scan"
        clean["agent_next_action"] = {
            "id": "no_continuity_domain_candidates",
            "label": "No supported continuity-domain candidates were found; keep the public dry-run report as evidence.",
            "command": "aippocampus continuity-domain preview --broad-scan --json",
            "requires_operator_review": False,
            "mutation_risk": "read_only",
            "claim_boundary": "preview_not_source_truth",
            "why": "No preview candidate is available in this bounded scan.",
        }
        clean["current_uncertainty"] = "bounded_scan_found_no_supported_candidates"
    clean.update(
        canonical_foreground_action_fields(
            clean["agent_next_action"],
            safe_next_actions=[
                clean["agent_next_action"],
                _ordinary_recall_path_action(),
                _preview_domain_candidates_action(broad=True),
            ],
        )
    )
    return redact_sensitive_values(redact_private_paths(clean))


def produce_command(args: argparse.Namespace) -> MappingPayload:
    if args.dry_run and args.append:
        raise ValueError("produce accepts --dry-run or --append, not both")
    if args.preview and args.append:
        raise ValueError("produce --preview is dry-run only; use --append after review")
    if args.preview and args.include_local_detail:
        raise ValueError("produce accepts --preview or --include-local-detail, not both")
    preview_scan_policy: MappingPayload | None = None
    broad_scan = bool(getattr(args, "broad_scan", False))
    max_threads = args.max_threads
    max_candidates = args.max_candidates
    # Plain `produce --json` is often reached from foreground agents. Keep that
    # path bounded and preview-shaped unless the operator explicitly asks for a
    # broad/custom backfill scan. Do not treat `--include-local-detail` as broad
    # permission; it can expose local detail, but it should still inherit the
    # safe thread budget unless paired with --broad-scan, --append, or
    # --max-threads.
    foreground_bounded_default = not args.append and not broad_scan and max_threads is None
    preview_equivalent = bool(
        args.preview or (foreground_bounded_default and not args.include_local_detail)
    )
    if foreground_bounded_default:
        max_threads = DEFAULT_CONTINUITY_DOMAIN_PREVIEW_THREAD_BUDGET
        preview_scan_policy = {
            "mode": "foreground_bounded_default",
            "max_threads": max_threads,
            "broad_scan_command": "aippocampus continuity-domain preview --broad-scan --json",
        }
    elif args.preview:
        if broad_scan:
            preview_scan_policy = {
                "mode": "explicit_broad_scan",
                "max_threads": max_threads,
            }
        else:
            preview_scan_policy = {
                "mode": "explicit_bounded",
                "max_threads": max_threads,
            }
    if preview_equivalent and max_candidates is None:
        max_candidates = DEFAULT_CONTINUITY_DOMAIN_PREVIEW_CANDIDATE_BUDGET
    elif max_candidates is None:
        max_candidates = 24
    proposal = propose_continuity_domain_events_from_registry(
        registry_path=Path(args.registry).resolve() if args.registry else None,
        registry_dir=_registry_dir_path(args),
        min_support=args.min_support,
        max_threads=max_threads,
        max_candidates=max_candidates,
        include_local_detail=True,
        refresh_query_pattern_routes=(
            bool(args.refresh_query_pattern_routes)
            or (bool(args.append) and not bool(args.no_refresh_query_pattern_routes))
        ),
    )
    events = list(proposal.get("candidate_events") or [])
    if preview_equivalent:
        payload = _producer_agent_preview(proposal)
    elif args.include_local_detail:
        payload = proposal
    else:
        payload = _strip_producer_local_detail(proposal)
    if preview_scan_policy is not None:
        payload["preview_scan_policy"] = preview_scan_policy
    payload["mode"] = "append" if args.append else "dry_run"
    if not args.append:
        return payload

    events_path = _events_path(args)
    appended = []
    rejected = 0
    for event in events:
        try:
            appended.append(
                append_continuity_domain_event(
                    events_path,
                    event,
                    clean_source_dir=None,
                )
            )
        except ValueError:
            rejected += 1
    write_report: MappingPayload = {
        "append_requested": True,
        "appended_event_count": len(appended),
        "append_rejected_event_count": rejected,
        "events_path": str(events_path),
    }
    if args.publish:
        publish_report = publish_continuity_domains_snapshot(
            events_path=events_path,
            snapshot_dir=_snapshot_dir(args),
            clean_source_dir=None,
        )
        write_report["publish_report"] = publish_report
        payload["snapshot_id"] = publish_report.get("snapshot_id")
    payload["write_report"] = write_report
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus continuity-domain",
        description=(
            "Inspect or backfill source-trailed continuity domains. Ordinary "
            "foreground use goes through agent recall/deepen; manual append and "
            "publish are operator/debug/backfill paths."
        ),
        epilog=(
            "Ordinary path: use `aippocampus agent recall` and deepen source "
            "routes before claims. Use `continuity-domain preview --json` for a "
            "foreground-bounded route card; `produce --dry-run` and append/publish "
            "are heavier operator/backfill paths."
        ),
    )
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--registry-dir")
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="operator/debug manual event append")
    append.add_argument("--events-path")
    append.add_argument("--clean-source-dir")
    append.add_argument("--snapshot-dir")
    append.add_argument("--event-json")
    append.add_argument("--event-file")
    append.add_argument("--stdin", action="store_true")
    append.add_argument("--publish", action="store_true")
    append.add_argument("--json", action="store_true", dest="json_output")

    publish = sub.add_parser("publish", help="operator/debug snapshot rebuild")
    publish.add_argument("--events-path")
    publish.add_argument("--clean-source-dir")
    publish.add_argument("--snapshot-dir")
    publish.add_argument("--json", action="store_true", dest="json_output")

    read_path_description = (
        "Read-path action card:\n"
        "  Continuity-domain snapshots are reopenable routes, not source truth.\n"
        "  Use them to choose what to reopen; deepen clean source before factual claims.\n"
        "  Empty output means no published snapshot for this scope, not no memory exists."
    )

    latest = sub.add_parser(
        "latest",
        help="read the latest public-safe snapshot card",
        description=read_path_description,
        epilog=(
            "Try:\n"
            "  aippocampus continuity-domain latest --json\n"
            "  aippocampus agent recall <cue> --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    latest.add_argument("--snapshot-dir")
    latest.add_argument("--json", action="store_true", dest="json_output")

    list_parser = sub.add_parser(
        "list",
        help="list public-safe continuity-domain snapshots",
        description=read_path_description,
        epilog=(
            "Try:\n"
            "  aippocampus continuity-domain list --json\n"
            "  aippocampus continuity-domain latest --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument("--snapshot-dir")
    list_parser.add_argument("--json", action="store_true", dest="json_output")

    report = sub.add_parser(
        "report",
        help="read an existing public-safe snapshot report",
        description=read_path_description,
        epilog=(
            "Try:\n"
            "  aippocampus continuity-domain report --json\n"
            "  aippocampus continuity-domain preview --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    report.add_argument("--snapshot")
    report.add_argument("--snapshot-dir")
    report.add_argument("--json", action="store_true", dest="json_output")

    produce = sub.add_parser("produce", help="preview/backfill deterministic producer candidates")
    produce.add_argument("--registry")
    produce.add_argument("--registry-dir", dest="subcommand_registry_dir")
    produce.add_argument("--events-path")
    produce.add_argument("--snapshot-dir")
    produce.add_argument("--dry-run", action="store_true")
    produce.add_argument("--append", action="store_true")
    produce.add_argument("--publish", action="store_true")
    produce.add_argument("--refresh-query-pattern-routes", action="store_true")
    produce.add_argument("--no-refresh-query-pattern-routes", action="store_true")
    produce.add_argument("--include-local-detail", action="store_true")
    produce.add_argument("--preview", action="store_true")
    produce.add_argument("--broad-scan", action="store_true")
    produce.add_argument("--min-support", type=int, default=2)
    produce.add_argument("--max-threads", type=int)
    produce.add_argument("--max-candidates", type=int)
    produce.add_argument("--json", action="store_true", dest="json_output")

    preview = sub.add_parser(
        "preview",
        help="foreground preview alias for deterministic producer candidates",
    )
    preview.add_argument("--registry")
    preview.add_argument("--registry-dir", dest="subcommand_registry_dir")
    preview.add_argument("--broad-scan", action="store_true")
    preview.add_argument("--min-support", type=int, default=2)
    preview.add_argument("--max-threads", type=int)
    preview.add_argument("--max-candidates", type=int)
    preview.add_argument("--json", action="store_true", dest="json_output")
    preview.set_defaults(
        preview=True,
        dry_run=True,
        append=False,
        publish=False,
        include_local_detail=False,
        refresh_query_pattern_routes=False,
        no_refresh_query_pattern_routes=False,
        events_path=None,
        snapshot_dir=None,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    command_names = {"append", "publish", "latest", "list", "report", "produce", "preview"}
    if not any(arg in command_names for arg in raw_args) and not any(
        arg in {"-h", "--help"} for arg in raw_args
    ):
        payload = recovery_payload()
        _print_payload(payload, json_output="--json" in raw_args)
        return 2
    parser = build_arg_parser()
    args = parser.parse_args(raw_args)
    try:
        if args.command == "append":
            payload = append_command(args)
        elif args.command == "publish":
            payload = publish_command(args)
        elif args.command == "latest":
            payload = latest_command(args)
        elif args.command == "list":
            payload = list_command(args)
        elif args.command == "report":
            payload = report_command(args)
        elif args.command in {"produce", "preview"}:
            payload = produce_command(args)
        else:
            parser.error("unknown command")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = _json_error("continuity_domain_cli_error", str(exc))
        _print_payload(payload, json_output=getattr(args, "json_output", False))
        return 2
    _print_payload(payload, json_output=getattr(args, "json_output", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
