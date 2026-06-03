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
    lines = [
        "# AIppocampus Bundle",
        "",
        "Use `$aippocampus` in a Codex thread to import or search this bundle.",
        "",
        f"- Created: {manifest.get('created_at')}",
        f"- Source cwd: {manifest.get('cwd')}",
        f"- Message count: {manifest.get('message_count')}",
        f"- Anchor count: {manifest.get('anchor_count')}",
        f"- Graph nodes: {manifest.get('graph', {}).get('node_count')}",
        f"- Raw rollout included: {'yes' if include_raw else 'no'}",
        "",
        "Suggested recovery commands:",
        "",
        "```powershell",
        'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\import_bundle.py" "<this zip>"',
        'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\search_rollout.py" "keyword" --index "<extracted>\\index\\source_index.sqlite"',
        "```",
        "",
        "`search_rollout.py` resolves the version pointer when the bundle carries",
        "`index/source_index.pointer.json` and `index/versions/source_index-*.sqlite`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def export_bundle(args: argparse.Namespace) -> dict[str, Any]:
    cwd = Path(args.cwd).resolve()
    redaction_profile = str(getattr(args, "redaction_profile", "raw-private") or "raw-private")
    if redaction_profile == "public-export" and not args.no_raw:
        raise ValueError("public-export redaction profile requires --no-raw")
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
    manifest = run_build_index(
        cwd,
        rollout,
        index_dir,
        anchors,
        args.hash_source,
        redaction_profile=redaction_profile,
    )
    artifact_manifest = (
        privacy.redact_private_paths(manifest) if redaction_profile == "public-export" else manifest
    )
    if redaction_profile == "public-export":
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

    if anchors.exists():
        shutil.copy2(anchors, bundle_root / "thread-anchors.md")
    if not args.no_raw:
        shutil.copy2(rollout, bundle_root / "rollout.jsonl")

    write_handoff(bundle_root / "handoff.md", artifact_manifest, include_raw=not args.no_raw)

    bundle_manifest = dict(artifact_manifest)
    bundle_manifest["bundle_schema_version"] = 1
    bundle_manifest["raw_rollout_included"] = not args.no_raw
    bundle_manifest["redaction_profile"] = redaction_profile
    bundle_manifest["bundle_files"] = {
        "handoff": "handoff.md",
        "anchors": "thread-anchors.md" if anchors.exists() else None,
        "raw_rollout": "rollout.jsonl" if not args.no_raw else None,
        "index_dir": "index",
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
        if redaction_profile == "public-export"
        else str(rollout),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--output")
    parser.add_argument(
        "--work-dir", default=None, help="Defaults to the global thread store's index directory."
    )
    parser.add_argument("--no-raw", action="store_true", help="Do not include raw rollout JSONL.")
    parser.add_argument("--hash-source", action="store_true")
    parser.add_argument(
        "--redaction-profile",
        default="raw-private",
        choices=["raw-private", "redacted-local", "public-export"],
        help="Project bundle index text; public-export also requires --no-raw.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    print(json.dumps(export_bundle(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
