#!/usr/bin/env python3
"""Compatibility shim for packaged coding rejected-route Dream probes."""

from __future__ import annotations

from aippocampus_runtime.coding.rejected_route_probes import (
    ELIGIBLE_EVENT_TYPES,
    PROBE_FAMILY,
    PROBE_KIND,
    build_rejected_route_probe,
    build_rejected_route_probes,
    event_is_rejected_route,
    format_utc,
    future_utc,
    normalize_source_refs,
    parse_utc,
    public_fixture_summary,
    rejected_route_surface,
    run_rejected_route_fixture,
    source_ref_key,
    stable_id,
)

__all__ = [
    "ELIGIBLE_EVENT_TYPES",
    "PROBE_FAMILY",
    "PROBE_KIND",
    "build_rejected_route_probe",
    "build_rejected_route_probes",
    "event_is_rejected_route",
    "format_utc",
    "future_utc",
    "normalize_source_refs",
    "parse_utc",
    "public_fixture_summary",
    "rejected_route_surface",
    "run_rejected_route_fixture",
    "source_ref_key",
    "stable_id",
]
