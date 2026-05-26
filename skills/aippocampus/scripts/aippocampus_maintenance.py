#!/usr/bin/env python3
"""Threshold-style maintenance hook for aippocampus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return proc.stdout


def has_action(health: dict, action_id: str) -> bool:
    return any(item.get("id") == action_id for item in health.get("recommended_actions", []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--append-checkpoint", action="store_true", help="Append checkpoint candidates instead of only suggesting them.")
    parser.add_argument("--no-refresh-cognitive-map", action="store_true", help="Do not refresh the cognitive-map sidecar from existing subconscious findings.")
    parser.add_argument("--no-refresh-graphify", action="store_true", help="Do not refresh the prepared Graphify corpus.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    actions: list[dict] = []

    health_cmd = [sys.executable, str(SCRIPT_DIR / "aippocampus_health.py"), "--cwd", str(cwd), "--json"]
    health = run_json(health_cmd)
    actions.append({"id": "health_initial", "result": health})

    if has_action(health, "build_index"):
        out = run_text([sys.executable, str(SCRIPT_DIR / "build_index.py"), "--cwd", str(cwd)])
        actions.append({"id": "build_index", "output": out.strip()})
        health = run_json(health_cmd)

    if has_action(health, "checkpoint"):
        cmd = [sys.executable, str(SCRIPT_DIR / "checkpoint.py"), "--cwd", str(cwd), "--json"]
        if args.append_checkpoint:
            cmd.append("--append")
        checkpoint = run_json(cmd)
        actions.append({"id": "checkpoint", "appended": args.append_checkpoint, "result": checkpoint})
        health = run_json(health_cmd)
        if args.append_checkpoint:
            run_text([sys.executable, str(SCRIPT_DIR / "build_index.py"), "--cwd", str(cwd)])
            health = run_json(health_cmd)

    if has_action(health, "build_segments"):
        # Segments are an acceleration layer over the same normalized transcript
        # as the main index. Build them after the main index/checkpoint pass so
        # shard metadata points at the latest anchors and message count.
        out = run_text([sys.executable, str(SCRIPT_DIR / "build_segments.py"), "--cwd", str(cwd)])
        actions.append({"id": "build_segments", "output": out.strip()})
        health = run_json(health_cmd)

    if not args.no_refresh_cognitive_map:
        # Cognitive-map routes are produced by the detached subconscious layer;
        # maintenance only validates and materializes whatever staging already
        # exists, keeping this foreground pass model-free and hook-safe.
        cognitive_map = run_json([
            sys.executable,
            str(SCRIPT_DIR / "build_cognitive_map.py"),
            "--json",
        ])
        actions.append({"id": "build_cognitive_map", "result": cognitive_map})
        health = run_json(health_cmd)

    if has_action(health, "prepare_graphify_corpus") and not args.no_refresh_graphify:
        graphify = run_json([
            sys.executable,
            str(SCRIPT_DIR / "prepare_graphify_corpus.py"),
            "--cwd",
            str(cwd),
            "--json",
        ])
        actions.append({"id": "prepare_graphify_corpus", "result": graphify})
        health = run_json(health_cmd)

    result = {"cwd": str(cwd), "actions": actions, "health_final": health}
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"memory hook complete for {cwd}")
        for item in actions[1:]:
            print(f"- {item['id']}")
        final_actions = health.get("recommended_actions", [])
        if final_actions:
            print("remaining recommendations:")
            for item in final_actions:
                print(f"- {item['id']} [{item['severity']}]: {item['reason']}")
        else:
            print("no remaining recommendations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
