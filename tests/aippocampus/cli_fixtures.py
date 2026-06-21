from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"


def run_aippocampus_cli(
    *args: str,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
        cwd=SCRIPTS,
        env=env,
        input=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def registry_env(root: Path, **extra: str) -> dict[str, str]:
    return {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry"), **extra}


def write_continuity_domain_registry(
    root: Path,
    *,
    thread_count: int,
    message_text: str,
    title: str = "provider orchestration continuity route",
) -> Path:
    registry_dir = root / "registry"
    registry_dir.mkdir()
    threads = []
    for index in range(thread_count):
        clean = root / f"clean-source-{index}"
        clean.mkdir()
        rows = [
            {
                "message_id": f"msg-{index}-{line}",
                "turn_id": f"turn-{index}-{line}",
                "turn_index": line,
                "source_line": line,
                "phase": "final_answer",
                "text": message_text,
            }
            for line in (1, 2)
        ]
        (clean / "messages.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        threads.append(
            {
                "thread_key": f"session:{index}",
                "title": title,
                "summary": title,
                "project_label": "AIppocampus",
                "paths": {"clean_source_dir": str(clean)},
            }
        )
    (registry_dir / "threads.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2026-06-16T00:00:00Z",
                "threads": threads,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return registry_dir
