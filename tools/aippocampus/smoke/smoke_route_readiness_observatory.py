#!/usr/bin/env python3
"""No-write smoke for the route-readiness Cognitive Observatory readout."""

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

from aippocampus_runtime.ops import cognitive_observatory  # noqa: E402
from aippocampus_runtime.public_output import emit_public_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic route-readiness observatory smoke."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = cognitive_observatory.fixture_cognitive_observatory_readout()
    if args.json_output:
        emit_public_text(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        emit_public_text(cognitive_observatory.render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
