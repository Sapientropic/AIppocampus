"""Public semantic-sidecar Track B adapter."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import smoke_source_evidence_recall_eval as source_evidence_eval

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.model.client import DEEPSEEK_PREFIX_CACHE_CONTRACT
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.semantic_scope_labels import (
    SEMANTIC_SCOPE_LABELS_FILENAME,
    clean_messages_by_id,
    load_semantic_scope_labels,
    semantic_scope_label_rows_from_findings,
    write_semantic_scope_label_sidecar,
)
from aippocampus_runtime.subconscious.runtime import call_chat_json, compact_usage
from aippocampus_runtime.subconscious.worker import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    parse_model_json,
)

from .defaults import (
    DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT,
    DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR,
    PUBLIC_SEMANTIC_SELECTION_METHOD,
    SCHEMA_VERSION,
    PublicSemanticLabelerFn,
)
from .reporting import claim_boundary, now_utc, query_origin, sha1_text
from .selected_source import summarize_source_payload
from .sharegpt_public import load_sharegpt_conversations, normalize_source_line


def public_semantic_source_ref(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "source_line": message.get("source_line"),
        "role": message.get("role"),
        "phase": message.get("phase") or "",
    }


def public_semantic_turn_rows(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_turn: dict[str, list[dict[str, Any]]] = {}
    for message in messages:
        turn_id = str(message.get("turn_id") or "")
        if not turn_id:
            continue
        by_turn.setdefault(turn_id, []).append(message)
    turns: list[dict[str, Any]] = []
    for turn_id, rows in by_turn.items():
        lines = [normalize_source_line(row, idx + 1) for idx, row in enumerate(rows)]
        turn_indices = [int(row.get("turn_index") or 0) for row in rows]
        turns.append(
            {
                "turn_id": turn_id,
                "turn_index": min(turn_indices) if turn_indices else 0,
                "message_ids": [
                    str(row.get("message_id") or row.get("id") or "")
                    for row in rows
                    if row.get("message_id") or row.get("id")
                ],
                "start_line": min(lines) if lines else None,
                "end_line": max(lines) if lines else None,
            }
        )
    turns.sort(key=lambda item: (int(item.get("turn_index") or 0), str(item.get("turn_id") or "")))
    return turns


def public_semantic_subset_messages(
    conversations: list[list[dict[str, Any]]], *, max_messages: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    source_line = 1
    for rows in conversations:
        for row in rows:
            if len(selected) >= max(1, int(max_messages)):
                return selected
            text = str(row.get("text") or "").strip()
            message_id = str(row.get("message_id") or "").strip()
            turn_id = str(row.get("turn_id") or "").strip()
            if not text or not message_id or not turn_id:
                continue
            selected.append(
                {
                    **row,
                    "source_line": source_line,
                    "clean_ordinal": source_line - 1,
                    "text": text,
                }
            )
            source_line += 1
    return selected


def write_public_semantic_subset_pack(
    *,
    output_dir: Path,
    corpus_dir: Path,
    conversations: list[list[dict[str, Any]]],
    max_messages: int,
) -> dict[str, Any]:
    clean_source_dir = output_dir / "clean-source"
    registry_dir = output_dir / "registry"
    messages_path = clean_source_dir / "messages.jsonl"
    turns_path = clean_source_dir / "turns.jsonl"
    registry_path = registry_dir / "threads.json"
    messages = public_semantic_subset_messages(conversations, max_messages=max_messages)
    turns = public_semantic_turn_rows(messages)
    clean_source_dir.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)
    messages_path.write_text(
        "".join(json.dumps(message, ensure_ascii=False) + "\n" for message in messages),
        encoding="utf-8",
    )
    turns_path.write_text(
        "".join(json.dumps(turn, ensure_ascii=False) + "\n" for turn in turns),
        encoding="utf-8",
    )
    thread_key = f"public-semantic-sidecar:{sha1_text(str(corpus_dir))[:12]}"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": thread_key,
                        "title": "Public semantic sidecar benchmark subset",
                        "workspace_name": "benchmark_corpus",
                        "project_key": "project:public_semantic_sidecar",
                        "project_label": "public_semantic_sidecar",
                        "project_tags": ["benchmark", "public", "semantic-sidecar"],
                        "paths": {
                            "clean_source_messages_jsonl": "clean-source/messages.jsonl",
                            "clean_source_turns_jsonl": "clean-source/turns.jsonl",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": output_dir,
        "clean_source_dir": clean_source_dir,
        "messages_path": messages_path,
        "turns_path": turns_path,
        "registry_path": registry_path,
        "messages": messages,
        "turns": turns,
        "thread_key": thread_key,
    }


def public_semantic_candidate_messages(
    messages: list[dict[str, Any]], *, max_candidates: int
) -> list[dict[str, Any]]:
    candidates = []
    for message in messages:
        text = str(message.get("text") or "").strip()
        if not text or not message.get("message_id"):
            continue
        role = str(message.get("role") or "")
        score = min(len(text), 800) / 100.0
        if role == "user":
            score += 3.0
        if "?" in text or "？" in text:
            score += 0.4
        candidates.append((score, message))
    candidates.sort(
        key=lambda item: (
            -item[0],
            normalize_source_line(item[1], 1),
            str(item[1].get("message_id") or ""),
        )
    )
    return [
        {
            "message_id": message.get("message_id") or message.get("id"),
            "turn_id": message.get("turn_id"),
            "source_line": message.get("source_line"),
            "role": message.get("role"),
            "phase": message.get("phase") or "",
            "text": compact_text(str(message.get("text") or ""), 900),
        }
        for _, message in candidates[: max(1, int(max_candidates))]
    ]


def public_semantic_full_source_candidate_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return every clean-source message as a labeler candidate in source order."""

    candidates: list[dict[str, Any]] = []
    for message in sorted(messages, key=lambda item: normalize_source_line(item, 1)):
        text = str(message.get("text") or "").strip()
        if not text or not message.get("message_id"):
            continue
        candidates.append(
            {
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "source_line": message.get("source_line"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "text": compact_text(text, 900),
            }
        )
    return candidates


def public_semantic_labeler_messages(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    system = """You are labeling public benchmark clean-source messages for AIppocampus.
Return one valid JSON object only. Labels are navigation hints, not source truth."""
    user = json.dumps(
        {
            "canonical_scope_labels": list(SCOPE_LABEL_ORDER),
            "required_top_level_shape": {"findings": ["finding objects"]},
            "task": (
                "For each candidate that genuinely needs a fuzzy semantic scope label, "
                "return one source-backed semantic_scope_labels finding. Omit candidates "
                "that only have keyword matches or ordinary one-off assistant requests. "
                "Keep the findings list compact; an empty findings list is valid."
            ),
            "label_rules": {
                "personal_reflection": "self, feelings, doubts, identity, or meaning",
                "relationship_continuity": "explicit shared history or ongoing relationship arc",
                "reading_notes": "explicit books, papers, essays, articles, or notes",
                "idea_seed": "new direction, metaphor, possibility, or spark to revisit",
                "preference": "stable or situational way something should be done",
                "life_context": "concrete lived circumstance, body, schedule, mood, or day-to-day situation",
                "technical_work": "implementation, tools, architecture, tests, or technical decisions",
                "open_question": "explicit unresolved question, uncertainty, or inquiry to pursue later",
            },
            "required_finding_shape": {
                "finding_kind": "semantic_scope_labels",
                "job": "semantic_scope_labeling",
                "message_id": "candidate message_id",
                "turn_id": "candidate turn_id",
                "scope_labels": ["canonical labels only"],
                "confidence": "0.0-1.0",
                "summary": "short source-grounded summary",
                "source_refs": [
                    {
                        "message_id": "same message_id",
                        "turn_id": "same turn_id",
                        "source_line": "candidate source_line",
                        "role": "candidate role",
                        "phase": "candidate phase",
                    }
                ],
                "label_evidence": [
                    {
                        "label": "canonical label",
                        "reason": "one short reason grounded in this exact message",
                        "confidence": "0.0-1.0",
                    }
                ],
            },
            "candidate_messages": candidates,
        },
        ensure_ascii=False,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def normalize_public_semantic_findings(
    findings: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidate_by_id = {
        str(candidate.get("message_id") or ""): candidate
        for candidate in candidates
        if candidate.get("message_id")
    }
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        message_id = str(finding.get("message_id") or finding.get("id") or "").strip()
        candidate = candidate_by_id.get(message_id)
        if not candidate:
            continue
        item = dict(finding)
        item["message_id"] = message_id
        item["turn_id"] = item.get("turn_id") or candidate.get("turn_id")
        item["job"] = "semantic_scope_labeling"
        item["finding_kind"] = "semantic_scope_labels"
        item["source"] = item.get("source") or "public_semantic_sidecar_labeler"
        exact_refs = [
            ref
            for ref in item.get("source_refs") or []
            if isinstance(ref, dict)
            and str(ref.get("message_id") or "").strip() == message_id
        ]
        if not exact_refs:
            exact_refs = [public_semantic_source_ref(candidate)]
        item["source_refs"] = exact_refs
        normalized.append(item)
    return normalized


def run_public_semantic_labeler(
    candidates: list[dict[str, Any]],
    *,
    api_key_env: str = "DEEPSEEK_API_KEY",
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
) -> dict[str, Any]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        return {
            "available": False,
            "findings": [],
            "errors": ["missing semantic labeler api key"],
        }
    if not candidates:
        return {"available": False, "findings": [], "errors": ["empty candidate set"]}
    response = call_chat_json(
        public_semantic_labeler_messages(candidates),
        api_key,
        model or os.environ.get("AIPPOCAMPUS_PUBLIC_SEMANTIC_MODEL") or DEFAULT_MODEL,
        base_url or os.environ.get("AIPPOCAMPUS_PUBLIC_SEMANTIC_BASE_URL") or DEFAULT_BASE_URL,
        None if int(max_tokens) <= 0 else int(max_tokens),
        int(timeout),
        0.0,
        cache_contract=DEEPSEEK_PREFIX_CACHE_CONTRACT,
    )
    parsed = parse_model_json(response)
    raw_findings = parsed.get("findings") if isinstance(parsed, dict) else []
    findings = [item for item in raw_findings or [] if isinstance(item, dict)]
    return {
        "available": True,
        "findings": normalize_public_semantic_findings(findings, candidates),
        "usage": compact_usage(response.get("usage") or {}),
    }


def summarize_public_semantic_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "public_semantic_sidecar_source_evidence",
        "status": payload.get("status"),
        "ok": bool(payload.get("ok")),
        "claim_level": payload.get("claim_level"),
        "sample_case_count": int(payload.get("sample_case_count") or 0),
        "minimum_empirical_case_count": int(
            payload.get("minimum_empirical_case_count") or 0
        ),
        "selection_method": payload.get("selection_method"),
        "sample_size_warning": payload.get("sample_size_warning"),
        "config": payload.get("config") or {},
        "corpus": payload.get("corpus") or {},
        "artifacts": payload.get("artifacts") or {},
        "metrics": payload.get("metrics") or {},
        "anti_circular_controls": payload.get("anti_circular_controls") or {},
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cannot_claim": payload.get("cannot_claim") or [],
        "skip_reason": payload.get("skip_reason"),
        "query_origin": query_origin(
            "source_derived_sparse",
            query_author="public semantic sidecar labeler over clean-source rows",
            notes=(
                "Semantic-sidecar labels are source-backed navigation hints over the "
                "public clean-source subset, not independently authored user queries."
            ),
        ),
        "claim_boundary": claim_boundary(
            measures="public_source_labeled_source_navigation",
            can_claim=["public_semantic_sidecar_source_navigation_diagnostic"],
            cannot_claim=[
                "natural_user_query_recall",
                "human_reviewed_semantic_labels",
                "unbounded_public_semantic_sidecar_quality",
            ],
        ),
        "elapsed_ms": payload.get("elapsed_ms"),
    }


def public_semantic_status(
    source_payload: dict[str, Any],
    *,
    sidecar_rows: int,
    sample_case_count: int,
    minimum_empirical_case_count: int,
) -> str:
    if int(sidecar_rows) <= 0:
        return "insufficient_sidecar_rows"
    if str(source_payload.get("status") or "").startswith("insufficient_selected_cases"):
        return "insufficient_selected_cases"
    if not source_payload.get("ok"):
        return str(source_payload.get("status") or "diagnostic_only")
    if int(sample_case_count) < int(minimum_empirical_case_count):
        return "diagnostic_only"
    return "sufficient"


def public_semantic_claim_level(status: str) -> str:
    if status == "sufficient":
        return "empirical_benchmark"
    if status == "diagnostic_only":
        return "diagnostic_pilot"
    return "diagnostic_only"


def public_semantic_sample_size_warning(
    *,
    sample_case_count: int,
    minimum_empirical_case_count: int,
    claim_level: str,
) -> dict[str, Any] | None:
    if sample_case_count >= minimum_empirical_case_count:
        return None
    return {
        "sample_case_count": sample_case_count,
        "minimum_empirical_case_count": minimum_empirical_case_count,
        "claim_level": claim_level,
        "selection_method": PUBLIC_SEMANTIC_SELECTION_METHOD,
        "cannot_claim": [
            "empirical_public_semantic_sidecar_quality_below_minimum_case_count"
        ],
    }


def public_semantic_eval_control_summary(
    payload: dict[str, Any], *, control_kind: str
) -> dict[str, Any]:
    return {
        "control_kind": control_kind,
        "status": payload.get("status"),
        "ok": bool(payload.get("ok")),
        "sample_gate_ok": bool(payload.get("sample_gate_ok")),
        "quality_gate_ok": bool(payload.get("quality_gate_ok")),
        "case_count": int(payload.get("case_count") or 0),
        "passed_count": int(payload.get("passed_count") or 0),
        "failed_count": int(payload.get("failed_count") or 0),
        "top_k_hit_rate": float(payload.get("top_k_hit_rate") or 0.0),
        "selection_mode": (payload.get("selection") or {}).get("mode"),
        "cannot_claim": payload.get("cannot_claim") or [],
    }


def public_semantic_control_deltas(
    *,
    sidecar: dict[str, Any],
    no_sidecar_baseline: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sidecar_vs_no_sidecar_case_delta": int(sidecar.get("case_count") or 0)
        - int(no_sidecar_baseline.get("case_count") or 0),
        "sidecar_vs_no_sidecar_passed_delta": int(sidecar.get("passed_count") or 0)
        - int(no_sidecar_baseline.get("passed_count") or 0),
        "sidecar_vs_no_sidecar_hit_rate_delta": round(
            float(sidecar.get("top_k_hit_rate") or 0.0)
            - float(no_sidecar_baseline.get("top_k_hit_rate") or 0.0),
            4,
        ),
    }


def wrong_message_semantic_sidecar_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = dict(row)
        wrong_message_id = f"wrong-message-control-{index}"
        wrong_turn_id = f"wrong-turn-control-{index}"
        item["message_id"] = wrong_message_id
        item["turn_id"] = wrong_turn_id
        item["source_refs"] = [
            {
                "message_id": wrong_message_id,
                "turn_id": wrong_turn_id,
                "source_line": 0,
                "role": "control",
                "phase": "wrong_message_negative",
            }
        ]
        item["control_kind"] = "wrong_message_negative"
        controls.append(item)
    return controls


def run_public_semantic_source_eval(
    subset: dict[str, Any],
    *,
    max_cases: int,
    min_cases: int,
    top_k: int,
    min_hit_rate: float,
    require_semantic_sidecar: bool,
) -> dict[str, Any]:
    return source_evidence_eval.run_source_evidence_recall_eval(
        registry_path=subset["registry_path"],
        max_cases=max_cases,
        min_cases=min_cases,
        top_k=top_k,
        min_hit_rate=min_hit_rate,
        require_semantic_sidecar=require_semantic_sidecar,
        ranking="dynamic_source",
    )


def skipped_public_semantic_sidecar_payload(
    *,
    started: float,
    reason: str,
    status: str,
    config: dict[str, Any],
    corpus_dir: Path,
    include_private_text: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "public_semantic_sidecar_source_evidence",
        "generated_at": now_utc(),
        "status": status,
        "ok": True,
        "claim_level": "not_run",
        "sample_case_count": 0,
        "minimum_empirical_case_count": DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT,
        "selection_method": PUBLIC_SEMANTIC_SELECTION_METHOD,
        "sample_size_warning": None,
        "config": config,
        "corpus": {
            "corpus_dir_sha1": sha1_text(str(corpus_dir))[:16],
            "conversation_count": 0,
            "subset_message_count": 0,
            "candidate_message_count": 0,
        },
        "artifacts": {
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "absolute_paths_emitted": bool(include_private_text),
        },
        "metrics": {"case_count": 0, "passed_count": 0, "failed_count": 0},
        "cases": [],
        "skip_reason": reason,
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": False,
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_public_semantic_sidecar",
        },
        "cannot_claim": [
            "private_real_history_source_evidence_quality",
            "human_reviewed_semantic_labels",
            "unbounded_public_semantic_sidecar_quality",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_public_semantic_sidecar_benchmark(
    *,
    corpus_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    conversations: int = DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    max_messages: int = DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    max_candidates: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    max_cases: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    min_cases: int = DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    top_k: int = DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    min_hit_rate: float = DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    min_confidence: float = DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    include_private_text: bool = False,
    labeler_fn: PublicSemanticLabelerFn | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_corpus_dir = Path(corpus_dir or DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR).resolve()
    resolved_output_dir = (
        Path(output_dir).resolve()
        if output_dir
        else Path(tempfile.mkdtemp(prefix="aippocampus-public-semantic-sidecar-")).resolve()
    )
    config = {
        "corpus": "sharegpt_public_clean_source",
        "corpus_dir_sha1": sha1_text(str(resolved_corpus_dir))[:16],
        "artifact_dir_sha1": sha1_text(str(resolved_output_dir))[:16],
        "conversations": int(conversations),
        "max_messages": int(max_messages),
        "max_candidates": int(max_candidates),
        "max_cases": int(max_cases),
        "min_cases": int(min_cases),
        "top_k": int(top_k),
        "min_hit_rate": float(min_hit_rate),
        "min_confidence": float(min_confidence),
        "timeout": int(timeout),
        "max_tokens": int(max_tokens),
        "include_private_text": bool(include_private_text),
        "minimum_empirical_case_count": DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT,
    }
    try:
        conversations_payload = load_sharegpt_conversations(
            resolved_corpus_dir,
            max_conversations=conversations,
        )
    except FileNotFoundError as exc:
        return skipped_public_semantic_sidecar_payload(
            started=started,
            reason=str(exc),
            status="skipped_missing_public_corpus",
            config=config,
            corpus_dir=resolved_corpus_dir,
            include_private_text=include_private_text,
        )
    subset = write_public_semantic_subset_pack(
        output_dir=resolved_output_dir,
        corpus_dir=resolved_corpus_dir,
        conversations=conversations_payload,
        max_messages=max_messages,
    )
    candidates = public_semantic_candidate_messages(
        list(subset["messages"]),
        max_candidates=max_candidates,
    )
    sidecar_path = subset["clean_source_dir"] / SEMANTIC_SCOPE_LABELS_FILENAME
    if sidecar_path.exists():
        sidecar_path.unlink()
    no_sidecar_payload = run_public_semantic_source_eval(
        subset,
        max_cases=max_cases,
        min_cases=min_cases,
        top_k=top_k,
        min_hit_rate=min_hit_rate,
        require_semantic_sidecar=False,
    )
    try:
        if labeler_fn:
            labeler_payload = labeler_fn(candidates)
        else:
            labeler_payload = run_public_semantic_labeler(
                candidates,
                timeout=timeout,
                max_tokens=max_tokens,
            )
    except Exception as exc:
        return skipped_public_semantic_sidecar_payload(
            started=started,
            reason=f"{type(exc).__name__}: {compact_text(str(exc), 360)}",
            status="skipped_semantic_labeler_error",
            config=config,
            corpus_dir=resolved_corpus_dir,
            include_private_text=include_private_text,
        )
    if not labeler_payload.get("available", True):
        return skipped_public_semantic_sidecar_payload(
            started=started,
            reason="; ".join(str(item) for item in labeler_payload.get("errors") or []),
            status="skipped_missing_semantic_backend",
            config=config,
            corpus_dir=resolved_corpus_dir,
            include_private_text=include_private_text,
        )
    messages_by_id = clean_messages_by_id(subset["clean_source_dir"])
    findings = normalize_public_semantic_findings(
        [item for item in labeler_payload.get("findings") or [] if isinstance(item, dict)],
        candidates,
    )
    sidecar_rows = semantic_scope_label_rows_from_findings(
        findings,
        messages_by_id,
        min_confidence=min_confidence,
    )
    write_semantic_scope_label_sidecar(subset["clean_source_dir"], sidecar_rows)
    reviewed_sidecar = load_semantic_scope_labels(subset["clean_source_dir"])
    source_payload = run_public_semantic_source_eval(
        subset,
        max_cases=max_cases,
        min_cases=min_cases,
        top_k=top_k,
        min_hit_rate=min_hit_rate,
        require_semantic_sidecar=True,
    )
    write_semantic_scope_label_sidecar(
        subset["clean_source_dir"],
        wrong_message_semantic_sidecar_rows(sidecar_rows),
    )
    wrong_message_payload = run_public_semantic_source_eval(
        subset,
        max_cases=max_cases,
        min_cases=min_cases,
        top_k=top_k,
        min_hit_rate=min_hit_rate,
        require_semantic_sidecar=True,
    )
    write_semantic_scope_label_sidecar(subset["clean_source_dir"], sidecar_rows)
    sample_case_count = int(source_payload.get("case_count") or 0)
    status = public_semantic_status(
        source_payload,
        sidecar_rows=len(sidecar_rows),
        sample_case_count=sample_case_count,
        minimum_empirical_case_count=DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT,
    )
    claim_level = public_semantic_claim_level(status)
    sample_warning = public_semantic_sample_size_warning(
        sample_case_count=sample_case_count,
        minimum_empirical_case_count=DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT,
        claim_level=claim_level,
    )
    no_sidecar_summary = public_semantic_eval_control_summary(
        no_sidecar_payload,
        control_kind="no_sidecar",
    )
    sidecar_summary = public_semantic_eval_control_summary(
        source_payload,
        control_kind="semantic_sidecar",
    )
    wrong_message_summary = public_semantic_eval_control_summary(
        wrong_message_payload,
        control_kind="wrong_message",
    )
    anti_circular_gate_passed = not bool(wrong_message_summary["quality_gate_ok"])
    quality_gate_ok = (
        bool(source_payload.get("ok")) and len(sidecar_rows) > 0 and anti_circular_gate_passed
    )
    if not anti_circular_gate_passed and status == "sufficient":
        status = "anti_circular_control_failed"
        claim_level = public_semantic_claim_level(status)
    metrics = {
        "case_count": sample_case_count,
        "passed_count": int(source_payload.get("passed_count") or 0),
        "failed_count": int(source_payload.get("failed_count") or 0),
        "top_k_hit_rate": float(source_payload.get("top_k_hit_rate") or 0.0),
        "rate_estimates": source_payload.get("rate_estimates") or {},
        "warning_count": int(source_payload.get("warning_count") or 0),
        "label_coverage": source_payload.get("label_coverage") or [],
    }
    artifacts = {
        "sidecar_filename": SEMANTIC_SCOPE_LABELS_FILENAME,
        "sidecar_row_count": len(sidecar_rows),
        "reviewed_sidecar_row_count": len(reviewed_sidecar),
        "artifact_dir_sha1": sha1_text(str(resolved_output_dir))[:16],
        "registry_sha1": sha1_text((subset["registry_path"]).read_text(encoding="utf-8"))[:16],
        "messages_sha1": sha1_text((subset["messages_path"]).read_text(encoding="utf-8"))[:16],
        "sidecar_sha1": sha1_text(
            (subset["clean_source_dir"] / SEMANTIC_SCOPE_LABELS_FILENAME).read_text(
                encoding="utf-8"
            )
        )[:16],
        "absolute_paths_emitted": bool(include_private_text),
    }
    if include_private_text:
        artifacts.update(
            {
                "artifact_dir": str(resolved_output_dir),
                "registry_path": str(subset["registry_path"]),
                "sidecar_path": str(subset["clean_source_dir"] / SEMANTIC_SCOPE_LABELS_FILENAME),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "public_semantic_sidecar_source_evidence",
        "generated_at": now_utc(),
        "status": status,
        "ok": quality_gate_ok,
        "quality_gate_ok": quality_gate_ok,
        "claim_level": claim_level,
        "sample_case_count": sample_case_count,
        "minimum_empirical_case_count": DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT,
        "selection_method": PUBLIC_SEMANTIC_SELECTION_METHOD,
        "sample_size_warning": sample_warning,
        "config": config,
        "corpus": {
            "corpus_dir_sha1": sha1_text(str(resolved_corpus_dir))[:16],
            "conversation_count": len(conversations_payload),
            "subset_message_count": len(subset["messages"]),
            "subset_turn_count": len(subset["turns"]),
            "candidate_message_count": len(candidates),
            "thread_count": 1,
        },
        "artifacts": artifacts,
        "metrics": metrics,
        "cases": [
            dict(case)
            for case in source_payload.get("cases") or []
            if isinstance(case, dict)
        ],
        "labeler": {
            "available": bool(labeler_payload.get("available", True)),
            "finding_count": len(findings),
            "usage": compact_usage(labeler_payload.get("usage") or {}),
            "error_count": len(labeler_payload.get("errors") or []),
            "identity": str(
                labeler_payload.get("labeler_identity")
                or ("custom_labeler_fn" if labeler_fn else "public_semantic_labeler")
            ),
            "review_status": str(labeler_payload.get("review_status") or "validator_reviewed"),
            "human_reviewed": bool(labeler_payload.get("human_reviewed")),
        },
        "anti_circular_controls": {
            "sidecar": sidecar_summary,
            "no_sidecar_baseline": no_sidecar_summary,
            "wrong_message_negative": wrong_message_summary,
            "control_deltas": public_semantic_control_deltas(
                sidecar=sidecar_summary,
                no_sidecar_baseline=no_sidecar_summary,
            ),
            "anti_circular_gate": {
                "passed": anti_circular_gate_passed,
                "negative_control_quality_gate_ok": bool(
                    wrong_message_summary["quality_gate_ok"]
                ),
                "cannot_claim": []
                if anti_circular_gate_passed
                else ["semantic_sidecar_quality_without_passing_anti_circular_controls"],
            },
            "label_review_boundary": {
                "labeler_identity": str(
                    labeler_payload.get("labeler_identity")
                    or ("custom_labeler_fn" if labeler_fn else "public_semantic_labeler")
                ),
                "review_status": str(
                    labeler_payload.get("review_status") or "validator_reviewed"
                ),
                "human_reviewed": bool(labeler_payload.get("human_reviewed")),
                "cannot_claim": []
                if labeler_payload.get("human_reviewed")
                else ["human_reviewed_semantic_labels"],
            },
        },
        "source_evidence": summarize_source_payload(source_payload),
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_public_semantic_sidecar",
        },
        "cannot_claim": [
            "private_real_history_source_evidence_quality",
            "human_reviewed_semantic_labels",
            "unbounded_public_semantic_sidecar_quality",
            *(
                []
                if anti_circular_gate_passed
                else ["semantic_sidecar_quality_without_passing_anti_circular_controls"]
            ),
            *(
                sample_warning.get("cannot_claim", [])
                if isinstance(sample_warning, dict)
                else []
            ),
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
