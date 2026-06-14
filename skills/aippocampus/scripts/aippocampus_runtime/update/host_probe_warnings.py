#!/usr/bin/env python3
"""Classify host-probe stderr without changing probe pass/fail semantics."""

from __future__ import annotations

from typing import Any, Mapping

from aippocampus_runtime.core import compact_text

SUMMARY_KIND = "aippocampus_host_probe_warning_summary"
BUCKETS = (
    "fatal_failures",
    "aippocampus_actionable_warnings",
    "benign_host_probe_warnings",
    "unrelated_host_or_plugin_noise",
    "unclassified_stderr",
)


def _stderr_lines(stderr_tail: Any) -> list[str]:
    return [
        compact_text(line.strip(), 260)
        for line in str(stderr_tail or "").splitlines()
        if line.strip()
    ]


def _classify_line(line: str, *, validation_ok: bool) -> str:
    lower = line.casefold()
    if validation_ok and "aippocampus" not in lower and any(
        token in lower
        for token in (
            "authorizationrequired",
            "backend-api/wham/apps",
            "client error: http request failed",
            "invalid refresh token",
            "send initialized notification",
            "token refresh not possible",
            "codex_rmcp_client",
            "rmcp::transport::auth",
            "rmcp::transport::worker",
        )
    ):
        return "unrelated_host_or_plugin_noise"
    if any(token in lower for token in ("fatal", "traceback", "panic")):
        return "fatal_failures"
    if "ignoring interface.defaultprompt" in lower:
        return "unrelated_host_or_plugin_noise"
    if validation_ok and (
        "resources/templates/list" in lower or "resources/list" in lower
    ):
        return "benign_host_probe_warnings"
    if validation_ok and "failed to kill mcp process group" in lower:
        return "benign_host_probe_warnings"
    if validation_ok and "state db discrepancy" in lower and "falling_back" in lower:
        return "benign_host_probe_warnings"
    if validation_ok and "aippocampus" not in lower:
        return "unrelated_host_or_plugin_noise"
    if "aippocampus" in lower and any(token in lower for token in ("warn", "error", "failed")):
        return "aippocampus_actionable_warnings"
    return "unclassified_stderr"


def summarize_host_probe_warnings(probe: Mapping[str, Any] | None) -> dict[str, Any]:
    payload: Mapping[str, Any] = probe if isinstance(probe, Mapping) else {}
    validation_ok = bool(payload.get("validation_ok"))
    classified: dict[str, list[str]] = {bucket: [] for bucket in BUCKETS}
    for line in _stderr_lines(payload.get("stderr_tail")):
        classified[_classify_line(line, validation_ok=validation_ok)].append(line)

    warning_count = sum(len(items) for items in classified.values())
    nonfatal_count = warning_count - len(classified["fatal_failures"])
    if not warning_count:
        status = "verification_passed_without_stderr_warnings" if validation_ok else "probe_failed_without_stderr"
    elif validation_ok and not classified["fatal_failures"]:
        status = "verification_passed_with_nonfatal_host_warnings"
    else:
        status = "probe_failed_or_has_fatal_stderr"
    return {
        "kind": SUMMARY_KIND,
        "status": status,
        "validation_ok": validation_ok,
        "warning_count": warning_count,
        "nonfatal_warning_count": nonfatal_count,
        **classified,
    }


def attach_host_probe_warning_summary(probe: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if probe is None:
        return None
    result = dict(probe)
    result["warning_summary"] = summarize_host_probe_warnings(result)
    return result
