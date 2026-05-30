from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = [
    "skills/aippocampus/scripts",
    "tools/aippocampus",
    "plugins/aippocampus",
]


def run(command: list[str]) -> int:
    proc = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return int(proc.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an AIppocampus test tier with coverage.py reporting."
    )
    parser.add_argument(
        "--tier",
        choices=("fast", "slow", "benchmark", "full"),
        default="fast",
        help="Test tier to run under coverage. Default is the deterministic fast tier.",
    )
    parser.add_argument(
        "--xml",
        default="coverage.xml",
        help="Write a coverage XML report to this path. Pass an empty value to skip XML.",
    )
    parser.add_argument(
        "--html",
        default=None,
        help="Optional directory for an HTML coverage report.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Optional report threshold. Omit until the project has reviewed a real baseline.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if importlib.util.find_spec("coverage") is None:
        print(
            "coverage.py is required; install it with: python -m pip install coverage",
            file=sys.stderr,
        )
        return 2

    source_arg = ",".join(SOURCE_PATHS)
    erase = run([sys.executable, "-m", "coverage", "erase"])
    if erase != 0:
        return erase

    test_result = run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--source={source_arg}",
            "tools/aippocampus/run_tests.py",
            "--tier",
            args.tier,
        ]
    )
    if test_result != 0:
        return test_result

    report_cmd = [sys.executable, "-m", "coverage", "report", "-m"]
    if args.fail_under is not None:
        report_cmd.append(f"--fail-under={args.fail_under:g}")
    report_result = run(report_cmd)
    if report_result != 0:
        return report_result

    if args.xml:
        xml_result = run([sys.executable, "-m", "coverage", "xml", "-o", args.xml])
        if xml_result != 0:
            return xml_result

    if args.html:
        html_result = run([sys.executable, "-m", "coverage", "html", "-d", args.html])
        if html_result != 0:
            return html_result

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
