#!/usr/bin/env python3
"""Provider-aware onboarding facade for AIppocampus."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from aippocampus_runtime.core import aippocampus_registry_resolution, codex_home
from aippocampus_runtime.onboarding import codex as onboard_codex
from conversation_sources import create_conversation_provider, normalize_provider_name


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


def _provider_capability(provider: str, *, cwd: str | None = None) -> dict:
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

    sessions = list(instance.discover_sessions())
    current_match = False
    if cwd:
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
        "current_cwd_match": current_match,
        "dry_run_available": True,
        "write_registration_available": write_enabled,
        "mcp_available": True,
        "blockers": blockers,
    }


def provider_status_report(cwd: str | None = None) -> dict:
    providers = [
        _provider_capability("codex", cwd=cwd),
        _provider_capability("claude-code", cwd=cwd),
        _provider_capability("generic-jsonl", cwd=cwd),
    ]
    return {
        "ok": True,
        "data": {
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
            "storage": aippocampus_registry_resolution(),
        },
        "meta": {"facade": "onboard.py", "schema_version": 1},
    }


def render_status_text(report: dict) -> str:
    lines = ["AIppocampus provider status"]
    for item in report.get("data", {}).get("providers", []):
        blockers = item.get("blockers") or []
        suffix = f" | blocker: {blockers[0]}" if blockers else ""
        lines.append(
            "- {provider}: {state} | detected={detected} | transcripts={count} | "
            "current_cwd_match={match}{suffix}".format(
                provider=item.get("provider"),
                state=item.get("state"),
                detected=str(bool(item.get("detected"))).lower(),
                count=item.get("transcript_count", 0),
                match=str(bool(item.get("current_cwd_match"))).lower(),
                suffix=suffix,
            )
        )
    auto = report.get("data", {}).get("auto", {})
    lines.append(f"auto: {auto.get('default_provider')} - {auto.get('why')}")
    storage = report.get("data", {}).get("storage") or {}
    if storage:
        legacy = " legacy fallback" if storage.get("legacy_fallback") else ""
        lines.append(f"registry: {storage.get('path')} ({storage.get('source')}{legacy})")
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
    parser.add_argument("-h", "--help", action="store_true")
    known, remaining = parser.parse_known_args(raw_args)

    if known.help:
        print("usage: onboard.py [--status] [--provider auto|codex|claude-code|generic-jsonl] [onboard options]")
        print()
        print("Providers:")
        print("  auto         Use the default implemented provider for this install.")
        print("  codex        Onboard local Codex rollout JSONL sessions.")
        print("  claude-code  Onboard local Claude Code JSONL transcripts.")
        print("  generic-jsonl Onboard validated AIppocampus generic JSONL imports.")
        print()
        print("Run onboard_codex.py --help for the current Codex onboarding options.")
        return 0

    if known.status:
        report = provider_status_report(cwd=_arg_value(raw_args, "--cwd"))
        wants_json = (
            known.json_output
            or known.format == "json"
            or (known.format == "auto" and not sys.stdout.isatty())
        )
        if wants_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_status_text(report))
        return 0

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
