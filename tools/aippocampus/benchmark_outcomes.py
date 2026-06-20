#!/usr/bin/env python3
"""Turn AIppocampus benchmark reports into compact next-action cards."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from repo_paths import ensure_repo_imports

PATHS = ensure_repo_imports(Path(__file__).resolve(), include_benchmark_tools=True)
if str(PATHS.repo_root) not in sys.path:
    sys.path.insert(0, str(PATHS.repo_root))

from shared.benchmark_outcome_router import (  # noqa: E402
    benchmark_outcome_digest,
    build_benchmark_issue_drafts,
    build_benchmark_outcome_card,
)


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PATHS.repo_root).as_posix()
    except ValueError:
        return path.name if path.is_absolute() else path.as_posix()


def _load_reports(paths: list[Path]) -> list[tuple[str, dict[str, Any]]]:
    reports: list[tuple[str, dict[str, Any]]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"benchmark report must be a JSON object: {path}")
        reports.append((_repo_relative(path), payload))
    return reports


def _print_human_cards(cards: list[dict[str, Any]]) -> None:
    for card in cards:
        print(f"{card['report_path']}:")
        print(f"- claim action: {card['claim_action']['decision']}")
        print(f"- owner action: {card['owner_action']['decision']}")
        print(f"- adoption action: {card['adoption_action']['decision']}")
        print(f"- next: {card['safe_next_action']['label']}")


def _print_human_drafts(drafts: list[dict[str, Any]]) -> None:
    if not drafts:
        print("No benchmark issue drafts: reports declare no owner action or explicit no-action.")
        return
    for index, draft in enumerate(drafts, start=1):
        print(f"<!-- benchmark issue draft {index}: {draft['title']} -->")
        print(draft["body"].rstrip())
        print()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read benchmark report JSON and emit outcome cards, issue drafts, "
            "or a first-screen digest. This never creates GitHub issues."
        )
    )
    parser.add_argument(
        "--report",
        action="append",
        type=Path,
        required=True,
        help="Benchmark report JSON path. Repeat for a digest across reports.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--issue-drafts",
        action="store_true",
        help="Emit draft-only GitHub issue bodies from owner/review action fields.",
    )
    parser.add_argument(
        "--digest",
        action="store_true",
        help="Emit only the aggregate outcome digest.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    reports = _load_reports(args.report)
    cards = [
        build_benchmark_outcome_card(report, report_path=report_path)
        for report_path, report in reports
    ]
    if args.issue_drafts:
        drafts = build_benchmark_issue_drafts(reports)
        if args.json_output:
            print(
                json.dumps(
                    {
                        "kind": "aippocampus_benchmark_issue_drafts",
                        "schema_version": 1,
                        "draft_count": len(drafts),
                        "drafts": drafts,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_human_drafts(drafts)
        return 0

    digest = benchmark_outcome_digest(cards)
    if args.digest:
        payload: dict[str, Any] = digest
    else:
        payload = {
            "kind": "aippocampus_benchmark_outcome_report",
            "schema_version": 1,
            "cards": cards,
            "digest": digest,
        }
    if args.json_output or args.digest:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human_cards(cards)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
