"""Import a portable AIppocampus bundle into the current workspace."""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.artifacts.publish import (
    index_pointer_path,
    resolve_sqlite_index_path,
)
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)

BUNDLE_INTEGRITY_NAME = "bundle_integrity.json"
IMPORT_ORIGIN_BOUNDARY = (
    "Checksum verification only proves the imported bundle bytes match its "
    "manifest. Without a verified signature or local source reopen, imported "
    "rows must stay below source-supported authority."
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


def verify_bundle_integrity(extract_dir: Path) -> dict[str, Any]:
    integrity_path = extract_dir / BUNDLE_INTEGRITY_NAME
    if not integrity_path.exists():
        return {
            "status": "missing_integrity_manifest",
            "checksum_verified": False,
            "verified_origin": False,
            "boundary": "legacy or unsigned bundle; imported bytes are not promoted to source authority",
        }
    try:
        manifest = json.loads(integrity_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("bundle_integrity_invalid_json") from exc
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("bundle_integrity_missing_files")
    root = extract_dir.resolve()
    checked = 0
    expected_paths: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("bundle_integrity_invalid_file_entry")
        rel = str(entry.get("path") or "").replace("\\", "/")
        member = Path(rel)
        if not rel or member.is_absolute() or ".." in member.parts:
            raise ValueError("bundle_integrity_unsafe_path")
        target = (root / member).resolve()
        if target != root and root not in target.parents:
            raise ValueError("bundle_integrity_unsafe_path")
        if not target.is_file():
            raise ValueError(f"bundle_integrity_missing_file:{rel}")
        expected_size = entry.get("size")
        if isinstance(expected_size, int) and target.stat().st_size != expected_size:
            raise ValueError(f"bundle_integrity_size_mismatch:{rel}")
        expected_sha = str(entry.get("sha256") or "")
        if expected_sha and core.file_sha256(target) != expected_sha:
            raise ValueError(f"bundle_integrity_hash_mismatch:{rel}")
        expected_paths.add(rel)
        checked += 1
    actual_paths = {
        path.resolve().relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != BUNDLE_INTEGRITY_NAME
    }
    unlisted = sorted(actual_paths - expected_paths)
    if unlisted:
        raise ValueError(f"bundle_integrity_unlisted_file:{unlisted[0]}")
    if manifest.get("file_count") not in {None, checked}:
        raise ValueError("bundle_integrity_file_count_mismatch")
    origin = manifest.get("origin") if isinstance(manifest.get("origin"), dict) else {}
    signature_verified = bool(origin.get("signature_verified"))
    manifest_claimed_verified_origin = bool(origin.get("verified_origin"))
    return {
        "status": "checksum_verified",
        "checksum_verified": True,
        "verified_origin": bool(manifest_claimed_verified_origin and signature_verified),
        "manifest_claimed_verified_origin": manifest_claimed_verified_origin,
        "signature_verified": signature_verified,
        "file_count": checked,
        "boundary": IMPORT_ORIGIN_BOUNDARY,
    }


def _import_origin_for_rows(integrity: Mapping[str, Any]) -> dict[str, Any]:
    verified_origin = bool(integrity.get("verified_origin") and integrity.get("signature_verified"))
    return {
        "verified_origin": verified_origin,
        "origin_verified": verified_origin,
        "user_authorized_import": True,
        "checksum_verified": bool(integrity.get("checksum_verified")),
        "signature_verified": bool(integrity.get("signature_verified")),
        "origin_kind": "portable_bundle_import",
        "usable_for": ["search", "recall_route", "source_reopen"],
        "source_authority": "requires_source_reopen_or_verified_signature",
        "boundary": IMPORT_ORIGIN_BOUNDARY,
    }


CLAIM_PROMOTING_ROW_KINDS = {
    "aippocampus_learning_finding",
    "source_backed_lesson_candidate",
    "aippocampus_learning_action_guidance",
    "aippocampus_workflow_candidate",
    "aippocampus_learning_guidance_outcome",
    "aippocampus_learning_effectiveness_ledger_row",
}
CLAIM_PROMOTING_FILENAMES = {
    "findings.jsonl",
    "effectiveness-ledger.jsonl",
}


def _claim_promoting_import_row(path: Path, row: Mapping[str, Any]) -> bool:
    kind = str(row.get("kind") or "")
    if kind in CLAIM_PROMOTING_ROW_KINDS:
        return True
    if path.name in CLAIM_PROMOTING_FILENAMES and {"learning-loop", "learning"} & set(path.parts):
        return True
    return False


def _stamp_imported_claim_rows(extract_dir: Path, integrity: Mapping[str, Any]) -> dict[str, Any]:
    origin = _import_origin_for_rows(integrity)
    touched_files = 0
    stamped_rows = 0
    skipped_source_rows = 0
    malformed_rows = 0
    for path in sorted(extract_dir.rglob("*.jsonl")):
        try:
            original_text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        output_lines: list[str] = []
        changed = False
        for line in original_text.splitlines():
            if not line.strip():
                output_lines.append(line)
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                malformed_rows += 1
                output_lines.append(line)
                continue
            if not isinstance(payload, dict):
                output_lines.append(line)
                continue
            if not _claim_promoting_import_row(path, payload):
                skipped_source_rows += 1
                output_lines.append(line)
                continue
            row = dict(payload)
            # Do not preserve a row-level "verified" claim from an unsigned
            # imported claim-promoting artifact. User-authorized import makes
            # the bundle usable for recall/search, but source-supported AIppo
            # promotion still needs a verified origin or a reopened source.
            row["verified_origin"] = bool(origin["verified_origin"])
            row["origin_verified"] = bool(origin["origin_verified"])
            row["import_origin"] = dict(origin)
            output_lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
            changed = True
            stamped_rows += 1
        if changed:
            path.write_text("\n".join(output_lines) + ("\n" if original_text.endswith("\n") else ""), encoding="utf-8")
            touched_files += 1
    return {
        "jsonl_files_stamped": touched_files,
        "jsonl_rows_stamped": stamped_rows,
        "jsonl_source_rows_left_reopenable": skipped_source_rows,
        "malformed_jsonl_rows_preserved": malformed_rows,
        "verified_origin": bool(origin["verified_origin"]),
        "user_authorized_import": True,
        "checksum_verified_before_local_stamp": bool(integrity.get("checksum_verified")),
        "boundary": IMPORT_ORIGIN_BOUNDARY,
    }


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
    integrity = verify_bundle_integrity(extract_dir)
    row_provenance = _stamp_imported_claim_rows(extract_dir, integrity)
    integrity["import_row_provenance"] = row_provenance

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
        "integrity": integrity,
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
                "integrity": payload.get("integrity"),
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


def _bundle_import_preview(args: argparse.Namespace) -> dict[str, Any]:
    bundle = Path(args.bundle).resolve()
    if not bundle.is_file():
        raise FileNotFoundError(f"bundle not found: {bundle}")
    manifest: dict[str, Any] = {}
    member_count = 0
    with zipfile.ZipFile(bundle, "r") as zf:
        names = zf.namelist()
        member_count = len(names)
        if "bundle_manifest.json" in names:
            manifest = json.loads(zf.read("bundle_manifest.json").decode("utf-8"))
    primary = {
        "id": "write_bundle_import_after_preview",
        "label": "Write bundle import after preview",
        "command_template": (
            "aippocampus import {bundle_zip} --dest {destination_folder} "
            "--name {import_name} --json"
        ),
        "requires": ["bundle_zip", "destination_folder", "import_name"],
        "template_only": True,
        "mutation_risk": "explicit_local_import_write",
        "claim_boundary": "operator_transfer_not_memory_claim",
        "why": "Dry-run only inspected the bundle manifest; rerun explicitly to extract files and optionally append an anchor.",
    }
    return redact_sensitive_values(
        redact_private_paths(
            {
                "ok": True,
                "kind": "aippocampus_bundle_import_preview",
                "mode": "dry_run",
                "bundle_label": bundle.name,
                "route_value": "bundle_import_preview_before_local_write",
                "current_uncertainty": "preview_did_not_extract_files_or_register_sources",
                **canonical_foreground_action_fields(primary, safe_next_actions=[primary]),
                "write_preview": {
                    "would_extract_bundle": True,
                    "would_append_anchor": not bool(args.no_anchor),
                    "would_create_destination_folder": True,
                    "member_count": member_count,
                    "message_count": manifest.get("message_count"),
                    "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
                    "redaction_profile": manifest.get("redaction_profile"),
                },
                "privacy_boundary": {
                    "local_paths_included": False,
                    "writes_performed": False,
                    "bundle_contents_extracted": False,
                    "anchor_written": False,
                },
            }
        )
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
    parser.add_argument("--dry-run", action="store_true", help="Preview extract and anchor writes without mutating local files.")
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
                f"{canonical_format} --input {{input_path}} --dry-run --json"
            ),
        },
        "safety": {
            "no_write_happened": True,
            "bundle_import_not_attempted": True,
        },
        "privacy_boundary": {
            "local_paths_included": False,
            "path_redaction": LOCAL_PATH_REDACTION,
            "operator_input": "private transcript path supplied explicitly with --input",
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    format_guess = str(args.bundle).strip().casefold()
    if format_guess in {"generic-jsonl", "jsonl"}:
        print(json.dumps(_transcript_intent_payload(format_guess), ensure_ascii=False, indent=2))
        return 2
    if args.dry_run:
        try:
            payload = _bundle_import_preview(args)
        except FileNotFoundError as exc:
            message = str(redact_private_paths(str(exc)))
            payload = {
                "ok": False,
                "kind": "aippocampus_bundle_import_preview",
                "mode": "dry_run",
                "error": {
                    "code": "bundle_not_found",
                    "message": message,
                    "bundle_label": Path(str(args.bundle)).name,
                },
                "privacy_boundary": {
                    "local_paths_included": False,
                    "path_redaction": LOCAL_PATH_REDACTION,
                    "writes_performed": False,
                },
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
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
    except ValueError as exc:
        payload = {
            "ok": False,
            "kind": "aippocampus_bundle_import_summary",
            "error": {
                "code": "bundle_integrity_failed",
                "message": str(redact_private_paths(str(exc))),
                "bundle_label": Path(str(args.bundle)).name,
            },
            "integrity": {
                "status": "failed",
                "verified_origin": False,
                "checksum_verified": False,
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
