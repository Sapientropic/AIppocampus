#!/usr/bin/env python3
"""Materialize semantic scope-label sidecars from subconscious job findings.

The model-facing job may make fuzzy judgments, but this script is deliberately
boring: it only accepts source-backed `semantic_scope_labels` staging rows that
target existing clean-source message ids, then writes the sidecar consumed by
search and timelines.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aippocampuslib import cli_error_payload, cli_exit_code_for_error_code
from build_project_timeline import resolve_registry_member_path
from registry import load_registry, registry_paths
from semantic_scope_labels import (
    SEMANTIC_SCOPE_LABELS_FILENAME,
    clean_messages_by_id,
    iter_jsonl,
    semantic_scope_label_rows_from_findings,
    write_semantic_scope_label_sidecar,
)


def entry_matches_project(entry: dict[str, Any], project: str | None) -> bool:
    if not project:
        return True
    needle = project.casefold().strip()
    blob = " ".join(
        [
            str(entry.get("project_label") or ""),
            str(entry.get("workspace_name") or ""),
            str(entry.get("title") or ""),
            " ".join(str(item) for item in entry.get("project_tags") or []),
        ]
    ).casefold()
    return needle in blob


def build_semantic_scope_labels(
    *,
    jobs_output_path: Path,
    clean_source_dir: Path,
    min_confidence: float = 0.45,
    no_write: bool = False,
) -> dict[str, Any]:
    messages_by_id = clean_messages_by_id(clean_source_dir)
    findings = iter_jsonl(jobs_output_path)
    rows = semantic_scope_label_rows_from_findings(
        findings,
        messages_by_id,
        min_confidence=min_confidence,
    )
    output_path = clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME
    if not no_write:
        output_path = write_semantic_scope_label_sidecar(clean_source_dir, rows)
    return {
        "ok": True,
        "jobs_output": str(jobs_output_path),
        "clean_source_dir": str(clean_source_dir),
        "output": str(output_path),
        "message_count": len(messages_by_id),
        "finding_count": len(findings),
        "row_count": len(rows),
        "wrote": not no_write,
        "boundary": "Semantic scope labels are navigation hints; clean source remains the source of truth.",
    }


def clean_source_dirs_from_registry(
    registry_path: Path, *, project: str | None = None
) -> list[Path]:
    registry = load_registry(registry_path)
    dirs: list[Path] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict) or not entry_matches_project(entry, project):
            continue
        messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
        messages_path = (
            resolve_registry_member_path(str(messages_path_value), registry_path)
            if messages_path_value
            else None
        )
        if messages_path and messages_path.exists():
            dirs.append(messages_path.parent)
    return list(dict.fromkeys(dirs))


def build_semantic_scope_labels_for_registry(
    *,
    registry_path: Path,
    jobs_output_path: Path,
    project: str | None = None,
    min_confidence: float = 0.45,
    no_write: bool = False,
) -> dict[str, Any]:
    targets = []
    for clean_source_dir in clean_source_dirs_from_registry(registry_path, project=project):
        targets.append(
            build_semantic_scope_labels(
                jobs_output_path=jobs_output_path,
                clean_source_dir=clean_source_dir,
                min_confidence=min_confidence,
                no_write=no_write,
            )
        )
    return {
        "ok": True,
        "registry": str(registry_path),
        "jobs_output": str(jobs_output_path),
        "project": project,
        "target_count": len(targets),
        "row_count": sum(int(target.get("row_count") or 0) for target in targets),
        "wrote": not no_write,
        "targets": targets,
        "boundary": "Semantic scope labels are navigation hints; clean source remains the source of truth.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-output")
    parser.add_argument("--clean-source-dir")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--project")
    parser.add_argument("--min-confidence", type=float, default=0.45)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        registry_path = None
        if args.registry or args.registry_dir or not args.clean_source_dir:
            registry_path = (
                Path(args.registry).resolve()
                if args.registry
                else registry_paths(
                    Path(args.registry_dir).resolve() if args.registry_dir else None
                )[0]
            )
        jobs_output_path = (
            Path(args.jobs_output).resolve()
            if args.jobs_output
            else (registry_path.parent / "subconscious_jobs.jsonl" if registry_path else None)
        )
        if jobs_output_path is None:
            raise ValueError(
                "--jobs-output is required when --clean-source-dir is used without --registry/--registry-dir"
            )
        if args.clean_source_dir:
            result = build_semantic_scope_labels(
                jobs_output_path=jobs_output_path,
                clean_source_dir=Path(args.clean_source_dir).resolve(),
                min_confidence=args.min_confidence,
                no_write=args.no_write,
            )
        elif registry_path:
            result = build_semantic_scope_labels_for_registry(
                registry_path=registry_path,
                jobs_output_path=jobs_output_path,
                project=args.project,
                min_confidence=args.min_confidence,
                no_write=args.no_write,
            )
        else:
            raise ValueError("pass --clean-source-dir or --registry/--registry-dir")
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"semantic scope-label rows: {result['row_count']}")
        if "output" in result:
            print(f"output: {result['output']}")
        else:
            print(f"targets: {result.get('target_count', 0)}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
