#!/usr/bin/env python3
"""Structured behavior-event extraction for Codex rollout clean source."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.rollout import iter_jsonl

TOOL_EXIT_CODE_RE = re.compile(r"Exit code:\s*(-?\d+)", re.IGNORECASE)
PATH_TOKEN_RE = re.compile(
    r"""(?:"([^"]+)"|'([^']+)'|([A-Za-z]:[^\s'"]+|(?:\.{1,2}[\\/])?[A-Za-z0-9_.@+-]+[\\/][^\s'"]+|[A-Za-z0-9_.@+-]+\.(?:cfg|conf|csv|go|ini|js|json|jsonl|jsx|lock|md|py|rs|toml|ts|tsx|txt|yaml|yml)))""",
    re.IGNORECASE,
)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File:\s+(.+)$", re.MULTILINE)
TEST_TIER_RE = re.compile(r"--tier(?:=|\s+)([A-Za-z0-9_-]+)", re.IGNORECASE)
GENERATED_PATH_MARKERS = {
    ".aippocampus",
    ".pytest_cache",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "generated",
    "node_modules",
    "target",
}
SOURCE_EXTENSIONS = {"go", "js", "jsx", "py", "rs", "ts", "tsx"}
CONFIG_EXTENSIONS = {"cfg", "conf", "ini", "json", "lock", "toml", "yaml", "yml"}
DOC_EXTENSIONS = {"md", "rst", "txt"}
PRIVATE_PATH_MARKERS = {
    ".ssh",
    "appdata",
    "administrator",
    "codexhome",
    "cookies",
    "password",
    "secret",
    "secrets",
    "token",
    "users",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _tool_call_id(payload: dict[str, Any]) -> str:
    return str(payload.get("call_id") or payload.get("id") or payload.get("tool_call_id") or "")


def _tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("name") or payload.get("tool_name") or payload.get("type") or "tool")


def _tool_input(payload: dict[str, Any]) -> Any:
    for key in ("arguments", "args", "input", "parameters"):
        if key in payload:
            return _parse_maybe_json(payload.get(key))
    return {}


def _tool_output_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if output is None:
        output = payload.get("content")
    if isinstance(output, str):
        return output
    if output is None:
        return ""
    return json.dumps(output, ensure_ascii=False, sort_keys=True)


