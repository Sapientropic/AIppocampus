#!/usr/bin/env python3
"""AMemGym metadata and source-backed overlay smoke for AIppocampus.

This is intentionally not an official AMemGym score runner. The upstream
benchmark is interactive and on-policy: agents see evolving user state, write or
retrieve memory through different arms, and answer later questions. This helper
keeps the first AIppocampus adapter slice smaller and harder to overclaim:
standard-library dataset intake, sanitized shape observations, optional local
prediction scoring, and source-backed overlay diagnostics that stay separate
from AMemGym's native score and official diagnosis files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
DEFAULT_CASE_LIMIT = 20
DEFAULT_MANIFEST = _paths.REPO_ROOT / "benchmark_corpus" / "amemgym_manifest.json"
DEFAULT_DATASET_PATH = _paths.REPO_ROOT / "benchmark_corpus" / "amemgym" / "v1.base" / "data.json"

REQUIRED_TOP_LEVEL_FIELDS = ("id", "start_time", "user_profile", "state_schema", "periods", "qas")
OFFICIAL_RAW_DATA_URL = "https://huggingface.co/datasets/AGI-Eval/AMemGym/raw/main/v1.base/data.json"

CANNOT_CLAIM = [
    "official_amemgym_score",
    "official_runner_compatibility",
    "interactive_on_policy_agent_quality",
    "native_or_rag_or_awi_or_awe_baseline_parity",
    "write_read_diagnosis_compatibility",
    "upperbound_utilization_compatibility",
    "llm_simulated_user_represents_real_life_wide_memory",
    "source_backed_overlay_is_official_accuracy",
]


@dataclass(frozen=True)
class SourceEvent:
    source_ref: str
    state: dict[str, Any]
    is_initial: bool


@dataclass(frozen=True)
class AMemGymCase:
    case_id: str
    row_id: str
    qa_index: int
    required_info: tuple[str, ...]
    gold_answer: str
    supported_by_current_state: bool
    current_choice_found: bool
    stale_choice_available: bool
    current_source_refs: tuple[str, ...]
    answer_choices: tuple[dict[str, Any], ...]


@dataclass
class SchemaObservation:
    row_count: int = 0
    rows_with_required_fields: int = 0
    period_count: int = 0
    session_count: int = 0
    message_count: int = 0
    update_count: int = 0
    qa_count: int = 0
    answer_choice_count: int = 0
    rows_with_stale_current_pair: int = 0
    rows_with_current_source_hit: int = 0
    rows_with_unsupported_qa: int = 0
    state_schema_slot_counts: Counter[int] = field(default_factory=Counter)
    answer_choice_counts: Counter[int] = field(default_factory=Counter)
    required_info_counts: Counter[int] = field(default_factory=Counter)
    answer_choice_type_counts: Counter[str] = field(default_factory=Counter)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_file:{sha1_short(str(resolved))}"


def load_manifest(path: Path | str = DEFAULT_MANIFEST) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise ValueError(f"{path.name}: expected a JSON array")
        return [dict(row) for row in rows if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: row must be an object")
        rows.append(dict(row))
    return rows


def download_official_dataset(path: Path = DEFAULT_DATASET_PATH, *, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(OFFICIAL_RAW_DATA_URL, timeout=60) as response:
        path.write_bytes(response.read())
    return path


def stable_row_id(row: dict[str, Any], row_index: int) -> str:
    value = str(row.get("id") or "").strip()
    return value or f"row-{row_index}"


def as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def iter_periods(row: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for period in as_list(row.get("periods")):
        if isinstance(period, dict):
            yield period


def iter_sessions(period: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for session in as_list(period.get("sessions")):
        if isinstance(session, dict):
            yield session


def update_entries(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def state_from_update(update: Any) -> dict[str, Any]:
    if not isinstance(update, dict):
        return {}
    if isinstance(update.get("state"), dict):
        return dict(update["state"])
    if isinstance(update.get("states"), dict):
        return dict(update["states"])
    exposed = update.get("exposed_states")
    if isinstance(exposed, dict):
        return dict(exposed)
    return {
        key: value
        for key, value in update.items()
        if key not in {"text", "message", "messages", "source", "query", "event", "session_time"}
        and isinstance(key, str)
    }


def source_events_for_row(row: dict[str, Any], row_id: str) -> list[SourceEvent]:
    events: list[SourceEvent] = []
    update_index = 0
    for period_index, period in enumerate(iter_periods(row), start=1):
        period_state = as_mapping(period.get("state"))
        if period_state:
            events.append(
                SourceEvent(
                    source_ref=f"{row_id}:p{period_index}:state",
                    state=period_state,
                    is_initial=period_index == 1,
                )
            )
        for session_index, session in enumerate(iter_sessions(period), start=1):
            exposed_state = as_mapping(session.get("exposed_states"))
            if exposed_state:
                events.append(
                    SourceEvent(
                        source_ref=f"{row_id}:p{period_index}:s{session_index}:exposed",
                        state=exposed_state,
                        is_initial=period_index == 1,
                    )
                )
            for update in update_entries(session.get("updates")):
                update_state = state_from_update(update)
                if update_state:
                    update_index += 1
                    events.append(
                        SourceEvent(
                            source_ref=f"{row_id}:p{period_index}:s{session_index}:u{update_index}",
                            state=update_state,
                            is_initial=period_index == 1 and update_index == 1,
                        )
                    )
        for update in update_entries(period.get("updates")):
            update_state = state_from_update(update)
            if update_state:
                update_index += 1
                events.append(
                    SourceEvent(
                        source_ref=f"{row_id}:p{period_index}:u{update_index}",
                        state=update_state,
                        is_initial=period_index == 1 and update_index == 1,
                    )
                )
    return events


def latest_state(events: Iterable[SourceEvent]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for event in events:
        state.update(event.state)
    return state


def history_by_key(events: Iterable[SourceEvent]) -> dict[str, list[Any]]:
    history: dict[str, list[Any]] = {}
    for event in events:
        for key, value in event.state.items():
            history.setdefault(str(key), []).append(value)
    return history


def normalize_state_values(values: Any) -> tuple[str, ...]:
    if isinstance(values, list):
        return tuple(str(value) for value in values)
    return (str(values),)


def choice_matches_state(choice: dict[str, Any], required_info: tuple[str, ...], state: dict[str, Any]) -> bool:
    values = normalize_state_values(choice.get("state"))
    if len(values) != len(required_info):
        return False
    for key, value in zip(required_info, values):
        if str(state.get(key)) != value:
            return False
    return True


def choice_matches_history(
    choice: dict[str, Any],
    required_info: tuple[str, ...],
    history: dict[str, list[Any]],
    current_state: dict[str, Any],
) -> bool:
    values = normalize_state_values(choice.get("state"))
    if len(values) != len(required_info) or choice_matches_state(choice, required_info, current_state):
        return False
    for key, value in zip(required_info, values):
        historical_values = [str(item) for item in history.get(key, [])]
        if value not in historical_values:
            return False
    return True


def current_source_refs(events: Iterable[SourceEvent], required_info: tuple[str, ...], current_state: dict[str, Any]) -> tuple[str, ...]:
    refs: list[str] = []
    for event in events:
        if all(key in event.state and str(event.state[key]) == str(current_state.get(key)) for key in required_info):
            refs.append(event.source_ref)
    return tuple(refs)


def build_cases(rows: list[dict[str, Any]], *, case_limit: int) -> list[AMemGymCase]:
    cases: list[AMemGymCase] = []
    for row_index, row in enumerate(rows, start=1):
        row_id = stable_row_id(row, row_index)
        events = source_events_for_row(row, row_id)
        current_state = latest_state(events)
        history = history_by_key(events)
        for qa_index, qa in enumerate(as_list(row.get("qas")), start=1):
            if not isinstance(qa, dict):
                continue
            required_info = tuple(str(item) for item in as_list(qa.get("required_info")))
            answer_choices = tuple(dict(choice) for choice in as_list(qa.get("answer_choices")) if isinstance(choice, dict))
            current_choice = next(
                (choice for choice in answer_choices if choice_matches_state(choice, required_info, current_state)),
                None,
            )
            fallback_choice = answer_choices[0] if answer_choices else {}
            supported = bool(required_info) and all(key in current_state for key in required_info)
            gold_choice = current_choice if supported and current_choice else fallback_choice
            stale_choice_available = any(
                choice_matches_history(choice, required_info, history, current_state)
                for choice in answer_choices
            )
            cases.append(
                AMemGymCase(
                    case_id=f"{row_id}:q{qa_index}",
                    row_id=row_id,
                    qa_index=qa_index,
                    required_info=required_info,
                    gold_answer=str(gold_choice.get("answer") or ""),
                    supported_by_current_state=supported and current_choice is not None,
                    current_choice_found=current_choice is not None,
                    stale_choice_available=stale_choice_available,
                    current_source_refs=current_source_refs(events, required_info, current_state),
                    answer_choices=answer_choices,
                )
            )
            if len(cases) >= case_limit:
                return cases
    return cases


def observe_schema(rows: list[dict[str, Any]], *, case_limit: int) -> tuple[SchemaObservation, list[AMemGymCase]]:
    observation = SchemaObservation(row_count=len(rows))
    cases = build_cases(rows, case_limit=case_limit)
    cases_by_row: dict[str, list[AMemGymCase]] = {}
    for case in cases:
        cases_by_row.setdefault(case.row_id, []).append(case)
    for row_index, row in enumerate(rows, start=1):
        row_id = stable_row_id(row, row_index)
        if all(field in row for field in REQUIRED_TOP_LEVEL_FIELDS):
            observation.rows_with_required_fields += 1
        state_schema = as_mapping(row.get("state_schema"))
        observation.state_schema_slot_counts[len(state_schema)] += 1
        for period in iter_periods(row):
            observation.period_count += 1
            observation.update_count += len(update_entries(period.get("updates")))
            for session in iter_sessions(period):
                observation.session_count += 1
                observation.message_count += len(as_list(session.get("messages")))
                observation.update_count += len(update_entries(session.get("updates")))
        qas = [qa for qa in as_list(row.get("qas")) if isinstance(qa, dict)]
        observation.qa_count += len(qas)
        for qa in qas:
            required_info = as_list(qa.get("required_info"))
            observation.required_info_counts[len(required_info)] += 1
            answer_choices = [choice for choice in as_list(qa.get("answer_choices")) if isinstance(choice, dict)]
            observation.answer_choice_count += len(answer_choices)
            observation.answer_choice_counts[len(answer_choices)] += 1
            for choice in answer_choices:
                choice_type = str(choice.get("type") or "unknown")
                observation.answer_choice_type_counts[choice_type] += 1
        row_cases = cases_by_row.get(row_id, [])
        if any(case.stale_choice_available for case in row_cases):
            observation.rows_with_stale_current_pair += 1
        # This metadata-rate intentionally asks whether the row contains a
        # current value that arrives after an initial state/source event. A row
        # with only one state snapshot is readable, but it has not exercised the
        # source-reopen risk that #733 is trying to isolate.
        events = source_events_for_row(row, row_id)
        if len(events) > 1 and any(case.current_source_refs for case in row_cases):
            observation.rows_with_current_source_hit += 1
        if any(not case.supported_by_current_state for case in row_cases):
            observation.rows_with_unsupported_qa += 1
    return observation, cases


def rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def prediction_rows(path: Path | str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in read_json_or_jsonl(Path(path)):
        case_id = str(row.get("case_id") or "")
        if case_id:
            rows[case_id] = row
    return rows


def answer_choice_for_prediction(case: AMemGymCase, prediction: str) -> dict[str, Any] | None:
    for choice in case.answer_choices:
        if str(choice.get("answer") or "").strip() == prediction.strip():
            return choice
    return None


def has_real_source_ref(prediction: dict[str, Any]) -> bool:
    for ref in as_list(prediction.get("source_refs")):
        text = str(ref)
        if text and not text.startswith("scent:"):
            return True
    return False


def build_overlay_metrics(cases: list[AMemGymCase], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    matched: list[tuple[AMemGymCase, dict[str, Any]]] = [
        (case, predictions[case.case_id]) for case in cases if case.case_id in predictions
    ]
    sample_count = len(matched)
    correct = 0
    source_reopen = 0
    current_source_hit = 0
    stale_as_current = 0
    unsupported_personalization = 0
    scent_as_evidence = 0
    correct_but_unsupported = 0
    write_failure = 0
    read_failure = 0
    utilization_failure = 0
    official_diagnosis_memory_success = 0

    for case, prediction in matched:
        prediction_text = str(prediction.get("prediction") or "")
        is_correct = prediction_text.strip() == case.gold_answer.strip()
        if is_correct:
            correct += 1
        if has_real_source_ref(prediction):
            source_reopen += 1
            current_source_hit += 1
        if bool(prediction.get("used_current_state")) and is_correct and case.supported_by_current_state:
            official_diagnosis_memory_success += 1
        chosen = answer_choice_for_prediction(case, prediction_text)
        if bool(prediction.get("used_stale_state")):
            stale_as_current += 1
        elif chosen and choice_matches_history(chosen, case.required_info, {}, {}):
            stale_as_current += 1
        if bool(prediction.get("unsupported_personalization")) or (
            not case.supported_by_current_state and prediction_text.strip()
        ):
            unsupported_personalization += 1
        if bool(prediction.get("scent_as_evidence")) or any(
            str(ref).startswith("scent:") for ref in as_list(prediction.get("source_refs"))
        ):
            scent_as_evidence += 1
        if is_correct and not case.supported_by_current_state:
            correct_but_unsupported += 1
        if bool(prediction.get("write_failure")):
            write_failure += 1
        if bool(prediction.get("read_failure")):
            read_failure += 1
        if bool(prediction.get("utilization_failure")):
            utilization_failure += 1

    return {
        "sample_count": sample_count,
        "accuracy": rate(correct, sample_count),
        "normalized_memory_score": rate(correct, sample_count),
        "source_reopen_success": rate(source_reopen, sample_count),
        "current_state_source_hit": rate(current_source_hit, sample_count),
        "stale_state_as_current_rate": rate(stale_as_current, sample_count),
        "unsupported_personalization_rate": rate(unsupported_personalization, sample_count),
        "scent_as_evidence_rate": rate(scent_as_evidence, sample_count),
        "answer_correct_but_unsupported_rate": rate(correct_but_unsupported, sample_count),
        "write_failure_rate": rate(write_failure, sample_count),
        "read_failure_rate": rate(read_failure, sample_count),
        "utilization_failure_rate": rate(utilization_failure, sample_count),
        "official_diagnosis_memory_success_rate": rate(official_diagnosis_memory_success, sample_count),
    }


def build_prediction_template(cases: list[AMemGymCase]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "qa_index": case.qa_index,
            "required_info_count": len(case.required_info),
            "supported_by_current_state": case.supported_by_current_state,
            "current_choice_found": case.current_choice_found,
            "stale_choice_available": case.stale_choice_available,
            "prediction": "",
            "source_refs": [],
            "used_current_state": False,
            "used_stale_state": False,
            "unsupported_personalization": False,
            "scent_as_evidence": False,
            "write_failure": False,
            "read_failure": False,
            "utilization_failure": False,
        }
        for case in cases
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def safe_cases(cases: list[AMemGymCase]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "row_id_sha1": sha1_short(case.row_id),
            "qa_index": case.qa_index,
            "required_info_count": len(case.required_info),
            "answer_choice_count": len(case.answer_choices),
            "supported_by_current_state": case.supported_by_current_state,
            "current_choice_found": case.current_choice_found,
            "stale_choice_available": case.stale_choice_available,
            "current_source_ref_count": len(case.current_source_refs),
            "gold_answer_sha1": sha1_short(case.gold_answer) if case.gold_answer else None,
        }
        for case in cases
    ]


def schema_payload(observation: SchemaObservation) -> dict[str, Any]:
    return {
        "required_top_level_fields": list(REQUIRED_TOP_LEVEL_FIELDS),
        "required_top_level_fields_present_rate": rate(
            observation.rows_with_required_fields,
            observation.row_count,
        ),
        "period_count": observation.period_count,
        "session_count": observation.session_count,
        "message_count": observation.message_count,
        "update_count": observation.update_count,
        "qa_count": observation.qa_count,
        "answer_choice_count": observation.answer_choice_count,
        "state_schema_slot_count_histogram": {
            str(key): value for key, value in sorted(observation.state_schema_slot_counts.items())
        },
        "required_info_count_histogram": {
            str(key): value for key, value in sorted(observation.required_info_counts.items())
        },
        "answer_choice_count_histogram": {
            str(key): value for key, value in sorted(observation.answer_choice_counts.items())
        },
        "answer_choice_type_counts": dict(sorted(observation.answer_choice_type_counts.items())),
    }


def baseline_metrics(observation: SchemaObservation, manifest: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "official_expected_rows": int(manifest["official_dataset"]["rows"]),
        "observed_row_count": len(rows),
        "metadata_row_current_source_hit_rate": rate(
            observation.rows_with_current_source_hit,
            observation.row_count,
        ),
        "current_state_source_hit_rate": rate(
            observation.rows_with_current_source_hit,
            observation.row_count,
        ),
        "stale_state_as_current_rate": rate(
            observation.rows_with_stale_current_pair,
            observation.row_count,
        ),
        "unsupported_personalization_rate": rate(
            observation.rows_with_unsupported_qa,
            observation.row_count,
        ),
    }


def run_amemgym_smoke(
    *,
    dataset_path: Path | str = DEFAULT_DATASET_PATH,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    case_limit: int = DEFAULT_CASE_LIMIT,
    predictions_path: Path | str | None = None,
    prediction_template_output: Path | str | None = None,
    download_official: bool = False,
    compute_sha256: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    manifest = load_manifest(manifest_path)
    dataset = Path(dataset_path)
    if download_official:
        dataset = download_official_dataset(dataset)

    if not dataset.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_amemgym_metadata_smoke",
            "generated_at": now_utc(),
            "status": "skipped_missing_dataset",
            "ok": True,
            "configuration": {
                "dataset_path_sha1": sha1_short(str(dataset.resolve())),
                "manifest": safe_path_label(manifest_path),
                "case_limit": case_limit,
                "downloads_dataset": download_official,
                "live_llm": False,
            },
            "source": {
                "benchmark": manifest["benchmark"],
                "official_sources": manifest["official_sources"],
                "official_dataset": manifest["official_dataset"],
            },
            "metrics": {
                "official_expected_rows": int(manifest["official_dataset"]["rows"]),
                "observed_row_count": 0,
                "sample_count": 0,
            },
            "schema_observation": {},
            "evaluation_layers": {
                "native_metrics": ["native_accuracy_requires_predictions"],
                "official_diagnosis": [
                    "write_failure_and_read_failure_require_official_or_compatible_logs",
                    "memory_success_is_not_source_truth",
                ],
                "source_backed_overlay": "not_run_without_local_rows",
                "cost_latency": "elapsed_ms_only_no_model_calls",
            },
            "claim_boundary": claim_boundary(predictions_present=False),
            "privacy_boundary": {
                "raw_text_emitted": False,
                "absolute_paths_emitted": False,
                "prediction_template_raw_text_emitted": False,
                "default_report_shape": "metadata_schema_hashes_and_counts_only",
            },
            "artifacts": {
                "prediction_template_written": False,
                "prediction_template_status": "not_requested",
            },
            "cannot_claim": CANNOT_CLAIM,
            "next_step": (
                "Download the public AMemGym v1.base JSON with --download-official, "
                "or provide a local JSON/JSONL export under benchmark_corpus/amemgym/."
            ),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    rows = read_json_or_jsonl(dataset)
    observation, cases = observe_schema(rows, case_limit=case_limit)
    predictions = prediction_rows(predictions_path)
    overlay = build_overlay_metrics(cases, predictions) if predictions else {}
    metrics = baseline_metrics(observation, manifest, rows)
    if overlay:
        metrics.update(overlay)
    else:
        metrics["sample_count"] = 0

    template_path: Path | None = None
    template_status = "not_requested"
    if prediction_template_output:
        template_path = Path(prediction_template_output)
        write_jsonl(template_path, build_prediction_template(cases))
        template_status = "written"

    status = "overlay_metrics_smoke" if predictions else "metadata_smoke"
    file_payload: dict[str, Any] = {
        "label": safe_path_label(dataset),
        "path_sha1": sha1_short(str(dataset.resolve())),
        "bytes": dataset.stat().st_size,
    }
    if compute_sha256:
        file_payload["sha256"] = file_sha256(dataset)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_amemgym_metadata_smoke",
        "generated_at": now_utc(),
        "status": status,
        "ok": True,
        "configuration": {
            "dataset_path_sha1": sha1_short(str(dataset.resolve())),
            "manifest": safe_path_label(manifest_path),
            "case_limit": case_limit,
            "compute_sha256": compute_sha256,
            "downloads_dataset": download_official,
            "live_llm": False,
        },
        "source": {
            "benchmark": manifest["benchmark"],
            "official_sources": manifest["official_sources"],
            "official_dataset": manifest["official_dataset"],
            "observed_at": manifest["observed_at"],
        },
        "dataset_file": file_payload,
        "metrics": metrics,
        "schema_observation": schema_payload(observation),
        "cases": safe_cases(cases),
        "evaluation_layers": {
            "native_metrics": [
                "native_accuracy_requires_predictions",
                "accuracy_is_exact_answer_choice_match_for_local_slice",
                "normalized_memory_score_is_local_slice_accuracy_until_official_runner_is_wired",
            ],
            "official_diagnosis": [
                "write_failure_and_read_failure_require_official_or_compatible_logs",
                "repo_diagnosis_outputs_memory_success_not_utilization_failure",
                "utilization_requires_upperbound_or_explicit_overlay_flag",
            ],
            "source_backed_overlay": [
                "source_reopen_success",
                "current_state_source_hit",
                "stale_state_as_current_rate",
                "unsupported_personalization_rate",
                "scent_as_evidence_rate",
                "answer_correct_but_unsupported_rate",
            ],
            "cost_latency": "elapsed_ms_only_no_model_calls",
        },
        "claim_boundary": claim_boundary(predictions_present=bool(predictions)),
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
            "prediction_template_raw_text_emitted": False,
            "default_report_shape": "metadata_schema_hashes_counts_and_case_hashes_only",
        },
        "artifacts": {
            "prediction_template_written": bool(template_path),
            "prediction_template_status": template_status,
            "prediction_template_output_sha1": sha1_short(str(template_path.resolve())) if template_path else None,
        },
        "cannot_claim": CANNOT_CLAIM,
        "next_step": (
            "Use a local prediction JSONL to inspect source-backed overlay metrics. "
            "Do not treat this as an official AMemGym score until the official interactive runner "
            "and Native/RAG/AWI/AWE arms are wired under a documented cost/latency boundary."
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def claim_boundary(*, predictions_present: bool) -> dict[str, str]:
    return {
        "amemgym_score": "not_claimed",
        "official_runner_compatibility": "not_claimed",
        "native_accuracy": "local_prediction_exact_match_only" if predictions_present else "not_measured",
        "source_backed_fidelity": "overlay_metrics_only" if predictions_present else "not_measured",
        "write_read_diagnosis": "operator_prediction_flags_only" if predictions_present else "not_measured",
        "cost_latency": "reported_without_model_cost",
        "public_claim": "schema_and_sanitized_adapter_boundary_only",
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus AMemGym metadata / overlay smoke")
    print(f"- status: {payload['status']}")
    print(f"- observed rows: {payload['metrics'].get('observed_row_count', 0)}")
    print(f"- sample count: {payload['metrics'].get('sample_count', 0)}")
    print("- cannot claim:")
    for item in payload["cannot_claim"]:
        print(f"  - {item}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-path", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--case-limit", type=int, default=DEFAULT_CASE_LIMIT)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--prediction-template-output", type=Path)
    parser.add_argument(
        "--download-official",
        action="store_true",
        help="Download the public Hugging Face v1.base/data.json into the selected dataset path before running.",
    )
    parser.add_argument("--skip-sha256", action="store_true", help="Skip file sha256 hashing for local datasets.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_amemgym_smoke(
        dataset_path=args.dataset_path,
        manifest_path=args.manifest,
        case_limit=args.case_limit,
        predictions_path=args.predictions,
        prediction_template_output=args.prediction_template_output,
        download_official=args.download_official,
        compute_sha256=not args.skip_sha256,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
