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

from aippocampus_runtime.contracts import (
    foreground_chooser_card,
    foreground_shell_action,
)
from aippocampus_runtime.cli.recovery_cards import (
    object_sync_chooser_payload,
    storage_chooser_payload,
    storage_gc_recovery_payload,
)
from aippocampus_runtime.recall import background_findings

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
    print("next: aippocampus storage gc --dry-run --summary-json --cwd .", file=target)
    print("audit: aippocampus storage gc --dry-run --json --top 1 --cwd .", file=target)
    print("apply: aippocampus storage gc --apply --class rebuildable --summary-json --cwd .", file=target)
    print("boundary: cleanup is explicit operator work; dry-run before apply.", file=target)


def print_import_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus import", file=target)
    print("decision: choose bundle import or transcript registration", file=target)
    print("bundle: aippocampus import <bundle.zip> --dest <folder>", file=target)
    print(
        "transcript: aippocampus import conversation --format generic-jsonl --input <file> --dry-run --json",
        file=target,
    )
    print(
        "boundary: no write happens from the bare chooser; preview transcript imports before registering new source.",
        file=target,
    )


def import_recovery_payload() -> dict[str, Any]:
    return {
        "kind": "aippocampus_import_recovery",
        "ok": False,
        "error": {
            "code": "import_choice_required",
            "message": "Choose a private AIppocampus bundle import or a preview-first conversation import.",
        },
        "choices": {
            "bundle_import": {
                "label": "private AIppocampus bundle import",
                "command_template": "aippocampus import {bundle_zip} --dest {destination_folder}",
                "requires": ["bundle_zip", "destination_folder"],
                "boundary": "imports an explicit local AIppocampus bundle; paths stay redacted by default",
            },
            "conversation_import": {
                "label": "generic conversation transcript import",
                "preview_command_template": (
                    "aippocampus import conversation --format generic-jsonl --input {input_path} --dry-run --json"
                ),
                "write_command_template": (
                    "aippocampus import conversation --format generic-jsonl --input {input_path}"
                ),
                "requires": ["input_path"],
                "boundary": "preview first; the input transcript stays local operator material",
            },
        },
        "agent_next_action": (
            "Preview conversation imports with --dry-run --json before any registry write; "
            "pass an explicit bundle path for private AIppocampus bundle transfer."
        ),
        "safety": {
            "no_write_happened": True,
            "preview_before_write": True,
            "explicit_input_required": True,
        },
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
        },
        "privacy_boundary": {
            "raw_local_paths_emitted": False,
            "local_path_redaction_required": True,
            "private_transcript_material_loaded": False,
        },
    }


def plugin_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_plugin_chooser",
        decision="choose plugin status, verify, or install",
        choices=[
            foreground_shell_action(
                action_id="install_or_refresh_codex_plugin",
                label="Install or refresh Codex plugin",
                command="aippocampus plugin install --codex --verify --json",
                why="This is the ordinary Codex setup path and verifies host-visible tools after refresh.",
                mutation_risk="explicit_local_plugin_write",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_codex_plugin_status",
                label="Check Codex plugin status",
                command="aippocampus plugin status --json",
                why="Read current freshness/callability without changing local plugin files.",
                mutation_risk="read_only",
                claim_boundary="host_status_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="preview_codex_plugin_uninstall",
                label="Preview explicit rollback",
                command="aippocampus plugin uninstall --codex --dry-run --json",
                why="Rollback stays preview-first and should not be confused with setup.",
                mutation_risk="read_only_preview_of_delete",
                claim_boundary="host_setup_not_memory_evidence",
            ),
        ],
    )


def hooks_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_hooks_chooser",
        decision="choose a hook family before checking, installing, or rolling back",
        choices=[
            foreground_shell_action(
                action_id="check_prompt_hook",
                label="Check prompt hook",
                command="aippocampus hooks prompt status --last --json",
                why="Prompt hooks are the Codex UserPromptSubmit recall affordance, not the whole hook family.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_lifecycle_hooks",
                label="Check lifecycle hooks",
                command="aippocampus hooks lifecycle status --json",
                why="Lifecycle hooks cover bounded start/stop/compact maintenance.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_action_hints",
                label="Check action-time hints",
                command="aippocampus hooks action status --json",
                why="Action-time hints are recommended trusted-Codex setup, but remain fail-open navigation guidance.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_claude_code_hooks",
                label="Check Claude Code hook helper",
                command="aippocampus hooks claude-code status --json",
                why="Claude Code has a host-specific status/dry-run helper rather than Codex hook installation.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
        ],
    )


