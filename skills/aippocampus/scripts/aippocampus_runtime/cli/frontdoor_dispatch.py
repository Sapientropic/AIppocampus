"""Top-level CLI help, chooser, and recovery-card dispatch."""

from __future__ import annotations

import contextlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO

from aippocampus_runtime.cli.chooser_accept import (
    accept_result_payload,
    accepted_action_from_payload,
    chooser_tail_supported,
    parse_chooser_tail,
)
from aippocampus_runtime.cli.command_registry import (
    COMMANDS,
    CommandInvocation,
    invocation_from_spec,
    module_name_for_script,
    resolve_command,
)
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
from aippocampus_runtime.cli.human_io import emit_json
from aippocampus_runtime.cli.recovery_cards import (
    hooks_chooser_payload,
    import_recovery_payload,
    logs_chooser_payload,
    object_sync_chooser_payload,
    plugin_chooser_payload,
    plugin_status_payload,
    smoke_chooser_payload,
    storage_chooser_payload,
    storage_gc_recovery_payload,
    sync_chooser_payload,
)
from aippocampus_runtime.cli.version_info import render_version_text, version_payload
from aippocampus_runtime.recall import background_findings

PLUGIN_STATUS_COMPACT_IGNORED_FLAGS = {"--no-child-check"}


@dataclass(frozen=True)
class FrontdoorDispatchResult:
    handled: bool
    invocation: CommandInvocation | None = None
    exit_code: int = 0

    @classmethod
    def unhandled(cls) -> FrontdoorDispatchResult:
        return cls(handled=False)


def _emit_chooser_accept(
    payload: dict[str, object],
    tail: list[str],
    *,
    run_invocation: Callable[[CommandInvocation], int],
) -> int:
    request = parse_chooser_tail(tail)
    accepted = accepted_action_from_payload(payload, action_id=request.action_id)
    if accepted.block_payload is not None:
        if request.json_output:
            emit_json(accepted.block_payload)
        else:
            print(f"AIppocampus chooser accept: {accepted.block_payload['status']}")
            print(f"reason: {accepted.block_payload['reason']}")
            requires = accepted.block_payload.get("requires") or []
            if requires:
                print(f"requires: {', '.join(str(item) for item in requires)}")
        return 2
    if accepted.invocation is None:
        return 2
    stdout = StringIO()
    stderr = StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = run_invocation(accepted.invocation)
    result = accept_result_payload(
        chooser_kind=str(payload.get("kind") or "aippocampus_chooser"),
        action=accepted.action,
        exit_code=code,
        stdout_text=stdout.getvalue(),
        stderr_text=stderr.getvalue(),
    )
    if request.json_output:
        emit_json(result)
    else:
        print(f"AIppocampus chooser accept: {result['status']}")
        print(f"action: {result.get('accepted_action_id')}")
        nested = result.get("result")
        if isinstance(nested, dict) and nested.get("stdout"):
            print(str(nested["stdout"]))
        elif nested is not None:
            print(json.dumps(nested, ensure_ascii=False, indent=2))
        if result.get("stderr"):
            print(str(result["stderr"]), file=sys.stderr)
    return 0 if code == 0 else code


def _emit_chooser_or_accept(
    title: str,
    payload: dict[str, object],
    tail: list[str],
    *,
    run_invocation: Callable[[CommandInvocation], int],
    human_printer: Callable[[], None] | None = None,
) -> FrontdoorDispatchResult:
    request = parse_chooser_tail(tail)
    if request.accept_requested:
        return FrontdoorDispatchResult(
            True,
            None,
            _emit_chooser_accept(
                payload,
                tail,
                run_invocation=run_invocation,
            ),
        )
    if request.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif human_printer is not None:
        human_printer()
    else:
        print_chooser_card(title, payload)
    return FrontdoorDispatchResult(True, None, 0)


def _print_sync_chooser_card() -> None:
    print("AIppocampus sync")
    print("decision: check status before push, pull, or object-store writes")
    print("next: aippocampus sync status --json")
    print("object-store: aippocampus object-sync status --json")
    print("boundary: sync writes are explicit operator actions.")


def _print_object_sync_chooser_card() -> None:
    print("AIppocampus object sync")
    print("decision: check object-store status before push, pull, or repair")
    print("next: aippocampus object-sync status --json")
    print("boundary: object-sync writes are explicit operator actions.")


