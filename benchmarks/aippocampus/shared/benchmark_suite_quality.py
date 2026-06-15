"""Quality-state aggregation helpers for the benchmark suite."""

from __future__ import annotations

from typing import Any


def track_quality_state(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    maturity = payload.get("benchmark_maturity")
    if not isinstance(maturity, dict):
        maturity = {}
    if "quality_gate_ok" in payload:
        quality_gate_ok = bool(payload.get("quality_gate_ok"))
        status = "passed" if quality_gate_ok else "failed"
        source = "quality_gate_ok"
    elif "public_quality_gate_ok" in payload:
        quality_gate_ok = bool(payload.get("public_quality_gate_ok"))
        status = "passed" if quality_gate_ok else "failed"
        source = "public_quality_gate_ok"
    elif "quality_gate_ok" in maturity:
        quality_gate_ok = bool(maturity.get("quality_gate_ok"))
        status = "passed" if quality_gate_ok else "failed"
        source = "benchmark_maturity.quality_gate_ok"
    elif "public_quality_gate_ok" in maturity:
        quality_gate_ok = bool(maturity.get("public_quality_gate_ok"))
        status = "passed" if quality_gate_ok else "failed"
        source = "benchmark_maturity.public_quality_gate_ok"
    elif "quality_gate_kind" in payload:
        quality_gate_ok = None
        status = "unknown"
        source = "quality_gate_kind"
    elif not bool(payload.get("ok")):
        quality_gate_ok = False
        status = "failed"
        source = "track_ok_false_without_quality_metadata"
    else:
        quality_gate_ok = None
        status = "unknown"
        source = "missing_quality_metadata"

    return {
        "track": name,
        "ok": bool(payload.get("ok")),
        "quality_gate_ok": quality_gate_ok,
        "quality_gate_status": status,
        "metadata_source": source,
        "benchmark_maturity_level": (
            payload.get("benchmark_maturity_level")
            or maturity.get("benchmark_maturity_level")
            or "unknown"
        ),
    }


def suite_quality_summary(tracks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    states = {
        name: track_quality_state(name, payload)
        for name, payload in sorted(tracks.items())
    }
    unknown_tracks = [
        name
        for name, state in states.items()
        if state["quality_gate_status"] == "unknown"
    ]
    failed_tracks = [
        name for name, state in states.items() if state["quality_gate_status"] == "failed"
    ]
    passed_tracks = [
        name for name, state in states.items() if state["quality_gate_status"] == "passed"
    ]
    quality_gate_ok = bool(states) and not unknown_tracks and not failed_tracks
    return {
        "quality_gate_ok": quality_gate_ok,
        "quality_gate_status": "passed"
        if quality_gate_ok
        else ("unknown" if unknown_tracks else "failed"),
        "passed_tracks": passed_tracks,
        "failed_tracks": failed_tracks,
        "unknown_tracks": unknown_tracks,
        "unmatured_tracks": unknown_tracks,
        "track_quality_states": states,
    }
