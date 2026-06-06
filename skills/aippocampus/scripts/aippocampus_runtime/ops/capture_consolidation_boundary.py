#!/usr/bin/env python3
"""No-write readout for edge capture vs async consolidation ownership."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths

READOUT_KIND = "aippocampus_capture_consolidation_boundary"
SCHEMA_VERSION = 1
STATUS_ORDER = (
    "captured",
    "pending_consolidation",
    "consolidated_sidecars_ready",
    "source_reopenable",
)


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def capture_status(row: Mapping[str, Any]) -> str:
    """Return the highest no-write lifecycle state supported by current metadata."""

    source_refs = [ref for ref in _as_list(row.get("source_refs")) if isinstance(ref, Mapping)]
    if row.get("source_reopenable") and source_refs:
        return "source_reopenable"
    if row.get("sidecars_ready"):
        return "consolidated_sidecars_ready"
    if row.get("clean_source_ready") or row.get("pending_consolidation"):
        return "pending_consolidation"
    return "captured"


def _project_item(row: Mapping[str, Any]) -> dict[str, Any]:
    status = capture_status(row)
    source_refs = [ref for ref in _as_list(row.get("source_refs")) if isinstance(ref, Mapping)]
    return {
        "item_id": str(row.get("item_id") or row.get("source_id") or ""),
        "source_id": str(row.get("source_id") or ""),
        "status": status,
        "edge_capture_lane": status == "captured",
        "consolidation_lane": status in {
            "pending_consolidation",
            "consolidated_sidecars_ready",
            "source_reopenable",
        },
        "source_ref_count": len(source_refs),
        "source_refs_available": bool(source_refs),
        "external_model_required_for_capture": False,
        "raw_text_serialized": False,
        "claim_support": "source_required" if status != "source_reopenable" else "source_open",
    }


def capture_consolidation_readout(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Project local capture/consolidation state without exposing private text.

    This readout intentionally does not mutate clean source, indexes, sidecars,
    or sync state. It gives future agents a single boundary check before moving
    heavier semantic, Dream, graph, or cross-device work into foreground capture.
    """

    items = [_project_item(row) for row in rows]
    counts = {status: 0 for status in STATUS_ORDER}
    for item in items:
        counts[item["status"]] += 1
    payload = {
        "kind": READOUT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "no_write": True,
        "items": items,
        "metrics": {
            "captured_count": counts["captured"],
            "pending_consolidation_count": counts["pending_consolidation"],
            "consolidated_sidecars_ready_count": counts["consolidated_sidecars_ready"],
            "source_reopenable_count": counts["source_reopenable"],
            "state_count": len(items),
        },
        "contract": {
            "edge_capture_local_first": True,
            "edge_capture_offline_safe": True,
            "edge_capture_requires_external_model": False,
            "consolidation_is_async": True,
            "generated_sidecars_are_cache": True,
            "source_refs_remain_authority": True,
            "foreground_hooks_must_not_wait_for_consolidation": True,
        },
        "privacy_boundary": {
            "raw_text_serialized": False,
            "secret_values_serialized": False,
            "local_paths_serialized": False,
            "provider_payload_serialized": False,
        },
        "can_claim": [
            "capture_and_consolidation_states_are_distinguished",
            "stale_consolidation_does_not_imply_lost_source",
            "local_only_capture_is_valid_product_mode",
        ],
        "cannot_claim": [
            "hosted_cloud_required",
            "foreground_hooks_may_run_heavy_consolidation",
            "generated_sidecars_replace_clean_source",
            "capture_status_proves_recall_quality",
        ],
    }
    return redact_private_paths(payload)


def fixture_capture_consolidation_readout() -> dict[str, Any]:
    rows = [
        {
            "item_id": "edge-captured",
            "source_id": "clean:edge-captured",
            "raw_text": "private text must never be serialized",
        },
        {
            "item_id": "pending",
            "source_id": "clean:pending",
            "clean_source_ready": True,
        },
        {
            "item_id": "sidecars",
            "source_id": "clean:sidecars",
            "clean_source_ready": True,
            "sidecars_ready": True,
        },
        {
            "item_id": "reopenable",
            "source_id": "clean:reopenable",
            "clean_source_ready": True,
            "sidecars_ready": True,
            "source_reopenable": True,
            "source_refs": [{"source_id": "clean:reopenable", "message_id": "m1"}],
        },
    ]
    return capture_consolidation_readout(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="Emit the public-safe fixture readout.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)
    payload = fixture_capture_consolidation_readout()
    if args.json or args.fixture:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("capture/consolidation boundary: " + ("ok" if payload["ok"] else "failed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
