"""Public projection for dream input packs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


def public_pack_summary(payload: Mapping[str, Any], *, schema_version: int = 1) -> dict[str, Any]:
    audit_value = payload.get("source_ref_audit")
    audit: Mapping[str, Any] = audit_value if isinstance(audit_value, Mapping) else {}
    contributions = [
        {
            "seed_kind": item.get("seed_kind"),
            "source_ref_count": item.get("source_ref_count"),
            "source_thread_count": item.get("source_thread_count"),
            "readiness_role": item.get("readiness_role"),
            "question_count": item.get("question_count"),
            "frontier_count": item.get("frontier_count"),
            "theme_count": item.get("theme_count"),
            "concept_count": item.get("concept_count"),
        }
        for item in payload.get("source_contributions") or []
        if isinstance(item, Mapping)
    ]
    return {
        "schema_version": schema_version,
        "kind": "aippocampus_dream_input_pack_summary",
        "pack_id": payload.get("pack_id"),
        "status": payload.get("status"),
        "pack_kind": payload.get("pack_kind"),
        "source_seed_kind_counts": dict(
            Counter(str(kind) for kind in payload.get("source_seed_kinds") or [])
        ),
        "source_ref_audit": {
            "status": audit.get("status"),
            "source_ref_count": audit.get("source_ref_count"),
            "source_thread_count": audit.get("source_thread_count"),
            "clean_source_resolution": audit.get("clean_source_resolution"),
        },
        "weak_source_handle_count": payload.get("weak_source_handle_count"),
        "source_contributions": contributions,
        "eligible_dream_functions": payload.get("eligible_dream_functions") or [],
        "downstream_use": payload.get("downstream_use") or [],
        "foreground_eligible": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "truth_boundary": payload.get("truth_boundary"),
        "cannot_claim": payload.get("cannot_claim") or [],
    }
