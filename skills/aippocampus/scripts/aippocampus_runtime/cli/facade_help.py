"""Human help text owned outside the CLI dispatcher."""

from __future__ import annotations

import argparse
import sys
from typing import TextIO


def print_version_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus version [--json]", file=target)
    print("", file=target)
    print("Show the active AIppocampus runtime and release metadata version.", file=target)
    print("Use --json for a bounded machine-readable version/source summary.", file=target)


def print_config_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus config [describe KNOB] [--resolved] [--json|--compact-json]", file=target)
    print("", file=target)
    print("Config recovery card:", file=target)
    print("  Default output lists the readable knob catalog without printing configured values.", file=target)
    print("  --resolved may print safe non-sensitive values; secrets and local paths stay redacted.", file=target)
    print("  This is the natural shortcut to the safe config doctor, not a second config source.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus config", file=target)
    print("  aippocampus config describe AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS --resolved", file=target)
    print("  aippocampus config --compact-json", file=target)
    print("  aippocampus doctor config --json", file=target)



def print_repro_package_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus repro package [-h] [--input-json INPUT_JSON]", file=target)
    print("                                  [--stdin] [--template]", file=target)
    print("                                  [--version VERSION]", file=target)
    print("                                  [--commit COMMIT]", file=target)
    print("                                  [--plugin-manifest-version PLUGIN_MANIFEST_VERSION]", file=target)
    print("                                  [--json]", file=target)
    print("", file=target)
    print("Create a public-safe command/output issue package.", file=target)
    print("Primary path: aippocampus repro package --input-json command-output.json --json", file=target)
    print("Portable stdin example: cat command-output.json | aippocampus repro package --stdin --json", file=target)
    print("", file=target)
    print("Options:", file=target)
    print("  -h, --help", file=target)
    print("  --input-json INPUT_JSON", file=target)
    print("  --stdin", file=target)
    print("  --template", file=target)
    print("  --version VERSION", file=target)
    print("  --commit COMMIT", file=target)
    print("  --plugin-manifest-version PLUGIN_MANIFEST_VERSION", file=target)
    print("  --json", file=target)


def print_status_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus health [--json|--agent-json]", file=target)
    print("alias: aippocampus status [--json|--agent-json]", file=target)
    print("", file=target)
    print("Status decision card:", file=target)
    print("  pulse: one-line readiness; status: summary/current posture; health: full diagnostics/operator view.", file=target)
    print("  Use health when you need one-screen readiness and a next action.", file=target)
    print("  Use update status when checking installed skill/plugin/hook freshness.", file=target)
    print("  Use operator diagnostics only when repairing local artifacts.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus status", file=target)
    print("  aippocampus health --json", file=target)
    print("  aippocampus update status --json", file=target)


