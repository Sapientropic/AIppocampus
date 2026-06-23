#!/usr/bin/env python3
"""Authority helpers for Dream probes that are useful but not source truth."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.dream.risk_terms import dream_text_hard_risk
from aippocampus_runtime.source.io_kernel import source_ref_key


def _normalize_refs(value: object) -> list[dict[str, Any]]:
    items = [value] if isinstance(value, Mapping) else value if isinstance(value, Iterable) and not isinstance(value, (str, bytes)) else []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        key = source_ref_key(item)
        if any(key) and key not in seen:
            seen.add(key)
            refs.append(dict(item))
    return refs


def _bridge_claim_ref_count(probe: Mapping[str, Any]) -> int:
    return sum(
        len(_normalize_refs(claim.get("source_refs")))
        for claim in probe.get("bridge_claims") or []
        if isinstance(claim, Mapping)
    )


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item not in {None, ""}]
    return []


def active_imagination_probe_boundary(probe: Mapping[str, Any]) -> dict[str, Any]:
    refs = _normalize_refs(probe.get("source_refs"))
    thread_count = len({str(ref.get("thread_key") or ref.get("thread_id") or "") for ref in refs})
    bridge_ref_count = _bridge_claim_ref_count(probe)
    sandbox_text = " ".join(str(probe.get(key) or "") for key in ("sandbox_boundary", "truth_boundary", "source_authority", "support_level")).casefold()
    allowed = (
        str(probe.get("dream_function") or "") == "active_imagination"
        and thread_count == 1
        and len(refs) >= 3
        and bridge_ref_count >= 2
        and bool(compact_text(str(probe.get("why_this_is_not_fact") or ""), 300))
        and bool(_string_values(probe.get("counter_evidence")))
        and bool(_string_values(probe.get("activation_cues")))
        and any(term in sandbox_text for term in ("sandbox", "not_fact", "not fact", "not_source_fact"))
        and not dream_text_hard_risk(probe.get("title"), probe.get("summary"), probe.get("counter_evidence"))
    )
    return {
        "state": "single_thread_source_dense_probe" if allowed else "cross_thread_source_required",
        "allowed": allowed,
        "authority": "source_reopen_required_probe" if allowed else "requires_two_independent_threads",
        "source_ref_count": len(refs),
        "source_thread_count": thread_count,
        "bridge_claim_source_ref_count": bridge_ref_count,
        "requires_source_reopen_before_claim": True,
        "not_foreground_truth": True,
    }


def authority_from_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    authority = finding.get("probe_authority") or finding.get("source_authority") or {}
    return dict(authority) if isinstance(authority, Mapping) else {}


def applies_single_thread_probe(authority: Mapping[str, Any]) -> bool:
    return authority.get("state") == "single_thread_source_dense_probe"


def apply_foreground_use(authority: Mapping[str, Any], foreground_use: MutableMapping[str, Any]) -> None:
    if not applies_single_thread_probe(authority):
        return
    foreground_use.update(
        {
            "default_action": "source_reopen_required_probe",
            "single_thread_probe_action": "optional_probe",
            "accepted_capsule_can_be_used_quietly_until_invalidated": False,
            "source_reopen_required_before_use": True,
        }
    )


def source_strength_score(authority: Mapping[str, Any], ref_count: int) -> float:
    if applies_single_thread_probe(authority):
        return 0.65
    return 1.0 if ref_count >= 2 else 0.75
