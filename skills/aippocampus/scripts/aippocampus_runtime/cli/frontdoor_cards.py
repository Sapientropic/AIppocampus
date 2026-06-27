"""Human frontdoor and recovery cards for bare CLI parent commands."""

from __future__ import annotations

import sys
from typing import TextIO


def print_storage_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus storage", file=target)
    print("decision: choose an explicit storage action", file=target)
    print("why: bare storage should not dump a long cleanup candidate list.", file=target)
    print("next: aippocampus storage gc --dry-run --summary-json --cwd .", file=target)
    print("audit: aippocampus storage gc --dry-run --json --top 1 --cwd .", file=target)
    print(
        "apply: aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
        file=target,
    )
    print("boundary: cleanup is explicit operator work; dry-run before apply.", file=target)


def print_import_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus import", file=target)
    print("decision: choose bundle import or transcript registration", file=target)
    print("bundle: aippocampus import <bundle.zip> --dest <folder>", file=target)
    print(
        "transcript: aippocampus import conversation --format generic-jsonl --input <file> --dry-run --json",
        file=target,
    )
    print(
        "boundary: no write happens from the bare chooser; preview transcript imports before registering new source.",
        file=target,
    )


def print_doctor_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus doctor", file=target)
    print("decision: pick the health question first", file=target)
    print("preflight: aippocampus doctor preflight --json\nprovider: aippocampus doctor provider --json", file=target)
    print("config: aippocampus doctor config --compact-json", file=target)
    print("spend: aippocampus doctor spend --json", file=target)
    print("boundary: doctor output is local diagnostics, not a recall result.", file=target)


def print_first_run_setup_card(kind: str, *, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    title = "First-run install card" if kind == "install" else "First-run setup card"
    print(f"AIppocampus {kind}", file=target)
    print(title + ":", file=target)
    print("  Goal: make the local Codex/CLI surface callable, then see one source-backed recall/search result.", file=target)
    print("", file=target)
    print("Ordinary Codex path:", file=target)
    print("  aippocampus start --json", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("  aippocampus update status --json", file=target)
    print('  aippocampus agent recall "old decision or handoff cue" --json', file=target)
    print("", file=target)
    print("No installed command yet:", file=target)
    print("  uvx aippocampus --help", file=target)
    print("  uvx aippocampus onboard --provider auto --status", file=target)
    print("", file=target)
    print("Boundary: setup does not copy private memory, enable hooks, or configure provider keys unless you run those explicit commands.", file=target)


def print_memory_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus memory", file=target)
    print("Memory action card:", file=target)
    print("  Use source-backed recall/search for facts; use self-notes only as weak direction.", file=target)
    print("", file=target)
    print("Recall/search:", file=target)
    print('  aippocampus agent recall "old decision or handoff cue" --json', file=target)
    print('  aippocampus search "exact phrase" --json', file=target)
    print("  aippocampus latest-reply --cwd .", file=target)
    print("", file=target)
    print("Weak or route-only lanes:", file=target)
    print("  aippocampus self-note list --json", file=target)
    print("  aippocampus continuity-domain latest --json", file=target)
    print("Boundary: reopen/deepen clean source before quoting or making source-backed claims.", file=target)



def print_privacy_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus privacy", file=target)
    print("Privacy and control card:", file=target)
    print("  Defaults are read-only and redacted; destructive or private-path output is explicit operator work.", file=target)
    print("", file=target)
    print("Controls:", file=target)
    print("  aippocampus pause --json", file=target)
    print("  aippocampus forget --json", file=target)
    print("  aippocampus do-not-use-here --json", file=target)
    print("", file=target)
    print("Portability and credentials:", file=target)
    print("  aippocampus export --json", file=target)
    print("  aippocampus import --help", file=target)
    print("  aippocampus provider-key --json", file=target)
    print("Boundary: provider keys are optional; AIppocampus should still have a no-key source-backed path.", file=target)



def print_controls_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus controls", file=target)
    print("Personal controls card:", file=target)
    print("  Use these when you want less memory influence, narrower scope, or a route disabled here.", file=target)
    print("", file=target)
    print("Commands:", file=target)
    print("  aippocampus pause --json", file=target)
    print("  aippocampus forget --json", file=target)
    print("  aippocampus do-not-use-here --json", file=target)
    print("", file=target)
    print("Boundary: control commands do not delete private history by surprise; deletion/cleanup stays explicit.", file=target)
