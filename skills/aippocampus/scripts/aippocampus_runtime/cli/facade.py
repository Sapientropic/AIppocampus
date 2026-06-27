"""Unified AIppocampus command facade over packaged runtime entrypoints."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import json
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.cli.errors import cli_error_object
from aippocampus_runtime.cli.facade_help import (
    print_config_help,
    print_help,
    print_plugin_status_help,
    print_repro_package_help,
    print_status_help,
    print_version_help,
)
from aippocampus_runtime.cli.foreground_choosers import (
    agent_chooser_payload,
    controls_chooser_payload,
    memory_chooser_payload,
    print_chooser_card,
    privacy_chooser_payload,
    warm_chooser_payload,
)
from aippocampus_runtime.cli.frontdoor_cards import (
    print_controls_card,
    print_first_run_setup_card,
    print_import_recovery_card,
    print_memory_card,
    print_privacy_card,
    print_storage_recovery_card,
)
from aippocampus_runtime.cli.hooks_help import (
    hooks_help_kind,
    hooks_help_request,
    print_hooks_help,
)
from aippocampus_runtime.cli.human_io import emit_json, exit_code_for_payload
from aippocampus_runtime.cli.recovery import handle_module_exception
from aippocampus_runtime.cli.recovery_cards import (
    hooks_chooser_payload,
    import_recovery_payload,
    logs_chooser_payload,
    object_sync_chooser_payload,
    plugin_chooser_payload,
    smoke_chooser_payload,
    storage_chooser_payload,
    storage_gc_recovery_payload,
    sync_chooser_payload,
)
from aippocampus_runtime.cli.runtime_floor import (
    emit_python_runtime_floor,
    python_runtime_floor_payload,
)
from aippocampus_runtime.cli.version_info import render_version_text, version_payload
from aippocampus_runtime.recall import background_findings

SCRIPT_DIR = Path(__file__).resolve().parents[2]


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
    "pulse": CommandSpec("pulse.py", "aippocampus_runtime.cli.pulse"),
    "start": CommandSpec("start.py", "aippocampus_runtime.cli.start"),
    "status": CommandSpec("aippocampus_health.py", "aippocampus_runtime.health"),
    "onboard": CommandSpec("onboard.py", "aippocampus_runtime.onboarding.facade"),
    "search": CommandSpec("search_clean_source.py", "aippocampus_runtime.source.search"),
    "registry": CommandSpec("registry.py", "aippocampus_runtime.registry.api"),
    "agent": CommandSpec("agent_continuity.py", "aippocampus_runtime.recall.agent_continuity"),
    "export": CommandSpec("export_bundle.py", "aippocampus_runtime.artifacts.export_bundle"),
    "import": CommandSpec("import_bundle.py", "aippocampus_runtime.artifacts.import_bundle"),
    "doctor": CommandSpec("provider_doctor.py", "aippocampus_runtime.ops.provider_doctor"),
    "update": CommandSpec("update.py", "aippocampus_runtime.update.cli"),
    "plugin": CommandSpec("plugin.py", "aippocampus_runtime.update.plugin_installer"),
    "uninstall": CommandSpec("uninstall.py", "aippocampus_runtime.ops.uninstall"),
    "smoke": CommandSpec("recall_funnel_smoke.py", "aippocampus_runtime.ops.recall_funnel_smoke"),
    "logs": CommandSpec("log_retention.py", "aippocampus_runtime.ops.log_retention"),
    "maintenance": CommandSpec("maintenance.py", "aippocampus_runtime.ops.maintenance"),
    "warm": CommandSpec("warm_ambient_cli.py", "aippocampus_runtime.warm_ambient.cli"),
    "dream": CommandSpec("dream_frontdoor.py", "aippocampus_runtime.dream.frontdoor"),
    "subconscious": CommandSpec(
        "dream_frontdoor.py",
        "aippocampus_runtime.dream.frontdoor",
        prefix=("subconscious",),
    ),
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
    "vault": CommandSpec("vault_sync.py", "aippocampus_runtime.vault.sync"),
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
    "uninstall.py": "aippocampus_runtime.ops.uninstall",
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
    "action_hint.py": "aippocampus_runtime.hooks.action_hint",
    "action_hint_cache.py": "aippocampus_runtime.hooks.action_hint_cache",
    "aippocampus_claude_code_hooks.py": "aippocampus_runtime.hooks.claude_code",
    "start.py": "aippocampus_runtime.cli.start",
    "pulse.py": "aippocampus_runtime.cli.pulse",
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


def _system_exit_status(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


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
        stderr = StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                code = _coerce_exit_code(main_func(list(args)))
        except SystemExit as exc:
            if _system_exit_status(exc) == 0:
                print(stderr.getvalue(), end="", file=sys.stderr)
                return 0
            return handle_module_exception(
                script_name,
                args,
                exc,
                stderr_text=stderr.getvalue(),
            )
        except Exception as exc:
            return handle_module_exception(
                script_name,
                args,
                exc,
                stderr_text=stderr.getvalue(),
            )
        print(stderr.getvalue(), end="", file=sys.stderr)
        return code

    old_argv = sys.argv[:]
    sys.argv = [str(SCRIPT_DIR / script_name), *args]
    stderr = StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            code = _coerce_exit_code(main_func())
    except SystemExit as exc:
        if _system_exit_status(exc) == 0:
            print(stderr.getvalue(), end="", file=sys.stderr)
            return 0
        return handle_module_exception(
            script_name,
            args,
            exc,
            stderr_text=stderr.getvalue(),
        )
    except Exception as exc:
        return handle_module_exception(
            script_name,
            args,
            exc,
            stderr_text=stderr.getvalue(),
        )
    else:
        print(stderr.getvalue(), end="", file=sys.stderr)
        return code
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
    if command == "vault":
        if not rest:
            rest = ["--help"]
        elif rest[0] == "sync":
            rest = rest[1:] or ["--help"]
        return invocation_from_spec(command, COMMANDS[command], rest)
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
        if hook_kind == "action" and hook_args and hook_args[0] == "probe":
            return CommandInvocation(
                command,
                "action_hint.py",
                module_name_for_script("action_hint.py"),
                ["probe", *hook_args[1:]],
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
    if (runtime_floor := python_runtime_floor_payload()) is not None:
        emit_python_runtime_floor(runtime_floor, args)
        return None, 2
    if not args:
        invocation = resolve_command(["start"])
        if invocation is not None:
            return invocation, run_invocation(invocation)
        print_help()
        return None, 0
    if args[0] in {"-h", "--help"}:
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
    if args[0] == "agent" and set(args[1:]) <= {"--json"}:
        payload = agent_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_chooser_card("AIppocampus agent", payload)
        return None, 0
    if args[0] in {"dream", "subconscious"} and set(args[1:]) <= {"--json"}:
        payload = background_findings.background_recovery_card(args[0])
        if "--json" in args[1:]:
            emit_json(payload)
        else:
            print("AIppocampus background findings")
            print("decision: use the foreground agent background route")
            print('template: aippocampus agent background "{task_cue}" --json\nstatus: aippocampus dream status --json\nboundary: Dream/subconscious findings are navigation only until source is reopened.')
        return None, 2
    if args[0] == "warm" and set(args[1:]) <= {"--json"}:
        payload = warm_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_chooser_card("AIppocampus warm ambient", payload)
        return None, 0
    if args[0] == "memory" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        print_memory_card()
        return None, 0
    if args[0] == "memory" and set(args[1:]) <= {"--json"}:
        print(json.dumps(memory_chooser_payload(), ensure_ascii=False, indent=2))
        return None, 0
    if args[0] == "privacy" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        print_privacy_card()
        return None, 0
    if args[0] == "privacy" and set(args[1:]) <= {"--json"}:
        print(json.dumps(privacy_chooser_payload(), ensure_ascii=False, indent=2))
        return None, 0
    if args[0] == "controls" and set(args[1:]) <= {"--json"}:
        payload = controls_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_controls_card()
        return None, 0
    if args[0] == "controls" and (len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])):
        print_controls_card()
        return None, 0
    if args[0] == "plugin" and set(args[1:]) <= {"--json"}:
        payload = plugin_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_plugin_status_help()
        return None, 0
    if args[0] == "hooks" and set(args[1:]) <= {"--json"}:
        payload = hooks_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_hooks_help()
        return None, 0
    if args[0] == "sync" and set(args[1:]) <= {"--json"}:
        payload = sync_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("AIppocampus sync")
            print("decision: check status before push, pull, or object-store writes")
            print("next: aippocampus sync status --json")
            print("object-store: aippocampus object-sync status --json")
            print("boundary: sync writes are explicit operator actions.")
        return None, 0
    if args[0] == "object-sync" and set(args[1:]) <= {"--json"}:
        payload = object_sync_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("AIppocampus object sync")
            print("decision: check object-store status before push, pull, or repair")
            print("next: aippocampus object-sync status --json")
            print("boundary: object-sync writes are explicit operator actions.")
        return None, 0
    if len(args) >= 3 and args[:2] == ["plugin", "install"] and "--status" in args[2:]:
        print_plugin_status_help()
        return None, 0
    if args[0] == "storage" and set(args[1:]) <= {"--json"}:
        payload = storage_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_storage_recovery_card()
        return None, 0
    if args[:2] == ["storage", "gc"] and set(args[2:]) <= {"--json"}:
        payload = storage_gc_recovery_payload()
        if "--json" in args[2:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_storage_recovery_card()
        return None, 0
    if args and args[0] == "import" and set(args[1:]) <= {"--json"}:
        payload = import_recovery_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_import_recovery_card()
        return None, 0
    if len(args) >= 3 and args[:2] == ["repro", "package"] and any(
        arg in {"-h", "--help"} for arg in args[2:]
    ):
        print_repro_package_help()
        return None, 0
    if args[0] == "doctor" and set(args[1:]) <= {"--json"}:
        invocation = CommandInvocation(
            "doctor",
            "provider_doctor.py",
            module_name_for_script("provider_doctor.py"),
            ["preflight", *(["--json"] if "--json" in args[1:] else [])],
        )
        return invocation, run_invocation(invocation)
    if args[0] == "smoke" and set(args[1:]) <= {"--json"}:
        payload = smoke_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("AIppocampus smoke")
            print("decision: choose a bounded smoke runner")
            print('next: aippocampus smoke recall-funnel "old decision or handoff cue" --json')
            print("ordinary path: aippocampus agent recall \"old decision or handoff cue\" --json")
            print("boundary: smoke output is diagnostic, not source evidence.")
        return None, 0
    if args[0] == "logs" and set(args[1:]) <= {"--json"}:
        payload = logs_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_chooser_card("AIppocampus logs", payload)
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

    if "--json" in args:
        payload = {
            "kind": "aippocampus_cli_error",
            "ok": False,
            "error": cli_error_object(
                "unsupported_operation",
                f"unknown command: {args[0]}",
            ),
            "safe_next_actions": [
                {
                    "id": "show_help",
                    "label": "Show AIppocampus commands",
                    "command": "aippocampus --help",
                    "mutation_risk": "read_only",
                }
            ],
        }
        emit_json(payload)
        return None, exit_code_for_payload(payload)
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


if __name__ == "__main__":
    raise SystemExit(main())
