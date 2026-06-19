"""Foreground projections for macro-orientation recovery cards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields


def compact_missing_state_card(
    *,
    kind: str,
    schema_version: str,
    macro_packet_schema_version: str,
    suggested_next: str,
    foreground_action: Mapping[str, Any],
    safe_next_actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Keep missing-state recovery foreground-first; ledgers stay in detail."""

    return {
        "kind": kind,
        "schema_version": schema_version,
        "macro_packet_schema_version": macro_packet_schema_version,
        "mode": "macro",
        "surface": "macro_orientation",
        "detail": "compact",
        "status": "missing_macro_state_path",
        "ok": False,
        "suggested_next": suggested_next,
        "state_ready": False,
        "message": "No macro-orientation state is available yet; use recall or inspect the schema before creating local macro state.",
        **canonical_foreground_action_fields(foreground_action, safe_next_actions=safe_next_actions),
        "claim_boundary": "macro_orientation_is_navigation_not_source_truth",
        "operator_detail_command": "aippocampus agent macro --json --detail full",
        "output_boundary": "compact_foreground_no_audit_ledgers",
    }
