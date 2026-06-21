#!/usr/bin/env python3
"""Public-safe smoke for the #281 living cue cache slice."""

from __future__ import annotations

import argparse
import json
from typing import Any

from _paths import ensure_paths


def _living_cue_cache_runtime() -> tuple[Any, Any, Any]:
    ensure_paths()
    from aippocampus_runtime.recall.living_cue_cache import (
        demo_living_cue_entries,
        living_cue_cache_report,
        select_living_cue_packet,
    )

    return demo_living_cue_entries, living_cue_cache_report, select_living_cue_packet


def _case_projection(label: str, packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": label,
        "decision": packet.get("decision"),
        "support_level": packet.get("support_level"),
        "selected_count": packet.get("selected_count"),
        "candidate_ref_count": len(packet.get("candidate_refs") or []),
        "diagnostics": dict(packet.get("diagnostics") or {}),
    }


def run_smoke() -> dict[str, Any]:
    (
        demo_living_cue_entries,
        living_cue_cache_report,
        select_living_cue_packet,
    ) = _living_cue_cache_runtime()
    entries = demo_living_cue_entries()
    positive = select_living_cue_packet("please continue learned phrase alpha", entries)
    negative = select_living_cue_packet("temporary mood beta", entries)
    report = living_cue_cache_report(entries)
    cases = [
        _case_projection("learned_phrase_bridge", positive),
        _case_projection("temporary_mood_suppression", negative),
    ]
    payload = {
        "ok": (
            positive.get("decision") == "scent"
            and positive.get("selected_count") == 1
            and negative.get("decision") == "skip"
            and negative.get("diagnostics", {}).get("temporary_suppressed_count") == 1
        ),
        "cases": cases,
        "report": report,
        "output_boundary": "no_raw_prompt_no_raw_cue_no_snippet_no_local_path",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = (
        "tree problem",
        "stressed tonight",
        "learned phrase alpha",
        "temporary mood beta",
        "clean source text",
        "E:\\",
        "C:\\",
        "sk_",
    )
    payload["public_safe_output"] = not any(token in encoded for token in forbidden)
    payload["ok"] = bool(payload["ok"] and payload["public_safe_output"])
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    payload = run_smoke()
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "ok" if payload["ok"] else "failed"
        print(f"living cue cache smoke: {status}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