def sync_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_sync_chooser",
        decision="choose a read-only sync status before push or pull",
        choices=[
            foreground_shell_action(
                action_id="check_sync_status",
                label="Check local sync status",
                command="aippocampus sync status --json",
                why="Parent sync commands should not imply push/pull or object-store writes.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="check_object_sync_status",
                label="Check object sync status",
                command="aippocampus object-sync status --json",
                why="Use this when an object-storage backend is involved.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def print_doctor_recovery_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus doctor", file=target)
    print("decision: pick the health question first", file=target)
    print("provider: aippocampus doctor provider --json", file=target)
    print("config: aippocampus doctor config --compact-json", file=target)
    print("spend: aippocampus doctor spend --json", file=target)
    print("boundary: doctor output is local diagnostics, not a recall result.", file=target)


def doctor_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_doctor_chooser",
        status="needs_subcommand",
        decision="choose the local diagnostic question",
        choices=[
            foreground_shell_action(
                action_id="provider",
                label="Check optional provider visibility",
                command="aippocampus doctor provider --json",
                why="Use when model/provider key visibility or semantic-worker availability is the question.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="spend",
                label="Review spend/yield diagnostics",
                command="aippocampus doctor spend --json",
                why="Use when local model spend, yield, or blocked warm work needs review.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="config",
                label="Audit registered configuration",
                command="aippocampus doctor config --compact-json",
                why="Use when checking configured AIPPOCAMPUS_* knobs without printing values.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def smoke_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_smoke_chooser",
        status="needs_subcommand",
        decision="choose a bounded smoke runner",
        choices=[
            _template_action(
                action_id="recall_funnel",
                label="Run progressive recall funnel smoke",
                command_template='aippocampus smoke recall-funnel "{cue}" --json',
                requires="cue",
                why="Use for a bounded diagnostic of recall_context -> deepen flow.",
                mutation_risk="read_only",
                claim_boundary="smoke_diagnostic_not_source_evidence",
            ),
            _template_action(
                action_id="ordinary_agent_recall",
                label="Use ordinary continuity path",
                command_template='aippocampus agent recall "{cue}" --json',
                requires="cue",
                why="Use for normal foreground continuity work instead of a smoke diagnostic.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
    )


def logs_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_logs_chooser",
        status="needs_subcommand",
        decision="inspect log status before rotating local audit artifacts",
        choices=[
            foreground_shell_action(
                action_id="status",
                label="Inspect log retention status",
                command="aippocampus logs status --json",
                why="Read-only status never prints log contents.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="rotate_dry_run",
                label="Preview bounded rotation",
                command="aippocampus logs rotate --plan --json",
                why="Use before any write to see which known artifacts would rotate.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="rotate_apply",
                label="Apply bounded rotation explicitly",
                command="aippocampus logs rotate --apply --json",
                why="Write mode is explicit and should only follow a reviewed plan.",
                mutation_risk="explicit_local_log_write",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def print_repro_package_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus repro package [-h] [--input-json INPUT_JSON]", file=target)
    print("                                  [--stdin] [--template]", file=target)
    print("                                  [--version VERSION]", file=target)
    print("                                  [--commit COMMIT]", file=target)
    print("                                  [--plugin-manifest-version PLUGIN_MANIFEST_VERSION]", file=target)
    print("                                  [--json]", file=target)
    print("", file=target)
    print("Create a public-safe command/output issue package.", file=target)
    print("Primary path: aippocampus repro package --input-json command-output.json --json", file=target)
    print("Portable stdin example: cat command-output.json | aippocampus repro package --stdin --json", file=target)
    print("", file=target)
    print("Options:", file=target)
    print("  -h, --help", file=target)
    print("  --input-json INPUT_JSON", file=target)
    print("  --stdin", file=target)
    print("  --template", file=target)
    print("  --version VERSION", file=target)
    print("  --commit COMMIT", file=target)
    print("  --plugin-manifest-version PLUGIN_MANIFEST_VERSION", file=target)
    print("  --json", file=target)


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
    print("  aippocampus health --json", file=target)
    print("  aippocampus update status --json", file=target)


def print_plugin_status_help(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("usage: aippocampus plugin status [--json|--operator-json]", file=target)
    print("", file=target)
    print("Plugin status readiness card:", file=target)
    print("  Checks whether the local Codex plugin package/cache and host-visible tools look fresh.", file=target)
    print("  It is a plugin-shaped shortcut to update status, not a plugin install or hook enablement command.", file=target)
    print("", file=target)
    print("Try:", file=target)
    print("  aippocampus plugin status --json", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("  aippocampus update status --json", file=target)


def print_first_run_setup_card(kind: str, *, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    title = "First-run install card" if kind == "install" else "First-run setup card"
    print(f"AIppocampus {kind}", file=target)
    print(title + ":", file=target)
    print("  Goal: make the local Codex/CLI surface callable, then see one source-backed recall/search result.", file=target)
    print("", file=target)
    print("Ordinary Codex path:", file=target)
    print("  aippocampus start --json", file=target)
    print("  aippocampus plugin install --codex --verify", file=target)
    print("  aippocampus update status --json", file=target)
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


def _with_safe_next_actions(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose the chooser choices under the recovery-card action name too.

    Some front doors are choosers, but foreground agents already know to look
    for `safe_next_actions` on recovery cards. Keep both names pointed at the
    same action list so parent-command cards stay easy to consume without
    inventing a second contract shape.
    """

    payload["safe_next_actions"] = list(payload.get("choices", []))
    return payload


def _template_action(
    *,
    action_id: str,
    command_template: str,
    label: str,
    why: str,
    mutation_risk: str = "read_only",
    claim_boundary: str = "source_reopen_required_before_claims",
    requires: str | None = None,
    operator_only: bool | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "id": action_id,
        "label": label,
        "command_template": command_template,
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
        "why": why,
    }
    if requires:
        action["requires"] = requires
    if operator_only is not None:
        action["operator_only"] = operator_only
    return action


def agent_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_agent_recovery",
        status="command_required",
        decision="choose the foreground continuity action",
        choices=[
            _template_action(
                action_id="recall",
                label="Recall old context from a cue",
                command_template='aippocampus agent recall "<continuity cue>" --json',
                requires="continuity cue",
                why="Use recall for fuzzy old context, unfinished work, corrections, or handoffs.",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_shell_action(
                action_id="aippo",
                label="Ask for AIppo working guidance",
                command="aippocampus agent aippo --json",
                why="Use AIppo for task-contract orientation; guidance is not source truth.",
                mutation_risk="read_only",
                claim_boundary="working_guidance_not_source_truth",
            ),
            _template_action(
                action_id="background",
                label="Review background findings",
                command_template='aippocampus agent background "<task cue>" --json',
                requires="task cue",
                why=(
                    "Use for reviewed Dream/subconscious findings relevant to this task; "
                    "they are navigation only until source is reopened."
                ),
                claim_boundary="background_navigation_not_source_truth",
            ),
            _template_action(
                action_id="deepen",
                label="Deepen the selected route",
                command_template="aippocampus agent deepen --request 1 --last-recall --json",
                requires="prior recall result",
                why="Use after recall chooses a route; deepen/reopen before exact or high-risk claims.",
                claim_boundary="source_reopen_required_before_claim",
            ),
            _template_action(
                action_id="feedback",
                label="Record scoped route feedback",
                command_template="aippocampus agent feedback <route_id> --outcome source_reopen_success --json",
                requires="route id and outcome",
                why="Feedback is a low-authority control lane; it is not source evidence.",
                mutation_risk="explicit_feedback_write",
                claim_boundary="feedback_is_not_source_truth",
            ),
        ],
    )
    return _with_safe_next_actions(payload)


def memory_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_memory_chooser",
        decision="choose a source-backed memory read path",
        choices=[
            _template_action(
                action_id="agent_recall",
                label="Recall fuzzy continuity",
                command_template='aippocampus agent recall "<continuity cue>" --json',
                requires="continuity cue",
                why="Use for old decisions, unfinished work, style preferences, corrections, or handoffs.",
                claim_boundary="no_claim_before_reopen",
            ),
            _template_action(
                action_id="search_exact_phrase",
                label="Search exact clean-source wording",
                command_template='aippocampus search "<distinctive exact phrase>" --json',
                requires="exact phrase",
                why="Use when the user or agent remembers wording and needs a source route.",
                claim_boundary="search_result_requires_source_boundary",
            ),
            foreground_shell_action(
                action_id="latest_reply",
                label="Inspect latest closeout",
                command="aippocampus latest-reply --cwd . --json",
                why="Use when continuing from the latest final assistant closeout.",
                mutation_risk="read_only",
                claim_boundary="latest_reply_is_navigation_not_memory_fact",
            ),
            foreground_shell_action(
                action_id="list_threads",
                label="List registered source threads",
                command="aippocampus onboard --provider auto --status --json",
                why="Use when no source appears available or registration needs checking.",
                mutation_risk="read_only",
                claim_boundary="setup_status_not_memory_evidence",
            ),
        ],
    )
    return _with_safe_next_actions(payload)


def print_privacy_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus privacy", file=target)
    print("Privacy and control card:", file=target)
    print("  Defaults are read-only and redacted; destructive or private-path output is explicit operator work.", file=target)
    print("", file=target)
    print("Controls:", file=target)
    print("  aippocampus pause --json", file=target)
    print("  aippocampus forget --json", file=target)
    print("  aippocampus do-not-use-here --json", file=target)
    print("", file=target)
    print("Portability and credentials:", file=target)
    print("  aippocampus export --json", file=target)
    print("  aippocampus import --help", file=target)
    print("  aippocampus provider-key --json", file=target)
    print("Boundary: provider keys are optional; AIppocampus should still have a no-key source-backed path.", file=target)


def privacy_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_privacy_chooser",
        decision="choose a privacy or control surface",
        choices=[
            foreground_shell_action(
                action_id="open_controls",
                label="Open personal controls",
                command="aippocampus controls --json",
                why="Use when the user wants pause, forget, do-not-use-here, or why-not control lanes.",
                mutation_risk="read_only",
                claim_boundary="control_card_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="do_not_use_here",
                label="Quiet this context",
                command="aippocampus do-not-use-here --json",
                why="Shows the scoped no-use boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="feedback_is_not_source_truth",
            ),
            foreground_shell_action(
                action_id="export_boundary",
                label="Inspect export choices",
                command="aippocampus export --json",
                why="Use before moving local bundles or deciding public/private export scope.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="provider_key_boundary",
                label="Inspect provider-key boundary",
                command="aippocampus provider-key --json",
                why="Provider keys are optional and should not be printed by default.",
                mutation_risk="read_only",
                claim_boundary="provider_config_not_memory_evidence",
            ),
        ],
    )
    return _with_safe_next_actions(payload)


def controls_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_controls_chooser",
        decision="choose a scoped personal control",
        choices=[
            foreground_shell_action(
                action_id="pause_scope",
                label="Open pause scope card",
                command="aippocampus pause --json",
                why="Shows the scoped-control boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="forget_scope",
                label="Open forget scope card",
                command="aippocampus forget --json",
                why="Shows the scoped-control boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="do_not_use_here",
                label="Open do-not-use-here card",
                command="aippocampus do-not-use-here --json",
                why="Shows the scoped no-use boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="feedback_is_not_source_truth",
            ),
            _template_action(
                action_id="why_not_recall",
                label="Explain why recall stayed silent",
                command_template='aippocampus why-not-recall "<continuity cue>" --json',
                requires="continuity cue",
                why="Use when the question is why a route did not surface.",
                mutation_risk="read_only",
                claim_boundary="diagnostic_not_source_evidence",
            ),
            _template_action(
                action_id="find_control_target",
                label="Find a route id first",
                command_template='aippocampus agent recall "<route to quiet>" --json',
                why="Use this if you do not yet have the concrete route id.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
    )
    return _with_safe_next_actions(payload)


def warm_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_warm_chooser",
        status="command_or_prompt_required",
        decision="inspect warm status before optional operator warming",
        choices=[
            foreground_shell_action(
                action_id="status",
                label="Inspect warm ambient status",
                command="aippocampus warm status --json",
                why="Read-only status should be the first path; it does not run warm jobs.",
                mutation_risk="read_only",
                claim_boundary="warm_status_not_source_evidence",
            ),
            _template_action(
                action_id="run_with_prompt",
                label="Run optional warm job with a prompt",
                command_template='aippocampus warm --prompt "<cue>" --json',
                requires="cue",
                why="Warm runs are operator paths and should not be started by the bare parent command.",
                mutation_risk="operator_model_job",
                claim_boundary="warm_output_is_navigation_until_source_reopen",
                operator_only=True,
            ),
            foreground_shell_action(
                action_id="repair_or_disable",
                label="Find repair or disable action",
                command="aippocampus warm status --json",
                why="When warm is blocked or stale, status is the safe surface for repair/disable actions.",
                mutation_risk="read_only",
                claim_boundary="warm_status_not_source_evidence",
            ),
            _template_action(
                action_id="ordinary_recall",
                label="Use ordinary source-backed recall",
                command_template='aippocampus agent recall "<continuity cue>" --json',
                requires="continuity cue",
                why="Warm ambient is optional; ordinary recall remains the primary continuity path.",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
    )
    return _with_safe_next_actions(payload)



def print_controls_card(*, file: TextIO | None = None) -> None:
    target = sys.stdout if file is None else file
    print("AIppocampus controls", file=target)
    print("Personal controls card:", file=target)
    print("  Use these when you want less memory influence, narrower scope, or a route disabled here.", file=target)
    print("", file=target)
    print("Commands:", file=target)
    print("  aippocampus pause --json", file=target)
    print("  aippocampus forget --json", file=target)
    print("  aippocampus do-not-use-here --json", file=target)
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
    "start": CommandSpec("start.py", "aippocampus_runtime.cli.start"),
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
    "start.py": "aippocampus_runtime.cli.start",
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
    if args[0] == "agent" and set(args[1:]) <= {"--json"}:
        payload = agent_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            invocation = resolve_command(["agent"])
            if invocation is not None:
                return invocation, run_invocation(invocation)
        return None, 0
    if args[0] in {"dream", "subconscious"} and set(args[1:]) <= {"--json"}:
        payload = background_findings.background_recovery_card(args[0])
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("AIppocampus background findings")
            print("decision: use the foreground agent background route")
            print('next: aippocampus agent background "task cue" --json')
            print("boundary: Dream/subconscious findings are navigation only until source is reopened.")
        return None, 2
    if args[0] == "warm" and set(args[1:]) <= {"--json"}:
        payload = warm_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            invocation = resolve_command(["warm"])
            if invocation is not None:
                return invocation, run_invocation(invocation)
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
        payload = doctor_chooser_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_doctor_recovery_card()
        return None, 0
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
            invocation = resolve_command(["logs"])
            if invocation is not None:
                return invocation, run_invocation(invocation)
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
    print("  aippocampus start --json              Choose the first useful continuity path", file=target)
    print("  aippocampus agent recall \"old cue\" --json", file=target)
    print("                                        Continue old work from source routes", file=target)
    print("  aippocampus agent deepen --request 1 --last-recall --json", file=target)
    print("                                        Reopen the selected route before claims", file=target)
    print("  aippocampus search \"exact phrase\"      Exact wording fallback/demo", file=target)
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
    print("  start               First useful continuity-path chooser", file=target)
    print("  health              Run runtime health checks", file=target)
    print("  version             Show active runtime and release metadata version", file=target)
    print("  onboard             Check/register provider-backed clean source", file=target)
    print("  search              Search clean-source memory", file=target)
    print("  agent recall        Agent continuity pull path: recall/AIppo/deepen/explain", file=target)
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
    print("  mcp list-tools      Compact readiness by default; --json lists full schemas", file=target)
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
