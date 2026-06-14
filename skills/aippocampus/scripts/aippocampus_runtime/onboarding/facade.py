#!/usr/bin/env python3
"""Provider-aware onboarding facade for AIppocampus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Sequence

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
    blockers: list[str] = []
    if resolved == "generic-jsonl" and not sessions:
        blockers.append("Set AIPPOCAMPUS_GENERIC_IMPORT_DIR to a generic JSONL file or directory.")
    return {
        "provider": resolved,
        "state": state if sessions or resolved == "codex" else "blocked",
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
    storage = aippocampus_registry_resolution()
    return {
        "ok": True,
        "data": {
            "provider_scope": provider_scope,
            "providers": providers,
            "state_legend": {
                "discovery_only": "Provider can list local transcripts but cannot safely build clean source yet.",
                "dry_run": "Provider can preview planned registration without writing.",
                "write_enabled": "Provider has a clean-source parser and can write registry artifacts when explicitly run.",
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


def render_status_text(report: dict) -> str:
    lines = ["AIppocampus provider status"]
    provider_scope = report.get("data", {}).get("provider_scope")
    if provider_scope and provider_scope != "auto":
        lines.append(f"provider scope: {provider_scope}")
    for item in report.get("data", {}).get("providers", []):
        blockers = item.get("blockers") or []
        suffix = f" | blocker: {blockers[0]}" if blockers else ""
        lines.append(
            "- {provider}: {state} | detected={detected} | transcripts={count} | "
            "current_cwd_match={match}{suffix}".format(
                provider=item.get("provider"),
                state=item.get("state"),
                detected=str(bool(item.get("detected"))).lower(),
                count=item.get("transcript_count_label", item.get("transcript_count", 0)),
                match=str(bool(item.get("current_cwd_match"))).lower(),
                suffix=suffix,
            )
        )
        if item.get("scan_status") == "partial_frontstage_sample":
            lines.append("  scan: partial frontstage sample; use --json for operator inventory")
    auto = report.get("data", {}).get("auto", {})
    if provider_scope in {None, "auto"}:
        lines.append(f"auto: {auto.get('default_provider')} - {auto.get('why')}")
    storage = report.get("data", {}).get("storage") or {}
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
    parser.add_argument("-h", "--help", action="store_true")
    known, remaining = parser.parse_known_args(raw_args)

    if known.help:
        print("usage: aippocampus onboard [--status] [--provider auto|codex|claude-code|generic-jsonl] [onboard options]")
        print()
        print("Providers:")
        print("  auto         Use the default implemented provider for this install.")
        print("  codex        Onboard local Codex rollout JSONL sessions.")
        print("  claude-code  Onboard local Claude Code JSONL transcripts.")
        print("  generic-jsonl Onboard validated AIppocampus generic JSONL imports.")
        print()
        print("Provider key bridge:")
        print("  provider-key  Plan/apply/undo an explicit provider key bridge for Codex hooks.")
        print()
        print("Run with --provider codex --help for the current Codex onboarding options.")
        return 0

    if known.status:
        detailed = bool(known.details or known.json_output or known.format == "json")
        report = provider_status_report(
            provider=known.provider,
            cwd=_arg_value(raw_args, "--cwd"),
            detailed=detailed,
        )
        wants_json = (
            known.json_output
            or known.format == "json"
        )
        if wants_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_status_text(report))
        return 0

    if remaining and remaining[0] == "provider-key":
        provider_key_args = remaining[1:]
        if known.json_output and "--json" not in provider_key_args:
            provider_key_args.append("--json")
        return provider_key_bridge.main(provider_key_args)

    provider = str(known.provider or "auto").strip().replace("_", "-").casefold()
    resolved = normalize_provider_name(provider)
    if resolved == "codex":
        return onboard_codex.main(
            remaining,
            provider_name="codex",
            provider=create_conversation_provider("codex", codex_home_dir=codex_home()),
        )
    if resolved == "claude-code":
        return onboard_codex.main(
            remaining,
            provider_name="claude-code",
            provider=create_conversation_provider("claude-code"),
        )
    if resolved == "generic-jsonl":
        return onboard_codex.main(
            remaining,
            provider_name="generic-jsonl",
            provider=create_conversation_provider("generic-jsonl"),
        )

    error = _provider_error(provider)
    if _wants_json(raw_args) or not sys.stdout.isatty():
        print(json.dumps(error, ensure_ascii=False, indent=2))
    else:
        print(f"provider not available: {provider}", file=sys.stderr)
    return 2


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
