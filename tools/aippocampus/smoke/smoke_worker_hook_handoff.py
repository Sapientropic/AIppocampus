#!/usr/bin/env python3
"""Deterministic public-safe smoke for worker/prewarm foreground handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from repo_paths import ensure_repo_imports

ensure_repo_imports(Path(__file__))

from aippocampus_runtime.ops import worker_hook_handoff  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic worker-to-hook handoff smoke."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = worker_hook_handoff.build_worker_hook_handoff_smoke()
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(worker_hook_handoff.render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
