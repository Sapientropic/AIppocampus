#!/usr/bin/env python3
"""Schema helpers for the public-safe hippocampal recall fixture.

The fixture rows are synthetic, source-backed contracts for GitHub #229/#230/#231.
They intentionally repeat metadata per JSONL row so each case can be copied,
reviewed, and validated without relying on private registry state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

DATASET_ID = "hippocampal_synthetic_v1"
FIXTURE_SCHEMA_VERSION = "aippocampus.hippocampal_recall_fixture.v1"
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "hippocampal_fixtures"
    / "hippocampal_synthetic_v1.jsonl"
)
DENSITY_FLOOR = 5
DEGRADATION_LEVELS = tuple(f"D{level}" for level in range(7))
INTERFERENCE_LEVELS = tuple(f"I{level}" for level in range(6))
RELEASE_DEGRADATION_LEVELS = {"D0", "D1", "D2", "D3"}
EXPECTED_DECISIONS = {"skip", "scent", "evidence"}
AMBIGUITY_POLICIES = {
    "single_target",
    "multi_candidate_scent",
    "unsupported_skip",
    "source_required",
}
TRUTH_SOURCES = {"human_authored_fixture"}
ALLOWED_SCORER_INPUTS = {
    "query",
    "candidate_refs",
    "source_reopen_result",
}
FORBIDDEN_REPORT_FIELDS = {
    "internal_cue_list",
    "local_path",
    "raw_private_text",
    "raw_source_text",
    "source_snippet",
    "private_registry_path",
}
REQUIRED_FIELDS = {
    "dataset_id",
    "schema_version",
    "fixture_license",
    "public_safety",
    "scene_id",
    "case_id",
    "degradation_level",
    "interference_level",
    "query",
    "expected_decision",
    "expected_source_refs",
    "acceptable_scent_refs",
    "distractor_source_refs",
    "forbidden_claims",
    "ambiguity_policy",
    "truth_source",
    "scorer_allowed_inputs",
    "candidate_source_refs",
    "baseline_outputs",
}


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _blocker(code: str, field: str, message: str, *, case_id: str = "") -> dict[str, str]:
    payload = {"code": code, "field": field, "message": message}
    if case_id:
        payload["case_id"] = case_id
    return payload


def load_fixture(path: str | Path = DEFAULT_FIXTURE) -> list[dict[str, Any]]:
    fixture_path = Path(path)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(fixture_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"expected object row at {fixture_path}:{line_number}")
        rows.append(payload)
    return rows


def write_fixture(rows: Sequence[Mapping[str, Any]], path: str | Path = DEFAULT_FIXTURE) -> None:
    fixture_path = Path(path)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = "\n".join(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True) for row in rows
    )
    fixture_path.write_text(serialized + "\n", encoding="utf-8")


def cases_by_id(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("case_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("case_id")
    }


def _public_safety_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    safety_rows = [_as_mapping(row.get("public_safety")) for row in rows]
    return {
        "synthetic_public_safe": bool(rows)
        and all(bool(item.get("synthetic_public_safe")) for item in safety_rows),
        "uses_private_history": any(bool(item.get("uses_private_history")) for item in safety_rows),
        "raw_private_text_included": any(
            bool(item.get("raw_private_text_included")) for item in safety_rows
        ),
        "fixture_licenses": sorted({str(row.get("fixture_license") or "") for row in rows}),
    }


def _case_blockers(row: Mapping[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    case_id = str(row.get("case_id") or "<missing>")
    missing = sorted(field for field in REQUIRED_FIELDS if field not in row)
    for field in missing:
        code = f"missing_{field}" if field == "ambiguity_policy" else "missing_required_field"
        blockers.append(
            _blocker(
                code,
                field,
                "Fixture row is missing a required field.",
                case_id=case_id,
            )
        )

    if row.get("dataset_id") != DATASET_ID:
        blockers.append(
            _blocker("unsupported_dataset_id", "dataset_id", "Unsupported dataset id.", case_id=case_id)
        )
    if row.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _blocker(
                "unsupported_fixture_schema_version",
                "schema_version",
                "Unsupported hippocampal recall fixture schema.",
                case_id=case_id,
            )
        )
    if row.get("degradation_level") not in DEGRADATION_LEVELS:
        blockers.append(
            _blocker(
                "invalid_degradation_level",
                "degradation_level",
                "Degradation level must be D0-D6.",
                case_id=case_id,
            )
        )
    if row.get("interference_level") not in INTERFERENCE_LEVELS:
        blockers.append(
            _blocker(
                "invalid_interference_level",
                "interference_level",
                "Interference level must be I0-I5.",
                case_id=case_id,
            )
        )
    if row.get("expected_decision") not in EXPECTED_DECISIONS:
        blockers.append(
            _blocker(
                "invalid_expected_decision",
                "expected_decision",
                "Expected decision must be skip, scent, or evidence.",
                case_id=case_id,
            )
        )
    if not _as_list(row.get("expected_source_refs")):
        blockers.append(
            _blocker(
                "missing_source_refs",
                "expected_source_refs",
                "Each row needs at least one source ref, including skip/scent cases.",
                case_id=case_id,
            )
        )
    if "ambiguity_policy" not in row:
        blockers.append(
            _blocker(
                "missing_ambiguity_policy",
                "ambiguity_policy",
                "Ambiguity policy must be explicit.",
                case_id=case_id,
            )
        )
    elif row.get("ambiguity_policy") not in AMBIGUITY_POLICIES:
        blockers.append(
            _blocker(
                "unsupported_ambiguity_policy",
                "ambiguity_policy",
                "Unsupported ambiguity policy.",
                case_id=case_id,
            )
        )
    if row.get("truth_source") not in TRUTH_SOURCES:
        blockers.append(
            _blocker(
                "unsupported_truth_source",
                "truth_source",
                "Fixture labels must come from the human-authored synthetic fixture.",
                case_id=case_id,
            )
        )

    scorer_inputs = set(_as_list(row.get("scorer_allowed_inputs")))
    if not scorer_inputs or not scorer_inputs.issubset(ALLOWED_SCORER_INPUTS):
        blockers.append(
            _blocker(
                "unsupported_scorer_input",
                "scorer_allowed_inputs",
                "Scorer inputs must not expose internal cue lists or private source text.",
                case_id=case_id,
            )
        )
    if FORBIDDEN_REPORT_FIELDS & set(row):
        blockers.append(
            _blocker(
                "forbidden_fixture_field",
                "row",
                "Fixture row contains a private or internal-only field.",
                case_id=case_id,
            )
        )

    expected_refs = set(_as_list(row.get("expected_source_refs")))
    distractor_refs = set(_as_list(row.get("distractor_source_refs")))
    if expected_refs & distractor_refs:
        blockers.append(
            _blocker(
                "source_ref_role_overlap",
                "expected_source_refs",
                "Expected refs and distractor refs must be disjoint.",
                case_id=case_id,
            )
        )

    safety = _as_mapping(row.get("public_safety"))
    if not bool(safety.get("synthetic_public_safe")) or bool(safety.get("uses_private_history")):
        blockers.append(
            _blocker(
                "invalid_public_safety_contract",
                "public_safety",
                "Fixture rows must be public-safe synthetic and must not use private history.",
                case_id=case_id,
            )
        )
    if bool(safety.get("raw_private_text_included")):
        blockers.append(
            _blocker(
                "raw_private_text_in_fixture",
                "public_safety.raw_private_text_included",
                "Committed fixture rows must not include raw private text.",
                case_id=case_id,
            )
        )
    return blockers


def _cell_density(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    counts = {
        f"{degradation}/{interference}": 0
        for degradation in DEGRADATION_LEVELS
        for interference in INTERFERENCE_LEVELS
    }
    for row in rows:
        key = f"{row.get('degradation_level')}/{row.get('interference_level')}"
        if key in counts:
            counts[key] += 1

    density: dict[str, dict[str, Any]] = {}
    for degradation in DEGRADATION_LEVELS:
        for interference in INTERFERENCE_LEVELS:
            key = f"{degradation}/{interference}"
            count = counts[key]
            if count < DENSITY_FLOOR:
                status = "diagnostic_only"
            elif degradation in RELEASE_DEGRADATION_LEVELS:
                status = "release_gate"
            else:
                status = "exploratory"
            density[key] = {
                "case_count": count,
                "density_floor": DENSITY_FLOOR,
                "coverage_status": status,
                "phase": "exploratory" if degradation not in RELEASE_DEGRADATION_LEVELS else "p1_gate",
            }
    return density


def validate_fixture(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if not rows:
        blockers.append(_blocker("empty_fixture", "rows", "Fixture must contain at least one row."))

    case_ids = [str(row.get("case_id") or "") for row in rows]
    if len(set(case_ids)) != len(case_ids):
        blockers.append(_blocker("duplicate_case_id", "case_id", "Case ids must be unique."))

    dataset_ids = {str(row.get("dataset_id") or "") for row in rows}
    for row in rows:
        blockers.extend(_case_blockers(row))

    density = _cell_density(rows)
    diagnostic_only = [
        key for key, payload in density.items() if payload["coverage_status"] == "diagnostic_only"
    ]
    release_gate_cells = [
        key for key, payload in density.items() if payload["coverage_status"] == "release_gate"
    ]
    all_cells_dense = all(
        payload["case_count"] >= DENSITY_FLOOR for payload in density.values()
    )
    public_safety = _public_safety_report(rows)
    return {
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "dataset_id": DATASET_ID if dataset_ids == {DATASET_ID} else sorted(dataset_ids),
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "case_count": len(rows),
        "scene_count": len({str(row.get("scene_id") or "") for row in rows if row.get("scene_id")}),
        "density_floor": DENSITY_FLOOR,
        "cell_density": density,
        "diagnostic_only_cells": diagnostic_only,
        "release_gate_cells": release_gate_cells,
        "coverage": {
            "full_p1_matrix_claim": bool(all_cells_dense),
            "diagnostic_only_cell_count": len(diagnostic_only),
            "release_gate_cell_count": len(release_gate_cells),
            "d4_d6_exploratory": True,
        },
        "public_safety": public_safety,
    }


def sanitized_case(row: Mapping[str, Any]) -> dict[str, Any]:
    expected_refs = _as_list(row.get("expected_source_refs"))
    acceptable_refs = _as_list(row.get("acceptable_scent_refs"))
    distractor_refs = _as_list(row.get("distractor_source_refs"))
    return {
        "dataset_id": row.get("dataset_id"),
        "scene_id": row.get("scene_id"),
        "case_id": row.get("case_id"),
        "degradation_level": row.get("degradation_level"),
        "interference_level": row.get("interference_level"),
        "expected_decision": row.get("expected_decision"),
        "ambiguity_policy": row.get("ambiguity_policy"),
        "truth_source": row.get("truth_source"),
        "query_sha1": sha1_text(str(row.get("query") or ""))[:16],
        "expected_source_ref_hashes": [sha1_text(ref)[:16] for ref in sorted(expected_refs)],
        "acceptable_scent_ref_hashes": [
            sha1_text(ref)[:16] for ref in sorted(acceptable_refs)
        ],
        "distractor_source_ref_hashes": [
            sha1_text(ref)[:16] for ref in sorted(distractor_refs)
        ],
        "scorer_allowed_inputs": sorted(_as_list(row.get("scorer_allowed_inputs"))),
    }
