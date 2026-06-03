"""Shared helpers for registry registration entrypoints."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from aippocampus_runtime.core import canonical_path, compact_text, workspace_identity_key
from aippocampus_runtime.registry.store import safe_slug

SCRIPT_DIR = Path(__file__).resolve().parents[2]


def _stable_identity_digest(value: str) -> str:
    # These registry ids are deterministic join keys, not secrecy boundaries.
    # Use SHA-256 anyway so changed identity flows do not reintroduce weak-hash
    # security alerts, and keep the suffix long enough for practical uniqueness.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


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
        # Registry project keys are long-lived join ids. Use the central
        # workspace identity helper so symlink spelling, macOS /var aliases, and
        # Windows path-case variants do not split one project into multiple
        # registry identities. Keep the human label spelling separate from the
        # identity digest; explicit labels remain operator-chosen display text.
        canonical_cwd = canonical_path(cwd)
        digest = _stable_identity_digest(workspace_identity_key(cwd))
        return f"project:{safe_slug(label or canonical_cwd.name or 'workspace')}:{digest}"
    # Same compatibility boundary as the cwd-backed branch above.
    digest = _stable_identity_digest((label or "unknown").casefold())
    return f"project:{safe_slug(label or 'unknown')}:{digest}"


def project_fields(
    cwd: Path | None, *, project: str | None = None, tags: list[str] | None = None
) -> dict:
    label = project or (canonical_path(cwd).name if cwd else "unknown")
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
