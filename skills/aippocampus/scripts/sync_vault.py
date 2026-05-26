#!/usr/bin/env python3
"""Sync thread-memory artifacts into an Obsidian vault and dashboard."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from registry import register_current_thread
from aippocampuslib import compact_text, now_utc, parse_anchor_file


SCRIPT_DIR = Path(__file__).resolve().parent


def env_value(name: str, legacy_name: str | None = None) -> str | None:
    return os.environ.get(name) or (os.environ.get(legacy_name) if legacy_name else None)


def optional_env_path(name: str, legacy_name: str | None = None) -> Path | None:
    value = env_value(name, legacy_name)
    return Path(value) if value else None


DEFAULT_VAULT = Path(env_value("AIPPOCAMPUS_VAULT", "CODEX_MEMORY_VAULT") or (Path.home() / "AIppocampus Memory"))
DEFAULT_STYLE_SOURCE = optional_env_path("AIPPOCAMPUS_STYLE_SOURCE", "CODEX_MEMORY_STYLE_SOURCE")
DEFAULT_SCRIPT_SOURCE = optional_env_path("AIPPOCAMPUS_SCRIPT_SOURCE", "CODEX_MEMORY_SCRIPT_SOURCE")
DEFAULT_SITE_MARK = optional_env_path("AIPPOCAMPUS_SITE_MARK", "CODEX_MEMORY_SITE_MARK")
DEFAULT_SITE_TITLE = env_value("AIPPOCAMPUS_SITE_TITLE", "CODEX_MEMORY_SITE_TITLE") or "AIppocampus"
DEFAULT_D3_SOURCE = SCRIPT_DIR.parent / "assets" / "d3-7.9.0.min.js"
DEFAULT_PIXI_SOURCE = SCRIPT_DIR.parent / "assets" / "pixi-7.2.4.min.js"


def resolve_under(base: Path, *parts: str) -> Path:
    base = base.resolve()
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"refusing to write outside vault: {target}")
    return target


def safe_filename(name: str, fallback: str = "untitled") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip()
    name = re.sub(r"\s+", " ", name)
    name = name.rstrip(". ")
    return name[:120] or fallback


def wikilink(path: Path, vault: Path, label: str | None = None) -> str:
    rel = path.resolve().relative_to(vault.resolve())
    stem = str(rel.with_suffix("")).replace("\\", "/")
    if label:
        return f"[[{stem}|{label}]]"
    return f"[[{stem}]]"


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return proc.stdout


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def format_frontmatter(data: dict) -> str:
    data = dict(data)
    if "cssclasses" not in data and "codex-memory" in data.get("tags", []):
        data["cssclasses"] = ["codex-memory"]
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def read_recent_messages(path: Path, limit: int = 8) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            item.setdefault("id", idx)
            rows.append(item)
    return rows[-limit:]


def copy_dashboard_assets(vault: Path) -> dict[str, str]:
    assets_dir = resolve_under(vault, "_dashboards", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    if DEFAULT_STYLE_SOURCE and DEFAULT_STYLE_SOURCE.exists():
        target = assets_dir / "publish-reference.css"
        shutil.copy2(DEFAULT_STYLE_SOURCE, target)
        copied["publish_css"] = "assets/publish-reference.css"
    if DEFAULT_SCRIPT_SOURCE and DEFAULT_SCRIPT_SOURCE.exists():
        target = assets_dir / "publish-reference.js"
        shutil.copy2(DEFAULT_SCRIPT_SOURCE, target)
        copied["publish_js"] = "assets/publish-reference.js"
    if DEFAULT_D3_SOURCE.exists():
        target = assets_dir / "d3-7.9.0.min.js"
        shutil.copy2(DEFAULT_D3_SOURCE, target)
        copied["d3_js"] = "assets/d3-7.9.0.min.js"
    if DEFAULT_PIXI_SOURCE.exists():
        target = assets_dir / "pixi-7.2.4.min.js"
        shutil.copy2(DEFAULT_PIXI_SOURCE, target)
        copied["pixi_js"] = "assets/pixi-7.2.4.min.js"
    if DEFAULT_SITE_MARK and DEFAULT_SITE_MARK.exists():
        target = assets_dir / "site-mark.svg"
        shutil.copy2(DEFAULT_SITE_MARK, target)
        copied["site_mark"] = "assets/site-mark.svg"
    return copied


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


def json_script(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def dashboard_anchor_title(anchor: dict, idx: int) -> str:
    """Return a short display title for the private dashboard.

    Keep the underlying anchor notes untouched; this is only a visual alias so
    the Publish-like navigation remains scannable instead of wrapping long
    implementation-oriented English titles through the sidebar.
    """
    title = anchor.get("title") or f"Anchor {idx}"
    known = {
        "Codex local thread memory index": "本地线程索引",
        "Thread memory bundle and graph upgrade": "记忆包与图谱升级",
        "Thread memory implementation status": "实现状态",
        "Graphify bridge for long-thread memory": "Graphify 桥",
        "Thread memory health checkpoint and light hook": "健康检查与轻量 hook",
        "Codex Memory vault and heartbeat route": "Vault 与 Heartbeat",
        "Private dashboard aligned with Obsidian Publish now page": "Publish 风格 Dashboard",
        "D3 force graph adapter for private dashboard": "D3 图谱适配器",
    }
    if title in known:
        return known[title]
    return compact_text(title, 28)


def dashboard_graph_data(anchors: list[dict]) -> dict:
    nodes = [
        {
            "id": "now",
            "label": "现在",
            "type": "page",
            "pane": "now",
            "local": True,
            "label_priority": 0,
        }
    ]
    edges = []
    seen_keywords: dict[str, str] = {}
    for idx, anchor in enumerate(anchors, start=1):
        anchor_id = f"anchor-{idx}"
        title = dashboard_anchor_title(anchor, idx)
        nodes.append({
            "id": anchor_id,
            "label": title,
            "type": "topic",
            "pane": anchor_id,
            "local": True,
            "label_priority": idx,
        })
        edges.append({"source": "now", "target": anchor_id, "type": "HAS_TOPIC"})
        for keyword in anchor.get("keywords", [])[:2]:
            key = keyword.strip()
            if not key:
                continue
            keyword_id = seen_keywords.setdefault(
                key.lower(), f"keyword-{len(seen_keywords) + 1}"
            )
            if not any(node["id"] == keyword_id for node in nodes):
                nodes.append({
                    "id": keyword_id,
                    "label": key,
                    "type": "keyword",
                    "pane": anchor_id,
                    "local": False,
                    "label_priority": 99,
                })
            edges.append({"source": anchor_id, "target": keyword_id, "type": "HAS_KEYWORD"})
    for page_id, label in [
        ("health", "记忆健康"),
        ("threads", "正在追的线索"),
        ("routes", "建议的走法"),
        ("anchors", "锚点"),
        ("heartbeat", "Heartbeat"),
        ("recent", "最近消息"),
    ]:
        if any(node["id"] == page_id for node in nodes):
            continue
        nodes.append({
            "id": page_id,
            "label": label,
            "type": "page",
            "pane": page_id,
            "local": True,
            "label_priority": 12,
        })
        edges.append({"source": "now", "target": page_id, "type": "LINKS_TO"})
    for special_id, label in [
        ("graphify", "Graphify corpus"),
    ]:
        nodes.append({
            "id": special_id,
            "label": label,
            "type": "system",
            "pane": "heartbeat" if special_id == "graphify" else special_id,
            "local": special_id != "graphify",
            "label_priority": 20,
        })
        edges.append({"source": "now", "target": special_id, "type": "TRACKS"})
    return {"nodes": nodes, "edges": edges, "root": "now"}


def dashboard_pane_data_v2(
    health: dict,
    anchors: list[dict],
    checkpoint_state: dict,
    recent_messages: list[dict],
) -> dict:
    status = "OK" if health.get("ok") else "Needs maintenance"
    checkpoint = checkpoint_state.get("last_candidate") or {}
    messages = health.get("rollout", {}).get("message_count", 0)
    anchor_count = health.get("anchors", {}).get("count", 0)
    checkpoint_state_text = "需要巩固" if health.get("checkpoint", {}).get("due") else "已巩固"
    graphify_state = "需要刷新" if health.get("graphify", {}).get("stale") else "已同步"

    anchor_links = "".join(
        f"<li><a class='internal-link' href='#anchor-{idx}' data-note='anchor-{idx}'>{html.escape(dashboard_anchor_title(anchor, idx))}</a></li>"
        for idx, anchor in enumerate(anchors, start=1)
    ) or "<li>暂无锚点</li>"
    recent_items = "".join(
        f"<li><span>{html.escape(msg.get('role', 'message'))}</span>{html.escape(compact_text(msg.get('text', ''), 220))}</li>"
        for msg in recent_messages[-5:]
    )

    pages = {
        "now": {
            "title": "现在",
            "outline": ["从这里进入", "现在在追的线索", "建议的走法"],
            "body": "\n".join([
                "<div class='callout' data-callout='noteinfo'>",
                "  <div class='callout-title'><div class='callout-icon'>↗</div><div class='callout-title-inner'>Noteinfo</div></div>",
                "  <div class='callout-content'>",
                "    <p>这不是一个按指标消费的 dashboard，更像一个会继续长出来的私有笔记空间。</p>",
                "    <p>它把这个线程的索引、锚点、图谱和 heartbeat 串起来，让以后回来时能沿着线索重新进入。</p>",
                "  </div>",
                "</div>",
                "<p class='codex-lead'>我想把这里做成一种低压力的长期对话空间。</p>",
                "<h2 id='从这里进入' data-heading='从这里进入'>从这里进入</h2>",
                "<ul class='link-list'>",
                "  <li><a class='internal-link' href='#health' data-note='health'>记忆健康</a></li>",
                "  <li><a class='internal-link' href='#threads' data-note='threads'>正在追的线索</a></li>",
                "  <li><a class='internal-link' href='#routes' data-note='routes'>建议的走法</a></li>",
                "  <li><a class='internal-link' href='#anchors' data-note='anchors'>锚点</a></li>",
                "  <li><a class='internal-link' href='#heartbeat' data-note='heartbeat'>Heartbeat</a></li>",
                "</ul>",
                "<h2 id='现在在追的线索' data-heading='现在在追的线索'>现在在追的线索</h2>",
                f"<ul class='link-list'>{anchor_links}</ul>",
                "<h2 id='建议的走法' data-heading='建议的走法'>建议的走法</h2>",
                "<div class='callout' data-callout='links'>",
                "  <div class='callout-title'><div class='callout-title-inner'>Links</div></div>",
                "  <div class='callout-content'>",
                "    <p><a class='internal-link' href='#health' data-note='health'>记忆健康</a> -> <a class='internal-link' href='#heartbeat' data-note='heartbeat'>Heartbeat</a> -> <a class='internal-link' href='#anchors' data-note='anchors'>锚点</a> -> <a class='internal-link' href='#graph'>互动图谱</a></p>",
                "  </div>",
                "</div>",
            ]),
        },
        "health": {
            "title": "记忆健康",
            "outline": ["状态", "索引"],
            "body": "\n".join([
                "<h2 id='状态' data-heading='状态'>状态</h2>",
                "<ul class='status-list'>",
                f"<li>状态：{html.escape(status)}</li>",
                f"<li>锚点：{anchor_count}</li>",
                f"<li>消息：{messages}</li>",
                f"<li>Checkpoint：{checkpoint_state_text}</li>",
                f"<li>Graphify corpus：{graphify_state}</li>",
                "</ul>",
                "<h2 id='索引' data-heading='索引'>索引</h2>",
                "<p>SQLite FTS、锚点和轻量图谱共同负责召回；图谱负责导航，不替代原始检索。</p>",
            ]),
        },
        "threads": {
            "title": "正在追的线索",
            "outline": ["锚点列表"],
            "body": f"<h2 id='锚点列表' data-heading='锚点列表'>锚点列表</h2><ul class='link-list'>{anchor_links}</ul>",
        },
        "routes": {
            "title": "建议的走法",
            "outline": ["记忆系统路线", "精神主线路线"],
            "body": "\n".join([
                "<h2 id='记忆系统路线' data-heading='记忆系统路线'>记忆系统路线</h2>",
                "<div class='callout' data-callout='links'><div class='callout-content'>",
                "<p><a class='internal-link' href='#health' data-note='health'>记忆健康</a> -> <a class='internal-link' href='#heartbeat' data-note='heartbeat'>Heartbeat</a> -> <a class='internal-link' href='#anchors' data-note='anchors'>锚点</a> -> <a class='internal-link' href='#graph'>互动图谱</a></p>",
                "</div></div>",
                "<h2 id='精神主线路线' data-heading='精神主线路线'>精神主线路线</h2>",
                f"<ul class='link-list'>{anchor_links}</ul>",
            ]),
        },
        "anchors": {
            "title": "锚点",
            "outline": ["锚点列表"],
            "body": f"<h2 id='锚点列表' data-heading='锚点列表'>锚点列表</h2><ul class='link-list'>{anchor_links}</ul>",
        },
        "heartbeat": {
            "title": "Heartbeat",
            "outline": ["唤醒路线", "最近 checkpoint"],
            "body": "\n".join([
                "<h2 id='唤醒路线' data-heading='唤醒路线'>唤醒路线</h2>",
                "<p>Heartbeat 会定期唤醒这个线程，运行 memory health，刷新 vault，并在 Slack / PR / feedback 连接可用时检查外部反馈；不可用时明确记为 skipped。</p>",
                "<h2 id='最近 checkpoint' data-heading='最近 checkpoint'>最近 checkpoint</h2>",
                f"<p>{html.escape(checkpoint.get('title', 'No checkpoint yet'))}</p>",
            ]),
        },
        "recent": {
            "title": "最近消息",
            "outline": ["消息"],
            "body": f"<h2 id='消息' data-heading='消息'>消息</h2><ol class='messages'>{recent_items}</ol>" if recent_items else "<p>暂无最近消息。</p>",
        },
    }

    for idx, anchor in enumerate(anchors, start=1):
        title = dashboard_anchor_title(anchor, idx)
        source_title = anchor.get("title") or f"Anchor {idx}"
        notes = "".join(f"<li>{html.escape(note)}</li>" for note in anchor.get("notes", [])) or "<li>暂无说明。</li>"
        keywords = "".join(f"<span>{html.escape(keyword)}</span>" for keyword in anchor.get("keywords", [])[:10])
        pages[f"anchor-{idx}"] = {
            "title": title,
            "outline": ["关键词", "Notes"],
            "body": "\n".join([
                f"<p class='codex-source-title'>{html.escape(source_title)}</p>",
                "<h2 id='关键词' data-heading='关键词'>关键词</h2>",
                f"<div class='tags'>{keywords}</div>",
                "<h2 id='Notes' data-heading='Notes'>Notes</h2>",
                f"<ul>{notes}</ul>",
            ]),
        }
    return pages


def html_graph_canvas_v2() -> str:
    return """<div class="graph-view" style="padding: 0px; overflow: hidden; position: relative;">
                <canvas class="codex-graph-hit-canvas" aria-hidden="true"></canvas>
                <canvas class="codex-graph-canvas" role="img" aria-label="Thread memory graph"></canvas>
              </div>"""


def dashboard_interaction_script_v2() -> str:
    return r"""
