#!/usr/bin/env python3
"""Provider-aware onboarding facade for AIppocampus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Sequence

from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import aippocampus_registry_resolution, codex_home
from aippocampus_runtime.legacy_aliases import legacy_alias_diagnostics
from aippocampus_runtime.onboarding import codex as onboard_codex
from aippocampus_runtime.ops import provider_key_bridge
from conversation_sources import (
    ConversationProvider,
    create_conversation_provider,
    normalize_provider_name,
)


def _wants_json(argv: Sequence[str]) -> bool:
    return "--json" in argv or any(
        arg == "--format=json" or (arg == "--format" and idx + 1 < len(argv) and argv[idx + 1] == "json")
        for idx, arg in enumerate(argv)
    )


def _provider_error(provider: str) -> dict:
    return {
        "ok": False,
        "error": {
            "code": "provider_not_available",
            "provider": provider,
            "message": (
                "This conversation provider is not implemented yet. "
                "Verify the host transcript schema first, then add a provider without changing "
                "AIppocampus registry storage defaults."
            ),
        },
        "meta": {"facade": "onboard.py", "provider": provider},
    }


def _provider_registration_error(provider: str) -> dict:
    return {
        "ok": False,
        "error": {
            "code": "provider_registration_not_available",
            "provider": provider,
            "message": (
                "This provider can be discovered in dry-run mode, but clean-source "
                "registration is not enabled until its transcript parser is wired."
            ),
        },
        "meta": {"facade": "onboard.py", "provider": provider},
    }


FRONTSTAGE_PROVIDER_SAMPLE_LIMIT = 3
FRONTSTAGE_PROVIDER_SCAN_BUDGET_SECONDS = 0.75
SEARCH_EXISTING_MEMORY_COMMAND_TEMPLATE = 'aippocampus search "{exact_phrase}" --json'
GENERIC_JSONL_IMPORT_PREVIEW_COMMAND_TEMPLATE = (
    'aippocampus import conversation --format generic-jsonl --input "{input_path}" --dry-run --json'
)


def _provider_write_command(provider: str) -> str | None:
    clean_provider = normalize_provider_name(str(provider or "").strip().replace("_", "-").casefold())
    if clean_provider in {"codex", "claude-code"}:
        return f"aippocampus onboard --provider {clean_provider} --cwd . --json"
    if clean_provider == "generic-jsonl":
        return 'aippocampus import conversation --format generic-jsonl --input "{input_path}" --json'
    return None


def _frontstage_state_from_machine_state(state: str) -> str:
    if state == "write_enabled":
        return "registration_available_after_consent"
    if state == "dry_run":
        return "preview_available"
    return state or "unknown"


def _sample_sessions(instance: ConversationProvider, *, detailed: bool) -> tuple[list[object], bool]:
    if detailed:
        return list(instance.discover_sessions()), True
    sessions: list[object] = []
    deadline = time.monotonic() + FRONTSTAGE_PROVIDER_SCAN_BUDGET_SECONDS
    complete = True
    iterator = iter(instance.discover_sessions())
    while len(sessions) <= FRONTSTAGE_PROVIDER_SAMPLE_LIMIT:
        if time.monotonic() > deadline:
            complete = False
            break
        try:
            sessions.append(next(iterator))
        except StopIteration:
            break
    else:
        complete = False
    if len(sessions) > FRONTSTAGE_PROVIDER_SAMPLE_LIMIT:
        complete = False
        sessions = sessions[:FRONTSTAGE_PROVIDER_SAMPLE_LIMIT]
    return sessions, complete


def _provider_capability(provider: str, *, cwd: str | None = None, detailed: bool = False) -> dict:
    resolved = normalize_provider_name(provider)
    try:
        instance = create_conversation_provider(resolved, codex_home_dir=codex_home())
    except Exception as exc:
        return {
            "provider": resolved,
            "state": "blocked",
            "detected": False,
            "transcript_count": 0,
            "current_cwd_match": False,
            "dry_run_available": False,
            "write_registration_available": False,
            "mcp_available": False,
            "blockers": [str(exc)[:220]],
        }

    sessions, scan_complete = _sample_sessions(instance, detailed=detailed)
    current_match = False
    if cwd and detailed:
        try:
            instance.locate_current(cwd)
            current_match = True
        except Exception:
            current_match = False
    write_enabled = resolved in {"codex", "claude-code", "generic-jsonl"}
    state = "write_enabled" if write_enabled else "dry_run"
    machine_state = state if sessions or resolved == "codex" else "blocked"
    blockers: list[str] = []
    if resolved == "generic-jsonl" and not sessions:
        blockers.append("Set AIPPOCAMPUS_GENERIC_IMPORT_DIR to a generic JSONL file or directory.")
    return {
        "provider": resolved,
        "state": machine_state,
        "frontstage_state": _frontstage_state_from_machine_state(machine_state),
        "detected": bool(sessions),
        "transcript_count": len(sessions),
        "transcript_count_exact": bool(detailed and scan_complete),
        "transcript_count_label": str(len(sessions))
        if scan_complete
        else f"{len(sessions)}+",
        "scan_status": "complete" if scan_complete else "partial_frontstage_sample",
        "current_cwd_match": current_match,
        "dry_run_available": True,
        "write_registration_available": write_enabled,
        "mcp_available": True,
        "blockers": blockers,
    }


def _status_provider_scope(provider: str | None) -> tuple[str, list[str]]:
    raw = (provider or "auto").strip().replace("_", "-").casefold()
    if raw == "auto":
        return "auto", ["codex", "claude-code", "generic-jsonl"]
    resolved = normalize_provider_name(raw)
    return resolved, [resolved]


def provider_status_report(
    provider: str | None = "auto",
    cwd: str | None = None,
    *,
    detailed: bool = False,
) -> dict:
    provider_scope, provider_names = _status_provider_scope(provider)
    providers = [_provider_capability(name, cwd=cwd, detailed=detailed) for name in provider_names]
    providers = [_with_provider_next_action(item) for item in providers]
    primary_next_action = _provider_status_primary_decision(providers, provider_scope)
    storage = aippocampus_registry_resolution()
    return {
        "ok": True,
        "foreground_guidance": primary_next_action["foreground_guidance"],
        "primary_next_action": primary_next_action,
        "data": {
            "provider_scope": provider_scope,
            "providers": providers,
            "primary_next_action": primary_next_action,
            "next_actions": _provider_status_next_actions(providers),
            "state_legend": {
                "discovery_only": "Provider can list local transcripts but cannot safely build clean source yet.",
                "dry_run": "Provider can preview planned registration without writing.",
                "write_enabled": "Machine state: registration is available only when an explicit onboarding command is run.",
                "registration_available_after_consent": "Frontstage state: registration can be previewed and written only after explicit consent.",
                "blocked": "Provider is missing, not configured, or has no discoverable transcripts.",
            },
            "auto": {
                "default_provider": "codex",
                "why": "auto keeps the safest fully implemented default and lists other providers separately.",
            },
            "storage": storage,
            "legacy_aliases": legacy_alias_diagnostics(registry_resolution=storage),
            "detail_level": "operator" if detailed else "frontstage",
        },
        "meta": {"facade": "onboard.py", "schema_version": 1},
    }


def _with_provider_next_action(item: dict) -> dict:
    provider = str(item.get("provider") or "auto")
    state = str(item.get("state") or "")
    detected = bool(item.get("detected"))
    current_match = bool(item.get("current_cwd_match"))
    dry_run = bool(item.get("dry_run_available"))
    public = dict(item)
    if provider == "generic-jsonl":
        public["next_action_code"] = (
            "import_conversation_preview"
            if detected and state != "blocked"
            else "generic_import_needs_input"
        )
        public["foreground_guidance"] = (
            "Generic JSONL is explicit file import. Use it when the user has an export "
            "file, preview the import path, and avoid no-input provider scans."
        )
        public["preview_command_template"] = GENERIC_JSONL_IMPORT_PREVIEW_COMMAND_TEMPLATE
        public["requires"] = ["input_path"]
        public["broad_scan_boundary"] = (
            "file/input-shaped import only; not an ordinary no-input provider scan"
        )
        return public
    if detected and current_match:
        public["next_action_code"] = "try_search_existing_registry"
        public["foreground_guidance"] = (
            "Use `aippocampus search` or `aippocampus agent recall` for old/source-backed "
            "memory before previewing new registration."
        )
        public["search_command_template"] = SEARCH_EXISTING_MEMORY_COMMAND_TEMPLATE
        public["requires"] = ["exact_phrase"]
        return public
    if detected and not current_match and dry_run and state != "blocked":
        public["next_action_code"] = "preview_current_project_registration"
        public["foreground_guidance"] = (
            "History exists, but it does not appear to match the current project. Search old "
            "registered memory if the cue is global; otherwise preview current-project "
            "registration before writing."
        )
        public["search_command_template"] = SEARCH_EXISTING_MEMORY_COMMAND_TEMPLATE
        public["requires"] = ["exact_phrase"]
        public["preview_command"] = f"aippocampus onboard --provider {provider} --dry-run --json"
        public["broad_scan_boundary"] = (
            "dry-run may inspect local provider transcripts; preview before any registration write"
        )
        return public
    if not detected:
        public["next_action_code"] = "provider_not_detected"
        public["foreground_guidance"] = (
            "Use existing registered memory if available, configure this provider, or skip "
            "onboarding for this surface."
        )
        return public
    public["next_action_code"] = "preview_before_write"
    public["foreground_guidance"] = (
        "Preview registration with --dry-run before writing local clean-source history."
    )
    public["preview_command"] = f"aippocampus onboard --provider {provider} --dry-run --json"
    return public


def _provider_status_primary_decision(providers: list[dict], provider_scope: str) -> dict:
    if provider_scope == "generic-jsonl":
        return {
            "provider": "generic-jsonl",
            "code": "import_conversation_preview",
            "decision": "preview explicit generic JSONL import",
            "foreground_guidance": (
                "Use generic JSONL only when the user has an export file; preview "
                "that file import before writing."
            ),
            "command_template": GENERIC_JSONL_IMPORT_PREVIEW_COMMAND_TEMPLATE,
            "requires": ["input_path"],
            "broad_scan_boundary": (
                "generic JSONL is file/input-shaped, not a no-input foreground scan"
            ),
        }

    for item in providers:
        if item.get("current_cwd_match") and item.get("detected"):
            return {
                "provider": item.get("provider"),
                "code": "search_existing_registered_memory",
                "decision": "search existing registered memory first",
                "foreground_guidance": (
                    "Search existing source-backed memory for the cue before previewing "
                    "another registration write."
                ),
                "command_template": SEARCH_EXISTING_MEMORY_COMMAND_TEMPLATE,
                "requires": ["exact_phrase"],
            }

    for item in providers:
        provider = str(item.get("provider") or "")
        if provider == "generic-jsonl" or item.get("state") == "blocked":
            continue
        if item.get("dry_run_available"):
            return {
                "provider": provider,
                "code": "preview_current_project_registration",
                "decision": f"preview current-project registration with {provider}",
                "foreground_guidance": (
                    "Preview the best-fit local provider registration before writing "
                    "clean-source history."
                ),
                "command": f"aippocampus onboard --provider {provider} --dry-run --json",
            }

    return {
        "provider": "registry",
        "code": "search_existing_registered_memory",
        "decision": "search existing registered memory first",
        "foreground_guidance": (
            "Search existing registered memory first; configure or import a provider only "
            "if no source-backed result appears."
        ),
        "command_template": SEARCH_EXISTING_MEMORY_COMMAND_TEMPLATE,
        "requires": ["exact_phrase"],
    }


def _provider_status_next_actions(providers: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for item in providers:
        code = item.get("next_action_code")
        if not code:
            continue
        action = {
            "provider": item.get("provider"),
            "code": code,
            "foreground_guidance": item.get("foreground_guidance"),
        }
        for key in (
            "search_command",
            "search_command_template",
            "preview_command",
            "preview_command_template",
            "requires",
            "broad_scan_boundary",
        ):
            if item.get(key):
                action[key] = item[key]
        actions.append(action)
    return actions


def public_provider_status_report(report: dict, *, include_private_paths: bool = False) -> dict:
    if include_private_paths:
        return report
    public = dict(report)
    data = dict(public.get("data") or {})
    providers = []
    for item in data.get("providers") or []:
        provider = dict(item)
        provider.setdefault(
            "frontstage_state",
            _frontstage_state_from_machine_state(str(provider.get("state") or "")),
        )
        providers.append(provider)
    data["providers"] = providers
    storage = dict(data.get("storage") or {})
    if storage.get("path"):
        storage["path"] = "<local-path-redacted>"
        storage["path_redacted"] = True
    storage["paths_included"] = False
    data["storage"] = storage
    public["data"] = data
    return public


def compact_provider_status_card(report: dict) -> dict:
    """Return the default foreground setup chooser for auto onboarding.

    Operator status owns provider inventories, storage fallbacks, and legacy
    aliases. The ordinary auto-status JSON should answer only: what can be
    previewed now, what provider states matter, and where to go for detail.
    """

    data = report.get("data") or {}
    provider_scope = str(data.get("provider_scope") or "auto")
    primary = dict(data.get("primary_next_action") or report.get("primary_next_action") or {})
    provider_summary = []
    for item in data.get("providers") or []:
        state = _frontstage_state_label(item)
        provider = {
            "provider": item.get("provider"),
            "state": state,
            "frontstage_state": state,
            "detected": bool(item.get("detected")),
        }
        if item.get("transcript_count_label") is not None:
            provider["transcript_count_label"] = item.get("transcript_count_label")
        if item.get("scan_status") == "partial_frontstage_sample":
            provider["scan_status"] = "partial_frontstage_sample"
        if item.get("requires"):
            provider["requires"] = list(item.get("requires") or [])
        provider_summary.append(provider)

    primary_action = {
        key: primary[key]
        for key in (
            "provider",
            "code",
            "decision",
            "command",
            "command_template",
            "requires",
            "broad_scan_boundary",
        )
        if primary.get(key) not in (None, "", [])
    }
    primary_action.setdefault("id", str(primary_action.get("code") or "preview_registration"))
    primary_action["mutation_risk"] = "read_only"
    primary_action["claim_boundary"] = "setup_status_not_source_evidence"
    if primary_action.get("command_template"):
        primary_action["template_only"] = True
    write_command = _provider_write_command(str(primary.get("provider") or ""))
    if primary.get("code") == "preview_current_project_registration" and write_command:
        primary_action["write_command_after_preview"] = write_command
        primary_action["write_mutation_risk"] = "writes_local_clean_source"
        primary_action["write_boundary"] = (
            "run only after reviewing the dry-run preview and confirming this provider is the intended source"
        )

    status = "no_provider_available"
    if primary.get("code") == "preview_current_project_registration":
        status = "registration_available_after_consent"
    elif primary.get("code") == "import_conversation_preview":
        status = "explicit_file_import_requires_input"
    elif primary.get("code") == "search_existing_registered_memory":
        status = "existing_registry_search_available"

    return {
        "kind": "aippocampus_onboard_status_card",
        "ok": bool(report.get("ok", True)),
        "status": status,
        "surface_class": "foreground_chooser_card",
        "read_only": True,
        "provider_scope": provider_scope,
        "decision": primary.get("decision"),
        "primary_next_action": primary_action,
        **canonical_foreground_action_fields(primary_action, safe_next_actions=[primary_action]),
        "provider_summary": provider_summary,
        "operator_detail_command": (
            f"aippocampus onboard --provider {provider_scope} --status --operator-json"
        ),
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": True,
        },
        "output_boundary": "compact_setup_card_no_operator_inventory",
    }


def _frontstage_state_label(item: dict) -> str:
    return _frontstage_state_from_machine_state(
        str(item.get("frontstage_state") or item.get("state") or "")
    )


def render_status_text(report: dict) -> str:
    lines = ["AIppocampus provider status"]
    data = report.get("data", {})
    provider_scope = data.get("provider_scope")
    if provider_scope and provider_scope != "auto":
        lines.append(f"provider scope: {provider_scope}")
    primary = data.get("primary_next_action") or report.get("primary_next_action")
    if primary:
        lines.append(f"primary: {primary.get('decision')}")
        if primary.get("command"):
            lines.append(f"next command: {primary.get('command')}")
    for item in data.get("providers", []):
        blockers = item.get("blockers") or []
        suffix = f" | blocker: {blockers[0]}" if blockers else ""
        lines.append(
            "- {provider}: {state} | detected={detected} | transcripts={count} | "
            "current_cwd_match={match}{suffix}".format(
                provider=item.get("provider"),
                state=_frontstage_state_label(item),
                detected=str(bool(item.get("detected"))).lower(),
                count=item.get("transcript_count_label", item.get("transcript_count", 0)),
                match=str(bool(item.get("current_cwd_match"))).lower(),
                suffix=suffix,
            )
        )
        if item.get("scan_status") == "partial_frontstage_sample":
            lines.append("  scan: partial frontstage sample; use --operator-json for operator inventory")
        if item.get("foreground_guidance"):
            lines.append(f"  next: {item.get('foreground_guidance')}")
        if item.get("preview_command"):
            lines.append(f"  preview: {item.get('preview_command')}")
    auto = data.get("auto", {})
    if provider_scope in {None, "auto"}:
        lines.append(f"auto: {auto.get('default_provider')} - {auto.get('why')}")
    storage = data.get("storage") or {}
    if storage:
        legacy = " legacy fallback" if storage.get("legacy_fallback") else ""
        lines.append(f"registry configured ({storage.get('source')}{legacy})")
    lines.append("")
    lines.append("First recall")
    lines.append('- exact phrase: aippocampus search "distinctive old phrase"')
    lines.append('- project cue: aippocampus search "repo, feature, object, or topic"')
    lines.append('- time cue: aippocampus search "recent, last month, or a known date"')
    lines.append(
        "Boundary: project/time cues are candidate navigation until a source-backed snippet appears."
    )
    return "\n".join(lines)


def _is_dry_run(argv: Sequence[str]) -> bool:
    return "--dry-run" in argv or "--preview" in argv


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", default="auto")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--format", choices=["auto", "json", "text"], default="auto")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--details", action="store_true", help="Use the full operator inventory path for status.")
    parser.add_argument(
        "--operator-json",
        "--full-json",
        action="store_true",
        dest="operator_json",
        help="Emit the full operator provider inventory instead of the bounded frontstage status.",
    )
    parser.add_argument("--include-private-paths", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    known, remaining = parser.parse_known_args(raw_args)

    if remaining and remaining[0] == "provider-key":
        provider_key_args = remaining[1:]
        if known.help and "--help" not in provider_key_args and "-h" not in provider_key_args:
            provider_key_args.append("--help")
        if (known.json_output or known.operator_json) and "--json" not in provider_key_args:
            provider_key_args.append("--json")
        return provider_key_bridge.main(provider_key_args)

    if known.help:
        print("usage: aippocampus onboard [--status] [--provider auto|codex|claude-code|generic-jsonl] [onboard options]")
        print()
        print("Providers:")
        print("  auto         Show the provider matrix; default registration path stays Codex.")
        print("  codex        Onboard local Codex rollout JSONL sessions.")
        print("  claude-code  Onboard local Claude Code JSONL transcripts.")
        print("  generic-jsonl Onboard validated AIppocampus generic JSONL imports.")
        print()
        print("Provider key bridge:")
        print("  provider-key  Plan/apply/undo an explicit provider key bridge for Codex hooks.")
        print()
        print("Examples:")
        print("  aippocampus onboard --provider auto --status")
        print("  aippocampus onboard --provider codex --status --json")
        print("  aippocampus onboard --status --operator-json")
        print("  aippocampus import conversation --format generic-jsonl --input sessions.jsonl --dry-run --json")
        return 0

    # Bare/selector-only onboard is a foreground status card. Older behavior
    # could register or refresh local source just because an agent asked for
    # `onboard --json`; keep writes behind explicit provider sub-flags such as
    # --dry-run/--all/apply paths owned by the provider-specific onboarding CLI.
    selector_only = not remaining
    if known.status or selector_only:
        detailed = bool(known.details or known.operator_json)
        report = provider_status_report(
            provider=known.provider,
            cwd=_arg_value(raw_args, "--cwd"),
            detailed=detailed,
        )
        public_report = public_provider_status_report(
            report,
            include_private_paths=known.include_private_paths,
        )
        wants_json = (
            known.json_output
            or known.operator_json
            or known.format == "json"
        )
        if wants_json:
            output = (
                compact_provider_status_card(public_report)
                if not detailed
                else public_report
            )
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(render_status_text(public_report))
        return 0

    provider = str(known.provider or "auto").strip().replace("_", "-").casefold()
    resolved = normalize_provider_name(provider)
    provider_remaining = list(remaining)
    if (known.json_output or known.format == "json") and "--json" not in provider_remaining:
        provider_remaining.append("--json")
    if resolved == "codex":
        return onboard_codex.main(
            provider_remaining,
            provider_name="codex",
            provider=create_conversation_provider("codex", codex_home_dir=codex_home()),
        )
    if resolved == "claude-code":
        return onboard_codex.main(
            provider_remaining,
            provider_name="claude-code",
            provider=create_conversation_provider("claude-code"),
        )
    if resolved == "generic-jsonl":
        return onboard_codex.main(
            provider_remaining,
            provider_name="generic-jsonl",
            provider=create_conversation_provider("generic-jsonl"),
        )

    error = _provider_error(provider)
    if _wants_json(raw_args) or not sys.stdout.isatty():
        print(json.dumps(error, ensure_ascii=False, indent=2))
    else:
        print(f"provider not available: {provider}", file=sys.stderr)
    return exit_code_for_payload(error)


def _arg_value(argv: Sequence[str], name: str) -> str | None:
    for idx, arg in enumerate(argv):
        if arg == name and idx + 1 < len(argv):
            return argv[idx + 1]
        prefix = name + "="
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
