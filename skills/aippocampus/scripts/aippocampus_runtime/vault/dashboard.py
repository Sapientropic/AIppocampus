#!/usr/bin/env python3
"""HTML dashboard rendering for AIppocampus vault sync."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.mcp.public_projection import compact_health_payload
from aippocampus_runtime.vault.utils import DEFAULT_SITE_TITLE

_DASHBOARD_ASSET_DIR = Path(__file__).with_name("dashboard_assets")
_BODY_NODE_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "dd",
    "div",
    "dl",
    "dt",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_BODY_NODE_VOID_TAGS = {"br"}
_BODY_NODE_GLOBAL_ATTRS = {
    "class",
    "data-callout",
    "data-heading",
    "data-note",
    "id",
}
_BODY_NODE_TAG_ATTRS = {"a": {"href"}}


def _load_dashboard_asset(filename: str) -> str:
    # Dashboard v2 runtime assets live as versioned files; do not inline them
    # back into Python strings.
    return (_DASHBOARD_ASSET_DIR / filename).read_text(encoding="utf-8")


def json_script(data: dict | list) -> str:
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _safe_generated_body_url(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("#"):
        return True
    if text.startswith("//"):
        return False
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", text)
    if not match:
        return True
    return match.group(1).casefold() in {"http", "https", "mailto"}


def _body_node_attrs(tag: str, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    allowed = _BODY_NODE_GLOBAL_ATTRS | _BODY_NODE_TAG_ATTRS.get(tag, set())
    result: dict[str, str] = {}
    for raw_name, raw_value in attrs:
        name = raw_name.casefold()
        value = raw_value or ""
        if name.startswith("on") or name == "style" or name not in allowed:
            continue
        if name == "href" and not _safe_generated_body_url(value):
            continue
        result[name] = value
    return result


class _DashboardBodyNodeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []

    def _children(self) -> list[dict[str, Any]]:
        if not self._stack:
            return self.nodes
        return self._stack[-1]["children"]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag not in _BODY_NODE_ALLOWED_TAGS:
            return
        node: dict[str, Any] = {
            "tag": tag,
            "attrs": _body_node_attrs(tag, attrs),
            "children": [],
        }
        self._children().append(node)
        if tag not in _BODY_NODE_VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag not in _BODY_NODE_ALLOWED_TAGS:
            return
        self._children().append(
            {
                "tag": tag,
                "attrs": _body_node_attrs(tag, attrs),
                "children": [],
            }
        )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx].get("tag") == tag:
                del self._stack[idx:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self._children().append({"text": data})


def dashboard_body_nodes(body_html: str) -> list[dict[str, Any]]:
    parser = _DashboardBodyNodeParser()
    parser.feed(body_html)
    parser.close()
    return parser.nodes


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
        nodes.append(
            {
                "id": anchor_id,
                "label": title,
                "type": "topic",
                "pane": anchor_id,
                "local": True,
                "label_priority": idx,
            }
        )
        edges.append({"source": "now", "target": anchor_id, "type": "HAS_TOPIC"})
        for keyword in anchor.get("keywords", [])[:2]:
            key = keyword.strip()
            if not key:
                continue
            keyword_id = seen_keywords.setdefault(key.lower(), f"keyword-{len(seen_keywords) + 1}")
            if not any(node["id"] == keyword_id for node in nodes):
                nodes.append(
                    {
                        "id": keyword_id,
                        "label": key,
                        "type": "keyword",
                        "pane": anchor_id,
                        "local": False,
                        "label_priority": 99,
                    }
                )
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
        nodes.append(
            {
                "id": page_id,
                "label": label,
                "type": "page",
                "pane": page_id,
                "local": True,
                "label_priority": 12,
            }
        )
        edges.append({"source": "now", "target": page_id, "type": "LINKS_TO"})
    for special_id, label in [
        ("graphify", "Graphify corpus"),
    ]:
        nodes.append(
            {
                "id": special_id,
                "label": label,
                "type": "system",
                "pane": "heartbeat" if special_id == "graphify" else special_id,
                "local": special_id != "graphify",
                "label_priority": 20,
            }
        )
        edges.append({"source": "now", "target": special_id, "type": "TRACKS"})
    return {"nodes": nodes, "edges": edges, "root": "now"}


def _first_action_command(action: Any) -> str:
    if not isinstance(action, dict):
        return ""
    for key in ("command", "cli_command", "next_command"):
        value = str(action.get(key) or "").strip()
        if value:
            return value
    for key in ("before_exact_latest_claims", "when_idle", "primary"):
        nested = _first_action_command(action.get(key))
        if nested:
            return nested
    return ""


def _health_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _foreground_health_card_html(health: dict) -> str:
    card = compact_health_payload(health)
    raw_action = card.get("foreground_action")
    action: dict[str, Any] = raw_action if isinstance(raw_action, dict) else {}
    command = _first_action_command(action) or str(
        card.get("operator_detail_command") or "aippocampus health --detail full --json"
    )
    action_id = str(action.get("id") or action.get("action_id") or "open_health_detail")
    boundary = str(
        action.get("claim_boundary")
        or card.get("output_boundary")
        or "health_status_is_a_decision_card_not_source_truth"
    )
    return "\n".join(
        [
            "<div class='foreground-action-card' data-card='memory-health-foreground'>",
            "  <div class='foreground-action-kicker'>Foreground action</div>",
            "  <h2 id='前台动作' data-heading='前台动作'>前台动作</h2>",
            "  <dl class='foreground-health-fields'>",
            f"    <div><dt>status</dt><dd>{html.escape(str(card.get('status') or 'unknown'))}</dd></div>",
            f"    <div><dt>ordinary_first_recall_usable</dt><dd>{_health_bool(card.get('ordinary_first_recall_usable'))}</dd></div>",
            f"    <div><dt>blocks_first_recall</dt><dd>{_health_bool(card.get('blocks_first_recall'))}</dd></div>",
            f"    <div><dt>blocks_exact_latest_claims</dt><dd>{_health_bool(card.get('blocks_exact_latest_claims'))}</dd></div>",
            "  </dl>",
            f"  <p class='foreground-action-label'>{html.escape(action_id)}</p>",
            f"  <p class='foreground-action-command'><code>{html.escape(command)}</code></p>",
            f"  <p class='foreground-action-boundary'>{html.escape(boundary)}</p>",
            "</div>",
        ]
    )


def dashboard_pane_data_v2(
    health: dict,
    anchors: list[dict],
    checkpoint_state: dict,
    recent_messages: list[dict],
) -> dict:
    status = "OK" if health.get("ok") else "Needs maintenance"
    checkpoint = checkpoint_state.get("last_candidate") or {}
    messages = html.escape(str(health.get("rollout", {}).get("message_count", 0)))
    anchor_count = html.escape(str(health.get("anchors", {}).get("count", 0)))
    checkpoint_state_text = "需要巩固" if health.get("checkpoint", {}).get("due") else "已巩固"
    graphify_state = "需要刷新" if health.get("graphify", {}).get("stale") else "已同步"
    foreground_health_card = _foreground_health_card_html(health)

    anchor_links = (
        "".join(
            f"<li><a class='internal-link' href='#anchor-{idx}' data-note='anchor-{idx}'>{html.escape(dashboard_anchor_title(anchor, idx))}</a></li>"
            for idx, anchor in enumerate(anchors, start=1)
        )
        or "<li>暂无锚点</li>"
    )
    recent_items = "".join(
        f"<li><span>{html.escape(msg.get('role', 'message'))}</span>{html.escape(compact_text(msg.get('text', ''), 220))}</li>"
        for msg in recent_messages[-5:]
    )

    pages: dict[str, dict[str, Any]] = {
        "now": {
            "title": "现在",
            "outline": ["前台动作", "从这里进入", "现在在追的线索", "建议的走法"],
            "body": "\n".join(
                [
                    foreground_health_card,
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
                ]
            ),
        },
        "health": {
            "title": "记忆健康",
            "outline": ["前台动作", "状态", "索引"],
            "body": "\n".join(
                [
                    foreground_health_card,
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
                ]
            ),
        },
        "threads": {
            "title": "正在追的线索",
            "outline": ["锚点列表"],
            "body": f"<h2 id='锚点列表' data-heading='锚点列表'>锚点列表</h2><ul class='link-list'>{anchor_links}</ul>",
        },
        "routes": {
            "title": "建议的走法",
            "outline": ["记忆系统路线", "精神主线路线"],
            "body": "\n".join(
                [
                    "<h2 id='记忆系统路线' data-heading='记忆系统路线'>记忆系统路线</h2>",
                    "<div class='callout' data-callout='links'><div class='callout-content'>",
                    "<p><a class='internal-link' href='#health' data-note='health'>记忆健康</a> -> <a class='internal-link' href='#heartbeat' data-note='heartbeat'>Heartbeat</a> -> <a class='internal-link' href='#anchors' data-note='anchors'>锚点</a> -> <a class='internal-link' href='#graph'>互动图谱</a></p>",
                    "</div></div>",
                    "<h2 id='精神主线路线' data-heading='精神主线路线'>精神主线路线</h2>",
                    f"<ul class='link-list'>{anchor_links}</ul>",
                ]
            ),
        },
        "anchors": {
            "title": "锚点",
            "outline": ["锚点列表"],
            "body": f"<h2 id='锚点列表' data-heading='锚点列表'>锚点列表</h2><ul class='link-list'>{anchor_links}</ul>",
        },
        "heartbeat": {
            "title": "Heartbeat",
            "outline": ["唤醒路线", "最近 checkpoint"],
            "body": "\n".join(
                [
                    "<h2 id='唤醒路线' data-heading='唤醒路线'>唤醒路线</h2>",
                    "<p>Heartbeat 会定期唤醒这个线程，运行 memory health，刷新 vault，并在 Slack / PR / feedback 连接可用时检查外部反馈；不可用时明确记为 skipped。</p>",
                    "<h2 id='最近 checkpoint' data-heading='最近 checkpoint'>最近 checkpoint</h2>",
                    f"<p>{html.escape(checkpoint.get('title', 'No checkpoint yet'))}</p>",
                ]
            ),
        },
        "recent": {
            "title": "最近消息",
            "outline": ["消息"],
            "body": f"<h2 id='消息' data-heading='消息'>消息</h2><ol class='messages'>{recent_items}</ol>"
            if recent_items
            else "<p>暂无最近消息。</p>",
        },
    }

    for idx, anchor in enumerate(anchors, start=1):
        title = dashboard_anchor_title(anchor, idx)
        source_title = anchor.get("title") or f"Anchor {idx}"
        notes = (
            "".join(f"<li>{html.escape(note)}</li>" for note in anchor.get("notes", []))
            or "<li>暂无说明。</li>"
        )
        keywords = "".join(
            f"<span>{html.escape(keyword)}</span>" for keyword in anchor.get("keywords", [])[:10]
        )
        pages[f"anchor-{idx}"] = {
            "title": title,
            "outline": ["关键词", "Notes"],
            "body": "\n".join(
                [
                    f"<p class='codex-source-title'>{html.escape(source_title)}</p>",
                    "<h2 id='关键词' data-heading='关键词'>关键词</h2>",
                    f"<div class='tags'>{keywords}</div>",
                    "<h2 id='Notes' data-heading='Notes'>Notes</h2>",
                    f"<ul>{notes}</ul>",
                ]
            ),
        }
    for page in pages.values():
        page["body_nodes"] = dashboard_body_nodes(str(page.get("body") or ""))
    return pages


def html_graph_canvas_v2() -> str:
    return """<div class="graph-view" style="padding: 0px; overflow: hidden; position: relative;">
                <canvas class="codex-graph-hit-canvas" aria-hidden="true"></canvas>
                <canvas class="codex-graph-canvas" role="img" aria-label="Thread memory graph"></canvas>
              </div>"""


def dashboard_interaction_script_v2() -> str:
    return _load_dashboard_asset("dashboard_v2.js")


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
    publish_link = (
        f'  <link rel="stylesheet" href="{html.escape(publish_css)}">\n' if publish_css else ""
    )
    publish_script = f'  <script src="{html.escape(publish_js)}"></script>\n' if publish_js else ""
    pixi_script = f'  <script src="{html.escape(pixi_js)}"></script>\n' if pixi_js else ""
    d3_script = f'  <script src="{html.escape(d3_js)}"></script>\n' if d3_js else ""
    site_title = DEFAULT_SITE_TITLE
    site_mark_html = (
        f"<img src='{html.escape(site_mark)}' alt='{html.escape(site_title)} site mark'>"
        if site_mark
        else "<div class='mark-fallback'>☯</div>"
    )
    favicon_link = (
        f'  <link rel="icon" href="{html.escape(site_mark)}">\n'
        if site_mark
        else '  <link rel="icon" href="data:,">\n'
    )
    pages = dashboard_pane_data_v2(health, anchors, checkpoint_state, recent_messages)
    pane_json = json_script(pages)
    graph_json = json_script(dashboard_graph_data(anchors))
    now_body = pages["now"]["body"]

    anchor_nav = [
        nav_file_v2(dashboard_anchor_title(anchor, idx), f"anchor-{idx}")
        for idx, anchor in enumerate(anchors, start=1)
    ]
    nav_items_html = "\n".join(
        [
            nav_file_v2("现在", "now", active=True, main=True),
            nav_file_v2("记忆健康", "health"),
            nav_file_v2("正在追的线索", "threads"),
            nav_file_v2("建议的走法", "routes"),
            nav_folder_v2(
                "锚点",
                [
                    nav_file_v2("锚点总览", "anchors"),
                    *anchor_nav,
                ],
                expanded=False,
            ),
            nav_file_v2("Heartbeat", "heartbeat"),
            nav_file_v2("最近消息", "recent"),
            nav_folder_v2(
                "地图",
                [
                    nav_file_v2("当前图谱", "now", main=True),
                    nav_file_v2("Graphify corpus", "heartbeat"),
                ],
                expanded=False,
            ),
        ]
    )
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
    menu_icon = (
        "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M3 6h18M3 12h18M3 18h18'/></svg>"
    )
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
{publish_link}{favicon_link}
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
    return _load_dashboard_asset("dashboard_v2.css")
