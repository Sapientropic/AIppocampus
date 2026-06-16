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


def print_version_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus version [--json]", file=target)
    print("", file=target)
    print("Show the active AIppocampus runtime and release metadata version.", file=target)
    print("Use --json for a bounded machine-readable version/source summary.", file=target)


def print_config_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus config [--json|--compact-json]", file=target)
    print("", file=target)
    print("Config recovery card:", file=target)
    print("  Values are never printed; configured values are reported as presence only.", file=target)
    print("  This is the natural shortcut to the safe config doctor, not a second config source.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus config", file=target)
    print("  aippocampus config --compact-json", file=target)
    print("  aippocampus doctor config --json", file=target)


def print_storage_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus storage", file=target)
    print("decision: choose an explicit storage action", file=target)
    print("why: bare storage should not dump a long cleanup candidate list.", file=target)
    print("next: aippocampus storage gc --dry-run --json", file=target)
    print("apply: aippocampus storage gc --apply --i-understand-this-deletes-data", file=target)
    print("boundary: cleanup is explicit operator work; dry-run before apply.", file=target)


def print_import_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus import", file=target)
    print("decision: choose bundle import or transcript registration", file=target)
    print("next: aippocampus import <bundle.zip> --dest <folder>", file=target)
    print(
        "transcript: aippocampus import conversation --format generic-jsonl --input <file> --dry-run --json",
        file=target,
    )
    print("boundary: preview transcript imports before registering new source.", file=target)


def print_doctor_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus doctor", file=target)
    print("decision: pick the health question first", file=target)
    print("provider: aippocampus doctor provider --json", file=target)
    print("config: aippocampus doctor config --compact-json", file=target)
    print("spend: aippocampus doctor spend --json", file=target)
    print("boundary: doctor output is local diagnostics, not a recall result.", file=target)


def print_status_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus health [--json|--agent-json]", file=target)
    print("alias: aippocampus status [--json|--agent-json]", file=target)
    print("", file=target)
    print("Status decision card:", file=target)
    print("  Use health when you need one-screen readiness and a next action.", file=target)
    print("  Use update status when checking installed skill/plugin/hook freshness.", file=target)
    print("  Use operator diagnostics only when repairing local artifacts.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus status", file=target)
    print("  aippocampus health --agent-json", file=target)
    print("  aippocampus update status --agent-json", file=target)


