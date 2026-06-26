from __future__ import annotations

import argparse
import json
import sys
from typing import cast

import test_plan as planner
from test_plan_projection import compact_changed_surface_plan, compact_release_preflight_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan focused AIppocampus verification from changed files.")
    parser.add_argument("--base", default="origin/main", help="Base ref for committed changes.")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Provide an explicit changed file. Repeat for tests or scripted callers.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the plan as JSON.")
    parser.add_argument(
        "--detail",
        choices=("compact", "full"),
        default="compact",
        help="Compact is action-shaped; full preserves the complete planner payload.",
    )
    parser.add_argument(
        "--local-executable",
        action="store_true",
        help="Use the exact local Python executable in emitted commands instead of portable python.",
    )
    parser.add_argument(
        "--release-preflight",
        action="store_true",
        help="Emit the lean local gate for a CI-green release before tagging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.release_preflight:
        plan = planner.build_release_preflight_plan(local_executable=args.local_executable)
        if args.json:
            payload = (
                plan
                if args.detail == "full"
                else compact_release_preflight_plan(
                    plan,
                    base=args.base,
                    local_executable=args.local_executable,
                )
            )
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            print()
            return 0

        print("AIppocampus release preflight plan")
        print(plan["assumption"])
        print("Local required:")
        local_required = cast(list[dict[str, str]], plan["local_required"])
        post_publish_required = cast(list[dict[str, str]], plan["post_publish_required"])
        for command in local_required:
            print(f"- {command['command']}")
            print(f"  {command['reason']}")
        print("Post-publish required:")
        for command in post_publish_required:
            print(f"- {command['command']}")
            print(f"  {command['reason']}")
        return 0

    changed_files = (
        sorted({planner._repo_relative(path) for path in args.changed_file})
        if args.changed_file
        else planner.collect_changed_files(base=args.base)
    )
    plan = planner.build_test_plan(changed_files, local_executable=args.local_executable)
    if args.json:
        payload = (
            plan
            if args.detail == "full"
            else compact_changed_surface_plan(
                plan,
                changed_files=changed_files,
                base=args.base,
                local_executable=args.local_executable,
            )
        )
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print("AIppocampus changed-surface verification plan")
    environment = cast(dict[str, object], plan["python_environment"])
    print(
        "Python: "
        f"local {str(environment['local_python_version'])} / "
        f"CI {str(environment['canonical_ci_python_version'])}"
    )
    warnings = cast(list[dict[str, str]], plan["warnings"])
    commands = cast(list[dict[str, str]], plan["commands"])
    for warning in warnings:
        print(f"Warning: {warning['message']}")
        print(f"Next: {warning['next_action']}")
    print(f"Changed files: {len(changed_files)}")
    for command in commands:
        print(f"- {command['command']}")
        print(f"  {command['reason']}")
    return 0
