"""Import a portable AIppocampus bundle into the current workspace."""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import (
    index_pointer_path,
    resolve_sqlite_index_path,
)
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def append_import_anchor(
    anchor_path: Path, bundle: Path, extract_dir: Path, manifest: dict[str, Any]
) -> None:
    created = not anchor_path.exists()
    lines = []
    if created:
        lines.extend(
            [
                "# Thread Anchors",
                "",
                "Concise index for recovering important context from this long Codex thread.",
                "",
            ]
        )
    lines.extend(
        [
            "## Imported AIppocampus bundle",
            f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "- Keywords: imported bundle,aippocampus,portable memory",
            f"- Note: Imported bundle from {bundle}.",
            f"- Note: Extracted files are under {extract_dir}.",
            f"- Note: Source cwd was {manifest.get('cwd', 'unknown')}; message count {manifest.get('message_count', 'unknown')}.",
            f"- Source: {extract_dir / 'index' / 'source_index.sqlite'}",
            "",
        ]
    )
    with anchor_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def safe_extract(zip_file: zipfile.ZipFile, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    for info in zip_file.infolist():
        name = info.filename.replace("\\", "/")
        member_path = Path(name)
        # Bundles may come from another machine, so reject paths that could
        # escape the chosen import directory before handing them to zipfile.
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"unsafe zip member path: {info.filename}")
        target = (root / member_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe zip member path: {info.filename}")
    zip_file.extractall(root)


def import_bundle(args: argparse.Namespace) -> dict[str, Any]:
    bundle = Path(args.bundle).resolve()
    if not bundle.is_file():
        raise FileNotFoundError(f"bundle not found: {bundle}")
    dest = Path(args.dest).resolve()
    name = args.name or f"aippocampus-import-{timestamp_slug()}"
    extract_dir = dest / name
    extract_dir.mkdir(parents=True, exist_ok=False)

    with zipfile.ZipFile(bundle, "r") as zf:
        safe_extract(zf, extract_dir)

    manifest_path = extract_dir / "bundle_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not args.no_anchor:
        append_import_anchor(dest / "thread-anchors.md", bundle, extract_dir, manifest)

    sqlite_index = extract_dir / "index" / "source_index.sqlite"
    sqlite_current = resolve_sqlite_index_path(sqlite_index)
    sqlite_pointer = index_pointer_path(sqlite_index)

    return {
        "ok": True,
        "kind": "aippocampus_bundle_import",
        "extracted_to": str(extract_dir),
        "manifest": str(manifest_path) if manifest_path.exists() else None,
        "sqlite_index": str(sqlite_index),
        "sqlite_current": str(sqlite_current) if sqlite_current.is_file() else None,
        "sqlite_pointer": str(sqlite_pointer) if sqlite_pointer.is_file() else None,
        "messages_jsonl": str(extract_dir / "index" / "messages.jsonl"),
        "graph_json": str(extract_dir / "index" / "graph.json"),
        "anchor_written": not bool(args.no_anchor),
        "anchor_path": str(dest / "thread-anchors.md") if not bool(args.no_anchor) else None,
        "message_count": manifest.get("message_count"),
        "raw_rollout_included": manifest.get("raw_rollout_included"),
        "redaction_profile": manifest.get("redaction_profile"),
    }


def _public_import_projection(payload: dict[str, Any], *, include_private_paths: bool) -> dict[str, Any]:
    anchor_written = bool(payload.get("anchor_written"))
    diagnostics = {
        "extracted_to": payload.get("extracted_to"),
        "manifest": payload.get("manifest"),
        "sqlite_current": payload.get("sqlite_current"),
        "sqlite_pointer": payload.get("sqlite_pointer"),
        "messages_jsonl": payload.get("messages_jsonl"),
        "graph_json": payload.get("graph_json"),
        "anchor_path": payload.get("anchor_path"),
    }
    if not include_private_paths:
        diagnostics = redact_private_paths(diagnostics)
    return redact_sensitive_values(
        {
            "ok": bool(payload.get("ok", True)),
            "kind": "aippocampus_bundle_import_summary",
            "summary": {
                "imported": bool(payload.get("ok", True)),
                "message_count": payload.get("message_count"),
                "anchor_written": anchor_written,
                "redaction_profile": payload.get("redaction_profile"),
                "raw_rollout_included": bool(payload.get("raw_rollout_included")),
                "next_command": 'aippocampus search "keyword" --clean-source-dir <imported-index-folder> --json',
                "no_anchor_command": "aippocampus import <bundle.zip> --dest <folder> --no-anchor",
            },
            "diagnostics": diagnostics,
            "privacy_boundary": {
                "local_paths_included": include_private_paths,
                "path_redaction": "none" if include_private_paths else LOCAL_PATH_REDACTION,
                "operator_private_details_flag": "--include-private-paths",
            },
        }
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus import",
        usage="aippocampus import <bundle.zip> [--dest <folder>] [--name <label>] [--no-anchor]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Import a portable AIppocampus bundle into a local folder.\n\n"
            "Default output is a compact action card with local paths redacted. "
            "Use --include-private-paths only for local operator diagnostics.\n\n"
            "Anchor behavior:\n"
            "  default      append a short local thread-anchors.md pointer under --dest\n"
            "  --no-anchor  extract only; do not write the anchor note"
        ),
    )
    parser.add_argument("bundle", help="Portable bundle zip to import.")
    parser.add_argument(
        "--dest",
        default=os.getcwd(),
        help="Local folder that receives the extracted bundle and optional thread-anchors.md.",
    )
    parser.add_argument("--name", help="Folder name under --dest. Defaults to timestamped import.")
    parser.add_argument("--no-anchor", action="store_true", help="Do not append thread-anchors.md.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON; accepted for facade consistency.")
    parser.add_argument(
        "--include-private-paths",
        action="store_true",
        help="Operator diagnostic opt-in: include local extracted paths in JSON output.",
    )
    return parser


def _transcript_intent_payload(format_guess: str) -> dict[str, Any]:
    canonical_format = "generic-jsonl"
    return {
        "ok": False,
        "kind": "aippocampus_import_recovery",
        "error": {
            "code": "transcript_import_intent_detected",
            "message": (
                f"`{format_guess}` looks like a transcript format, not a portable bundle zip. "
                "No write happened."
            ),
            "next_command": (
                "aippocampus import conversation --format "
                f"{canonical_format} --input <path> --dry-run --json"
            ),
        },
        "safety": {
            "no_write_happened": True,
            "bundle_import_not_attempted": True,
        },
        "privacy_boundary": {
            "local_paths_included": False,
            "path_redaction": LOCAL_PATH_REDACTION,
            "operator_input": "private transcript path supplied explicitly with --input <path>",
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    format_guess = str(args.bundle).strip().casefold()
    if format_guess in {"generic-jsonl", "jsonl"}:
        print(json.dumps(_transcript_intent_payload(format_guess), ensure_ascii=False, indent=2))
        return 2
    try:
        payload = import_bundle(args)
    except FileNotFoundError as exc:
        message = str(redact_private_paths(str(exc)))
        payload = {
            "ok": False,
            "kind": "aippocampus_bundle_import_summary",
            "error": {
                "code": "bundle_not_found",
                "message": message,
                "bundle_label": Path(str(args.bundle)).name,
                "next_command": "aippocampus import <existing-bundle.zip> --dest <folder>",
            },
            "privacy_boundary": {
                "local_paths_included": False,
                "path_redaction": LOCAL_PATH_REDACTION,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(
        json.dumps(
            _public_import_projection(
                payload,
                include_private_paths=bool(args.include_private_paths),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
