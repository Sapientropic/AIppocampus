#!/usr/bin/env python3
"""Semantic ambient-recall gate for AIppocampus.

The deterministic prompt hook is intentionally conservative, but human recall is
not a fixed phrase table. This module adds an optional DeepSeek-compatible
semantic layer that can:

- decide whether a prompt wants old-thread memory at all
- generate multilingual query aliases for local source search
- choose recall scope and catch over-personalization risks

The model never becomes a source of truth. Its output only changes what local
clean-source / registry indexes search for, and final evidence must still come
from source-backed hits.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from aippocampus_runtime.core import (
    compact_text,
    now_utc,
    sanitize_external_model_payload,
    sanitize_external_model_text,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    resolve_model_route,
    route_cache_metrics,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.recall.semantic_cue_cache import (
    default_semantic_cues_path,
    semantic_cue_triggers,
)
from aippocampus_runtime.registry.api import load_registry, registry_paths, unique_preserve
from aippocampus_runtime.subconscious.runtime import add_usage, call_chat_json, compact_usage
from aippocampus_runtime.subconscious.worker import clamp_confidence, parse_model_json

PROMPT_VERSION = "aippocampus-semantic-recall-gate-v0"
SCHEMA_VERSION = 1
DEFAULT_CACHE_NAME = "semantic_recall_cache.json"
DEFAULT_TRIGGERS_NAME = "semantic_triggers.jsonl"
DEFAULT_TIMEOUT = int(os.environ.get("AIPPOCAMPUS_SEMANTIC_TIMEOUT", "12"))
DEFAULT_TEMPERATURE = float(os.environ.get("AIPPOCAMPUS_SEMANTIC_TEMPERATURE", "0.2"))
DEFAULT_MAX_CACHE_ENTRIES = 256
DEFAULT_CACHE_TTL_SECONDS = int(os.environ.get("AIPPOCAMPUS_SEMANTIC_CACHE_TTL", str(24 * 60 * 60)))
# Foreground semantic recall is quality-first. A limit of 0 means "send the full
# compact catalog"; env limits are explicit debug/perf overrides, not product
# defaults, because truncating the catalog silently turns into recall loss.
DEFAULT_MAX_CATALOG_ITEMS = int(os.environ.get("AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT", "0"))
DEFAULT_MAX_PROMPT_RELEVANT_CATALOG_ITEMS = 8
DEFAULT_MAX_TRIGGER_ITEMS = int(os.environ.get("AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT", "0"))
DEFAULT_MAX_PROMPT_RELEVANT_TRIGGER_ITEMS = 8
DEFAULT_WORKERS = ("gate", "alias", "scope")

VALID_DECISIONS = {"skip", "background_only", "scent", "evidence"}
DECISION_RANK = {"skip": 0, "background_only": 1, "scent": 2, "evidence": 3}
HIGH_RISK_MAX_DECISION = "scent"


ChatFn = Callable[..., dict[str, Any]]


SYSTEM_PROMPT = """You are AIppocampus semantic recall gate.
Your job is to decide whether a user's current prompt should receive ambient
old-thread memory hints, and to generate multilingual aliases for local memory
retrieval.

Rules:
- Be conservative. Ordinary coding/product tasks usually return skip or background_only.
- Use scent when prior conversation memory may help but is not requested as proof.
- Use evidence only when the user asks for exact prior wording, last reply, source-backed status, or a decision that depends on old-thread facts.
- Do not invent facts. Do not answer the user. Do not quote source text.
- Query aliases are search hints only; they are not claims.
- Prefer cross-lingual and paraphrase aliases when useful.
- Avoid over-personalizing generic work prompts.
- Return JSON only.
"""


def default_cache_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_CACHE_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_CACHE_NAME


def default_semantic_triggers_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_TRIGGERS_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_TRIGGERS_NAME


def semantic_gate_mode(value: str | None = None) -> str:
    raw = (
        (value if value is not None else os.environ.get("AIPPOCAMPUS_SEMANTIC_GATE", "auto"))
        .strip()
        .casefold()
    )
    if raw in {"0", "false", "off", "no", "disabled"}:
        return "off"
    if raw in {"1", "true", "on", "yes", "force"}:
        return "on"
    return "auto"


def semantic_gate_enabled(
    mode: str | None = None, *, api_key: str | None = None, api_key_env: str = "DEEPSEEK_API_KEY"
) -> bool:
    resolved = semantic_gate_mode(mode)
    if resolved == "off":
        return False
    key = api_key or os.environ.get(api_key_env)
    if resolved == "on":
        return bool(key)
    return bool(key)


def sanitize_prompt_for_semantic_gate(
    prompt: str,
    *,
    project_root: Path | str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Redact likely credentials before sending prompt text to a semantic model.

    The prompt hook is automatic, so credential handling must be stricter than a
    normal chat completion. Still, many useful prompts mention a token or
    connection string while asking a memory question. We redact known secret
    shapes and only hard-block prompts that are private-key dumps or mostly
    credentials after redaction.
    """

    return sanitize_external_model_text(prompt, project_root=project_root)


