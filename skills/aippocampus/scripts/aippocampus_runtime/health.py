#!/usr/bin/env python3
"""Report health and recommended maintenance for a long Codex thread."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.core import (
    aippocampus_registry_resolution,
    codex_home,
    default_thread_checkpoint_state_path,
    default_thread_clean_source_dir,
    default_thread_graphify_corpus_dir,
    default_thread_index_dir,
    default_thread_segments_dir,
    file_sha256,
    locate_rollout,
    parse_anchor_file,
    resolve_artifact_path,
)
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.registry.store import registry_paths
from aippocampus_runtime.source.rollout import iter_messages

DEFAULT_JOBS_OUTPUT_NAME = "subconscious_jobs.jsonl"


@dataclass(frozen=True)
class HealthOptions:
    cwd: str | Path
    index_dir: str | Path | None = None
    anchors: str | Path = "thread-anchors.md"
    graphify_corpus: str | Path | None = None
    segments_dir: str | Path | None = None
    checkpoint_state: str | Path | None = None
    clean_source_dir: str | Path | None = None
    registry: str | Path | None = None
    registry_dir: str | Path | None = None
    jobs_output: str | Path | None = None
    include_question_stats: bool = False
    question_stats_details: bool = False
    question_dormant_days: int = DEFAULT_DORMANT_AFTER_DAYS
    max_stale_messages: int = 25
    max_stale_bytes: int = 5 * 1024 * 1024
    checkpoint_messages: int = 30
    deep_graph_messages: int = 1000
    deep_graph_bytes: int = 100 * 1024 * 1024
    segment_threshold_bytes: int = 100 * 1024 * 1024


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def question_health_stats(*args: Any, **kwargs: Any) -> dict[str, Any]:
    impl = importlib.import_module("aippocampus_runtime.question.health").question_health_stats
    return impl(*args, **kwargs)


def aggregate_question_health_stats(payload: Mapping[str, Any]) -> dict[str, Any]:
    impl = importlib.import_module(
        "aippocampus_runtime.question.health"
    ).aggregate_question_health_stats
    return impl(payload)


def count_messages(rollout: Path) -> tuple[int, int | None]:
    count = 0
    last_line = None
    for msg in iter_messages(rollout):
        count += 1
        last_line = msg["line"]
    return count, last_line


def action(action_id: str, severity: str, reason: str, command: str) -> dict[str, str]:
    return {"id": action_id, "severity": severity, "reason": reason, "command": command}


def quote_posix_double(value: str | Path) -> str:
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    )
    return f'"{escaped}"'


def recommended_script_command(script_name: str, cwd: str | Path) -> str:
    if os.name == "nt":
        windows_cwd = str(PureWindowsPath(str(cwd)))
        return (
            f'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\{script_name}" '
            f'--cwd "{windows_cwd}"'
        )
    return (
        f'python "$CODEX_HOME/skills/aippocampus/scripts/{script_name}" '
        f"--cwd {quote_posix_double(cwd)}"
    )


def render_health_text(result: dict[str, Any]) -> None:
    status = "OK" if result["ok"] else "needs maintenance"
    rollout = result["rollout"]
    index = result["index"]
    clean_source = result["clean_source"]
    segments = result["segments"]
    checkpoint = result["checkpoint"]
    graphify = result["graphify"]
    storage = result.get("storage") or {}
    question_stats = result.get("question_stats") or {}
    actions = result["recommended_actions"]

    print(f"thread memory health: {status}")
    if storage:
        print(
            "registry: "
            f"{storage.get('active_registry')} "
            f"({storage.get('active_registry_source')})"
        )
    print(
        f"rollout: {rollout['path']} ({rollout['size']} bytes, {rollout['message_count']} messages)"
    )
    if index["stale"]:
        print("index: stale")
    elif index["message_delta"] or index["byte_delta"]:
        print(
            f"index: fresh window ({index['message_delta']} unindexed messages, {index['byte_delta']} new bytes below threshold)"
        )
    else:
        print("index: fresh")
    if index["rag"]:
        print(f"rag cache: {index['rag'].get('chunk_count', 0)} chunks")
    print(f"clean source: {'stale' if clean_source['stale'] else 'fresh'}")
    if segments["exists"]:
        print(
            f"segments: {'stale' if segments['stale'] else 'fresh'} ({segments['segment_count']} shards)"
        )
    elif segments["needed"]:
        print("segments: missing")
    else:
        print("segments: not needed yet")
    print(f"checkpoint: {'due' if checkpoint['due'] else 'not due'}")
    print(f"graphify corpus: {'stale' if graphify['stale'] else 'fresh'}")
    if question_stats.get("available"):
        print(
            "question health: "
            f"{question_stats.get('question_group_count', 0)} groups, "
            f"{question_stats.get('recurring_link_count', 0)} recurring links, "
            f"{question_stats.get('dormant_question_count', 0)} dormant, "
            f"{question_stats.get('resolved_question_count', 0)} resolved"
        )
    if actions:
        print("\nrecommended actions:")
        for item in actions:
            print(f"- {item['id']} [{item['severity']}]: {item['reason']}")


def load_question_stats(
    *,
    jobs_path: Path | None,
    registry_path: Path | None,
    dormant_after_days: int = DEFAULT_DORMANT_AFTER_DAYS,
    resolve_registry_refs: bool = True,
    include_details: bool = False,
) -> dict[str, Any]:
    if jobs_path is None:
        return {"available": False, "reason": "jobs_unresolved"}
    try:
        payload = question_health_stats(
            jobs_path,
            registry_path=registry_path if resolve_registry_refs else None,
            dormant_after_days=dormant_after_days,
        )
        return payload if include_details else aggregate_question_health_stats(payload)
    except Exception as exc:
        # Health checks are operator diagnostics. Question lifecycle reporting is
        # allowed to disappear when local staging artifacts are stale or corrupt;
        # it must not block core index/clean-source maintenance advice.
        return {
            "available": False,
            "reason": "question_health_error",
            "error_type": type(exc).__name__,
            "message": str(exc)[:240],
            "jobs": str(jobs_path),
            "registry": str(registry_path) if registry_path else None,
        }


def default_question_jobs_path(registry_path: Path) -> Path:
    return registry_path.resolve().parent / DEFAULT_JOBS_OUTPUT_NAME


def health_report(cwd: str | Path | None = None, **overrides: Any) -> dict[str, Any]:
    """Return the runtime health payload without shelling out to the CLI.

    CLI, MCP, recall, and registry code all need the same operator health
    contract. Keeping that contract as a package API prevents frozen binaries
    and embedded hosts from accidentally re-entering the facade through
    `sys.executable script.py`.
    """
    return build_health_report(HealthOptions(cwd=Path.cwd() if cwd is None else cwd, **overrides))


def build_health_report(options: HealthOptions) -> dict[str, Any]:
    cwd = Path(options.cwd).resolve()
    rollout = locate_rollout(cwd, codex_home())
    index_dir = resolve_artifact_path(options.index_dir, cwd, default_thread_index_dir(cwd, rollout))
    anchors = Path(options.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    graphify_corpus = resolve_artifact_path(
        options.graphify_corpus, cwd, default_thread_graphify_corpus_dir(cwd, rollout)
    )
    segments_dir = resolve_artifact_path(
        options.segments_dir, cwd, default_thread_segments_dir(cwd, rollout)
    )
    checkpoint_state = resolve_artifact_path(
        options.checkpoint_state, cwd, default_thread_checkpoint_state_path(cwd, rollout)
    )
    clean_source_dir = resolve_artifact_path(
        options.clean_source_dir, cwd, default_thread_clean_source_dir(cwd, rollout)
    )
    registry_path = (
        Path(options.registry).resolve()
        if options.registry
        else registry_paths(Path(options.registry_dir).resolve() if options.registry_dir else None)[0]
    )
    registry_resolution = aippocampus_registry_resolution()
    jobs_path = (
        Path(options.jobs_output).resolve()
        if options.jobs_output
        else default_question_jobs_path(registry_path)
    )
    rollout_stat = rollout.stat()
    current_message_count, last_line = count_messages(rollout)
    current_anchor_count = len(parse_anchor_file(anchors))
    current_anchor_sha = file_sha256(anchors) if anchors.exists() else None

    manifest_path = index_dir / "manifest.json"
    messages_path = index_dir / "messages.jsonl"
    stable_sqlite_path = index_dir / "source_index.sqlite"
    sqlite_path = resolve_sqlite_index_path(stable_sqlite_path)
    manifest = load_json(manifest_path)

    index_reasons: list[str] = []
    if not manifest:
        index_reasons.append("index manifest is missing")
    if not messages_path.exists():
        index_reasons.append("messages.jsonl is missing")
    if not sqlite_path.exists():
        index_reasons.append("source_index.sqlite is missing")
    indexed_messages = int(manifest.get("message_count") or 0)
    indexed_bytes = int(manifest.get("source_rollout_size") or 0)
    indexed_last_line = manifest.get("last_message_line")
    message_delta = max(0, current_message_count - indexed_messages)
    byte_delta = max(0, rollout_stat.st_size - indexed_bytes)
    if manifest and message_delta >= options.max_stale_messages:
        index_reasons.append(f"{message_delta} new messages since last index")
    if manifest and byte_delta >= options.max_stale_bytes:
        index_reasons.append(f"{byte_delta} new rollout bytes since last index")
    if manifest and current_anchor_sha and manifest.get("anchor_sha256") != current_anchor_sha:
        index_reasons.append("thread-anchors.md changed since last index")
    rag_manifest = manifest.get("rag") or {}
    if manifest and not rag_manifest.get("enabled"):
        index_reasons.append("rag-lite chunk cache is missing from index manifest")

    index_stale = bool(index_reasons)

    clean_manifest_path = clean_source_dir / "manifest.json"
    clean_messages_path = clean_source_dir / "messages.jsonl"
    clean_turns_path = clean_source_dir / "turns.jsonl"
    clean_manifest = load_json(clean_manifest_path)
    clean_reasons: list[str] = []
    if not clean_manifest:
        clean_reasons.append("clean-source manifest is missing")
    if not clean_messages_path.exists():
        clean_reasons.append("clean-source messages.jsonl is missing")
    if not clean_turns_path.exists():
        clean_reasons.append("clean-source turns.jsonl is missing")
    try:
        clean_schema = int(clean_manifest.get("schema_version") or 0)
    except (TypeError, ValueError):
        clean_schema = 0
    if clean_manifest and clean_schema < 2:
        clean_reasons.append("clean-source schema is older than v2 upgrade contract")
    if clean_manifest and clean_schema >= 2 and not clean_manifest.get("upgrade_contract"):
        clean_reasons.append("clean-source upgrade contract is missing")
    clean_indexed_bytes = int(clean_manifest.get("source_rollout_size") or 0)
    clean_byte_delta = max(0, rollout_stat.st_size - clean_indexed_bytes)
    if clean_manifest and clean_byte_delta >= options.max_stale_bytes:
        clean_reasons.append(f"{clean_byte_delta} new rollout bytes since clean-source build")
    clean_source_stale = bool(clean_reasons)

    corpus_manifest_path = graphify_corpus / "corpus_manifest.json"
    corpus_manifest = load_json(corpus_manifest_path)
    current_manifest_sha = file_sha256(manifest_path) if manifest_path.exists() else None
    graphify_reasons: list[str] = []
    if not graphify_corpus.exists():
        graphify_reasons.append("graphify corpus is missing")
    elif not corpus_manifest:
        graphify_reasons.append("graphify corpus_manifest.json is missing")
    elif (
        current_manifest_sha
        and corpus_manifest.get("source_index_manifest_sha256") != current_manifest_sha
    ):
        graphify_reasons.append("graphify corpus was prepared from an older index manifest")
    if index_stale:
        graphify_reasons.append("index is stale, so prepared corpus may be stale too")
    graphify_stale = bool(graphify_reasons)

    segments_manifest_path = segments_dir / "manifest.json"
    segments_manifest = load_json(segments_manifest_path)
    segments_reasons: list[str] = []
    segments_needed = rollout_stat.st_size >= options.segment_threshold_bytes
    segments_message_delta = 0
    segments_byte_delta = 0
    if segments_needed and not segments_manifest:
        segments_reasons.append("segment manifest is missing for a large rollout")
    if segments_manifest:
        segment_rollout_size = int(segments_manifest.get("source_rollout_size") or 0)
        segment_message_count = int(segments_manifest.get("message_count") or 0)
        segments_byte_delta = max(0, rollout_stat.st_size - segment_rollout_size)
        segments_message_delta = max(0, current_message_count - segment_message_count)
        # Rollout files grow during any live interaction, including the health
        # check itself. Do not mark shards stale for one fresh message or a tiny
        # tool output; use the same stale thresholds as the main index so hooks
        # do not rebuild segments on every turn.
        if segments_message_delta >= options.max_stale_messages:
            segments_reasons.append(
                f"{segments_message_delta} new messages since segmented index build"
            )
        if segments_byte_delta >= options.max_stale_bytes:
            segments_reasons.append(
                f"{segments_byte_delta} new rollout bytes since segmented index build"
            )
        if current_anchor_sha and segments_manifest.get("anchor_sha256") != current_anchor_sha:
            segments_reasons.append("thread-anchors.md changed since segmented index build")
        missing_segment_indexes = [
            item.get("id") or "unknown"
            for item in segments_manifest.get("segments") or []
            if not Path(str(item.get("sqlite") or "")).exists()
        ]
        if missing_segment_indexes:
            segments_reasons.append(
                "segment sqlite file(s) missing: " + ", ".join(missing_segment_indexes[:6])
            )
    segments_stale = bool(segments_reasons)

    checkpoint = load_json(checkpoint_state)
    captured_count = int(checkpoint.get("last_captured_message_count") or 0)
    checked_count = int(checkpoint.get("last_checked_message_count") or 0)
    checkpoint_delta = current_message_count - captured_count
    checkpoint_due = captured_count == 0 or checkpoint_delta >= options.checkpoint_messages

    deep_graph_recommended = (
        current_message_count >= options.deep_graph_messages
        or rollout_stat.st_size >= options.deep_graph_bytes
    )

    actions = []
    if index_stale:
        severity = "critical" if not manifest else "warning"
        actions.append(
            action(
                "build_index",
                severity,
                "; ".join(index_reasons),
                recommended_script_command("build_index.py", cwd),
            )
        )
    if clean_source_stale:
        actions.append(
            action(
                "build_clean_source",
                "warning" if clean_manifest else "critical",
                "; ".join(clean_reasons),
                recommended_script_command("build_clean_source.py", cwd),
            )
        )
    if checkpoint_due:
        actions.append(
            action(
                "checkpoint",
                "suggestion",
                f"{checkpoint_delta} messages since the last captured checkpoint",
                recommended_script_command("checkpoint.py", cwd),
            )
        )
    if graphify_stale:
        actions.append(
            action(
                "prepare_graphify_corpus",
                "info",
                "; ".join(graphify_reasons),
                recommended_script_command("prepare_graphify_corpus.py", cwd),
            )
        )
    if segments_stale:
        severity = "warning" if segments_manifest else "info"
        actions.append(
            action(
                "build_segments",
                severity,
                "; ".join(segments_reasons),
                recommended_script_command("build_segments.py", cwd),
            )
        )
    if deep_graph_recommended:
        actions.append(
            action(
                "consider_graphify",
                "info",
                "thread size crossed the deep graph threshold",
                f'Use $graphify on "{graphify_corpus}" when conceptual navigation is worth the cost.',
            )
        )
    question_stats = (
        {"available": False, "reason": "not_requested"}
        if not options.include_question_stats
        else load_question_stats(
            jobs_path=jobs_path,
            registry_path=registry_path,
            dormant_after_days=options.question_dormant_days,
            resolve_registry_refs=True,
            include_details=options.question_stats_details,
        )
    )

    result: dict[str, Any] = {
        "ok": not any(a["severity"] in {"critical", "warning"} for a in actions),
        "cwd": str(cwd),
        "rollout": {
            "path": str(rollout),
            "size": rollout_stat.st_size,
            "message_count": current_message_count,
            "last_message_line": last_line,
        },
        "anchors": {
            "path": str(anchors),
            "exists": anchors.exists(),
            "count": current_anchor_count,
            "sha256": current_anchor_sha,
        },
        "storage": {
            "default_registry_dir": registry_resolution["path"],
            "default_registry_source": registry_resolution["source"],
            "legacy_fallback": registry_resolution["legacy_fallback"],
            "active_registry": str(registry_path),
            "active_registry_source": (
                "--registry"
                if options.registry
                else "--registry-dir"
                if options.registry_dir
                else registry_resolution["source"]
            ),
        },
        "index": {
            "dir": str(index_dir),
            "manifest": str(manifest_path),
            "sqlite": str(sqlite_path),
            "stable_sqlite": str(stable_sqlite_path),
            "exists": bool(manifest),
            "stale": index_stale,
            "reasons": index_reasons,
            "indexed_message_count": indexed_messages,
            "indexed_last_message_line": indexed_last_line,
            "current_last_message_line": last_line,
            "message_delta": message_delta,
            "byte_delta": byte_delta,
            "rag": rag_manifest,
        },
        "clean_source": {
            "dir": str(clean_source_dir),
            "manifest": str(clean_manifest_path),
            "exists": bool(clean_manifest),
            "stale": clean_source_stale,
            "reasons": clean_reasons,
            "message_count": int(clean_manifest.get("message_count") or 0) if clean_manifest else 0,
            "turn_count": int(clean_manifest.get("turn_count") or 0) if clean_manifest else 0,
            "byte_delta": clean_byte_delta,
        },
        "checkpoint": {
            "state": str(checkpoint_state),
            "due": checkpoint_due,
            "last_checked_message_count": checked_count,
            "last_captured_message_count": captured_count,
            "message_delta": checkpoint_delta,
        },
        "graphify": {
            "corpus": str(graphify_corpus),
            "exists": graphify_corpus.exists(),
            "stale": graphify_stale,
            "reasons": graphify_reasons,
            "deep_graph_recommended": deep_graph_recommended,
        },
        "segments": {
            "dir": str(segments_dir),
            "manifest": str(segments_manifest_path),
            "needed": segments_needed,
            "exists": bool(segments_manifest),
            "stale": segments_stale,
            "reasons": segments_reasons,
            "segment_count": int(segments_manifest.get("segment_count") or 0)
            if segments_manifest
            else 0,
            "message_delta": segments_message_delta,
            "byte_delta": segments_byte_delta,
        },
        "question_stats": question_stats,
        "recommended_actions": actions,
    }

    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--index-dir",
        default=None,
        help="Defaults to the AIppocampus registry thread store.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument(
        "--graphify-corpus",
        default=None,
        help="Defaults to the global thread store's graphify-corpus.",
    )
    parser.add_argument(
        "--segments-dir",
        default=None,
        help="Defaults to the global thread store's segments directory.",
    )
    parser.add_argument(
        "--checkpoint-state",
        default=None,
        help="Defaults to the global thread store's checkpoint state.",
    )
    parser.add_argument(
        "--clean-source-dir",
        default=None,
        help="Defaults to the global thread store's clean-source directory.",
    )
    parser.add_argument("--registry", default=None)
    parser.add_argument("--registry-dir", default=None)
    parser.add_argument(
        "--jobs-output",
        default=None,
        help="Defaults to the registry-local subconscious_jobs.jsonl.",
    )
    parser.add_argument(
        "--question-stats",
        action="store_true",
        help="Include derived aggregate question lifecycle/reporting stats.",
    )
    parser.add_argument(
        "--question-stats-resolve-refs",
        action="store_true",
        help="Compatibility flag; question stats resolve refs against registry clean source by default.",
    )
    parser.add_argument(
        "--question-stats-details",
        action="store_true",
        help="Include source-derived question lifecycle details in JSON; local diagnostics only.",
    )
    parser.add_argument(
        "--question-dormant-days",
        type=int,
        default=DEFAULT_DORMANT_AFTER_DAYS,
        help="Days without a source-backed reappearance before a question is reported dormant.",
    )
    parser.add_argument("--max-stale-messages", type=int, default=25)
    parser.add_argument("--max-stale-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--checkpoint-messages", type=int, default=30)
    parser.add_argument("--deep-graph-messages", type=int, default=1000)
    parser.add_argument("--deep-graph-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--segment-threshold-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--exit-code", action="store_true", help="Exit 2 when maintenance is recommended."
    )
    return parser


def options_from_args(args: argparse.Namespace) -> HealthOptions:
    return HealthOptions(
        cwd=args.cwd,
        index_dir=args.index_dir,
        anchors=args.anchors,
        graphify_corpus=args.graphify_corpus,
        segments_dir=args.segments_dir,
        checkpoint_state=args.checkpoint_state,
        clean_source_dir=args.clean_source_dir,
        registry=args.registry,
        registry_dir=args.registry_dir,
        jobs_output=args.jobs_output,
        include_question_stats=args.question_stats,
        question_stats_details=args.question_stats_details,
        question_dormant_days=args.question_dormant_days,
        max_stale_messages=args.max_stale_messages,
        max_stale_bytes=args.max_stale_bytes,
        checkpoint_messages=args.checkpoint_messages,
        deep_graph_messages=args.deep_graph_messages,
        deep_graph_bytes=args.deep_graph_bytes,
        segment_threshold_bytes=args.segment_threshold_bytes,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = build_health_report(options_from_args(args))
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_health_text(result)

    if args.exit_code and result["recommended_actions"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
