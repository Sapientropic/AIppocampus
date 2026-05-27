#!/usr/bin/env python3
"""Sync thread-memory artifacts into an Obsidian vault and dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from aippocampuslib import default_thread_index_dir, parse_anchor_file
from registry import register_current_thread
from vault_dashboard import html_dashboard_v2
from vault_notes import (
    anchor_note,
    checkpoint_note,
    dashboard_markdown,
    health_note,
    heartbeat_note,
    homepage,
    obsidian_snippet_css,
)
from vault_sync_utils import (
    DEFAULT_SITE_TITLE,
    DEFAULT_VAULT,
    copy_dashboard_assets,
    load_json,
    read_recent_messages,
    resolve_under,
    run_json,
    run_text,
    safe_filename,
    write,
)

SCRIPT_DIR = Path(__file__).resolve().parent


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
        run_text(
            [sys.executable, str(SCRIPT_DIR / "aippocampus_maintenance.py"), "--cwd", str(cwd)]
        )

    health = run_json(
        [sys.executable, str(SCRIPT_DIR / "aippocampus_health.py"), "--cwd", str(cwd), "--json"]
    )
    index_dir = Path((health.get("index") or {}).get("dir") or default_thread_index_dir(cwd))
    checkpoint_state = load_json(
        Path((health.get("checkpoint") or {}).get("state") or (index_dir / "checkpoint_state.json"))
    )
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
    write(
        dashboard_path,
        dashboard_markdown(
            thread_home,
            vault,
            anchors,
            health_path,
            checkpoint_path,
            heartbeat_path,
            dashboard_html_path,
        ),
    )
    write(
        vault / f"{safe_filename(DEFAULT_SITE_TITLE)} Dashboard.md", homepage(vault, dashboard_path)
    )

    recent = read_recent_messages(index_dir / "messages.jsonl")
    write(
        dashboard_html_path,
        html_dashboard_v2(
            thread_slug, health, anchors, checkpoint_state, recent, vault, dashboard_assets
        ),
    )
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
