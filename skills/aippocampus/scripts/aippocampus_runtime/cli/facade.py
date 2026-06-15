"""Unified AIppocampus command facade over packaged runtime entrypoints."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.metadata
import inspect
import json
import sys
import tomllib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable, TextIO

SCRIPT_DIR = Path(__file__).resolve().parents[2]
PLUGIN_MANIFEST_RELATIVE = Path("plugins") / "aippocampus" / ".codex-plugin" / "plugin.json"


def _find_project_root(start: Path = SCRIPT_DIR) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _json_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _pyproject_version(root: Path | None) -> str | None:
    if root is None:
        return None
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except Exception:
        return None
    project = data.get("project") if isinstance(data, dict) else None
    return str(project.get("version") or "") if isinstance(project, dict) else None


def _distribution_version() -> str | None:
    try:
        return importlib.metadata.version("aippocampus")
    except importlib.metadata.PackageNotFoundError:
        return None


def version_payload() -> dict[str, Any]:
    root = _find_project_root()
    pyproject = _pyproject_version(root)
    plugin = _json_file(root / PLUGIN_MANIFEST_RELATIVE) if root else None
    plugin_version = str((plugin or {}).get("version") or "") or None
    active_version = pyproject or _distribution_version() or plugin_version or "unknown"
    versions = {
        "active": active_version,
        "pyproject": pyproject,
        "installed_distribution": _distribution_version(),
        "plugin_manifest": plugin_version,
    }
    known = {value for value in versions.values() if value}
    return {
        "kind": "aippocampus_version",
        "ok": bool(active_version and active_version != "unknown"),
        "version": active_version,
        "versions": versions,
        "metadata_consistent": len(known) <= 1,
        "source_checkout_available": root is not None,
        "runtime": {
            "facade": "aippocampus_runtime.cli.facade",
            "python": Path(sys.executable).name,
        },
    }


def render_version_text(payload: dict[str, Any]) -> str:
    version = payload.get("version") or "unknown"
    suffix = "" if payload.get("metadata_consistent") else " (metadata mismatch)"
    return f"AIppocampus {version}{suffix}"

@dataclass(frozen=True)
class CommandSpec:
    script_name: str
    module_name: str
    prefix: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandInvocation:
    command: str
    script_name: str
    module_name: str
    args: list[str]


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    invocation: CommandInvocation | None
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


COMMANDS = {
    "health": CommandSpec("aippocampus_health.py", "aippocampus_runtime.health"),
    "onboard": CommandSpec("onboard.py", "aippocampus_runtime.onboarding.facade"),
    "search": CommandSpec("search_clean_source.py", "aippocampus_runtime.source.search"),
    "agent": CommandSpec("agent_continuity.py", "aippocampus_runtime.recall.agent_continuity"),
    "export": CommandSpec("export_bundle.py", "aippocampus_runtime.artifacts.export_bundle"),
    "import": CommandSpec("import_bundle.py", "aippocampus_runtime.artifacts.import_bundle"),
    "doctor": CommandSpec("provider_doctor.py", "aippocampus_runtime.ops.provider_doctor"),
    "update": CommandSpec("update.py", "aippocampus_runtime.update.cli"),
    "plugin": CommandSpec("plugin.py", "aippocampus_runtime.update.plugin_installer"),
    "smoke": CommandSpec("recall_funnel_smoke.py", "aippocampus_runtime.ops.recall_funnel_smoke"),
    "logs": CommandSpec("log_retention.py", "aippocampus_runtime.ops.log_retention"),
    "maintenance": CommandSpec("maintenance.py", "aippocampus_runtime.ops.maintenance"),
    "warm": CommandSpec("warm_ambient_cli.py", "aippocampus_runtime.warm_ambient.cli"),
    "storage": CommandSpec(
        "storage_governance.py",
        "aippocampus_runtime.ops.storage_governance",
    ),
    "observatory": CommandSpec(
        "cognitive_observatory.py",
        "aippocampus_runtime.ops.cognitive_observatory",
    ),
    "episode-arcs": CommandSpec(
        "episode_arc_private_adjudication.py",
        "aippocampus_runtime.coding.episode_arc_private_adjudication",
    ),
    "why-recall": CommandSpec(
        "why_recall.py",
        "aippocampus_runtime.recall.why_cli",
        prefix=("why-recall",),
    ),
    "why-not-recall": CommandSpec(
        "why_recall.py",
        "aippocampus_runtime.recall.why_cli",
        prefix=("why-not-recall",),
    ),
    "self-note": CommandSpec(
        "agent_self_note_cli.py",
        "aippocampus_runtime.source.agent_self_note_cli",
    ),
    "continuity-domain": CommandSpec(
        "continuity_domain.py",
        "aippocampus_runtime.recall.continuity_domain_cli",
    ),
    "work-guard": CommandSpec(
        "issue_work_guard.py",
        "aippocampus_runtime.ops.issue_work_guard",
    ),
    "telepathy": CommandSpec(
        "telepathy_handoff_store.py",
        "aippocampus_runtime.ops.telepathy_handoff_store",
    ),
}

SCRIPT_MODULES = {
    spec.script_name: spec.module_name for spec in COMMANDS.values()
} | {
    "aippocampus_mcp_server.py": "aippocampus_runtime.mcp.server",
    "registry.py": "aippocampus_runtime.registry.api",
    "sync_bundle.py": "aippocampus_runtime.sync.bundle",
    "sync_object_storage.py": "aippocampus_runtime.sync.object_storage.cli",
    "provider_doctor.py": "aippocampus_runtime.ops.provider_doctor",
    "cognitive_observatory.py": "aippocampus_runtime.ops.cognitive_observatory",
    "episode_arc_private_adjudication.py": (
        "aippocampus_runtime.coding.episode_arc_private_adjudication"
    ),
    "update.py": "aippocampus_runtime.update.cli",
    "plugin.py": "aippocampus_runtime.update.plugin_installer",
    "recall_funnel_smoke.py": "aippocampus_runtime.ops.recall_funnel_smoke",
    "maintenance.py": "aippocampus_runtime.ops.maintenance",
    "warm_ambient_cli.py": "aippocampus_runtime.warm_ambient.cli",
    "continuity_domain.py": "aippocampus_runtime.recall.continuity_domain_cli",
    "issue_work_guard.py": "aippocampus_runtime.ops.issue_work_guard",
    "telepathy_handoff_store.py": "aippocampus_runtime.ops.telepathy_handoff_store",
    "agent_continuity.py": "aippocampus_runtime.recall.agent_continuity",
    "storage_governance.py": "aippocampus_runtime.ops.storage_governance",
    "install_aippocampus_prompt_hook.py": "aippocampus_runtime.hooks.install_prompt",
    "install_aippocampus_lifecycle_hook.py": "aippocampus_runtime.hooks.install_lifecycle",
    "install_aippocampus_action_hint_hook.py": "aippocampus_runtime.hooks.install_action_hint",
    "aippocampus_claude_code_hooks.py": "aippocampus_runtime.hooks.claude_code",
}


def module_name_for_script(script_name: str) -> str:
    return SCRIPT_MODULES.get(script_name, Path(script_name).stem)


def run_script(script_name: str, args: list[str]) -> int:
    return run_module_main(module_name_for_script(script_name), script_name, args)


def _coerce_exit_code(result: Any) -> int:
    return int(result or 0)


def _system_exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def main_accepts_argv(main_func: Callable[..., Any]) -> bool:
    """Return whether a command main can be called as `main(argv)`.

    The facade should prefer package APIs over script emulation. Some older
    entrypoints still only expose a no-argument `main()` that reads `sys.argv`;
    those stay on the compatibility path until their owner grows an argv-aware
    API. Do not simplify this to "always pass argv": it would break legacy
    public scripts that are intentionally still script-shaped.
    """
    try:
        signature = inspect.signature(main_func)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        }:
            return True
    return False


def run_module_main(module_name: str, script_name: str, args: list[str]) -> int:
    """Run a packaged command main in-process.

    Argv-aware package owners are called directly as Python APIs. Legacy
    no-argument mains still get a temporary script-shaped `sys.argv` so old
    direct-entrypoint semantics remain intact while the runtime is migrated.
    """
    module = importlib.import_module(module_name)
    main_func = getattr(module, "main", None)
    if not callable(main_func):
        raise RuntimeError(f"module {module_name} has no callable main()")

    if main_accepts_argv(main_func):
        try:
            return _coerce_exit_code(main_func(list(args)))
        except SystemExit as exc:
            return _system_exit_code(exc)

    old_argv = sys.argv[:]
    sys.argv = [str(SCRIPT_DIR / script_name), *args]
    try:
        return _coerce_exit_code(main_func())
    except SystemExit as exc:
        return _system_exit_code(exc)
    finally:
        sys.argv = old_argv


def invocation_from_spec(command: str, spec: CommandSpec, rest: list[str]) -> CommandInvocation:
    return CommandInvocation(
        command=command,
        script_name=spec.script_name,
        module_name=spec.module_name,
        args=[*spec.prefix, *rest],
    )


def _conversation_import_args(rest: list[str]) -> list[str]:
    registry_args: list[str] = []
    source_args: list[str] = ["register-source"]
    index = 0
    while index < len(rest):
        item = rest[index]
        if item == "--registry-dir" and index + 1 < len(rest):
            registry_args.extend([item, rest[index + 1]])
            index += 2
            continue
        if item == "--format" and index + 1 < len(rest):
            source_args.extend(["--provider", rest[index + 1]])
            index += 2
            continue
        source_args.append(item)
        index += 1
    return [*registry_args, *source_args]


def resolve_command(argv: list[str]) -> CommandInvocation | None:
    if not argv:
        return None
    command, rest = argv[0], argv[1:]
    if command == "import" and rest and rest[0] == "conversation":
        return CommandInvocation(
            command,
            "registry.py",
            module_name_for_script("registry.py"),
            _conversation_import_args(rest[1:]),
        )
    if command == "plugin" and rest and rest[0] == "status":
        return CommandInvocation(
            command,
            "update.py",
            module_name_for_script("update.py"),
            ["status", *rest[1:]],
        )
    if command in COMMANDS:
        return invocation_from_spec(command, COMMANDS[command], rest)
    if command == "mcp":
        args = ["--list-tools", *rest[1:]] if rest and rest[0] == "list-tools" else rest
        return CommandInvocation(
            command=command,
            script_name="aippocampus_mcp_server.py",
            module_name=module_name_for_script("aippocampus_mcp_server.py"),
            args=args,
        )
    if command == "sync":
        return CommandInvocation(
            command,
            "sync_bundle.py",
            module_name_for_script("sync_bundle.py"),
            rest,
        )
    if command == "object-sync":
        return CommandInvocation(
            command,
            "sync_object_storage.py",
            module_name_for_script("sync_object_storage.py"),
            rest,
        )
    if command == "hooks":
        if rest and rest[0] == "claude-code":
            return CommandInvocation(
                command,
                "aippocampus_claude_code_hooks.py",
                module_name_for_script("aippocampus_claude_code_hooks.py"),
                list(rest[1:]),
            )
        hook_kind = "prompt"
        hook_args = list(rest)
        if hook_args and hook_args[0] in {"prompt", "lifecycle", "action"}:
            hook_kind = hook_args.pop(0)
        script_by_kind = {
            "prompt": "install_aippocampus_prompt_hook.py",
            "lifecycle": "install_aippocampus_lifecycle_hook.py",
            "action": "install_aippocampus_action_hint_hook.py",
        }
        script = script_by_kind[hook_kind]
        return CommandInvocation(command, script, module_name_for_script(script), hook_args)
    return None


def run_invocation(invocation: CommandInvocation) -> int:
    return run_script(invocation.script_name, invocation.args)


def dispatch(argv: list[str]) -> tuple[CommandInvocation | None, int]:
    args = list(argv)
    if not args or args[0] in {"-h", "--help"}:
        print_help()
        return None, 0
    if args[0] in {"--version", "-V", "version"}:
        payload = version_payload()
        if "--json" in args:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_version_text(payload))
        return None, 0

    invocation = resolve_command(args)
    if invocation is not None:
        return invocation, run_invocation(invocation)

    print(f"unknown command: {args[0]}", file=sys.stderr)
    print_help(file=sys.stderr)
    return None, 2


def run_command(argv: list[str] | None = None, *, capture_output: bool = False) -> CommandResult:
    args = list(sys.argv[1:] if argv is None else argv)
    if not capture_output:
        invocation, code = dispatch(args)
        return CommandResult(tuple(args), invocation, code)

    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        invocation, code = dispatch(args)
    return CommandResult(tuple(args), invocation, code, stdout.getvalue(), stderr.getvalue())


def main(argv: list[str] | None = None) -> int:
    return run_command(argv).exit_code


def run_hooks(args: list[str]) -> int:
    invocation = resolve_command(["hooks", *args])
    if invocation is None:
        return 2
    return run_invocation(invocation)


def print_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    parser = argparse.ArgumentParser(
        prog="aippocampus",
        description="Unified facade for AIppocampus personal and operator commands.",
        add_help=False,
    )
    parser.print_usage(target)
    print("", file=target)
    print("Commands:", file=target)
    print("", file=target)
    print("Personal path:", file=target)
    print("  health              Run runtime health checks", file=target)
    print("  version             Show active runtime and release metadata version", file=target)
    print("  onboard             Check/register provider-backed clean source", file=target)
    print("  search              Search clean-source memory", file=target)
    print("  agent recall        Opt-in agent recall/AIppo/deepen/explain path", file=target)
    print("  self-note append    Add a voluntary foreground-agent margin note", file=target)
    print("  continuity-domain   Explicitly produce/append source-trailed domains", file=target)
    print("  work-guard          Agent issue-work active-pull orientation packet", file=target)
    print("  update status       Check personal core/magic readiness", file=target)
    print("  export              Export a portable AIppocampus bundle", file=target)
    print("  import              Import a portable AIppocampus bundle", file=target)
    print("  import conversation Register an explicit provider transcript", file=target)
    print("", file=target)
    print("Advanced/operator diagnostics:", file=target)
    print("  doctor provider     Check live-provider env visibility", file=target)
    print("  doctor config       Report registered env config without values", file=target)
    print("  doctor spend        Report local model spend/yield diagnostics", file=target)
    print("  mcp list-tools      List MCP tool schemas", file=target)
    print("  smoke recall-funnel Run a progressive recall funnel diagnostic", file=target)
    print("  observatory         Read-only route-readiness observatory report", file=target)
    print("  episode-arcs        Aggregate Episode/Arc private-history readout", file=target)
    print("  telepathy           Opt-in local handoff card lifecycle", file=target)
    print("  logs status/rotate  Inspect or apply bounded local log retention", file=target)
    print("  maintenance         Run bounded local maintenance", file=target)
    print("  warm status         Inspect warm ambient queue without model calls", file=target)
    print("  storage gc          Plan storage cleanup from existing evidence", file=target)
    print("  why-recall          Explain why a recall route surfaced or degraded", file=target)
    print("  why-not-recall      Explain why a recall route stayed silent", file=target)
    print("  sync                Local-folder sync status/push/pull/repair", file=target)
    print("  object-sync         Object-storage sync status/push/pull/repair", file=target)
    print("  plugin install      Install/verify the local Codex plugin", file=target)
    print(
        "  hooks [kind]        Host hook status/install/uninstall surfaces (prompt/lifecycle/action)",
        file=target,
    )
    print("", file=target)
    print("All commands run packaged entrypoints and preserve their output and exit code.", file=target)


if __name__ == "__main__":
    raise SystemExit(main())