def prompt_may_contain_secret(prompt: str) -> bool:
    _, policy = sanitize_prompt_for_semantic_gate(prompt)
    return bool(policy.get("redacted") or policy.get("hard_block"))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def normalize_alias(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")
    if not text:
        return ""
    if len(text) > 96:
        return ""
    if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", text):
        return ""
    if prompt_may_contain_secret(text):
        return ""
    return text


def collect_aliases(values: list[Any], limit: int = 24) -> list[str]:
    aliases: list[str] = []
    for value in values:
        if isinstance(value, list):
            aliases.extend(collect_aliases(value, limit=limit))
            continue
        text = normalize_alias(value)
        if text:
            aliases.append(text)
            aliases.extend(split_query_terms([text])[:4])
    return unique_preserve(aliases, limit=limit)


def collect_exact_aliases(values: list[Any], limit: int = 24) -> list[str]:
    return unique_preserve([text for value in values if (text := normalize_alias(value))], limit)


def current_project_hint(registry: dict[str, Any], cwd: Path) -> str | None:
    target = str(cwd.resolve()).casefold()
    best: tuple[int, str] | None = None
    for entry in registry.get("threads") or []:
        paths = entry.get("paths") or {}
        workspace = str(
            paths.get("workspace") or (entry.get("session_meta") or {}).get("cwd") or ""
        )
        if not workspace:
            continue
        try:
            workspace_low = str(Path(workspace).resolve()).casefold()
        except Exception:
            workspace_low = workspace.casefold()
        score = 0
        if workspace_low == target:
            score = 3
        elif target.startswith(workspace_low) or workspace_low.startswith(target):
            score = 2
        if score:
            label = str(entry.get("project_label") or entry.get("workspace_name") or "")
            if label and (best is None or score > best[0]):
                best = (score, label)
    return best[1] if best else None


def entry_catalog_item(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "thread_key": entry.get("thread_key"),
        "title": compact_text(str(entry.get("title") or entry.get("workspace_name") or ""), 80),
        "project_label": entry.get("project_label") or entry.get("workspace_name"),
        "anchors": unique_preserve([str(x) for x in entry.get("anchor_titles") or []], limit=5),
        "keywords": unique_preserve([str(x) for x in entry.get("keywords") or []], limit=10),
        "summary": compact_text(str(entry.get("summary") or ""), 280),
        "updated_at": entry.get("updated_at") or (entry.get("session_meta") or {}).get("timestamp"),
    }


def catalog_overlap_score(entry: dict[str, Any], prompt_terms: list[str]) -> int:
    if not prompt_terms:
        return 0
    blob = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("project_label") or ""),
            " ".join(str(x) for x in entry.get("anchor_titles") or []),
            " ".join(str(x) for x in entry.get("keywords") or []),
            str(entry.get("summary") or ""),
        ]
    ).casefold()
    score = 0
    for term in prompt_terms:
        normalized = str(term or "").strip().casefold()
        if len(normalized) < 2:
            continue
        if normalized in blob:
            score += 3 if len(normalized) >= 6 else 1
    return score


