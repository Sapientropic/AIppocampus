#!/usr/bin/env python3
"""Build VCS future-event benchmark fixtures from normalized public rows.

This adapter is deliberately boring: it does not download MSR/Gerrit/SATD
corpora or infer soft labels. It only groups already-curated public event-link
rows into the benchmark schema consumed by
`benchmark_vcs_future_event_recall.py`.

The guardrail matters: many public VCS datasets are usable for local public
reports but are not automatically safe to redistribute inside this repository.
The builder therefore defaults to CC0 output and requires an explicit opt-in for
non-CC0 local outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.aippocampus import _paths

_paths.ensure_paths()

from benchmarks.aippocampus import benchmark_vcs_future_event_recall as recall

SCHEMA_VERSION = 1
DEFAULT_DATASET_ID = "aippocampus_vcs_future_events_built_v1"
DEFAULT_LICENSE = "CC0-1.0"
DEFAULT_SOURCE_FAMILY = "public_vcs_curated"
ALLOWED_FAMILIES = {
    "rejected_route",
    "reopen_condition",
    "tacit_constraint",
    "workaround_rationale",
    "stale_assumption_corrected",
    "anti_drift_negative",
}
CANONICAL_DISCOVERY_QUERY_FAMILIES = ("again", "reland", "revert", "workaround")
SYNONYM_DISCOVERY_TERMS = ("backout", "patch", "rollback", "undo")
SAFE_DISCOVERY_LABEL_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz0123456789_- "
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def read_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise ValueError(f"expected JSON array in {path}")
        return [dict(row) for row in rows]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value] if value else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def safe_discovery_label(value: Any, *, default: str = "unknown") -> str:
    text = compact_optional_text(value).casefold()
    if not text:
        return default
    if len(text) > 80:
        return "redacted_label"
    if any(ch in text for ch in ("\\", "/", ":", "@")):
        return "redacted_label"
    if not set(text) <= SAFE_DISCOVERY_LABEL_CHARS:
        return "redacted_label"
    return text


def discovery_metadata(row: dict[str, Any]) -> dict[str, Any]:
    nested_meta = nested(row, "candidate_discovery")
    if not nested_meta and not any(
        key in row
        for key in (
            "source_surface",
            "source_surfaces",
            "query_term",
            "query_terms",
            "manual_decision",
            "candidate_decision",
            "manual_reason_code",
            "sampled_miss",
            "missed_by_narrow_query",
        )
    ):
        return {}
    meta = dict(nested_meta)
    for key in (
        "source_surface",
        "source_surfaces",
        "query_term",
        "query_terms",
        "manual_decision",
        "candidate_decision",
        "manual_reason_code",
        "reason_code",
        "sampled_miss",
        "missed_by_narrow_query",
    ):
        if key not in meta and key in row:
            meta[key] = row[key]
    return meta


def event_family_for_row(row: dict[str, Any]) -> str:
    event = nested(row, "future_event")
    return safe_discovery_label(first_value(event.get("family"), row.get("family")))


def proportion_counts(counter: Counter[str]) -> dict[str, dict[str, Any]]:
    total = sum(counter.values())
    return {
        key: {"count": count, "proportion": round(count / total, 4) if total else 0.0}
        for key, count in sorted(counter.items())
    }


def summarize_candidate_discovery_bias(
    input_rows: list[dict[str, Any]],
    *,
    audit_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize license-safe candidate-discovery metadata.

    This reports how benchmark candidates were found and reviewed; it must not
    infer gold from raw PR bodies or emit reviewer text. Keep it as audit
    telemetry, not a coverage proof.
    """
    records = [row for row in [*input_rows, *(audit_rows or [])] if discovery_metadata(row)]
    surface_counts: Counter[str] = Counter()
    query_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    sampled_count = 0
    sampled_miss_count = 0

    for row in records:
        meta = discovery_metadata(row)
        surfaces = as_string_list(
            meta.get("source_surfaces")
            or meta.get("source_surface")
            or meta.get("search_surfaces")
            or meta.get("surface")
        )
        for surface in surfaces or ["unknown"]:
            surface_counts[safe_discovery_label(surface)] += 1

        query_terms = as_string_list(
            meta.get("query_terms")
            or meta.get("query_term")
            or meta.get("matched_terms")
            or meta.get("query_family")
        )
        for query_term in query_terms or ["unknown"]:
            query_counts[safe_discovery_label(query_term)] += 1

        decision = safe_discovery_label(
            first_value(
                meta.get("manual_decision"),
                meta.get("candidate_decision"),
                default="unknown",
            )
        )
        decision_counts[decision] += 1

        reason_code = safe_discovery_label(
            first_value(meta.get("manual_reason_code"), meta.get("reason_code"))
        )
        if reason_code != "unknown":
            reason_counts[reason_code] += 1

        family_counts[event_family_for_row(row)] += 1

        sampled_miss_value = meta.get("sampled_miss", meta.get("missed_by_narrow_query"))
        if sampled_miss_value is not None:
            sampled_count += 1
            sampled_miss_count += int(
                as_bool(sampled_miss_value, field_name="candidate_discovery.sampled_miss")
            )

    observed_required = sorted(
        family for family in CANONICAL_DISCOVERY_QUERY_FAMILIES if query_counts.get(family, 0) > 0
    )
    observed_synonyms = sorted(
        synonym for synonym in SYNONYM_DISCOVERY_TERMS if query_counts.get(synonym, 0) > 0
    )
    return {
        "available": bool(records),
        "record_count": len(records),
        "source_surface_mix": proportion_counts(surface_counts),
        "query_term_hit_mix_by_family": dict(sorted(query_counts.items())),
        "manual_decision_counts": dict(sorted(decision_counts.items())),
        "manual_reason_code_counts": dict(sorted(reason_counts.items())),
        "event_family_balance": proportion_counts(family_counts),
        "synonym_coverage": {
            "required_families": list(CANONICAL_DISCOVERY_QUERY_FAMILIES),
            "observed_required_families": observed_required,
            "missing_required_families": [
                family
                for family in CANONICAL_DISCOVERY_QUERY_FAMILIES
                if family not in observed_required
            ],
            "synonym_terms": list(SYNONYM_DISCOVERY_TERMS),
            "observed_synonym_terms": observed_synonyms,
        },
        "sampled_miss_rate": {
            "available": sampled_count > 0,
            "sample_count": sampled_count,
            "miss_count": sampled_miss_count,
            "rate": round(sampled_miss_count / sampled_count, 4) if sampled_count else 0.0,
        },
        "claim_boundary": (
            "Candidate discovery bias is audit telemetry for the curated gold "
            "universe. It is not a wild-corpus coverage claim and must not emit "
            "raw PR bodies, review text, local paths, or non-redistributable snippets."
        ),
    }


