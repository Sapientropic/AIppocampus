#!/usr/bin/env python3
"""Sync thread-memory artifacts into an Obsidian vault and dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from aippocampus_runtime.contracts import canonical_foreground_action_fields, foreground_shell_action
from aippocampus_runtime.core import codex_home, default_thread_index_dir, parse_anchor_file
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.registry.api import register_current_thread
from aippocampus_runtime.vault.dashboard import html_dashboard_v2
from aippocampus_runtime.vault.notes import (
    anchor_note,
    checkpoint_note,
    dashboard_markdown,
    health_note,
    heartbeat_note,
    homepage,
    obsidian_snippet_css,
)
from aippocampus_runtime.vault.utils import (
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
from aippocampus_runtime.vault.sync_cards import (
    vault_status_action,
    vault_sync_read_only_payload,
)
from conversation_sources import PROVIDER_CHOICES, create_conversation_provider

# Packaged vault code lives two levels below the installable script root.
# Keep direct child-script execution anchored at that root so the projection
# remains compatible with copied skill installs and frozen binary staging.
SCRIPT_DIR = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus vault sync",
        description="Sync thread-memory artifacts into a local human-readable vault and dashboard.",
    )
    parser.add_argument("mode", nargs="?", choices=["status", "preview", "write"])
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--automation-name")
    parser.add_argument("--no-hook", action="store_true")
    parser.add_argument(
        "--provider",
        choices=PROVIDER_CHOICES,
        default="codex",
        help="Conversation source provider for registry refresh.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--operator-json", action="store_true")
    parser.add_argument("--dry-run", "--preview", action="store_true", dest="dry_run")
    parser.add_argument("--write", action="store_true", dest="write_mode")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    vault = Path(args.vault).resolve()
    write_requested = bool(args.write_mode or args.mode == "write")
    read_only_mode = "preview" if args.dry_run or args.mode == "preview" else "status"
    if not write_requested:
        payload = vault_sync_read_only_payload(
            cwd=cwd,
            vault=vault,
            mode=read_only_mode,
            automation_name=args.automation_name,
            provider=args.provider,
            include_operator_detail=bool(args.operator_json),
        )
        if args.json_output or args.operator_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("vault sync: read-only preview")
            print("next: aippocampus vault sync --dry-run --json")
            print("write: aippocampus vault sync --write --json")
        return 0

    vault.mkdir(parents=True, exist_ok=True)

    if not args.no_hook:
        run_text(
            [sys.executable, "-m", "aippocampus_runtime.ops.maintenance", "--cwd", str(cwd)]
        )

    health = run_json(
        [sys.executable, "-m", "aippocampus_runtime.health", "--cwd", str(cwd), "--json"]
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
        provider=create_conversation_provider(args.provider, codex_home_dir=codex_home()),
    )

    summary: dict[str, object] = {
        "kind": "aippocampus_vault_sync",
        "ok": True,
        "mode": "write",
        "status": "written",
        "vault": "<local-vault-redacted>",
        "thread": thread_slug,
        "dashboard_note": "<local-vault-dashboard-note-redacted>",
        "dashboard_html": "<local-vault-dashboard-html-redacted>",
        "anchor_notes": len(anchor_paths),
        "health_ok": health.get("ok"),
        "message_count": health.get("rollout", {}).get("message_count"),
        "anchor_count": len(anchors),
        "registry_json": "<local-registry-path-redacted>",
        "registry_markdown": "<local-registry-path-redacted>",
        "route_value": "vault_dashboard_written_for_human_review",
        "current_uncertainty": "vault_dashboard_write_does_not_prove_memory_correctness",
        **canonical_foreground_action_fields(
            foreground_shell_action(
                action_id="inspect_vault_dashboard",
                label="Inspect vault dashboard",
                command="aippocampus vault sync --dry-run --json",
                why="Re-run the read-only card when deciding whether another vault write is needed.",
                mutation_risk="read_only",
                claim_boundary="vault_dashboard_status_not_memory_evidence",
            ),
            safe_next_actions=[vault_status_action()],
        ),
        "write_boundary": {
            "writes_performed": True,
            "mutated": [
                "local_vault_dashboard_files",
                "local_vault_notes",
                "local_thread_registry_entry",
            ],
        },
        "privacy_boundary": {
            "local_paths_included": False,
            "writes_performed": True,
            "raw_private_text_serialized": False,
        },
    }
    if args.operator_json:
        summary["operator_detail"] = {
            "vault": str(vault),
            "dashboard_note": str(dashboard_path),
            "dashboard_html": str(dashboard_html_path),
            "registry_json": registry.get("registry_json"),
            "registry_markdown": registry.get("registry_markdown"),
        }
    summary = redact_sensitive_values(redact_private_paths(summary))
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