def registry_catalog(
    registry: dict[str, Any],
    *,
    cwd: Path,
    limit: int = DEFAULT_MAX_CATALOG_ITEMS,
) -> list[dict[str, Any]]:
    project = current_project_hint(registry, cwd)
    scored: list[tuple[tuple[int, str], dict[str, Any]]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        has_memory_surface = bool(
            entry.get("anchor_titles") or entry.get("keywords") or entry.get("summary")
        )
        if not has_memory_surface:
            continue
        same_project = project and project == (
            entry.get("project_label") or entry.get("workspace_name")
        )
        score = 2 if same_project else 0
        score += 1 if entry.get("anchor_titles") else 0
        score += 1 if entry.get("keywords") else 0
        scored.append(((score, str(entry.get("updated_at") or "")), entry_catalog_item(entry)))
    scored.sort(key=lambda item: item[0], reverse=True)
    items = [item for _, item in scored]
    return items if limit <= 0 else items[:limit]


def prompt_relevant_catalog(
    registry: dict[str, Any],
    *,
    cwd: Path,
    prompt: str,
    limit: int = DEFAULT_MAX_PROMPT_RELEVANT_CATALOG_ITEMS,
) -> list[dict[str, Any]]:
    prompt_terms = split_query_terms([prompt])[:40] if prompt else []
    project = current_project_hint(registry, cwd)
    scored: list[tuple[tuple[int, str], dict[str, Any]]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        overlap = catalog_overlap_score(entry, prompt_terms)
        if overlap <= 0:
            continue
        same_project = project and project == (
            entry.get("project_label") or entry.get("workspace_name")
        )
        score = overlap + (2 if same_project else 0)
        scored.append(((score, str(entry.get("updated_at") or "")), entry_catalog_item(entry)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:limit]]


def trigger_from_working_memory(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "working_memory",
        "title": compact_text(str(row.get("title") or ""), 90),
        "aliases": collect_aliases(
            [
                row.get("title"),
                row.get("trigger_terms") or [],
                row.get("concepts") or [],
            ],
            limit=12,
        ),
        "when_to_use": compact_text(
            str(row.get("summary") or row.get("recommendation") or ""), 220
        ),
        "when_not_to_use": str(row.get("ask_policy") or ""),
        "confidence": row.get("confidence"),
        "route": row.get("route"),
        "project_label": row.get("project_label"),
    }


def trigger_from_association(term: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "association",
        "title": term,
        "aliases": collect_aliases([term, row.get("related_terms") or []], limit=12),
        "when_to_use": "Use as an ambient recall association only; search source before treating as evidence.",
        "status": row.get("status"),
        "confidence": row.get("confidence"),
    }


def trigger_overlap_score(trigger: dict[str, Any], prompt_terms: list[str]) -> int:
    if not prompt_terms:
        return 0
    activation_cues = trigger.get("activation_cues") or []
    if activation_cues:
        # Sidecar cues are the prompt route surface; prose stays context only.
        trigger_values = collect_exact_aliases([*activation_cues, *(trigger.get("aliases") or [])], 32)
    else:
        trigger_values = collect_aliases(
            [
                trigger.get("title"),
                trigger.get("aliases") or [],
                trigger.get("when_to_use"),
                trigger.get("project_label"),
            ],
            limit=32,
        )
    # `when_not_to_use` is reviewer guidance, not an activation surface. Treating
    # it as positive text made prompts such as "fixture 名字太误导" wake the Atlas
    # trigger only because the trigger warned not to use it for fixture edits.
    blob = " ".join(trigger_values).casefold()
    score = 0
    for term in prompt_terms:
        normalized = str(term or "").strip().casefold()
        if len(normalized) < 2:
            continue
        if normalized in blob:
            score += trigger_term_weight(normalized)
            continue
        for value in trigger_values:
            value_low = value.casefold()
            if trigger_term_weight(value_low) >= 3 and value_low in normalized:
                score += trigger_term_weight(value_low)
                break
    return score


def trigger_term_weight(term: str) -> int:
    # Single short Latin entities such as "Atlas" are common project/product
    # words and should not make a reviewed trigger prompt-relevant on their own.
    # Longer Latin phrases and compact CJK recall terms are much stronger
    # signals, so they can activate the trigger path without a live model call.
    if re.fullmatch(r"[a-z0-9_.-]+", term) and len(term) < 6:
        return 1
    if re.search(r"[\u4e00-\u9fff]", term) and len(term) >= 4:
        return 3
    if any(ch.isalpha() and ord(ch) > 0x7F for ch in term) and len(term) >= 4:
        return 3
    return 3 if len(term) >= 6 else 1


def load_semantic_triggers(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for row in load_jsonl(path):
        if row.get("status") in {"inactive", "parked"}:
            continue
        if row.get("kind") not in {None, "aippocampus_semantic_trigger"}:
            continue
        activation_cues = collect_exact_aliases(row.get("activation_cues") or [], limit=24)
        source_refs = [ref for ref in row.get("source_refs") or [] if isinstance(ref, dict)]
        fallback_inputs = [row.get("aliases") or [], row.get("trigger_terms") or [], row.get("concept")]
        aliases = activation_cues or collect_aliases(fallback_inputs, limit=40)
        out.append(
            {
                "source": "semantic_triggers",
                "title": compact_text(str(row.get("title") or row.get("concept") or ""), 90),
                # Reviewed trigger rows replace brittle domain word lists. Keep
                # enough aliases for long multilingual/domain clusters; a short
                # cap silently drops late aliases such as self-continuity and
                # makes reviewed triggers look worse than the old hard-coding.
                "aliases": aliases,
                "activation_cues": activation_cues,
                "when_to_use": compact_text(
                    str(row.get("when_to_use") or row.get("summary") or ""), 220
                ),
                "when_not_to_use": compact_text(str(row.get("when_not_to_use") or ""), 180),
                "confidence": row.get("confidence"),
                "source_refs": source_refs[:8],
            }
        )
    return out


def all_trigger_rows(
    *,
    associations: dict[str, Any] | None = None,
    working_memory: list[dict[str, Any]] | None = None,
    semantic_triggers_path: Path | None = None,
    semantic_cues_path: Path | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(semantic_cue_triggers(semantic_cues_path))
    rows.extend(load_semantic_triggers(semantic_triggers_path))
    for row in working_memory or []:
        if row.get("status") == "active":
            rows.append(trigger_from_working_memory(row))
    assoc_terms = associations.get("terms") if isinstance(associations, dict) else {}
    if isinstance(assoc_terms, dict):
        scored = sorted(
            assoc_terms.items(),
            key=lambda item: (float((item[1] or {}).get("confidence") or 0.0), str(item[0])),
            reverse=True,
        )
        for term, row in scored:
            if not isinstance(row, dict):
                continue
            if row.get("status") == "verified" or float(row.get("confidence") or 0.0) >= 0.82:
                rows.append(trigger_from_association(str(term), row))
    return rows


def trigger_catalog(
    *,
    associations: dict[str, Any] | None = None,
    working_memory: list[dict[str, Any]] | None = None,
    semantic_triggers_path: Path | None = None,
    semantic_cues_path: Path | None = None,
    limit: int = DEFAULT_MAX_TRIGGER_ITEMS,
) -> list[dict[str, Any]]:
    rows = all_trigger_rows(
        associations=associations,
        working_memory=working_memory,
        semantic_triggers_path=semantic_triggers_path,
        semantic_cues_path=semantic_cues_path,
    )
    return rows if limit <= 0 else rows[:limit]


def prompt_relevant_triggers(
    *,
    prompt: str,
    associations: dict[str, Any] | None = None,
    working_memory: list[dict[str, Any]] | None = None,
    semantic_triggers_path: Path | None = None,
    semantic_cues_path: Path | None = None,
    limit: int = DEFAULT_MAX_PROMPT_RELEVANT_TRIGGER_ITEMS,
) -> list[dict[str, Any]]:
    prompt_terms = split_query_terms([prompt])[:40] if prompt else []
    scored: list[tuple[tuple[int, float, str], dict[str, Any]]] = []
    for row in all_trigger_rows(
        associations=associations,
        working_memory=working_memory,
        semantic_triggers_path=semantic_triggers_path,
        semantic_cues_path=semantic_cues_path,
    ):
        overlap = trigger_overlap_score(row, prompt_terms)
        if overlap < 3:
            continue
        scored.append(
            (
                (overlap, float(row.get("confidence") or 0.0), str(row.get("title") or "")),
                row,
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:limit]]


def catalog_payload(
    *,
    prompt: str,
    cwd: Path,
    registry: dict[str, Any],
    associations: dict[str, Any] | None = None,
    working_memory: list[dict[str, Any]] | None = None,
    semantic_triggers_path: Path | None = None,
    semantic_cues_path: Path | None = None,
) -> dict[str, Any]:
    # DeepSeek KV cache matches complete prompt-prefix units. Keep stable,
    # potentially large catalogs before the per-prompt text so unrelated prompts
    # can still share the same cached catalog prefix.
    return {
        "prompt_version": PROMPT_VERSION,
        "current_project_hint": current_project_hint(registry, cwd),
        "memory_catalog": registry_catalog(registry, cwd=cwd),
        "trigger_catalog": trigger_catalog(
            associations=associations,
            working_memory=working_memory,
            semantic_triggers_path=semantic_triggers_path,
            semantic_cues_path=semantic_cues_path,
        ),
        "prompt": compact_text(prompt, 1200),
        "prompt_relevant_catalog": prompt_relevant_catalog(
            registry,
            cwd=cwd,
            prompt=prompt,
        ),
        "prompt_relevant_triggers": prompt_relevant_triggers(
            prompt=prompt,
            associations=associations,
            working_memory=working_memory,
            semantic_triggers_path=semantic_triggers_path,
            semantic_cues_path=semantic_cues_path,
        ),
    }


def worker_prompt(worker: str, payload: dict[str, Any]) -> str:
    schema = {
        "worker": worker,
        "decision": "skip|background_only|scent|evidence",
        "intent": "ordinary_task|recall|continuation|decision_check|preference_update|implementation",
        "confidence": 0.0,
        "query_aliases": ["short multilingual search aliases"],
        "memory_scope": ["current_project|registered_threads|cross_project|working_memory"],
        "negative_contexts": ["when not to recall"],
        "anti_personalization_risk": "low|medium|high",
        "reason": "short reason",
    }
    task = {
        "gate": "Decide whether ambient memory should surface. Be strict about skip vs scent.",
        "alias": "Generate multilingual/paraphrase query aliases for local retrieval. Do not decide facts.",
        "scope": "Choose memory scope and detect over-personalization risk.",
    }.get(worker, "Analyze semantic recall relevance.")
    # Put the shared payload first. The worker-specific task/schema are smaller
    # and intentionally trail the common prefix so parallel workers can reuse
    # DeepSeek's server-side prefix cache whenever it has landed.
    return json.dumps(
        {
            "input": payload,
            "output_schema": schema,
            "task": task,
        },
        ensure_ascii=False,
        indent=2,
    )


def parse_worker_response(response: dict[str, Any], worker: str) -> dict[str, Any]:
    parsed = parse_model_json(response)
    decision = str(parsed.get("decision") or "skip").strip().casefold()
    if decision not in VALID_DECISIONS:
        decision = "skip"
    aliases = collect_aliases(
        [
            parsed.get("query_aliases") or [],
            parsed.get("aliases") or [],
            parsed.get("concept_aliases") or [],
        ]
    )
    scopes = unique_preserve(
        [str(x) for x in parsed.get("memory_scope") or [] if str(x).strip()], limit=8
    )
    negatives = unique_preserve(
        [str(x) for x in parsed.get("negative_contexts") or [] if str(x).strip()], limit=8
    )
    risk = str(parsed.get("anti_personalization_risk") or "medium").strip().casefold()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    return {
        "worker": worker,
        "decision": decision,
        "intent": str(parsed.get("intent") or "").strip()[:80],
        "confidence": clamp_confidence(parsed.get("confidence")),
        "query_aliases": aliases,
        "memory_scope": scopes,
        "negative_contexts": negatives,
        "anti_personalization_risk": risk,
        "reason": compact_text(str(parsed.get("reason") or ""), 220),
    }


def run_worker(
    worker: str,
    *,
    payload: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    timeout: float,
    temperature: float,
    chat_fn: ChatFn,
    service_name: str = "DeepSeek API",
    response_format_json: bool = True,
) -> dict[str, Any]:
    args = (
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": worker_prompt(worker, payload)},
        ],
        api_key,
        model,
        base_url,
        None,
        timeout,
        temperature,
    )
    if chat_fn is call_chat_json:
        response = chat_fn(
            *args,
            service_name=service_name,
            response_format_json=response_format_json,
        )
    else:
        response = chat_fn(*args)
    parsed = parse_worker_response(response, worker)
    parsed["usage"] = response.get("usage") or {}
    return parsed


def merge_workers(workers: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    decision = "skip"
    winning_worker = ""
    winning_worker_decision = "skip"
    confidence_values: list[float] = []
    aliases: list[str] = []
    scopes: list[str] = []
    negatives: list[str] = []
    reasons: list[str] = []
    risk = "medium"
    risk_worker = ""
    risk_worker_decision = ""
    intents: list[str] = []
    for row in workers:
        row_decision = str(row.get("decision") or "skip")
        if not winning_worker or DECISION_RANK.get(row_decision, 0) > DECISION_RANK.get(decision, 0):
            decision = row_decision
            winning_worker = str(row.get("worker") or "")
            winning_worker_decision = row_decision
        confidence_values.append(float(row.get("confidence") or 0.0))
        aliases.extend(row.get("query_aliases") or [])
        scopes.extend(row.get("memory_scope") or [])
        negatives.extend(row.get("negative_contexts") or [])
        if row.get("reason"):
            reasons.append(str(row.get("reason")))
        if row.get("intent"):
            intents.append(str(row.get("intent")))
        if row.get("anti_personalization_risk") == "high":
            risk = "high"
            if not risk_worker:
                risk_worker = str(row.get("worker") or "")
                risk_worker_decision = row_decision
        elif risk != "high" and row.get("anti_personalization_risk") == "low":
            risk = "low"
    confidence = max(confidence_values or [0.0])
    decision_before_risk_cap = decision
    decision_cap_reason = ""
    if risk == "high" and DECISION_RANK.get(decision, 0) > DECISION_RANK[HIGH_RISK_MAX_DECISION]:
        decision = HIGH_RISK_MAX_DECISION
        decision_cap_reason = "high_anti_personalization_risk"
        reasons.append(
            "capped semantic evidence by high anti-personalization risk from "
            f"{risk_worker or 'worker'}"
        )
    if risk == "high" and decision == "scent" and confidence < 0.82:
        decision = "background_only"
        reasons.append("downgraded by high anti-personalization risk")
    if decision == "evidence" and confidence < 0.6:
        decision = "scent"
        reasons.append("downgraded low-confidence evidence request")
    if decision == "scent" and confidence < 0.35:
        decision = "background_only"
        reasons.append("downgraded low-confidence scent")
    return {
        "decision": decision,
        "confidence": round(confidence, 4),
        "intent": unique_preserve(intents, limit=4)[0] if intents else "",
        "query_aliases": collect_aliases(aliases, limit=24),
        "memory_scope": unique_preserve(scopes, limit=8),
        "negative_contexts": unique_preserve(negatives, limit=8),
        "anti_personalization_risk": risk,
        "winning_worker": winning_worker,
        "winning_worker_decision": winning_worker_decision,
        "risk_worker": risk_worker,
        "risk_worker_decision": risk_worker_decision,
        "decision_capped": bool(decision_cap_reason),
        "decision_before_risk_cap": decision_before_risk_cap if decision_cap_reason else None,
        "decision_cap_reason": decision_cap_reason,
        "reasons": unique_preserve(reasons + errors, limit=8),
    }


def cache_fingerprint(
    *,
    prompt: str,
    cwd: Path,
    registry_path: Path | None = None,
    semantic_triggers_path: Path | None = None,
    semantic_cues_path: Path | None = None,
    mode: str = "auto",
    model: str = "",
    base_url: str = "",
    workers: tuple[str, ...] = DEFAULT_WORKERS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    parts = [
        PROMPT_VERSION,
        semantic_gate_mode(mode),
        model,
        base_url,
        ",".join(workers),
        str(float(temperature)),
        re.sub(r"\s+", " ", prompt).strip(),
        str(cwd.resolve()).casefold(),
    ]
    for path in [registry_path, semantic_triggers_path, semantic_cues_path]:
        if not path:
            continue
        try:
            resolved = path.resolve()
            if path.exists():
                stat = path.stat()
                parts.append(f"{resolved}:{stat.st_mtime_ns}:{stat.st_size}")
            else:
                parts.append(f"{resolved}:missing")
        except OSError:
            parts.append(str(path))
    return "sg_" + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


def read_cache(
    path: Path, key: str, *, ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
) -> dict[str, Any] | None:
    data = load_json(path)
    entry = (data.get("entries") or {}).get(key) if isinstance(data.get("entries"), dict) else None
    if not isinstance(entry, dict):
        return None
    created = float(entry.get("created_unix") or 0.0)
    if ttl_seconds > 0 and created and time.time() - created > ttl_seconds:
        return None
    result = entry.get("result")
    if isinstance(result, dict):
        result = dict(result)
        result["cached"] = True
        return result
    return None


def write_cache(
    path: Path, key: str, result: dict[str, Any], *, max_entries: int = DEFAULT_MAX_CACHE_ENTRIES
) -> None:
    data = load_json(path)
    raw_entries = data.get("entries")
    entries: dict[str, Any] = dict(raw_entries) if isinstance(raw_entries, dict) else {}
    slim = dict(result)
    slim.pop("elapsed_ms", None)
    slim.pop("cached", None)
    entries[key] = {"created_at": now_utc(), "created_unix": time.time(), "result": slim}
    if len(entries) > max_entries:
        kept = sorted(
            entries.items(),
            key=lambda item: float((item[1] or {}).get("created_unix") or 0.0),
            reverse=True,
        )[:max_entries]
        entries = dict(kept)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "updated_at": now_utc(), "entries": entries},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def error_bucket(message: str) -> str:
    text = str(message or "").casefold()
    if "overall deadline" in text:
        return "overall_deadline"
    if "timeout" in text or "timed out" in text:
        return "read_timeout"
    if "json" in text or "parse" in text or "decode" in text:
        return "invalid_json"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return "auth_error"
    if "connect" in text or "connection" in text or "urlerror" in text:
        return "connection_error"
    return "semantic_worker_error"


def error_buckets(errors: list[str]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for error in errors:
        kind = error_bucket(error)
        buckets[kind] = buckets.get(kind, 0) + 1
    return buckets


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def public_model_route(route: Any) -> dict[str, str]:
    if not isinstance(route, Mapping):
        return {}
    provider = str(route.get("provider") or "").strip()
    safe = "".join(char for char in provider[:48] if char.isalnum() or char in {"_", "-", "."})
    return {"provider": safe or "unknown"}


def public_cache(cache: Any) -> dict[str, Any]:
    if not isinstance(cache, Mapping):
        return {}
    result: dict[str, Any] = {"available": bool(cache.get("available"))}
    for key in ("hit_tokens", "miss_tokens"):
        if key in cache:
            result[key] = public_count(cache.get(key))
    return result


def public_error_buckets(buckets: Any) -> dict[str, int]:
    if not isinstance(buckets, Mapping):
        return {}
    allowed = {
        "auth_error",
        "foreground_budget",
        "read_timeout",
        "overall_deadline",
        "semantic_worker_error",
    }
    return {
        str(key): public_count(value)
        for key, value in buckets.items()
        if str(key) in allowed
    }


def public_semantic_gate_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    workers_value = result.get("workers")
    workers = workers_value if isinstance(workers_value, list) else []
    return {
        "available": bool(result.get("available")),
        "decision": str(result.get("decision") or "skip")
        if str(result.get("decision") or "skip") in VALID_DECISIONS
        else "skip",
        "confidence": public_confidence(result.get("confidence")),
        "cached": bool(result.get("cached")),
        "availability_reason": str(result.get("availability_reason") or "")
        if result.get("availability_reason")
        else None,
        "diagnostic": str(result.get("diagnostic") or "") if result.get("diagnostic") else None,
        "error_buckets": public_error_buckets(result.get("error_buckets")),
        "worker_count": public_count(result.get("worker_count") or len(workers)),
        "cache": public_cache(result.get("cache")),
        "model_route": public_model_route(result.get("model_route")),
        "elapsed_ms": public_count(result.get("elapsed_ms")),
        "output_boundary": "semantic_gate_private_worker_details_omitted",
    }


def unavailable_result(
    reason: str,
    *,
    elapsed_ms: float = 0.0,
    model_route: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
    cache_diagnostics: dict[str, Any] | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    worker_count: int | None = None,
) -> dict[str, Any]:
    buckets = error_buckets([reason])
    if buckets.get("read_timeout"):
        availability_reason = "semantic_worker_timeout"
        diagnostic = "semantic_provider_read_timeout"
    elif buckets.get("auth_error"):
        availability_reason = "semantic_unavailable"
        diagnostic = "semantic_disabled_or_auth_unavailable"
    else:
        availability_reason = "semantic_unavailable"
        diagnostic = "semantic_unavailable"
    return {
        "kind": "aippocampus_semantic_recall_gate",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "available": False,
        "decision": "skip",
        "confidence": 0.0,
        "availability_reason": availability_reason,
        "diagnostic": diagnostic,
        "query_aliases": [],
        "memory_scope": [],
        "negative_contexts": [],
        "anti_personalization_risk": "medium",
        "reasons": [reason],
        "workers": [],
        "errors": [reason],
        "error_buckets": buckets,
        "timeout": timeout,
        "temperature": temperature,
        "worker_count": worker_count,
        "cache": cache or {},
        "model_route": model_route or {},
        "cache_diagnostics": cache_diagnostics or {},
        "secret_policy": None,
        "cached": False,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def foreground_budget_unavailable_result(
    reason: str,
    *,
    diagnostic: str,
    deadline_seconds: float | None,
    elapsed_ms: float = 0.0,
    model_route: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
    cache_diagnostics: dict[str, Any] | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    worker_count: int | None = None,
) -> dict[str, Any]:
    result = unavailable_result(
        reason,
        elapsed_ms=elapsed_ms,
        model_route=model_route,
        cache=cache,
        cache_diagnostics=cache_diagnostics,
        timeout=timeout,
        temperature=temperature,
        worker_count=worker_count,
    )
    result.update(
        {
            "availability_reason": "foreground_budget_skipped",
            "diagnostic": diagnostic,
            "error_buckets": {"foreground_budget": 1},
            "deadline": {
                "seconds": deadline_seconds,
                "exceeded": True,
                "unfinished_workers": [],
            },
            "foreground": True,
        }
    )
    return result


def run_semantic_gate(
    prompt: str,
    *,
    cwd: Path | str,
    registry: dict[str, Any] | None = None,
    registry_path: Path | str | None = None,
    associations: dict[str, Any] | None = None,
    working_memory: list[dict[str, Any]] | None = None,
    semantic_triggers_path: Path | str | None = None,
    semantic_cues_path: Path | str | None = None,
    cache_path: Path | str | None = None,
    mode: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    model_route: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    temperature: float = DEFAULT_TEMPERATURE,
    workers: tuple[str, ...] = DEFAULT_WORKERS,
    deadline_seconds: float | None = None,
    foreground: bool = False,
    use_cache: bool = True,
    chat_fn: ChatFn = call_chat_json,
) -> dict[str, Any]:
    start = time.perf_counter()
    prompt = str(prompt or "").strip()
    cwd_path = Path(cwd).resolve()
    sanitized_prompt, secret_policy = sanitize_prompt_for_semantic_gate(
        prompt,
        project_root=cwd_path,
    )
    registry_path_obj = Path(registry_path).resolve() if registry_path else None
    triggers_path = (
        Path(semantic_triggers_path).resolve()
        if semantic_triggers_path
        else (
            default_semantic_triggers_path(registry_path=registry_path_obj)
            if registry_path_obj
            else None
        )
    )
    cues_path = (
        Path(semantic_cues_path).resolve()
        if semantic_cues_path
        else (default_semantic_cues_path(registry_path=registry_path_obj) if registry_path_obj else None)
    )
    route = resolve_model_route(
        model_route,
        explicit_model=model if not model_route else None,
        explicit_base_url=base_url if not model_route else None,
        explicit_api_key_env=api_key_env if not model_route else None,
    )
    resolved_model = model or route.model
    resolved_base_url = base_url or route.base_url
    resolved_api_key_env = api_key_env or route.api_key_env or DEFAULT_DEEPSEEK_API_KEY_ENV
    capabilities = route.capabilities
    route_payload = route_payload_with_effective_values(
        route,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key_env=resolved_api_key_env,
    )
    key_value = api_key or os.environ.get(resolved_api_key_env)
    unavailable_metadata: dict[str, Any] = {
        "model_route": route_payload,
        "cache": route_cache_metrics(route, {}),
        "cache_diagnostics": {
            "lookup": "disabled",
            "cache_key": None,
            "semantic_cues_in_cache_key": False,
        },
        "timeout": timeout,
        "temperature": temperature,
        "worker_count": len(tuple(worker for worker in workers if worker in set(DEFAULT_WORKERS))),
    }
    if not semantic_gate_enabled(mode, api_key=key_value, api_key_env=resolved_api_key_env):
        return unavailable_result(
            "semantic gate disabled or missing api key",
            **unavailable_metadata,
        )
    if not prompt:
        return unavailable_result("empty prompt", **unavailable_metadata)
    if secret_policy.get("hard_block"):
        result = unavailable_result(
            str(secret_policy.get("reason") or "sensitive prompt hard-blocked"),
            **unavailable_metadata,
        )
        result["secret_policy"] = secret_policy
        return result

    deadline = float(deadline_seconds) if deadline_seconds and deadline_seconds > 0 else None
    try:
        worker_timeout_seconds = float(timeout)
    except (TypeError, ValueError):
        worker_timeout_seconds = DEFAULT_TIMEOUT
    if foreground:
        # Foreground hooks are latency fail-open surfaces. They may use semantic
        # workers as a source-backed search hint, but only when both the overall
        # wall-clock deadline and the per-worker socket timeout are explicit.
        # Background/operator callers keep the quality-first default timeout.
        if deadline is None:
            return foreground_budget_unavailable_result(
                "semantic foreground gate requires an explicit overall deadline",
                diagnostic="semantic_foreground_deadline_required",
                deadline_seconds=None,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                **unavailable_metadata,
            )
        if worker_timeout_seconds > deadline:
            return foreground_budget_unavailable_result(
                "semantic foreground worker timeout exceeds overall deadline",
                diagnostic="semantic_foreground_timeout_exceeds_deadline",
                deadline_seconds=deadline,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                **unavailable_metadata,
            )

    cache = (
        Path(cache_path).resolve()
        if cache_path
        else (default_cache_path(registry_path=registry_path_obj) if registry_path_obj else None)
    )
    cache_key = cache_fingerprint(
        prompt=sanitized_prompt,
        cwd=cwd_path,
        registry_path=registry_path_obj,
        semantic_triggers_path=triggers_path,
        semantic_cues_path=cues_path,
        mode=mode or "auto",
        model=resolved_model,
        base_url=resolved_base_url,
        workers=tuple(worker for worker in workers if worker in set(DEFAULT_WORKERS)),
        temperature=temperature,
    )
    cache_lookup = "disabled"
    if use_cache and cache:
        cached = read_cache(cache, cache_key)
        if cached:
            cached.setdefault("model_route", route_payload)
            cached["foreground"] = bool(foreground)
            cached["cache_diagnostics"] = {
                **(cached.get("cache_diagnostics") or {}),
                "lookup": "hit",
                "cache_key": cache_key,
                "semantic_cues_in_cache_key": bool(cues_path),
            }
            cached["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return cached
        cache_lookup = "miss"

    if registry is None:
        registry = load_registry(registry_path_obj) if registry_path_obj else {"threads": []}
    payload = catalog_payload(
        prompt=sanitized_prompt,
        cwd=cwd_path,
        registry=registry,
        associations=associations,
        working_memory=working_memory,
        semantic_triggers_path=triggers_path,
        semantic_cues_path=cues_path,
    )
    payload = sanitize_external_model_payload(payload, project_root=cwd_path)
    parsed_workers: list[dict[str, Any]] = []
    errors: list[str] = []
    worker_names = tuple(worker for worker in workers if worker in set(DEFAULT_WORKERS))
    if route.provider != "deepseek" and capabilities:
        worker_names = worker_names[: max(1, int(capabilities.safe_default_concurrency or 1))]
    worker_kwargs: dict[str, Any] = {
        "payload": payload,
        "api_key": str(key_value),
        "model": resolved_model,
        "base_url": resolved_base_url,
        "timeout": worker_timeout_seconds,
        "temperature": temperature,
        "chat_fn": chat_fn,
        "service_name": route_service_name(route),
        "response_format_json": bool(capabilities.supports_json_response if capabilities else True),
    }
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(worker_names)))
    futures = {executor.submit(run_worker, worker, **worker_kwargs): worker for worker in worker_names}
    done, not_done = concurrent.futures.wait(
        futures, timeout=deadline, return_when=concurrent.futures.ALL_COMPLETED
    )
    deadline_exceeded = bool(not_done)
    unfinished_workers = [worker for future, worker in futures.items() if future in not_done]
    for future in done:
        worker = futures[future]
        try:
            parsed_workers.append(future.result())
        except Exception as exc:
            errors.append(f"{worker}: {exc}")
    for future in not_done:
        future.cancel()
    errors.extend(
        f"{worker}: semantic overall deadline exceeded after {deadline:.3g}s"
        for worker in unfinished_workers
    )
    # Foreground hook deadlines are fail-open boundaries. `cancel_futures`
    # prevents queued work from starting; already-running HTTP calls cannot be
    # killed from a thread, so foreground callers pass a sub-deadline socket
    # timeout to keep those calls bounded too.
    executor.shutdown(wait=not deadline_exceeded, cancel_futures=deadline_exceeded)

    merged = merge_workers(parsed_workers, errors)
    usage_total: dict[str, Any] = {}
    for worker_result in parsed_workers:
        add_usage(usage_total, compact_usage(worker_result.get("usage") or {}))
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    result = {
        "kind": "aippocampus_semantic_recall_gate",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "available": bool(parsed_workers),
        **merged,
        "workers": parsed_workers,
        "errors": errors,
        "error_buckets": error_buckets(errors),
        "warnings": [],
        "usage": usage_total,
        "timeout": timeout,
        "deadline": {"seconds": deadline, "exceeded": deadline_exceeded, "unfinished_workers": unfinished_workers},
        "foreground": bool(foreground),
        "temperature": temperature,
        "worker_count": len(worker_names),
        "cache": route_cache_metrics(route, usage_total),
        "model_route": route_payload,
        "cache_diagnostics": {
            "lookup": cache_lookup,
            "cache_key": cache_key,
            "semantic_cues_in_cache_key": bool(cues_path),
        },
        "secret_policy": secret_policy,
        "cached": False,
        "elapsed_ms": elapsed_ms,
    }
    if not parsed_workers and errors:
        result["available"] = False
        result["decision"] = "skip"
        if result["error_buckets"].get("overall_deadline"):
            result["availability_reason"] = "semantic_worker_timeout"
            result["diagnostic"] = "semantic_overall_deadline_exceeded"
        elif result["error_buckets"].get("read_timeout"):
            result["availability_reason"] = "semantic_worker_timeout"
            result["diagnostic"] = "semantic_provider_read_timeout"
        else:
            result["availability_reason"] = "semantic_worker_error"
            result["diagnostic"] = "semantic_worker_error"
    if use_cache and cache and result.get("available") and not deadline_exceeded:
        try:
            write_cache(cache, cache_key, result)
        except Exception as exc:
            # Cache writes are an optimization and must not break the foreground
            # hook, but operator/debug callers still need to see degraded state.
            result.setdefault("warnings", []).append(
                {
                    "stage": "cache_write",
                    "path": str(cache),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--registry")
    parser.add_argument("--associations")
    parser.add_argument("--working-memory")
    parser.add_argument("--semantic-triggers")
    parser.add_argument("--semantic-cues")
    parser.add_argument("--cache")
    parser.add_argument("--mode", choices=["auto", "on", "off"], default=None)
    parser.add_argument("--model-route")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve() if args.registry else registry_paths()[0]
    result = run_semantic_gate(
        args.prompt,
        cwd=Path(args.cwd),
        registry_path=registry_path,
        associations=load_json(Path(args.associations).resolve()) if args.associations else None,
        working_memory=load_jsonl(Path(args.working_memory).resolve())
        if args.working_memory
        else None,
        semantic_triggers_path=Path(args.semantic_triggers).resolve()
        if args.semantic_triggers
        else None,
        semantic_cues_path=Path(args.semantic_cues).resolve() if args.semantic_cues else None,
        cache_path=Path(args.cache).resolve() if args.cache else None,
        mode=args.mode,
        model_route=args.model_route,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout=args.timeout,
        temperature=args.temperature,
        use_cache=not args.no_cache,
    )
    public_result = public_semantic_gate_payload(result)
    if args.json_output:
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        print(
            "semantic gate: "
            f"{public_result.get('decision')} confidence={public_result.get('confidence')} "
            f"cached={public_result.get('cached')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