def as_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"{field_name} must be a boolean-like value")


def first_value(*values: Any, default: str = "") -> str:
    for value in values:
        if value is not None and str(value) != "":
            return str(value)
    return default


def nested(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return dict(value) if isinstance(value, dict) else {}


def compact_optional_text(value: Any) -> str:
    text = str(value or "").strip()
    return " ".join(text.split())


def is_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def normalized_past_source(row: dict[str, Any]) -> dict[str, Any]:
    source = nested(row, "past_source")
    source_id = first_value(source.get("source_id"), row.get("past_source_id"))
    if not source_id:
        raise ValueError("past_source.source_id or past_source_id is required")
    result: dict[str, Any] = {
        "source_id": source_id,
        "kind": first_value(source.get("kind"), row.get("past_kind"), default="vcs_source"),
        "timestamp": first_value(source.get("timestamp"), row.get("past_timestamp")),
        "text": compact_optional_text(first_value(source.get("text"), row.get("past_text"))),
    }
    public_url = first_value(source.get("public_url"), row.get("past_public_url"))
    source_dataset_id = first_value(source.get("source_dataset_id"), row.get("source_dataset_id"))
    if public_url:
        result["public_url"] = public_url
    if source_dataset_id:
        result["source_dataset_id"] = source_dataset_id
    if "behavior_backed" in source or "behavior_backed" in row:
        result["behavior_backed"] = as_bool(
            source.get("behavior_backed", row.get("behavior_backed")),
            field_name=f"{source_id}.behavior_backed",
        )
    for optional_key in (
        "tool_name",
        "command_class",
        "tool_intent",
        "command_family",
        "target_class",
        "test_target_class",
        "failure_family",
        "path_categories",
        "path_extensions",
        "path_fingerprints",
        "generated_file",
        "generated_file_reason",
        "exit_code",
        "artifact_sha1",
        "diff_sha1",
        "observation_sha1",
    ):
        raw_optional_value = source.get(optional_key, row.get(optional_key))
        optional_value = (
            raw_optional_value
            if isinstance(raw_optional_value, list | bool)
            else first_value(raw_optional_value)
        )
        if is_present(optional_value):
            if optional_key == "exit_code":
                try:
                    result[optional_key] = int(str(raw_optional_value))
                except (TypeError, ValueError):
                    result[optional_key] = optional_value
            else:
                result[optional_key] = optional_value
    return {key: value for key, value in result.items() if is_present(value)}


def normalized_future_event(row: dict[str, Any]) -> dict[str, Any]:
    event = nested(row, "future_event")
    event_id = first_value(event.get("event_id"), row.get("future_event_id"), row.get("event_id"))
    if not event_id:
        raise ValueError("future_event.event_id or event_id is required")
    family = first_value(event.get("family"), row.get("family"))
    if family not in ALLOWED_FAMILIES:
        raise ValueError(f"unsupported family for event {event_id}: {family!r}")
    hard_event_kind = first_value(event.get("hard_event_kind"), row.get("hard_event_kind"))
    if hard_event_kind not in recall.HARD_EVENT_KINDS:
        raise ValueError(f"unsupported hard_event_kind for event {event_id}: {hard_event_kind!r}")
    required_sources = as_string_list(
        event.get("required_past_source_ids", row.get("required_past_source_ids"))
    )
    result = {
        "event_id": event_id,
        "family": family,
        "hard_event_kind": hard_event_kind,
        "timestamp": first_value(event.get("timestamp"), row.get("event_timestamp")),
        "flag_worthy": as_bool(
            event.get("flag_worthy", row.get("flag_worthy")),
            field_name=f"{event_id}.flag_worthy",
        ),
        "text": compact_optional_text(first_value(event.get("text"), row.get("event_text"))),
        "required_past_source_ids": sorted(set(required_sources)),
    }
    expected_signal = first_value(event.get("expected_signal"), row.get("expected_signal"))
    public_url = first_value(event.get("public_url"), row.get("event_public_url"))
    source_dataset_id = first_value(event.get("source_dataset_id"), row.get("source_dataset_id"))
    source_degradation = first_value(event.get("source_degradation"), row.get("source_degradation"))
    if expected_signal:
        result["expected_signal"] = compact_optional_text(expected_signal)
    if public_url:
        result["public_url"] = public_url
    if source_dataset_id:
        result["source_dataset_id"] = source_dataset_id
    if source_degradation:
        result["source_degradation"] = source_degradation
    for anti_drift_key in ("anti_drift_family_under_test", "anti_drift_contrast_family"):
        anti_drift_value = first_value(event.get(anti_drift_key), row.get(anti_drift_key))
        if anti_drift_value:
            result[anti_drift_key] = anti_drift_value
    return {key: value for key, value in result.items() if is_present(value)}


def merge_unique(
    bucket: OrderedDict[str, dict[str, Any]],
    *,
    item: dict[str, Any],
    item_id_key: str,
    merge_list_keys: set[str] | None = None,
) -> None:
    item_id = str(item.get(item_id_key) or "")
    if not item_id:
        raise ValueError(f"missing {item_id_key}")
    merge_list_keys = merge_list_keys or set()
    existing = bucket.get(item_id)
    if existing is None:
        bucket[item_id] = item
        return

    merged = dict(existing)
    for key, value in item.items():
        if key in merge_list_keys:
            merged[key] = sorted(
                set(as_string_list(existing.get(key))) | set(as_string_list(value))
            )
            continue
        if not is_present(value):
            continue
        if key not in merged or not is_present(merged.get(key)):
            merged[key] = value
            continue
        if merged[key] != value:
            raise ValueError(f"conflicting duplicate {item_id_key} {item_id}")
    bucket[item_id] = merged


def build_fixture_rows(
    input_rows: list[dict[str, Any]],
    *,
    dataset_id: str = DEFAULT_DATASET_ID,
    license_id: str = DEFAULT_LICENSE,
    source_family: str = DEFAULT_SOURCE_FAMILY,
    allow_non_cc0_output: bool = False,
    candidate_discovery_audit_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not input_rows:
        raise ValueError("input rows are empty")
    if license_id.upper() != "CC0-1.0" and not allow_non_cc0_output:
        raise ValueError(
            "non-CC0 VCS fixture output requires --allow-non-cc0-output and should "
            "stay out of the checked-in benchmark corpus unless redistribution is verified"
        )

    projects: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for index, row in enumerate(input_rows, start=1):
        project_id = first_value(row.get("project_id"))
        if not project_id:
            raise ValueError(f"row {index}: project_id is required")
        row_license = first_value(row.get("license"), default=license_id)
        if row_license.upper() != "CC0-1.0" and not allow_non_cc0_output:
            raise ValueError(
                f"row {index}: non-CC0 license {row_license!r} requires "
                "--allow-non-cc0-output"
            )
        project = projects.setdefault(
            project_id,
            {
                "dataset_id": first_value(row.get("dataset_id"), default=dataset_id),
                "schema_version": SCHEMA_VERSION,
                "license": row_license,
                "project_id": project_id,
                "source_family": first_value(row.get("source_family"), default=source_family),
                "past_window": OrderedDict(),
                "future_window": OrderedDict(),
            },
        )
        project_label = first_value(row.get("project_label"))
        if project_label:
            project["project_label"] = project_label

        source = normalized_past_source(row)
        event = normalized_future_event(row)
        if bool(event.get("flag_worthy")) and not event.get("required_past_source_ids"):
            raise ValueError(f"row {index}: flag-worthy event {event['event_id']} needs past sources")
        merge_unique(
            project["past_window"],
            item=source,
            item_id_key="source_id",
        )
        merge_unique(
            project["future_window"],
            item=event,
            item_id_key="event_id",
            merge_list_keys={"required_past_source_ids"},
        )

    candidate_discovery_bias = summarize_candidate_discovery_bias(
        input_rows,
        audit_rows=candidate_discovery_audit_rows,
    )
    output_rows: list[dict[str, Any]] = []
    for project_id in sorted(projects):
        project = projects[project_id]
        row = {
            key: value
            for key, value in project.items()
            if key not in {"past_window", "future_window"} and is_present(value)
        }
        row["candidate_discovery_bias"] = candidate_discovery_bias
        row["past_window"] = [
            project["past_window"][source_id] for source_id in sorted(project["past_window"])
        ]
        row["future_window"] = [
            project["future_window"][event_id] for event_id in sorted(project["future_window"])
        ]
        output_rows.append(row)
    return output_rows


def load_clean_source_events(path: Path | str) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(read_json_or_jsonl(Path(path)), start=1):
        event_id = first_value(row.get("event_id"), row.get("id"))
        if not event_id:
            raise ValueError(f"clean-source event row {index} missing event_id")
        if event_id in events:
            raise ValueError(f"duplicate clean-source event_id {event_id}")
        events[event_id] = row
    return events


def past_source_from_clean_event(event: dict[str, Any]) -> dict[str, Any]:
    source_id = first_value(event.get("event_id"), event.get("id"))
    if not source_id:
        raise ValueError("clean-source event missing event_id")
    source = {
        "source_id": source_id,
        "kind": first_value(event.get("hard_event_kind"), event.get("event_kind"), default="tool_event"),
        "timestamp": first_value(event.get("timestamp")),
        "text": compact_optional_text(
            first_value(event.get("text"), event.get("hard_event_kind"), event.get("event_kind"))
        ),
        "behavior_backed": as_bool(event.get("behavior_backed", True), field_name=f"{source_id}.behavior_backed"),
    }
    for key in (
        "source_ref",
        "tool_name",
        "command_class",
        "tool_intent",
        "command_family",
        "target_class",
        "test_target_class",
        "failure_family",
        "path_categories",
        "path_extensions",
        "path_fingerprints",
        "generated_file",
        "generated_file_reason",
        "exit_code",
        "input_sha256",
        "observation_sha256",
        "artifact_sha1",
        "diff_sha1",
    ):
        value = event.get(key)
        if is_present(value):
            source[key] = value
    return {key: value for key, value in source.items() if is_present(value)}


def event_link_rows_from_clean_events(
    *,
    clean_events: dict[str, dict[str, Any]],
    link_rows: list[dict[str, Any]],
    dataset_id: str,
    license_id: str,
    source_family: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, link in enumerate(link_rows, start=1):
        past_event_ids = as_string_list(link.get("past_event_ids") or link.get("past_source_ids"))
        if not past_event_ids:
            raise ValueError(f"link row {index}: past_event_ids is required")
        future_event = nested(link, "future_event") or {
            key: value
            for key, value in link.items()
            if key
            in {
                "event_id",
                "future_event_id",
                "family",
                "hard_event_kind",
                "event_timestamp",
                "timestamp",
                "flag_worthy",
                "event_text",
                "text",
                "expected_signal",
                "event_public_url",
                "public_url",
                "anti_drift_family_under_test",
                "anti_drift_contrast_family",
                "source_degradation",
            }
        }
        required_sources = as_string_list(
            future_event.get("required_past_source_ids")
            or link.get("required_past_source_ids")
            or past_event_ids
        )
        future_event = dict(future_event)
        future_event["required_past_source_ids"] = sorted(set(required_sources))
        for past_event_id in past_event_ids:
            clean_event = clean_events.get(past_event_id)
            if clean_event is None:
                raise ValueError(f"link row {index}: unknown past_event_id {past_event_id}")
            rows.append(
                {
                    "dataset_id": first_value(link.get("dataset_id"), default=dataset_id),
                    "license": first_value(link.get("license"), default=license_id),
                    "project_id": first_value(link.get("project_id"), default="rollout-project"),
                    "project_label": first_value(link.get("project_label")),
                    "source_family": first_value(link.get("source_family"), default=source_family),
                    "candidate_discovery": nested(link, "candidate_discovery"),
                    "past_source": past_source_from_clean_event(clean_event),
                    "future_event": future_event,
                }
            )
    return rows


def build_fixture_from_clean_events(
    *,
    clean_source_events_path: Path | str,
    links_path: Path | str,
    output_path: Path | str,
    dataset_id: str = DEFAULT_DATASET_ID,
    license_id: str = DEFAULT_LICENSE,
    source_family: str = "agent_rollout_behavior_clean_source",
    allow_non_cc0_output: bool = False,
    candidate_discovery_audit_path: Path | str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    clean_events_path = Path(clean_source_events_path).resolve()
    links = Path(links_path).resolve()
    destination = Path(output_path).resolve()
    clean_events = load_clean_source_events(clean_events_path)
    link_rows = read_json_or_jsonl(links)
    audit_rows = (
        read_json_or_jsonl(Path(candidate_discovery_audit_path).resolve())
        if candidate_discovery_audit_path
        else None
    )
    normalized_rows = event_link_rows_from_clean_events(
        clean_events=clean_events,
        link_rows=link_rows,
        dataset_id=dataset_id,
        license_id=license_id,
        source_family=source_family,
    )
    output_rows = build_fixture_rows(
        normalized_rows,
        dataset_id=dataset_id,
        license_id=license_id,
        source_family=source_family,
        allow_non_cc0_output=allow_non_cc0_output,
        candidate_discovery_audit_rows=audit_rows,
    )
    write_jsonl(destination, output_rows)
    dataset = recall.load_dataset(
        destination,
        require_cc0=not allow_non_cc0_output,
    )
    return {
        "kind": "aippocampus_rollout_behavior_fixture_builder",
        "status": "fixture_built_from_clean_source_events",
        "ok": True,
        "generated_at": now_utc(),
        "clean_source_events_path_sha1": sha1_text(str(clean_events_path))[:16],
        "links_path_sha1": sha1_text(str(links))[:16],
        "output_path_sha1": sha1_text(str(destination))[:16],
        "config": {
            "dataset_id": dataset_id,
            "license": license_id,
            "source_family": source_family,
            "allow_non_cc0_output": allow_non_cc0_output,
        },
        "metrics": {
            "clean_source_event_count": len(clean_events),
            "link_row_count": len(link_rows),
            "project_count": len(dataset.rows),
            "future_event_count": len(dataset.events_by_id),
            "flag_worthy_event_count": len(dataset.flag_worthy_event_ids),
            "non_flag_future_event_count": len(dataset.non_flag_event_ids),
        },
        "candidate_discovery_bias": summarize_candidate_discovery_bias(
            normalized_rows,
            audit_rows=audit_rows,
        ),
        "claim_boundary": (
            "This builder links curated clean-source behavior events to hard "
            "future labels. The links remain human/program-curated gold; the "
            "builder does not infer rejected routes from raw traces by itself."
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def build_fixture(
    *,
    input_path: Path | str,
    output_path: Path | str,
    dataset_id: str = DEFAULT_DATASET_ID,
    license_id: str = DEFAULT_LICENSE,
    source_family: str = DEFAULT_SOURCE_FAMILY,
    allow_non_cc0_output: bool = False,
    candidate_discovery_audit_path: Path | str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    source_path = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    input_rows = read_json_or_jsonl(source_path)
    audit_rows = (
        read_json_or_jsonl(Path(candidate_discovery_audit_path).resolve())
        if candidate_discovery_audit_path
        else None
    )
    output_rows = build_fixture_rows(
        input_rows,
        dataset_id=dataset_id,
        license_id=license_id,
        source_family=source_family,
        allow_non_cc0_output=allow_non_cc0_output,
        candidate_discovery_audit_rows=audit_rows,
    )
    write_jsonl(destination, output_rows)
    dataset = recall.load_dataset(
        destination,
        require_cc0=not allow_non_cc0_output,
    )
    return {
        "kind": "aippocampus_vcs_future_event_fixture_builder",
        "status": "fixture_built",
        "ok": True,
        "generated_at": now_utc(),
        "input_path_sha1": sha1_text(str(source_path))[:16],
        "output_path_sha1": sha1_text(str(destination))[:16],
        "config": {
            "dataset_id": dataset_id,
            "license": license_id,
            "source_family": source_family,
            "allow_non_cc0_output": allow_non_cc0_output,
        },
        "metrics": {
            "input_row_count": len(input_rows),
            "project_count": len(dataset.rows),
            "future_event_count": len(dataset.events_by_id),
            "flag_worthy_event_count": len(dataset.flag_worthy_event_ids),
            "non_flag_future_event_count": len(dataset.non_flag_event_ids),
        },
        "candidate_discovery_bias": summarize_candidate_discovery_bias(
            input_rows,
            audit_rows=audit_rows,
        ),
        "claim_boundary": (
            "This builder only converts curated public VCS event-link rows into "
            "the recall benchmark schema. It does not prove wild-corpus quality, "
            "closed-book lift, or license-safe redistribution."
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus VCS future-event fixture builder")
    print(
        f"- projects: {metrics['project_count']} future_events: "
        f"{metrics['future_event_count']} flag_worthy: {metrics['flag_worthy_event_count']}"
    )
    print(f"- status: {payload['status']}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--clean-source-events",
        type=Path,
        help="Use clean-source events.jsonl as past behavior sources.",
    )
    parser.add_argument(
        "--links",
        type=Path,
        help="Curated JSON/JSONL rows linking clean-source event ids to future labels.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--license", dest="license_id", default=DEFAULT_LICENSE)
    parser.add_argument("--source-family", default=DEFAULT_SOURCE_FAMILY)
    parser.add_argument(
        "--candidate-discovery-audit",
        type=Path,
        default=None,
        help=(
            "Optional sanitized JSON/JSONL audit rows for excluded candidates "
            "and sampled misses. Do not include raw PR/review text."
        ),
    )
    parser.add_argument(
        "--allow-non-cc0-output",
        action="store_true",
        help=(
            "Permit local fixture output with non-CC0 licensing. Generated files "
            "must stay out of the checked-in public corpus unless redistribution "
            "has been verified."
        ),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.clean_source_events or args.links:
        if not args.clean_source_events or not args.links:
            raise SystemExit("--clean-source-events and --links must be provided together")
        payload = build_fixture_from_clean_events(
            clean_source_events_path=args.clean_source_events,
            links_path=args.links,
            output_path=args.output,
            dataset_id=args.dataset_id,
            license_id=args.license_id,
            source_family=args.source_family,
            allow_non_cc0_output=args.allow_non_cc0_output,
            candidate_discovery_audit_path=args.candidate_discovery_audit,
        )
    else:
        if not args.input:
            raise SystemExit("--input is required unless --clean-source-events and --links are used")
        payload = build_fixture(
            input_path=args.input,
            output_path=args.output,
            dataset_id=args.dataset_id,
            license_id=args.license_id,
            source_family=args.source_family,
            allow_non_cc0_output=args.allow_non_cc0_output,
            candidate_discovery_audit_path=args.candidate_discovery_audit,
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
