#!/usr/bin/env python3
"""No-write smoke for source-backed repo familiarity packets.

The smoke uses public repo files as source rows. It does not read private
registries or emit local absolute paths; fingerprints are only used to verify
that stale cards are rejected before they become foreground work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from repo_paths import ensure_repo_imports

PATHS = ensure_repo_imports(Path(__file__))

from aippocampus_runtime.navigation import repo_familiarity  # noqa: E402


def rel(path: str) -> str:
    return Path(path).as_posix()


def file_sha256(repo_relative: str) -> str:
    data = (PATHS.repo_root / repo_relative).read_bytes()
    return hashlib.sha256(data).hexdigest()


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PATHS.repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def source_row(
    *,
    kind: str,
    landmark: str,
    route_terms: list[str],
    boundary: str,
    route: dict[str, list[str]],
    source_path: str,
    source_line: int,
    why_now: str,
    action_delta_required: str,
    first_source_to_reopen: str,
    stop_after: str,
    do_not_use_for: list[str] | None = None,
    decision_shadow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    invalidation_paths = sorted({source_path, first_source_to_reopen})
    return {
        "kind": kind,
        "landmark": landmark,
        "route_terms": route_terms,
        "boundary": boundary,
        "route": route,
        "decision_shadow": decision_shadow or {},
        "source_refs": [{"path": source_path, "line": source_line}],
        "freshness": "current",
        "invalidation": {
            "commit": git_commit(),
            "files": [
                {"path": path, "sha256": file_sha256(path)}
                for path in invalidation_paths
                if (PATHS.repo_root / path).exists()
            ],
        },
        "why_now": why_now,
        "action_delta_required": action_delta_required,
        "first_source_to_reopen": first_source_to_reopen,
        "stop_after": stop_after,
        "do_not_use_for": do_not_use_for or [],
    }


def smoke_manifest() -> dict[str, Any]:
    return {
        "repo_commit": git_commit(),
        "source_rows": [
            source_row(
                kind="docs_boundary",
                landmark="source-backed memory boundary",
                route_terms=["source", "truth", "memory"],
                boundary="Source is ground; interpretation and scent remain navigation.",
                route={"docs": [rel("docs/research/source-as-world.md")]},
                source_path=rel("docs/research/source-as-world.md"),
                source_line=28,
                why_now="Relevant when a task may turn navigation hints into memory claims.",
                action_delta_required="Reopen source docs before making a memory-backed claim.",
                first_source_to_reopen=rel("docs/research/source-as-world.md"),
                stop_after="Stop once the source-vs-weather boundary is confirmed.",
                do_not_use_for=["current repo facts without reopening source"],
            ),
            source_row(
                kind="runtime_owner",
                landmark="foreground hook semantic budget",
                route_terms=["hook", "semantic", "budget"],
                boundary="Foreground hook must stay cheap and fail open.",
                route={
                    "files": [rel("skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py")],
                    "tests": [rel("tests/aippocampus/test_aippocampus_prompt_hook.py")],
                },
                source_path=rel("docs/architecture/cognitive-runtime-architecture.md"),
                source_line=160,
                why_now="May affect hook timeout and route visibility decisions.",
                action_delta_required="Inspect hook prompt owner and hook tests before changing semantic budget.",
                first_source_to_reopen=rel("skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"),
                stop_after="Stop after hook owner and tests confirm the budget boundary.",
                do_not_use_for=["unrelated README/public readiness edits"],
            ),
            source_row(
                kind="compat_shim",
                landmark="compatibility shim cleanup",
                route_terms=["compat", "shim", "package owner"],
                boundary="Flat shims are temporary unless documented as direct commands.",
                route={
                    "docs": [rel("docs/architecture/compatibility-shim-inventory.md")],
                    "tests": [rel("tests/aippocampus/test_compat_shim_inventory.py")],
                },
                source_path=rel("docs/architecture/compatibility-shim-inventory.md"),
                source_line=1,
                why_now="Relevant when deleting flat runtime scripts or changing packaging exposure.",
                action_delta_required="Run the inventory before deleting another flat shim.",
                first_source_to_reopen=rel("docs/architecture/compatibility-shim-inventory.md"),
                stop_after="Stop after inventory explains the shim bucket and removal condition.",
                do_not_use_for=["current code claims without inventory output"],
            ),
            source_row(
                kind="test_boundary",
                landmark="storage governance rebuildable cache",
                route_terms=["storage", "governance", "cache"],
                boundary="Apply mode only evicts supported rebuildable caches with manifests.",
                route={
                    "files": [rel("skills/aippocampus/scripts/aippocampus_runtime/ops/storage_governance.py")],
                    "tests": [rel("tests/aippocampus/test_storage_governance.py")],
                },
                source_path=rel("docs/architecture/gb-scale-roadmap.md"),
                source_line=90,
                why_now="Relevant when touching storage GC or cache eviction contracts.",
                action_delta_required="Inspect storage governance tests before changing apply behavior.",
                first_source_to_reopen=rel("tests/aippocampus/test_storage_governance.py"),
                stop_after="Stop after manifest and health degraded/rebuildable behavior are verified.",
                do_not_use_for=["raw source deletion"],
            ),
            source_row(
                kind="decision_shadow",
                landmark="rejected registry route card",
                route_terms=["registry", "rejected", "route"],
                boundary="Rejected-route hints require current source reopen before warning.",
                route={"tests": [rel("tests/aippocampus/test_coding_ticket_host_contract.py")]},
                source_path=rel("docs/research/agent-coding-context-analysis.md"),
                source_line=313,
                why_now="Relevant when a task may repeat an old rejected registry route.",
                action_delta_required="Check the host contract before surfacing a rejected-route warning.",
                first_source_to_reopen=rel("docs/research/agent-coding-context-analysis.md"),
                stop_after="Stop after source thickness and current visibility are checked.",
                do_not_use_for=["routine README edits", "unrelated public-readiness work"],
                decision_shadow={"status": "candidate", "source_thickness": "usable"},
            ),
        ],
    }


def current_fingerprints(cards: list[dict[str, Any]]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for card in cards:
        invalidation = card.get("invalidation") or {}
        for item in invalidation.get("files") or []:
            path = item.get("path")
            digest = item.get("sha256")
            if path and digest:
                fingerprints[str(path)] = str(digest)
    return fingerprints


def run_smoke() -> dict[str, Any]:
    manifest = smoke_manifest()
    cards = repo_familiarity.build_repo_familiarity_cards(manifest)
    commit = str(manifest.get("repo_commit") or "")
    fingerprints = current_fingerprints(cards)
    packet = repo_familiarity.select_repo_familiarity_packet(
        cards,
        task="Change prompt hook semantic budget without increasing foreground latency",
        current_fingerprints=fingerprints,
        current_commit=commit,
        max_cards=2,
        max_packet_bytes=2200,
    )
    stale_fingerprints = dict(fingerprints)
    stale_fingerprints[rel("skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py")] = "stale"
    stale_packet = repo_familiarity.select_repo_familiarity_packet(
        cards,
        task="Change prompt hook semantic budget",
        current_fingerprints=stale_fingerprints,
        current_commit=commit,
        max_cards=3,
    )
    readme_packet = repo_familiarity.select_repo_familiarity_packet(
        cards,
        task="Polish README public readiness copy",
        current_fingerprints=fingerprints,
        current_commit=commit,
        max_cards=3,
    )
    stale_fast_rejects = [
        item for item in stale_packet["rejected_cards"] if item["reason"] == "stale_invalidation"
    ]
    ok = (
        5 <= len(cards) <= 12
        and len(packet["selected_cards"]) <= 2
        and packet["cost_delta_report"]["cannot_claim_live_cost_reduction"]
        and bool(stale_fast_rejects)
        and "rejected registry route card"
        not in json.dumps(readme_packet["selected_cards"], ensure_ascii=False)
    )
    return {
        "ok": ok,
        "kind": "aippocampus_repo_familiarity_smoke",
        "card_count": len(cards),
        "packet_selected_count": len(packet["selected_cards"]),
        "packet_bytes": packet["packet_bytes"],
        "stale_fast_reject_count": len(stale_fast_rejects),
        "readme_selected_landmarks": [
            card.get("landmark") for card in readme_packet["selected_cards"]
        ],
        "cannot_claim_live_cost_reduction": packet["cost_delta_report"][
            "cannot_claim_live_cost_reduction"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the repo familiarity no-write smoke.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()
    result = run_smoke()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "repo familiarity smoke: "
            f"ok={result['ok']} cards={result['card_count']} "
            f"selected={result['packet_selected_count']} stale_fast_rejects={result['stale_fast_reject_count']}"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