def _print_smoke_chooser_card() -> None:
    print("AIppocampus smoke")
    print("decision: choose a bounded smoke runner")
    print('next: aippocampus smoke recall-funnel "old decision or handoff cue" --json')
    print('ordinary path: aippocampus agent recall "old decision or handoff cue" --json')
    print("boundary: smoke output is diagnostic, not source evidence.")


def _plugin_status_compact_tail(tail: list[str]) -> list[str] | None:
    if "--operator-json" in tail:
        return None
    compact_tail = [arg for arg in tail if arg not in PLUGIN_STATUS_COMPACT_IGNORED_FLAGS]
    return compact_tail if chooser_tail_supported(compact_tail) else None


def _dispatch_help_or_card(
    args: list[str],
    *,
    run_invocation: Callable[[CommandInvocation], int],
) -> FrontdoorDispatchResult:
    if not args:
        invocation = resolve_command(["start"])
        if invocation is not None:
            return FrontdoorDispatchResult(
                True,
                invocation,
                run_invocation(invocation),
            )
        print_help()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] in {"-h", "--help"}:
        print_help()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "version" and any(arg in {"-h", "--help"} for arg in args[1:]):
        print_version_help()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "status" and any(arg in {"-h", "--help"} for arg in args[1:]):
        print_status_help()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "config" and (
        len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])
    ):
        if any(arg in {"-h", "--help"} for arg in args[1:]):
            print_config_help()
            return FrontdoorDispatchResult(True, None, 0)
    if (
        len(args) >= 2
        and args[0] == "plugin"
        and args[1] == "status"
        and any(arg in {"-h", "--help"} for arg in args[2:])
    ):
        print_plugin_status_help()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] in {"setup", "install"} and (
        len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])
    ):
        print_first_run_setup_card(args[0])
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "memory" and (
        len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])
    ):
        print_memory_card()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "privacy" and (
        len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])
    ):
        print_privacy_card()
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "controls" and (
        len(args) == 1 or any(arg in {"-h", "--help"} for arg in args[1:])
    ):
        print_controls_card()
        return FrontdoorDispatchResult(True, None, 0)
    if len(args) >= 3 and args[:2] == ["plugin", "install"] and "--status" in args[2:]:
        print_plugin_status_help()
        return FrontdoorDispatchResult(True, None, 0)
    if len(args) >= 3 and args[:2] == ["repro", "package"] and any(
        arg in {"-h", "--help"} for arg in args[2:]
    ):
        print_repro_package_help()
        return FrontdoorDispatchResult(True, None, 0)
    return FrontdoorDispatchResult.unhandled()


