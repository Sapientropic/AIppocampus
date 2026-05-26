#!/usr/bin/env python3
"""Import a portable AIppocampus bundle into the current workspace."""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def append_import_anchor(anchor_path: Path, bundle: Path, extract_dir: Path, manifest: dict) -> None:
    created = not anchor_path.exists()
    lines = []
    if created:
        lines.extend([
            "# Thread Anchors",
            "",
            "Concise index for recovering important context from this long Codex thread.",
            "",
        ])
    lines.extend([
        "## Imported AIppocampus bundle",
        f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "- Keywords: imported bundle,aippocampus,portable memory",
        f"- Note: Imported bundle from {bundle}.",
        f"- Note: Extracted files are under {extract_dir}.",
        f"- Note: Source cwd was {manifest.get('cwd', 'unknown')}; message count {manifest.get('message_count', 'unknown')}.",
        f"- Source: {extract_dir / 'index' / 'source_index.sqlite'}",
        "",
    ])
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    parser.add_argument("--dest", default=os.getcwd())
    parser.add_argument("--name")
    parser.add_argument("--no-anchor", action="store_true")
    args = parser.parse_args()

    bundle = Path(args.bundle).resolve()
    dest = Path(args.dest).resolve()
    name = args.name or f"aippocampus-import-{timestamp_slug()}"
    extract_dir = dest / name
    extract_dir.mkdir(parents=True, exist_ok=False)

    with zipfile.ZipFile(bundle, "r") as zf:
        safe_extract(zf, extract_dir)

    manifest_path = extract_dir / "bundle_manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not args.no_anchor:
        append_import_anchor(dest / "thread-anchors.md", bundle, extract_dir, manifest)

    print(json.dumps({
        "extracted_to": str(extract_dir),
        "manifest": str(manifest_path) if manifest_path.exists() else None,
        "sqlite_index": str(extract_dir / "index" / "source_index.sqlite"),
        "messages_jsonl": str(extract_dir / "index" / "messages.jsonl"),
        "graph_json": str(extract_dir / "index" / "graph.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
