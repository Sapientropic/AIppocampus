#!/usr/bin/env python3
"""Recall-aware public VCS future-event benchmark for AIppocampus Dream work.

This is the first hard-event scaffold for the public longitudinal-user track.
Unlike the synthetic pseudo-user contract smoke, this runner scores over the
whole future window: every flag-worthy hard event that is not predicted is a
false negative. That prevents a silent Dream layer from winning by precision
alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from benchmark_statistics import binomial_rate_report, lower_bound_gate

SCHEMA_VERSION = 1
DEFAULT_DATASET = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "vcs_future_events_v1.jsonl"
).resolve()
FLAG_DECISIONS = {"flag", "suppress", "unknown"}
HARD_EVENT_KINDS = {
    "pull_request_merged",
    "pull_request_rejected",
    "issue_reopened",
    "commit_reverted",
    "patchset_superseded",
    "satd_comment_removed",
    "tool_call_failed",
    "tool_call_succeeded",
    "test_failed",
    "test_passed",
    "edit_reverted",
    "route_abandoned",
}
SOURCE_DEGRADATION_STATES = {
    "full_source",
    "truncated_source",
    "redacted_source",
    "missing_source_id",
    "partial_support",
}
FULL_SUPPORT_BLOCKING_DEGRADATIONS = {"missing_source_id", "partial_support"}
SOURCE_DISAMBIGUATION_INPUT_FIELDS = [
    "future_window.text",
    "future_window.family",
    "future_window.hard_event_kind",
    "past_window.kind",
    "past_window.text",
    "past_window.behavior_backed",
    "past_window.tool_name",
    "past_window.command_class",
    "past_window.failure_family",
]
TRACK_PREFIXES = {
    "adv-dual-": "dual_source_counterfactual",
    "adv-temporal-": "temporal_override_chain",
    "adv-cross-family-": "family_cross_contamination",
    "adv-paraphrase-": "adversarial_paraphrase",
    "adv-lexical-": "lexical_near_miss_anti_drift",
    "adv-abstain-": "abstention_unsupported",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "but",
    "by",
    "for",
    "from",
    "has",
    "if",
    "in",
    "into",
    "is",
    "it",
    "not",
    "of",
    "on",
    "or",
    "pr",
    "source",
    "that",
    "the",
    "this",
    "to",
    "was",
    "with",
}


@dataclass(frozen=True)
class VcsFutureEventDataset:
    dataset_id: str
    path: Path
    rows: list[dict[str, Any]]
    events_by_id: dict[str, dict[str, Any]]
    flag_worthy_event_ids: set[str]
    non_flag_event_ids: set[str]
    candidate_discovery_bias: dict[str, Any]


@dataclass(frozen=True)
class Prediction:
    prediction_id: str
    event_id: str
    decision: str
    past_source_ids: tuple[str, ...]
    family: str | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def public_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_dataset:{sha1_text(str(resolved))[:16]}"


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def normalize_decision(value: Any) -> str:
    decision = str(value or "unknown").strip().lower()
    return decision if decision in FLAG_DECISIONS else "unknown"


def normalize_source_degradation(value: Any) -> str:
    state = str(value or "full_source").strip().lower()
    return state if state in SOURCE_DEGRADATION_STATES else "full_source"


def tokenize_for_retrieval(value: Any) -> set[str]:
    return {
        token
        for token in TOKEN_RE.findall(str(value or "").casefold())
        if token and token not in STOPWORDS and len(token) > 1
    }


def retrieval_text_for_source(source: dict[str, Any]) -> str:
    # Deliberately omit source_id: source ids are oracle labels for grading and
    # often encode "current" / "stale" in synthetic fixtures. Ranking may use
    # public-safe candidate content and bounded source metadata only.
    fields = [
        source.get("kind"),
        source.get("text"),
        source.get("tool_name"),
        source.get("command_class"),
        source.get("command_family"),
        source.get("target_class"),
        source.get("test_target_class"),
        source.get("failure_family"),
    ]
    return " ".join(str(field or "") for field in fields)


def retrieval_text_for_event(event: dict[str, Any]) -> str:
    # Do not include expected_signal, flag_worthy, or required_past_source_ids.
    # The production-like arm receives the future event surface, not the grader.
    return " ".join(
        str(field or "")
        for field in (
            event.get("text"),
            event.get("family"),
            event.get("hard_event_kind"),
        )
    )


def source_kind(source: dict[str, Any]) -> str:
    return str(source.get("kind") or "").casefold()


def source_is_behavior_backed(source: dict[str, Any]) -> bool:
    return bool(source.get("behavior_backed")) or source_kind(source) in {
        "tool_call",
        "tool_call_failed",
        "test_failed",
        "edit_reverted",
        "route_abandoned",
    }


def source_is_current_like(source: dict[str, Any]) -> bool:
    kind = source_kind(source)
    source_text = str(source.get("text") or "").casefold()
    return any(
        marker in f"{kind} {source_text}"
        for marker in (
            "counterfactual_current",
            "current_decision",
            "current source",
            "active rationale",
            "effective rule",
            "local override",
        )
    )


def source_is_stale_like(source: dict[str, Any]) -> bool:
    kind = source_kind(source)
    source_text = str(source.get("text") or "").casefold()
    return any(
        marker in f"{kind} {source_text}"
        for marker in (
            "old_decision",
            "old source",
            "original public",
            "stale",
            "superseded",
            "earlier constraint",
            "pull_request_metadata",
            "weak_related_source",
        )
    )


def source_is_weak_or_narrative(source: dict[str, Any]) -> bool:
    kind = source_kind(source)
    return kind in {"weak_related_source", "assistant_message"} or bool(
        source.get("behavior_backed") is False
    )


def event_requests_current_source(event: dict[str, Any]) -> bool:
    text = retrieval_text_for_event(event).casefold()
    return any(
        marker in text
        for marker in (
            "current",
            "effective",
            "override",
            "overrides",
            "overridden",
            "newer",
            "active",
        )
    )


def event_requests_behavior_source(event: dict[str, Any]) -> bool:
    text = retrieval_text_for_event(event).casefold()
    return any(
        marker in text
        for marker in (
            "behavior",
            "failed",
            "failure",
            "test_failed",
            "tool_call_failed",
            "edit_reverted",
            "route_abandoned",
        )
    )


def event_has_unsupported_signal(event: dict[str, Any]) -> bool:
    text = retrieval_text_for_event(event).casefold()
    return any(
        marker in text
        for marker in (
            "unsupported",
            "no source-backed",
            "without support",
            "unrelated",
            "similar surface",
            "weak related",
            "narrative-only",
            "successful tool behavior",
            "docs-only",
        )
    )


def infer_event_track(event_id: str) -> str | None:
    for prefix, track in TRACK_PREFIXES.items():
        if event_id.startswith(prefix):
            return track
    if event_id.startswith("adv-rollout-"):
        if event_id.endswith("-behavior-event"):
            return "behavior_only_rollout_gold"
        if event_id.endswith("-narrative-negative"):
            return "behavior_narrative_negative"
    return None


def load_event_metadata(path: Path | str | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        return {
            str(event_id): dict(value)
            for event_id, value in rows.items()
            if isinstance(value, dict)
        }
    if isinstance(rows, list):
        result: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"event metadata row {index} must be an object")
            event_id = str(row.get("event_id") or "")
            if not event_id:
                raise ValueError(f"event metadata row {index} missing event_id")
            result[event_id] = dict(row)
        return result
    raise ValueError("event metadata must be a JSON object or array")


def event_track(
    event: dict[str, Any] | None,
    event_metadata: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    if event is None:
        return None
    explicit_track = str(event.get("track") or "").strip()
    if explicit_track:
        return explicit_track
    event_id = str(event.get("event_id") or "")
    metadata_track = str((event_metadata or {}).get(event_id, {}).get("track") or "").strip()
    if metadata_track:
        return metadata_track
    return infer_event_track(event_id)


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


def load_dataset(
    path: Path | str = DEFAULT_DATASET,
    *,
    require_cc0: bool = True,
) -> VcsFutureEventDataset:
    dataset_path = Path(path).resolve()
    rows = read_json_or_jsonl(dataset_path)
    if not rows:
        raise ValueError(f"empty VCS future-event dataset: {dataset_path}")

    dataset_ids = {str(row.get("dataset_id") or "") for row in rows}
    dataset_ids.discard("")
    if len(dataset_ids) != 1:
        raise ValueError(f"expected exactly one dataset_id, got {sorted(dataset_ids)}")
    dataset_id = next(iter(dataset_ids))

    project_ids: set[str] = set()
    source_ids: set[str] = set()
    events_by_id: dict[str, dict[str, Any]] = {}
    flag_worthy_event_ids: set[str] = set()
    non_flag_event_ids: set[str] = set()
    candidate_discovery_bias: dict[str, Any] = {"available": False}
    errors: list[str] = []

    for row_number, row in enumerate(rows, start=1):
        project_id = str(row.get("project_id") or "")
        if not project_id:
            errors.append(f"row {row_number}: missing project_id")
        if project_id in project_ids:
            errors.append(f"row {row_number}: duplicate project_id {project_id}")
        project_ids.add(project_id)

        license_id = str(row.get("license") or "")
        if not license_id:
            errors.append(f"row {row_number}: missing license")
        elif require_cc0 and license_id.upper() != "CC0-1.0":
            errors.append(f"row {row_number}: fixture rows must be CC0-1.0")
        row_bias = row.get("candidate_discovery_bias")
        if isinstance(row_bias, dict) and row_bias.get("available"):
            candidate_discovery_bias = dict(row_bias)

        row_source_ids: set[str] = set()
        row_sources_by_id: dict[str, dict[str, Any]] = {}
        for source in row.get("past_window") or []:
            source_id = str(source.get("source_id") or "")
            if not source_id:
                errors.append(f"row {row_number}: past source missing source_id")
            if source_id in source_ids:
                errors.append(f"row {row_number}: duplicate source_id {source_id}")
            source_ids.add(source_id)
            row_source_ids.add(source_id)
            row_sources_by_id[source_id] = dict(source)

        future_window = row.get("future_window") or []
        if not future_window:
            errors.append(f"row {row_number}: missing future_window")
        for event in future_window:
            event_id = str(event.get("event_id") or "")
            if not event_id:
                errors.append(f"row {row_number}: future event missing event_id")
            if event_id in events_by_id:
                errors.append(f"row {row_number}: duplicate event_id {event_id}")
            hard_event_kind = str(event.get("hard_event_kind") or "")
            if hard_event_kind not in HARD_EVENT_KINDS:
                errors.append(f"row {row_number}: unsupported hard_event_kind {hard_event_kind!r}")
            source_degradation = normalize_source_degradation(event.get("source_degradation"))
            missing_sources = set(as_string_list(event.get("required_past_source_ids"))) - row_source_ids
            if missing_sources and source_degradation != "missing_source_id":
                errors.append(
                    f"row {row_number}: event {event_id} references missing past sources "
                    f"{sorted(missing_sources)}"
                )
            for required_source_id in as_string_list(event.get("required_past_source_ids")):
                required_source = row_sources_by_id.get(required_source_id) or {}
                # Agent rollout fixtures may contain assistant narration as context,
                # but narrative-only text cannot be the gold support for a rejected
                # route. Only deterministic behavior traces should support future
                # hard-event labels when the source explicitly declares this boundary.
                if bool(event.get("flag_worthy")) and required_source.get("behavior_backed") is False:
                    errors.append(
                        f"row {row_number}: event {event_id} uses narrative-only source "
                        f"{required_source_id} as required support"
                    )
            enriched = dict(event)
            enriched["project_id"] = project_id
            enriched["source_degradation"] = source_degradation
            events_by_id[event_id] = enriched
            if bool(event.get("flag_worthy")):
                flag_worthy_event_ids.add(event_id)
            else:
                non_flag_event_ids.add(event_id)

    if errors:
        raise ValueError("VCS future-event dataset validation failed:\n- " + "\n- ".join(errors))

    return VcsFutureEventDataset(
        dataset_id=dataset_id,
        path=dataset_path,
        rows=rows,
        events_by_id=events_by_id,
        flag_worthy_event_ids=flag_worthy_event_ids,
        non_flag_event_ids=non_flag_event_ids,
        candidate_discovery_bias=candidate_discovery_bias,
    )


def source_support_allowed(event: dict[str, Any] | None) -> bool:
    if event is None:
        return False
    return normalize_source_degradation(
        event.get("source_degradation")
    ) not in FULL_SUPPORT_BLOCKING_DEGRADATIONS


def load_predictions(path: Path) -> list[Prediction]:
    predictions: list[Prediction] = []
    seen_prediction_ids: set[str] = set()
    for index, row in enumerate(read_json_or_jsonl(path), start=1):
        event_id = str(row.get("event_id") or "")
        prediction_id = str(row.get("prediction_id") or "") or f"{event_id or 'missing'}:{index}"
        if prediction_id in seen_prediction_ids:
            raise ValueError(f"duplicate prediction_id {prediction_id}")
        seen_prediction_ids.add(prediction_id)
        predictions.append(
            Prediction(
                prediction_id=prediction_id,
                event_id=event_id,
                decision=normalize_decision(row.get("decision")),
                past_source_ids=tuple(sorted(set(as_string_list(row.get("past_source_ids"))))),
                family=str(row.get("family") or "") or None,
            )
        )
    return predictions


def baseline_predictions(dataset: VcsFutureEventDataset, mode: str) -> list[Prediction]:
    if mode == "empty":
        return []
    predictions: list[Prediction] = []
    for event_id in sorted(dataset.flag_worthy_event_ids):
        event = dataset.events_by_id[event_id]
        predictions.append(
            Prediction(
                prediction_id=f"gold:{event_id}",
                event_id=event_id,
                decision="flag",
                past_source_ids=tuple(sorted(as_string_list(event.get("required_past_source_ids")))),
                family=str(event.get("family") or "") or None,
            )
        )
    return predictions


def score_source_for_event(
    *,
    event: dict[str, Any],
    source: dict[str, Any],
    row_sources: list[dict[str, Any]],
) -> float:
    query_tokens = tokenize_for_retrieval(retrieval_text_for_event(event))
    source_tokens = tokenize_for_retrieval(retrieval_text_for_source(source))
    overlap = query_tokens & source_tokens
    score = float(len(overlap))

    has_current_choice = any(source_is_current_like(candidate) for candidate in row_sources)
    has_behavior_choice = any(source_is_behavior_backed(candidate) for candidate in row_sources)
    if event_requests_current_source(event):
        if source_is_current_like(source):
            score += 8.0
        elif has_current_choice and source_is_stale_like(source):
            score -= 3.0
    if event_requests_behavior_source(event):
        if source_is_behavior_backed(source):
            score += 6.0
        elif has_behavior_choice and source_is_weak_or_narrative(source):
            score -= 4.0
    if source_is_weak_or_narrative(source):
        score -= 2.0
    if event_has_unsupported_signal(event):
        score -= 3.0
    return round(score, 4)


def rank_sources_for_event(
    *,
    event: dict[str, Any],
    row_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for source in row_sources:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            continue
        ranked.append(
            {
                "source_id": source_id,
                "kind": str(source.get("kind") or ""),
                "score": score_source_for_event(
                    event=event,
                    source=source,
                    row_sources=row_sources,
                ),
                "source_text_sha1": sha1_text(str(source.get("text") or ""))[:16],
                "behavior_backed": source.get("behavior_backed")
                if "behavior_backed" in source
                else None,
            }
        )
    return sorted(
        ranked,
        key=lambda item: (
            -float(item["score"]),
            str(item.get("kind") or ""),
            str(item.get("source_text_sha1") or ""),
        ),
    )


def should_flag_from_ranked_sources(
    *,
    event: dict[str, Any],
    ranked_sources: list[dict[str, Any]],
    min_score: float,
) -> bool:
    if not ranked_sources:
        return False
    top = ranked_sources[0]
    if float(top["score"]) < min_score:
        return False
    if event_has_unsupported_signal(event):
        return False
    top_kind = str(top.get("kind") or "").casefold()
    if top_kind in {"weak_related_source", "assistant_message"}:
        return False
    if top.get("behavior_backed") is False and event_requests_behavior_source(event):
        return False
    return True


def source_disambiguation_case_rows(
    dataset: VcsFutureEventDataset,
    *,
    event_metadata: dict[str, dict[str, Any]] | None = None,
    top_k: int = 1,
    min_score: float = 1.0,
) -> tuple[list[Prediction], list[dict[str, Any]]]:
    predictions: list[Prediction] = []
    case_rows: list[dict[str, Any]] = []
    safe_top_k = max(1, int(top_k))
    for row in dataset.rows:
        row_sources = [dict(source) for source in row.get("past_window") or []]
        source_by_id = {
            str(source.get("source_id") or ""): source
            for source in row_sources
            if str(source.get("source_id") or "")
        }
        for raw_event in row.get("future_window") or []:
            event = dataset.events_by_id[str(raw_event.get("event_id") or "")]
            ranked = rank_sources_for_event(event=event, row_sources=row_sources)
            selected = should_flag_from_ranked_sources(
                event=event,
                ranked_sources=ranked,
                min_score=min_score,
            )
            top_sources = ranked[:safe_top_k]
            selected_source_ids = [str(source["source_id"]) for source in top_sources] if selected else []
            if selected:
                predictions.append(
                    Prediction(
                        prediction_id=f"production-like:{event['event_id']}",
                        event_id=str(event["event_id"]),
                        decision="flag",
                        past_source_ids=tuple(selected_source_ids),
                        family=str(event.get("family") or "") or None,
                    )
                )

            required_source_ids = set(as_string_list(event.get("required_past_source_ids")))
            stale_source_ids = sorted(set(source_by_id) - required_source_ids)
            scores_by_source_id = {
                str(source["source_id"]): float(source["score"]) for source in ranked
            }
            pairwise_comparisons = 0
            pairwise_wins = 0
            for required_source_id in required_source_ids:
                if required_source_id not in scores_by_source_id:
                    continue
                for stale_source_id in stale_source_ids:
                    if stale_source_id not in scores_by_source_id:
                        continue
                    pairwise_comparisons += 1
                    pairwise_wins += int(
                        scores_by_source_id[required_source_id]
                        > scores_by_source_id[stale_source_id]
                    )
            top_source_ids = [str(source["source_id"]) for source in top_sources]
            flag_worthy = bool(event.get("flag_worthy"))
            current_top_k_hit = (
                bool(required_source_ids)
                and required_source_ids <= set(top_source_ids)
                and source_support_allowed(event)
            )
            wrong_source_evidence = bool(
                flag_worthy
                and selected
                and (
                    not required_source_ids <= set(selected_source_ids)
                    or bool(set(selected_source_ids) - required_source_ids)
                )
            )
            negative_false_positive = bool((not flag_worthy) and selected)
            case_rows.append(
                {
                    "event_id": event.get("event_id"),
                    "project_id": event.get("project_id"),
                    "track": event_track(event, event_metadata),
                    "family": event.get("family"),
                    "hard_event_kind": event.get("hard_event_kind"),
                    "flag_worthy": flag_worthy,
                    "required_past_source_ids": sorted(required_source_ids),
                    "selected_past_source_ids": selected_source_ids,
                    "top_source_ids": top_source_ids,
                    "top_sources": top_sources,
                    "stale_or_decoy_source_ids": stale_source_ids,
                    "current_source_top_k_hit": current_top_k_hit,
                    "stale_source_top_k": bool(set(top_source_ids) & set(stale_source_ids))
                    if flag_worthy
                    else False,
                    "wrong_source_evidence": wrong_source_evidence,
                    "negative_false_positive": negative_false_positive,
                    "pairwise_current_vs_stale": {
                        "wins": pairwise_wins,
                        "comparisons": pairwise_comparisons,
                    },
                }
            )
    return predictions, case_rows


def summarize_source_disambiguation_cases(
    case_rows: list[dict[str, Any]],
    *,
    top_k: int,
    min_score: float,
) -> dict[str, Any]:
    def bucket_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        positives = [row for row in rows if row["flag_worthy"]]
        negatives = [row for row in rows if not row["flag_worthy"]]
        pairwise_wins = sum(
            int(row["pairwise_current_vs_stale"]["wins"]) for row in positives
        )
        pairwise_comparisons = sum(
            int(row["pairwise_current_vs_stale"]["comparisons"]) for row in positives
        )
        return {
            "event_count": len(rows),
            "gold_event_count": len(positives),
            "non_flag_event_count": len(negatives),
            "current_source_top_k_hit_rate": safe_rate(
                sum(1 for row in positives if row["current_source_top_k_hit"]),
                len(positives),
            ),
            "current_vs_stale_pairwise_win_rate": safe_rate(
                pairwise_wins,
                pairwise_comparisons,
            ),
            "stale_source_top_k_rate": safe_rate(
                sum(1 for row in positives if row["stale_source_top_k"]),
                len(positives),
            ),
            "wrong_source_evidence_rate": safe_rate(
                sum(1 for row in positives if row["wrong_source_evidence"]),
                len(positives),
            ),
            "negative_false_positive_rate": safe_rate(
                sum(1 for row in negatives if row["negative_false_positive"]),
                len(negatives),
            ),
            "current_vs_stale_pairwise_wins": pairwise_wins,
            "current_vs_stale_pairwise_comparisons": pairwise_comparisons,
        }

    metrics = bucket_summary(case_rows)
    by_track: dict[str, dict[str, Any]] = {}
    for row in case_rows:
        track = str(row.get("track") or "unknown")
        by_track.setdefault(track, {"rows": []})["rows"].append(row)
    return {
        "available": True,
        "kind": "production_like_source_disambiguation",
        "config": {
            "top_k": top_k,
            "min_score": min_score,
        },
        "input_contract": {
            "uses_required_past_source_ids_for_ranking": False,
            "required_past_source_ids_used_for": "grading_only",
            "ranking_input_fields": SOURCE_DISAMBIGUATION_INPUT_FIELDS,
            "live_model_or_provider_call": False,
            "claim_boundary": (
                "This arm builds a local in-memory candidate index from each "
                "case's past_window and ranks candidates without gold source ids. "
                "It is production-like deterministic retrieval, not live LLM quality."
            ),
        },
        "metrics": metrics,
        "by_track": {
            track: bucket_summary(bucket["rows"])
            for track, bucket in sorted(by_track.items())
        },
        "events": case_rows,
        "privacy_boundary": {
            "raw_event_text_emitted": False,
            "raw_past_source_text_emitted": False,
            "source_text_hashes_emitted": True,
            "absolute_paths_emitted": False,
        },
    }


def claim_levels(
    *,
    production_like_retrieval: bool,
    predictions_file: Path | str | None,
    baseline: str,
) -> dict[str, Any]:
    oracle_baseline = (
        predictions_file is None and baseline == "gold" and not production_like_retrieval
    )
    return {
        "source_window_oracle_contract": {
            "available": not production_like_retrieval,
            "uses_required_past_source_ids_as_prediction_input": oracle_baseline,
            "claim_boundary": (
                "The gold baseline is an oracle contract check: it proves scorer "
                "semantics only when required source ids are supplied as predictions."
            ),
        },
        "production_like_retrieval": {
            "available": production_like_retrieval,
            "uses_required_past_source_ids_as_prediction_input": False,
            "claim_boundary": (
                "Ranks a local past-window source index without gold ids; it is "
                "not a live model/provider quality claim."
            ),
        },
        "live_source_disambiguation": {
            "available": False,
            "why": "No live model/provider call is made by this deterministic runner.",
        },
    }


def score_predictions(
    dataset: VcsFutureEventDataset,
    predictions: list[Prediction],
    *,
    event_metadata: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    event_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []

    flagged_by_event: dict[str, list[Prediction]] = {}
    for prediction in predictions:
        if prediction.decision == "flag":
            flagged_by_event.setdefault(prediction.event_id, []).append(prediction)

    for event_id, event in dataset.events_by_id.items():
        flag_worthy = bool(event.get("flag_worthy"))
        event_predictions = flagged_by_event.get(event_id, [])
        best_prediction = event_predictions[0] if event_predictions else None
        required_sources = set(as_string_list(event.get("required_past_source_ids")))
        predicted_sources = set(best_prediction.past_source_ids) if best_prediction else set()
        source_supported = required_sources <= predicted_sources and source_support_allowed(event)
        flagged = bool(event_predictions)
        true_positive = flag_worthy and flagged and source_supported
        false_negative = flag_worthy and not true_positive
        false_positive = (not flag_worthy) and flagged
        event_rows.append(
            {
                "event_id": event_id,
                "project_id": event.get("project_id"),
                "track": event_track(event, event_metadata),
                "family": event.get("family"),
                "hard_event_kind": event.get("hard_event_kind"),
                "flag_worthy": flag_worthy,
                "event_text_sha1": sha1_text(str(event.get("text") or ""))[:16],
                "required_past_source_ids": sorted(required_sources),
                "predicted_past_source_ids": sorted(predicted_sources),
                "flagged": flagged,
                "source_supported": source_supported if flagged else False,
                "source_degradation": normalize_source_degradation(event.get("source_degradation")),
                "anti_drift_family_under_test": event.get("anti_drift_family_under_test"),
                "anti_drift_contrast_family": event.get("anti_drift_contrast_family"),
                "true_positive": true_positive,
                "false_negative": false_negative,
                "false_positive": false_positive,
                "anti_drift_violation": false_positive,
                "prediction_count": len(event_predictions),
            }
        )

    known_event_ids = set(dataset.events_by_id)
    for prediction in predictions:
        maybe_event = dataset.events_by_id.get(prediction.event_id)
        unknown_event_id = prediction.event_id not in known_event_ids
        non_flag_event = prediction.event_id in dataset.non_flag_event_ids
        flag_worthy = prediction.event_id in dataset.flag_worthy_event_ids
        required_sources = (
            set(as_string_list(maybe_event.get("required_past_source_ids"))) if maybe_event else set()
        )
        predicted_sources = set(prediction.past_source_ids)
        source_supported = (
            required_sources <= predicted_sources and source_support_allowed(maybe_event)
            if maybe_event
            else False
        )
        prediction_rows.append(
            {
                "prediction_id": prediction.prediction_id,
                "event_id": prediction.event_id,
                "decision": prediction.decision,
                "track": event_track(maybe_event, event_metadata),
                "family": prediction.family or (maybe_event.get("family") if maybe_event else None),
                "known_event_id": not unknown_event_id,
                "flag_worthy_event": flag_worthy,
                "non_flag_event": non_flag_event,
                "source_supported": source_supported,
                "source_degradation": normalize_source_degradation(
                    maybe_event.get("source_degradation") if maybe_event else None
                ),
                "unknown_event_false_positive": unknown_event_id and prediction.decision == "flag",
                "non_flag_false_positive": non_flag_event and prediction.decision == "flag",
                "missing_required_sources": sorted(required_sources - predicted_sources),
                "extra_past_source_ids": sorted(predicted_sources - required_sources),
            }
        )
    return event_rows, prediction_rows


def summarize(event_rows: list[dict[str, Any]], prediction_rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive_rows = [row for row in event_rows if row["flag_worthy"]]
    non_flag_rows = [row for row in event_rows if not row["flag_worthy"]]
    true_positive_count = sum(1 for row in positive_rows if row["true_positive"])
    false_negative_count = sum(1 for row in positive_rows if row["false_negative"])
    false_positive_count = sum(1 for row in event_rows if row["false_positive"]) + sum(
        1 for row in prediction_rows if row["unknown_event_false_positive"]
    )
    predicted_flag_count = sum(1 for row in prediction_rows if row["decision"] == "flag")
    identity_true_positive_count = sum(
        1
        for row in prediction_rows
        if row["decision"] == "flag" and row["known_event_id"] and row["flag_worthy_event"]
    )
    family_counts: dict[str, dict[str, Any]] = {}
    for row in positive_rows:
        family = str(row.get("family") or "unknown")
        bucket = family_counts.setdefault(
            family,
            {"gold_event_count": 0, "true_positive_count": 0, "false_negative_count": 0},
        )
        bucket["gold_event_count"] += 1
        bucket["true_positive_count"] += int(bool(row["true_positive"]))
        bucket["false_negative_count"] += int(bool(row["false_negative"]))
    for bucket in family_counts.values():
        bucket["recall"] = safe_rate(bucket["true_positive_count"], bucket["gold_event_count"])
    precision = safe_rate(true_positive_count, predicted_flag_count)
    diagnostic_event_identity_precision = safe_rate(
        identity_true_positive_count,
        predicted_flag_count,
    )
    recall = safe_rate(true_positive_count, len(positive_rows))
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
    anti_drift_violation_count = sum(1 for row in non_flag_rows if row["false_positive"])
    rate_estimates = {
        "future_event_flag_recall": binomial_rate_report(
            "future_event_flag_recall",
            numerator=true_positive_count,
            denominator=len(positive_rows),
        ),
        "future_event_flag_precision": binomial_rate_report(
            "future_event_flag_precision",
            numerator=true_positive_count,
            denominator=predicted_flag_count,
        ),
        "anti_drift_pass_rate": binomial_rate_report(
            "anti_drift_pass_rate",
            numerator=sum(1 for row in non_flag_rows if not row["false_positive"]),
            denominator=len(non_flag_rows),
        ),
        "anti_drift_violation_rate": binomial_rate_report(
            "anti_drift_violation_rate",
            numerator=anti_drift_violation_count,
            denominator=len(non_flag_rows),
        ),
    }
    return {
        "total_future_event_count": len(event_rows),
        "future_event_gold_count": len(positive_rows),
        "non_flag_future_event_count": len(non_flag_rows),
        "predicted_flag_count": predicted_flag_count,
        "true_positive_count": true_positive_count,
        "false_negative_count": false_negative_count,
        "false_positive_count": false_positive_count,
        "future_event_flag_recall_rate": recall,
        "future_event_flag_precision": precision,
        "diagnostic_event_identity_precision": diagnostic_event_identity_precision,
        "future_event_flag_f1": f1,
        "rate_estimates": rate_estimates,
        "silent_dream_penalty_applies": True,
        "anti_drift_negative_count": len(non_flag_rows),
        "anti_drift_violation_count": anti_drift_violation_count,
        "anti_drift_pass_rate": safe_rate(
            sum(1 for row in non_flag_rows if not row["false_positive"]),
            len(non_flag_rows),
        ),
        "unknown_event_false_positive_count": sum(
            1 for row in prediction_rows if row["unknown_event_false_positive"]
        ),
        "source_support_failure_count": sum(
            1
            for row in prediction_rows
            if row["flag_worthy_event"] and not row["source_supported"]
        ),
        "by_family": family_counts,
    }


def source_degradation_controls(event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in event_rows:
        state = normalize_source_degradation(row.get("source_degradation"))
        counts[state] = counts.get(state, 0) + 1
    return {
        "available": any(state != "full_source" for state in counts),
        "counts_by_state": dict(sorted(counts.items())),
        "full_support_blocking_states": sorted(FULL_SUPPORT_BLOCKING_DEGRADATIONS),
        "full_support_blocked_count": sum(
            count
            for state, count in counts.items()
            if state in FULL_SUPPORT_BLOCKING_DEGRADATIONS
        ),
        "claim_boundary": (
            "Source-degradation controls test scorer behavior under retained, "
            "redacted, partial, or missing support. Partial support and missing "
            "source ids cannot satisfy the source-backed contract by themselves."
        ),
    }


def anti_drift_controls(event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    negative_rows = [row for row in event_rows if not row["flag_worthy"]]
    cross_family_rows = [
        row
        for row in negative_rows
        if row.get("anti_drift_family_under_test")
        and row.get("anti_drift_contrast_family")
        and row.get("anti_drift_family_under_test") != row.get("anti_drift_contrast_family")
    ]
    same_family_rows = [
        row
        for row in negative_rows
        if row.get("anti_drift_family_under_test")
        and row.get("anti_drift_contrast_family")
        and row.get("anti_drift_family_under_test") == row.get("anti_drift_contrast_family")
    ]
    return {
        "negative_count": len(negative_rows),
        "negative_cross_family_count": len(cross_family_rows),
        "negative_same_family_count": len(same_family_rows),
        "negative_cross_family_violation_count": sum(
            1 for row in cross_family_rows if row["false_positive"]
        ),
        "claim_boundary": (
            "Negative cross-family anti-drift rows prove that similar public "
            "events from another family are penalized when flagged. They are "
            "separate from positive family-cross-contamination checks."
        ),
    }


def run_benchmark(
    *,
    dataset_path: Path | str = DEFAULT_DATASET,
    predictions_file: Path | str | None = None,
    closed_book_predictions_file: Path | str | None = None,
    event_metadata_file: Path | str | None = None,
    baseline: str = "gold",
    production_like_retrieval: bool = False,
    source_disambiguation_top_k: int = 1,
    source_disambiguation_min_score: float = 1.0,
    require_cc0_dataset: bool = True,
    min_recall: float = 1.0,
    min_precision: float = 1.0,
    max_false_positives: int = 0,
    gate_statistic: str = "point",
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset = load_dataset(dataset_path, require_cc0=require_cc0_dataset)
    event_metadata = load_event_metadata(event_metadata_file)
    source_disambiguation: dict[str, Any] | None = None
    if production_like_retrieval and predictions_file:
        raise ValueError("--production-like-retrieval cannot be combined with --predictions")
    if production_like_retrieval:
        predictions, source_disambiguation_rows = source_disambiguation_case_rows(
            dataset,
            event_metadata=event_metadata,
            top_k=source_disambiguation_top_k,
            min_score=source_disambiguation_min_score,
        )
        source_disambiguation = summarize_source_disambiguation_cases(
            source_disambiguation_rows,
            top_k=source_disambiguation_top_k,
            min_score=source_disambiguation_min_score,
        )
    else:
        predictions = (
            load_predictions(Path(predictions_file).resolve())
            if predictions_file
            else baseline_predictions(dataset, baseline)
        )
    event_rows, prediction_rows = score_predictions(
        dataset,
        predictions,
        event_metadata=event_metadata,
    )
    metrics = summarize(event_rows, prediction_rows)
    closed_book: dict[str, Any] | None = None
    if closed_book_predictions_file:
        closed_book_predictions = load_predictions(Path(closed_book_predictions_file).resolve())
        closed_event_rows, closed_prediction_rows = score_predictions(
            dataset,
            closed_book_predictions,
            event_metadata=event_metadata,
        )
        closed_metrics = summarize(closed_event_rows, closed_prediction_rows)
        closed_book = {
            "predictions_file_sha1": sha1_text(str(closed_book_predictions_file))[:16],
            "metrics": closed_metrics,
            "source_over_closed_book_lift": {
                "recall": round(
                    float(metrics["future_event_flag_recall_rate"])
                    - float(closed_metrics["future_event_flag_recall_rate"]),
                    4,
                ),
                "precision": round(
                    float(metrics["future_event_flag_precision"])
                    - float(closed_metrics["future_event_flag_precision"]),
                    4,
                ),
                "f1": round(
                    float(metrics["future_event_flag_f1"])
                    - float(closed_metrics["future_event_flag_f1"]),
                    4,
                ),
                "false_negative_reduction": int(closed_metrics["false_negative_count"])
                - int(metrics["false_negative_count"]),
            },
            "interpretation": (
                "If closed-book performance is near source-window performance, "
                "the fixture may be measuring pretrained public knowledge rather "
                "than source-backed recovery."
            ),
        }
    if gate_statistic not in {"point", "lower_bound"}:
        raise ValueError("gate_statistic must be 'point' or 'lower_bound'")
    gate_applied_to_status = gate_statistic == "lower_bound"
    recall_gate = lower_bound_gate(
        metrics["rate_estimates"]["future_event_flag_recall"],
        threshold=min_recall,
        applied_to_status=gate_applied_to_status,
    )
    precision_gate = lower_bound_gate(
        metrics["rate_estimates"]["future_event_flag_precision"],
        threshold=min_precision,
        applied_to_status=gate_applied_to_status,
    )
    if gate_applied_to_status:
        rate_gate_ok = (
            recall_gate["passes_lower_bound"]
            and precision_gate["passes_lower_bound"]
        )
    else:
        rate_gate_ok = (
            recall_gate["passes_point_estimate"]
            and precision_gate["passes_point_estimate"]
        )
    ok = bool(rate_gate_ok and int(metrics["false_positive_count"]) <= int(max_false_positives))
    row_licenses = sorted({str(row.get("license") or "") for row in dataset.rows})
    source_families = sorted({str(row.get("source_family") or "") for row in dataset.rows})
    has_rollout_sources = any("rollout" in source_family for source_family in source_families)
    claim_boundary = (
        "V1 is a hard-event public contract fixture. It proves recall-aware "
        "scoring semantics over deterministic rollout behavior traces, not "
        "live agent quality or private real-history continuity."
        if has_rollout_sources
        else (
            "V1 is a VCS-shaped public contract fixture. It proves recall-aware "
            "scoring semantics, not wild MSR/Gerrit/SATD corpus performance."
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_vcs_future_event_recall_benchmark",
        "generated_at": now_utc(),
        "status": "future_event_recall_scored",
        "ok": ok,
        "quality_gate_ok": ok,
        "config": {
            "dataset_path_sha1": sha1_text(str(Path(dataset_path).resolve()))[:16],
            "predictions_file_sha1": sha1_text(str(predictions_file))[:16]
            if predictions_file
            else None,
            "closed_book_predictions_file_sha1": sha1_text(str(closed_book_predictions_file))[:16]
            if closed_book_predictions_file
            else None,
            "event_metadata_file_sha1": sha1_text(str(Path(event_metadata_file).resolve()))[:16]
            if event_metadata_file
            else None,
            "prediction_source": (
                "production_like_retrieval"
                if production_like_retrieval
                else ("external_predictions" if predictions_file else f"{baseline}_baseline")
            ),
            "baseline": None if (predictions_file or production_like_retrieval) else baseline,
            "closed_book_ablation": bool(closed_book_predictions_file),
            "require_cc0_dataset": require_cc0_dataset,
            "production_like_retrieval": production_like_retrieval,
            "source_disambiguation_top_k": source_disambiguation_top_k,
            "source_disambiguation_min_score": source_disambiguation_min_score,
            "min_recall": min_recall,
            "min_precision": min_precision,
            "max_false_positives": max_false_positives,
            "gate_statistic": gate_statistic,
            "live_llm": False,
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "fixture": public_path_label(dataset_path),
            "license": row_licenses[0] if len(row_licenses) == 1 else "mixed",
            "source_family": source_families[0] if len(source_families) == 1 else "mixed",
            "project_count": len(dataset.rows),
            "future_event_count": len(dataset.events_by_id),
            "future_event_gold_available": True,
            "hard_event_kinds": sorted({row["hard_event_kind"] for row in event_rows}),
            "claim_boundary": claim_boundary,
        },
        "metrics": metrics,
        "precision_contract": {
            "primary_metric": "future_event_flag_precision",
            "primary_definition": (
                "true positives require a flag-worthy event, all required "
                "past source ids, and no full-support-blocking source degradation"
            ),
            "diagnostic_metric": "diagnostic_event_identity_precision",
            "diagnostic_definition": (
                "known flag-worthy event ids among predicted flags, ignoring "
                "required-source support; useful for debugging but not for the "
                "source-backed quality gate"
            ),
        },
        "claim_levels": claim_levels(
            production_like_retrieval=production_like_retrieval,
            predictions_file=predictions_file,
            baseline=baseline,
        ),
        "source_disambiguation": source_disambiguation
        or {
            "available": False,
            "why": "Run with --production-like-retrieval to score local source disambiguation.",
        },
        "candidate_discovery_bias": dataset.candidate_discovery_bias,
        "source_degradation_controls": source_degradation_controls(event_rows),
        "anti_drift_controls": anti_drift_controls(event_rows),
        "lower_bound_gates": {
            "future_event_flag_recall": recall_gate,
            "future_event_flag_precision": precision_gate,
        },
        "contamination_control": {
            "closed_book_ablation_available": bool(closed_book_predictions_file),
            "closed_book": closed_book,
            "time_split_required_for_public_claims": True,
            "counterfactual_perturbation_required_for_public_claims": True,
            "private_real_history_must_report_separately": True,
            "why": (
                "Public VCS outcomes may be memorized by pretrained models. "
                "Closed-book collapse is the cheap first contamination test; "
                "time splits and counterfactual variants are needed before "
                "wild public-corpus claims."
            ),
        },
        "events": event_rows,
        "predictions": prediction_rows,
        "privacy_boundary": {
            "fixture_contains_private_user_data": False,
            "raw_event_text_emitted": False,
            "raw_past_source_text_emitted": False,
            "absolute_paths_emitted": False,
            "event_ids_are_public": True,
            "output_shape": "sanitized_vcs_future_event_recall_scores",
        },
        "cannot_claim": [
            "wild_vcs_corpus_quality",
            "contamination_resistant_public_score_without_closed_book_lift",
            "private_real_history_coding_continuity_quality",
            "live_dream_worker_quality",
            "external_baseline_superiority",
            "soft_semantic_reopen_support",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus VCS future-event recall benchmark")
    print(
        f"- gold_events: {metrics['future_event_gold_count']} "
        f"predicted_flags: {metrics['predicted_flag_count']}"
    )
    print(
        f"- recall: {metrics['future_event_flag_recall_rate']:.2%} "
        f"precision: {metrics['future_event_flag_precision']:.2%} "
        f"f1: {metrics['future_event_flag_f1']:.2%}"
    )
    print(
        f"- false_negatives: {metrics['false_negative_count']} "
        f"false_positives: {metrics['false_positive_count']} "
        f"anti_drift_pass: {metrics['anti_drift_pass_rate']:.2%}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--closed-book-predictions", type=Path, default=None)
    parser.add_argument(
        "--event-metadata",
        type=Path,
        default=None,
        help=(
            "Optional sanitized event metadata JSON with fields such as track. "
            "Gold required source ids are still used only for grading."
        ),
    )
    parser.add_argument("--baseline", choices=["gold", "empty"], default="gold")
    parser.add_argument(
        "--production-like-retrieval",
        action="store_true",
        help=(
            "Build a local past-window source index and rank sources without "
            "required_past_source_ids as prediction input."
        ),
    )
    parser.add_argument("--source-disambiguation-top-k", type=int, default=1)
    parser.add_argument("--source-disambiguation-min-score", type=float, default=1.0)
    parser.add_argument(
        "--allow-non-cc0-dataset",
        action="store_true",
        help=(
            "Allow scoring an external public VCS dataset with a non-CC0 license. "
            "Use only for local reports whose raw dataset is not checked into the repo."
        ),
    )
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--min-precision", type=float, default=1.0)
    parser.add_argument("--max-false-positives", type=int, default=0)
    parser.add_argument(
        "--gate-statistic",
        choices=["point", "lower_bound"],
        default="point",
        help="Use point estimates by default; lower_bound applies Wilson lower bounds to status.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        dataset_path=args.dataset,
        predictions_file=args.predictions,
        closed_book_predictions_file=args.closed_book_predictions,
        event_metadata_file=args.event_metadata,
        baseline=args.baseline,
        production_like_retrieval=args.production_like_retrieval,
        source_disambiguation_top_k=args.source_disambiguation_top_k,
        source_disambiguation_min_score=args.source_disambiguation_min_score,
        require_cc0_dataset=not args.allow_non_cc0_dataset,
        min_recall=args.min_recall,
        min_precision=args.min_precision,
        max_false_positives=args.max_false_positives,
        gate_statistic=args.gate_statistic,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