def _dispatch_chooser(
    args: list[str],
    *,
    run_invocation: Callable[[CommandInvocation], int],
) -> FrontdoorDispatchResult:
    if len(args) >= 2 and args[:2] == ["plugin", "status"]:
        compact_tail = _plugin_status_compact_tail(args[2:])
        if compact_tail is None:
            return FrontdoorDispatchResult.unhandled()
        return _emit_chooser_or_accept(
            "AIppocampus plugin status",
            plugin_status_payload(),
            compact_tail,
            run_invocation=run_invocation,
        )
    if args[0] == "agent" and chooser_tail_supported(args[1:]):
        payload = agent_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus agent",
            payload,
            args[1:],
            run_invocation=run_invocation,
        )
    if args[0] == "warm" and chooser_tail_supported(args[1:]):
        payload = warm_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus warm ambient",
            payload,
            args[1:],
            run_invocation=run_invocation,
        )
    if args[0] == "memory" and chooser_tail_supported(args[1:]):
        return _emit_chooser_or_accept(
            "AIppocampus memory",
            memory_chooser_payload(),
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_memory_card,
        )
    if args[0] == "privacy" and chooser_tail_supported(args[1:]):
        return _emit_chooser_or_accept(
            "AIppocampus privacy",
            privacy_chooser_payload(),
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_privacy_card,
        )
    if args[0] == "controls" and chooser_tail_supported(args[1:]):
        payload = controls_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus controls",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_controls_card,
        )
    if args[0] == "plugin" and chooser_tail_supported(args[1:]):
        payload = plugin_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus plugin",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_plugin_status_help,
        )
    if args[0] == "hooks" and chooser_tail_supported(args[1:]):
        payload = hooks_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus hooks",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_hooks_help,
        )
    if args[0] == "sync" and chooser_tail_supported(args[1:]):
        payload = sync_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus sync",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=_print_sync_chooser_card,
        )
    if args[0] == "object-sync" and chooser_tail_supported(args[1:]):
        payload = object_sync_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus object sync",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=_print_object_sync_chooser_card,
        )
    if args[0] == "storage" and chooser_tail_supported(args[1:]):
        payload = storage_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus storage",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_storage_recovery_card,
        )
    if args[:2] == ["storage", "gc"] and chooser_tail_supported(args[2:]):
        if len(args) == 2 and getattr(sys.stdout, "isatty", lambda: False)():
            invocation = invocation_from_spec("storage", COMMANDS["storage"], ["gc", "--dry-run"])
            return FrontdoorDispatchResult(
                True,
                invocation,
                run_invocation(invocation),
            )
        payload = storage_gc_recovery_payload()
        return _emit_chooser_or_accept(
            "AIppocampus storage gc",
            payload,
            args[2:],
            run_invocation=run_invocation,
            human_printer=print_storage_recovery_card,
        )
    if args and args[0] == "import" and chooser_tail_supported(args[1:]):
        payload = import_recovery_payload()
        return _emit_chooser_or_accept(
            "AIppocampus import",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=print_import_recovery_card,
        )
    if args[0] == "smoke" and chooser_tail_supported(args[1:]):
        payload = smoke_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus smoke",
            payload,
            args[1:],
            run_invocation=run_invocation,
            human_printer=_print_smoke_chooser_card,
        )
    if args[0] == "logs" and chooser_tail_supported(args[1:]):
        payload = logs_chooser_payload()
        return _emit_chooser_or_accept(
            "AIppocampus logs",
            payload,
            args[1:],
            run_invocation=run_invocation,
        )
    return FrontdoorDispatchResult.unhandled()


def _dispatch_special(
    args: list[str],
    *,
    run_invocation: Callable[[CommandInvocation], int],
) -> FrontdoorDispatchResult:
    if args[0] in {"dream", "subconscious"} and set(args[1:]) <= {"--json"}:
        payload = background_findings.background_recovery_card(args[0])
        if "--json" in args[1:]:
            emit_json(payload)
        else:
            print("AIppocampus background findings")
            print("decision: use the foreground agent background route")
            print('template: aippocampus agent background "{task_cue}" --json')
            print("status: aippocampus dream status --json")
            print(
                "boundary: Dream/subconscious findings are navigation only "
                "until source is reopened."
            )
        return FrontdoorDispatchResult(True, None, 2)
    if args[0] == "doctor" and set(args[1:]) <= {"--json"}:
        invocation = CommandInvocation(
            "doctor",
            "provider_doctor.py",
            module_name_for_script("provider_doctor.py"),
            ["preflight", *(["--json"] if "--json" in args[1:] else [])],
        )
        return FrontdoorDispatchResult(True, invocation, run_invocation(invocation))
    if args[0] in {"--version", "-V", "version"}:
        payload = version_payload()
        if "--json" in args:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_version_text(payload))
        return FrontdoorDispatchResult(True, None, 0)
    if args[0] == "hooks" and hooks_help_request(args[1:]):
        print_hooks_help(hooks_help_kind(args[1:]))
        return FrontdoorDispatchResult(True, None, 0)
    return FrontdoorDispatchResult.unhandled()


def dispatch_frontdoor(
    args: list[str],
    *,
    run_invocation: Callable[[CommandInvocation], int],
) -> FrontdoorDispatchResult:
    """Handle command frontdoors that render cards or run fixed safe actions.

    The facade owns process capture and final unknown-command errors; this owner
    owns top-level human/agent affordances so new chooser branches do not keep
    accumulating inside the command runner.
    """

    for dispatcher in (_dispatch_help_or_card, _dispatch_chooser, _dispatch_special):
        result = dispatcher(args, run_invocation=run_invocation)
        if result.handled:
            return result
    return FrontdoorDispatchResult.unhandled()
