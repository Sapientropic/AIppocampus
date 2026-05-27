from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "skills" / "aippocampus"
SKILL_SCRIPTS = SKILL_ROOT / "scripts"
SMOKE_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "smoke"


def ensure_paths() -> None:
    for path in (SKILL_SCRIPTS, SMOKE_TOOLS):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
