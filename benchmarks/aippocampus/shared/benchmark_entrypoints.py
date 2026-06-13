"""Small CLI contracts for benchmark helper modules.

Benchmark submodules often live beside public runners because aggregate
benchmarks import them directly. If one of those helpers is executed by a
second user, it should explain the supported runner instead of failing with an
import traceback or succeeding with empty output.
"""

from __future__ import annotations

import argparse
import json
from typing import Sequence


def library_only_payload(
    *,
    module_path: str,
    supported_runner: str,
    summary: str,
) -> dict[str, object]:
    return {
        "kind": "aippocampus_benchmark_helper_entrypoint_contract",
        "ok": True,
        "status": "library_only",
        "module": module_path,
        "supported_runner": supported_runner,
        "summary": summary,
    }


def library_only_main(
    *,
    module_path: str,
    supported_runner: str,
    summary: str,
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog=module_path,
        description=(
            f"{module_path} is library-only. {summary} "
            f"Run {supported_runner} for the supported public benchmark surface."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print a machine-readable library-only contract.",
    )
    args = parser.parse_args(argv)
    payload = library_only_payload(
        module_path=module_path,
        supported_runner=supported_runner,
        summary=summary,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"{module_path} is library-only; run {supported_runner} "
            "for the supported public benchmark surface."
        )
    return 0
