from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SOURCE_REFS = (
    "AGENTS.md",
    "docs/agent-context.md",
    "docs/guides/public-api.md",
    "docs/guides/public-core-boundary.md",
    "CONTRIBUTING.md",
)


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "README.md").is_file():
            return candidate
    raise RuntimeError("could not locate AIppocampus repository root")


def build_payload(repo_root: Path) -> dict[str, Any]:
    available_refs = [ref for ref in SOURCE_REFS if (repo_root / ref).is_file()]

    return {
        "kind": "aippocampus_first_move_demo",
        "ok": available_refs == list(SOURCE_REFS),
        "gesture": "source_backed_continuity_gesture_v1",
        "no_private_data_required": True,
        "external_api_required": False,
        "source_refs": available_refs,
        "next_actions": [
            "Open AGENTS.md for repository posture and public boundaries.",
            "Use docs/agent-context.md for first-thread orientation before broad search.",
            "Use docs/guides/public-api.md for stable public surface boundaries.",
            "Use CONTRIBUTING.md before turning local context into public source.",
        ],
        "cannot_claim": [
            "No private history has been inspected.",
            "No local registry or generated recall index has been validated.",
            "This is an orientation gesture, not evidence for product readiness.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a public first-move AIppocampus gesture.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    repo_root = find_repo_root(Path(__file__).resolve())
    payload = build_payload(repo_root)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("AIppocampus first-move gesture")
        for ref in payload["source_refs"]:
            print(f"- {ref}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
