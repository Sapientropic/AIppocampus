"""Shared helpers for registry registration entrypoints."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.registry.store import safe_slug

SCRIPT_DIR = Path(__file__).resolve().parents[2]


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def unique_preserve(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", str(item)).strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def project_key_for(cwd: Path | None, label: str | None = None) -> str:
    if cwd:
        # Registry project keys are long-lived join ids, not credential hashes.
        # Keep the legacy suffix stable until a dual-read alias migration exists.
        digest = hashlib.sha1(str(cwd).casefold().encode("utf-8")).hexdigest()[:12]
        return f"project:{safe_slug(label or cwd.name or 'workspace')}:{digest}"
    # Same compatibility boundary as the cwd-backed branch above.
    digest = hashlib.sha1((label or "unknown").casefold().encode("utf-8")).hexdigest()[:12]
    return f"project:{safe_slug(label or 'unknown')}:{digest}"


def project_fields(
    cwd: Path | None, *, project: str | None = None, tags: list[str] | None = None
) -> dict:
    label = project or (cwd.name if cwd else "unknown")
    project_tags = unique_preserve([label, *(tags or [])], limit=24)
    return {
        "project_key": project_key_for(cwd, label),
        "project_label": label,
        "project_tags": project_tags,
    }


def anchor_summary(anchors: list[dict]) -> tuple[list[str], list[str], str]:
    titles = unique_preserve([anchor.get("title") or "" for anchor in anchors], limit=20)
    keywords: list[str] = []
    notes: list[str] = []
    for anchor in anchors:
        keywords.extend(anchor.get("keywords") or [])
        notes.extend(anchor.get("notes") or [])
    summary = compact_text(" ".join(notes[:6]), 700) if notes else ""
    return titles, unique_preserve(keywords, limit=32), summary
