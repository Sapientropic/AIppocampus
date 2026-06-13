#!/usr/bin/env python3
"""Build the first public-safe hippocampal recall diagnostic seed.

The generated JSONL is deliberately small. It proves the #229 fixture contract,
the #230 runner shape, and the #231 calibration categories without claiming the
full 50-scene / 350-case P1 matrix.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

import hippocampal_fixture_schema as schema

PUBLIC_SAFETY = {
    "synthetic_public_safe": True,
    "uses_private_history": False,
    "raw_private_text_included": False,
    "review_status": "human_authored_public_safe_seed",
}
FIXTURE_LICENSE = "CC0-compatible synthetic fixture text"
SCORER_ALLOWED_INPUTS = [
    "query",
    "candidate_refs",
    "source_reopen_result",
]
DEFAULT_ARMS = ("full_query", "keyword_only", "random_retrieval")


def _response(
    decision: str,
    *,
    confidence: float,
    evidence_refs: Sequence[str] = (),
    scent_refs: Sequence[str] = (),
    source_reopened: bool = False,
    claims: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "decision": decision,
        "confidence": confidence,
        "evidence_refs": list(evidence_refs),
        "scent_refs": list(scent_refs),
        "source_reopened": bool(source_reopened),
        "claims": list(claims),
    }


def _case(
    *,
    scene_id: str,
    case_id: str,
    degradation_level: str,
    interference_level: str,
    query: str,
    expected_decision: str,
    expected_source_refs: Sequence[str],
    acceptable_scent_refs: Sequence[str] = (),
    distractor_source_refs: Sequence[str] = (),
    forbidden_claims: Sequence[str] = (),
    ambiguity_policy: str = "single_target",
    baseline_outputs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_refs = sorted(
        set(expected_source_refs) | set(acceptable_scent_refs) | set(distractor_source_refs)
    )
    return {
        "dataset_id": schema.DATASET_ID,
        "schema_version": schema.FIXTURE_SCHEMA_VERSION,
        "fixture_license": FIXTURE_LICENSE,
        "public_safety": dict(PUBLIC_SAFETY),
        "source_issue_refs": [
            "https://github.com/Sapientropic/AIppocampus/issues/229",
            "https://github.com/Sapientropic/AIppocampus/issues/230",
            "https://github.com/Sapientropic/AIppocampus/issues/231",
        ],
        "design_doc_refs": [
            "docs/evidence/benchmarks/design/hippocampal-recall-plan.md",
        ],
        "scene_id": scene_id,
        "case_id": case_id,
        "degradation_level": degradation_level,
        "interference_level": interference_level,
        "query": query,
        "expected_decision": expected_decision,
        "expected_source_refs": list(expected_source_refs),
        "acceptable_scent_refs": list(acceptable_scent_refs),
        "distractor_source_refs": list(distractor_source_refs),
        "forbidden_claims": list(forbidden_claims),
        "ambiguity_policy": ambiguity_policy,
        "truth_source": "human_authored_fixture",
        "scorer_allowed_inputs": list(SCORER_ALLOWED_INPUTS),
        "candidate_source_refs": candidate_refs,
        "baseline_outputs": {arm: dict(output) for arm, output in baseline_outputs.items()},
    }


def build_fixture_rows() -> list[dict[str, Any]]:
    rows = [
        _case(
            scene_id="keyword_contract",
            case_id="keyword_contract__d0_i0",
            degradation_level="D0",
            interference_level="I0",
            query="Which source-backed route did we choose for the prompt hook contract?",
            expected_decision="evidence",
            expected_source_refs=["source:keyword_contract:target"],
            acceptable_scent_refs=["source:keyword_contract:target"],
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.93,
                    evidence_refs=["source:keyword_contract:target"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.84,
                    evidence_refs=["source:keyword_contract:target"],
                    source_reopened=True,
                ),
                "random_retrieval": _response("skip", confidence=0.12),
            },
        ),
        _case(
            scene_id="superseded_route",
            case_id="superseded_route__d1_i5",
            degradation_level="D1",
            interference_level="I5",
            query="The old route decision after it was replaced",
            expected_decision="evidence",
            expected_source_refs=["source:superseded_route:new"],
            acceptable_scent_refs=[
                "source:superseded_route:new",
                "source:superseded_route:old",
            ],
            distractor_source_refs=["source:superseded_route:old"],
            forbidden_claims=["The old route remains the current decision."],
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.89,
                    evidence_refs=["source:superseded_route:new"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.9,
                    evidence_refs=["source:superseded_route:old"],
                    source_reopened=True,
                ),
                "random_retrieval": _response(
                    "scent",
                    confidence=0.42,
                    scent_refs=[
                        "source:superseded_route:old",
                        "source:superseded_route:new",
                    ],
                ),
            },
        ),
        _case(
            scene_id="metaphor_cache",
            case_id="metaphor_cache__d2_i1",
            degradation_level="D2",
            interference_level="I1",
            query="That lantern metaphor for the cache rule",
            expected_decision="evidence",
            expected_source_refs=["source:metaphor_cache:target"],
            acceptable_scent_refs=["source:metaphor_cache:target"],
            distractor_source_refs=["source:metaphor_cache:neighbor"],
            forbidden_claims=["The neighbor cache rule was the chosen contract."],
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.82,
                    evidence_refs=["source:metaphor_cache:target"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "scent",
                    confidence=0.48,
                    scent_refs=["source:metaphor_cache:target"],
                ),
                "random_retrieval": _response("skip", confidence=0.18),
            },
        ),
        _case(
            scene_id="same_token_context",
            case_id="same_token_context__d2_i4",
            degradation_level="D2",
            interference_level="I4",
            query="The same token but the repo context meant the other memory",
            expected_decision="evidence",
            expected_source_refs=["source:same_token_context:repo"],
            acceptable_scent_refs=["source:same_token_context:repo"],
            distractor_source_refs=["source:same_token_context:personal"],
            forbidden_claims=["The personal note is enough for the repo contract."],
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.81,
                    evidence_refs=["source:same_token_context:repo"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.79,
                    evidence_refs=["source:same_token_context:personal"],
                    source_reopened=True,
                ),
                "random_retrieval": _response("skip", confidence=0.19),
            },
        ),
        _case(
            scene_id="ambiguous_hook",
            case_id="ambiguous_hook__d3_i3",
            degradation_level="D3",
            interference_level="I3",
            query="The tense little hook choice that might have two nearby causes",
            expected_decision="scent",
            expected_source_refs=["source:ambiguous_hook:alpha"],
            acceptable_scent_refs=["source:ambiguous_hook:alpha"],
            distractor_source_refs=["source:ambiguous_hook:beta"],
            forbidden_claims=["The alpha source alone proves the final answer."],
            ambiguity_policy="multi_candidate_scent",
            baseline_outputs={
                "full_query": _response(
                    "scent",
                    confidence=0.55,
                    scent_refs=[
                        "source:ambiguous_hook:alpha",
                        "source:ambiguous_hook:beta",
                    ],
                ),
                "keyword_only": _response(
                    "scent",
                    confidence=0.52,
                    scent_refs=["source:ambiguous_hook:beta"],
                ),
                "random_retrieval": _response("skip", confidence=0.16),
            },
        ),
        _case(
            scene_id="unsupported_hypothesis",
            case_id="unsupported_hypothesis__d3_i1",
            degradation_level="D3",
            interference_level="I1",
            query="The idea we only floated about promoting every extracted preference",
            expected_decision="skip",
            expected_source_refs=["source:unsupported_hypothesis:mention"],
            acceptable_scent_refs=["source:unsupported_hypothesis:mention"],
            forbidden_claims=["Every extracted preference should be promoted automatically."],
            ambiguity_policy="unsupported_skip",
            baseline_outputs={
                "full_query": _response("skip", confidence=0.28),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.77,
                    evidence_refs=["source:unsupported_hypothesis:mention"],
                    source_reopened=True,
                ),
                "random_retrieval": _response("skip", confidence=0.14),
            },
        ),
        _case(
            scene_id="context_boundary",
            case_id="context_boundary__d3_i2",
            degradation_level="D3",
            interference_level="I2",
            query="The careful boundary when a source sounds right but will not reopen",
            expected_decision="evidence",
            expected_source_refs=["source:context_boundary:target"],
            acceptable_scent_refs=["source:context_boundary:target"],
            distractor_source_refs=["source:context_boundary:near"],
            forbidden_claims=["A plausible source title is enough without reopen."],
            ambiguity_policy="source_required",
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.86,
                    evidence_refs=["source:context_boundary:target"],
                    source_reopened=False,
                ),
                "keyword_only": _response(
                    "scent",
                    confidence=0.47,
                    scent_refs=["source:context_boundary:target"],
                ),
                "random_retrieval": _response("skip", confidence=0.13),
            },
        ),
        _case(
            scene_id="stance_reversal",
            case_id="stance_reversal__d1_i3",
            degradation_level="D1",
            interference_level="I3",
            query="The reversal where the earlier stance must not win",
            expected_decision="evidence",
            expected_source_refs=["source:stance_reversal:current"],
            acceptable_scent_refs=[
                "source:stance_reversal:current",
                "source:stance_reversal:old",
            ],
            distractor_source_refs=["source:stance_reversal:old"],
            forbidden_claims=["The older stance is still the preferred implementation."],
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.83,
                    evidence_refs=["source:stance_reversal:current"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.81,
                    evidence_refs=["source:stance_reversal:old"],
                    source_reopened=True,
                    claims=["The older stance is still the preferred implementation."],
                ),
                "random_retrieval": _response("skip", confidence=0.2),
            },
        ),
        _case(
            scene_id="cross_language_note",
            case_id="cross_language_note__d4_i4",
            degradation_level="D4",
            interference_level="I4",
            query="那条中文碎片说的是 source reopen，不是表面最近的英文标题",
            expected_decision="evidence",
            expected_source_refs=["source:cross_language_note:target"],
            acceptable_scent_refs=["source:cross_language_note:target"],
            distractor_source_refs=["source:cross_language_note:surface_match"],
            forbidden_claims=["The surface-nearest English title is sufficient."],
            baseline_outputs={
                "full_query": _response(
                    "scent",
                    confidence=0.51,
                    scent_refs=["source:cross_language_note:target"],
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.8,
                    evidence_refs=["source:cross_language_note:surface_match"],
                    source_reopened=True,
                ),
                "random_retrieval": _response("skip", confidence=0.18),
            },
        ),
        _case(
            scene_id="structure_only",
            case_id="structure_only__d5_i2",
            degradation_level="D5",
            interference_level="I2",
            query="The one with three nested checks before the route could answer",
            expected_decision="scent",
            expected_source_refs=["source:structure_only:target"],
            acceptable_scent_refs=["source:structure_only:target"],
            distractor_source_refs=["source:structure_only:near"],
            ambiguity_policy="source_required",
            baseline_outputs={
                "full_query": _response(
                    "scent",
                    confidence=0.44,
                    scent_refs=["source:structure_only:target"],
                ),
                "keyword_only": _response("skip", confidence=0.2),
                "random_retrieval": _response("skip", confidence=0.13),
            },
        ),
        _case(
            scene_id="structure_warning_code",
            case_id="structure_warning_code__d5_i1",
            degradation_level="D5",
            interference_level="I1",
            query="The answer shaped like a code block followed by a caution note",
            expected_decision="evidence",
            expected_source_refs=["source:structure_warning_code:target"],
            acceptable_scent_refs=["source:structure_warning_code:target"],
            distractor_source_refs=["source:structure_warning_code:near"],
            forbidden_claims=["The nearby bulleted note was the code-block answer."],
            ambiguity_policy="source_required",
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.79,
                    evidence_refs=["source:structure_warning_code:target"],
                    source_reopened=True,
                ),
                "keyword_only": _response("skip", confidence=0.18),
                "random_retrieval": _response("skip", confidence=0.11),
            },
        ),
        _case(
            scene_id="structure_checklist_boundary",
            case_id="structure_checklist_boundary__d5_i3",
            degradation_level="D5",
            interference_level="I3",
            query="The one organized as three checks before a boundary decision",
            expected_decision="scent",
            expected_source_refs=["source:structure_checklist_boundary:target"],
            acceptable_scent_refs=["source:structure_checklist_boundary:target"],
            distractor_source_refs=["source:structure_checklist_boundary:neighbor"],
            forbidden_claims=["The neighbor checklist proves the boundary decision."],
            ambiguity_policy="source_required",
            baseline_outputs={
                "full_query": _response(
                    "scent",
                    confidence=0.58,
                    scent_refs=["source:structure_checklist_boundary:target"],
                ),
                "keyword_only": _response(
                    "scent",
                    confidence=0.41,
                    scent_refs=["source:structure_checklist_boundary:neighbor"],
                ),
                "random_retrieval": _response("skip", confidence=0.12),
            },
        ),
        _case(
            scene_id="time_cue",
            case_id="time_cue__d6_i5",
            degradation_level="D6",
            interference_level="I5",
            query="The after-lunch decision that replaced the morning answer",
            expected_decision="evidence",
            expected_source_refs=["source:time_cue:afternoon"],
            acceptable_scent_refs=[
                "source:time_cue:afternoon",
                "source:time_cue:morning",
            ],
            distractor_source_refs=["source:time_cue:morning"],
            forbidden_claims=["The morning answer is the current decision."],
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.76,
                    evidence_refs=["source:time_cue:afternoon"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.82,
                    evidence_refs=["source:time_cue:morning"],
                    source_reopened=True,
                ),
                "random_retrieval": _response("skip", confidence=0.18),
            },
        ),
        _case(
            scene_id="time_window_evening_patch",
            case_id="time_window_evening_patch__d6_i4",
            degradation_level="D6",
            interference_level="I4",
            query="The evening patch after the earlier rollback note",
            expected_decision="evidence",
            expected_source_refs=["source:time_window_evening_patch:evening"],
            acceptable_scent_refs=[
                "source:time_window_evening_patch:evening",
                "source:time_window_evening_patch:rollback",
            ],
            distractor_source_refs=["source:time_window_evening_patch:rollback"],
            forbidden_claims=["The rollback note is the current patch decision."],
            ambiguity_policy="single_target",
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.78,
                    evidence_refs=["source:time_window_evening_patch:evening"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "evidence",
                    confidence=0.8,
                    evidence_refs=["source:time_window_evening_patch:rollback"],
                    source_reopened=True,
                ),
                "random_retrieval": _response("skip", confidence=0.15),
            },
        ),
        _case(
            scene_id="time_window_followup",
            case_id="time_window_followup__d6_i1",
            degradation_level="D6",
            interference_level="I1",
            query="The follow-up from the next morning, not the draft from the night before",
            expected_decision="evidence",
            expected_source_refs=["source:time_window_followup:morning"],
            acceptable_scent_refs=[
                "source:time_window_followup:morning",
                "source:time_window_followup:draft",
            ],
            distractor_source_refs=["source:time_window_followup:draft"],
            forbidden_claims=["The night-before draft is the current follow-up."],
            ambiguity_policy="single_target",
            baseline_outputs={
                "full_query": _response(
                    "evidence",
                    confidence=0.8,
                    evidence_refs=["source:time_window_followup:morning"],
                    source_reopened=True,
                ),
                "keyword_only": _response(
                    "scent",
                    confidence=0.43,
                    scent_refs=["source:time_window_followup:draft"],
                ),
                "random_retrieval": _response("skip", confidence=0.14),
            },
        ),
        _case(
            scene_id="source_required_skip",
            case_id="source_required_skip__d0_i2",
            degradation_level="D0",
            interference_level="I2",
            query="What was the exact durable claim for the missing-source note?",
            expected_decision="skip",
            expected_source_refs=["source:source_required_skip:gap"],
            acceptable_scent_refs=["source:source_required_skip:gap"],
            distractor_source_refs=["source:source_required_skip:near"],
            forbidden_claims=["The missing-source note established a durable claim."],
            ambiguity_policy="unsupported_skip",
            baseline_outputs={
                "full_query": _response("skip", confidence=0.24),
                "keyword_only": _response(
                    "scent",
                    confidence=0.45,
                    scent_refs=["source:source_required_skip:near"],
                ),
                "random_retrieval": _response("skip", confidence=0.1),
            },
        ),
    ]
    missing_arms = [
        row["case_id"]
        for row in rows
        if set(row["baseline_outputs"]) != set(DEFAULT_ARMS)
    ]
    if missing_arms:
        raise RuntimeError(f"fixture rows missing baseline arms: {missing_arms}")
    return rows


def write_fixture(
    path: str | Path = schema.DEFAULT_FIXTURE,
    *,
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    fixture_rows = list(rows) if rows is not None else build_fixture_rows()
    validation = schema.validate_fixture(fixture_rows)
    if validation["ok"]:
        schema.write_fixture(fixture_rows, path)
    return {
        "ok": bool(validation["ok"]),
        "path": str(Path(path)),
        "case_count": validation["case_count"],
        "blocker_codes": validation["blocker_codes"],
        "coverage": validation["coverage"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=schema.DEFAULT_FIXTURE)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    rows = build_fixture_rows()
    report: dict[str, Any] = {
        "ok": True,
        "output": str(args.output),
        "fixture_dataset_id": schema.DATASET_ID,
        "fixture_schema_version": schema.FIXTURE_SCHEMA_VERSION,
        "fixture_version": schema.FIXTURE_VERSION,
        "fixture_seed": schema.FIXTURE_SEED,
        "validation": schema.validate_fixture(rows),
    }
    if not args.validate_only:
        write_report = write_fixture(args.output, rows=rows)
        report["ok"] = bool(write_report["ok"])
        report["write"] = write_report
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"hippocampal fixture rows: {report['validation']['case_count']}")
        print(f"valid: {report['validation']['ok']}")
        print(f"output: {args.output}")
    return 0 if report["ok"] and report["validation"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
