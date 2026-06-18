from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)

SCHEMA_VERSION = 1
MIN_PYTHON_VERSION = (3, 12)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_status(command: str) -> dict[str, Any]:
    return {"id": command, "available": shutil.which(command) is not None, "path_emitted": False}


def _registry_writable_status(registry_dir: str | Path | None = None) -> dict[str, Any]:
    target = Path(registry_dir).expanduser() if registry_dir else core.aippocampus_registry_dir()
    probe_dir = target if target.exists() else next((p for p in target.parents if p.exists()), target.parent)
    writable = False
    error_code = ""
    try:
        if probe_dir.exists() and probe_dir.is_dir():
            with tempfile.NamedTemporaryFile(prefix=".aippocampus-preflight-", dir=probe_dir, delete=True):
                writable = True
        else:
            error_code = "registry_parent_missing"
    except OSError:
        error_code = "registry_not_writable"
    return {
        "id": "registry_dir",
        "writable": writable,
        "target_exists": target.exists(),
        "target_label": "AIPPOCAMPUS_REGISTRY_DIR",
        "local_path_emitted": False,
        "error_code": error_code or None,
    }


def _preflight_blocker(checks: dict[str, Any]) -> dict[str, Any] | None:
    if not _as_dict(checks.get("python")).get("ok"):
        return {
            "id": "python_version",
            "message": "Python 3.12 or newer is required before running AIppocampus.",
            "fix_command": "py -3.12 --version",
            "manual_instruction": "Install Python 3.12+ and rerun the same command with that interpreter.",
        }
    if not _as_dict(checks.get("console_script")).get("available"):
        return {
            "id": "aippocampus_console_script",
            "message": "The aippocampus console script is not resolvable from this host process.",
            "fix_command": "python -m pip install -e .",
            "fallback_command": "python -m aippocampus_runtime.cli.facade doctor preflight --json",
        }
    if not _as_dict(checks.get("registry_dir")).get("writable"):
        return {
            "id": "registry_dir_writable",
            "message": "The AIppocampus registry location is not writable or its parent cannot be probed.",
            "fix_command": "aippocampus doctor preflight --json",
            "manual_instruction": "Choose a writable AIPPOCAMPUS_REGISTRY_DIR or repair permissions, then rerun preflight.",
        }
    age = _as_dict(checks.get("age"))
    age_keygen = _as_dict(checks.get("age_keygen"))
    if not age.get("available") or not age_keygen.get("available"):
        return {
            "id": "age_encryption_tools",
            "message": "Encrypted sync needs both age and age-keygen on PATH.",
            "fix_command": "age --version",
            "manual_instruction": "Install age/age-keygen for your OS, then rerun preflight.",
        }
    if not _as_dict(checks.get("host_cli")).get("available"):
        return {
            "id": "host_cli",
            "message": "Neither codex nor claude CLI is resolvable from this host process.",
            "fix_command": "codex --version",
            "fallback_command": "claude --version",
        }
    return None


def build_preflight_report(*, registry_dir: str | Path | None = None) -> dict[str, Any]:
    codex = _tool_status("codex")
    claude = _tool_status("claude")
    checks: dict[str, Any] = {
        "python": {
            "ok": sys.version_info >= MIN_PYTHON_VERSION,
            "required": ".".join(str(part) for part in MIN_PYTHON_VERSION),
            "current": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "console_script": _tool_status("aippocampus"),
        "age": _tool_status("age"),
        "age_keygen": _tool_status("age-keygen"),
        "host_cli": {"available": bool(codex["available"] or claude["available"]), "codex": codex, "claude": claude},
        "registry_dir": _registry_writable_status(registry_dir),
    }
    blocker = _preflight_blocker(checks)
    primary = (
        foreground_shell_action(
            action_id=str(blocker["id"]),
            command=str(blocker.get("fix_command") or "aippocampus doctor preflight --json"),
            label="Fix first preflight blocker",
            why=str(blocker.get("message") or "Repair the first host prerequisite before setup."),
            mutation_risk="manual_setup",
            claim_boundary="host_setup_not_memory_evidence",
        )
        if blocker
        else foreground_shell_action(
            action_id="continue_with_install_or_recall",
            command="aippocampus update status --json",
            label="Continue with AIppocampus setup/status",
            why="Host prerequisites passed; continue with package/plugin/hook readiness.",
            mutation_risk="read_only",
            claim_boundary="host_setup_not_memory_evidence",
        )
    )
    for key in ("fallback_command", "manual_instruction"):
        if blocker and blocker.get(key):
            primary[key] = str(blocker[key])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_doctor_preflight",
        "ok": blocker is None,
        "status": "ready" if blocker is None else "blocked",
        "blocking_issue": blocker,
        **canonical_foreground_action_fields(primary),
        "checks": checks,
        "privacy": {"local_paths_emitted": False, "secret_values_checked": False, "secret_values_printed": False},
        "claim_boundary": "host preflight proves local prerequisite visibility only, not recall quality or source truth",
    }
