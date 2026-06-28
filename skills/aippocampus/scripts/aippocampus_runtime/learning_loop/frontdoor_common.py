"""Shared public-boundary helpers for learning frontdoor payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

KIND = "aippocampus_learning_frontdoor"
SCHEMA_VERSION = 1
LEARNING_OPERATOR_DETAIL_COMMAND = "aippocampus learning guidance --operator-json --json"


def public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def with_boundary_detail(
    payload: Mapping[str, Any],
    *,
    cannot_claim: list[str],
    include_cannot_claim: bool = True,
) -> dict[str, Any]:
    """Keep compact foreground JSON useful while preserving inspectable bounds."""

    out = dict(payload)
    detail_raw = out.get("boundary_detail")
    detail: dict[str, Any] = dict(detail_raw) if isinstance(detail_raw, Mapping) else {}
    if include_cannot_claim and cannot_claim:
        detail["cannot_claim"] = list(dict.fromkeys(str(item) for item in cannot_claim if item))
    detail.setdefault(
        "frontstage_rule",
        "compact learning/repro surfaces summarize bounds here instead of top-level caveat walls",
    )
    if cannot_claim and not include_cannot_claim:
        detail.setdefault("full_detail_owns_cannot_claim", True)
        detail.setdefault("detail_available_with", LEARNING_OPERATOR_DETAIL_COMMAND)
    out["boundary_detail"] = detail
    out.pop("cannot_claim", None)
    return out


def privacy_boundary() -> dict[str, Any]:
    return {
        "raw_rollout_scan_default": False,
        "raw_rollouts_serialized": False,
        "raw_prompt_or_stdout_serialized": False,
        "learning_guidance_is_source_truth": False,
        "source_reopen_required_for_claims": True,
        "default_output_redacts_local_paths": True,
    }
