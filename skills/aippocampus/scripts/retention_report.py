#!/usr/bin/env python3
"""Generate a retention/safety report for a long Codex thread.

This report is intentionally conservative. It can identify data that is
compressible or rebuildable, but it does not delete anything and does not
recommend rewriting the live rollout file in place.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aippocampuslib import (
    codex_home,
    default_thread_index_dir,
    default_thread_retention_dir,
    file_sha256,
    locate_rollout,
    now_utc,
    parse_anchor_file,
    resolve_artifact_path,
)
from rollout_size_audit import audit_rollout

CORE_INDEX_FILES = {
    "manifest.json",
    "messages.jsonl",
    "source_index.sqlite",
    "graph.json",
    "checkpoint_state.json",
}


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for file in path.rglob("*"):
        if file.is_file():
            try:
                total += file.stat().st_size
            except OSError:
                pass
    return total


def pct(part: int, total: int) -> float:
    return round((part * 100.0 / total), 2) if total else 0.0


def item(
    item_id: str,
    label: str,
    *,
    kind: str,
    bytes_count: int,
    action: str,
    safety: str,
    evidence: list[str],
    path: str | None = None,
    confidence: float = 0.85,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "label": label,
        "kind": kind,
        "path": path,
        "bytes": bytes_count,
        "human_bytes": human_bytes(bytes_count),
        "action": action,
        "safety": safety,
        "evidence": evidence,
        "confidence": confidence,
    }


def class_bytes(audit: dict[str, Any], key: str) -> tuple[int, int]:
    for row in audit.get("by_class") or []:
        if row.get("key") == key:
            return int(row.get("bytes") or 0), int(row.get("count") or 0)
    return 0, 0


def generated_artifact_items(index_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not index_dir.exists():
        return items

    sqlite_path = index_dir / "source_index.sqlite"
    if sqlite_path.exists():
        size = sqlite_path.stat().st_size
        items.append(
            item(
                "rebuildable-main-sqlite",
                "Main SQLite/FTS index",
                kind="rebuildable_generated_index",
                path=str(sqlite_path),
                bytes_count=size,
                action="rebuildable_delete_under_disk_pressure",
                safety="safe_to_delete_after_raw_rollout_and_anchors_are_available",
                evidence=[
                    "Created by build_index.py from the raw rollout plus thread-anchors.md.",
                    "Deleting it only removes speed/cache, not source conversation history.",
                ],
                confidence=0.9,
            )
        )

    segments_dir = index_dir / "segments"
    if segments_dir.exists():
        segment_sqlites = list(segments_dir.glob("seg-*/source_index.sqlite"))
        segment_sqlite_bytes = sum(path.stat().st_size for path in segment_sqlites if path.exists())
        if segment_sqlites:
            items.append(
                item(
                    "rebuildable-segment-sqlite",
                    "Segment SQLite indexes",
                    kind="rebuildable_generated_index",
                    path=str(segments_dir),
                    bytes_count=segment_sqlite_bytes,
                    action="rebuildable_delete_under_disk_pressure",
                    safety="safe_to_delete_after_raw_rollout_and_anchors_are_available",
                    evidence=[
                        f"{len(segment_sqlites)} segment SQLite files found.",
                        "Created by build_segments.py; segment manifests and indexes can be rebuilt.",
                    ],
                    confidence=0.9,
                )
            )

    graphify_dir = index_dir / "graphify-corpus"
    if graphify_dir.exists():
        size = dir_size(graphify_dir)
        items.append(
            item(
                "rebuildable-graphify-corpus",
                "Graphify bridge corpus",
                kind="rebuildable_generated_corpus",
                path=str(graphify_dir),
                bytes_count=size,
                action="rebuildable_delete_under_disk_pressure",
                safety="safe_to_delete_after_index_and_anchors_are_available",
                evidence=[
                    "Created by prepare_graphify_corpus.py from index metadata, graph, anchors, and normalized messages.",
                    "Deleting it removes the prepared bridge, not the raw thread memory.",
                ],
                confidence=0.86,
            )
        )

    bundle_dir = index_dir / "bundle"
    if bundle_dir.exists():
        items.append(
            item(
                "delete-bundle-staging",
                "Temporary export bundle staging directory",
                kind="temporary_generated_staging",
                path=str(bundle_dir),
                bytes_count=dir_size(bundle_dir),
                action="delete_when_no_export_is_running",
                safety="usually_safe_to_delete_after_confirming_no_export_process_is_active",
                evidence=[
                    "export_bundle.py recreates this staging directory before each export.",
                    "It is not the canonical raw rollout or anchor file.",
                ],
                confidence=0.82,
            )
        )

    screenshot_files = [
        file
        for file in index_dir.glob("*")
        if file.is_file()
        and file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".json"}
        and file.name not in CORE_INDEX_FILES
    ]
    screenshot_bytes = sum(path.stat().st_size for path in screenshot_files if path.exists())
    if screenshot_files:
        items.append(
            item(
                "review-artifacts",
                "Ad hoc UI review screenshots/JSON traces",
                kind="user_review_artifact",
                path=str(index_dir),
                bytes_count=screenshot_bytes,
                action="archive_or_delete_after_human_review",
                safety="needs_human_confirmation",
                evidence=[
                    f"{len(screenshot_files)} non-core PNG/JPEG/WebP/JSON files found under .aippocampus.",
                    "These are useful for visual debugging but are not needed for raw text recall.",
                ],
                confidence=0.78,
            )
        )

    return items


def build_report(
    cwd: Path,
    rollout: Path,
    *,
    index_dir: Path,
    anchors: Path,
    top: int = 12,
    hash_rollout: bool = True,
) -> dict[str, Any]:
    audit = audit_rollout(rollout, top=top)
    rollout_size = int(audit["size_bytes"])
    anchors_count = len(parse_anchor_file(anchors))
    compaction = audit.get("compaction") or {}
    images = audit.get("embedded_images") or {}
    tool_output_bytes, tool_output_count = class_bytes(audit, "tool_function_call_output")
    turn_context_bytes, turn_context_count = class_bytes(audit, "event_turn_context")

    items: list[dict[str, Any]] = [
        item(
            "must-keep-active-rollout",
            "Active Codex rollout JSONL",
            kind="live_source_of_truth",
            path=str(rollout),
            bytes_count=rollout_size,
            action="do_not_modify_live_file",
            safety="must_keep",
            evidence=[
                "This is the active Codex Desktop/CLI session source used for resume/history.",
                "Cold archive may copy/compress it, but live mutation is intentionally out of scope.",
            ],
            confidence=0.93,
        ),
        item(
            "compress-raw-rollout-copy",
            "Cold compressed copy of raw rollout",
            kind="cold_archive_candidate",
            path=str(rollout),
            bytes_count=rollout_size,
            action="compress_copy_with_cold_archive.py",
            safety="safe_non_destructive_copy",
            evidence=[
                "A gzip copy preserves raw bytes without touching the active rollout.",
                "SHA-256 can verify the archive against the live source.",
            ],
            confidence=0.9,
        ),
        item(
            "must-keep-anchors",
            "Thread anchors",
            kind="human_recall_map",
            path=str(anchors) if anchors.exists() else None,
            bytes_count=anchors.stat().st_size if anchors.exists() else 0,
            action="keep_and_version",
            safety="must_keep",
            evidence=[
                f"{anchors_count} anchors parsed.",
                "Anchors tell future agents what to search for after compaction.",
            ],
            confidence=0.92,
        ),
        item(
            "compress-compaction-snapshots",
            "Compaction snapshot payloads inside raw rollout",
            kind="compressible_inside_raw_rollout",
            path=str(rollout),
            bytes_count=int(compaction.get("bytes") or 0),
            action="compress_in_cold_archive_only",
            safety="do_not_strip_from_live_rollout",
            evidence=[
                f"{int(compaction.get('count') or 0)} compacted lines.",
                f"{int(compaction.get('replacement_history_items') or 0)} replacement_history entries.",
                f"{pct(int(compaction.get('bytes') or 0), rollout_size)}% of current rollout bytes.",
            ],
            confidence=0.86,
        ),
        item(
            "compress-image-payloads",
            "Embedded image payload carrier lines",
            kind="compress_or_externalize_candidate",
            path=str(rollout),
            bytes_count=int(images.get("carrier_line_bytes") or 0),
            action="compress_in_cold_archive_only",
            safety="do_not_strip_from_live_rollout_without_app_support",
            evidence=[
                f"{int(images.get('count') or 0)} image payload references/data entries detected.",
                f"{int(images.get('carrier_line_bytes') or 0)} carrier-line bytes.",
            ],
            confidence=0.8,
        ),
        item(
            "compress-tool-output",
            "Tool function output lines",
            kind="compressible_inside_raw_rollout",
            path=str(rollout),
            bytes_count=tool_output_bytes,
            action="compress_in_cold_archive_only",
            safety="do_not_strip_from_live_rollout",
            evidence=[
                f"{tool_output_count} function_call_output lines.",
                "Tool outputs can be large but may be needed to reconstruct task provenance.",
            ],
            confidence=0.82,
        ),
        item(
            "compress-turn-context",
            "Turn context/event envelope lines",
            kind="compressible_inside_raw_rollout",
            path=str(rollout),
            bytes_count=turn_context_bytes,
            action="compress_in_cold_archive_only",
            safety="do_not_strip_from_live_rollout",
            evidence=[
                f"{turn_context_count} event_turn_context lines.",
                "These are app/session envelopes, not user-visible text, but may be needed by resume logic.",
            ],
            confidence=0.76,
        ),
    ]
    items.extend(generated_artifact_items(index_dir))

    totals: dict[str, int] = {}
    for entry in items:
        totals[entry["action"]] = totals.get(entry["action"], 0) + int(entry["bytes"] or 0)

    return {
        "schema_version": 1,
        "created_at": now_utc(),
        "cwd": str(cwd),
        "rollout": {
            "path": str(rollout),
            "size_bytes": rollout_size,
            "sha256": file_sha256(rollout) if hash_rollout else None,
        },
        "anchors": {
            "path": str(anchors),
            "exists": anchors.exists(),
            "count": anchors_count,
        },
        "index_dir": str(index_dir),
        "audit_summary": {
            "visible_indexed_messages": audit.get("visible_indexed_messages"),
            "visible_indexed_text_bytes": audit.get("visible_indexed_text_bytes"),
            "visible_indexed_text_percent": audit.get("visible_indexed_text_percent"),
            "compaction_bytes": int(compaction.get("bytes") or 0),
            "embedded_image_carrier_bytes": int(images.get("carrier_line_bytes") or 0),
            "tool_output_bytes": tool_output_bytes,
            "turn_context_bytes": turn_context_bytes,
            "largest_lines": audit.get("largest_lines") or [],
        },
        "items": items,
        "totals_by_action": {
            action: {
                "bytes": size,
                "human_bytes": human_bytes(size),
                "rollout_percent": pct(size, rollout_size),
            }
            for action, size in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        },
        "recommendations": [
            "Create a cold archive before any manual cleanup.",
            "Do not rewrite the active rollout JSONL in place.",
            "Use generated-index deletion only as a disk-pressure measure; rebuild immediately when recall speed matters.",
            "Move day-to-day work to a fresh thread and recall this thread through registry/segments if Desktop UI lag is the main pain.",
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Thread Retention Report",
        "",
        f"- Created: {report['created_at']}",
        f"- Rollout: `{report['rollout']['path']}`",
        f"- Rollout size: {human_bytes(int(report['rollout']['size_bytes']))}",
        f"- Rollout SHA-256: `{report['rollout']['sha256'] or 'not computed'}`",
        f"- Anchors: {report['anchors']['count']}",
        "",
        "## Summary",
        "",
        f"- Visible indexed text: {human_bytes(int(report['audit_summary']['visible_indexed_text_bytes'] or 0))} "
        f"({report['audit_summary']['visible_indexed_text_percent']}% of rollout)",
        f"- Compaction payloads: {human_bytes(int(report['audit_summary']['compaction_bytes']))}",
        f"- Embedded image carrier lines: {human_bytes(int(report['audit_summary']['embedded_image_carrier_bytes']))}",
        f"- Tool outputs: {human_bytes(int(report['audit_summary']['tool_output_bytes']))}",
        f"- Turn context envelopes: {human_bytes(int(report['audit_summary']['turn_context_bytes']))}",
        "",
        "## Retention Items",
        "",
        "| Safety | Action | Item | Size | Evidence |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for entry in report["items"]:
        evidence = "<br>".join(entry["evidence"])
        lines.append(
            f"| `{entry['safety']}` | `{entry['action']}` | {entry['label']} | "
            f"{entry['human_bytes']} | {evidence} |"
        )
    lines.extend(
        [
            "",
            "## Totals By Action",
            "",
            "| Action | Size | Rollout % |",
            "| --- | ---: | ---: |",
        ]
    )
    for action, row in report["totals_by_action"].items():
        lines.append(f"| `{action}` | {row['human_bytes']} | {row['rollout_percent']}% |")
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
        ]
    )
    for rec in report["recommendations"]:
        lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--index-dir", default=None, help="Defaults to the CODEX_HOME global thread store."
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the global thread store's retention directory.",
    )
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--no-hash", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else locate_rollout(cwd, codex_home())
    index_dir = resolve_artifact_path(args.index_dir, cwd, default_thread_index_dir(cwd, rollout))
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    output_dir = resolve_artifact_path(
        args.output_dir, cwd, default_thread_retention_dir(cwd, rollout)
    )

    report = build_report(
        cwd,
        rollout,
        index_dir=index_dir,
        anchors=anchors,
        top=args.top,
        hash_rollout=not args.no_hash,
    )
    if args.write:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "retention_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output_dir / "retention_report.md").write_text(markdown_report(report), encoding="utf-8")

    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown_report(report))
        if args.write:
            print(f"\nWrote: {output_dir / 'retention_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