(() => {
  const body = document.body;
  const container = document.querySelector(".published-container");
  const siteHeader = document.querySelector(".site-header");
  const siteBody = document.querySelector(".site-body");
  const leftColumn = document.querySelector(".site-body-left-column");
  const centerColumn = document.querySelector(".site-body-center-column");
  const rightColumn = document.querySelector(".site-body-right-column");
  const mobileToolsButton = document.querySelector("#mobile-tools-btn");
  const sidebarButton = document.querySelector("#codex-mobile-nav-btn");
  const footer = document.querySelector(".site-footer");
  const search = document.querySelector(".search-bar");
  const renderContainer = document.querySelector(".render-container");
  const track = document.querySelector(".render-container-inner");
  const mainRenderer = track?.querySelector(".codex-main-renderer");
  const graphContainer = document.querySelector(".graph-view-container");
  const graphView = graphContainer?.querySelector(".graph-view");
  const graphCanvas = graphContainer?.querySelector(".codex-graph-canvas");
  const hitCanvas = graphContainer?.querySelector(".codex-graph-hit-canvas");
  const desktopGraphExpandIcon = document.querySelector(".graph-icon.graph-expand")?.innerHTML || "";
  const desktopGraphGlobalIcon = document.querySelector(".graph-icon.graph-global")?.innerHTML || "";
  const mobileCurrentGraphIcon = '<svg class="lucide lucide-locate-fixed" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="2" x2="5" y1="12" y2="12"/><line x1="19" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="5"/><line x1="12" x2="12" y1="19" y2="22"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/></svg>';
  const mobileGlobalGraphIcon = '<svg class="lucide lucide-share-2" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/></svg>';
  let graphPlaceholder = null;
  const paneData = JSON.parse(document.getElementById("codex-pane-data")?.textContent || "{}");
  const graphData = JSON.parse(document.getElementById("codex-graph-data")?.textContent || "{\"nodes\":[],\"edges\":[]}");
  const footerHome = { parent: footer?.parentNode || null, next: footer?.nextSibling || null };

  const state = {
    activeNote: "now",
    stackMode: "split",
    graphMode: "local",
    nodes: [],
    edges: [],
    hovered: null,
    dragging: null,
    dragStart: null,
    frame: 0,
    hoverFrame: 0,
    simulation: null,
    pixi: null,
    positions: new Map(),
    scrollAnimation: null,
    stagedOpenTimers: [],
    slidingClassFrame: 0,
    graphSoftRefresh: false
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#039;"
    }[ch]));
  }

  function slug(value) {
    return String(value || "note").trim().replace(/\s+/g, "-").replace(/[^\p{L}\p{N}_-]+/gu, "") || "note";
  }

  function supportsSlidingPanes() {
    return window.matchMedia?.("(min-width: 1279px)")?.matches ?? true;
  }

  function isCompactLayout() {
    return window.matchMedia?.("(max-width: 760px)")?.matches ?? false;
  }

  function publishHeading(level, title) {
    const safeTitle = escapeHtml(title);
    const safeSlug = escapeHtml(slug(title));
    return `
      <div class="el-h${level}">
        <h${level} data-heading="${safeTitle}" dir="auto" class="publish-article-heading" id="${safeSlug}" data-publish-anchor="${safeTitle}" data-publish-anchor-aliases="${safeTitle}">${safeTitle}</h${level}>
      </div>
    `;
  }

  function publishBody(bodyHtml) {
    const template = document.createElement("template");
    template.innerHTML = bodyHtml || "";
    const fragment = document.createElement("div");
    Array.from(template.content.childNodes).forEach((node) => {
      if (node.nodeType !== Node.ELEMENT_NODE) {
        fragment.appendChild(node.cloneNode(true));
        return;
      }
      const element = node.cloneNode(true);
      const tag = element.tagName.toLowerCase();
      if (/^h[1-6]$/.test(tag)) {
        const level = tag.slice(1);
        const title = element.textContent.trim();
        element.classList.add("publish-article-heading");
        element.setAttribute("data-heading", title);
        element.setAttribute("dir", "auto");
        element.id ||= slug(title);
        element.setAttribute("data-publish-anchor", title);
        element.setAttribute("data-publish-anchor-aliases", title);
        const wrapper = document.createElement(`div`);
        wrapper.className = `el-h${level}`;
        wrapper.appendChild(element);
        fragment.appendChild(wrapper);
        return;
      }
      const wrapperMap = { p: "el-p", ul: "el-ul", ol: "el-ol", div: "el-div", blockquote: "el-blockquote", table: "el-table", pre: "el-pre" };
      const wrapperClass = wrapperMap[tag];
      if (wrapperClass) {
        const wrapper = document.createElement("div");
        wrapper.className = wrapperClass;
        wrapper.appendChild(element);
        fragment.appendChild(wrapper);
        return;
      }
      fragment.appendChild(element);
    });
    return fragment.innerHTML;
  }

  function pageMarkup(id) {
    const page = paneData[id] || paneData.now;
    const title = page?.title || id;
    return `
      <div class="markdown-preview-pusher" style="width: 1px; height: 0.1px; margin-bottom: 0px;"></div>
      <div class="mod-header mod-ui">
        <h1 class="page-header" id="${escapeHtml(slug(title))}" data-heading="${escapeHtml(title)}">${escapeHtml(title)}</h1>
      </div>
      ${publishHeading(1, title)}
      ${publishBody(page?.body || "")}
    `;
  }

  function rendererShell(id, classes = "publish-renderer codex-slide-pane") {
    const page = paneData[id] || paneData.now;
    return `
      <article class="${classes}" data-note-id="${escapeHtml(id)}">
        <div class="markdown-preview-view markdown-rendered node-insert-event" tabindex="-1">
          <div class="markdown-preview-sizer markdown-preview-section">${pageMarkup(id)}</div>
        </div>
      </article>
    `;
  }

  function rendererTitle(renderer) {
    return renderer?.querySelector(".publish-article-heading, .page-header, h1")?.textContent?.trim() || "";
  }

  function closeIconMarkup() {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon lucide-x" aria-hidden="true" focusable="false"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>`;
  }

  function linkIconMarkup() {
    return `<svg class="lucide lucide-link" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`;
  }

  function ensureRendererChrome(renderer) {
    if (!renderer) return;
    const title = rendererTitle(renderer) || renderer.dataset.noteId || "";
    const noteId = renderer.dataset.noteId || "";
    let extraTitle = renderer.querySelector(":scope > .extra-title");
    if (!extraTitle) {
      extraTitle = document.createElement("div");
      extraTitle.className = "extra-title";
      extraTitle.innerHTML = `
        <span class="extra-title-text"></span>
        <span class="codex-pane-close" role="button">${closeIconMarkup()}</span>
      `;
      renderer.appendChild(extraTitle);
    }
    if (noteId) extraTitle.dataset.note = noteId;
    const titleText = extraTitle.querySelector(".extra-title-text");
    titleText.textContent = title;
    titleText.setAttribute("role", "link");
    titleText.tabIndex = 0;
    titleText.setAttribute("aria-label", `打开 ${title}`);
    if (titleText && titleText.dataset.boundOpen !== "true") {
      titleText.dataset.boundOpen = "true";
      titleText.addEventListener("click", (event) => {
        event.stopPropagation();
        const targetId = renderer.dataset.noteId;
        if (targetId) openNote(targetId);
      });
      titleText.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        titleText.click();
      });
    }
    const closeButton = extraTitle.querySelector(".codex-pane-close");
    closeButton?.setAttribute("aria-label", `关闭 ${title}`);
    if (closeButton && closeButton.dataset.boundClose !== "true") {
      closeButton.dataset.boundClose = "true";
      closeButton.addEventListener("click", (event) => {
        event.stopPropagation();
        if (renderer.classList.contains("codex-main-renderer")) {
          setMainPage("now", { clearPanes: true });
        } else {
          closePane(renderer);
        }
      });
      closeButton.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        closeButton.click();
      });
    }
  }

  function sourcePaneWidth() {
    return window.matchMedia?.("(min-width: 1800px)")?.matches ? 800 : 700;
  }

  const FOLDED_PANE_STEP = 36;

  function shouldSplitTwoPane(nextCount) {
    // Obsidian Publish only keeps a two-page open as a flat split when the
    // center rail can actually contain two readable panes. Below that width it
    // uses the same overlay drawer mechanics as deeper stacks.
    return nextCount === 2 && (renderContainer?.clientWidth || 0) >= 1400;
  }

  function applyStackLayout(activeId = state.activeNote) {
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    const stacked = supportsSlidingPanes() && renderers.length > 1;
    const mode = stacked ? state.stackMode : "split";
    const paneWidth = sourcePaneWidth();
    renderers.forEach((renderer, index) => {
      ensureRendererChrome(renderer);
      // Obsidian Publish's stack is history-sensitive. Opening the second pane
      // may be a true split on very wide center rails, but it becomes overlay
      // drawer navigation as soon as the rail cannot hold two readable panes.
      // Three or more panes keep old pages as book spines instead of replacing
      // history. The source runtime does not decide overlay/squished from the
      // current note id; it derives those classes from horizontal scroll. That
      // distinction is what makes clicking an existing book spine expand it in
      // place instead of feeling like a fresh page navigation.
      if (stacked) {
        if (mode === "split") {
          renderer.style.flex = "1 1 0px";
          renderer.style.width = "100%";
          renderer.style.minWidth = "0px";
        } else {
          renderer.style.flex = `0 0 ${paneWidth}px`;
          renderer.style.width = `${paneWidth}px`;
          renderer.style.minWidth = "700px";
        }
        renderer.style.left = `${index * 36}px`;
        renderer.style.right = `${-(664 - (renderers.length - 1 - index) * 36)}px`;
      } else {
        renderer.style.flex = "";
        renderer.style.width = "";
        renderer.style.minWidth = "700px";
        renderer.style.left = "0px";
        renderer.style.right = "-664px";
        renderer.classList.remove("mod-overlay", "mod-squished");
      }
    });
    state.activeNote = activeId;
    syncSlidingWindowClasses();
  }

  function rendererIndexForNote(id) {
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    const index = renderers.findIndex((renderer) => renderer.dataset.noteId === id);
    return index >= 0 ? index : Math.max(0, renderers.length - 1);
  }

  function stackScrollTargetForIndex(index) {
    if (!renderContainer) return 0;
    const maxScroll = Math.max(0, renderContainer.scrollWidth - renderContainer.clientWidth);
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    if (renderers.length <= 1 || state.stackMode === "split") return 0;
    const paneWidth = sourcePaneWidth();
    const sourceLikeTarget = Math.max(0, index) * (paneWidth - FOLDED_PANE_STEP);
    return Math.max(0, Math.min(maxScroll, Math.round(sourceLikeTarget)));
  }

  function stackEndScrollTarget() {
    return stackScrollTargetForIndex(rendererIndexForNote(state.activeNote));
  }

  function syncSlidingWindowClasses(scrollLeft = null) {
    const renderers = Array.from(track?.querySelectorAll(":scope > .publish-renderer") || []);
    if (!renderContainer || !supportsSlidingPanes() || renderers.length <= 1 || state.stackMode === "split") {
      renderers.forEach((renderer) => renderer.classList.remove("mod-overlay", "mod-squished"));
      return;
    }
    const paneWidth = sourcePaneWidth();
    const spineTravel = paneWidth - FOLDED_PANE_STEP;
    const left = Number.isFinite(scrollLeft) ? scrollLeft : renderContainer.scrollLeft;
    const right = left + renderContainer.clientWidth;
    const count = renderers.length;
    renderers.forEach((renderer, index) => {
      const overlay =
        (index > 0 && left > spineTravel * (index - 1)) ||
        (index * paneWidth + (count - index - 1) * FOLDED_PANE_STEP > right);
      const squished =
        left >= spineTravel * (index + 1) ||
        (index * paneWidth + (count - index) * FOLDED_PANE_STEP >= right);
      renderer.classList.toggle("mod-overlay", overlay);
      renderer.classList.toggle("mod-squished", squished);
    });
  }

  function scheduleSlidingClassSync() {
    if (state.slidingClassFrame) return;
    state.slidingClassFrame = window.requestAnimationFrame(() => {
      state.slidingClassFrame = 0;
      syncSlidingWindowClasses();
    });
  }

  function sourceStackEase(t) {
    const clamped = Math.max(0, Math.min(1, t));
    if (clamped < 0.18) {
      const early = clamped / 0.18;
      return 0.1 * early * early;
    }
    const late = (clamped - 0.18) / 0.82;
    return 0.1 + 0.9 * (1 - Math.pow(1 - late, 4));
  }

  function stopScrollAnimation() {
    if (state.scrollAnimation?.frame) {
      window.cancelAnimationFrame(state.scrollAnimation.frame);
    }
    state.scrollAnimation = null;
  }

  function animateRenderScroll(target, options = {}) {
    if (!renderContainer) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const next = Math.max(0, Math.round(target));
    stopScrollAnimation();
    const explicitStart = Number.isFinite(options.from) ? Math.max(0, Math.round(options.from)) : null;
    if (reduceMotion || options.instant) {
      renderContainer.scrollLeft = next;
      return;
    }
    const start = explicitStart ?? renderContainer.scrollLeft;
    if (explicitStart !== null) {
      renderContainer.scrollLeft = start;
    }
    const delta = next - start;
    if (Math.abs(delta) < 1) {
      renderContainer.scrollLeft = next;
      return;
    }
    if (options.nativeSmooth && typeof renderContainer.scrollTo === "function") {
      // Source Obsidian Publish uses native smooth scrolling when a user clicks
      // an already-open folded pane. Keeping that path native preserves the
      // slow acceleration/deceleration that makes the book-spine feel unfold
      // instead of snapping into the current page slot.
      renderContainer.scrollTo({ left: next, top: 0, behavior: "smooth" });
      syncSlidingWindowClasses(start);
      return;
    }
    const duration = options.duration || 360;
    const startedAt = performance.now();
    const animation = { frame: 0 };
    state.scrollAnimation = animation;
    const step = (now) => {
      if (state.scrollAnimation !== animation) return;
      const progress = Math.min(1, (now - startedAt) / duration);
      const current = start + delta * sourceStackEase(progress);
      renderContainer.scrollLeft = current;
      syncSlidingWindowClasses(current);
      if (progress < 1) {
        animation.frame = window.requestAnimationFrame(step);
      } else {
        renderContainer.scrollLeft = next;
        syncSlidingWindowClasses(next);
        state.scrollAnimation = null;
      }
    };
    animation.frame = window.requestAnimationFrame(step);
  }

  function alignToActivePane(options = {}) {
    if (!renderContainer) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const settleDelay = reduceMotion || options.instant ? 0 : (options.nativeSmooth ? 860 : 560);

    window.requestAnimationFrame(() => {
      const target = stackEndScrollTarget();
      animateRenderScroll(target, options);

      // Publish's sliding stack changes width/class first, then lets the
      // horizontal scroller glide to the active page. Re-landing once after the
      // motion settles protects trimmed stacks and late width changes without
      // turning the drawer open into a hard jump.
      window.setTimeout(() => {
        const finalTarget = stackEndScrollTarget();
        if (Math.abs(renderContainer.scrollLeft - finalTarget) > 2) {
          stopScrollAnimation();
          renderContainer.scrollLeft = finalTarget;
        }
      }, settleDelay);
    });
  }

  function setActiveNav(id) {
    document.querySelectorAll("[data-note]").forEach((item) => {
      item.classList.toggle("mod-active", item.dataset.note === id);
    });
  }

  function renderOutline(id) {
    const outline = document.querySelector(".outline-view");
    const page = paneData[id] || paneData.now;
    if (!outline || !page) return;
    const children = (page.outline || []).map((heading) => `
      <div class="tree-item">
        <a class="tree-item-self is-clickable" href="#${escapeHtml(id)}" data-outline-target="#${escapeHtml(slug(heading))}" data-publish-anchor-target="${escapeHtml(slug(heading))}">
          <span class="tree-item-inner">${escapeHtml(heading)}</span>
        </a>
      </div>
    `).join("");
    outline.innerHTML = `
      <div class="tree-item">
        <a class="tree-item-self is-clickable mod-active" href="#${escapeHtml(id)}" data-outline-target="#${escapeHtml(slug(page.title))}" data-publish-anchor-target="${escapeHtml(slug(page.title))}">
          <span class="tree-item-inner">${escapeHtml(page.title)}</span>
        </a>
        <div class="tree-item-children">${children}</div>
      </div>
    `;
    outline.querySelectorAll(".tree-item-self.is-clickable[href]").forEach((link) => {
      if (link.dataset.boundOutline === "true") return;
      link.dataset.boundOutline = "true";
      link.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        scrollActiveOutlineTo(link.dataset.outlineTarget || link.getAttribute("href"), link);
      });
    });
  }

  function activeRenderer() {
    return (
      track?.querySelector(`:scope > .publish-renderer[data-note-id="${CSS.escape(state.activeNote)}"]`) ||
      mainRenderer ||
      track?.querySelector(":scope > .publish-renderer:last-of-type")
    );
  }

  function normalizeHash(value) {
    try {
      return decodeURIComponent(String(value || "").replace(/^#/, ""));
    } catch {
      return String(value || "").replace(/^#/, "");
    }
  }

  function findHeadingInRenderer(renderer, hash) {
    if (!renderer || !hash) return null;
    const normalized = normalizeHash(hash);
    const byId = renderer.querySelector(`#${CSS.escape(normalized)}`);
    if (byId) return byId;
    return Array.from(renderer.querySelectorAll(":is(h1, h2, h3, h4, h5, h6)[data-heading], .publish-article-heading"))
      .find((element) => slug(element.dataset.heading || element.textContent) === normalized) || null;
  }

  function flashHeading(target) {
    const flashTarget = target?.closest?.(".el-h1, .el-h2, .el-h3, .el-h4, .el-h5, .el-h6") || target;
    if (!flashTarget) return;
    flashTarget.classList.add("is-flashing");
    window.setTimeout(() => flashTarget.classList.remove("is-flashing"), 900);
  }

  function scrollActiveOutlineTo(hash, sourceElement = null) {
    const renderer = activeRenderer();
    const target = findHeadingInRenderer(renderer, hash);
    if (!renderer || !target) return false;
    const scroller = renderer.querySelector(".markdown-preview-view") || renderContainer;
    if (scroller) {
      const targetRect = target.getBoundingClientRect();
      const scrollRect = scroller.getBoundingClientRect();
      const nextTop = scroller.scrollTop + targetRect.top - scrollRect.top - 18;
      scroller.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });
    } else {
      target.scrollIntoView({ block: "start", behavior: "smooth" });
    }
    document.querySelectorAll(".outline-view .tree-item-self").forEach((item) => {
      item.classList.toggle("mod-active", item === sourceElement);
    });
    flashHeading(target);
    window.history.replaceState({}, "", `#${state.activeNote}`);
    return true;
  }

  let hoverPreview = null;
  let hoverPreviewTrigger = null;
  let hoverPreviewTimer = 0;
  let hoverPreviewHideTimer = 0;
  const hoverPreviewMarkupCache = new Map();

  function previewTriggerFromEventTarget(target) {
    const trigger = target?.closest?.("a[data-note], .extra-title-text");
    if (!trigger || trigger.closest(".popover.hover-popover")) return null;
    if (trigger.classList?.contains("extra-title-text")) return trigger;
    // Preview only in reading panes. Left nav / right outline links already have
    // their own navigation semantics; previewing every sidebar link makes mouse
    // movement expensive on long generated dashboards.
    if (trigger.closest(".render-container")) return trigger;
    return null;
  }

  function noteIdFromPreviewTrigger(trigger) {
    const noteElement = trigger?.closest?.("[data-note]");
    const explicitNote = noteElement?.dataset?.note;
    if (explicitNote && paneData[explicitNote]) return explicitNote;
    const link = trigger?.closest?.("a[href]");
    const hashNote = normalizeHash(link?.getAttribute("href") || "");
    if (hashNote && paneData[hashNote]) return hashNote;
    const paneNote = trigger?.closest?.(".publish-renderer[data-note-id]")?.dataset?.noteId;
    if (trigger?.closest?.(".extra-title") && paneNote && paneData[paneNote]) return paneNote;
    return "";
  }

  function removeHoverPreview() {
    window.clearTimeout(hoverPreviewTimer);
    window.clearTimeout(hoverPreviewHideTimer);
    hoverPreviewTimer = 0;
    hoverPreviewHideTimer = 0;
    hoverPreview?.remove();
    hoverPreview = null;
    hoverPreviewTrigger = null;
  }

  function positionHoverPreview(trigger, preview) {
    const triggerRect = trigger.getBoundingClientRect();
    const width = Math.min(450, Math.max(320, Math.round(window.innerWidth - 32)));
    preview.style.width = `${width}px`;
    const height = Math.min(400, Math.max(260, Math.round(window.innerHeight - 32)));
    preview.style.height = `${height}px`;
    preview.style.maxWidth = "";
    preview.style.maxHeight = "";
    let left = triggerRect.left;
    left = Math.max(16, Math.min(left, window.innerWidth - width - 16));
    let top = triggerRect.bottom + 10;
    if (top + height > window.innerHeight - 16) {
      top = triggerRect.top - height - 10;
    }
    top = Math.max(16, Math.min(top, window.innerHeight - height - 16));
    preview.style.left = `${Math.round(left)}px`;
    preview.style.top = `${Math.round(top)}px`;
  }

  function hoverPreviewMarkupFor(noteId) {
    if (hoverPreviewMarkupCache.has(noteId)) return hoverPreviewMarkupCache.get(noteId);
    const page = paneData[noteId] || paneData.now;
    const markup = `
      <a class="hover-popover-link" href="#${escapeHtml(noteId)}" data-note="${escapeHtml(noteId)}" aria-label="打开 ${escapeHtml(page.title || noteId)}">${linkIconMarkup()}</a>
      <div class="markdown-embed is-loaded" data-note-id="${escapeHtml(noteId)}">
        <div class="markdown-embed-content">
          <div class="markdown-preview-view markdown-rendered node-insert-event" tabindex="-1">
            <div class="markdown-preview-sizer markdown-preview-section">
              <div class="markdown-preview-pusher" style="width: 1px; height: 0.1px; margin-bottom: 0px;"></div>
              ${pageMarkup(noteId)}
            </div>
          </div>
        </div>
      </div>
    `;
    hoverPreviewMarkupCache.set(noteId, markup);
    return markup;
  }

  function showHoverPreview(trigger) {
    const noteId = noteIdFromPreviewTrigger(trigger);
    if (!noteId || isCompactLayout()) return;
    if (hoverPreview && hoverPreviewTrigger === trigger) {
      positionHoverPreview(trigger, hoverPreview);
      return;
    }
    removeHoverPreview();
    hoverPreviewTrigger = trigger;
    hoverPreview = document.createElement("div");
    hoverPreview.className = "popover hover-popover is-loaded";
    hoverPreview.setAttribute("role", "tooltip");
    hoverPreview.innerHTML = hoverPreviewMarkupFor(noteId);
    hoverPreview.addEventListener("pointerenter", () => {
      window.clearTimeout(hoverPreviewHideTimer);
    });
    hoverPreview.addEventListener("pointerleave", (event) => {
      if (hoverPreviewTrigger?.contains(event.relatedTarget)) return;
      hoverPreviewHideTimer = window.setTimeout(removeHoverPreview, 160);
    });
    document.body.appendChild(hoverPreview);
    positionHoverPreview(trigger, hoverPreview);
  }

  function scheduleHoverPreview(trigger) {
    if (!trigger || trigger.closest(".popover.hover-popover")) return;
    window.clearTimeout(hoverPreviewHideTimer);
    window.clearTimeout(hoverPreviewTimer);
    hoverPreviewTimer = window.setTimeout(() => showHoverPreview(trigger), 400);
  }

  function scheduleHoverPreviewHide(relatedTarget) {
    if (hoverPreview?.contains(relatedTarget) || hoverPreviewTrigger?.contains(relatedTarget)) return;
    window.clearTimeout(hoverPreviewTimer);
    window.clearTimeout(hoverPreviewHideTimer);
    hoverPreviewHideTimer = window.setTimeout(removeHoverPreview, 160);
  }

  function setMainPage(id, options = {}) {
    const sizer = mainRenderer?.querySelector(".markdown-preview-sizer");
    if (!sizer || !paneData[id]) return false;
    clearStagedOpenTimers();
    if (options.clearPanes) {
      track?.querySelectorAll(":scope > .codex-slide-pane").forEach((pane) => pane.remove());
      state.stackMode = "split";
    }
    state.activeNote = id;
    sizer.innerHTML = pageMarkup(id);
    mainRenderer.dataset.noteId = id;
    applyStackLayout(id);
    renderOutline(id);
    setActiveNav(id);
    window.setTimeout(() => renderGraph({ soft: Boolean(options.softGraph) }), 60);
    mainRenderer?.scrollIntoView({ inline: "start", block: "nearest" });
    if (options.clearPanes && renderContainer) {
      stopScrollAnimation();
      renderContainer.scrollLeft = 0;
    }
    window.history.replaceState({}, "", `#${id}`);
    return true;
  }

  function rendererCount() {
    return track?.querySelectorAll(":scope > .publish-renderer")?.length || 0;
  }

  function setStackModeForOpen(nextCount) {
    if (!supportsSlidingPanes() || nextCount <= 1) {
      state.stackMode = "split";
    } else if (shouldSplitTwoPane(nextCount)) {
      state.stackMode = "split";
    } else {
      state.stackMode = "overlay";
    }
  }

  function setStackModeForClose(previousCount, nextCount) {
    if (!supportsSlidingPanes() || nextCount <= 1) {
      state.stackMode = "split";
    } else if (shouldSplitTwoPane(nextCount)) {
      state.stackMode = "split";
    } else {
      state.stackMode = "overlay";
    }
  }

  function clearStagedOpenTimers() {
    state.stagedOpenTimers.forEach((timer) => window.clearTimeout(timer));
    state.stagedOpenTimers = [];
  }

  function scheduleStagedOpenStep(callback, delay) {
    const timer = window.setTimeout(() => {
      state.stagedOpenTimers = state.stagedOpenTimers.filter((item) => item !== timer);
      callback();
    }, delay);
    state.stagedOpenTimers.push(timer);
  }

  function stageNewPaneForSourceOpen(pane, nextCount, activeId) {
    if (!pane) return;
    const paneWidth = sourcePaneWidth();
    const index = Math.max(0, nextCount - 1);
    ensureRendererChrome(pane);
    // Obsidian Publish does not immediately collapse the old foreground page
    // when a deeper card opens. The new renderer is first appended as a normal
    // right-side page, then the scroll motion starts, and only later do the old
    // pages become book spines. Adding final overlay classes up front makes the
    // page feel like it refreshed before sliding.
    pane.classList.remove("mod-overlay", "mod-squished");
    pane.style.flex = `0 0 ${paneWidth}px`;
    pane.style.width = `${paneWidth}px`;
    pane.style.minWidth = "700px";
    pane.style.left = `${index * 36}px`;
    pane.style.right = "-664px";
    state.activeNote = activeId;
  }

  function activatePane(pane) {
    const id = pane?.dataset.noteId;
    if (!pane || !id) return;
    const alreadyInStack = pane.parentElement === track;
    const previousCount = rendererCount();
    const previousScrollLeft = renderContainer?.scrollLeft || 0;
    clearStagedOpenTimers();
    if (alreadyInStack) {
      setStackModeForOpen(previousCount);
      applyStackLayout(id);
      alignToActivePane({ nativeSmooth: true });
      return;
    }
    track?.appendChild(pane);
    trimPaneStack();
    const nextCount = rendererCount();
    const stagedOpen = supportsSlidingPanes() && previousCount >= 2 && nextCount >= 3;
    if (stagedOpen) {
      setStackModeForOpen(nextCount);
      stageNewPaneForSourceOpen(pane, nextCount, id);
      scheduleStagedOpenStep(() => {
        animateRenderScroll(stackEndScrollTarget(), {
          from: previousScrollLeft,
          duration: 430
        });
      }, 33);
      scheduleStagedOpenStep(() => {
        applyStackLayout(id);
      }, 520);
      scheduleStagedOpenStep(() => {
        const finalTarget = stackEndScrollTarget();
        if (renderContainer && Math.abs(renderContainer.scrollLeft - finalTarget) > 2) {
          stopScrollAnimation();
          renderContainer.scrollLeft = finalTarget;
          syncSlidingWindowClasses(finalTarget);
        }
      }, 560);
      return;
    }
    setStackModeForOpen(nextCount);
    applyStackLayout(id);
    alignToActivePane({ from: previousScrollLeft });
  }

  function trimPaneStack() {
    // Source Publish keeps deep navigation history as a row of narrow book
    // spines. Do not trim old panes here: the long stack is the interaction,
    // and collapsing it turns the drawer into a hard page replacement.
  }

  function closePane(pane) {
    clearStagedOpenTimers();
    const previousCount = rendererCount();
    pane?.remove();
    const nextCount = rendererCount();
    setStackModeForClose(previousCount, nextCount);
    const latest = track?.querySelector(":scope > .codex-slide-pane:last-of-type");
    if (latest) {
      const id = latest.dataset.noteId || state.activeNote;
      state.activeNote = id;
      applyStackLayout(id);
      alignToActivePane();
      setActiveNav(id);
      renderOutline(id);
      window.setTimeout(renderGraph, 60);
      window.history.replaceState({}, "", `#${id}`);
    } else {
      const id = mainRenderer?.dataset.noteId || "now";
      state.activeNote = id;
      applyStackLayout(id);
      alignToActivePane();
      setActiveNav(id);
      renderOutline(id);
      window.setTimeout(renderGraph, 60);
      window.history.replaceState({}, "", `#${id}`);
    }
  }

  function openNote(id, options = {}) {
    if (!paneData[id]) return false;
    if (id === "now" || options.replaceMain || !supportsSlidingPanes()) {
      return setMainPage(id, { clearPanes: true });
    }
    let pane = track?.querySelector(`:scope > .codex-slide-pane[data-note-id="${CSS.escape(id)}"]`);
    if (!pane && track) {
      const fragment = document.createElement("template");
      fragment.innerHTML = rendererShell(id);
      pane = fragment.content.firstElementChild;
      ensureRendererChrome(pane);
    }
    if (pane) {
      activatePane(pane);
      setActiveNav(id);
      renderOutline(id);
      window.setTimeout(renderGraph, 60);
      window.history.replaceState({}, "", `#${id}`);
      return true;
    }
    return false;
  }

  function normalizeResponsiveStack() {
    if (supportsSlidingPanes()) return;
    track?.querySelectorAll(":scope > .codex-slide-pane").forEach((pane) => pane.remove());
    applyStackLayout(state.activeNote);
    if (renderContainer) renderContainer.scrollLeft = 0;
  }

  function isPrimaryNavigationOpen() {
    return Boolean(container?.classList.contains("is-left-column-open"));
  }

  function isMobileToolsDrawerOpen() {
    return Boolean(container?.classList.contains("is-mobile-tools-open"));
  }

  function setPrimaryNavigationOpen(open) {
    const nextState = Boolean(open) && isCompactLayout();
    if (nextState) container?.classList.remove("is-mobile-tools-open");
    container?.classList.toggle("is-left-column-open", nextState);
    sidebarButton?.setAttribute("aria-expanded", String(nextState));
    if (!nextState) sidebarButton?.blur?.();
    return nextState;
  }

  function setMobileToolsDrawerOpen(open) {
    const nextState = Boolean(open) && isCompactLayout();
    if (nextState) container?.classList.remove("is-left-column-open");
    container?.classList.toggle("is-mobile-tools-open", nextState);
    mobileToolsButton?.setAttribute("aria-expanded", String(nextState));
    scheduleGraphControlSync();
    if (nextState) window.setTimeout(renderGraph, 80);
    return nextState;
  }

  function syncFooterPlacement() {
    if (!footer || !centerColumn || !rightColumn) return;
    const compact = isCompactLayout();
    if (compact) {
      if (footer.parentNode !== centerColumn) centerColumn.appendChild(footer);
      return;
    }
    if (footerHome.parent && footer.parentNode !== footerHome.parent) {
      footerHome.parent.insertBefore(footer, footerHome.next);
    } else if (!footerHome.parent && footer.parentNode !== rightColumn) {
      rightColumn.appendChild(footer);
    }
  }

  function updateMobileShellMetrics() {
    if (!container) return;
    const headerHeight = siteHeader?.getBoundingClientRect().height || 0;
    const footerHeight = footer?.getBoundingClientRect().height || 0;
    container.style.setProperty("--mobile-shell-header-height", `${Math.round(headerHeight || 50)}px`);
    container.style.setProperty("--mobile-shell-footer-height", `${Math.round(footerHeight || 26)}px`);
  }

  function syncResponsiveShell() {
    const canSlide = supportsSlidingPanes();
    const compact = isCompactLayout();
    body.classList.toggle("sliding-windows", canSlide);
    if (!canSlide) normalizeResponsiveStack();
    rightColumn?.classList.toggle("mobile-tools-drawer", compact);
    if (mobileToolsButton) {
      mobileToolsButton.hidden = !compact;
      mobileToolsButton.setAttribute("aria-hidden", String(!compact));
    }
    if (!compact) {
      container?.classList.remove("is-left-column-open", "is-mobile-tools-open");
      sidebarButton?.setAttribute("aria-expanded", "false");
      mobileToolsButton?.setAttribute("aria-expanded", "false");
    }
    syncFooterPlacement();
    updateMobileShellMetrics();
    scheduleGraphControlSync();
  }

  function restoreFooter() {
    if (!footer) return;
    footer.dataset.customizedFooter = "true";
    footer.dataset.codexFooter = "memory";
    footer.innerHTML = `
      <div class="foot-links"><a href="#now" data-note="now" data-main="true">现在</a> · <a href="#health" data-note="health" data-main="true">Codex Memory</a> · <a href="#heartbeat" data-note="heartbeat" data-main="true">Heartbeat</a></div>
    `;
    syncFooterPlacement();
    updateMobileShellMetrics();
  }

  function setTheme(nextTheme, options = {}) {
    const isLight = nextTheme === "light";
    body.classList.toggle("theme-light", isLight);
    body.classList.toggle("theme-dark", !isLight);
    const toggle = document.querySelector(".site-body-left-column-site-theme-toggle");
    toggle?.classList.toggle("is-light", isLight);
    toggle?.classList.toggle("is-dark", !isLight);
    toggle?.querySelector(".checkbox-container")?.classList.toggle("is-enabled", !isLight);
    if (options.persist !== false) {
      try {
        window.localStorage?.setItem("codex-memory-theme", isLight ? "light" : "dark");
      } catch {
        // Storage can be unavailable in file previews; theme should still switch.
      }
    }
    window.setTimeout(renderGraph, 80);
  }

  function toggleTheme() {
    setTheme(body.classList.contains("theme-dark") ? "light" : "dark");
  }

  document.querySelector(".site-body-left-column-site-theme-toggle")?.addEventListener("click", toggleTheme);
  document.querySelector(".site-body-left-column-site-theme-toggle")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleTheme();
    }
  });

  sidebarButton?.addEventListener("click", () => {
    setPrimaryNavigationOpen(!isPrimaryNavigationOpen());
  });

  mobileToolsButton?.addEventListener("click", () => {
    setMobileToolsDrawerOpen(!isMobileToolsDrawerOpen());
  });

  // Bind on window capture so the private adapter wins before the copied
  // Publish helper's document-level hash navigation. Otherwise outline clicks
  // can be remapped by source heuristics that were built for real Publish DOM.
  window.addEventListener("click", (event) => {
    removeHoverPreview();
    const folder = event.target.closest("[data-folder-toggle]");
    if (folder) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      folder.closest(".tree-item")?.classList.toggle("is-collapsed");
      return;
    }
    const outlineLink = event.target.closest(".outline-view .tree-item-self.is-clickable[href]");
    if (outlineLink) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      scrollActiveOutlineTo(outlineLink.dataset.outlineTarget || outlineLink.getAttribute("href"), outlineLink);
      return;
    }
    const link = event.target.closest("a[data-note]");
    if (!link) return;
    const id = link.dataset.note;
    if (!id) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    const shouldReplaceMain = link.dataset.main === "true" || id === "now" || !supportsSlidingPanes();
    const didOpen = openNote(id, { replaceMain: shouldReplaceMain });
    if (didOpen && isCompactLayout()) {
      setPrimaryNavigationOpen(false);
      setMobileToolsDrawerOpen(false);
    }
  }, true);

  document.addEventListener("pointerover", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreview(trigger);
  }, true);

  document.addEventListener("pointerout", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreviewHide(event.relatedTarget);
  }, true);

  document.addEventListener("mouseover", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreview(trigger);
  }, true);

  document.addEventListener("mouseout", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreviewHide(event.relatedTarget);
  }, true);

  document.addEventListener("focusin", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreview(trigger);
  }, true);

  document.addEventListener("focusout", (event) => {
    const trigger = previewTriggerFromEventTarget(event.target);
    if (!trigger) return;
    scheduleHoverPreviewHide(event.relatedTarget);
  }, true);

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      search?.focus();
      search?.select();
    }
    if (event.key === "Escape") {
      if (isMobileToolsDrawerOpen()) {
        setMobileToolsDrawerOpen(false);
        return;
      }
      if (isPrimaryNavigationOpen()) {
        setPrimaryNavigationOpen(false);
        return;
      }
      closePane(track?.querySelector(":scope > .codex-slide-pane:last-of-type"));
      if (graphContainer?.classList.contains("mod-expanded")) {
        setGraphExpanded(false);
      }
    }
  });

  search?.addEventListener("input", () => {
    const value = search.value.trim().toLowerCase();
    document.querySelectorAll(".nav-view .tree-item").forEach((item) => {
      const text = item.textContent.toLowerCase();
      item.hidden = Boolean(value && !text.includes(value));
    });
  });

  window.addEventListener("resize", () => {
    window.requestAnimationFrame(() => {
      syncResponsiveShell();
      applyStackLayout(state.activeNote);
      alignToActivePane();
    });
  });

  renderContainer?.addEventListener("scroll", scheduleSlidingClassSync, { passive: true });

  function graphSize() {
    const rect = graphView?.getBoundingClientRect();
    return {
      width: Math.max(180, Math.round(rect?.width || 242)),
      height: Math.max(180, Math.round(rect?.height || 250))
    };
  }

  function resizeCanvas(canvas, width, height) {
    if (!canvas) return null;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.width = Math.max(1, Math.round(width * dpr));
    canvas.height = Math.max(1, Math.round(height * dpr));
    const ctx = canvas.getContext("2d");
    ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    return ctx;
  }

  function graphNodeIdForPane(paneId) {
    const direct = graphData.nodes.find((node) => node.id === paneId);
    if (direct) return direct.id;
    const byPane = graphData.nodes.find((node) => node.pane === paneId);
    return byPane?.id || graphData.root || "now";
  }

  function visibleGraph() {
    const visible = new Set();
    if (state.graphMode === "global") {
      graphData.nodes.forEach((node) => visible.add(node.id));
    } else {
      const activeId = graphNodeIdForPane(state.activeNote);
      visible.add(activeId);
      const byId = new Map(graphData.nodes.map((node) => [node.id, node]));
      const neighbors = [];
      graphData.edges.forEach((edge) => {
        if (edge.source === activeId && byId.has(edge.target)) neighbors.push(byId.get(edge.target));
        if (edge.target === activeId && byId.has(edge.source)) neighbors.push(byId.get(edge.source));
      });
      const uniqueNeighbors = Array.from(new Map(neighbors.map((node) => [node.id, node])).values());
      const pageNeighbors = uniqueNeighbors.filter((node) => node.type === "page" || node.type === "system");
      const topicNeighbors = uniqueNeighbors
        .filter((node) => node.type === "topic")
        .sort((a, b) => Number(a.label_priority || 99) - Number(b.label_priority || 99));
      pageNeighbors.forEach((node) => visible.add(node.id));
      topicNeighbors.slice(0, activeId === "now" ? 8 : 10).forEach((node) => visible.add(node.id));
      // Keyword helper nodes support global clustering, but they are not real
      // Publish note links. Keeping them out of current-page graphs prevents a
      // local graph from looking like one labeled page dragging anonymous dots.
      if (visible.size < 10 && activeId === (graphData.root || "now")) {
        graphData.nodes
          .filter((node) => node.type === "page" || node.type === "system")
          .forEach((node) => visible.add(node.id));
        graphData.nodes
          .filter((node) => node.type === "topic")
          .sort((a, b) => Number(a.label_priority || 99) - Number(b.label_priority || 99))
          .slice(0, 8)
          .forEach((node) => visible.add(node.id));
      }
    }
    return {
      nodes: graphData.nodes.filter((node) => visible.has(node.id)).map((node) => ({ ...node })),
      edges: graphData.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target))
    };
  }

  function seed(nodes, width, height) {
    const cx = width / 2;
    const cy = height / 2;
    const span = Math.min(width, height);
    const activeRoot = graphNodeIdForPane(state.activeNote);
    const primaryRoot = state.graphMode === "local" ? activeRoot : (graphData.root || "now");
    const radiusScale = graphContainer?.classList.contains("mod-expanded")
      ? Math.min(1.16, Math.max(0.94, span / 780))
      : 0.8;
    nodes.forEach((node, index) => {
      const saved = state.positions.get(node.id);
      const canReuseSaved = saved?.width && saved?.height
        && Math.max(width / saved.width, saved.width / width) < 1.35
        && Math.max(height / saved.height, saved.height / height) < 1.35;
      const angle = index * 2.399963229728653 - Math.PI / 2;
      const normalized = Math.sqrt((index + 1) / Math.max(1, nodes.length));
      const spread = span * normalized * (node.type === "keyword" ? 0.36 : node.type === "system" ? 0.24 : 0.28);
      const isPrimaryRoot = node.id === primaryRoot;
      const shouldGlideRoot = state.graphSoftRefresh && isPrimaryRoot && canReuseSaved;
      node.x = shouldGlideRoot ? saved.x : (isPrimaryRoot ? cx : (canReuseSaved ? saved.x : cx + Math.cos(angle) * spread));
      node.y = shouldGlideRoot ? saved.y : (isPrimaryRoot ? cy : (canReuseSaved ? saved.y : cy + Math.sin(angle) * spread));
      node.vx = canReuseSaved ? saved.vx : 0;
      node.vy = canReuseSaved ? saved.vy : 0;
      const isPinnedRoot = state.graphMode === "local" && node.id === activeRoot;
      const baseRadius = isPinnedRoot ? 6.2 : (node.type === "page" ? 5.4 : node.type === "topic" ? 3.8 : node.type === "system" ? 3.4 : 2.4);
      node.r = baseRadius * radiusScale;
      node.pinnedRoot = isPinnedRoot;
      // Do not hard-pin the active node with fx/fy on navigation: D3 applies
      // fixed coordinates immediately, which reads as a visual jump. The x/y
      // forces below still make the clicked node become the new center, but it
      // glides there from its saved position.
      node.fx = null;
      node.fy = null;
    });
  }

  function tick(width, height) {
    const byId = new Map(state.nodes.map((node) => [node.id, node]));
    state.edges.forEach((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const ideal = edge.type === "HAS_KEYWORD" ? 48 : 68;
      const force = (distance - ideal) * 0.006;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      if (!source.fixed) {
        source.vx += fx;
        source.vy += fy;
      }
      if (!target.fixed) {
        target.vx -= fx;
        target.vy -= fy;
      }
    });
    for (let i = 0; i < state.nodes.length; i += 1) {
      for (let j = i + 1; j < state.nodes.length; j += 1) {
        const a = state.nodes[i];
        const b = state.nodes[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const force = 36 / (distance * distance);
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        if (!a.fixed) {
          a.vx -= fx;
          a.vy -= fy;
        }
        if (!b.fixed) {
          b.vx += fx;
          b.vy += fy;
        }
      }
    }
    const cx = width / 2;
    const cy = height / 2;
    state.nodes.forEach((node) => {
      if (!node.fixed) {
        node.vx += (cx - node.x) * 0.0025;
        node.vy += (cy - node.y) * 0.0025;
        node.vx *= 0.84;
        node.vy *= 0.84;
        node.x = Math.min(width - 18, Math.max(18, node.x + node.vx));
        node.y = Math.min(height - 18, Math.max(18, node.y + node.vy));
      }
      state.positions.set(node.id, { x: node.x, y: node.y, vx: node.vx, vy: node.vy, width, height });
    });
  }

  function connected(id) {
    const set = new Set([id]);
    state.edges.forEach((edge) => {
      if (edge.source === id) set.add(edge.target);
      if (edge.target === id) set.add(edge.source);
    });
    return set;
  }

  function cssVar(name, fallback) {
    return getComputedStyle(body).getPropertyValue(name).trim() || fallback;
  }

  function colorNumber(value, fallback) {
    const raw = String(value || fallback || "").trim();
    const hex = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hex) {
      const body = hex[1].length === 3
        ? hex[1].split("").map((ch) => ch + ch).join("")
        : hex[1];
      return Number.parseInt(body, 16);
    }
    const rgb = raw.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (rgb) return (Number(rgb[1]) << 16) + (Number(rgb[2]) << 8) + Number(rgb[3]);
    return colorNumber(fallback || "#38a6de", "#38a6de");
  }

  function ensurePixiRenderer(width, height) {
    if (!window.PIXI?.Application || !graphCanvas) return false;
    const resolution = Math.min(window.devicePixelRatio || 1, 2);
    if (!state.pixi) {
      try {
        const app = new window.PIXI.Application({
          view: graphCanvas,
          width,
          height,
          backgroundAlpha: 0,
          antialias: true,
          autoDensity: true,
          resolution
        });
        const links = new window.PIXI.Graphics();
        const nodes = new window.PIXI.Graphics();
        const labels = new window.PIXI.Container();
        app.stage.addChild(links);
        app.stage.addChild(nodes);
        app.stage.addChild(labels);
        state.pixi = { app, links, nodes, labels };
      } catch {
        state.pixi = null;
        return false;
      }
    }
    graphCanvas.style.width = `${width}px`;
    graphCanvas.style.height = `${height}px`;
    state.pixi.app.renderer.resize(width, height);
    resizeCanvas(hitCanvas, width, height);
    return true;
  }

  function drawPixi(width, height, muted) {
    const pixi = state.pixi;
    if (!pixi) return;
    const nodeColor = colorNumber(cssVar("--graph-node", "rgb(56, 166, 222)"), "#38a6de");
    const lineColor = colorNumber(cssVar("--graph-line", "rgba(118,117,117,0.58)"), "#767575");
    const textColor = colorNumber(cssVar("--graph-text", "rgba(136,159,170,1)"), "#889faa");
    const byId = new Map(state.nodes.map((node) => [node.id, node]));
    pixi.links.clear();
    pixi.nodes.clear();
    pixi.labels.removeChildren().forEach((child) => child.destroy({ children: true }));
    state.edges.forEach((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      const alpha = muted && (!muted.has(source.id) || !muted.has(target.id)) ? 0.1 : 0.42;
      pixi.links.lineStyle(0.75, lineColor, alpha);
      pixi.links.moveTo(source.x, source.y);
      pixi.links.lineTo(target.x, target.y);
    });
    state.nodes.forEach((node) => {
      const isMuted = muted && !muted.has(node.id);
      const fill = nodeColor;
      const alpha = isMuted ? 0.22 : (node.type === "keyword" ? 0.38 : 1);
      pixi.nodes.beginFill(fill, alpha);
      pixi.nodes.drawCircle(node.x, node.y, node.r);
      pixi.nodes.endFill();
      if (!shouldShowLabel(node, width, muted)) return;
      const label = compactGraphLabel(node.label, width, node);
      const fontSize = graphLabelFontSize(width, node);
      const text = new window.PIXI.Text(label, {
        fontFamily: cssVar("--font-default", "serif"),
        fontSize,
        fill: textColor,
        align: "center",
        resolution: Math.min(window.devicePixelRatio || 1, 2)
      });
      text.anchor.set(0.5, 1);
      text.alpha = isMuted ? 0.28 : 1;
      text.position.set(node.x, node.y - node.r - 4);
      pixi.labels.addChild(text);
    });
    pixi.app.renderer.render(pixi.app.stage);
  }

  function drawCanvas(width, height, muted) {
    if (!graphCanvas) return;
    const ctx = resizeCanvas(graphCanvas, width, height);
    resizeCanvas(hitCanvas, width, height);
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    const nodeColor = cssVar("--graph-node", "rgb(56, 166, 222)");
    const lineColor = cssVar("--graph-line", "rgba(118,117,117,0.58)");
    const textColor = cssVar("--graph-text", "rgba(136,159,170,1)");
    const byId = new Map(state.nodes.map((node) => [node.id, node]));
    ctx.lineWidth = 0.75;
    state.edges.forEach((edge) => {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) return;
      ctx.globalAlpha = muted && (!muted.has(source.id) || !muted.has(target.id)) ? 0.1 : 0.42;
      ctx.strokeStyle = lineColor;
      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
    state.nodes.forEach((node) => {
      const isMuted = muted && !muted.has(node.id);
      ctx.globalAlpha = isMuted ? 0.22 : (node.type === "keyword" ? 0.38 : 1);
      ctx.fillStyle = nodeColor;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
      ctx.fill();
      const showLabel = shouldShowLabel(node, width, muted);
      if (showLabel) {
        const fontSize = graphLabelFontSize(width, node);
        ctx.font = `${fontSize}px var(--font-default, serif)`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        const label = compactGraphLabel(node.label, width, node);
        ctx.globalAlpha = isMuted ? 0.28 : 1;
        ctx.fillStyle = textColor;
        ctx.fillText(label, node.x, node.y - node.r - 4);
      }
    });
    ctx.globalAlpha = 1;
  }

  function draw() {
    if (!graphCanvas) return;
    const { width, height } = graphSize();
    const muted = state.hovered ? connected(state.hovered) : null;
    if (ensurePixiRenderer(width, height)) {
      drawPixi(width, height, muted);
      body.dataset.graphRenderer = "pixi";
      return;
    }
    drawCanvas(width, height, muted);
    body.dataset.graphRenderer = "canvas";
  }

  function shouldShowLabel(node, width, muted) {
    if (node.id === state.hovered) return true;
    const isGlobal = state.graphMode === "global";
    const isSparseLocal = !isGlobal && state.nodes.length <= 8;
    if (node.pinnedRoot) return true;
    if (isSparseLocal) return true;
    if (node.type === "keyword") return false;
    const priority = Number(node.label_priority || 99);
    if (isGlobal && width < 300) return node.type === "page" || node.type === "system" || priority <= 8;
    if (isGlobal && width < 520) {
      return node.type === "page" || node.type === "system" || priority <= 12 || Boolean(muted?.has?.(node.id));
    }
    if (width < 300) return node.type === "page" || node.type === "system";
    if (width < 520) return node.type === "page" || node.type === "system" || priority <= 14 || Boolean(muted?.has?.(node.id));
    return true;
  }

  function graphLabelFontSize(width, node = null) {
    const base = width < 300 ? 7 : width < 520 ? 8 : Math.min(12, Math.max(9, width / 150));
    return node?.pinnedRoot ? Math.max(base + 1.5, 8.5) : base;
  }

  function compactGraphLabel(label, width, node = null) {
    const limit = node?.pinnedRoot ? (width < 300 ? 26 : 36) : (width < 300 ? 12 : width < 520 ? 18 : 28);
    return label.length > limit ? `${label.slice(0, limit)}…` : label;
  }

  function animate() {
    const { width, height } = graphSize();
    for (let i = 0; i < 3; i += 1) tick(width, height);
    draw();
    state.frame = window.requestAnimationFrame(animate);
  }

  function renderGraph(options = {}) {
    if (!graphCanvas || !graphView) return;
    state.graphSoftRefresh = Boolean(options.soft);
    if (state.frame) window.cancelAnimationFrame(state.frame);
    if (state.simulation) {
      state.simulation.stop();
      state.simulation = null;
    }
    const { width, height } = graphSize();
    const graph = visibleGraph();
    state.nodes = graph.nodes;
    state.edges = graph.edges;
    seed(state.nodes, width, height);
    draw();
    if (!startD3Simulation(width, height, { soft: state.graphSoftRefresh })) {
      body.dataset.graphEngine = state.pixi ? "pixi+manual-force" : "manual-force";
      state.frame = window.requestAnimationFrame(animate);
    }
    state.graphSoftRefresh = false;
  }

  function startD3Simulation(width, height, options = {}) {
    if (!window.d3?.forceSimulation) return false;
    body.dataset.graphEngine = state.pixi ? "pixi+d3-force" : "d3-force";
    const links = state.edges.map((edge) => ({ ...edge }));
    const expanded = graphContainer?.classList.contains("mod-expanded");
    const layoutScale = Math.max(1, Math.min(expanded ? 5.2 : 2.25, Math.min(width, height) / (expanded ? 210 : 300)));
    const linkDistance = (edge) => (edge.type === "HAS_KEYWORD" ? 25 : edge.type === "TRACKS" ? 46 : 54) * layoutScale;
    const linkStrength = (edge) => edge.type === "HAS_KEYWORD" ? 0.48 : 0.68;
    const chargeStrength = (node) => {
      if (node.type === "keyword") return -3.5 * layoutScale;
      if (node.type === "page") return -92 * layoutScale;
      if (node.type === "system") return -34 * layoutScale;
      return (state.graphMode === "global" ? -26 : -30) * layoutScale;
    };
    state.simulation = window.d3.forceSimulation(state.nodes)
      .alpha(options.soft ? 0.36 : 0.82)
      .alphaDecay(options.soft ? 0.045 : 0.035)
      .velocityDecay(options.soft ? 0.62 : 0.42)
      .force("link", window.d3.forceLink(links).id((node) => node.id).distance(linkDistance).strength(linkStrength))
      .force("charge", window.d3.forceManyBody().strength(chargeStrength).distanceMin(18).distanceMax(Math.max(width, height) * 0.75))
      .force("collide", window.d3.forceCollide((node) => node.r + (node.type === "keyword" ? 2 : 5) * layoutScale).strength(0.72).iterations(2))
      .force("center", window.d3.forceCenter(width / 2, height / 2).strength(expanded ? 0.12 : 0.18))
      .force("x", window.d3.forceX(width / 2).strength((node) => node.pinnedRoot ? (options.soft ? 0.5 : 0.34) : (expanded ? 0.028 : 0.045)))
      .force("y", window.d3.forceY(height / 2).strength((node) => node.pinnedRoot ? (options.soft ? 0.5 : 0.34) : (expanded ? 0.028 : 0.045)))
      .on("tick", () => {
        clampNodes(width, height);
        draw();
      });
    return true;
  }

  function clampNodes(width, height) {
    state.nodes.forEach((node) => {
      node.x = Math.min(width - 16, Math.max(16, node.x));
      node.y = Math.min(height - 16, Math.max(16, node.y));
      state.positions.set(node.id, { x: node.x, y: node.y, vx: node.vx || 0, vy: node.vy || 0, width, height });
    });
  }

  function pointerPoint(event) {
    const rect = graphCanvas.getBoundingClientRect();
    const { width, height } = graphSize();
    return {
      x: ((event.clientX - rect.left) / rect.width) * width,
      y: ((event.clientY - rect.top) / rect.height) * height
    };
  }

  function hitTest(point) {
    let winner = null;
    for (const node of state.nodes) {
      if (Math.hypot(node.x - point.x, node.y - point.y) <= Math.max(12, node.r + 7)) {
        winner = node;
      }
    }
    return winner;
  }

  function scheduleGraphHoverDraw() {
    if (state.hoverFrame) return;
    state.hoverFrame = window.requestAnimationFrame(() => {
      state.hoverFrame = 0;
      draw();
    });
  }

  graphCanvas?.addEventListener("pointerdown", (event) => {
    const node = hitTest(pointerPoint(event));
    if (!node) return;
    state.dragging = node;
    state.dragStart = { x: event.clientX, y: event.clientY, moved: false, node };
    node.fixed = true;
    node.fx = node.x;
    node.fy = node.y;
    state.simulation?.alphaTarget(0.16).restart();
    graphCanvas.setPointerCapture?.(event.pointerId);
  });

  graphCanvas?.addEventListener("pointermove", (event) => {
    const point = pointerPoint(event);
    if (state.dragging) {
      if (state.dragStart && Math.hypot(event.clientX - state.dragStart.x, event.clientY - state.dragStart.y) > 4) {
        state.dragStart.moved = true;
      }
      state.dragging.x = point.x;
      state.dragging.y = point.y;
      state.dragging.fx = point.x;
      state.dragging.fy = point.y;
      return;
    }
    const hit = hitTest(point);
    const nextHovered = hit?.id || null;
    if (state.hovered !== nextHovered) {
      state.hovered = nextHovered;
      scheduleGraphHoverDraw();
    }
    graphCanvas.style.cursor = hit ? "pointer" : "default";
  });

  graphCanvas?.addEventListener("pointerleave", () => {
    if (!state.hovered) return;
    state.hovered = null;
    graphCanvas.style.cursor = "default";
    scheduleGraphHoverDraw();
  });

  graphCanvas?.addEventListener("pointerup", (event) => {
    if (!state.dragging) return;
    const clicked = state.dragStart && !state.dragStart.moved ? state.dragStart.node : null;
    const wasPinnedRoot = state.dragging.pinnedRoot;
    state.dragging.fixed = false;
    state.dragging.fx = null;
    state.dragging.fy = null;
    state.dragging = null;
    state.dragStart = null;
    state.simulation?.alphaTarget(0);
    graphCanvas.releasePointerCapture?.(event.pointerId);
    if (clicked?.pane) {
      // A graph click is a focus change, not just navigation. Obsidian Publish
      // recenters the clicked note as the local graph root; keeping global mode
      // here makes the page change but leaves the old hub visually in charge.
      state.graphMode = "local";
      setMainPage(clicked.pane, { clearPanes: true, softGraph: true });
      scheduleGraphControlSync();
    }
  });

  function setGraphButtonIcon(button, iconMarkup, iconKey) {
    if (!button || button.dataset.mobileGraphIcon === iconKey) return;
    button.innerHTML = iconMarkup;
    button.dataset.mobileGraphIcon = iconKey;
  }

  function syncGraphControls() {
    const expand = document.querySelector(".graph-view-container .graph-icon.graph-expand");
    const globalToggle = document.querySelector(".graph-view-container .graph-icon.graph-global");
    const mobileDrawer = isCompactLayout() && Boolean(rightColumn?.classList.contains("mobile-tools-drawer"));
    const isGlobalView = state.graphMode === "global";
    const isExpanded = Boolean(graphContainer?.classList.contains("mod-expanded"));

    if (expand) {
      if (mobileDrawer) {
        setGraphButtonIcon(expand, mobileCurrentGraphIcon, "current");
        expand.removeAttribute("aria-hidden");
        expand.tabIndex = 0;
        expand.setAttribute("title", isGlobalView ? "切换到当前页面图谱" : "当前页面图谱");
        expand.setAttribute("aria-label", isGlobalView ? "当前页面图谱" : "当前页面图谱（当前）");
        expand.classList.toggle("is-active", !isGlobalView);
      } else {
        setGraphButtonIcon(expand, desktopGraphExpandIcon, "expand");
        expand.setAttribute("title", isExpanded ? "Collapse Graph" : (isGlobalView ? "Expand Global Graph" : "Expand Current Graph"));
        expand.setAttribute("aria-label", isExpanded ? "Collapse Graph" : (isGlobalView ? "Expand Global Graph" : "Expand Current Graph"));
        expand.classList.remove("is-active");
      }
    }

    if (globalToggle) {
      setGraphButtonIcon(
        globalToggle,
        mobileDrawer ? mobileGlobalGraphIcon : desktopGraphGlobalIcon,
        mobileDrawer ? "global-mobile" : "global-desktop"
      );
      globalToggle.setAttribute("title", mobileDrawer && isGlobalView ? "全局图谱" : "Global Graph");
      globalToggle.setAttribute("aria-label", isGlobalView ? "Global Graph (active)" : "Global Graph");
      globalToggle.classList.toggle("is-active", isGlobalView);
    }
  }

  function scheduleGraphControlSync() {
    syncGraphControls();
    window.requestAnimationFrame?.(() => {
      syncGraphControls();
      window.setTimeout(syncGraphControls, 120);
      window.setTimeout(syncGraphControls, 260);
    });
  }

  function switchMobileGraphMode(mode) {
    const nextGlobalState = mode === "global";
    if ((state.graphMode === "global") === nextGlobalState && !graphContainer?.classList.contains("mod-expanded")) {
      scheduleGraphControlSync();
      return true;
    }
    state.graphMode = nextGlobalState ? "global" : "local";
    setGraphExpanded(false);
    renderGraph();
    scheduleGraphControlSync();
    return true;
  }

  document.querySelector(".graph-global")?.addEventListener("click", (event) => {
    if (isCompactLayout() && rightColumn?.classList.contains("mobile-tools-drawer")) {
      event.preventDefault();
      switchMobileGraphMode("global");
      return;
    }
    state.graphMode = state.graphMode === "global" ? "local" : "global";
    renderGraph();
    scheduleGraphControlSync();
  });

  function setGraphExpanded(expanded) {
    if (!graphContainer) return;
    const modal = graphContainer.closest(".modal-container");
    if (expanded && !modal) {
      graphPlaceholder = document.createComment("codex-memory-graph-placeholder");
      graphContainer.parentNode?.insertBefore(graphPlaceholder, graphContainer);
      const modalContainer = document.createElement("div");
      modalContainer.className = "modal-container";
      const modalBg = document.createElement("div");
      modalBg.className = "modal-bg";
      modalBg.addEventListener("click", () => setGraphExpanded(false));
      modalContainer.appendChild(modalBg);
      modalContainer.appendChild(graphContainer);
      document.body.appendChild(modalContainer);
      graphContainer.classList.add("mod-expanded");
      window.setTimeout(renderGraph, 90);
      scheduleGraphControlSync();
      return;
    }
    if (!expanded && modal) {
      graphContainer.classList.remove("mod-expanded");
      if (graphPlaceholder?.parentNode) {
        graphPlaceholder.parentNode.insertBefore(graphContainer, graphPlaceholder);
        graphPlaceholder.remove();
      }
      graphPlaceholder = null;
      modal.remove();
      window.setTimeout(renderGraph, 90);
      scheduleGraphControlSync();
    }
  }

  document.querySelector(".graph-expand")?.addEventListener("click", (event) => {
    if (isCompactLayout() && rightColumn?.classList.contains("mobile-tools-drawer")) {
      event.preventDefault();
      switchMobileGraphMode("local");
      return;
    }
    setGraphExpanded(!graphContainer?.classList.contains("mod-expanded"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const graphButton = event.target.closest?.(".graph-icon.graph-expand, .graph-icon.graph-global");
    if (!graphButton) return;
    event.preventDefault();
    graphButton.click();
  });

  window.addEventListener("resize", () => {
    renderGraph();
    scheduleGraphControlSync();
  });
  window.codexMemoryDashboard = { openNote, setMainPage, renderGraph, switchMobileGraphMode };
  try {
    window.publish = window.publish || {};
    window.publish.currentFilepath = "现在";
    window.publish.render = window.publish.render || { currentFilepath: "现在" };
    const publishGraph = { renderer: { onResize: renderGraph }, onNavigated: renderGraph };
    Object.defineProperties(publishGraph, {
      global: {
        get() { return state.graphMode === "global"; },
        set(value) {
          state.graphMode = value ? "global" : "local";
          renderGraph();
          scheduleGraphControlSync();
        }
      },
      expanded: {
        get() { return Boolean(graphContainer?.classList.contains("mod-expanded")); },
        set(value) {
          setGraphExpanded(Boolean(value));
        }
      }
    });
    window.publish.graph = publishGraph;
  } catch {
    // The copied Publish shell may expose a read-only graph facade. Keep the
    // private adapter alive through its own event listeners and public handle.
  }

  const initialTheme = (() => {
    try {
      const stored = window.localStorage?.getItem("codex-memory-theme");
      if (stored === "light" || stored === "dark") return stored;
    } catch {
      // Ignore storage failures and fall through to the same media-query driven
      // default used by Publish-like shells.
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  })();
  setTheme(initialTheme, { persist: false });

  const initialNote = paneData[decodeURIComponent(window.location.hash.replace(/^#/, ""))] ? decodeURIComponent(window.location.hash.replace(/^#/, "")) : "now";
  syncResponsiveShell();
  setMainPage(initialNote, { clearPanes: true });
  restoreFooter();
  [0, 120, 500, 1200].forEach((delay) => window.setTimeout(restoreFooter, delay));
  renderGraph();
  scheduleGraphControlSync();
})();
"""


def nav_file_v2(label: str, note_id: str, active: bool = False, main: bool = False) -> str:
    active_class = " mod-active" if active else ""
    main_attr = " data-main='true'" if main else ""
    return (
        "<div class='tree-item'>"
        f"<a class='tree-item-self is-clickable{active_class}' href='#{html.escape(note_id)}' data-note='{html.escape(note_id)}'{main_attr}>"
        f"<span class='tree-item-inner'>{html.escape(label)}</span>"
        "</a></div>"
    )


def nav_folder_v2(label: str, children: list[str], expanded: bool = True) -> str:
    collapsed = "" if expanded else " is-collapsed"
    child_html = "\n".join(children)
    return (
        f"<div class='tree-item{collapsed}'>"
        "<div class='tree-item-self mod-collapsible is-clickable' data-folder-toggle='true'>"
        "<span class='tree-item-icon collapse-icon' aria-hidden='true'><svg viewBox='0 0 24 24' focusable='false'><path d='M9 6l6 6-6 6'/></svg></span>"
        f"<span class='tree-item-inner'>{html.escape(label)}</span>"
        "</div>"
        f"<div class='tree-item-children'>{child_html}</div>"
        "</div>"
    )


def html_dashboard_v2(
    thread_name: str,
    health: dict,
    anchors: list[dict],
    checkpoint_state: dict,
    recent_messages: list[dict],
    vault: Path,
    assets: dict[str, str] | None = None,
) -> str:
    assets = assets or {}
    site_mark = assets.get("site_mark", "")
    publish_css = assets.get("publish_css", "")
    publish_js = assets.get("publish_js", "")
    pixi_js = assets.get("pixi_js", "")
    d3_js = assets.get("d3_js", "")
    publish_link = f'  <link rel="stylesheet" href="{html.escape(publish_css)}">\n' if publish_css else ""
    publish_script = f'  <script src="{html.escape(publish_js)}"></script>\n' if publish_js else ""
    pixi_script = f'  <script src="{html.escape(pixi_js)}"></script>\n' if pixi_js else ""
    d3_script = f'  <script src="{html.escape(d3_js)}"></script>\n' if d3_js else ""
    site_title = DEFAULT_SITE_TITLE
    site_mark_html = (
        f"<img src='{html.escape(site_mark)}' alt='{html.escape(site_title)} site mark'>"
        if site_mark
        else "<div class='mark-fallback'>☯</div>"
    )
    pages = dashboard_pane_data_v2(health, anchors, checkpoint_state, recent_messages)
    pane_json = json_script(pages)
    graph_json = json_script(dashboard_graph_data(anchors))
    now_body = pages["now"]["body"]

    anchor_nav = [
        nav_file_v2(dashboard_anchor_title(anchor, idx), f"anchor-{idx}")
        for idx, anchor in enumerate(anchors, start=1)
    ]
    nav_items_html = "\n".join([
        nav_file_v2("现在", "now", active=True, main=True),
        nav_file_v2("记忆健康", "health"),
        nav_file_v2("正在追的线索", "threads"),
        nav_file_v2("建议的走法", "routes"),
        nav_folder_v2("锚点", [
            nav_file_v2("锚点总览", "anchors"),
            *anchor_nav,
        ], expanded=False),
        nav_file_v2("Heartbeat", "heartbeat"),
        nav_file_v2("最近消息", "recent"),
        nav_folder_v2("地图", [
            nav_file_v2("当前图谱", "now", main=True),
            nav_file_v2("Graphify corpus", "heartbeat"),
        ], expanded=False),
    ])
    nav_html = (
        "<div class='tree-item'>"
        "<a class='tree-item-self mod-root is-clickable' href='#now' data-note='now' data-main='true'></a>"
        f"<div class='tree-item-children'>{nav_items_html}</div>"
        "</div>"
    )

    moon_icon = "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M21 12.8A8.5 8.5 0 1 1 11.2 3a6.7 6.7 0 0 0 9.8 9.8Z'/></svg>"
    sun_icon = "<svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4'/></svg>"
    graph_icon = "<svg class='lucide lucide-git-fork' xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><circle cx='12' cy='18' r='3'/><circle cx='6' cy='6' r='3'/><circle cx='18' cy='6' r='3'/><path d='M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9'/><path d='M12 12v3'/></svg>"
    expand_icon = "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M7 7h10v10'/><path d='M7 17 17 7'/></svg>"
    global_icon = "<svg viewBox='0 0 24 24' aria-hidden='true'><circle cx='18' cy='5' r='3'/><circle cx='6' cy='12' r='3'/><circle cx='18' cy='19' r='3'/><line x1='8.59' x2='15.42' y1='13.51' y2='17.49'/><line x1='15.41' x2='8.59' y1='6.51' y2='10.49'/></svg>"
    outline_icon = "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 6h2M10 6h10M4 12h2M10 12h10M4 18h2M10 18h10'/></svg>"
    menu_icon = "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M3 6h18M3 12h18M3 18h18'/></svg>"
    mobile_tools_icon = graph_icon

    css = dashboard_css_v2()
    interaction_script = dashboard_interaction_script_v2()
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Cache-Control" content="no-store">
  <title>{html.escape(thread_name)} · {html.escape(site_title)}</title>
{publish_link}  <link rel="icon" href="data:,">
  <style>{css}</style>
</head>
<body class="styled-scrollbars theme-dark sliding-windows codex-memory-dashboard">
  <div class="published-container print has-navigation has-graph has-outline">
    <header class="site-header">
      <button id="codex-mobile-nav-btn" class="clickable-icon" type="button" aria-label="打开导航" aria-expanded="false">{menu_icon}</button>
      <a class="site-header-logo" href="#now" data-note="now" data-main="true">{site_mark_html}</a>
      <a class="site-header-text" href="#now" data-note="now" data-main="true">{html.escape(site_title)}</a>
      <button id="mobile-tools-btn" type="button" aria-label="打开互动图谱和本页目录" aria-expanded="false" hidden>{mobile_tools_icon}</button>
    </header>
    <div class="site-body">
      <aside class="site-body-left-column">
        <div class="site-body-left-column-inner">
          <a class="site-body-left-column-site-logo" href="#now" data-note="now" data-main="true">{site_mark_html}</a>
          <a class="site-body-left-column-site-name" href="#now" data-note="now" data-main="true">{html.escape(site_title)}</a>
          <div class="site-body-left-column-site-theme-toggle is-dark" role="button" tabindex="0" aria-label="切换明暗主题">
            <span class="option mod-dark">{moon_icon}</span>
            <div class="checkbox-container is-enabled"></div>
            <span class="option mod-light">{sun_icon}</span>
          </div>
          <div class="search-view-outer">
            <div class="search-view-container">
              <span class="published-search-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon lucide-search"><path d="m21 21-4.34-4.34"></path><circle cx="11" cy="11" r="8"></circle></svg></span>
              <input class="search-bar" type="text" aria-label="Search notes" placeholder="Search notes using Ctrl+K">
            </div>
          </div>
          <nav class="nav-view-outer" aria-label="Main navigation">
            <div class="nav-view">{nav_html}</div>
          </nav>
        </div>
      </aside>
      <main class="site-body-center-column">
        <div class="render-container">
          <div class="render-container-inner">
            <article class="publish-renderer codex-main-renderer" data-note-id="now" style="min-width: 700px; left: 0px; right: -664px;">
              <div class="markdown-preview-view markdown-rendered node-insert-event" tabindex="-1">
                <div class="markdown-preview-sizer markdown-preview-section">
                  <div class="markdown-preview-pusher" style="width: 1px; height: 0.1px; margin-bottom: 0px;"></div>
                  <div class="mod-header mod-ui"><h1 class="page-header" id="现在" data-heading="现在">现在</h1></div>
                  <section class="codex-note-page" data-note-id="now">
                    {now_body}
                  </section>
                </div>
              </div>
            </article>
          </div>
        </div>
      </main>
      <aside class="site-body-right-column">
        <div class="site-body-right-column-inner">
          <section id="graph" class="graph-view-outer">
            <div class="published-section-header">
              <span class="published-section-header-icon">{graph_icon}</span>
              <span class="published-section-header-label">互动图谱</span>
            </div>
            <div class="graph-view-container">
              {html_graph_canvas_v2()}
              <div class="graph-icon graph-expand" role="button" tabindex="0" title="Expand Current Graph" aria-label="Expand Current Graph">{expand_icon}</div>
              <div class="graph-icon graph-global" role="button" tabindex="0" title="Global Graph" aria-label="Global Graph">{global_icon}</div>
            </div>
          </section>
          <section class="outline-view-outer">
            <div class="published-section-header">
              <span class="published-section-header-icon">{outline_icon}</span>
              <span class="published-section-header-label">本页目录</span>
            </div>
            <nav class="outline-view" aria-label="Page outline"></nav>
          </section>
        </div>
        <footer class="site-footer"></footer>
      </aside>
    </div>
  </div>
  <script>
    window.publish = window.publish || {{}};
    window.publish.currentFilepath = "现在";
    window.publish.render = window.publish.render || {{ currentFilepath: "现在" }};
    try {{ window.localStorage.setItem("cookieConsent", "true"); }} catch (_) {{}}
  </script>
{publish_script}{pixi_script}{d3_script}  <script type="application/json" id="codex-pane-data">{pane_json}</script>
  <script type="application/json" id="codex-graph-data">{graph_json}</script>
  <script>{interaction_script}</script>
</body>
</html>"""


def dashboard_css_v2() -> str:
    return """
:root {
  color-scheme: light dark;
  --codex-pane-divider: color-mix(in srgb, var(--background-modifier-border) 54%, transparent);
}
* { box-sizing: border-box; }
html,
body {
  margin: 0;
  width: 100%;
  min-height: 100%;
}
body.codex-memory-dashboard.theme-light {
  color-scheme: light;
  --codex-pane-divider: rgba(92, 86, 76, 0.2);
}
body.codex-memory-dashboard.theme-dark {
  color-scheme: dark;
  --codex-pane-divider: rgba(166, 166, 166, 0.22);
}
body.codex-memory-dashboard {
  --site-tagline: "长期线程的私有记忆空间";
  --sidebar-left-background: var(--background-primary);
  --sidebar-right-background: var(--background-primary);
  background: var(--background-primary);
  color: var(--text-normal);
  font-family: var(--font-default, "Huiwen Mincho", "Songti SC", "STSong", "Noto Serif CJK SC", Georgia, serif);
  overflow: hidden;
}
.codex-memory-dashboard .published-container {
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
  background: var(--background-primary);
}
.codex-memory-dashboard .site-header {
  display: none;
}
.codex-memory-dashboard #codex-mobile-nav-btn,
.codex-memory-dashboard #mobile-tools-btn {
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.codex-memory-dashboard #codex-mobile-nav-btn svg,
.codex-memory-dashboard #mobile-tools-btn svg {
  display: block;
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.codex-memory-dashboard .site-body {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 300px;
  height: 100vh;
  min-height: 0;
}
.codex-memory-dashboard .site-body-left-column,
.codex-memory-dashboard .site-body-center-column,
.codex-memory-dashboard .site-body-right-column {
  min-width: 0;
  min-height: 0;
}
.codex-memory-dashboard .site-body-left-column {
  position: relative;
  overflow: auto;
  border-right: 1px solid var(--codex-pane-divider);
  padding: 12px 18px 28px;
  background: var(--sidebar-left-background);
}
.codex-memory-dashboard .site-body-center-column {
  position: relative;
  overflow: hidden;
  background: var(--background-primary);
}
.codex-memory-dashboard .render-container {
  width: 100%;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  overscroll-behavior: contain;
  position: relative;
  background: var(--background-primary);
  scrollbar-color: var(--scrollbar-thumb-bg, rgba(126, 126, 126, 0.58)) var(--background-primary);
}
.codex-memory-dashboard .render-container::-webkit-scrollbar {
  height: 14px;
  background: var(--background-primary);
}
.codex-memory-dashboard .render-container::-webkit-scrollbar-track,
.codex-memory-dashboard .render-container::-webkit-scrollbar-corner {
  background: var(--background-primary);
}
.codex-memory-dashboard .render-container::-webkit-scrollbar-thumb {
  min-width: 42px;
  border: 3px solid var(--background-primary);
  border-radius: 999px;
  background-color: var(--scrollbar-thumb-bg, rgba(126, 126, 126, 0.58));
}
.codex-memory-dashboard.theme-light .render-container::-webkit-scrollbar-thumb {
  background-color: rgba(92, 86, 76, 0.42);
}
.codex-memory-dashboard.theme-dark .render-container::-webkit-scrollbar-thumb {
  background-color: rgba(166, 166, 166, 0.55);
}
.codex-memory-dashboard .render-container-inner {
  display: flex;
  align-items: stretch;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--background-primary);
}
.codex-memory-dashboard .publish-renderer {
  position: sticky;
  height: 100%;
  background: var(--background-primary);
}
.codex-memory-dashboard .codex-main-renderer {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) {
  width: max-content;
  min-width: 100%;
  height: 100%;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) > .publish-renderer {
  position: sticky;
  flex: 0 0 800px;
  width: 800px;
  min-width: 700px;
  height: 100%;
  min-height: 0;
  border-right: 0;
  background: var(--background-primary);
  box-shadow: none;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) > .publish-renderer.mod-overlay {
  box-shadow: none;
}
.codex-memory-dashboard .codex-pane-close {
  position: sticky;
  left: 26px;
  bottom: 14px;
  z-index: 2;
  width: 24px;
  height: 24px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.codex-memory-dashboard .markdown-preview-view {
  height: 100%;
  overflow-x: auto;
  overflow-y: auto;
}
.codex-memory-dashboard .markdown-preview-sizer {
  min-height: 100%;
}
.codex-memory-dashboard .codex-main-renderer .markdown-preview-sizer {
  width: min(947px, 100%);
  max-width: none;
  margin: 0;
  padding: 24px clamp(46px, 4.4vw, 72px) 0;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) .markdown-preview-sizer.markdown-preview-section {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  padding: 24px 48px 0;
}
.codex-memory-dashboard .codex-slide-pane .markdown-rendered h1,
.codex-memory-dashboard .codex-slide-pane .page-header {
  overflow-wrap: anywhere;
}
.codex-memory-dashboard .site-body-right-column {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-left: 1px solid var(--codex-pane-divider);
  padding: 34px 24px 18px;
  background: var(--sidebar-right-background) !important;
}
.codex-memory-dashboard .site-body-right-column-inner {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding-bottom: 96px;
}
.codex-memory-dashboard .site-body-left-column-site-theme-toggle {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 5;
  display: flex;
  align-items: center;
  width: 82px;
  height: 34px;
  margin: 0;
  padding: 0 32px 12px 0;
  cursor: pointer;
}
.codex-memory-dashboard .site-body-left-column-site-theme-toggle .option {
  position: absolute;
  top: 3px;
  z-index: 2;
  width: 16px;
  height: 21px;
  color: var(--text-normal);
  pointer-events: none;
}
.codex-memory-dashboard .site-body-left-column-site-theme-toggle .option svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.codex-memory-dashboard .site-body-left-column-site-theme-toggle .mod-dark { left: 7px; }
.codex-memory-dashboard .site-body-left-column-site-theme-toggle .mod-light { left: 27px; }
.codex-memory-dashboard.theme-dark .site-body-left-column-site-theme-toggle .mod-dark,
.codex-memory-dashboard .site-body-left-column-site-theme-toggle.is-dark .mod-dark { display: block; }
.codex-memory-dashboard.theme-dark .site-body-left-column-site-theme-toggle .mod-light,
.codex-memory-dashboard .site-body-left-column-site-theme-toggle.is-dark .mod-light { display: none; }
.codex-memory-dashboard.theme-light .site-body-left-column-site-theme-toggle .mod-dark,
.codex-memory-dashboard .site-body-left-column-site-theme-toggle.is-light .mod-dark { display: none; }
.codex-memory-dashboard.theme-light .site-body-left-column-site-theme-toggle .mod-light,
.codex-memory-dashboard .site-body-left-column-site-theme-toggle.is-light .mod-light { display: block; }
.codex-memory-dashboard .checkbox-container {
  position: relative;
  left: 0;
  top: 0;
  z-index: 1;
  width: 50px;
  height: 22px;
  border-radius: 14px;
  border: 1px solid var(--background-modifier-border);
  background: var(--background-primary);
  box-shadow: none;
}
.codex-memory-dashboard.theme-dark .checkbox-container,
.codex-memory-dashboard .site-body-left-column-site-theme-toggle.is-dark .checkbox-container {
  border-color: transparent;
  background: var(--color-base-35, #403e3c);
}
.codex-memory-dashboard .checkbox-container::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 0;
  width: 16px;
  height: 16px;
  border-radius: 999px;
  background: #fff;
  transition: transform 0.16s ease;
  transform: translateX(1px);
}
.codex-memory-dashboard .checkbox-container.is-enabled::after {
  transform: translateX(26px);
}
.codex-memory-dashboard .site-body-left-column-site-logo {
  display: block;
  width: min(var(--sidebar-logo-width), var(--sidebar-logo-max-width));
  max-width: 100%;
  margin: 48px auto 12px;
}
.codex-memory-dashboard .site-body-left-column-site-logo img {
  width: 100%;
  height: auto;
}
.codex-memory-dashboard .mark-fallback {
  font-size: 150px;
  line-height: 1;
  text-align: center;
}
.codex-memory-dashboard .site-body-left-column-site-name {
  display: block;
  margin-bottom: var(--site-name-bottom-gap);
}
.codex-memory-dashboard .search-view-container {
  position: relative;
  margin: 28px 6px 28px;
}
.codex-memory-dashboard .search-view-container::before {
  content: none;
  display: none;
}
.codex-memory-dashboard .published-search-icon {
  position: absolute;
  left: 6px;
  top: 0;
  display: flex;
  align-items: center;
  width: 18px;
  height: 32px;
  color: var(--text-faint, var(--text-muted));
  pointer-events: none;
}
.codex-memory-dashboard .published-search-icon svg {
  display: block;
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
}
.codex-memory-dashboard input.search-bar {
  display: block;
  width: 100%;
  height: 32px;
  box-sizing: border-box;
  padding: 4px 8px 4px 30px;
  border: 1px solid var(--background-modifier-border);
  border-radius: var(--radius-l);
  background: var(--background-primary);
  color: var(--text-normal);
  font: inherit;
  font-size: 16px;
  line-height: normal;
}
.codex-memory-dashboard .nav-view {
  display: grid;
  gap: 5px;
  width: calc(100% - 12px);
}
.codex-memory-dashboard .tree-item[hidden] {
  display: none;
}
.codex-memory-dashboard .tree-item-self {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 23px;
  color: var(--text-normal);
  text-decoration: none;
  font-weight: 400;
}
.codex-memory-dashboard .tree-item-self:hover,
.codex-memory-dashboard .tree-item-self.mod-active {
  color: var(--text-accent-hover);
}
.codex-memory-dashboard .tree-item-icon {
  width: 10px;
  color: var(--text-muted);
  font-size: 20px;
  line-height: 1;
  transform: rotate(90deg);
}
.codex-memory-dashboard .tree-item-icon svg {
  display: block;
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.codex-memory-dashboard .tree-item.is-collapsed > .tree-item-self .tree-item-icon {
  transform: rotate(0deg);
}
.codex-memory-dashboard .tree-item.is-collapsed > .tree-item-children {
  display: none;
}
.codex-memory-dashboard .tree-item-children {
  margin-left: 20px;
  padding-left: 14px;
  border-left: 1px solid var(--codex-pane-divider);
}
.codex-memory-dashboard .nav-view > .tree-item > .tree-item-self.mod-root {
  display: block;
  width: 0;
  height: 0;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
}
.codex-memory-dashboard .nav-view > .tree-item > .tree-item-children {
  margin-left: 6px;
  padding: 2px 0 0;
  border-left: 0;
}
.codex-memory-dashboard .markdown-rendered h1,
.codex-memory-dashboard .markdown-rendered h2,
.codex-memory-dashboard .markdown-rendered h3 {
  letter-spacing: 0;
}
.codex-memory-dashboard .markdown-rendered h1 {
  margin: 0 0 0.24em;
}
.codex-memory-dashboard .markdown-rendered h2 {
  margin-top: 2.2em;
}
.codex-memory-dashboard .markdown-rendered a,
.codex-memory-dashboard .markdown-rendered .internal-link,
.codex-memory-dashboard .markdown-rendered .external-link {
  color: var(--link-color);
  text-decoration: underline;
  text-decoration-color: currentColor;
  transition: color 120ms ease, text-decoration-color 120ms ease;
}
.codex-memory-dashboard .markdown-rendered a:hover,
.codex-memory-dashboard .markdown-rendered .internal-link:hover,
.codex-memory-dashboard .markdown-rendered .external-link:hover {
  color: var(--text-accent-hover);
  text-decoration-color: var(--text-accent-hover);
}
.codex-memory-dashboard .callout[data-callout="noteinfo"] {
  margin-bottom: 58px;
}
.codex-memory-dashboard .callout[data-callout="noteinfo"] .callout-title {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0 0 18px;
  color: #1894ff;
  font-weight: 700;
}
.codex-memory-dashboard .callout[data-callout="noteinfo"] .callout-content p {
  color: var(--text-muted);
  margin: 0 0 0.2em;
}
.codex-memory-dashboard .codex-lead {
  margin: 74px 0 24px;
  color: var(--text-normal);
  font-size: calc(var(--font-text-size) * 1.22);
  font-weight: 600;
}
.codex-memory-dashboard .link-list,
.codex-memory-dashboard .status-list {
  margin: 12px 0 0;
  padding-left: 34px;
}
.codex-memory-dashboard .link-list li,
.codex-memory-dashboard .status-list li {
  margin: 0.28em 0;
}
.codex-memory-dashboard .callout[data-callout="links"] {
  margin: 26px 0;
  padding: 0 0 0 22px;
  border-left: 1px solid var(--blockquote-border-color);
  background: transparent;
  color: var(--text-muted);
}
.codex-memory-dashboard .codex-source-title {
  margin: -8px 0 28px;
  color: var(--text-muted);
  font-size: var(--font-smaller);
}
.codex-memory-dashboard .tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0 10px;
}
.codex-memory-dashboard .tags span {
  border: 1px solid var(--background-modifier-border);
  border-radius: var(--radius-s);
  color: var(--text-muted);
  font-size: var(--font-smallest);
  line-height: 1.45;
  padding: 0 6px;
}
.codex-memory-dashboard .messages {
  list-style: none;
  padding: 0;
  margin: 0;
  border-top: 1px solid var(--codex-pane-divider);
}
.codex-memory-dashboard .messages li {
  display: grid;
  grid-template-columns: 86px 1fr;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--codex-pane-divider);
  color: var(--text-muted);
  font-size: var(--font-smaller);
}
.codex-memory-dashboard .published-section-header {
  margin: 0 0 14px;
  color: var(--component-title-color);
  font-size: var(--font-small);
  font-weight: 700;
}
.codex-memory-dashboard .published-section-header-icon svg {
  display: block;
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.codex-memory-dashboard .graph-view-outer {
  margin: 0 0 38px;
}
.codex-memory-dashboard .graph-view-container {
  position: relative;
  width: 100%;
  height: 260px;
  padding: 4px;
  border: 1px solid var(--background-modifier-border);
  border-radius: var(--radius-m);
  overflow: hidden;
  background: var(--background-primary);
}
.codex-memory-dashboard .graph-view-container.mod-expanded {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  background: var(--background-primary);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.48);
}
.codex-memory-dashboard .modal-container {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 5.6vh 5vw;
}
.codex-memory-dashboard .modal-container .modal-bg {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.08);
  cursor: pointer;
}
.codex-memory-dashboard .modal-container .graph-view-container.mod-expanded {
  width: 100%;
  height: 100%;
  margin: 0;
  overflow: hidden;
}
.codex-memory-dashboard .graph-view {
  width: 100%;
  height: 100%;
}
.codex-memory-dashboard .graph-view canvas {
  position: absolute;
  inset: 4px;
  display: block;
  touch-action: none;
}
.codex-memory-dashboard .codex-graph-hit-canvas {
  opacity: 0;
  pointer-events: none;
}
.codex-memory-dashboard .graph-icon {
  position: absolute;
  z-index: 2;
  top: 6px;
  width: 18px;
  height: 23px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  cursor: pointer;
}
.codex-memory-dashboard .graph-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.codex-memory-dashboard .graph-icon:hover,
.codex-memory-dashboard .graph-icon.is-active {
  color: var(--text-accent);
}
.codex-memory-dashboard .graph-global { right: 28px; }
.codex-memory-dashboard .graph-expand { right: 6px; }
.codex-memory-dashboard .outline-view {
  display: grid;
  gap: 8px;
  margin-left: 0;
  padding-left: 22px;
  border-left: 1px solid var(--codex-pane-divider);
}
.codex-memory-dashboard .outline-view .tree-item-self {
  color: var(--text-muted);
  font-size: var(--font-smaller);
}
.codex-memory-dashboard .outline-view .tree-item-self:hover,
.codex-memory-dashboard .outline-view .tree-item-self.mod-active {
  color: var(--text-accent-hover);
}
.codex-memory-dashboard .popover.hover-popover {
  position: fixed;
  z-index: 120;
  box-sizing: border-box;
  min-height: 260px;
  max-width: min(92vw, 760px);
  overflow: hidden;
  border: 1px solid var(--background-modifier-border);
  border-radius: 8px;
  background: var(--background-primary);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.027),
    0 3.4px 6.7px rgba(0, 0, 0, 0.043),
    0 15px 30px rgba(0, 0, 0, 0.07);
}
.codex-memory-dashboard .popover.hover-popover .markdown-embed,
.codex-memory-dashboard .popover.hover-popover .markdown-embed-content {
  width: 100%;
  height: 100%;
  overflow: auto;
  background: transparent;
}
.codex-memory-dashboard .popover.hover-popover .markdown-preview-view {
  height: 100%;
  max-height: inherit;
  padding: 32px;
  box-sizing: border-box;
  overflow: auto;
  background: transparent;
}
.codex-memory-dashboard .popover.hover-popover .markdown-preview-sizer {
  box-sizing: border-box;
  width: 100% !important;
  max-width: none;
  min-height: 0;
  padding: 0;
}
.codex-memory-dashboard .hover-popover-link {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 2;
  color: var(--text-muted);
}
.codex-memory-dashboard .hover-popover-link:hover {
  color: var(--text-accent-hover);
}
.codex-memory-dashboard .hover-popover-link svg {
  width: 24px;
  height: 24px;
}
.codex-memory-dashboard .site-footer {
  position: absolute;
  left: 32px;
  right: 32px;
  bottom: 12px;
  color: var(--text-faint);
  font-size: var(--font-smallest);
  line-height: 1.35;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.codex-memory-dashboard .site-footer .foot-links {
  width: 100%;
  font-size: 11px;
  line-height: 1.25;
}

/* Source-aligned shell overrides.
   The copied Publish CSS owns the mood and typography; this dashboard layer only
   recreates the runtime shell that is not present in the static assets. Keep
   these values close to the measured public Publish DOM so later visual tweaks do
   not quietly turn the private dashboard into a different product. */
body.codex-memory-dashboard {
  font-size: 15px;
  overflow: clip;
}
.codex-memory-dashboard .site-body {
  display: flex;
  position: relative;
  height: 100vh;
  min-height: 0;
  overflow: hidden;
}
.codex-memory-dashboard .site-body-left-column {
  display: flex;
  flex: 0 0 280px;
  width: 280px;
  overflow: visible;
  padding: 32px 18px 0;
}
.codex-memory-dashboard .site-body-left-column-inner {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  min-height: 0;
  overflow: visible;
}
.codex-memory-dashboard .site-body-left-column-site-logo {
  width: min(var(--sidebar-logo-width), var(--sidebar-logo-max-width));
  margin: var(--sidebar-logo-top-gap) 0 var(--sidebar-logo-bottom-gap);
}
.codex-memory-dashboard .site-body-left-column-site-logo img {
  width: min(var(--sidebar-logo-width), var(--sidebar-logo-max-width));
  max-width: 100%;
  max-height: 200px;
  margin-inline: auto;
  object-fit: contain;
}
.codex-memory-dashboard .site-body-left-column-site-name {
  margin-bottom: var(--site-name-bottom-gap);
}
.codex-memory-dashboard .search-view-container {
  margin: 0 0 10px;
}
.codex-memory-dashboard input.search-bar {
  height: 32px;
  padding: 4px 8px 4px 30px;
  border: 1px solid var(--background-modifier-border);
  font: inherit;
  font-size: 16px;
  line-height: normal;
}
.codex-memory-dashboard .nav-view {
  display: block;
  width: calc(100% - 12px);
}
.codex-memory-dashboard .nav-view-outer {
  padding-top: 10px;
}
.codex-memory-dashboard .tree-item-self {
  min-height: 0;
  margin: 0 0 0 -1px;
  padding: 5px 9.8px 5px 16px;
  gap: 4px;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 18.2px;
}
.codex-memory-dashboard .tree-item-self:hover,
.codex-memory-dashboard .tree-item-self.mod-active {
  color: var(--text-accent-hover);
}
.codex-memory-dashboard .tree-item-icon {
  width: 10px;
  font-size: 14px;
  line-height: 1;
}
.codex-memory-dashboard .tree-item-icon svg {
  width: 14px;
  height: 14px;
}
.codex-memory-dashboard .tree-item-children {
  margin-left: 18px;
  padding-left: 14px;
}
.codex-memory-dashboard .nav-view > .tree-item > .tree-item-self.mod-root {
  display: block;
  width: 0;
  height: 0;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
}
.codex-memory-dashboard .nav-view > .tree-item > .tree-item-children {
  margin-left: 6px;
  padding: 2px 0 0;
  border-left: 0;
}
.codex-memory-dashboard .site-body-center-column {
  display: flex;
  flex-direction: column;
  flex: 1 0 0;
  width: auto;
  min-width: 0;
  overflow: hidden;
  padding-right: 300px;
}
.codex-memory-dashboard .render-container {
  display: flex;
  flex: 1 1 auto;
  width: 100%;
  max-width: none;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  background-color: var(--background-primary);
}
.codex-memory-dashboard .render-container-inner {
  display: flex;
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
}
.codex-memory-dashboard .codex-main-renderer {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) {
  flex: 0 0 auto;
  width: max-content;
  min-width: 100%;
  height: 100%;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) > .publish-renderer {
  flex: 0 0 800px;
  width: 800px;
  min-width: 700px;
  height: 100%;
  min-height: 0;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) .markdown-preview-view {
  overflow-x: auto;
  overflow-y: auto;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) .markdown-preview-sizer.markdown-preview-section {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
}
.codex-memory-dashboard .codex-main-renderer .markdown-preview-sizer {
  width: 935px;
  max-width: none;
  margin: 0;
  padding: 24px 48px 0;
}
.codex-memory-dashboard .markdown-rendered h1 {
  margin: 0;
  padding: 0;
  font-size: var(--h1-size);
  font-weight: var(--h1-weight);
  line-height: var(--h1-line-height);
}
.codex-memory-dashboard .site-body-right-column {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 300px;
  display: flex;
  flex: 0 0 300px;
  flex-direction: row;
  overflow: hidden;
  padding: 0;
  border-left: 0;
  background: transparent !important;
}
.codex-memory-dashboard .site-body-right-column-inner {
  width: 252px;
  height: 100%;
  margin: 0 24px;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding-bottom: 96px;
}
.codex-memory-dashboard .graph-view-outer {
  margin: 32px 0 0;
}
.codex-memory-dashboard .graph-view-container {
  width: 252px;
  height: 260px;
  margin-top: 12px;
  overflow: visible;
  background: var(--background-primary);
}
.codex-memory-dashboard .graph-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.codex-memory-dashboard .graph-view canvas {
  inset: 0;
}
.codex-memory-dashboard .outline-view-outer {
  margin: 0 0 24px;
  padding: 32px 0 120px;
}
.codex-memory-dashboard .site-body-right-column .published-section-header {
  margin: 0;
}
.codex-memory-dashboard .outline-view {
  display: block;
  gap: normal;
  padding-top: 12px;
  border-left: 0;
}
.codex-memory-dashboard .outline-view .tree-item-self {
  padding-top: 5px;
  padding-bottom: 5px;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 18.2px;
}
.codex-memory-dashboard .site-footer {
  left: 24px;
  right: 24px;
  bottom: 0;
  color: #7e7e7e;
  font-size: 11px;
}
.codex-memory-dashboard .publish-renderer {
  overflow: hidden;
}
.codex-memory-dashboard .render-container {
  scroll-behavior: auto;
}
.codex-memory-dashboard .render-container-inner > .publish-renderer {
  border-left: 1px solid var(--codex-pane-divider);
  transition:
    flex-basis 0.32s ease-in-out,
    min-width 0.32s ease-in-out,
    width 0.32s ease-in-out,
    left 0.32s ease-in-out,
    right 0.32s ease-in-out,
    transform 0.32s ease-in-out,
    box-shadow 0.32s ease-in-out;
}
.codex-memory-dashboard .render-container-inner > .publish-renderer:first-child {
  border-left: 0;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) > .publish-renderer {
  transition:
    flex-basis 0.32s ease-in-out,
    min-width 0.32s ease-in-out,
    width 0.32s ease-in-out,
    left 0.32s ease-in-out,
    right 0.32s ease-in-out,
    transform 0.32s ease-in-out,
    box-shadow 0.32s ease-in-out;
}
.codex-memory-dashboard .extra-title {
  display: none;
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 5;
  width: 32.8px;
  height: 100%;
  padding: 24px 6px 12px;
  overflow: hidden;
  writing-mode: vertical-lr;
  color: var(--text-normal);
  pointer-events: none;
}
.codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) > .publish-renderer > .extra-title {
  display: flex;
  pointer-events: auto;
}
.codex-memory-dashboard .extra-title-text {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  color: inherit;
  cursor: pointer;
  font-size: 16px;
  font-weight: 500;
  line-height: 20.8px;
  text-orientation: mixed;
  white-space: nowrap;
  writing-mode: vertical-lr;
}
.codex-memory-dashboard .extra-title-text:hover,
.codex-memory-dashboard .extra-title-text:focus-visible {
  color: var(--text-accent);
  outline: none;
}
.codex-memory-dashboard .codex-pane-close {
  all: unset;
  display: block;
  flex: 0 0 auto;
  width: 20.8px;
  height: 18px;
  color: currentColor;
  cursor: pointer;
  opacity: 0.76;
}
.codex-memory-dashboard .codex-pane-close svg {
  display: block;
  width: 18px;
  height: 18px;
}
.codex-memory-dashboard .codex-pane-close:hover {
  color: var(--text-accent);
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .codex-memory-dashboard .render-container {
    scroll-behavior: auto;
  }
  .codex-memory-dashboard .render-container-inner > .publish-renderer,
  .codex-memory-dashboard .render-container-inner:has(.publish-renderer.mod-overlay) > .publish-renderer {
    transition: none;
  }
}
@media (min-width: 761px) and (max-width: 1278px) {
  body.codex-memory-dashboard {
    overflow: hidden;
  }
  .codex-memory-dashboard .published-container,
  .codex-memory-dashboard .site-body {
    height: 100vh;
    min-height: 0;
    overflow: hidden;
  }
  .codex-memory-dashboard .site-body {
    display: flex;
  }
  .codex-memory-dashboard .site-body-center-column {
    flex: 1 0 0;
    width: auto;
    padding-right: 0;
    overflow: hidden;
  }
  .codex-memory-dashboard .render-container {
    display: flex;
    flex: 1 1 auto;
    width: 100%;
    height: 100%;
    overflow-x: auto;
    overflow-y: hidden;
  }
  .codex-memory-dashboard .render-container-inner {
    display: flex;
    flex: 0 1 auto;
    width: calc(100% - 300px);
    min-width: 0;
    height: 100%;
    overflow: visible;
  }
  .codex-memory-dashboard .render-container-inner > .publish-renderer {
    position: static !important;
    left: auto !important;
    right: auto !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    height: 100%;
    min-height: 0;
    flex: 1 1 auto !important;
  }
  .codex-memory-dashboard .site-body-right-column {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 300px;
    max-width: 300px;
    height: 100vh;
    flex: 0 0 300px;
    margin: 0;
    padding: 0;
    overflow: hidden;
    border-left: 0;
    border-top: 0;
  }
  .codex-memory-dashboard .site-body-right-column-inner {
    width: 252px;
    height: 100%;
    max-width: 300px;
    margin-left: 24px;
    overflow: auto;
  }
  .codex-memory-dashboard .graph-view-container {
    width: 252px !important;
  }
}
@media (max-width: 760px) {
  body.codex-memory-dashboard {
    height: auto !important;
    min-height: 100vh;
    max-height: none !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
  }
  .codex-memory-dashboard .published-container,
  .codex-memory-dashboard .site-body {
    height: auto !important;
    min-height: 100vh;
    max-height: none !important;
    overflow: visible !important;
  }
  .codex-memory-dashboard .site-body { display: block; }
  .codex-memory-dashboard .site-body-center-column {
    width: 100%;
    height: auto !important;
    max-height: none !important;
    padding-right: 0;
    overflow: visible;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .render-container {
    width: 100%;
    overflow: visible;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .render-container-inner {
    display: block;
    width: 100%;
    min-width: 0;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .codex-main-renderer {
    width: 100%;
    max-width: 100%;
    min-width: 0 !important;
    flex: 0 0 auto;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .site-body-left-column {
    width: 100%;
    box-sizing: border-box;
    border-right: 0;
    border-bottom: 1px solid var(--codex-pane-divider);
  }
  .codex-memory-dashboard .site-body-left-column-site-theme-toggle {
    position: relative;
    top: 0;
    left: 0;
    margin: 0 0 16px 5px;
  }
  .codex-memory-dashboard .site-body-left-column-site-logo { width: 180px; }
  .codex-memory-dashboard .extra-title { display: none !important; }
  .codex-memory-dashboard .codex-main-renderer .markdown-preview-sizer {
    width: 100%;
    padding: 28px 22px 72px;
  }
  .codex-memory-dashboard .site-body-right-column {
    display: block !important;
    position: relative !important;
    inset: auto !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    height: auto !important;
    max-height: none !important;
    flex: 0 0 auto !important;
    padding: 24px 22px 90px;
    overflow: visible !important;
    pointer-events: auto;
  }
  .codex-memory-dashboard .site-body-right-column-inner {
    display: block !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    height: auto !important;
    max-height: none !important;
    margin-left: 0 !important;
    padding-bottom: 96px !important;
    overflow: visible !important;
  }
  .codex-memory-dashboard .graph-view-container {
    width: min(350px, 100%) !important;
    max-width: 100% !important;
    height: 320px;
  }
  .codex-memory-dashboard .site-footer {
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box;
    padding-inline: 22px;
  }
  .codex-memory-dashboard .messages li {
    grid-template-columns: 1fr;
    gap: 2px;
  }
}
@media (max-width: 760px) {
  html,
  body.codex-memory-dashboard {
    height: 100%;
  }
  body.codex-memory-dashboard {
    min-height: 100svh !important;
    max-height: 100svh !important;
    overflow-x: hidden !important;
    overflow-y: clip !important;
  }
  .codex-memory-dashboard .published-container {
    display: flex !important;
    flex-direction: column;
    height: 100svh !important;
    min-height: 100svh !important;
    max-height: 100svh !important;
    overflow: hidden !important;
  }
  .codex-memory-dashboard .site-header {
    position: relative;
    z-index: 70;
    display: flex !important;
    flex: 0 0 auto;
    align-items: center;
    gap: 12px;
    min-height: 50px;
    padding: 7px 10px;
    border-bottom: 0;
    background: var(--background-primary);
  }
  .codex-memory-dashboard #codex-mobile-nav-btn {
    display: inline-flex !important;
    position: static !important;
    top: auto !important;
    right: auto !important;
    left: auto !important;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 32px;
    padding: 5px;
    margin: 0;
  }
  .codex-memory-dashboard .site-header-text {
    display: inline-flex;
    min-width: 0;
    max-width: calc(100vw - 112px);
    overflow: hidden;
    color: var(--site-name-color, var(--text-normal)) !important;
    font-size: 15px;
    line-height: 20px;
    text-decoration: none !important;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .codex-memory-dashboard .site-header-text::after,
  .codex-memory-dashboard .site-header-logo {
    display: none !important;
  }
  .codex-memory-dashboard #mobile-tools-btn {
    display: inline-flex;
    position: static !important;
    top: auto !important;
    right: auto !important;
    left: auto !important;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    width: 30px;
    height: 32px;
    margin: 0 12px 0 auto;
    padding: 5px;
  }
  .codex-memory-dashboard #mobile-tools-btn[hidden] {
    display: none !important;
  }
  .codex-memory-dashboard .site-body {
    display: flex !important;
    flex: 1 1 auto;
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    overflow: hidden !important;
  }
  .codex-memory-dashboard .site-body-left-column {
    position: fixed !important;
    z-index: 60;
    top: var(--mobile-shell-header-height, 50px) !important;
    left: 0 !important;
    bottom: 0 !important;
    width: 100vw !important;
    max-width: 100vw !important;
    height: calc(100svh - var(--mobile-shell-header-height, 50px)) !important;
    margin: 0 !important;
    padding: 12px 24px 32px !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    border-right: 0 !important;
    border-bottom: 0 !important;
    background: var(--sidebar-left-background, var(--background-primary));
    transform: translate3d(-100%, 0, 0);
    transition: transform 0.2s ease-in-out;
  }
  .codex-memory-dashboard .published-container.is-left-column-open .site-body-left-column {
    transform: translate3d(0, 0, 0);
  }
  .codex-memory-dashboard .site-body-left-column-site-theme-toggle {
    position: relative !important;
    top: 0 !important;
    left: 0 !important;
    margin: 0 0 16px 5px !important;
  }
  .codex-memory-dashboard .site-body-left-column-site-logo {
    width: 180px !important;
    margin-left: auto;
    margin-right: auto;
  }
  .codex-memory-dashboard .site-body-center-column {
    display: flex !important;
    flex: 1 1 auto;
    flex-direction: column;
    width: 100% !important;
    height: auto !important;
    min-width: 0;
    min-height: 0 !important;
    max-height: none !important;
    padding-right: 0 !important;
    overflow: hidden !important;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .render-container {
    display: flex !important;
    flex: 1 1 auto;
    width: 100% !important;
    height: auto !important;
    min-height: 0;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    overscroll-behavior: contain;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .render-container-inner {
    display: flex !important;
    flex: 1 0 auto;
    flex-direction: column;
    width: 100% !important;
    min-width: 0 !important;
    height: auto !important;
    min-height: 100%;
    overflow: visible !important;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .render-container-inner > .publish-renderer,
  .codex-memory-dashboard .codex-main-renderer {
    position: static !important;
    left: auto !important;
    right: auto !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    height: auto !important;
    min-height: 0 !important;
    flex: 0 0 auto !important;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .markdown-preview-view {
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .codex-main-renderer .markdown-preview-sizer {
    width: 100% !important;
    max-width: 100% !important;
    padding: 28px 22px 72px !important;
  }
  .codex-memory-dashboard .extra-title {
    display: none !important;
  }
  .codex-memory-dashboard .site-body-right-column {
    display: block !important;
    position: fixed !important;
    top: var(--mobile-shell-header-height, 50px) !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    z-index: 65;
    width: 100vw !important;
    max-width: 100vw !important;
    min-width: 0 !important;
    height: calc(100svh - var(--mobile-shell-header-height, 50px)) !important;
    max-height: none !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    border-left: 0 !important;
    border-top: 0 !important;
    background: var(--sidebar-right-background, var(--background-primary)) !important;
    pointer-events: none;
    transform: translate3d(100%, 0, 0);
    transition: transform 0.2s ease-in-out;
  }
  .codex-memory-dashboard .published-container.is-mobile-tools-open .site-body-right-column.mobile-tools-drawer {
    transform: translate3d(0, 0, 0);
    pointer-events: auto;
  }
  .codex-memory-dashboard .published-container.is-mobile-tools-open .render-container-inner {
    visibility: hidden;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .site-body-right-column-inner {
    display: flex !important;
    flex-direction: column;
    gap: 12px;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    height: 100% !important;
    margin-left: 0 !important;
    padding: 16px 20px 32px !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .graph-view-outer,
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .outline-view-outer {
    position: static !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .published-section-header {
    justify-content: flex-start;
    margin: 0 !important;
    padding: 0 0 8px;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .graph-view-container {
    width: 100% !important;
    max-width: 100% !important;
    height: min(38svh, 320px) !important;
    min-height: min(38svh, 320px);
    margin: 0 !important;
    overflow: hidden !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .graph-view-container .graph-icon.graph-expand {
    top: 10px !important;
    right: 42px !important;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .graph-view-container .graph-icon.graph-global {
    top: 10px !important;
    right: 10px !important;
  }
  .codex-memory-dashboard .site-body-right-column.mobile-tools-drawer .outline-view {
    width: 100%;
    max-height: none;
    padding: 0;
    overflow: visible !important;
    background: var(--background-primary) !important;
  }
  .codex-memory-dashboard .site-body-center-column > .site-footer {
    position: relative !important;
    left: auto !important;
    right: auto !important;
    bottom: auto !important;
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    min-height: 26px;
    width: 100% !important;
    max-width: 100% !important;
    padding: 4px 20px 8px !important;
    color: #7e7e7e;
    background: var(--background-primary);
  }
}
"""


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--automation-name")
    parser.add_argument("--no-hook", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    vault = Path(args.vault).resolve()
    vault.mkdir(parents=True, exist_ok=True)

    if not args.no_hook:
        run_text([sys.executable, str(SCRIPT_DIR / "aippocampus_maintenance.py"), "--cwd", str(cwd)])

    health = run_json([sys.executable, str(SCRIPT_DIR / "aippocampus_health.py"), "--cwd", str(cwd), "--json"])
    index_dir = cwd / ".aippocampus"
    manifest = load_json(index_dir / "manifest.json")
    checkpoint_state = load_json(index_dir / "checkpoint_state.json")
    anchors_path = cwd / "thread-anchors.md"
    anchors = parse_anchor_file(anchors_path)

    thread_slug = safe_filename(cwd.name, "thread")
    thread_home = resolve_under(vault, "Threads", thread_slug)
    anchors_dir = resolve_under(vault, "Threads", thread_slug, "Anchors")
    dashboard_dir = resolve_under(vault, "_dashboards")
    snippets_dir = resolve_under(vault, ".obsidian", "snippets")
    thread_home.mkdir(parents=True, exist_ok=True)
    anchors_dir.mkdir(parents=True, exist_ok=True)
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    snippets_dir.mkdir(parents=True, exist_ok=True)
    dashboard_assets = copy_dashboard_assets(vault)

    anchor_paths = []
    for anchor in anchors:
        title = anchor.get("title") or "Untitled Anchor"
        path = anchors_dir / f"{safe_filename(title)}.md"
        write(path, anchor_note(anchor, thread_home, vault))
        anchor_paths.append(path)

    health_path = thread_home / "Memory Health.md"
    checkpoint_path = thread_home / "Latest Checkpoint.md"
    heartbeat_path = thread_home / "Heartbeat.md"
    dashboard_path = thread_home / "Thread Overview.md"
    dashboard_html_path = dashboard_dir / f"{thread_slug}.html"

    write(health_path, health_note(health, thread_home, vault))
    write(checkpoint_path, checkpoint_note(checkpoint_state, thread_home, vault))
    write(heartbeat_path, heartbeat_note(thread_home, vault, cwd, args.automation_name))
    write(dashboard_path, dashboard_markdown(
        thread_home,
        vault,
        anchors,
        health_path,
        checkpoint_path,
        heartbeat_path,
        dashboard_html_path,
    ))
    write(vault / f"{safe_filename(DEFAULT_SITE_TITLE)} Dashboard.md", homepage(vault, dashboard_path))

    recent = read_recent_messages(index_dir / "messages.jsonl")
    write(dashboard_html_path, html_dashboard_v2(thread_slug, health, anchors, checkpoint_state, recent, vault, dashboard_assets))
    write(snippets_dir / "codex-memory-dashboard.css", obsidian_snippet_css())
    registry = register_current_thread(
        cwd,
        vault=vault,
        dashboard_note=dashboard_path,
        dashboard_html=dashboard_html_path,
        health=health,
    )

    summary = {
        "vault": str(vault),
        "thread": thread_slug,
        "dashboard_note": str(dashboard_path),
        "dashboard_html": str(dashboard_html_path),
        "anchor_notes": len(anchor_paths),
        "health_ok": health.get("ok"),
        "message_count": health.get("rollout", {}).get("message_count"),
        "anchor_count": len(anchors),
        "registry_json": registry.get("registry_json"),
        "registry_markdown": registry.get("registry_markdown"),
    }
    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"vault synced: {vault}")
        print(f"dashboard note: {dashboard_path}")
        print(f"dashboard html: {dashboard_html_path}")
        print(f"anchors: {len(anchor_paths)}")
        print(f"registry: {registry.get('registry_json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
