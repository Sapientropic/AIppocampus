#!/usr/bin/env python3
"""No-write smoke for source-backed repo familiarity packets.

The smoke uses public repo files as source rows. It does not read private
registries or emit local absolute paths; fingerprints are only used to verify
that stale cards are rejected before they become foreground work.
"""

from __future__ import annotations

import argparse
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
from aippocampus_runtime.ops import repo_familiarity_foreground_experiment_fixtures  # noqa: E402


def rel(path: str) -> str:
    return Path(path).as_posix()


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


def smoke_manifest() -> dict[str, Any]:
    commit = git_commit()
    return {
        "repo_commit": commit,
        "source_rows": (
            repo_familiarity_foreground_experiment_fixtures.current_checkout_source_rows(
                PATHS.repo_root,
                repo_commit=commit,
            )
        ),
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
