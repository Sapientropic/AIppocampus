#!/usr/bin/env python3
"""Fresh-venv wheel contract smoke for public AIppocampus release surfaces.

Editable installs prove the checkout works. This release gate proves the wheel
that a PyPI user receives can import and run the documented public surfaces
without leaning on the source tree, private registries, provider credentials, or
network access.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PUBLIC_IMPORT_MODULES = (
    "aippocampus_runtime",
    "aippocampus_runtime.artifacts.export_bundle",
    "aippocampus_runtime.artifacts.import_bundle",
    "aippocampus_runtime.coding.episode_arc_private_adjudication",
    "aippocampus_runtime.cli.facade",
    "aippocampus_runtime.config.registry",
    "aippocampus_runtime.hooks.install_lifecycle",
    "aippocampus_runtime.hooks.install_prompt",
    "aippocampus_runtime.knowledge.answer_gate",
    "aippocampus_runtime.knowledge.schema",
    "aippocampus_runtime.mcp.server",
    "aippocampus_runtime.mcp.tool_catalog",
    "aippocampus_runtime.onboarding.facade",
    "aippocampus_runtime.ops.log_retention",
    "aippocampus_runtime.ops.provider_doctor",
    "aippocampus_runtime.ops.recall_funnel_smoke",
    "aippocampus_runtime.ops.spend_doctor",
    "aippocampus_runtime.ops.storage_governance",
    "aippocampus_runtime.registry.api",
    "aippocampus_runtime.recall.continuity_domain_cli",
    "aippocampus_runtime.recall.why_cli",
    "aippocampus_runtime.source.clean_source",
    "aippocampus_runtime.source.search",
    "aippocampus_runtime.sync.bundle",
    "aippocampus_runtime.sync.encrypted.admin",
    "aippocampus_runtime.sync.object_storage.cli",
    "aippocampus_runtime.update.cli",
    "aippocampus_runtime.vault.dashboard",
    "conversation_sources",
    "conversation_sources.generic_jsonl",
)

PUBLIC_CLI_HELP_COMMANDS = (
    ("health", "--help"),
    ("onboard", "--help"),
    ("search", "--help"),
    ("export", "--help"),
    ("import", "--help"),
    ("import", "conversation", "--help"),
    ("update", "--help"),
    ("continuity-domain", "--help"),
    ("doctor", "--help"),
    ("doctor", "provider", "--help"),
    ("doctor", "config", "--help"),
    ("mcp", "--help"),
    ("smoke", "--help"),
    ("logs", "--help"),
    ("storage", "--help"),
    ("why-recall", "--help"),
    ("why-not-recall", "--help"),
    ("sync", "--help"),
    ("object-sync", "--help"),
    ("hooks", "--help"),
    ("hooks", "prompt", "--help"),
    ("hooks", "lifecycle", "--help"),
    ("episode-arcs", "--help"),
)

EXPECTED_MCP_TOOLS = (
    "search_memory",
    "recall_context",
    "recall_deepen",
    "latest_reply",
    "get_turn_context",
    "list_threads",
    "register_thread",
    "sync_status",
    "memory_health",
)

CONTRACT_QUERY = "peppercorn continuity phrase"
DEFAULT_TIMEOUT = 120
FAIL_TAIL_CHARS = 4000
MINIMAL_ENV_ALLOWLIST = {
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PYTHONIOENCODING",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "WINDIR",
}


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    message: str
    details: dict[str, Any] | None = None


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "README.md").exists():
            return candidate
    raise SystemExit(f"could not find repository root from {start}")


def add(
    checks: list[Check],
    check_id: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(Check(check_id, status, message, details))


def summarize_command(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-FAIL_TAIL_CHARS:],
        "stderr_tail": proc.stderr[-FAIL_TAIL_CHARS:],
    }


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def venv_executable(venv: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


def fresh_env(work_dir: Path, repo_root: Path, *, include_live_provider: bool) -> dict[str, str]:
    if include_live_provider:
        env = dict(os.environ)
    else:
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in MINIMAL_ENV_ALLOWLIST
        }
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)

    home = work_dir / "isolated-home"
    registry = work_dir / "isolated-registry"
    codex_home = work_dir / "isolated-codex-home"
    generic_import = work_dir / "generic-import"
    appdata = home / "AppData" / "Roaming"
    local_appdata = home / "AppData" / "Local"
    temp = work_dir / "tmp"
    for path in (home, registry, codex_home, generic_import, appdata, local_appdata, temp):
        path.mkdir(parents=True, exist_ok=True)

    env.update(
        {
            "AIPPOCAMPUS_CONTRACT_REPO_ROOT": str(repo_root),
            "AIPPOCAMPUS_HOME": str(home / "aippocampus"),
            "AIPPOCAMPUS_REGISTRY_DIR": str(registry),
            "AIPPOCAMPUS_GENERIC_IMPORT_DIR": str(generic_import),
            "CODEX_HOME": str(codex_home),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(local_appdata),
            "TMP": str(temp),
            "TEMP": str(temp),
            "TMPDIR": str(temp),
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONUTF8": "1",
        }
    )
    return env


def resolve_wheel_arg(value: str | None, *, repo: Path) -> Path | None:
    if not value:
        return None
    matches = sorted(repo.glob(value)) if any(char in value for char in "*?[") else [Path(value)]
    if not matches:
        raise SystemExit(f"wheel path did not match anything: {value}")
    if len(matches) > 1:
        raise SystemExit(f"wheel path matched multiple files; pass one wheel: {value}")
    wheel = matches[0]
    if not wheel.is_absolute():
        wheel = (repo / wheel).resolve()
    if not wheel.exists():
        raise SystemExit(f"wheel does not exist: {wheel}")
    return wheel


def build_wheel(repo: Path, dist_dir: Path, checks: list[Check]) -> Path | None:
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)
    proc = run_command(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=repo,
        timeout=240,
    )
    if proc.returncode != 0:
        add(
            checks,
            "build_wheel",
            "fail",
            "python -m build --wheel failed",
            summarize_command(proc),
        )
        return None
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(wheels) != 1:
        add(
            checks,
            "build_wheel",
            "fail",
            "wheel build did not produce exactly one wheel",
            {"wheel_count": len(wheels), "wheel_names": [path.name for path in wheels]},
        )
        return None
    add(checks, "build_wheel", "pass", "built one wheel", {"wheel": wheels[0].name})
    return wheels[0]


def create_and_install_venv(wheel: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> Path | None:
    venv = work_dir / "fresh-venv"
    proc = run_command([sys.executable, "-m", "venv", str(venv)], cwd=work_dir, timeout=180)
    if proc.returncode != 0:
        add(checks, "fresh_venv", "fail", "creating a fresh venv failed", summarize_command(proc))
        return None
    python = venv_python(venv)
    proc = run_command(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
        cwd=work_dir,
        env=env,
        timeout=180,
    )
    if proc.returncode != 0:
        add(
            checks,
            "install_wheel",
            "fail",
            "installing the wheel into the fresh venv failed",
            summarize_command(proc),
        )
        return None
    add(
        checks,
        "install_wheel",
        "pass",
        "installed wheel into a fresh venv without dependency/network resolution",
        {"wheel": wheel.name},
    )
    return venv


def json_from_stdout(proc: subprocess.CompletedProcess[str]) -> Any:
    return json.loads(proc.stdout)


def check_import_matrix(venv: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> None:
    code = textwrap.dedent(
        """
        import importlib
        import json
        import os
        from pathlib import Path

        modules = json.loads(os.environ["AIPPOCAMPUS_CONTRACT_IMPORTS"])
        repo_root = Path(os.environ["AIPPOCAMPUS_CONTRACT_REPO_ROOT"]).resolve()
        loaded = []
        source_tree_modules = []
        for name in modules:
            module = importlib.import_module(name)
            loaded.append(name)
            module_file = getattr(module, "__file__", None)
            if module_file:
                try:
                    Path(module_file).resolve().relative_to(repo_root)
                except ValueError:
                    pass
                else:
                    source_tree_modules.append(name)
        print(json.dumps({"loaded": loaded, "source_tree_modules": source_tree_modules}))
        """
    )
    command_env = dict(env)
    command_env["AIPPOCAMPUS_CONTRACT_IMPORTS"] = json.dumps(PUBLIC_IMPORT_MODULES)
    proc = run_command([str(venv_python(venv)), "-c", code], cwd=work_dir, env=command_env)
    if proc.returncode != 0:
        add(
            checks,
            "public_import_matrix",
            "fail",
            "a documented public import failed from the installed wheel",
            summarize_command(proc),
        )
        return
    payload = json_from_stdout(proc)
    source_tree_modules = list(payload.get("source_tree_modules") or [])
    if source_tree_modules:
        add(
            checks,
            "public_import_matrix",
            "fail",
            "imports resolved from the source tree instead of the wheel",
            {"source_tree_modules": source_tree_modules},
        )
        return
    add(
        checks,
        "public_import_matrix",
        "pass",
        "documented public modules import from the installed wheel",
        {"module_count": len(payload.get("loaded") or [])},
    )


def check_cli_help(venv: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> None:
    proc = run_command([str(venv_executable(venv, "aippocampus")), "--help"], cwd=work_dir, env=env)
    required = ("Personal path", "doctor config", "mcp list-tools", "import conversation")
    if proc.returncode != 0 or any(term not in proc.stdout for term in required):
        add(
            checks,
            "cli_entrypoint",
            "fail",
            "aippocampus console script did not expose the documented command help",
            {**summarize_command(proc), "required_terms": list(required)},
        )
        return
    add(checks, "cli_entrypoint", "pass", "aippocampus console script exposes public help")


def check_cli_command_matrix(
    venv: Path,
    work_dir: Path,
    env: dict[str, str],
    checks: list[Check],
) -> None:
    cli = str(venv_executable(venv, "aippocampus"))
    failures: list[dict[str, Any]] = []
    for args in PUBLIC_CLI_HELP_COMMANDS:
        proc = run_command([cli, *args], cwd=work_dir, env=env)
        if proc.returncode != 0:
            failures.append({"args": list(args), **summarize_command(proc)})
    if failures:
        add(
            checks,
            "cli_command_matrix",
            "fail",
            "one or more documented CLI command help surfaces failed from the wheel",
            {"failures": failures},
        )
        return
    add(
        checks,
        "cli_command_matrix",
        "pass",
        "documented public CLI command help surfaces run from the wheel",
        {"command_count": len(PUBLIC_CLI_HELP_COMMANDS)},
    )


def check_doctor_config(venv: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> None:
    proc = run_command(
        [str(venv_executable(venv, "aippocampus")), "doctor", "config", "--json"],
        cwd=work_dir,
        env=env,
    )
    if proc.returncode != 0:
        add(checks, "doctor_config", "fail", "doctor config command failed", summarize_command(proc))
        return
    try:
        payload = json_from_stdout(proc)
    except json.JSONDecodeError as exc:
        add(
            checks,
            "doctor_config",
            "fail",
            "doctor config did not emit JSON",
            {"error": str(exc), **summarize_command(proc)},
        )
        return
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict) or data.get("kind") != "aippocampus_config_registry_report":
        add(
            checks,
            "doctor_config",
            "fail",
            "doctor config JSON does not match the public config report contract",
            {"top_level_keys": sorted(payload) if isinstance(payload, dict) else []},
        )
        return
    add(
        checks,
        "doctor_config",
        "pass",
        "doctor config public JSON report runs from the wheel",
        {"knob_count": len(data.get("knobs") or [])},
    )


def check_mcp_tools(venv: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> None:
    proc = run_command(
        [str(venv_executable(venv, "aippocampus")), "mcp", "list-tools", "--json"],
        cwd=work_dir,
        env=env,
    )
    if proc.returncode != 0:
        add(checks, "mcp_tools", "fail", "MCP tool catalog command failed", summarize_command(proc))
        return
    try:
        payload = json_from_stdout(proc)
    except json.JSONDecodeError as exc:
        add(
            checks,
            "mcp_tools",
            "fail",
            "MCP tool catalog did not emit JSON",
            {"error": str(exc), **summarize_command(proc)},
        )
        return
    tool_names = {str(tool.get("name")) for tool in payload.get("tools") or [] if isinstance(tool, dict)}
    missing = sorted(set(EXPECTED_MCP_TOOLS) - tool_names)
    if missing:
        add(checks, "mcp_tools", "fail", "MCP tool catalog is missing documented tools", {"missing": missing})
        return
    add(checks, "mcp_tools", "pass", "MCP tools/list surface is available from the wheel", {"tool_count": len(tool_names)})


def check_package_data(venv: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> None:
    code = textwrap.dedent(
        """
        import importlib.resources as resources
        import json

        root = resources.files("aippocampus_runtime.vault")
        assets = {}
        for filename in ("dashboard_v2.css", "dashboard_v2.js"):
            text = (root / "dashboard_assets" / filename).read_text(encoding="utf-8")
            assets[filename] = len(text)
        print(json.dumps({"assets": assets}))
        """
    )
    proc = run_command([str(venv_python(venv)), "-c", code], cwd=work_dir, env=env)
    if proc.returncode != 0:
        add(
            checks,
            "package_data",
            "fail",
            "wheel package data files are missing or unreadable",
            summarize_command(proc),
        )
        return
    try:
        payload = json_from_stdout(proc)
    except json.JSONDecodeError as exc:
        add(
            checks,
            "package_data",
            "fail",
            "package data check did not emit JSON",
            {"error": str(exc), **summarize_command(proc)},
        )
        return
    assets = payload.get("assets") if isinstance(payload, dict) else {}
    missing = [
        name
        for name in ("dashboard_v2.css", "dashboard_v2.js")
        if not isinstance(assets, dict) or int(assets.get(name) or 0) <= 0
    ]
    if missing:
        add(checks, "package_data", "fail", "wheel package data files were empty", {"missing": missing})
        return
    add(checks, "package_data", "pass", "wheel package data files are present and readable")


def parse_mcp_tool_text(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response, dict) else {}
    content = result.get("content") if isinstance(result, dict) else []
    if not isinstance(content, list) or not content:
        raise ValueError("MCP response did not include content")
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text":
        raise ValueError("MCP response content is not text")
    return json.loads(str(first.get("text") or "{}"))


def run_mcp_call(
    venv: Path,
    *,
    work_dir: Path,
    env: dict[str, str],
    request_id: int,
    name: str,
    arguments: dict[str, Any],
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    proc = run_command(
        [str(venv_python(venv)), "-m", "aippocampus_runtime.mcp.server"],
        cwd=work_dir,
        env=env,
        input_text=json.dumps(request, ensure_ascii=False) + "\n",
    )
    if proc.returncode != 0:
        return proc, None
    try:
        response = json.loads(proc.stdout)
        return proc, parse_mcp_tool_text(response)
    except (json.JSONDecodeError, ValueError) as exc:
        return proc, {"_parse_error": str(exc)}


def write_generic_jsonl_fixture(root: Path) -> tuple[Path, Path]:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    source = root / "generic-session.jsonl"
    rows = [
        {
            "session_id": "wheel-contract-session",
            "role": "user",
            "text": f"remember the {CONTRACT_QUERY}",
            "timestamp": "2026-06-08T00:00:00Z",
            "cwd": str(workspace),
        },
        {
            "session_id": "wheel-contract-session",
            "role": "assistant",
            "text": f"I will keep the {CONTRACT_QUERY} source backed.",
            "timestamp": "2026-06-08T00:00:01Z",
        },
    ]
    source.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return source, workspace


def check_generic_jsonl_reopen_path(
    venv: Path,
    work_dir: Path,
    env: dict[str, str],
    checks: list[Check],
) -> None:
    fixture = work_dir / "generic-jsonl-reopen"
    registry = fixture / "registry"
    source, workspace = write_generic_jsonl_fixture(fixture)
    cli = str(venv_executable(venv, "aippocampus"))

    import_proc = run_command(
        [
            cli,
            "import",
            "conversation",
            "--format",
            "generic-jsonl",
            "--input",
            str(source),
            "--registry-dir",
            str(registry),
            "--cwd",
            str(workspace),
            "--json",
        ],
        cwd=work_dir,
        env=env,
    )
    if import_proc.returncode != 0:
        add(checks, "generic_jsonl_reopen", "fail", "generic JSONL import failed", summarize_command(import_proc))
        return
    try:
        import_payload = json_from_stdout(import_proc)
        clean_source_dir = Path(import_payload["entry"]["paths"]["clean_source_dir"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "generic JSONL import did not return a clean-source path",
            {"error": str(exc), **summarize_command(import_proc)},
        )
        return

    direct_dry_run_proc = run_command(
        [
            str(venv_python(venv)),
            "-m",
            "aippocampus_runtime.registry.api",
            "--registry-dir",
            str(registry),
            "register-source",
            "--provider",
            "generic-jsonl",
            "--input",
            str(source),
            "--cwd",
            str(workspace),
            "--dry-run",
            "--json",
        ],
        cwd=work_dir,
        env=env,
    )
    if direct_dry_run_proc.returncode != 0:
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "direct registry.api register-source dry-run failed from the wheel",
            summarize_command(direct_dry_run_proc),
        )
        return
    try:
        dry_run_payload = json_from_stdout(direct_dry_run_proc)
    except json.JSONDecodeError as exc:
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "direct registry.api register-source dry-run did not emit JSON",
            {"error": str(exc), **summarize_command(direct_dry_run_proc)},
        )
        return
    if dry_run_payload.get("ok") is not True or dry_run_payload.get("dry_run") is not True:
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "direct registry.api register-source dry-run returned the wrong contract",
            {"keys": sorted(dry_run_payload) if isinstance(dry_run_payload, dict) else []},
        )
        return

    search_proc = run_command(
        [
            cli,
            "search",
            "peppercorn",
            "--cwd",
            str(workspace),
            "--clean-source-dir",
            str(clean_source_dir),
            "--json",
        ],
        cwd=work_dir,
        env=env,
    )
    if search_proc.returncode != 0:
        add(checks, "generic_jsonl_reopen", "fail", "clean-source search did not find the fixture", summarize_command(search_proc))
        return
    try:
        search_payload = json_from_stdout(search_proc)
        matches = list(search_payload.get("matches") or [])
    except json.JSONDecodeError as exc:
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "clean-source search did not emit JSON",
            {"error": str(exc), **summarize_command(search_proc)},
        )
        return
    if not matches:
        add(checks, "generic_jsonl_reopen", "fail", "clean-source search returned no matches")
        return

    context_proc, context_payload = run_mcp_call(
        venv,
        work_dir=work_dir,
        env=env,
        request_id=1,
        name="recall_context",
        arguments={
            "intent": "peppercorn",
            "cwd": str(workspace),
            "clean_source_dir": str(clean_source_dir),
            "registry_dir": str(registry),
            "max": 3,
            "detail": "full",
        },
    )
    if context_proc.returncode != 0 or not isinstance(context_payload, dict):
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "MCP recall_context failed for imported clean source",
            summarize_command(context_proc),
        )
        return
    if context_payload.get("_parse_error"):
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "MCP recall_context returned an unparsable tool payload",
            {"error": context_payload.get("_parse_error"), **summarize_command(context_proc)},
        )
        return
    routes = list(context_payload.get("routes") or [])
    handle = routes[0].get("handle") if routes and isinstance(routes[0], dict) else None
    if not handle:
        add(checks, "generic_jsonl_reopen", "fail", "recall_context did not return a reopenable handle")
        return

    deepen_proc, deepen_payload = run_mcp_call(
        venv,
        work_dir=work_dir,
        env=env,
        request_id=2,
        name="recall_deepen",
        arguments={
            "handle": handle,
            "cwd": str(workspace),
            "clean_source_dir": str(clean_source_dir),
            "registry_dir": str(registry),
            "max": 3,
        },
    )
    if deepen_proc.returncode != 0 or not isinstance(deepen_payload, dict):
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "MCP recall_deepen failed for imported clean source",
            summarize_command(deepen_proc),
        )
        return
    if deepen_payload.get("_parse_error"):
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "MCP recall_deepen returned an unparsable tool payload",
            {"error": deepen_payload.get("_parse_error"), **summarize_command(deepen_proc)},
        )
        return
    window = deepen_payload.get("source_window") if isinstance(deepen_payload, dict) else {}
    raw_messages = window.get("messages") if isinstance(window, dict) else []
    messages = raw_messages if isinstance(raw_messages, list) else []
    text = "\n".join(str(item.get("text") or "") for item in messages if isinstance(item, dict))
    if deepen_payload.get("evidence_level") != "source_backed" or "peppercorn" not in text:
        add(
            checks,
            "generic_jsonl_reopen",
            "fail",
            "recall_deepen did not reopen the expected source-backed window",
            {
                "status": deepen_payload.get("status"),
                "evidence_level": deepen_payload.get("evidence_level"),
                "message_count": len(messages),
            },
        )
        return
    add(
        checks,
        "generic_jsonl_reopen",
        "pass",
        "generic JSONL import, clean-source search, and MCP reopen path work from the wheel",
        {"match_count": len(matches), "reopened_message_count": len(messages)},
    )


def check_hooks_isolated_rollback(venv: Path, work_dir: Path, env: dict[str, str], checks: list[Check]) -> None:
    cli = str(venv_executable(venv, "aippocampus"))
    codex_home = work_dir / "hook-codex-home"
    failures: list[dict[str, Any]] = []
    for hook_kind in ("prompt", "lifecycle"):
        for action in ("status", "install", "status", "uninstall", "status"):
            proc = run_command(
                [
                    cli,
                    "hooks",
                    hook_kind,
                    action,
                    "--codex-home",
                    str(codex_home),
                    "--json",
                ],
                cwd=work_dir,
                env=env,
            )
            if proc.returncode != 0:
                failures.append({"hook": hook_kind, "action": action, **summarize_command(proc)})
                break
    if failures:
        add(
            checks,
            "hooks_isolated_rollback",
            "fail",
            "isolated hook install/status/uninstall smoke failed",
            {"failures": failures},
        )
        return
    add(
        checks,
        "hooks_isolated_rollback",
        "pass",
        "prompt and lifecycle hooks can status, install, and roll back in an isolated Codex home",
    )


def package_owner_for_module(module_name: str) -> str:
    parts = module_name.split(".")
    if not parts:
        return module_name
    if parts[0] == "aippocampus_runtime" and len(parts) >= 2:
        return ".".join(parts[:2])
    if parts[0] == "conversation_sources":
        return "conversation_sources"
    return parts[0]


def run_contract(
    repo: Path,
    *,
    wheel: Path | None = None,
    keep_temp: bool = False,
    include_live_provider: bool = False,
) -> dict[str, Any]:
    checks: list[Check] = []
    temp_context = tempfile.TemporaryDirectory(prefix="aippocampus-wheel-contract-")
    work_dir = Path(temp_context.name)
    try:
        env = fresh_env(work_dir, repo, include_live_provider=include_live_provider)
        selected_wheel = wheel
        if selected_wheel is None:
            selected_wheel = build_wheel(repo, work_dir / "dist", checks)
            if selected_wheel is None:
                return render_result(checks, work_dir=work_dir if keep_temp else None)
        else:
            add(checks, "build_wheel", "pass", "using prebuilt wheel", {"wheel": selected_wheel.name})

        venv = create_and_install_venv(selected_wheel, work_dir, env, checks)
        if venv is not None:
            check_import_matrix(venv, work_dir, env, checks)
            check_cli_help(venv, work_dir, env, checks)
            check_cli_command_matrix(venv, work_dir, env, checks)
            check_doctor_config(venv, work_dir, env, checks)
            check_mcp_tools(venv, work_dir, env, checks)
            check_package_data(venv, work_dir, env, checks)
            check_generic_jsonl_reopen_path(venv, work_dir, env, checks)
            check_hooks_isolated_rollback(venv, work_dir, env, checks)
        return render_result(checks, work_dir=work_dir if keep_temp else None)
    finally:
        if keep_temp:
            temp_context.cleanup = lambda: None  # type: ignore[method-assign]
        temp_context.cleanup()


def render_result(checks: list[Check], *, work_dir: Path | None = None) -> dict[str, Any]:
    summary: dict[str, int] = {"pass": 0, "fail": 0, "warn": 0}
    for check in checks:
        summary[check.status] = summary.get(check.status, 0) + 1
    result: dict[str, Any] = {
        "kind": "aippocampus_wheel_contract_check",
        "schema_version": 1,
        "ok": summary.get("fail", 0) == 0,
        "summary": summary,
        "checks": [asdict(check) for check in checks],
        "contract": {
            "fresh_venv": True,
            "no_network_install": True,
            "live_provider_default": False,
            "source_tree_imports_forbidden": True,
            "public_import_modules": list(PUBLIC_IMPORT_MODULES),
            "public_cli_help_commands": [list(args) for args in PUBLIC_CLI_HELP_COMMANDS],
            "expected_mcp_tools": list(EXPECTED_MCP_TOOLS),
        },
    }
    if work_dir is not None:
        result["work_dir"] = str(work_dir)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument(
        "--wheel",
        help=(
            "Use one prebuilt wheel path or repo-relative glob instead of building. "
            "Default builds a fresh wheel first."
        ),
    )
    parser.add_argument("--keep-temp", action="store_true", help="Keep the fresh venv work directory for debugging.")
    parser.add_argument(
        "--include-live-provider",
        action="store_true",
        help="Do not scrub provider/token-like environment variables. Off by default.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = find_repo_root(Path(args.repo_root))
    wheel = resolve_wheel_arg(args.wheel, repo=repo)
    result = run_contract(
        repo,
        wheel=wheel,
        keep_temp=args.keep_temp,
        include_live_provider=args.include_live_provider,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "pass" if result["ok"] else "fail"
        print(f"AIppocampus wheel contract: {status}")
        for check in result["checks"]:
            print(f"- {check['id']}: {check['status']} - {check['message']}")
        if result.get("work_dir"):
            print(f"work dir: {result['work_dir']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
