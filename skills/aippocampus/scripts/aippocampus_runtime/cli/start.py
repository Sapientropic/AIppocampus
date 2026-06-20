"""Agent-native first action chooser for AIppocampus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    foreground_shell_action,
)
from aippocampus_runtime.first_recall_readiness import start_first_recall_readiness
from aippocampus_runtime.onboarding.facade import provider_status_report
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.public_output import emit_public_json, emit_public_text

SCHEMA_VERSION = 1


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
    clean_dir = Path(explicit_dir).expanduser() if explicit_dir else core.default_thread_clean_source_dir(cwd)
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
        "message_count": message_count,
        "path_label": "thread-clean-source",
        "path_serialized": False,
    }


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
                "--input {input_path} --json"
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


def _start_actions(cwd: Path, state: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    source = state["clean_source"]
    if source["exists"] and source["stale"]:
        return "repair_stale_source_before_continuity", [
            foreground_shell_action(
                action_id="repair_health_first",
                label="Repair stale source health",
                command="aippocampus health --json",
                why="Stale or degraded source should be repaired before using continuity as evidence.",
                mutation_risk="read_only",
                claim_boundary="health_diagnostic_not_source_evidence",
            )
        ]
    if source["exists"]:
        return "continue_from_existing_source", [
            _template_action(
                action_id="recall_continuity_cue",
                label="Recall from existing source",
                command_template='aippocampus agent recall "{continuity_cue}" --json',
                requires=["continuity_cue"],
                why="Existing clean source is available; start with route recall, then deepen before claims.",
            ),
            foreground_shell_action(
                action_id="deepen_selected_route",
                label="Deepen selected route",
                command="aippocampus agent deepen --request 1 --last-recall --json",
                why="Use after a recall card exposes a request-index route.",
            ),
            *_carry_actions(),
        ]
    if state["trusted_codex_candidate"]:
        return "try_read_only_continuity_before_setup", [
            _template_action(
                action_id="try_first_recall",
                label="Try first recall",
                command_template='aippocampus agent recall "{continuity_cue}" --json',
                requires=["continuity_cue"],
                why=(
                    "The packaged CLI is callable from a trusted checkout; try a read-only "
                    "continuity route before changing plugin or hook state."
                ),
            ),
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


def build_start_card(cwd: Path, *, clean_source_dir: str | None = None, detail: str = "compact") -> dict[str, Any]:
    state: dict[str, Any] = {
        "clean_source": _clean_source_state(cwd, clean_source_dir),
        "trusted_codex_candidate": _trusted_codex_candidate(cwd),
        "provider_registration_candidates": _provider_registration_candidates(cwd),
    }
    decision, actions = _start_actions(cwd, state)
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
    first_recall_readiness = start_first_recall_readiness(
        decision=decision,
        source_exists=bool(source_state.get("exists")),
        source_stale=bool(source_state.get("stale")),
        action_id=str(primary.get("id") or ""),
    )
    card: dict[str, Any] = {
        "kind": "aippocampus_start_card",
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "status": "ready" if decision.startswith(("continue", "try_read_only")) else "needs_setup",
        "surface_class": "foreground_chooser_card",
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "decision": decision,
        "agent_next_action": primary,
        "foreground_action": primary,
        "safe_next_actions": actions,
        "first_recall_readiness": first_recall_readiness,
        "performance_expectation": first_recall_readiness.get("performance_expectation"),
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": True,
        },
        "claim_boundary": "start chooses a route; source-backed claims still require recall/deepen source reopen",
        "state_summary": state,
    }
    if detail == "full":
        card["operator_detail"] = {
            "cwd_checked": "current_working_directory",
            "clean_source_path_redacted": True,
            "plugin_manifest_checked": True,
        }
    return card


def _public_start_card(card: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive_values(redact_private_paths(card))


def render_text(card: dict[str, Any]) -> str:
    action = card["agent_next_action"]
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
    if action.get("command_template"):
        requires = action.get("requires") or []
        if requires:
            lines.append("requires: " + ", ".join(str(item) for item in requires))
        lines.append(f"template: {action.get('command_template')}")
    else:
        lines.append(f"next: {action.get('command')}")
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
    args = parser.parse_args(argv)
    detail = "full" if args.operator_json else args.detail
    card = build_start_card(
        Path(args.cwd).resolve(),
        clean_source_dir=args.clean_source_dir,
        detail=detail,
    )
    public_card = _public_start_card(card)
    if args.json_output or args.operator_json:
        emit_public_json(public_card)
    else:
        emit_public_text(render_text(public_card), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
