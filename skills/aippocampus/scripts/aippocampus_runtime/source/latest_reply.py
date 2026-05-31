#!/usr/bin/env python3
"""Return the latest assistant final answer from a Codex rollout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aippocampus_runtime import core


def latest_reply(rollout: Path) -> dict:
    messages, turns = core.normalize_rollout(rollout)
    assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
    final_messages = [
        msg
        for msg in assistant_messages
        if msg.get("phase") == "final_answer" or msg.get("is_final")
    ]
    if final_messages:
        msg = final_messages[-1]
        status = "final_answer"
        warning = None
    elif assistant_messages:
        msg = assistant_messages[-1]
        status = "only_commentary_found"
        warning = "[⚠️] only_commentary_found"
    else:
        msg = None
        status = "no_assistant_reply_found"
        warning = "[⚠️] no_assistant_reply_found"

    turn = None
    if msg and msg.get("turn_index") is not None:
        turn = next((item for item in turns if item.get("id") == msg.get("turn_index")), None)

    return {
        "status": status,
        "warning": warning,
        "rollout": str(rollout),
        "message": msg,
        "turn": turn,
        "message_count": len(messages),
        "turn_count": len(turns),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    rollout = Path(args.rollout) if args.rollout else core.locate_rollout(cwd, core.codex_home())
    result = latest_reply(rollout)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        message = result.get("message")
        print(f"status: {result['status']}")
        if result.get("warning"):
            print(result["warning"])
        print(f"rollout: {result['rollout']}")
        if not message:
            return 1
        print(
            f"line {message['line']} | {message.get('timestamp')} | "
            f"turn={message.get('turn_index')} | phase={message.get('phase') or '(none)'}"
        )
        print(message.get("text") or "")
    return 0 if result.get("message") else 1


if __name__ == "__main__":
    raise SystemExit(main())
