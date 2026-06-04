#!/usr/bin/env python3
"""No-write smoke for opt-in repo familiarity foreground experiment evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from repo_paths import ensure_repo_imports

PATHS = ensure_repo_imports(Path(__file__))

from aippocampus_runtime.ops import (  # noqa: E402
    repo_familiarity_foreground_experiment,
    repo_familiarity_foreground_experiment_fixtures,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic no-write repo familiarity foreground experiment smoke."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = repo_familiarity_foreground_experiment_fixtures.current_checkout_foreground_experiment(
        repo_root=PATHS.repo_root
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(repo_familiarity_foreground_experiment.render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
