#!/usr/bin/env python3
"""Thin foreground-callability gate for recall-related surfaces."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from typing import Any

READY_STATUSES = {
    "wired_foreground_action",
    "wired_secondary_action",
    "diagnostic_only",
    "proxy_only",
    "blocked",
}


def _surface(
    surface_id: str,
    *,
    status: str,
    owner_issue: str,
    foreground_callable: bool,
    cli_wired: bool,
    mcp_wired: bool,
    claim: str,
    command: str = "",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "surface_id": surface_id,
        "status": status,
        "owner_issue": owner_issue,
        "foreground_callable": foreground_callable,
        "cli_wired": cli_wired,
        "mcp_wired": mcp_wired,
        "claim": claim,
        "command": command,
        "reason": reason,
    }


def default_surfaces() -> list[dict[str, Any]]:
    return [
        _surface(
            "apw_fallback",
            status="wired_secondary_action",
            owner_issue="#2561",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="APW fallback is callable as opt-in/weak-recall recovery, not default ranking.",
            command="aippocampus agent recall <cue> --apw-fallback --json",
        ),
        _surface(
            "mcp_agent_recall_deepen_parity",
            status="wired_foreground_action",
            owner_issue="#2561",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="MCP agent_recall can emit a deepen action that MCP agent_deepen follows.",
        ),
        _surface(
            "low_specificity_recall_recovery",
            status="wired_foreground_action",
            owner_issue="#2562",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="Weak compact labels keep low-confidence choices and a safer recovery action.",
        ),
        _surface(
            "known_artifact_recall_dogfood",
            status="diagnostic_only",
            owner_issue="#2556",
            foreground_callable=False,
            cli_wired=True,
            mcp_wired=False,
            claim="Dogfood reports static setup separately from live recall/search discoverability.",
            command="python tools/aippocampus/smoke/known_artifact_recall_dogfood.py --json",
        ),
        _surface(
            "repo_familiarity_fallback",
            status="wired_foreground_action",
            owner_issue="#2557",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="Current-checkout repo familiarity can become a source-open action for repo-doc weak recall.",
        ),
        _surface(
            "ambient_tiny_agent_recall_affordance",
            status="wired_secondary_action",
            owner_issue="#2554",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim=(
                "Ambient tiny recall can emit an action-only agent_recall hint after "
                "source-open and drag-control gates pass; it is not default source evidence."
            ),
            command="aippocampus agent recall <distinctive continuity cue> --json",
            reason="host-replay tiny affordance gate passed; default foreground evidence remains diagnostic-only",
        ),
        _surface(
            "wrong_route_feedback_demotion",
            status="wired_secondary_action",
            owner_issue="#2553/#2560",
            foreground_callable=True,
            cli_wired=True,
            mcp_wired=True,
            claim="Wrong-route feedback can target APW route identity aliases and suppress reruns.",
        ),
    ]


def _clean_surfaces(extra_surfaces: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    surfaces = [dict(surface) for surface in default_surfaces()]
    for raw in extra_surfaces or []:
        if isinstance(raw, Mapping):
            surfaces.append(dict(raw))
    return surfaces


def build_recall_integration_readiness(
    extra_surfaces: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    surfaces = _clean_surfaces(extra_surfaces)
    failures: list[dict[str, Any]] = []
    for surface in surfaces:
        surface_id = str(surface.get("surface_id") or "surface")
        status = str(surface.get("status") or "")
        claim = str(surface.get("claim") or "")
        if status not in READY_STATUSES:
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "unknown_readiness_status",
                    "status": status,
                }
            )
            continue
        if status == "proxy_only" and "foreground" in claim.casefold():
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "proxy_only_surface_claims_foreground_ready",
                    "owner_issue": surface.get("owner_issue"),
                }
            )
        if (
            surface.get("foreground_callable")
            and surface.get("cli_wired")
            and not surface.get("mcp_wired")
        ):
            failures.append(
                {
                    "surface_id": surface_id,
                    "reason": "agent_facing_cli_wired_but_mcp_unwired",
                    "owner_issue": surface.get("owner_issue"),
                }
            )
    status_counts = {
        status: sum(1 for surface in surfaces if surface.get("status") == status)
        for status in sorted(READY_STATUSES)
    }
    return {
        "kind": "aippocampus_recall_integration_readiness",
        "schema_version": 1,
        "ok": not failures,
        "surface_count": len(surfaces),
        "status_counts": status_counts,
        "failure_count": len(failures),
        "failures": failures,
        "surfaces": surfaces,
        "claim_boundary": (
            "readiness reports foreground callability only; it is not a recall quality benchmark"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_recall_integration_readiness()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "recall integration readiness: "
            f"ok={str(report['ok']).lower()} surfaces={report['surface_count']} "
            f"failures={report['failure_count']}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
