#!/usr/bin/env python3
"""Shared filesystem, environment, and Markdown helpers for vault sync."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[2]


def env_value(name: str, legacy_name: str | None = None) -> str | None:
    return os.environ.get(name) or (os.environ.get(legacy_name) if legacy_name else None)


def optional_env_path(name: str, legacy_name: str | None = None) -> Path | None:
    value = env_value(name, legacy_name)
    return Path(value) if value else None


DEFAULT_VAULT = Path(env_value("AIPPOCAMPUS_VAULT") or (Path.home() / "AIppocampus Memory"))
DEFAULT_STYLE_SOURCE = optional_env_path("AIPPOCAMPUS_STYLE_SOURCE")
DEFAULT_SCRIPT_SOURCE = optional_env_path("AIPPOCAMPUS_SCRIPT_SOURCE")
DEFAULT_SITE_MARK = optional_env_path("AIPPOCAMPUS_SITE_MARK")
DEFAULT_SITE_MARK_SOURCE = (
    SCRIPT_DIR / "aippocampus_runtime" / "vault" / "dashboard_assets" / "aippocampus-site-mark.png"
)
DEFAULT_SITE_TITLE = env_value("AIPPOCAMPUS_SITE_TITLE") or "AIppocampus"
DEFAULT_D3_SOURCE = SCRIPT_DIR.parent / "assets" / "d3-7.9.0.min.js"
DEFAULT_PIXI_SOURCE = SCRIPT_DIR.parent / "assets" / "pixi-7.2.4.min.js"


def resolve_under(base: Path, *parts: str) -> Path:
    base = base.resolve()
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"refusing to write outside vault: {target}")
    return target


def safe_filename(name: str, fallback: str = "untitled") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip()
    name = re.sub(r"\s+", " ", name)
    name = name.rstrip(". ")
    return name[:120] or fallback


def wikilink(path: Path, vault: Path, label: str | None = None) -> str:
    rel = path.resolve().relative_to(vault.resolve())
    stem = str(rel.with_suffix("")).replace("\\", "/")
    if label:
        return f"[[{stem}|{label}]]"
    return f"[[{stem}]]"


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return proc.stdout


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def format_frontmatter(data: dict) -> str:
    data = dict(data)
    if "cssclasses" not in data and "codex-memory" in data.get("tags", []):
        data["cssclasses"] = ["codex-memory"]
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def read_recent_messages(path: Path, limit: int = 8) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            item.setdefault("id", idx)
            rows.append(item)
    return rows[-limit:]


def copy_dashboard_assets(vault: Path) -> dict[str, str]:
    assets_dir = resolve_under(vault, "_dashboards", "assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    if DEFAULT_STYLE_SOURCE and DEFAULT_STYLE_SOURCE.exists():
        target = assets_dir / "publish-reference.css"
        shutil.copy2(DEFAULT_STYLE_SOURCE, target)
        copied["publish_css"] = "assets/publish-reference.css"
    if DEFAULT_SCRIPT_SOURCE and DEFAULT_SCRIPT_SOURCE.exists():
        target = assets_dir / "publish-reference.js"
        shutil.copy2(DEFAULT_SCRIPT_SOURCE, target)
        copied["publish_js"] = "assets/publish-reference.js"
    if DEFAULT_D3_SOURCE.exists():
        target = assets_dir / "d3-7.9.0.min.js"
        shutil.copy2(DEFAULT_D3_SOURCE, target)
        copied["d3_js"] = "assets/d3-7.9.0.min.js"
    if DEFAULT_PIXI_SOURCE.exists():
        target = assets_dir / "pixi-7.2.4.min.js"
        shutil.copy2(DEFAULT_PIXI_SOURCE, target)
        copied["pixi_js"] = "assets/pixi-7.2.4.min.js"
    site_mark_source = (
        DEFAULT_SITE_MARK
        if DEFAULT_SITE_MARK and DEFAULT_SITE_MARK.exists()
        else DEFAULT_SITE_MARK_SOURCE
    )
    if site_mark_source.exists():
        suffix = site_mark_source.suffix.lower() or ".png"
        target = assets_dir / f"site-mark{suffix}"
        shutil.copy2(site_mark_source, target)
        copied["site_mark"] = f"assets/{target.name}"
    return copied
