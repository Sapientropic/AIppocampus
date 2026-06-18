from __future__ import annotations

import json
import sys
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action

MIN_RUNTIME_PYTHON = (3, 12)


def _version_parts(version_info: Any) -> tuple[int, int, int]:
    try:
        return int(version_info.major), int(version_info.minor), int(version_info.micro)
    except AttributeError:
        values = list(version_info)
        return (
            int(values[0]) if len(values) > 0 else 0,
            int(values[1]) if len(values) > 1 else 0,
            int(values[2]) if len(values) > 2 else 0,
        )


def _version_label(version_info: Any) -> str:
    return ".".join(str(part) for part in _version_parts(version_info))


def python_runtime_floor_payload(version_info: Any | None = None) -> dict[str, Any] | None:
    current = sys.version_info if version_info is None else version_info
    if _version_parts(current)[:2] >= MIN_RUNTIME_PYTHON:
        return None
    required = ".".join(str(part) for part in MIN_RUNTIME_PYTHON)
    return {
        "kind": "aippocampus_runtime_preflight",
        "ok": False,
        "status": "blocked",
        "blocking_issue": {
            "id": "python_runtime_too_old",
            "message": f"Python {required} or newer is required before running AIppocampus.",
            "current_python": _version_label(current),
            "required_python": f">={required}",
            "fix_command": f"py -{required} --version",
            "manual_instruction": f"Install Python {required}+ and rerun AIppocampus with that interpreter.",
        },
        "foreground_action": foreground_shell_action(
            action_id="check_python_runtime",
            label="Check Python runtime",
            command=f"py -{required} --version",
            why="AIppocampus runtime entrypoints require Python 3.12+.",
            mutation_risk="read_only",
            claim_boundary="runtime_preflight_not_memory_evidence",
        ),
        "safe_next_actions": [
            foreground_shell_action(
                action_id="check_python_runtime",
                label="Check Python runtime",
                command=f"py -{required} --version",
                why="Confirm a supported Python interpreter is installed.",
                mutation_risk="read_only",
                claim_boundary="runtime_preflight_not_memory_evidence",
            )
        ],
        "policy_boundary": {
            "runtime_check_precedes_command_dispatch": True,
            "host_setup_not_memory_evidence": True,
        },
    }


def emit_python_runtime_floor(payload: dict[str, Any], args: list[str]) -> None:
    if "--json" in args:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    issue = payload["blocking_issue"]
    print("AIppocampus runtime blocked", file=sys.stderr)
    print(f"why: {issue['message']}", file=sys.stderr)
    print(f"current: Python {issue['current_python']}", file=sys.stderr)
    print(f"next: {issue['fix_command']}", file=sys.stderr)
