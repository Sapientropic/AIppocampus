"""CLI command registry and argv-to-owner resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