def print_plugin_status_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus plugin status [--agent-json|--json]", file=target)
    print("", file=target)
    print("Plugin status readiness card:", file=target)
    print("  Checks whether the local Codex plugin package/cache and host-visible tools look fresh.", file=target)
    print("  It is a plugin-shaped shortcut to update status, not a plugin install or hook enablement command.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus plugin status --agent-json", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("  aippocampus update status --agent-json", file=target)


def print_first_run_setup_card(kind: str, *, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    title = "First-run install card" if kind == "install" else "First-run setup card"
    print(f"AIppocampus {kind}", file=target)
    print(title + ":", file=target)
    print("  Goal: make the local Codex/CLI surface callable, then see one source-backed recall/search result.", file=target)
    print("", file=target)
    print("Ordinary Codex path:", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("  aippocampus update status --agent-json", file=target)
    print('  aippocampus agent recall "old decision or handoff cue" --json', file=target)
    print("", file=target)
    print("No installed command yet:", file=target)
    print("  uvx aippocampus --help", file=target)
    print("  uvx aippocampus onboard --provider auto --status", file=target)
    print("", file=target)
    print("Boundary: setup does not copy private memory, enable hooks, or configure provider keys unless you run those explicit commands.", file=target)


def print_memory_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus memory", file=target)
    print("Memory action card:", file=target)
    print("  Use source-backed recall/search for facts; use self-notes only as weak direction.", file=target)
    print("", file=target)
    print("Recall/search:", file=target)
    print('  aippocampus agent recall "old decision or handoff cue" --json', file=target)
    print('  aippocampus search "exact phrase" --json', file=target)
    print("  aippocampus latest-reply --cwd .", file=target)
    print("", file=target)
    print("Weak or route-only lanes:", file=target)
    print("  aippocampus self-note list --json", file=target)
    print("  aippocampus continuity-domain latest --json", file=target)
    print("Boundary: reopen/deepen clean source before quoting or making source-backed claims.", file=target)


def print_privacy_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus privacy", file=target)
    print("Privacy and control card:", file=target)
    print("  Defaults are read-only and redacted; destructive or private-path output is explicit operator work.", file=target)
    print("", file=target)
    print("Controls:", file=target)
    print("  aippocampus pause --help", file=target)
    print("  aippocampus forget --help", file=target)
    print("  aippocampus do-not-use-here --help", file=target)
    print("", file=target)
    print("Portability and credentials:", file=target)
    print("  aippocampus export --help", file=target)
    print("  aippocampus import --help", file=target)
    print("  aippocampus provider-key --help", file=target)
    print("Boundary: provider keys are optional; AIppocampus should still have a no-key source-backed path.", file=target)


def print_controls_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus controls", file=target)
    print("Personal controls card:", file=target)
    print("  Use these when you want less memory influence, narrower scope, or a route disabled here.", file=target)
    print("", file=target)
    print("Commands:", file=target)
    print("  aippocampus pause --help", file=target)
    print("  aippocampus forget --help", file=target)
    print("  aippocampus do-not-use-here --help", file=target)
    print("", file=target)
    print("Boundary: control commands do not delete private history by surprise; deletion/cleanup stays explicit.", file=target)


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
    "status": CommandSpec("aippocampus_health.py", "aippocampus_runtime.health"),
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
    "why-not": CommandSpec(
        "why_recall.py",
        "aippocampus_runtime.recall.why_cli",
        prefix=("why-not",),
    ),
    "learning": CommandSpec("learning.py", "aippocampus_runtime.learning_loop.cli"),
    "questions": CommandSpec("questions.py", "aippocampus_runtime.question.frontdoor"),
    "pause": CommandSpec("controls.py", "aippocampus_runtime.controls", prefix=("pause",)),
    "forget": CommandSpec("controls.py", "aippocampus_runtime.controls", prefix=("forget",)),
    "do-not-use-here": CommandSpec(
        "controls.py",
        "aippocampus_runtime.controls",
        prefix=("do-not-use-here",),
    ),
    "self-note": CommandSpec(
        "agent_self_note_cli.py",
        "aippocampus_runtime.source.agent_self_note_cli",
    ),
    "latest-reply": CommandSpec(
        "latest_reply.py",
        "aippocampus_runtime.source.latest_reply",
    ),
    "last-reply": CommandSpec(
        "latest_reply.py",
        "aippocampus_runtime.source.latest_reply",
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
    "navigate": CommandSpec("navigate.py", "aippocampus_runtime.navigation.frontdoor"),
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
    "latest_reply.py": "aippocampus_runtime.source.latest_reply",
    "issue_work_guard.py": "aippocampus_runtime.ops.issue_work_guard",
    "telepathy_handoff_store.py": "aippocampus_runtime.ops.telepathy_handoff_store",
    "agent_continuity.py": "aippocampus_runtime.recall.agent_continuity",
    "storage_governance.py": "aippocampus_runtime.ops.storage_governance",
    "install_aippocampus_prompt_hook.py": "aippocampus_runtime.hooks.install_prompt",
    "install_aippocampus_lifecycle_hook.py": "aippocampus_runtime.hooks.install_lifecycle",
    "install_aippocampus_action_hint_hook.py": "aippocampus_runtime.hooks.install_action_hint",
    "action_hint_cache.py": "aippocampus_runtime.hooks.action_hint_cache",
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
    if command in {"recall", "deepen", "explain", "feedback", "aippo", "macro"}:
        return invocation_from_spec("agent", COMMANDS["agent"], [command, *rest])
    if command == "provider-key":
        return CommandInvocation(
            command,
            "onboard.py",
            module_name_for_script("onboard.py"),
            ["provider-key", *rest],
        )
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
    if command == "repro":
        repro_args = rest[1:] if rest and rest[0] == "package" else rest
        return CommandInvocation(
            command,
            "learning.py",
            module_name_for_script("learning.py"),
            ["repro-package", *repro_args],
        )
    if command == "config":
        return CommandInvocation(
            command,
            "provider_doctor.py",
            module_name_for_script("provider_doctor.py"),
            ["config", *rest],
        )
    if command in COMMANDS:
        if command == "agent" and not rest:
            return invocation_from_spec(command, COMMANDS[command], ["--help"])
        if command == "logs" and not rest:
            return invocation_from_spec(command, COMMANDS[command], ["status"])
        if command == "storage" and not rest:
            return invocation_from_spec(command, COMMANDS[command], ["--help"])
        if command == "warm" and not rest:
            return invocation_from_spec(command, COMMANDS[command], ["status"])
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
        if not rest:
            rest = ["status"]
        return CommandInvocation(
            command,
            "sync_bundle.py",
            module_name_for_script("sync_bundle.py"),
            rest,
        )
    if command == "object-sync":
        if not rest:
            rest = ["--help"]
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
        if hook_kind == "action" and hook_args and hook_args[0] == "refresh-cache":
            return CommandInvocation(
                command,
                "action_hint_cache.py",
                module_name_for_script("action_hint_cache.py"),
                ["refresh-cache", *hook_args[1:]],
            )
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
    if args[0] == "version" and any(arg in {"-h", "--help"} for arg in args[1:]):
        print_version_help()
        return None, 0
    if args[0] == "status" and any(arg in {"-h", "--help"} for arg in args[1:]):
        print_status_help()
        return None, 0
    if args[0] == "config" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        if any(arg in {"-h", "--help"} for arg in args[1:]):
            print_config_help()
            return None, 0
    if (
        len(args) >= 2
        and args[0] == "plugin"
        and args[1] == "status"
        and any(arg in {"-h", "--help"} for arg in args[2:])
    ):
        print_plugin_status_help()
        return None, 0
    if args[0] in {"setup", "install"} and (
        len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])
    ):
        print_first_run_setup_card(args[0])
        return None, 0
    if args[0] == "memory" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        print_memory_card()
        return None, 0
    if args[0] == "privacy" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        print_privacy_card()
        return None, 0
    if args[0] == "controls" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        print_controls_card()
        return None, 0
    if len(args) >= 3 and args[:2] == ["plugin", "install"] and "--status" in args[2:]:
        print_plugin_status_help()
        return None, 0
    if args == ["storage"]:
        print_storage_recovery_card()
        return None, 0
    if args == ["import"]:
        print_import_recovery_card()
        return None, 0
    if args == ["doctor"]:
        print_doctor_recovery_card()
        return None, 0
    if args[0] in {"--version", "-V", "version"}:
        payload = version_payload()
        if "--json" in args:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_version_text(payload))
        return None, 0
    if args[0] == "hooks" and hooks_help_request(args[1:]):
        print_hooks_help(hooks_help_kind(args[1:]))
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


def hooks_help_request(args: list[str]) -> bool:
    if args in (["--help"], ["-h"]):
        return True
    return (
        bool(args)
        and args[0] in {"prompt", "lifecycle", "action", "claude-code"}
        and any(arg in {"--help", "-h"} for arg in args[1:])
    )


def hooks_help_kind(args: list[str]) -> str | None:
    if len(args) >= 3 and args[0] == "action" and args[1] == "refresh-cache":
        return "action-refresh-cache"
    if len(args) >= 3 and args[0] in {"prompt", "lifecycle", "action"} and args[1] in {
        "install",
        "uninstall",
    }:
        return f"{args[0]}-{args[1]}"
    if len(args) >= 2 and args[0] in {"prompt", "lifecycle", "action", "claude-code"}:
        return args[0]
    return None


def print_hooks_help(kind: str | None = None, *, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    if kind == "prompt-install":
        print("usage: aippocampus hooks prompt install [options]", file=target)
        print("", file=target)
        print("Prompt hook install boundary:", file=target)
        print("  Writes/merges the Codex UserPromptSubmit hook entry for ambient recall.", file=target)
        print("  Does not install provider keys, rewrite transcripts, or enable heavy maintenance.", file=target)
        print("  The hook reads the current prompt and emits only a small route/action hint when useful.", file=target)
        print("", file=target)
        print("Before/after:", file=target)
        print("  aippocampus hooks prompt status --last", file=target)
        print("  aippocampus hooks prompt install --json", file=target)
        print("  aippocampus hooks prompt uninstall --json", file=target)
        print("  Ordinary recall still works without this hook: aippocampus agent recall \"old cue\" --json", file=target)
        return
    if kind == "prompt-uninstall":
        print("usage: aippocampus hooks prompt uninstall [options]", file=target)
        print("", file=target)
        print("Prompt hook rollback boundary:", file=target)
        print("  Removes the AIppocampus UserPromptSubmit hook entry from Codex hook config.", file=target)
        print("  Does not delete clean source, indexes, registry data, or provider configuration.", file=target)
        print("", file=target)
        print("Check:", file=target)
        print("  aippocampus hooks prompt status --last", file=target)
        print("  aippocampus hooks prompt uninstall --json", file=target)
        return
    if kind == "lifecycle-install":
        print("usage: aippocampus hooks lifecycle install [options]", file=target)
        print("", file=target)
        print("Lifecycle hook install boundary:", file=target)
        print("  Writes/merges Codex session lifecycle hooks for bounded local maintenance.", file=target)
        print("  Does not cold-archive, delete, run full Graphify, or install provider keys.", file=target)
        print("  Runtime work is limited to start/stop/compact upkeep such as clean source and indexes.", file=target)
        print("", file=target)
        print("Before/after:", file=target)
        print("  aippocampus hooks lifecycle status --json", file=target)
        print("  aippocampus hooks lifecycle install --json", file=target)
        print("  aippocampus hooks lifecycle uninstall --json", file=target)
        return
    if kind == "lifecycle-uninstall":
        print("usage: aippocampus hooks lifecycle uninstall [options]", file=target)
        print("", file=target)
        print("Lifecycle hook rollback boundary:", file=target)
        print("  Removes AIppocampus lifecycle hook entries from Codex hook config.", file=target)
        print("  Does not delete generated memory artifacts or source registries.", file=target)
        print("", file=target)
        print("Check:", file=target)
        print("  aippocampus hooks lifecycle status --json", file=target)
        print("  aippocampus hooks lifecycle uninstall --json", file=target)
        return
    if kind == "action-install":
        print("usage: aippocampus hooks action install [--cache-jsonl PATH] [options]", file=target)
        print("", file=target)
        print("Action-time hook install boundary:", file=target)
        print("  Writes/merges the optional Codex PreToolUse action-hint hook entry.", file=target)
        print("  Reads a prepared public-safe hint cache; it does not mine private history at tool time.", file=target)
        print("  Default cache: .aippocampus/action-hints/pretooluse-cache.jsonl", file=target)
        print("  Prepare or refresh the cache first when status says it is missing/stale.", file=target)
        print("", file=target)
        print("Before/after:", file=target)
        print("  aippocampus hooks action status --json", file=target)
        print("  aippocampus hooks action refresh-cache --write --json", file=target)
        print("  aippocampus hooks action install --json", file=target)
        print("  aippocampus hooks action uninstall --json", file=target)
        return
    if kind == "action-uninstall":
        print("usage: aippocampus hooks action uninstall [options]", file=target)
        print("", file=target)
        print("Action-time hook rollback boundary:", file=target)
        print("  Removes the AIppocampus PreToolUse action-hint hook entry.", file=target)
        print("  Does not delete the prepared hint cache or recall registry.", file=target)
        print("", file=target)
        print("Check:", file=target)
        print("  aippocampus hooks action status --json", file=target)
        print("  aippocampus hooks action uninstall --json", file=target)
        return
    if kind == "prompt":
        print("usage: aippocampus hooks prompt [status|install|uninstall] [options]", file=target)
        print("", file=target)
        print("Prompt hook: Codex UserPromptSubmit ambient recall affordances.", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks prompt status --last", file=target)
        print("  aippocampus hooks prompt install --json", file=target)
        print("  aippocampus hooks prompt uninstall --json", file=target)
        return
    if kind == "lifecycle":
        print("usage: aippocampus hooks lifecycle [status|install|uninstall] [options]", file=target)
        print("", file=target)
        print("Lifecycle hooks: Codex session maintenance on start/stop/compact events.", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks lifecycle status --json", file=target)
        print("  aippocampus hooks lifecycle install --json", file=target)
        print("  aippocampus hooks lifecycle uninstall --json", file=target)
        return
    if kind == "action":
        print("usage: aippocampus hooks action [status|install|uninstall|refresh-cache] [options]", file=target)
        print("", file=target)
        print("Action-time hints: optional PreToolUse nudges backed by a prepared cache.", file=target)
        print("Default cache: .aippocampus/action-hints/pretooluse-cache.jsonl", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks action status --json", file=target)
        print("  aippocampus hooks action refresh-cache --write --json", file=target)
        print("  aippocampus hooks action install --json", file=target)
        print("  aippocampus hooks action uninstall --json", file=target)
        return
    if kind == "action-refresh-cache":
        print(
            "usage: aippocampus hooks action refresh-cache [--cache-jsonl PATH] [--write] [--json]",
            file=target,
        )
        print("", file=target)
        print("Refresh the optional action-time hint cache from public-safe learning findings.", file=target)
        print("Default cache: .aippocampus/action-hints/pretooluse-cache.jsonl", file=target)
        print("Default is a dry run; add --write to update the local cache.", file=target)
        print("", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks action refresh-cache --json", file=target)
        print("  aippocampus hooks action refresh-cache --write --json", file=target)
        return
    if kind == "claude-code":
        print("usage: aippocampus hooks claude-code [status|dry-run] [options]", file=target)
        print("", file=target)
        print("Claude Code hook helper: host-specific status/dry-run, not Codex hook install.", file=target)
        print("Common:", file=target)
        print("  aippocampus hooks claude-code status --json", file=target)
        print("  aippocampus hooks claude-code dry-run --json", file=target)
        return
    print("usage: aippocampus hooks [prompt|lifecycle|action|claude-code] ...", file=target)
    print("", file=target)
    print("Hook families:", file=target)
    print("  prompt       Codex UserPromptSubmit recall affordance hook", file=target)
    print("  lifecycle    Codex session maintenance hooks", file=target)
    print("  action       Optional PreToolUse action-time hints and cache refresh", file=target)
    print("  claude-code  Host-specific Claude Code hook status/dry-run helper", file=target)
    print("", file=target)
    print("Examples:", file=target)
    print("  aippocampus hooks prompt status --last", file=target)
    print("  aippocampus hooks lifecycle status --json", file=target)
    print("  aippocampus hooks action status --json", file=target)
    print("  aippocampus hooks action refresh-cache --write --json", file=target)


def print_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    parser = argparse.ArgumentParser(
        prog="aippocampus",
        description="Unified facade for AIppocampus personal and operator commands.",
        add_help=False,
    )
    parser.print_usage(target)
    print("", file=target)
    print("Start here:", file=target)
    print("  aippocampus search \"exact phrase\"      Find a remembered source snippet", file=target)
    print("  aippocampus agent recall \"old cue\" --json", file=target)
    print("                                        Continue old work from source routes", file=target)
    print("  aippocampus agent deepen --request 1 --last-recall --json", file=target)
    print("                                        Reopen the selected route before claims", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("                                        Local Codex plugin install/refresh", file=target)
    print("", file=target)
    print("Recovery/readiness:", file=target)
    print("  aippocampus health                    Use when source is missing/stale, host tools feel", file=target)
    print("                                        installed-but-not-alive, or maintenance pressure matters", file=target)
    print("", file=target)
    print("Commands:", file=target)
    print("", file=target)
    print("Personal path:", file=target)
    print("  health              Run runtime health checks", file=target)
    print("  version             Show active runtime and release metadata version", file=target)
    print("  onboard             Check/register provider-backed clean source", file=target)
    print("  search              Search clean-source memory", file=target)
    print("  agent recall        Opt-in agent recall/AIppo/deepen/explain path", file=target)
    print("  learning            Source-backed learning loop status/replay/guidance", file=target)
    print("  repro package       Public-safe command/output issue package", file=target)
    print("  do-not-use-here     Quiet a route or ticket through low-authority feedback", file=target)
    print("  pause / forget      Safe personal-control cards, no destructive defaults", file=target)
    print("  latest-reply        Latest final assistant closeout, not commentary", file=target)
    print("  self-note append    Add a voluntary foreground-agent margin note", file=target)
    print("  continuity-domain   Explicitly produce/append source-trailed domains", file=target)
    print("  questions status    Read source-backed question tracking status", file=target)
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
    print("  mcp status          Compact MCP tool readiness", file=target)
    print("  mcp list-tools      List full MCP tool schemas", file=target)
    print("  smoke recall-funnel Run a progressive recall funnel diagnostic", file=target)
    print("  observatory         Read-only route-readiness observatory report", file=target)
    print("  episode-arcs        Aggregate Episode/Arc private-history readout", file=target)
    print("  navigate            Boundary card for navigation sidecars", file=target)
    print("  telepathy           Opt-in local handoff card lifecycle", file=target)
    print("  logs status/rotate  Inspect or apply bounded local log retention", file=target)
    print("  maintenance         Run bounded local maintenance", file=target)
    print("  warm status         Inspect warm ambient queue without model calls", file=target)
    print("  storage gc          Plan storage cleanup from existing evidence", file=target)
    print("  why-recall          Explain why a recall route surfaced or degraded", file=target)
    print("  why-not             Alias for why-not-recall", file=target)
    print("  why-not-recall      Explain why a recall route stayed silent", file=target)
    print("  sync                Local-folder sync status/push/pull/repair", file=target)
    print("  object-sync         Object-storage sync status/push/pull/repair", file=target)
    print("  plugin install      Install/verify the local Codex plugin", file=target)
    print(
        "  hooks [kind]        Host hook status/install/uninstall surfaces (prompt/lifecycle/action)",
        file=target,
    )
    print(
        "  hooks action refresh-cache  Materialize prepared action hints for the hot hook",
        file=target,
    )
    print("", file=target)
    print("All commands run packaged entrypoints and preserve their output and exit code.", file=target)


if __name__ == "__main__":
    raise SystemExit(main())
