#!/usr/bin/env python3
"""Evaluate recorded source-semantic candidates against deterministic-only recall.

This smoke is intentionally no-key friendly. It does not call a provider and it
does not claim live semantic-worker quality. The goal is to prove the route
consumer can use recorded, source-backed semantic candidates for fuzzy cues
while generic controls stay quiet.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import semantic_recall_gate as gate

RECORDED_TRIGGERS = [
    {
        "kind": "aippocampus_semantic_trigger",
        "title": "小海马体",
        "concept": "小海马体",
        "source_candidate_type": "source_semantic_candidate",
        "aliases": ["小海马体 continuity", "外置小海马"],
        "activation_cues": ["小海马体 continuity"],
        "claim_authority": "navigation_only",
        "semantic_candidate": True,
        "term_type": "relationship_cue",
        "surface_status": "exact_surface",
        "status": "active",
        "confidence": 0.86,
        "source_refs": [{"thread_key": "session:origin", "line": 12}],
    },
    {
        "kind": "aippocampus_semantic_trigger",
        "title": "foreground consumes; background audits",
        "concept": "foreground consumes; background audits",
        "source_candidate_type": "source_semantic_candidate",
        "aliases": ["foreground consumes background audits"],
        "activation_cues": ["foreground consumes background audits"],
        "claim_authority": "navigation_only",
        "semantic_candidate": True,
        "term_type": "decision_label",
        "surface_status": "lightly_normalized",
        "status": "active",
        "confidence": 0.82,
        "source_refs": [{"thread_key": "session:design", "line": 44}],
    },
]

SOURCE_ANCHORS = {
    "session:origin": ["小海马体", "机械飞升"],
    "session:design": ["foreground", "background", "audits"],
}

FUZZY_CASES = [
    {
        "cue": "小海马体 continuity 那条关系源头继续一下",
        "expected_title": "小海马体",
        "expected_thread_key": "session:origin",
        "anchors": ["小海马体"],
    },
    {
        "cue": "foreground consumes background audits 这个设计结论在哪",
        "expected_title": "foreground consumes; background audits",
        "expected_thread_key": "session:design",
        "anchors": ["foreground", "background"],
    },
]

GENERIC_CONTROLS = [
    "source agent memory",
    "not but system agent",
]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _opened_anchor_hits(match: dict[str, Any], anchors: list[str]) -> int:
    refs = [ref for ref in match.get("source_refs") or [] if isinstance(ref, dict)]
    source_terms: list[str] = []
    for ref in refs:
        source_terms.extend(SOURCE_ANCHORS.get(str(ref.get("thread_key") or ""), []))
    source_blob = " ".join(source_terms).casefold()
    return sum(1 for anchor in anchors if anchor.casefold() in source_blob)


def evaluate_source_semantic_candidates(*, recorded: bool = True) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        deterministic_path = root / "deterministic-only.jsonl"
        semantic_path = root / "semantic-triggers.jsonl"
        _write_jsonl(deterministic_path, [])
        _write_jsonl(semantic_path, RECORDED_TRIGGERS if recorded else [])

        cases: list[dict[str, Any]] = []
        semantic_lift_count = 0
        source_ref_success_count = 0
        anchor_hit_success_count = 0
        for case in FUZZY_CASES:
            deterministic_matches = gate.prompt_relevant_triggers(
                prompt=case["cue"],
                semantic_triggers_path=deterministic_path,
            )
            semantic_matches = gate.prompt_relevant_triggers(
                prompt=case["cue"],
                semantic_triggers_path=semantic_path,
            )
            top = semantic_matches[0] if semantic_matches else {}
            title_ok = str(top.get("title") or "") == case["expected_title"]
            refs = [ref for ref in top.get("source_refs") or [] if isinstance(ref, dict)]
            source_ok = any(
                str(ref.get("thread_key") or "") == case["expected_thread_key"] for ref in refs
            )
            anchor_hits = _opened_anchor_hits(top, case["anchors"]) if top else 0
            lifted = not deterministic_matches and title_ok
            semantic_lift_count += int(lifted)
            source_ref_success_count += int(source_ok)
            anchor_hit_success_count += int(anchor_hits > 0)
            cases.append(
                {
                    "cue_id": f"fuzzy_{len(cases) + 1}",
                    "deterministic_only_route_count": len(deterministic_matches),
                    "semantic_assisted_top_title": top.get("title"),
                    "semantic_lift": lifted,
                    "source_reopen_success": source_ok,
                    "opened_anchor_hits": anchor_hits,
                    "claim_authority": top.get("claim_authority"),
                }
            )

        false_positive_count = 0
        for cue in GENERIC_CONTROLS:
            matches = gate.prompt_relevant_triggers(
                prompt=cue,
                semantic_triggers_path=semantic_path,
            )
            false_positive_count += int(bool(matches))
            cases.append(
                {
                    "cue_id": f"generic_{len(cases) + 1}",
                    "semantic_assisted_route_count": len(matches),
                    "false_positive": bool(matches),
                }
            )

    if not recorded:
        status = "semantic_worker_unavailable"
        ok = True
    else:
        status = "sufficient" if semantic_lift_count >= 2 and false_positive_count == 0 else "insufficient"
        ok = status == "sufficient"
    return {
        "ok": ok,
        "status": status,
        "mode": "recorded_semantic_candidates" if recorded else "deterministic_no_key",
        "semantic_worker_unavailable": not recorded,
        "quality_gate_ok": bool(recorded and ok),
        "metrics": {
            "fuzzy_case_count": len(FUZZY_CASES),
            "semantic_lift_count": semantic_lift_count,
            "source_reopen_success_count": source_ref_success_count,
            "anchor_hit_success_count": anchor_hit_success_count,
            "generic_control_count": len(GENERIC_CONTROLS),
            "false_positive_count": false_positive_count,
            "live_model_call_count": 0,
        },
        "cases": cases,
        "cannot_claim": []
        if recorded
        else ["provider_backed_semantic_candidate_quality", "full_live_semantic_recall"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["recorded", "no-key"], default="recorded")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = evaluate_source_semantic_candidates(recorded=args.mode == "recorded")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(f"semantic lift: {payload['metrics']['semantic_lift_count']}")
        print(f"false positives: {payload['metrics']['false_positive_count']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
