#!/usr/bin/env python3
"""Provider-aware onboarding facade for AIppocampus."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

import onboard_codex

PROVIDER_ALIASES = {
    "auto": "codex",
    "codex": "codex",
}


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


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", default="auto")
    parser.add_argument("-h", "--help", action="store_true")
    known, remaining = parser.parse_known_args(raw_args)

    if known.help:
        print("usage: onboard.py [--provider auto|codex|claude-code] [onboard options]")
        print()
        print("Providers:")
        print("  auto         Use the default implemented provider for this install.")
        print("  codex        Onboard local Codex rollout JSONL sessions.")
        print("  claude-code  Reserved; transcript parser is not implemented yet.")
        print()
        print("Run onboard_codex.py --help for the current Codex onboarding options.")
        return 0

    provider = str(known.provider or "auto").strip().replace("_", "-").casefold()
    resolved = PROVIDER_ALIASES.get(provider)
    if resolved == "codex":
        return onboard_codex.main(remaining, provider_name="codex")

    error = _provider_error(provider)
    if _wants_json(raw_args) or not sys.stdout.isatty():
        print(json.dumps(error, ensure_ascii=False, indent=2))
    else:
        print(f"provider not available: {provider}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
