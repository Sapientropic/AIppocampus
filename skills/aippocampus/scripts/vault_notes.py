#!/usr/bin/env python3
"""Markdown note renderers for AIppocampus vault sync."""

from __future__ import annotations

import os
from pathlib import Path

from aippocampuslib import now_utc
from vault_sync_utils import DEFAULT_SITE_TITLE, format_frontmatter, safe_filename, wikilink


def anchor_note(anchor: dict, thread_home: Path, vault: Path) -> str:
    title = anchor.get("title") or "Untitled Anchor"
    keywords = anchor.get("keywords", [])
    notes = anchor.get("notes", [])
    quotes = anchor.get("quotes", [])
    sources = anchor.get("sources", [])
    lines = [
        format_frontmatter({
            "type": "codex-thread-anchor",
            "thread": str(thread_home.name),
            "tags": ["codex-memory", "thread-anchor"],
            "keywords": keywords,
        }).rstrip(),
        f"# {title}",
        "",
        f"Thread: {wikilink(thread_home / 'Thread Overview.md', vault, thread_home.name)}",
        "",
    ]
    if keywords:
        lines.extend(["## Keywords", "", ", ".join(f"`{k}`" for k in keywords), ""])
    if notes:
        lines.extend(["## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
        lines.append("")
    if quotes:
        lines.extend(["## Preserved Phrases", ""])
        lines.extend(f"> {quote}" for quote in quotes)
        lines.append("")
    if sources:
        lines.extend(["## Sources", ""])
        lines.extend(f"- `{source}`" for source in sources)
        lines.append("")
    return "\n".join(lines)


def health_note(health: dict, thread_home: Path, vault: Path) -> str:
    actions = health.get("recommended_actions", [])
    lines = [
        format_frontmatter({
            "type": "codex-thread-health",
            "thread": thread_home.name,
            "updated": now_utc(),
            "tags": ["codex-memory", "thread-health"],
        }).rstrip(),
        "# Memory Health",
        "",
        f"Thread: {wikilink(thread_home / 'Thread Overview.md', vault, thread_home.name)}",
        "",
        "## Status",
        "",
        f"- Overall: {'OK' if health.get('ok') else 'Needs maintenance'}",
        f"- Rollout messages: `{health.get('rollout', {}).get('message_count')}`",
        f"- Rollout size: `{health.get('rollout', {}).get('size')}` bytes",
        f"- Anchors: `{health.get('anchors', {}).get('count')}`",
        f"- Index stale: `{health.get('index', {}).get('stale')}`",
        f"- Checkpoint due: `{health.get('checkpoint', {}).get('due')}`",
        f"- Graphify corpus stale: `{health.get('graphify', {}).get('stale')}`",
        "",
        "## Recommended Actions",
        "",
    ]
    if actions:
        for item in actions:
            lines.append(f"- **{item.get('id')}** `{item.get('severity')}`: {item.get('reason')}")
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def checkpoint_note(state: dict, thread_home: Path, vault: Path) -> str:
    candidate = state.get("last_candidate") or {}
    lines = [
        format_frontmatter({
            "type": "codex-thread-checkpoint",
            "thread": thread_home.name,
            "updated": state.get("updated_at") or now_utc(),
            "tags": ["codex-memory", "checkpoint"],
        }).rstrip(),
        "# Latest Checkpoint",
        "",
        f"Thread: {wikilink(thread_home / 'Thread Overview.md', vault, thread_home.name)}",
        "",
    ]
    if not candidate:
        lines.append("No checkpoint candidate recorded yet.")
        return "\n".join(lines)
    lines.extend([
        f"## {candidate.get('title', 'Checkpoint Candidate')}",
        "",
        f"- Appended count: `{state.get('last_captured_message_count')}`",
        f"- Last checked count: `{state.get('last_checked_message_count')}`",
        f"- Line range: `{candidate.get('line_range', {}).get('start')}-{candidate.get('line_range', {}).get('end')}`",
        "",
        "## Keywords",
        "",
        ", ".join(f"`{k}`" for k in candidate.get("keywords", [])) or "- none",
        "",
        "## Notes",
        "",
    ])
    lines.extend(f"- {note}" for note in candidate.get("notes", []))
    if candidate.get("quotes"):
        lines.extend(["", "## Preserved Phrases", ""])
        lines.extend(f"> {quote}" for quote in candidate.get("quotes", []))
    lines.append("")
    return "\n".join(lines)


def heartbeat_note(thread_home: Path, vault: Path, cwd: Path, automation_name: str | None) -> str:
    lines = [
        format_frontmatter({
            "type": "codex-thread-heartbeat",
            "thread": thread_home.name,
            "updated": now_utc(),
            "tags": ["codex-memory", "heartbeat"],
        }).rstrip(),
        "# Heartbeat",
        "",
        f"Thread: {wikilink(thread_home / 'Thread Overview.md', vault, thread_home.name)}",
        "",
        "## Purpose",
        "",
        "- Wake this thread periodically.",
        "- Run memory health and threshold maintenance.",
        "- Refresh this vault dashboard.",
        "- Check external feedback sources when their connectors are available.",
        "",
        "## External Checks",
        "",
        "- Slack: skip unless the Slack connector is installed and authorized.",
        "- GitHub PRs: check through GitHub connector or `gh` when the target repo is known.",
        "- Feedback: record user-provided review comments, local TODOs, or linked issue summaries.",
        "",
        "## Automation",
        "",
    ]
    if automation_name:
        lines.append(f"- Suggested automation: `{automation_name}`")
    else:
        lines.append("- No Codex heartbeat automation has been created by this script.")
    lines.extend([
        "",
        "## Local Maintenance Command",
        "",
        "```powershell",
        f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\aippocampus_maintenance.py\" --cwd \"{cwd}\"",
        f"python \"$env:CODEX_HOME\\skills\\aippocampus\\scripts\\sync_vault.py\" --cwd \"{cwd}\" --vault \"{vault}\"",
        "```",
        "",
    ])
    return "\n".join(lines)


def dashboard_markdown(
    thread_home: Path,
    vault: Path,
    anchors: list[dict],
    health_path: Path,
    checkpoint_path: Path,
    heartbeat_path: Path,
    dashboard_html: Path,
) -> str:
    anchor_lines = []
    for anchor in anchors:
        title = anchor.get("title") or "Untitled Anchor"
        path = thread_home / "Anchors" / f"{safe_filename(title)}.md"
        anchor_lines.append(f"- {wikilink(path, vault, title)}")
    html_rel = Path(os.path.relpath(dashboard_html, start=thread_home)).as_posix()
    return "\n".join([
        format_frontmatter({
            "type": "codex-thread-dashboard",
            "thread": thread_home.name,
            "updated": now_utc(),
            "tags": ["codex-memory", "dashboard"],
        }).rstrip(),
        f"# {thread_home.name}",
        "",
        "## Control Panel",
        "",
        f"- {wikilink(health_path, vault, 'Memory Health')}",
        f"- {wikilink(checkpoint_path, vault, 'Latest Checkpoint')}",
        f"- {wikilink(heartbeat_path, vault, 'Heartbeat')}",
        f"- HTML dashboard: [{dashboard_html.name}]({html_rel})",
        "",
        "## Anchors",
        "",
        "\n".join(anchor_lines) if anchor_lines else "- No anchors yet.",
        "",
        "## Obsidian Graph Hint",
        "",
        "This dashboard writes each anchor as its own note so Obsidian's local graph can show thread-memory relationships through wikilinks and tags.",
        "",
    ])


def homepage(vault: Path, thread_dashboard: Path) -> str:
    return "\n".join([
        format_frontmatter({
            "type": "codex-memory-home",
            "updated": now_utc(),
            "tags": ["codex-memory"],
        }).rstrip(),
        f"# {DEFAULT_SITE_TITLE}",
        "",
        "这是给长线程记忆准备的本地 vault：人类可读、Obsidian 可连图、Codex 可同步。",
        "",
        "## Threads",
        "",
        f"- {wikilink(thread_dashboard, vault, thread_dashboard.parent.name)}",
        "",
        "## How This Works",
        "",
        "- `thread-anchors.md` keeps compact human-readable memory anchors.",
        "- SQLite FTS keeps old conversation searchable.",
        "- Graphify corpus is prepared only when deep graph analysis is worth it.",
        "- Heartbeat wakes the thread to run checks and update this vault.",
        "",
    ])
def obsidian_snippet_css() -> str:
    return """
/* Optional Codex Memory vault styling.
 * Scoped to notes with `cssclasses: codex-memory` so it will not retheme the
 * whole vault when the snippet is enabled in Obsidian.
 */
.markdown-preview-view.codex-memory,
.markdown-source-view.mod-cm6.codex-memory .cm-scroller {
  --codex-memory-bg: #fffcf0;
  --codex-memory-bg-soft: #f2f0e5;
  --codex-memory-ink: #100f0f;
  --codex-memory-muted: #6f6e69;
  --codex-memory-line: #dad8ce;
  --codex-memory-accent: #d3750d;
  background: var(--codex-memory-bg);
  color: var(--codex-memory-ink);
  font-family: "Huiwen Mincho", "Songti SC", "STSong", "Noto Serif CJK SC", Georgia, serif;
}
.markdown-preview-view.codex-memory h1,
.markdown-preview-view.codex-memory h2,
.markdown-preview-view.codex-memory h3 {
  font-weight: 400;
  letter-spacing: 0;
}
.markdown-preview-view.codex-memory h1 {
  font-size: 2.8em;
  line-height: 1;
}
.markdown-preview-view.codex-memory a {
  color: var(--codex-memory-accent);
}
.markdown-preview-view.codex-memory hr,
.markdown-preview-view.codex-memory blockquote {
  border-color: var(--codex-memory-line);
}
.markdown-preview-view.codex-memory code {
  background: var(--codex-memory-bg-soft);
}
"""
