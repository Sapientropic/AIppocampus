#!/usr/bin/env python3
"""Provider-conformance fixture benchmark for cross-provider memory surfaces.

This is a deterministic public-safe child slice for GitHub #988 / #981. It
checks provider/session identity, cross-provider source-reopen boundaries, host
injection demotion, and MCP drop-in metadata shape without requiring live
Claude Code, Codex, Cursor, Gemini, or MCP clients.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.provider_conformance_fixture.v1"
DEFAULT_FIXTURE = _paths.REPO_ROOT / "benchmark_corpus" / "provider_conformance" / "fixture.json"
EVIDENCE_GRAMMARS = {"bounded_evidence", "source_open"}
ROUTE_GRAMMARS = {"reopenable_route", *EVIDENCE_GRAMMARS}
INJECTED_ORIGINS = {"system", "tool", "injected"}
REQUIRED_MCP_FIELDS = {"provider", "session_id", "source_ref", "reopen_tool", "action_grammar"}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {path}")
    return payload


def _artifact_identity(artifact: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(artifact.get("provider") or ""),
        str(artifact.get("session_id") or ""),
        str(artifact.get("project_key") or ""),
    )


def _route_key_is_stable(artifact: Mapping[str, Any]) -> bool:
    provider, session_id, _ = _artifact_identity(artifact)
    route_key = str(artifact.get("route_key") or "")
    return bool(provider and session_id and route_key.startswith(f"{provider}:{session_id}:"))


def _detect_provider_conformance_failures(case: Mapping[str, Any]) -> list[str]:
    failures: set[str] = set()
    artifacts = [item for item in case.get("artifacts") or [] if isinstance(item, Mapping)]

    for artifact in artifacts:
        provider, session_id, project_key = _artifact_identity(artifact)
        action_grammar = str(artifact.get("action_grammar") or "")
        source_ref = str(artifact.get("source_ref") or "")
        source_reopenable = bool(artifact.get("source_reopenable"))
        content_origin = str(artifact.get("content_origin") or "")
        metadata_fields = set(_as_list(artifact.get("mcp_metadata_fields")))
        artifact_kind = str(artifact.get("artifact_kind") or "")
        consumer_provider = str(artifact.get("consumer_provider") or provider)

        if not (provider and session_id and project_key):
            failures.add("provider_conformance.missing_provider_session_identity")
        if not _route_key_is_stable(artifact):
            failures.add("provider_conformance.unstable_route_identity")
        if consumer_provider != provider and action_grammar in ROUTE_GRAMMARS:
            if not (source_ref and source_reopenable):
                failures.add("provider_conformance.cross_provider_route_without_reopenable_source")
        if content_origin in INJECTED_ORIGINS:
            if bool(artifact.get("durable_user_memory")) or action_grammar in EVIDENCE_GRAMMARS:
                failures.add("provider_conformance.injected_content_pollution")
        if artifact_kind == "mcp_tool_output":
            if not (source_ref and source_reopenable and REQUIRED_MCP_FIELDS.issubset(metadata_fields)):
                failures.add("provider_conformance.mcp_missing_source_ref_affordance")

    by_label_project: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for artifact in artifacts:
        key = (str(artifact.get("entity_label") or ""), str(artifact.get("project_key") or ""))
        if key[0] and key[1]:
            by_label_project.setdefault(key, []).append(artifact)
    for grouped in by_label_project.values():
        entity_keys = {str(item.get("entity_key") or "") for item in grouped}
        route_keys = {str(item.get("route_key") or "") for item in grouped}
        if len(entity_keys) > 1 and len(route_keys) != len(grouped):
            failures.add("provider_conformance.same_name_conflation")

    return sorted(failures)


def _source_route_count(case: Mapping[str, Any]) -> int:
    return sum(
        1
        for artifact in case.get("artifacts") or []
        if isinstance(artifact, Mapping)
        and str(artifact.get("action_grammar") or "") == "reopenable_route"
        and bool(artifact.get("source_reopenable"))
        and bool(str(artifact.get("source_ref") or ""))
    )


def _navigation_only_count(case: Mapping[str, Any]) -> int:
    return sum(
        1
        for artifact in case.get("artifacts") or []
        if isinstance(artifact, Mapping)
        and str(artifact.get("action_grammar") or "") in {"direction_only", "ignore_or_blocked"}
        and not bool(artifact.get("source_reopenable"))
    )


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    expected_failure_codes = sorted(set(_as_list(case.get("expected_failure_codes"))))
    detected_failure_codes = _detect_provider_conformance_failures(case)
    unexpected = sorted(set(detected_failure_codes) - set(expected_failure_codes))
    missing = sorted(set(expected_failure_codes) - set(detected_failure_codes))
    expectation = str(case.get("expectation") or "pass")
    passed = not unexpected and not missing
    if expectation == "pass":
        passed = passed and not detected_failure_codes
    return {
        "case_id": case.get("case_id"),
        "case_family": case.get("case_family"),
        "expectation": expectation,
        "expected_failure_codes": expected_failure_codes,
        "detected_failure_codes": detected_failure_codes,
        "unexpected_failure_codes": unexpected,
        "missing_expected_failure_codes": missing,
        "source_reopen_route_count": _source_route_count(case),
        "navigation_only_artifact_count": _navigation_only_count(case),
        "passed": passed,
        "artifacts": [_sanitized_artifact(item) for item in case.get("artifacts") or []],
    }


def validate_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            {
                "code": "unsupported_fixture_schema_version",
                "field": "schema_version",
                "message": "Unsupported provider-conformance fixture schema.",
            }
        )
    source = _as_mapping(fixture.get("source"))
    if "issues/988" not in str(source.get("issue") or ""):
        blockers.append(
            {
                "code": "missing_source_issue",
                "field": "source.issue",
                "message": "Provider conformance fixture must link GitHub #988.",
            }
        )
    provider_rows = [
        item for item in fixture.get("providers") or [] if isinstance(item, Mapping)
    ]
    provider_keys = {_artifact_identity(item) for item in provider_rows}
    if len(provider_keys) < 3:
        blockers.append(
            {
                "code": "insufficient_provider_surface",
                "field": "providers",
                "message": "Fixture must cover at least three provider/session surfaces.",
            }
        )
    cases = [item for item in fixture.get("cases") or [] if isinstance(item, Mapping)]
    case_ids = [str(item.get("case_id") or "") for item in cases]
    if len(set(case_ids)) != len(case_ids):
        blockers.append(
            {
                "code": "duplicate_case_id",
                "field": "cases.case_id",
                "message": "Case ids must be unique.",
            }
        )
    families = {str(item.get("case_family") or "") for item in cases}
    required_families = {
        "provider_session_identity",
        "cross_provider_correction",
        "copied_summary_boundary",
        "injected_content_pollution",
        "mcp_drop_in_boundary",
    }
    if not required_families.issubset(families):
        blockers.append(
            {
                "code": "missing_required_case_family",
                "field": "cases.case_family",
                "message": "Fixture does not cover all required #988 case families.",
            }
        )
    return {
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "provider_count": len(provider_keys),
        "case_count": len(cases),
        "case_families": sorted(families),
    }


def _sanitized_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    provider, session_id, project_key = _artifact_identity(artifact)
    metadata_fields = sorted(_as_list(artifact.get("mcp_metadata_fields")))
    return {
        "artifact_id": artifact.get("artifact_id"),
        "provider": provider,
        "consumer_provider": artifact.get("consumer_provider"),
        "session_id_present": bool(session_id),
        "project_key_present": bool(project_key),
        "entity_label": artifact.get("entity_label"),
        "entity_key": artifact.get("entity_key"),
        "artifact_kind": artifact.get("artifact_kind"),
        "content_origin": artifact.get("content_origin"),
        "action_grammar": artifact.get("action_grammar"),
        "route_identity_stable": _route_key_is_stable(artifact),
        "source_ref_present": bool(str(artifact.get("source_ref") or "")),
        "source_reopenable": bool(artifact.get("source_reopenable")),
        "durable_user_memory": bool(artifact.get("durable_user_memory")),
        "mcp_metadata_fields": metadata_fields,
        "mcp_evidence_drawer_ready": REQUIRED_MCP_FIELDS.issubset(set(metadata_fields)),
    }


def _metrics(cases: Sequence[Mapping[str, Any]], reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    family_counts = Counter(str(case.get("case_family") or "") for case in cases)
    detected_failures = [
        code for report in reports for code in _as_list(report.get("detected_failure_codes"))
    ]
    expected_failures = [
        code for report in reports for code in _as_list(report.get("expected_failure_codes"))
    ]
    artifacts = [
        artifact
        for case in cases
        for artifact in case.get("artifacts") or []
        if isinstance(artifact, Mapping)
    ]
    return {
        "case_count": len(cases),
        "case_family_counts": dict(family_counts),
        "provider_count": len({_artifact_identity(artifact) for artifact in artifacts}),
        "provider_conformance_failure_count": len(detected_failures),
        "expected_provider_conformance_failure_count": len(expected_failures),
        "unexpected_provider_conformance_failure_count": sum(
            len(_as_list(report.get("unexpected_failure_codes"))) for report in reports
        ),
        "missing_expected_failure_count": sum(
            len(_as_list(report.get("missing_expected_failure_codes"))) for report in reports
        ),
        "source_reopen_route_count": sum(
            int(report.get("source_reopen_route_count") or 0) for report in reports
        ),
        "navigation_only_artifact_count": sum(
            int(report.get("navigation_only_artifact_count") or 0) for report in reports
        ),
        "injected_content_demoted_count": sum(
            1
            for artifact in artifacts
            if str(artifact.get("content_origin") or "") in INJECTED_ORIGINS
            and not bool(artifact.get("durable_user_memory"))
            and str(artifact.get("action_grammar") or "") == "ignore_or_blocked"
        ),
        "mcp_evidence_drawer_ready_count": sum(
            1
            for artifact in artifacts
            if str(artifact.get("artifact_kind") or "") == "mcp_tool_output"
            and bool(str(artifact.get("source_ref") or ""))
            and bool(artifact.get("source_reopenable"))
            and REQUIRED_MCP_FIELDS.issubset(set(_as_list(artifact.get("mcp_metadata_fields"))))
        ),
        "same_name_conflation_failure_count": detected_failures.count(
            "provider_conformance.same_name_conflation"
        ),
        "failure_code_counts": dict(Counter(detected_failures)),
    }


def run_benchmark(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture = load_fixture(path)
    validation = validate_fixture(fixture)
    cases = [item for item in fixture.get("cases") or [] if isinstance(item, Mapping)]
    reports = [evaluate_case(case) for case in cases]
    metrics = _metrics(cases, reports)
    ok = (
        validation["ok"]
        and all(bool(report.get("passed")) for report in reports)
        and metrics["unexpected_provider_conformance_failure_count"] == 0
        and metrics["missing_expected_failure_count"] == 0
        and metrics["source_reopen_route_count"] >= 3
        and metrics["navigation_only_artifact_count"] >= 3
        and metrics["injected_content_demoted_count"] >= 2
        and metrics["mcp_evidence_drawer_ready_count"] >= 1
    )
    return {
        "kind": "aippocampus_provider_conformance_benchmark",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "config": {
            "fixture_id": fixture.get("fixture_id"),
            "uses_live_provider": False,
            "uses_private_history": False,
        },
        "source": dict(_as_mapping(fixture.get("source"))),
        "fixture_validation": validation,
        "metrics": metrics,
        "cases": reports,
        "privacy_boundary": {
            "public_safe_synthetic_fixtures": True,
            "raw_provider_logs_emitted": False,
            "raw_memory_blob_text_emitted": False,
            "source_ref_values_emitted": False,
            "absolute_paths_emitted": False,
            "secret_values_emitted": False,
        },
        "claim_boundary": (
            "Synthetic provider-conformance child fixture for #988. It validates "
            "metadata and authority boundaries, not live provider adapter quality."
        ),
        "cannot_claim": _as_list(fixture.get("cannot_claim")),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Fixture JSON path.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", help="Optional path for the JSON report.")
    args = parser.parse_args(argv)

    payload = run_benchmark(args.fixture)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output or args.output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(f"cases: {payload['metrics']['case_count']}")
        print(
            "provider conformance failures: "
            f"{payload['metrics']['provider_conformance_failure_count']}"
        )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
