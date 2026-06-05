#!/usr/bin/env python3
"""Report aggregate AIppocampus storage size and index amplification.

The report is designed for scale planning. It stats files and reads registry or
manifest JSON only; it does not open clean-source message bodies for analysis.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.artifacts.publish import index_generation_diagnostics
from aippocampus_runtime.core import aippocampus_registry_dir, now_utc
from aippocampus_runtime.sync.bundle import iter_clean_source_sync_files, iter_registry_sync_files

CANONICAL_CLEAN_FILES = ("manifest.json", "messages.jsonl", "turns.jsonl")
SEMANTIC_SIDECAR_FILES = ("semantic-scope-labels.jsonl",)
MAIN_SQLITE_NAME = "source_index.sqlite"


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if value < 1024 or unit == "PB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def safe_stat_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            total += safe_stat_size(item)
    return total


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def report_path(path: Path, root: Path, *, include_paths: bool) -> dict[str, str]:
    result = {"relative_path": relative_path(path, root)}
    if include_paths:
        result["path"] = str(path)
    return result


def iter_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return
    for item in path.rglob("*"):
        if item.is_file():
            yield item


def registry_threads(registry_dir: Path) -> list[dict[str, Any]]:
    registry = load_json(registry_dir / "threads.json")
    threads = registry.get("threads") or []
    return [thread for thread in threads if isinstance(thread, dict)]


def thread_dir_for_entry(registry_dir: Path, entry: dict[str, Any]) -> Path | None:
    key = str(entry.get("thread_key") or "")
    paths = entry.get("paths") or {}
    store = paths.get("registry_thread_store")
    if store:
        path = Path(store)
        if not path.is_absolute():
            path = registry_dir / path
        if path.exists():
            return path
    # Registry thread directories are already slugged. Use the existing
    # directory match instead of reimplementing all historical slug rules.
    threads_dir = registry_dir / "threads"
    if not threads_dir.exists():
        return None
    candidates = [item for item in threads_dir.iterdir() if item.is_dir()]
    for candidate in candidates:
        if candidate.name == key or candidate.name == key.replace(":", "-"):
            return candidate
    if len(candidates) == 1:
        return candidates[0]
    return None


def clean_source_bytes(clean_dir: Path) -> tuple[int, int]:
    canonical = sum(safe_stat_size(clean_dir / name) for name in CANONICAL_CLEAN_FILES)
    sidecars = sum(safe_stat_size(clean_dir / name) for name in SEMANTIC_SIDECAR_FILES)
    return canonical, sidecars


def sqlite_stats(index_dir: Path) -> dict[str, int]:
    main_sqlite = index_dir / MAIN_SQLITE_NAME
    segment_sqlites = list((index_dir / "segments").glob("seg-*/source_index.sqlite"))
    return {
        "main_sqlite_count": 1 if main_sqlite.is_file() else 0,
        "main_sqlite_bytes": safe_stat_size(main_sqlite),
        "segment_sqlite_count": len(segment_sqlites),
        "segment_sqlite_bytes": sum(safe_stat_size(path) for path in segment_sqlites),
    }


def segment_manifest_count(index_dir: Path) -> int:
    manifest = load_json(index_dir / "segments" / "manifest.json")
    try:
        return int(manifest.get("segment_count") or 0)
    except (TypeError, ValueError):
        return 0


def raw_rollout_bytes(entry: dict[str, Any]) -> int:
    paths = entry.get("paths") or {}
    rollout = paths.get("rollout")
    if not rollout:
        return 0
    return safe_stat_size(Path(rollout))


def current_sync_policy_bytes(registry_dir: Path) -> tuple[int, int]:
    total = 0
    main_sqlite = 0
    for source, _relative in iter_registry_sync_files(registry_dir):
        size = safe_stat_size(source)
        total += size
        if source.name == MAIN_SQLITE_NAME:
            main_sqlite += size
    # The default bundle now moves clean source through content-addressed
    # chunks. Capacity reporting estimates that source payload by stat size
    # instead of hashing or reading private message bodies.
    for source, _relative in iter_clean_source_sync_files(registry_dir):
        total += safe_stat_size(source)
    return total, main_sqlite


def largest_files(registry_dir: Path, *, top: int, include_paths: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in iter_files(registry_dir):
        rows.append(
            {
                **report_path(path, registry_dir, include_paths=include_paths),
                "bytes": safe_stat_size(path),
                "human_bytes": human_bytes(safe_stat_size(path)),
            }
        )
    rows.sort(key=lambda item: int(item["bytes"]), reverse=True)
    return rows[:top]


def scan_thread(
    registry_dir: Path, thread_dir: Path, entry: dict[str, Any], *, include_paths: bool
) -> dict[str, Any]:
    clean_dir = thread_dir / "clean-source"
    index_dir = thread_dir / "index"
    canonical_clean, semantic_sidecars = clean_source_bytes(clean_dir)
    generated_index = dir_size(index_dir)
    sqlite = sqlite_stats(index_dir)
    raw_bytes = raw_rollout_bytes(entry)
    fanout = sqlite["segment_sqlite_count"] or sqlite["main_sqlite_count"]
    index_generations = index_generation_diagnostics(
        index_dir / MAIN_SQLITE_NAME,
        root=registry_dir,
        include_paths=include_paths,
    )

    return {
        "thread_key": entry.get("thread_key"),
        "thread_dir": thread_dir.name,
        **report_path(thread_dir, registry_dir, include_paths=include_paths),
        "raw_audit_source_bytes": raw_bytes,
        "raw_audit_source_human": human_bytes(raw_bytes),
        "canonical_clean_source_bytes": canonical_clean,
        "canonical_clean_source_human": human_bytes(canonical_clean),
        "semantic_sidecar_bytes": semantic_sidecars,
        "semantic_sidecar_human": human_bytes(semantic_sidecars),
        "generated_index_bytes": generated_index,
        "generated_index_human": human_bytes(generated_index),
        "index_amplification_ratio": ratio(generated_index, canonical_clean),
        "segment_count_declared": segment_manifest_count(index_dir),
        "query_fanout_indexes": fanout,
        "index_generations": index_generations,
        **sqlite,
    }


def sqlite_handle_count(thread: dict[str, Any]) -> int:
    return int(thread["main_sqlite_count"]) + int(thread["segment_sqlite_count"])


def query_terms(query: str | None) -> list[str]:
    if not query:
        return []
    return [
        item.casefold()
        for item in re.split(r"[^0-9A-Za-z_\-\u3400-\u9fff]+", query)
        if item.strip()
    ]


def planner_text(thread: dict[str, Any]) -> str:
    fields = [
        str(thread.get("thread_key") or ""),
        str(thread.get("thread_dir") or ""),
        str(thread.get("relative_path") or ""),
    ]
    return " ".join(fields).casefold()


def build_query_plan(
    scanned: list[dict[str, Any]],
    *,
    planner_query: str | None,
    fanout_budget: int,
) -> dict[str, Any]:
    budget = max(1, int(fanout_budget))
    worst_case = sum(sqlite_handle_count(thread) for thread in scanned)
    terms = query_terms(planner_query)
    fallback_used = False
    fallback_reason = None
    if terms:
        candidates = [
            thread
            for thread in scanned
            if all(term in planner_text(thread) for term in terms)
        ]
        if not candidates:
            candidates = list(scanned)
            fallback_used = True
            fallback_reason = "no_metadata_match"
    else:
        candidates = list(scanned)
        fallback_used = True
        fallback_reason = "no_query"

    planned: list[dict[str, Any]] = []
    planned_handles = 0
    for thread in candidates:
        handles = sqlite_handle_count(thread)
        if handles <= 0:
            continue
        if planned and planned_handles + handles > budget:
            continue
        planned.append(
            {
                "thread_key": thread.get("thread_key"),
                "thread_dir": thread.get("thread_dir"),
                "sqlite_handles": handles,
                "segment_count_declared": thread.get("segment_count_declared"),
            }
        )
        planned_handles += handles
        if planned_handles >= budget:
            break

    return {
        "kind": "registry_metadata_query_plan",
        "planner_query": planner_query,
        "terms": terms,
        "fanout_budget": budget,
        "worst_case_sqlite_handles": worst_case,
        "candidate_thread_count": len(candidates),
        "planned_thread_count": len(planned),
        "planned_sqlite_handles": planned_handles,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "budget_exhausted": planned_handles >= budget and planned_handles < worst_case,
        "planned_threads": planned,
        "boundary": "Planner uses registry metadata and segment manifests; results still join back to stable source ids.",
    }


def build_report(
    registry_dir: str | Path | None = None,
    *,
    top: int = 12,
    include_paths: bool = False,
    planner_query: str | None = None,
    fanout_budget: int = 64,
) -> dict[str, Any]:
    root = Path(registry_dir or aippocampus_registry_dir()).resolve()
    entries = registry_threads(root)
    scanned: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for entry in entries:
        thread_dir = thread_dir_for_entry(root, entry)
        if not thread_dir:
            unresolved.append({"thread_key": entry.get("thread_key"), "reason": "missing_thread_dir"})
            continue
        scanned.append(scan_thread(root, thread_dir, entry, include_paths=include_paths))

    totals: dict[str, Any] = {
        "thread_count": len(entries),
        "scanned_thread_count": len(scanned),
        "unresolved_thread_count": len(unresolved),
        "total_registry_bytes": dir_size(root),
        "raw_audit_source_bytes": sum(int(item["raw_audit_source_bytes"]) for item in scanned),
        "canonical_clean_source_bytes": sum(
            int(item["canonical_clean_source_bytes"]) for item in scanned
        ),
        "semantic_sidecar_bytes": sum(int(item["semantic_sidecar_bytes"]) for item in scanned),
        "generated_index_bytes": sum(int(item["generated_index_bytes"]) for item in scanned),
        "main_sqlite_count": sum(int(item["main_sqlite_count"]) for item in scanned),
        "main_sqlite_bytes": sum(int(item["main_sqlite_bytes"]) for item in scanned),
        "segment_sqlite_count": sum(int(item["segment_sqlite_count"]) for item in scanned),
        "segment_sqlite_bytes": sum(int(item["segment_sqlite_bytes"]) for item in scanned),
        "old_generation_count": sum(
            int((item.get("index_generations") or {}).get("old_generation_count") or 0)
            for item in scanned
        ),
        "generation_gc_candidate_count": sum(
            int((item.get("index_generations") or {}).get("generation_gc_candidate_count") or 0)
            for item in scanned
        ),
        "generation_gc_candidate_bytes": sum(
            int((item.get("index_generations") or {}).get("generation_gc_candidate_bytes") or 0)
            for item in scanned
        ),
    }
    totals["index_amplification_ratio"] = ratio(
        int(totals["generated_index_bytes"]), int(totals["canonical_clean_source_bytes"])
    )
    totals["registry_to_clean_source_ratio"] = ratio(
        int(totals["total_registry_bytes"]), int(totals["canonical_clean_source_bytes"])
    )
    for key in list(totals):
        if key.endswith("_bytes"):
            totals[key.replace("_bytes", "_human")] = human_bytes(int(totals[key]))

    sync_bytes, sync_main_sqlite_bytes = current_sync_policy_bytes(root)
    fanout_handles = int(totals["main_sqlite_count"]) + int(totals["segment_sqlite_count"])
    query_plan = build_query_plan(
        scanned,
        planner_query=planner_query,
        fanout_budget=fanout_budget,
    )
    top_threads = sorted(
        scanned,
        key=lambda item: (
            int(item["canonical_clean_source_bytes"]) + int(item["generated_index_bytes"])
        ),
        reverse=True,
    )[:top]

    return {
        "schema_version": 1,
        "created_at": now_utc(),
        "registry": report_path(root, root, include_paths=include_paths),
        "privacy": {
            "reads_clean_source_message_bodies": False,
            "reads_raw_rollout_bodies": False,
            "reads_json_manifests": True,
            "absolute_paths_included": include_paths,
        },
        "totals": totals,
        "sync": {
            "current_policy_bytes": sync_bytes,
            "current_policy_human": human_bytes(sync_bytes),
            "current_policy_main_sqlite_bytes": sync_main_sqlite_bytes,
            "current_policy_to_clean_source_ratio": ratio(
                sync_bytes, int(totals["canonical_clean_source_bytes"])
            ),
        },
        "query_fanout": {
            "worst_case_sqlite_handles": fanout_handles,
            "planned_sqlite_handles": query_plan["planned_sqlite_handles"],
            "fanout_budget": query_plan["fanout_budget"],
            "main_sqlite_count": totals["main_sqlite_count"],
            "segment_sqlite_count": totals["segment_sqlite_count"],
            "note": "Counts SQLite files a naive all-thread/all-segment lexical search may need to open.",
        },
        "query_planner": query_plan,
        "top_threads": top_threads,
        "largest_files": largest_files(root, top=top, include_paths=include_paths),
        "unresolved_threads": unresolved,
        "recommendations": recommendations(totals, sync_bytes, fanout_handles),
    }


def recommendations(totals: dict[str, Any], sync_bytes: int, fanout_handles: int) -> list[str]:
    recs: list[str] = []
    clean = int(totals["canonical_clean_source_bytes"])
    generated = int(totals["generated_index_bytes"])
    if clean >= 1024 * 1024 * 1024:
        recs.append(
            "Clean source is already GB-scale; prefer chunked manifests and delta sync before adding more runtimes."
        )
    if generated > clean and clean:
        recs.append(
            "Generated indexes are larger than canonical clean source; treat them as rebuildable local caches."
        )
    if fanout_handles >= 100:
        recs.append(
            "Worst-case SQLite fanout is high; add a registry-level query planner before broad recall."
        )
    if sync_bytes >= 1024 * 1024 * 1024:
        recs.append(
            "Current sync policy moves GB-scale data; switch to content-addressed chunks and deltas."
        )
    if not recs:
        recs.append("Storage is below GB warning thresholds, but keep tracking amplification as corpus grows.")
    return recs


def render_text(report: dict[str, Any]) -> str:
    totals = report["totals"]
    sync = report["sync"]
    fanout = report["query_fanout"]
    planner = report["query_planner"]
    lines = [
        "AIppocampus storage capacity report",
        f"- Threads: {totals['scanned_thread_count']} scanned / {totals['thread_count']} registered",
        f"- Canonical clean source: {totals['canonical_clean_source_human']}",
        f"- Generated indexes: {totals['generated_index_human']} ({totals['index_amplification_ratio']}x clean source)",
        f"- Semantic sidecars: {totals['semantic_sidecar_human']}",
        f"- Registry directory: {totals['total_registry_human']}",
        f"- Current sync policy: {sync['current_policy_human']} ({sync['current_policy_to_clean_source_ratio']}x clean source)",
        f"- Worst-case SQLite fanout: {fanout['worst_case_sqlite_handles']} handles",
        f"- Planned SQLite fanout: {planner['planned_sqlite_handles']} handles within budget {planner['fanout_budget']}",
        "",
        "Top threads:",
    ]
    for item in report["top_threads"]:
        lines.append(
            f"- {item['thread_dir']}: clean {item['canonical_clean_source_human']}, "
            f"index {item['generated_index_human']}, fanout {item['query_fanout_indexes']}"
        )
    lines.extend(["", "Recommendations:"])
    lines.extend(f"- {item}" for item in report["recommendations"])
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry-dir",
        default=None,
        help="Defaults to AIPPOCAMPUS_REGISTRY_DIR or CODEX_HOME/aippocampus-registry.",
    )
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--planner-query", default=None)
    parser.add_argument("--fanout-budget", type=int, default=64)
    parser.add_argument(
        "--include-paths",
        action="store_true",
        help="Include absolute local paths in JSON output. Off by default for privacy.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_report(
        args.registry_dir,
        top=args.top,
        include_paths=args.include_paths,
        planner_query=args.planner_query,
        fanout_budget=args.fanout_budget,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
