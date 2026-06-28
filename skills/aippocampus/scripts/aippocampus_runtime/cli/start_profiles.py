"""First-run setup profiles for the start foreground chooser."""

from __future__ import annotations

from collections.abc import MutableSequence
from typing import Any

from aippocampus_runtime.contracts import foreground_action_is_read_only, shell_quote

TRUSTED_LOCAL_PERSONAL_PROFILE = "trusted-local-personal-continuity"
START_PROFILE_CHOICES = ("default", TRUSTED_LOCAL_PERSONAL_PROFILE)


def is_trusted_local_personal_profile(profile: str | None) -> bool:
    return str(profile or "default") == TRUSTED_LOCAL_PERSONAL_PROFILE


def trusted_personal_receipt_command(clean_cue: str | None) -> str:
    if clean_cue:
        return f"aippocampus agent recall {shell_quote(clean_cue)} --json"
    return 'aippocampus agent recall "{continuity_cue}" --json'


def annotate_trusted_personal_write_actions(
    actions: MutableSequence[dict[str, Any]],
    *,
    clean_cue: str | None,
) -> None:
    receipt_command = trusted_personal_receipt_command(clean_cue)
    for action in actions:
        if not isinstance(action, dict) or foreground_action_is_read_only(action):
            continue
        action["consent_bundle_id"] = TRUSTED_LOCAL_PERSONAL_PROFILE
        action["after_success_command"] = receipt_command
        action["why"] = (
            str(action.get("why") or "")
            + " This is the trusted-personal first-run bundle: one explicit local "
            "consent should move directly toward the first recall receipt."
        )


def trusted_personal_card_fields(clean_cue: str | None) -> dict[str, Any]:
    has_cue = bool(clean_cue)
    return {
        "setup_profile": {
            "id": TRUSTED_LOCAL_PERSONAL_PROFILE,
            "consent_model": "consent_once_for_low_risk_local_personal_setup",
            "rollback_command": "aippocampus uninstall --dry-run --json",
            "detail_command": (
                "aippocampus start --profile trusted-local-personal-continuity --operator-json"
            ),
        },
        "consent_bundle": {
            "id": TRUSTED_LOCAL_PERSONAL_PROFILE,
            "low_risk_local_actions": [
                "local_source_registration_or_refresh",
                "rebuildable_index_refresh",
                "codex_plugin_mcp_verify",
                "supported_hook_status_or_safe_wiring",
            ],
            "requires_separate_consent": [
                "destructive_cleanup",
                "broad_private_export_or_import",
                "credential_handling",
                "cloud_or_model_spend_beyond_configured_policy",
                "enterprise_or_governed_privacy_profile",
            ],
        },
        "first_magic_path": {
            "target": "first_useful_recall_receipt",
            "after_setup_command": (
                trusted_personal_receipt_command(clean_cue) if has_cue else None
            ),
            "after_setup_command_template": (
                None if has_cue else 'aippocampus agent recall "{continuity_cue}" --json'
            ),
            "receipt_boundary": "recall_receipt_requires_deepen_or_source_open_before_claims",
        },
    }
