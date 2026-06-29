"""Agent-native first action chooser for AIppocampus."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.cli.start_profiles import (
    START_PROFILE_CHOICES,
    annotate_trusted_personal_write_actions,
    is_trusted_local_personal_profile,
    trusted_personal_card_fields,
)
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_action_is_read_only,
    foreground_shell_action,
    shell_quote,
)
from aippocampus_runtime.first_recall_readiness import (
    compact_start_first_recall_readiness,
    start_first_recall_readiness,
    start_first_recall_readiness_diagnostic,
)
from aippocampus_runtime.foreground_compact_language import compact_frontstage_projection
from aippocampus_runtime.onboarding.facade import provider_status_report
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.public_output import emit_public_json, emit_public_text
from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir

SCHEMA_VERSION = 1
LOW_SPECIFICITY_TERMS = {
    "agent",
    "aippocampus",
    "clean",
    "continuity",
    "deepen",
    "memory",
    "product",
    "recall",
    "refine",
    "route",
    "search",
    "source",
    "specificity",
    "usability",
}


def _template_action(
    *,
    action_id: str,
    command_template: str,
    label: str,
    why: str,
    requires: list[str],
    mutation_risk: str = "read_only",
    claim_boundary: str = "source_reopen_required_before_claims",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "command_template": command_template,
        "template_only": True,
        "requires": list(requires),
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
        "why": why,
    }


def _json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _clean_source_state(cwd: Path, explicit_dir: str | None = None) -> dict[str, Any]:
    clean_dir = resolve_clean_source_dir(cwd, explicit_dir)
    messages = clean_dir / "messages.jsonl"
    manifest = _json_file(clean_dir / "manifest.json")
    message_count = int(manifest.get("message_count") or 0)
    if messages.exists() and message_count <= 0:
        try:
            message_count = sum(1 for line in messages.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            message_count = 1
    stale = bool(
        manifest.get("stale")
        or str(manifest.get("status") or "").lower() in {"stale", "degraded"}
        or str(manifest.get("health") or "").lower() in {"stale", "degraded"}
    )
    return {
        "exists": messages.exists() and message_count > 0,
        "stale": stale,
        "manifest_stale": stale,
        "message_count": message_count,
        "path_label": "thread-clean-source",
        "path_serialized": False,
        "freshness_scope": (
            "explicit_clean_source_manifest_only" if explicit_dir else "workspace_health_summary"
        ),
    }


def _workspace_freshness_state(cwd: Path, explicit_dir: str | None = None) -> dict[str, Any]:
    """Return the small health-derived freshness slice that start can act on.

    `start` is a first-action chooser, not a health detail surface. The recurring
    failure here is subtler than a stale manifest: clean-source/index artifacts
    can exist and still miss the newest visible turns. Reuse health's existing
    product-readiness summary, but only project the behavior-bearing bits needed
    to decide whether exact latest/current-thread claims need maintenance first.
    """

    if explicit_dir:
        return {
            "assessed": False,
            "freshness_scope": "explicit_clean_source_manifest_only",
            "reason": "explicit_clean_source_dir_limits_start_to_manifest",
        }
    try:
        from aippocampus_runtime.health import health_report

        payload = health_report(cwd, include_operator_diagnostics=False)
    except Exception:
        return {
            "assessed": False,
            "freshness_scope": "workspace_health_summary_unavailable",
        }
    readiness = payload.get("product_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    recommended = payload.get("recommended_actions")
    rows = [item for item in recommended if isinstance(item, dict)] if isinstance(recommended, list) else []
    recommended_ids = [str(item.get("id") or "") for item in rows if item.get("id")]
    freshness_action_ids = {"build_clean_source", "build_index", "build_segments"}
    workspace_maintenance = bool(
        readiness.get("workspace_source_maintenance_required")
        or any(action_id in freshness_action_ids for action_id in recommended_ids)
    )
    live_delta_tolerated = bool(readiness.get("live_delta_tolerated"))
    latest_missing = bool(
        readiness.get("latest_current_thread_may_be_missing")
        and (workspace_maintenance or not live_delta_tolerated)
    )
    freshness_degraded = bool(
        workspace_maintenance
        and (
            readiness.get("freshness_degraded")
            or latest_missing
            or any(action_id in freshness_action_ids for action_id in recommended_ids)
        )
    )
    return {
        "assessed": True,
        "freshness_scope": "workspace_health_summary",
        "freshness_degraded": freshness_degraded,
        "latest_current_thread_may_be_missing": latest_missing,
        "workspace_source_maintenance_required": workspace_maintenance,
        "blocks_exact_latest_claims": bool(freshness_degraded),
        "recommended_action_ids": recommended_ids[:8],
        "product_readiness_status": str(readiness.get("status") or ""),
    }


def _apply_workspace_freshness(source: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    source = dict(source)
    source["freshness_scope"] = freshness.get("freshness_scope") or source.get("freshness_scope")
    if freshness.get("assessed"):
        source["workspace_health_freshness_assessed"] = True
    if freshness.get("freshness_degraded"):
        source["stale"] = True
        source["latest_source_may_be_missing"] = bool(
            freshness.get("latest_current_thread_may_be_missing")
        )
        source["workspace_source_maintenance_required"] = bool(
            freshness.get("workspace_source_maintenance_required")
        )
        source["blocks_exact_latest_claims"] = bool(
            freshness.get("blocks_exact_latest_claims")
        )
    return source


def _cue_value(cue: str | None) -> str:
    text = str(cue or "").strip()
    if not text:
        return ""
    return core.compact_text(str(redact_sensitive_values(redact_private_paths(text))), 240)


def _cue_specificity(cue: str) -> dict[str, Any]:
    terms = [
        term
        for term in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", cue.casefold())
        if term not in LOW_SPECIFICITY_TERMS
    ]
    unique_terms = sorted(set(terms))
    weak = len(unique_terms) < 2 or len(cue.strip()) < 12
    return {
        "status": "weak_cue_search_fallback_recommended" if weak else "callable_not_previewed",
        "specific_term_count": len(unique_terms),
        "bounded_recall_preview_run": False,
        "usefulness_verified_for_cue": False,
    }


def _recall_cue_action(cue: str) -> dict[str, Any]:
    return foreground_shell_action(
        action_id="recall_supplied_cue",
        label="Recall supplied cue",
        command=f"aippocampus agent recall {shell_quote(cue)} --json",
        why=(
            "A cue was supplied, so start can hand the next agent a concrete recall command; "
            "deepen or reopen source before claims."
        ),
        mutation_risk="read_only",
        claim_boundary="cue_recall_action_not_cue_specific_success_proof",
    )


def _search_cue_action(cue: str, *, registry: bool = False) -> dict[str, Any]:
    return foreground_shell_action(
        action_id="search_all_for_supplied_cue" if registry else "search_current_source_for_supplied_cue",
        label="Search all registered sources" if registry else "Search current source",
        command=(
            f"aippocampus search --all {shell_quote(cue)} --json"
            if registry
            else f"aippocampus search {shell_quote(cue)} --json"
        ),
        why=(
            "Use this when compact recall looks low-specificity or refine-only; source search "
            "can still find exact wording without treating navigation as evidence."
        ),
        mutation_risk="read_only",
        claim_boundary="search_result_requires_source_reopen_before_claims",
    )


def _trusted_codex_candidate(cwd: Path) -> bool:
    return (
        (cwd / "plugins" / "aippocampus" / ".codex-plugin" / "plugin.json").exists()
        or (cwd / ".codex-plugin" / "plugin.json").exists()
    )


def _carry_actions() -> list[dict[str, Any]]:
    return [
        foreground_shell_action(
            action_id="choose_export_for_next_thread",
            label="Carry context with export",
            command="aippocampus export --json",
            why="Use after recall/deepen when continuity needs to move into another thread or device.",
            mutation_risk="read_only",
            claim_boundary="transfer_setup_not_expanded_source_truth",
        ),
        foreground_shell_action(
            action_id="choose_sync_for_next_device",
            label="Carry context with sync",
            command="aippocampus sync --json",
            why="Use when continuity should survive through a local sync folder or device boundary.",
            mutation_risk="read_only",
            claim_boundary="transfer_setup_not_expanded_source_truth",
        ),
    ]


def _exact_latest_maintenance_actions() -> list[dict[str, Any]]:
    return [
        foreground_shell_action(
            action_id="review_maintenance_plan_before_exact_latest",
            label="Review maintenance before exact latest",
            command="aippocampus maintenance plan --summary-json",
            why=(
                "Existing source can support ordinary recall, but stale artifacts should be "
                "refreshed before exact latest/current-thread claims."
            ),
            mutation_risk="read_only",
            claim_boundary="maintenance_plan_not_source_evidence",
        ),
        foreground_shell_action(
            action_id="apply_maintenance_after_consent",
            label="Apply maintenance after consent",
            command="aippocampus maintenance apply --summary-json",
            why=(
                "Run only after reviewing the plan and deciding to refresh generated "
                "source/index artifacts."
            ),
            mutation_risk="writes_generated_source_artifacts",
            claim_boundary="explicit_maintenance_write_not_source_claim",
        )
        | {
            "write_boundary": {
                "explicit_user_consent_required": True,
                "no_write_happens_until_command_runs": True,
            }
        },
    ]


def _provider_registration_candidates(cwd: Path) -> list[str]:
    try:
        report = provider_status_report("auto", cwd=str(cwd), detailed=False)
    except Exception:
        return ["codex", "claude-code", "generic-jsonl"]
    data = report.get("data") if isinstance(report, dict) else {}
    raw_providers = data.get("providers") if isinstance(data, dict) else []
    providers = raw_providers if isinstance(raw_providers, list | tuple) else []
    rows = [item for item in providers if isinstance(item, dict)]
    if not rows:
        return ["codex", "claude-code", "generic-jsonl"]
    provider_order = {"codex": 0, "claude-code": 1, "generic-jsonl": 2}

    def rank(row: dict[str, Any]) -> tuple[int, int]:
        provider = str(row.get("provider") or "").strip()
        if row.get("current_cwd_match"):
            bucket = 0
        elif row.get("detected"):
            bucket = 1
        elif provider == "codex" and row.get("write_registration_available"):
            # Codex is the conservative fallback because its provider can
            # usually locate the active checkout even when frontstage sampling
            # does not see a transcript yet. Do not let this fallback outrank
            # an actually detected non-Codex source.
            bucket = 2
        elif row.get("write_registration_available"):
            bucket = 3
        else:
            bucket = 4
        return bucket, provider_order.get(provider, 99)

    candidates: list[str] = []
    for row in sorted(rows, key=rank):
        provider = str(row.get("provider") or "").strip()
        if provider in provider_order and provider not in candidates:
            candidates.append(provider)
    for provider in ["codex", "claude-code", "generic-jsonl"]:
        if provider not in candidates:
            candidates.append(provider)
    return candidates


def _source_registration_actions(providers: list[str]) -> list[dict[str, Any]]:
    actions_by_provider: dict[str, dict[str, Any]] = {
        "codex": foreground_shell_action(
            action_id="register_codex_source",
            label="Register Codex source",
            command="aippocampus onboard --provider codex --cwd . --json",
            why=(
                "No local clean source was found; this explicit write command registers "
                "Codex history so recall has source to search."
            ),
            mutation_risk="writes_local_clean_source",
            claim_boundary="registration_enables_source_reopen_not_source_evidence",
        ),
        "claude-code": foreground_shell_action(
            action_id="register_claude_code_source",
            label="Register Claude Code source",
            command="aippocampus onboard --provider claude-code --cwd . --json",
            why=(
                "Use when Claude Code transcripts are the local source the user wants "
                "to register before recall."
            ),
            mutation_risk="writes_local_clean_source",
            claim_boundary="registration_enables_source_reopen_not_source_evidence",
        ),
        "generic-jsonl": _template_action(
            action_id="import_generic_jsonl_source",
            label="Import generic JSONL source",
            command_template=(
                "aippocampus import conversation --format generic-jsonl "
                '--input "{input_path}" --json'
            ),
            requires=["input_path"],
            mutation_risk="writes_local_clean_source",
            why="Use when the source is an explicit exported transcript file rather than a host provider.",
            claim_boundary="registration_enables_source_reopen_not_source_evidence",
        ),
    }
    ordered: list[dict[str, Any]] = []
    for provider in providers:
        action = actions_by_provider.get(provider)
        if action and action not in ordered:
            ordered.append(action)
    return ordered


def _start_actions(cwd: Path, state: dict[str, Any], cue: str = "") -> tuple[str, list[dict[str, Any]]]:
    source = state["clean_source"]
    if source["exists"]:
        source_stale = bool(source.get("stale"))
        cue_specificity = _cue_specificity(cue) if cue else {}
        recall_action = _recall_cue_action(cue) if cue else _template_action(
            action_id="recall_continuity_cue",
            label="Recall from existing source",
            command_template='aippocampus agent recall "{continuity_cue}" --json',
            requires=["continuity_cue"],
            why="Existing clean source is available; start with route recall, then deepen before claims.",
        )
        actions = [
            recall_action,
            *(
                [
                    _search_cue_action(cue),
                    _search_cue_action(cue, registry=True),
                ]
                if cue
                else []
            ),
            *(_exact_latest_maintenance_actions() if source_stale else []),
        ]
        if cue_specificity.get("status") == "weak_cue_search_fallback_recommended":
            decision = (
                "continue_from_existing_source_latest_degraded"
                if source_stale
                else "continue_from_existing_source_with_search_fallback"
            )
            return decision, [
                actions[1],
                recall_action,
                *actions[2:],
            ]
        return (
            "continue_from_existing_source_latest_degraded"
            if source_stale
            else "continue_from_existing_source"
        ), actions
    if state["trusted_codex_candidate"]:
        read_only_recall = _recall_cue_action(cue) if cue else _template_action(
            action_id="try_first_recall",
            label="Try first recall",
            command_template='aippocampus agent recall "{continuity_cue}" --json',
            requires=["continuity_cue"],
            why=(
                "The packaged CLI is callable from a trusted checkout; try a read-only "
                "continuity route before changing plugin or hook state."
            ),
        )
        return "try_read_only_continuity_before_setup", [
            read_only_recall,
            _template_action(
                action_id="public_safe_demo_search",
                label="Try public-safe exact search",
                command_template=(
                    'aippocampus search "{exact_phrase}" --json '
                    "--clean-source-dir ./examples/public-memory-bundle/clean-source"
                ),
                requires=["exact_phrase"],
                why=(
                    "Use when there is no private source yet and the foreground needs a public "
                    "demo; this stays inside the packaged public fixture."
                ),
                claim_boundary="exact_search_result_requires_source_scope",
            ),
            foreground_shell_action(
                action_id="verify_codex_plugin_secondary",
                label="Install or verify Codex plugin",
                command="aippocampus plugin install --codex --verify --json",
                why="Setup remains available, but it is not the ordinary first continuity answer.",
                mutation_risk="writes_local_plugin_cache",
                claim_boundary="install_status_not_recall_quality",
            ),
        ]
    return "register_source_before_continuity", [
        *_source_registration_actions(state.get("provider_registration_candidates") or []),
        foreground_shell_action(
            action_id="inspect_onboarding_status",
            label="Inspect source onboarding status",
            command="aippocampus onboard --provider auto --status --json",
            why="Use when registration fails or the agent needs the provider matrix before choosing a write path.",
            mutation_risk="read_only",
            claim_boundary="onboarding_status_not_source_evidence",
        ),
        foreground_shell_action(
            action_id="review_claude_code_hooks",
            label="Review Claude Code hook setup",
            command="aippocampus hooks claude-code status --json",
            why=(
                "Claude Code ambient hooks are explicit host setup; review status before "
                "installing scoped UserPromptSubmit/Stop handlers."
            ),
            mutation_risk="read_only",
            claim_boundary="hook_status_not_source_evidence",
        ),
    ]


def build_start_card(
    cwd: Path,
    *,
    clean_source_dir: str | None = None,
    detail: str = "compact",
    cue: str | None = None,
    profile: str = "default",
) -> dict[str, Any]:
    clean_cue = _cue_value(cue)
    trusted_personal = is_trusted_local_personal_profile(profile)
    clean_source = _clean_source_state(cwd, clean_source_dir)
    freshness = _workspace_freshness_state(cwd, clean_source_dir)
    state: dict[str, Any] = {
        "clean_source": _apply_workspace_freshness(clean_source, freshness),
        "trusted_codex_candidate": _trusted_codex_candidate(cwd),
        "provider_registration_candidates": _provider_registration_candidates(cwd),
    }
    decision, actions = _start_actions(cwd, state, clean_cue)
    if trusted_personal and not state["clean_source"].get("exists"):
        annotate_trusted_personal_write_actions(actions, clean_cue=clean_cue)
    if not state["clean_source"].get("exists"):
        actions.append(
            _template_action(
                action_id="exact_search_fallback",
                label="Exact phrase fallback",
                command_template='aippocampus search "{exact_phrase}" --json',
                requires=["exact_phrase"],
                why=(
                    "Use only for exact known wording against the configured local source; "
                    "use public_safe_demo_search for the packaged public demo fixture."
                ),
                claim_boundary="exact_search_result_requires_source_scope",
            )
        )
    primary = actions[0]
    source_state = state["clean_source"]
    cue_specific = _cue_specificity(clean_cue) if clean_cue else {
        "status": "not_checked_no_cue_supplied",
        "bounded_recall_preview_run": False,
        "usefulness_verified_for_cue": False,
    }
    full_first_recall_readiness = start_first_recall_readiness_diagnostic(
        start_first_recall_readiness(
            decision=decision,
            source_exists=bool(source_state.get("exists")),
            source_stale=bool(source_state.get("stale")),
            action_id=str(primary.get("id") or ""),
        ),
        source_state=source_state,
        cue_specific=cue_specific,
        cue_supplied=bool(clean_cue),
        actions=actions,
    )
    compact_first_recall_readiness = compact_start_first_recall_readiness(
        full_first_recall_readiness
    )
    write_actions = [
        action
        for action in actions
        if isinstance(action, dict) and not foreground_action_is_read_only(action)
    ]
    action_fields = canonical_foreground_action_fields(
        primary,
        safe_next_actions=actions,
        safe_next_read_only_only=True,
    )
    detail_actions: dict[str, Any] = {
        "deepen_after_recall": (
            "aippocampus agent deepen --request {request_index} "
            "--recall-selector {recall_selector} --json"
        ),
        "export_after_recall": "aippocampus export --json",
        "sync_after_recall": "aippocampus sync --json",
    }
    hide_maintenance_write_actions = bool(source_state.get("exists")) and bool(write_actions)
    card: dict[str, Any] = {
        "kind": "aippocampus_start_card",
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "status": (
            "ready_with_freshness_degraded"
            if decision == "continue_from_existing_source_latest_degraded"
            else "ready"
            if decision.startswith(("continue", "try_read_only"))
            else "needs_setup"
        ),
        "surface_class": "foreground_chooser_card",
        "decision": decision,
        "cue_supplied": bool(clean_cue),
        **({"cue": clean_cue} if clean_cue else {}),
        **action_fields,
        "first_recall_readiness": compact_first_recall_readiness,
        "performance_expectation": full_first_recall_readiness.get("performance_expectation"),
        "blocks_exact_latest_claims": bool(
            full_first_recall_readiness.get("blocks_exact_latest_claims")
        ),
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": True,
        },
        **(trusted_personal_card_fields(clean_cue) if trusted_personal else {}),
        "detail_actions_available": detail_actions,
        **(
            {"manage_command": "aippocampus maintenance plan --summary-json"}
            if hide_maintenance_write_actions
            else {}
        ),
        **({"write_actions": write_actions} if write_actions and not hide_maintenance_write_actions else {}),
        "claim_boundary": "start chooses a route; source-backed claims still require recall/deepen source reopen",
    }
    if detail == "full":
        card["operator_detail"] = {
            "cwd_checked": "current_working_directory",
            "clean_source_path_redacted": True,
            "plugin_manifest_checked": True,
            "state_summary": state,
            "first_recall_readiness_diagnostic": full_first_recall_readiness,
            "carry_actions": _carry_actions(),
            "write_actions": write_actions,
        }
    return card


def _public_start_card(card: dict[str, Any], *, detail: str = "compact") -> dict[str, Any]:
    public = redact_sensitive_values(redact_private_paths(card))
    if detail == "full":
        return public
    compact = compact_frontstage_projection(public)
    if "safe_next_actions" in public and "safe_next_actions" not in compact:
        compact["safe_next_actions"] = []
    return compact


def render_text(card: dict[str, Any]) -> str:
    action = card["foreground_action"]
    readiness = card.get("first_recall_readiness") if isinstance(card, dict) else {}
    readiness_status = (
        str(readiness.get("status") or "")
        if isinstance(readiness, dict)
        else ""
    )
    lines = [
        "AIppocampus start",
        f"decision: {card['decision']}",
    ]
    if readiness_status:
        lines.append(f"first recall: {readiness_status}")
    setup_profile = card.get("setup_profile") if isinstance(card, dict) else {}
    if isinstance(setup_profile, dict) and setup_profile.get("id"):
        lines.append(f"profile: {setup_profile.get('id')}")
    if card.get("status") == "ready_with_freshness_degraded":
        lines.append(
            "ordinary recall: usable now; exact/latest claims need maintenance review first."
        )
        lines.append("maintenance: aippocampus maintenance plan --summary-json")
    if action.get("command_template"):
        requires = action.get("requires") or []
        if requires:
            lines.append("requires: " + ", ".join(str(item) for item in requires))
        lines.append(f"template: {action.get('command_template')}")
    else:
        lines.append(f"next: {action.get('command')}")
    magic_path = card.get("first_magic_path") if isinstance(card, dict) else {}
    if isinstance(magic_path, dict):
        after_setup = magic_path.get("after_setup_command") or magic_path.get(
            "after_setup_command_template"
        )
        if after_setup:
            lines.append(f"after setup: {after_setup}")
    lines.append(f"why: {action.get('why')}")
    lines.append("boundary: start is a chooser; reopen/deepen source before claims.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus start",
        description="Choose the first useful AIppocampus continuity action.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--operator-json", action="store_true")
    parser.add_argument("--detail", choices=("compact", "full"), default="compact")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--clean-source-dir")
    parser.add_argument("--cue")
    parser.add_argument(
        "--profile",
        choices=START_PROFILE_CHOICES,
        default="default",
    )
    parser.add_argument("cue_parts", nargs="*")
    args = parser.parse_args(argv)
    detail = "full" if args.operator_json else args.detail
    cue = args.cue or " ".join(args.cue_parts)
    card = build_start_card(
        Path(args.cwd).resolve(),
        clean_source_dir=args.clean_source_dir,
        detail=detail,
        cue=cue,
        profile=args.profile,
    )
    public_card = _public_start_card(card, detail=detail)
    if args.json_output or args.operator_json:
        emit_public_json(public_card)
    else:
        emit_public_text(render_text(public_card), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
