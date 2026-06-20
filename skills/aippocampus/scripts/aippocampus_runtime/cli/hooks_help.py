"""Help text for the AIppocampus hook command family."""

from __future__ import annotations

import sys
from typing import TextIO


def hooks_help_request(args: list[str]) -> bool:
    if args in (["--help"], ["-h"]):
        return True
    return (
        bool(args)
        and args[0] in {"prompt", "lifecycle", "action", "claude-code"}
        and any(arg in {"--help", "-h"} for arg in args[1:])
    )


def hooks_help_kind(args: list[str]) -> str | None:
    if len(args) >= 3 and args[0] == "action" and args[1] == "refresh-cache":
        return "action-refresh-cache"
    if len(args) >= 3 and args[0] in {"prompt", "lifecycle", "action"} and args[1] in {
        "install",
        "uninstall",
    }:
        return f"{args[0]}-{args[1]}"
    if len(args) >= 2 and args[0] in {"prompt", "lifecycle", "action", "claude-code"}:
        return args[0]
    return None


def print_hooks_help(kind: str | None = None, *, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    if kind == "prompt-install":
        print("usage: aippocampus hooks prompt install [options]", file=target)
        print("", file=target)
        print("Prompt hook install boundary:", file=target)
        print("  Writes/merges the Codex UserPromptSubmit hook entry for ambient recall.", file=target)
        print("  Does not install provider keys, rewrite transcripts, or enable heavy maintenance.", file=target)
        print("  The hook reads the current prompt and emits only a small route/action hint when useful.", file=target)
        print("", file=target)
        print("Before/after:", file=target)
        print("  aippocampus hooks prompt status --last", file=target)
        print("  aippocampus hooks prompt install --json", file=target)
        print("  aippocampus hooks prompt uninstall --json", file=target)
        print("  Ordinary recall still works without this hook: aippocampus agent recall \"old cue\" --json", file=target)
        return
    if kind == "prompt-uninstall":
        print("usage: aippocampus hooks prompt uninstall [options]", file=target)
        print("", file=target)
        print("Prompt hook rollback boundary:", file=target)
        print("  Removes the AIppocampus UserPromptSubmit hook entry from Codex hook config.", file=target)
        print("  Does not delete clean source, indexes, registry data, or provider configuration.", file=target)
        print("", file=target)
        print("Check:", file=target)
        print("  aippocampus hooks prompt status --last", file=target)
        print("  aippocampus hooks prompt uninstall --json", file=target)
        return
    if kind == "lifecycle-install":
        print("usage: aippocampus hooks lifecycle install [options]", file=target)
        print("", file=target)
        print("Lifecycle hook install boundary:", file=target)
        print("  Writes/merges Codex session lifecycle hooks for bounded local maintenance.", file=target)
        print("  Does not cold-archive, delete, run full Graphify, or install provider keys.", file=target)
        print("  Runtime work is limited to start/stop/compact upkeep such as clean source and indexes.", file=target)
        print("", file=target)
        print("Before/after:", file=target)
        print("  aippocampus hooks lifecycle status --json", file=target)
        print("  aippocampus hooks lifecycle install --json", file=target)
        print("  aippocampus hooks lifecycle uninstall --json", file=target)
        return
    if kind == "lifecycle-uninstall":
        print("usage: aippocampus hooks lifecycle uninstall [options]", file=target)
        print("", file=target)
        print("Lifecycle hook rollback boundary:", file=target)
        print("  Removes AIppocampus lifecycle hook entries from Codex hook config.", file=target)
        print("  Does not delete generated memory artifacts or source registries.", file=target)
        print("", file=target)
        print("Check:", file=target)
        print("  aippocampus hooks lifecycle status --json", file=target)
        print("  aippocampus hooks lifecycle uninstall --json", file=target)
        return
    if kind == "action-install":
        print("usage: aippocampus hooks action install [--cache-jsonl PATH] [options]", file=target)
        print("", file=target)
        print("Action-time hook install boundary:", file=target)
        print("  Writes/merges the optional Codex PreToolUse action-hint hook entry.", file=target)
        print("  Reads a prepared public-safe hint cache; it does not mine private history at tool time.", file=target)
        print("  Default cache: .aippocampus/action-hints/pretooluse-cache.jsonl", file=target)
        print("  Prepare or refresh the cache first when status says it is missing/stale.", file=target)
        print("", file=target)
        print("Before/after:", file=target)
        print("  aippocampus hooks action status --json", file=target)
        print("  aippocampus hooks action refresh-cache --write --json", file=target)
        print("  aippocampus hooks action install --json", file=target)
        print("  aippocampus hooks action uninstall --json", file=target)
        return
    if kind == "action-uninstall":
        print("usage: aippocampus hooks action uninstall [options]", file=target)
        print("", file=target)
        print("Action-time hook rollback boundary:", file=target)
        print("  Removes the AIppocampus PreToolUse action-hint hook entry.", file=target)
        print("  Does not delete the prepared hint cache or recall registry.", file=target)
        print("", file=target)
        print("Check:", file=target)
        print("  aippocampus hooks action status --json", file=target)
        print("  aippocampus hooks action uninstall --json", file=target)
        return
    if kind == "prompt":
        print("usage: aippocampus hooks prompt [status|install|uninstall] [options]", file=target)
        print("", file=target)
        print("Prompt hook: Codex UserPromptSubmit ambient recall affordances.", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks prompt status --last", file=target)
        print("  aippocampus hooks prompt install --json", file=target)
        print("  aippocampus hooks prompt uninstall --json", file=target)
        return
    if kind == "lifecycle":
        print("usage: aippocampus hooks lifecycle [status|install|uninstall] [options]", file=target)
        print("", file=target)
        print("Lifecycle hooks: Codex session maintenance on start/stop/compact events.", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks lifecycle status --json", file=target)
        print("  aippocampus hooks lifecycle install --json", file=target)
        print("  aippocampus hooks lifecycle uninstall --json", file=target)
        return
    if kind == "action":
        print("usage: aippocampus hooks action [status|install|uninstall|refresh-cache] [options]", file=target)
        print("", file=target)
        print("Action-time hints: optional PreToolUse nudges backed by a prepared cache.", file=target)
        print("Default cache: .aippocampus/action-hints/pretooluse-cache.jsonl", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks action status --json", file=target)
        print("  aippocampus hooks action refresh-cache --write --json", file=target)
        print("  aippocampus hooks action install --json", file=target)
        print("  aippocampus hooks action uninstall --json", file=target)
        return
    if kind == "action-refresh-cache":
        print(
            "usage: aippocampus hooks action refresh-cache [--cache-jsonl PATH] [--write] [--json]",
            file=target,
        )
        print("", file=target)
        print("Refresh the optional action-time hint cache from public-safe learning findings.", file=target)
        print("Default cache: .aippocampus/action-hints/pretooluse-cache.jsonl", file=target)
        print("Default is a dry run; add --write to update the local cache.", file=target)
        print("", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks action refresh-cache --json", file=target)
        print("  aippocampus hooks action refresh-cache --write --json", file=target)
        return
    if kind == "claude-code":
        print(
            "usage: aippocampus hooks claude-code "
            "[status|dry-run|install|uninstall|smoke] [options]",
            file=target,
        )
        print("", file=target)
        print("Claude Code hook helper: scoped UserPromptSubmit/Stop handlers.", file=target)
        print("Install/uninstall mutate only AIppocampus-owned Claude settings entries.", file=target)
        print("Codex prompt/lifecycle hook installers stay Codex-only.", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks claude-code status --json", file=target)
        print("  aippocampus hooks claude-code dry-run --json", file=target)
        print("  aippocampus hooks claude-code install --json", file=target)
        print("  aippocampus hooks claude-code uninstall --json", file=target)
        print("  aippocampus hooks claude-code smoke --json", file=target)
        return
    print("usage: aippocampus hooks [prompt|lifecycle|action|claude-code] ...", file=target)
    print("", file=target)
    print("Hook families:", file=target)
    print("  prompt       Codex UserPromptSubmit recall affordance hook", file=target)
    print("  lifecycle    Codex session maintenance hooks", file=target)
    print("  action       Optional PreToolUse action-time hints and cache refresh", file=target)
    print("  claude-code  Scoped Claude Code UserPromptSubmit/Stop hook helper", file=target)
    print("", file=target)
    print("Examples:", file=target)
    print("  aippocampus hooks prompt status --last", file=target)
    print("  aippocampus hooks lifecycle status --json", file=target)
    print("  aippocampus hooks action status --json", file=target)
    print("  aippocampus hooks action refresh-cache --write --json", file=target)
