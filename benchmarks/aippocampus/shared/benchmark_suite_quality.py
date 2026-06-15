"""Quality-state aggregation helpers for the benchmark suite."""

from __future__ import annotations

from typing import Any

PUBLIC_QUALITY_GATE_KINDS = {
    "public_quality",
    "public_quality_gate_ok",
    "external_public_quality",
}

NON_PUBLIC_QUALITY_GATE_HINTS = (
    "diagnostic",
    "contract",
    "fixture",
    "smoke",
    "proxy",
    "scoring",
    "not_public_quality",
)


def _metadata(payload: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    maturity = payload.get("benchmark_maturity")
    if not isinstance(maturity, dict):
        maturity = {}
    gate_kind = str(
        payload.get("quality_gate_kind")
        or payload.get("quality_gate_ok_means")
        or maturity.get("quality_gate_kind")
        or maturity.get("quality_gate_ok_means")
        or ""
    )
    maturity_level = str(
        payload.get("benchmark_maturity_level")
        or maturity.get("benchmark_maturity_level")
        or ""
    )
    return maturity, gate_kind, maturity_level


def _looks_non_public_quality(gate_kind: str, maturity_level: str) -> bool:
    text = f"{gate_kind} {maturity_level}".casefold()
    return any(hint in text for hint in NON_PUBLIC_QUALITY_GATE_HINTS)


def track_quality_state(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    maturity, gate_kind, maturity_level = _metadata(payload)
    if "public_quality_gate_ok" in payload:
        quality_gate_ok = bool(payload.get("public_quality_gate_ok"))
        if quality_gate_ok:
            status = "passed"
        elif bool(payload.get("quality_gate_ok")):
            status = "diagnostic_passed_not_public_quality"
        elif bool(payload.get("contract_gate_ok")) and bool(payload.get("ok")):
            status = "contract_passed_not_public_quality"
        else:
            status = "public_quality_failed"
        source = "public_quality_gate_ok"
    elif "public_quality_gate_ok" in maturity:
        quality_gate_ok = bool(maturity.get("public_quality_gate_ok"))
        if quality_gate_ok:
            status = "passed"
        elif bool(maturity.get("quality_gate_ok")):
            status = "diagnostic_passed_not_public_quality"
        elif bool(payload.get("contract_gate_ok")) and bool(payload.get("ok")):
            status = "contract_passed_not_public_quality"
        else:
            status = "public_quality_failed"
        source = "benchmark_maturity.public_quality_gate_ok"
    elif "quality_gate_ok" in payload:
        raw_quality_gate_ok = bool(payload.get("quality_gate_ok"))
        if gate_kind in PUBLIC_QUALITY_GATE_KINDS:
            quality_gate_ok = raw_quality_gate_ok
            status = "passed" if raw_quality_gate_ok else "public_quality_failed"
        elif raw_quality_gate_ok and _looks_non_public_quality(gate_kind, maturity_level):
            quality_gate_ok = False
            status = "diagnostic_passed_not_public_quality"
        elif raw_quality_gate_ok:
            quality_gate_ok = False
            status = "ambiguous_quality_gate_kind"
        elif bool(payload.get("contract_gate_ok")) and bool(payload.get("ok")):
            quality_gate_ok = False
            status = "contract_passed_not_public_quality"
        else:
            quality_gate_ok = False
            status = "public_quality_failed"
        source = "quality_gate_ok"
    elif "quality_gate_ok" in maturity:
        quality_gate_ok = bool(maturity.get("quality_gate_ok"))
        if gate_kind in PUBLIC_QUALITY_GATE_KINDS:
            status = "passed" if quality_gate_ok else "public_quality_failed"
        elif quality_gate_ok and _looks_non_public_quality(gate_kind, maturity_level):
            quality_gate_ok = False
            status = "diagnostic_passed_not_public_quality"
        elif quality_gate_ok:
            quality_gate_ok = False
            status = "ambiguous_quality_gate_kind"
        elif bool(payload.get("contract_gate_ok")) and bool(payload.get("ok")):
            status = "contract_passed_not_public_quality"
        else:
            status = "public_quality_failed"
        source = "benchmark_maturity.quality_gate_ok"
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
        "quality_gate_kind": gate_kind or "not_declared",
        "benchmark_maturity_level": (
            maturity_level
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
    bounded_not_public_tracks = [
        name
        for name, state in states.items()
        if state["quality_gate_status"]
        in {
            "diagnostic_passed_not_public_quality",
            "contract_passed_not_public_quality",
        }
    ]
    ambiguous_tracks = [
        name
        for name, state in states.items()
        if state["quality_gate_status"] == "ambiguous_quality_gate_kind"
    ]
    failed_tracks = [
        name
        for name, state in states.items()
        if state["quality_gate_status"]
        in {"failed", "public_quality_failed", "track_ok_false_without_quality_metadata"}
    ]
    passed_tracks = [
        name for name, state in states.items() if state["quality_gate_status"] == "passed"
    ]
    quality_gate_ok = bool(states) and not (
        unknown_tracks or failed_tracks or bounded_not_public_tracks or ambiguous_tracks
    )
    if quality_gate_ok:
        summary_status = "passed"
    elif unknown_tracks:
        summary_status = "unknown"
    elif failed_tracks:
        summary_status = "failed"
    elif ambiguous_tracks:
        summary_status = "ambiguous_quality_gate_kind"
    else:
        summary_status = "not_public_quality"
    return {
        "quality_gate_ok": quality_gate_ok,
        "quality_gate_status": summary_status,
        "passed_tracks": passed_tracks,
        "failed_tracks": failed_tracks,
        "unknown_tracks": unknown_tracks,
        "bounded_not_public_tracks": bounded_not_public_tracks,
        "ambiguous_tracks": ambiguous_tracks,
        "unmatured_tracks": unknown_tracks,
        "track_quality_states": states,
    }