def _input_command(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("command", "cmd", "script"):
            if key in value:
                return str(value.get(key) or "")
    return ""


def _input_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def classify_tool_command(tool_name: str, command: str = "") -> str:
    """Return a coarse, non-sensitive tool command class."""

    material = f"{tool_name}\n{command}".casefold()
    if "apply_patch" in material:
        return "edit"
    if any(
        token in material
        for token in (
            "pytest",
            "unittest",
            "run_tests.py",
            "cargo test",
            " tests\\",
            " tests/",
            "\ntests\\",
            "\ntests/",
        )
    ):
        return "test"
    if any(
        token in material
        for token in (
            "mypy",
            "ruff",
            "check_docs_health.py",
            "npm run lint",
            "cargo check",
            "tsc",
        )
    ):
        return "check"
    if any(token in material for token in (" rg ", "\nrg ", "ripgrep", "select-string", "grep")):
        return "search"
    if any(token in material for token in ("get-content", "read_file", "view_image")):
        return "read"
    if any(token in material for token in (" git ", "\ngit ", "gh issue", "gh pr")):
        return "vcs"
    if any(
        token in material
        for token in ("set-content", "out-file", "add-content", "tee-object", ">>", "\n> ")
    ):
        return "edit"
    if "shell_command" in material or command:
        return "shell"
    if "web_search" in material:
        return "web_search"
    return "tool"


def classify_tool_intent(tool_name: str, command_class: str, command: str = "") -> str:
    """Return a bounded purpose label for a tool call."""

    material = f"{tool_name}\n{command}".casefold()
    if command_class in {"test", "check"}:
        return "test_check"
    if command_class == "search":
        return "search"
    if command_class == "read":
        return "read"
    if command_class == "vcs":
        return "version_control"
    if command_class == "edit":
        return "file_edit"
    if command_class == "web_search" or "web_search" in material:
        return "web_lookup"
    if command_class == "shell":
        return "shell"
    return "tool"


def classify_command_family(tool_name: str, command: str = "") -> str:
    """Return a finer command family without preserving command text."""

    material = f"{tool_name}\n{command}".casefold()
    if "apply_patch" in material:
        return "apply_patch"
    if "run_tests.py" in material:
        return "repo_test_runner"
    if "pytest" in material:
        return "python_pytest"
    if "unittest" in material:
        return "python_unittest"
    if " tests\\" in material or " tests/" in material or "\ntests\\" in material or "\ntests/" in material:
        return "python_unittest"
    if "cargo test" in material:
        return "cargo_test"
    if "npm test" in material or "npm run test" in material:
        return "node_test"
    if "mypy" in material:
        return "python_mypy"
    if "ruff" in material:
        return "python_ruff"
    if "check_docs_health.py" in material:
        return "docs_health"
    if any(token in material for token in (" rg ", "\nrg ", "ripgrep")):
        return "ripgrep"
    if "select-string" in material:
        return "powershell_search"
    if "grep" in material:
        return "grep"
    if "get-content" in material:
        return "powershell_read"
    if "gh " in material or "gh issue" in material or "gh pr" in material:
        return "github_cli"
    if " git " in material or "\ngit " in material:
        return "git"
    if any(token in material for token in ("set-content", "out-file", "add-content", ">>", "\n> ")):
        return "shell_write"
    if "web_search" in material:
        return "web_search"
    if "shell_command" in material or command:
        return "shell"
    return "tool"


def _test_target_from_tier(command: str) -> str | None:
    match = TEST_TIER_RE.search(command)
    if not match:
        return None
    tier = match.group(1).casefold()
    if tier in {"fast", "full", "slow", "benchmark"}:
        return f"repo_{tier}_suite"
    return "repo_test_suite"


def classify_target_class(command_family: str, command: str = "") -> str:
    """Return a coarse target class useful for recall without path leakage."""

    material = command.casefold()
    if command_family == "repo_test_runner":
        return _test_target_from_tier(command) or "repo_test_suite"
    if command_family in {"python_pytest", "python_unittest"}:
        if " tests/" in material or " tests\\" in material or "\ntests/" in material:
            return "focused_test_path"
        return "unit_test"
    if command_family == "python_mypy":
        return "typecheck"
    if command_family == "python_ruff":
        return "lint"
    if command_family == "docs_health":
        return "docs_health_check"
    if command_family in {"cargo_test", "node_test"}:
        return "test_selection"
    if command_family in {"python_mypy", "python_ruff", "docs_health"}:
        return "quality_check"
    if command_family in {"ripgrep", "grep", "powershell_search"}:
        return "source_search"
    if command_family in {"powershell_read"}:
        return "source_read"
    if command_family in {"apply_patch", "shell_write"}:
        return "file_change"
    if command_family in {"git", "github_cli"}:
        return "repository_state"
    return "unknown"


def classify_failure_family(output_text: str, exit_code: int | None) -> str:
    """Return a privacy-safe failure family from bounded output inspection."""

    if exit_code is None:
        return "unknown"
    if exit_code == 0:
        return "none"
    material = output_text.casefold()
    if "syntaxerror" in material:
        return "syntax_error"
    if "modulenotfounderror" in material or "importerror" in material:
        return "dependency_missing"
    if "assertionerror" in material or "assert " in material:
        return "assertion_failure"
    if "command not found" in material or "not recognized as" in material:
        return "command_not_found"
    if "traceback" in material:
        return "python_exception"
    if "timeout" in material or "timed out" in material:
        return "timeout"
    if "permission denied" in material or "access is denied" in material:
        return "permission_or_access"
    if any(token in material for token in ("network", "connection refused", "download", "dns")):
        return "network_or_download"
    if "no tests ran" in material or "no tests collected" in material:
        return "no_tests_collected"
    if "failed" in material or "error:" in material:
        return "test_or_tool_failure"
    return "nonzero_exit"


def _normalize_path_token(token: str) -> str:
    token = token.strip().strip("\"'`;,")
    token = token.replace("\\", "/")
    if token.startswith(("a/", "b/")):
        token = token[2:]
    token = re.sub(r"[:#]L?\d+$", "", token)
    while token.startswith("./"):
        token = token[2:]
    return token.strip("/")


def _path_extension(path_token: str) -> str:
    suffix = Path(path_token).suffix.lower().lstrip(".")
    return suffix


def _path_kinds(path_token: str) -> set[str]:
    parts = [part.casefold() for part in path_token.replace("\\", "/").split("/") if part]
    extension = _path_extension(path_token)
    kinds: set[str] = set()
    if any(part in GENERATED_PATH_MARKERS for part in parts):
        kinds.add("generated")
    if "tests" in parts or any(part.startswith("test_") for part in parts):
        kinds.add("test")
    if "docs" in parts or extension in DOC_EXTENSIONS:
        kinds.add("docs")
    if "tools" in parts or "scripts" in parts:
        kinds.add("script")
    if extension in SOURCE_EXTENSIONS:
        kinds.add("source")
    if extension in CONFIG_EXTENSIONS:
        kinds.add("config")
    if not kinds:
        kinds.add("artifact")
    return kinds


def _is_safe_relative_path_token(path_token: str) -> bool:
    lowered = path_token.casefold()
    if re.match(r"^[a-z]:/", lowered) or lowered.startswith(("/", "\\\\", "~")):
        return False
    parts = [part for part in lowered.split("/") if part]
    if ".." in parts:
        return False
    if any(part in PRIVATE_PATH_MARKERS for part in parts):
        return False
    if any(marker in lowered for marker in ("api_key", "apikey", "bearer", "password")):
        return False
    return bool(parts)


def _path_tokens_from_input(tool_input: Any, command: str) -> list[str]:
    tokens: list[str] = []
    if command:
        for match in PATH_TOKEN_RE.finditer(command):
            tokens.extend(part for part in match.groups() if part)
    input_text = _input_text(tool_input)
    for match in PATCH_FILE_RE.finditer(input_text):
        tokens.append(match.group(1))
    if isinstance(tool_input, dict):
        for key in ("path", "file", "file_path", "target", "targets", "files"):
            value = tool_input.get(key)
            if isinstance(value, str):
                tokens.append(value)
            elif isinstance(value, list):
                tokens.extend(str(item) for item in value if isinstance(item, (str, Path)))
    return tokens


def path_breadcrumbs(tool_input: Any, command: str = "") -> dict[str, Any]:
    """Return path-derived breadcrumbs without retaining path text."""

    normalized = {
        token
        for token in (_normalize_path_token(item) for item in _path_tokens_from_input(tool_input, command))
        if token and not token.startswith("-")
    }
    if not normalized:
        return {}
    kinds: set[str] = set()
    extensions: set[str] = set()
    hashes: list[str] = []
    for token in sorted(normalized):
        kinds.update(_path_kinds(token))
        extension = _path_extension(token)
        if extension:
            extensions.add(extension)
        if _is_safe_relative_path_token(token):
            hashes.append(f"sha256:{hashlib.sha256(token.casefold().encode('utf-8')).hexdigest()[:16]}")
    result: dict[str, Any] = {
        "path_count": len(normalized),
        "path_categories": sorted(kinds),
        "path_extensions": sorted(extensions),
        "generated_file": "generated" in kinds,
    }
    if hashes:
        result["path_fingerprints"] = sorted(set(hashes))[:8]
    if result["generated_file"]:
        result["generated_file_reason"] = "generated_path_marker"
    return result


def parse_tool_exit_code(output_text: str) -> int | None:
    match = TOOL_EXIT_CODE_RE.search(output_text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _call_ref(call_id: str) -> str:
    return hashlib.sha1(call_id.encode("utf-8")).hexdigest()[:16] if call_id else ""


def extract_rollout_behavior_events(rollout: Path) -> list[dict[str, Any]]:
    """Extract structured tool/test behavior traces from a Codex rollout.

    The clean-source event lane records that a tool call happened and whether a
    bounded observation looked successful or failed. It stores hashes and coarse
    classes, not raw stdout, shell commands, full arguments, or local paths.
    """

    events: list[dict[str, Any]] = []
    current_turn = 0
    calls_by_ref: dict[str, dict[str, Any]] = {}
    for line_no, item in iter_jsonl(rollout):
        timestamp = item.get("timestamp")
        typ = item.get("type")
        payload = item.get("payload") or {}
        if typ == "event_msg" and payload.get("type") == "user_message":
            current_turn += 1
            continue
        if typ != "response_item" or not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        if ptype == "function_call":
            tool_name = _tool_name(payload)
            tool_input = _tool_input(payload)
            command = _input_command(tool_input)
            input_text = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
            call_ref = _call_ref(_tool_call_id(payload))
            command_class = classify_tool_command(tool_name, command)
            command_family = classify_command_family(tool_name, command)
            event = {
                "line": line_no,
                "timestamp": timestamp,
                "turn_index": current_turn or None,
                "event_kind": "tool_call_requested",
                "status": "requested",
                "tool_payload_kind": "function_call",
                "tool_name": tool_name,
                "call_ref": call_ref,
                "command_class": command_class,
                "tool_intent": classify_tool_intent(tool_name, command_class, command),
                "command_family": command_family,
                "target_class": classify_target_class(command_family, command),
                "test_target_class": classify_target_class(command_family, command)
                if command_class in {"test", "check"}
                else None,
                "input_sha256": _sha256_text(input_text),
                "input_field_names": sorted(tool_input.keys()) if isinstance(tool_input, dict) else [],
                "behavior_backed": True,
            }
            event.update(path_breadcrumbs(tool_input, command))
            if command_class == "edit":
                event["critical_operation_family"] = "file_edit_write_attempt"
            if call_ref:
                calls_by_ref[call_ref] = event
            events.append(event)
            continue
        if ptype not in {"function_call_output", "web_search_call"}:
            continue

        output_text = _tool_output_text(payload)
        call_ref = _call_ref(_tool_call_id(payload))
        prior = calls_by_ref.get(call_ref, {})
        exit_code = parse_tool_exit_code(output_text)
        status = "unknown"
        hard_event_kind = "tool_call_observed"
        if exit_code is not None:
            status = "succeeded" if exit_code == 0 else "failed"
            hard_event_kind = "tool_call_succeeded" if exit_code == 0 else "tool_call_failed"
        elif ptype == "web_search_call":
            status = "succeeded"
            hard_event_kind = "tool_call_succeeded"
        tool_name = prior.get("tool_name") or _tool_name(payload)
        command_class = str(prior.get("command_class") or classify_tool_command(str(tool_name), ""))
        observed = {
            "line": line_no,
            "timestamp": timestamp,
            "turn_index": current_turn or None,
            "event_kind": "tool_call_observed",
            "hard_event_kind": hard_event_kind,
            "tool_payload_kind": str(ptype),
            "tool_name": tool_name,
            "call_ref": call_ref,
            "command_class": command_class,
            "tool_intent": prior.get("tool_intent")
            or classify_tool_intent(str(tool_name), command_class, ""),
            "command_family": prior.get("command_family")
            or classify_command_family(str(tool_name), ""),
            "target_class": prior.get("target_class"),
            "failure_family": classify_failure_family(output_text, exit_code),
            "exit_code": exit_code,
            "status": status,
            "observation_sha256": _sha256_text(output_text),
            "behavior_backed": True,
        }
        for key in (
            "path_count",
            "path_categories",
            "path_extensions",
            "path_fingerprints",
            "generated_file",
            "generated_file_reason",
            "test_target_class",
        ):
            if key in prior:
                observed[key] = prior[key]
        if command_class in {"test", "check"} and exit_code is not None:
            observed["critical_operation_family"] = "test_check_command_result"
        events.append(observed)
    return events
