"""Export a portable bundle for an AIppocampus thread."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from aippocampus_runtime import core, privacy
from aippocampus_runtime.recall import index_builder

PUBLIC_NO_RAW_PROFILES = {"public-export", "public-metadata"}
PUBLIC_METADATA_PROFILES = {"public-export", "public-metadata"}
ALLOWED_REDACTION_PROFILES = ["raw-private", "redacted-local", "public-export", "public-metadata"]
PRIVATE_EXPORT_COMMAND = "aippocampus export --redaction-profile raw-private --output <bundle.zip>"
PUBLIC_EXPORT_COMMAND = (
    "aippocampus export --redaction-profile public-export --no-raw --output <bundle.zip>"
)


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _system_exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def run_build_index(
    cwd: Path,
    rollout: Path,
    index_dir: Path,
    anchors: Path,
    hash_source: bool,
    redaction_profile: str = "raw-private",
) -> dict[str, Any]:
    args = [
        "--cwd",
        str(cwd),
        "--rollout",
        str(rollout),
        "--output-dir",
        str(index_dir),
        "--anchors",
        str(anchors),
        "--json",
        "--redaction-profile",
        redaction_profile,
    ]
    if hash_source:
        args.append("--hash-source")

    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = int(index_builder.main(args) or 0)
        except SystemExit as exc:
            code = _system_exit_code(exc)
    if code != 0:
        raise RuntimeError(stdout.getvalue() or stderr.getvalue())
    return json.loads(stdout.getvalue())


def write_handoff(path: Path, manifest: dict[str, Any], include_raw: bool) -> None:
    public_boundary = manifest.get("public_sharing_boundary")
    public_share_safe = isinstance(public_boundary, dict) and bool(
        public_boundary.get("public_share_safe")
    )
    lines = [
        "# AIppocampus Bundle",
        "",
        "Use `$aippocampus` in a Codex thread to import or inspect this bundle.",
        "",
        f"- Created: {manifest.get('created_at')}",
        f"- Source cwd: {manifest.get('cwd')}",
        f"- Message count: {manifest.get('message_count')}",
        f"- Anchor count: {manifest.get('anchor_count')}",
        f"- Graph nodes: {manifest.get('graph', {}).get('node_count')}",
        f"- Raw rollout included: {'yes' if include_raw else 'no'}",
        "",
    ]
    if public_share_safe:
        lines.extend(
            [
                "This is a public metadata projection. It omits private source text, "
                "session refs, host session metadata, anchors, graph labels, and the "
                "searchable SQLite index.",
                "",
                "Use a private `raw-private` or `redacted-local` bundle when you need "
                "local search or source reopen after import.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Suggested recovery commands:",
                "",
                "```powershell",
                'aippocampus import "<this zip>" --dest "<local folder>"',
                'aippocampus search "keyword" --clean-source-dir "<extracted>\\index" --json',
                "```",
                "",
                "Use the imported `index/messages.jsonl` path as the search clean-source dir.",
                "Private raw/searchable bundles are for local transfer; do not publish them.",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _public_source_hash(*values: Any) -> str:
    raw = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return "source_hash:" + core.stable_text_fingerprint(
        raw,
        namespace="public-export-source-ref",
        length=20,
    )


def _metadata_projection_row(row: dict[str, Any], *, redaction_profile: str) -> dict[str, Any]:
    source_hash = _public_source_hash(
        row.get("source_ref"),
        row.get("source_id"),
        row.get("message_id"),
        row.get("turn_id"),
        row.get("line"),
    )
    projected: dict[str, Any] = {
        "message_id": _public_source_hash("message", row.get("message_id"), source_hash),
        "turn_id": _public_source_hash("turn", row.get("turn_id"), source_hash),
        "line": row.get("line"),
        "timestamp": row.get("timestamp"),
        "role": row.get("role"),
        "kind": row.get("kind"),
        "phase": row.get("phase"),
        "turn_index": row.get("turn_index"),
        "is_final": row.get("is_final"),
        "text": "",
        "source_ref": source_hash,
        "source_ref_hash": source_hash,
        "source_id": source_hash,
        "redaction_profile": redaction_profile,
        "redaction_policy": {
            "source_text_exported": False,
            "source_refs_hashed": True,
            "identifiers_hashed": True,
            "session_metadata_exported": False,
        },
    }
    for key in ("sha1", "content_sha256", "redacted_text_sha256", "scope_labels"):
        if row.get(key) not in (None, "", []):
            projected[key] = row.get(key)
    return {key: value for key, value in projected.items() if value is not None}


def _rewrite_messages_metadata_only(path: Path, *, redaction_profile: str) -> None:
    if not path.exists():
        return
    projected_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                projected_rows.append(
                    _metadata_projection_row(row, redaction_profile=redaction_profile)
                )
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in projected_rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _rewrite_turns_metadata_only(path: Path) -> None:
    if not path.exists():
        return
    projected_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            turn_hash = _public_source_hash("turn", row.get("turn_id"), row.get("turn_index"))
            message_hashes = [
                _public_source_hash("message", item, turn_hash)
                for item in row.get("message_ids") or []
            ]
            projected_rows.append(
                {
                    "turn_id": turn_hash,
                    "turn_index": row.get("turn_index"),
                    "timestamp": row.get("timestamp"),
                    "message_ids": message_hashes,
                    "redaction_policy": {
                        "identifiers_hashed": True,
                        "source_text_exported": False,
                    },
                }
            )
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in projected_rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _remove_search_index_artifacts(index_dir: Path) -> None:
    for pattern in ("*.sqlite", "*.sqlite-*", "source_index.pointer.json"):
        for file in index_dir.rglob(pattern):
            if file.is_file():
                file.unlink()
    generations = index_dir / "generations"
    if generations.exists():
        shutil.rmtree(generations)
    (index_dir / "search_index_omitted.json").write_text(
        json.dumps(
            {
                "kind": "aippocampus_public_metadata_search_index_projection",
                "search_index_included": False,
                "reason": "searchable_indexes_can_embed_private_clean_source_text",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _public_bundle_manifest(manifest: dict[str, Any], *, redaction_profile: str) -> dict[str, Any]:
    projected = privacy.redact_private_paths(manifest)
    if redaction_profile in PUBLIC_METADATA_PROFILES:
        projected.pop("session_meta", None)
        projected["redaction_profile"] = redaction_profile
        projected["source_thread_key"] = "<source-thread-key-omitted>"
        projected["source_rollout"] = privacy.LOCAL_PATH_REDACTION
        projected["source_rollout_sha256"] = None
        graph = dict(projected.get("graph") or {})
        projected["graph"] = {
            "node_count": graph.get("node_count", 0),
            "edge_count": graph.get("edge_count", 0),
            "projection": "count_only",
        }
        public_boundary = {
            "public_share_safe": True,
            "private_clean_source_text_included": False,
            "raw_rollout_included": False,
            "session_metadata_included": False,
            "source_refs_hashed": True,
            "anchors_and_graph_labels_omitted": True,
            "search_index_included": False,
            "legacy_public_export_boundary": (
                "public-export is metadata-only as of 0.3.2; use raw-private "
                "or redacted-local for private searchable transfer bundles."
            )
            if redaction_profile == "public-export"
            else None,
        }
        projected["public_sharing_boundary"] = {
            key: value for key, value in public_boundary.items() if value is not None
        }
    return projected


def _strip_public_metadata_index(
    index_dir: Path,
    manifest: dict[str, Any],
    *,
    redaction_profile: str,
) -> None:
    _rewrite_messages_metadata_only(index_dir / "messages.jsonl", redaction_profile=redaction_profile)
    _rewrite_turns_metadata_only(index_dir / "turns.jsonl")
    _remove_search_index_artifacts(index_dir)
    graph = dict(manifest.get("graph") or {})
    (index_dir / "graph.json").write_text(
        json.dumps(
            {
                "kind": "aippocampus_public_metadata_graph_projection",
                "node_count": graph.get("node_count", 0),
                "edge_count": graph.get("edge_count", 0),
                "nodes": [],
                "edges": [],
                "omitted": "anchor_labels_are_private",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def export_bundle(args: argparse.Namespace) -> dict[str, Any]:
    cwd = Path(args.cwd).resolve()
    redaction_profile = str(getattr(args, "redaction_profile", "raw-private") or "raw-private")
    if redaction_profile in PUBLIC_NO_RAW_PROFILES and not args.no_raw:
        raise ValueError(f"{redaction_profile} redaction profile requires --no-raw")
    rollout = Path(args.rollout) if args.rollout else core.locate_rollout(cwd, core.codex_home())
    anchors = Path(args.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    work_dir = core.resolve_artifact_path(
        args.work_dir, cwd, core.default_thread_index_dir(cwd, rollout)
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    bundle_root = work_dir / "bundle"
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True)

    index_dir = bundle_root / "index"
    index_redaction_profile = (
        "public-metadata" if redaction_profile in PUBLIC_METADATA_PROFILES else redaction_profile
    )
    manifest = run_build_index(
        cwd,
        rollout,
        index_dir,
        anchors,
        args.hash_source,
        redaction_profile=index_redaction_profile,
    )
    artifact_manifest = (
        _public_bundle_manifest(manifest, redaction_profile=redaction_profile)
        if redaction_profile in PUBLIC_NO_RAW_PROFILES
        else manifest
    )
    if redaction_profile in PUBLIC_METADATA_PROFILES:
        _strip_public_metadata_index(
            index_dir,
            manifest,
            redaction_profile=redaction_profile,
        )
    if redaction_profile in PUBLIC_NO_RAW_PROFILES:
        (index_dir / "manifest.json").write_text(
            json.dumps(artifact_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    meta = core.read_session_meta(rollout) or {}
    bundle_name = (
        args.output or f"aippocampus-bundle-{meta.get('id', 'thread')}-{timestamp_slug()}.zip"
    )
    output = Path(bundle_name)
    if not output.is_absolute():
        output = cwd / output

    if anchors.exists() and redaction_profile not in PUBLIC_METADATA_PROFILES:
        shutil.copy2(anchors, bundle_root / "thread-anchors.md")
    if not args.no_raw:
        shutil.copy2(rollout, bundle_root / "rollout.jsonl")

    write_handoff(bundle_root / "handoff.md", artifact_manifest, include_raw=not args.no_raw)

    bundle_manifest = dict(artifact_manifest)
    bundle_manifest["bundle_schema_version"] = 1
    bundle_manifest["raw_rollout_included"] = not args.no_raw
    bundle_manifest["redaction_profile"] = redaction_profile
    bundle_manifest["source_texture_policy"] = (
        {
            "projection": "omitted",
            "reason": "private_interpretation_sidecar",
            "canonical_source_replaced": False,
        }
        if redaction_profile in PUBLIC_NO_RAW_PROFILES
        else {
            "projection": "not_included_in_portable_index_bundle",
            "reason": "clean_source_sidecar_not_index_artifact",
            "canonical_source_replaced": False,
        }
    )
    bundle_manifest["bundle_files"] = {
        "handoff": "handoff.md",
        "anchors": "thread-anchors.md" if anchors.exists() and redaction_profile not in PUBLIC_METADATA_PROFILES else None,
        "raw_rollout": "rollout.jsonl" if not args.no_raw else None,
        "index_dir": "index",
        "search_index": None
        if redaction_profile in PUBLIC_METADATA_PROFILES
        else "index/source_index.sqlite",
    }
    (bundle_root / "bundle_manifest.json").write_text(
        json.dumps(bundle_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in bundle_root.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(bundle_root))

    return {
        "bundle": str(output),
        "size": output.stat().st_size,
        "source_rollout": privacy.LOCAL_PATH_REDACTION
        if redaction_profile in PUBLIC_NO_RAW_PROFILES
        else str(rollout),
        "public_sharing_boundary": bundle_manifest.get("public_sharing_boundary"),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus export",
        usage="aippocampus export [private local transfer | public metadata export] [options]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Portable memory export.\n\n"
            "Choose the human intent first:\n"
            "  Private local transfer:\n"
            "    aippocampus export --redaction-profile raw-private --output <bundle.zip>\n"
            "    Includes local/searchable memory artifacts and may include raw rollout data.\n"
            "    Keep this bundle private and local.\n\n"
            "  Public/shareable metadata:\n"
            "    aippocampus export --redaction-profile public-export --no-raw --output <bundle.zip>\n"
            "    Omits raw rollouts, clean-source text, anchors, graph labels, and searchable indexes.\n\n"
            "Default remains raw-private for local handoff compatibility, but public sharing "
            "requires an explicit public profile plus --no-raw."
        ),
    )
    parser.add_argument(
        "intent",
        nargs="?",
        help=(
            "Optional intent hint. `public` is accepted as a recovery hint and "
            "prints the public metadata command instead of writing."
        ),
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="Workspace whose current thread should be exported.")
    parser.add_argument("--rollout", help="Operator-private raw rollout path override.")
    parser.add_argument(
        "--anchors",
        default="thread-anchors.md",
        help="Optional local anchor file copied only into private/searchable bundles.",
    )
    parser.add_argument("--output", help="Bundle zip path to write.")
    parser.add_argument(
        "--work-dir", default=None, help="Defaults to the global thread store's index directory."
    )
    parser.add_argument("--no-raw", action="store_true", help="Do not include raw rollout JSONL.")
    parser.add_argument(
        "--hash-source",
        action="store_true",
        help="Hash source identifiers in generated index metadata where supported.",
    )
    parser.add_argument(
        "--redaction-profile",
        default="raw-private",
        help=(
            "Project bundle index text. public-export and public-metadata are "
            "metadata-only public-share-safe profiles; use raw-private or redacted-local "
            "for private searchable transfer bundles. Public profiles require --no-raw."
        ),
    )
    parser.add_argument("--public", action="store_true", help="Recovery hint for public metadata export.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Accepted for chooser/error cards.")
    return parser


def _chooser_payload(*, reason: str, public_hint: bool = False) -> dict[str, Any]:
    intent_action = {
        "id": "choose_export_intent",
        "label": "Choose export intent and output path",
        "requires": ["export_intent", "output_path"],
        "mutation_risk": "no_write_until_explicit_output",
        "claim_boundary": "private_raw_export_requires_explicit_private_intent",
        "why": (
            "Bare export is privacy-sensitive; choose public metadata or explicit "
            "private local transfer before writing a bundle."
        ),
    }
    error: dict[str, Any] = {
        "code": "export_intent_required",
        "message": (
            "Choose private local transfer or public/shareable metadata and provide "
            "an explicit --output path. No write happened."
        ),
        "reason": reason,
    }
    if public_hint:
        error["next_command"] = PUBLIC_EXPORT_COMMAND
    return {
        "ok": False,
        "kind": "aippocampus_export_chooser",
        "status": "intent_required",
        "error": error,
        "agent_next_action": intent_action,
        "foreground_action": intent_action,
        "choices": [
            {
                "intent": "private_local_transfer",
                "command_template": PRIVATE_EXPORT_COMMAND,
                "requires": ["output_path"],
                "boundary": "private local handoff only; may include searchable local memory artifacts",
                "mutation_risk": "writes_private_bundle",
                "claim_boundary": "private_local_transfer_only",
            },
            {
                "intent": "public_shareable_metadata",
                "command_template": PUBLIC_EXPORT_COMMAND,
                "requires": ["output_path"],
                "boundary": "metadata-only public export; omits raw rollout and source text",
                "mutation_risk": "writes_public_metadata_bundle",
                "claim_boundary": "public_metadata_no_raw_source_text",
            },
        ],
        "recommended_public_command": PUBLIC_EXPORT_COMMAND,
        "safety": {
            "no_write_happened": True,
            "requires_explicit_output": True,
            "raw_private_is_never_selected_by_bare_command": True,
        },
        "write_performed": False,
    }


def _export_recovery_actions(*, provided: str | None = None) -> list[dict[str, str]]:
    public_profile = "public-metadata" if provided == "public" else "public-metadata"
    return [
        {
            "id": "public_metadata_export",
            "command": f"aippocampus export --redaction-profile {public_profile} --no-raw --output <bundle.zip> --json",
        },
        {
            "id": "public_export",
            "command": "aippocampus export --redaction-profile public-export --no-raw --output <bundle.zip> --json",
        },
        {
            "id": "private_local_transfer",
            "command": PRIVATE_EXPORT_COMMAND + " --json",
        },
    ]


def _invalid_redaction_profile_payload(provided: str) -> dict[str, Any]:
    return {
        "ok": False,
        "kind": "aippocampus_export_recovery",
        "error": {
            "code": "invalid_redaction_profile",
            "message": "The selected redaction profile is not recognized. No write happened.",
            "provided": provided,
            "allowed": ALLOWED_REDACTION_PROFILES,
        },
        "safe_next_actions": _export_recovery_actions(provided=provided),
        "write_performed": False,
        "safety": {
            "no_write_happened": True,
            "no_traceback": True,
            "no_secret_values_printed": True,
        },
    }


def _recovery_payload(*, code: str, message: str, next_command: str) -> dict[str, Any]:
    return {
        "ok": False,
        "kind": "aippocampus_export_recovery",
        "error": {
            "code": code,
            "message": message,
            "next_command": next_command,
        },
        "safe_next_actions": _export_recovery_actions(),
        "write_performed": False,
        "safety": {
            "no_write_happened": True,
            "no_traceback": True,
            "no_secret_values_printed": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if str(args.redaction_profile) not in ALLOWED_REDACTION_PROFILES:
        if args.json_output:
            print(json.dumps(_invalid_redaction_profile_payload(str(args.redaction_profile)), ensure_ascii=False, indent=2))
            return 2
        build_arg_parser().error(
            "argument --redaction-profile: invalid choice: "
            f"{args.redaction_profile!r} (choose from {', '.join(ALLOWED_REDACTION_PROFILES)})"
        )
    intent = str(getattr(args, "intent", "") or "").strip().casefold()
    public_hint = bool(args.public) or intent in {"public", "public-export", "public-metadata"}
    if intent and intent not in {"public", "public-export", "public-metadata", "private", "raw-private"}:
        print(json.dumps(_chooser_payload(reason="unknown_intent", public_hint=False), ensure_ascii=False, indent=2))
        return 2
    # Export touches private local history and temporary bundle staging. A natural
    # bare/guessed command must stop here instead of falling through to the legacy
    # raw-private default or cleanup paths that can hit locked SQLite files.
    if public_hint or not args.output:
        reason = "public_metadata_hint" if public_hint else "missing_output"
        print(json.dumps(_chooser_payload(reason=reason, public_hint=public_hint), ensure_ascii=False, indent=2))
        return 2
    try:
        payload = export_bundle(args)
    except ValueError as exc:
        message = str(exc)
        code = "public_export_requires_no_raw" if "--no-raw" in message else "invalid_export_request"
        payload = _recovery_payload(
            code=code,
            message=message,
            next_command="aippocampus export --no-raw --redaction-profile <profile> --output <bundle.zip>",
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except OSError:
        payload = _recovery_payload(
            code="export_filesystem_recovery",
            message=(
                "Export could not complete because a local bundle/index file was locked or unavailable. "
                "No traceback is shown; rerun after closing the writer or choose a fresh --work-dir."
            ),
            next_command=(
                "aippocampus export --redaction-profile raw-private --output <bundle.zip> "
                "--work-dir <fresh-folder>"
            ),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