def print_plugin_status_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus plugin status [--json|--operator-json]", file=target)
    print("", file=target)
    print("Plugin status readiness card:", file=target)
    print("  Checks whether the local Codex plugin package/cache and host-visible tools look fresh.", file=target)
    print("  It is a plugin-shaped shortcut to update status, not a plugin install or hook enablement command.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus plugin status --json", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("  aippocampus update status --json", file=target)



def print_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    parser = argparse.ArgumentParser(
        prog="aippocampus",
        description="Unified facade for AIppocampus personal and operator commands.",
        add_help=False,
    )
    parser.print_usage(target)
    print("", file=target)
    print("Start here:", file=target)
    print("  aippocampus pulse --json              Quickest readiness pulse and next action", file=target)
    print("  aippocampus start --json              Choose the first useful continuity path", file=target)
    print("  aippocampus agent recall \"old cue\" --json", file=target)
    print("                                        Continue old work from source routes", file=target)
    print(
        "  aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json",
        file=target,
    )
    print("                                        Reopen the selected route before claims", file=target)
    print("  aippocampus search \"exact phrase\"      Exact wording fallback/demo", file=target)
    print("  aippocampus maintenance plan --summary-json", file=target)
    print("                                        Inspect maintenance when pulse/start points there", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("                                        Local Codex plugin install/refresh", file=target)
    print("", file=target)
    print("Recovery/readiness:", file=target)
    print("  aippocampus health                    Use when source is missing/stale, host tools feel", file=target)
    print("                                        installed-but-not-alive, or maintenance pressure matters", file=target)
    print("", file=target)
    print("Intent gradients:", file=target)
    print("  pulse -> one-line readiness; status/start -> summary/current posture; health -> diagnostics/operator view", file=target)
    print("  pause -> temporary/route-scoped quieting; do-not-use-here -> current-scope exclusion; forget -> explicit target workflow", file=target)
    print("  agent recall -> fuzzy continuity route finding; search -> exact/source wording", file=target)
    print("", file=target)
    print("Commands:", file=target)
    print("", file=target)
    print("Personal path:", file=target)
    print("  start               First useful continuity-path chooser", file=target)
    print("  pulse               One-line green/yellow/red readiness pulse", file=target)
    print("  health              Run runtime health checks", file=target)
    print("  version             Show active runtime and release metadata version", file=target)
    print("  onboard             Check/register provider-backed clean source", file=target)
    print("  search              Search current clean source, or --all registered sources", file=target)
    print("  registry            Inspect/search the local source registry", file=target)
    print("  agent recall        Agent continuity pull path: recall/AIppo/deepen/explain", file=target)
    print("  learning            Source-backed learning loop status/replay/guidance", file=target)
    print("  repro package       Public-safe command/output issue package", file=target)
    print("  do-not-use-here     Route-suppression / bad-route feedback card", file=target)
    print("  pause / forget      Safe personal-control cards, no destructive defaults", file=target)
    print("  latest-reply        Latest final assistant closeout, not commentary", file=target)
    print("  self-note append    Add a voluntary foreground-agent margin note", file=target)
    print("  vault sync          Build a local human-readable vault/dashboard", file=target)
    print("  continuity-domain   Explicitly produce/append source-trailed domains", file=target)
    print("  questions status    Read source-backed question tracking status", file=target)
    print("  work-guard          Agent issue-work active-pull orientation packet", file=target)
    print("  update status       Check personal core/magic readiness", file=target)
    print("  export              Export a portable AIppocampus bundle", file=target)
    print("  import              Import a portable AIppocampus bundle", file=target)
    print("  import conversation Register an explicit provider transcript", file=target)
    print("", file=target)
    print("Advanced/operator diagnostics:", file=target)
    print("  doctor provider     Check live-provider env visibility", file=target)
    print("  doctor config       Report registered env config without values", file=target)
    print("  doctor spend        Report local model spend/yield diagnostics", file=target)
    print("  mcp status          Compact MCP tool readiness", file=target)
    print("  mcp list-tools      List full MCP schemas; use mcp status for compact readiness", file=target)
    print("  smoke recall-funnel Run a progressive recall funnel diagnostic", file=target)
    print("  observatory         Route-readiness dashboard for source/route health, read-only", file=target)
    print("  episode-arcs        Conversation sequence and continuity-arc read model", file=target)
    print("  navigate            Navigation-sidecar boundary card for source route choice", file=target)
    print("  telepathy           Local handoff coordination records for agent continuity", file=target)
    print("  logs status/rotate  Inspect or apply bounded local log retention", file=target)
    print("  maintenance         Run bounded local maintenance", file=target)
    print("  warm status         Inspect warm ambient queue without model calls", file=target)
    print("  dream status        Background inference candidates, status only", file=target)
    print("  storage gc          Plan storage cleanup from existing evidence", file=target)
    print("  why-recall          Explain why a recall route surfaced or degraded", file=target)
    print("  why-not             Alias for why-not-recall", file=target)
    print("  why-not-recall      Explain why a recall route stayed silent", file=target)
    print("  sync                Local-folder sync status/push/pull/repair", file=target)
    print("  object-sync         Object-storage sync status/push/pull/repair", file=target)
    print("  plugin install      Install/verify the local Codex plugin", file=target)
    print("  uninstall           Inventory or purge AIppocampus-owned local artifacts", file=target)
    print(
        "  hooks [kind]        Host hook status/install/uninstall surfaces (prompt/lifecycle/action)",
        file=target,
    )
    print(
        "  hooks action refresh-cache  Materialize prepared action hints for the hot hook",
        file=target,
    )
    print("", file=target)
    print("All commands run packaged entrypoints and preserve their output and exit code.", file=target)
