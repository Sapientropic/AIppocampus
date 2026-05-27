from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / "skills" / "aippocampus"
SKILL_SCRIPTS = SKILL_ROOT / "scripts"


def ensure_paths() -> None:
    value = str(SKILL_SCRIPTS)
    if value not in sys.path:
        sys.path.insert(0, value)
