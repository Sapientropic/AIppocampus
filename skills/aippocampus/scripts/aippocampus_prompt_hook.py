#!/usr/bin/env python3
"""Codex UserPromptSubmit hook for ambient long-thread recall.

This hook is intentionally not a second general memory system. It behaves like
an associative gate over aippocampus artifacts:

- weak cues produce a small "scent" so the next model turn knows a memory may
  exist, without treating it as evidence
- explicit or high-salience cues run a tiny conclusion-first evidence search
- ordinary coding work stays silent, because a global UserPromptSubmit hook
  fires for every prompt and can become irritating if it over-personalizes
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

from build_associations import default_associations_path, load_associations, match_associations, source_text_is_noise
from build_concept_graph import default_concept_graph_path, expand_concepts
from memory_candidate_router import default_working_memory_path, load_working_memory, match_working_memory, strip_for_hook
from registry import deep_search_entry, entry_search_score, load_registry, registry_paths, unique_preserve
from retrieval import CONCEPT_TRIGGERS, RECALL_TRIGGERS, split_query_terms
from semantic_recall_gate import DEFAULT_TIMEOUT as DEFAULT_SEMANTIC_TIMEOUT, default_semantic_triggers_path, run_semantic_gate
from aippocampuslib import codex_home, compact_text, now_utc


SCENT_THRESHOLD = 5.0
EVIDENCE_THRESHOLD = 10.0
DEFAULT_SEARCH_BUDGET = 3
MAX_CONTEXT_CHARS = 1800
SCENT_PROBE_LIMIT = 32
SCENT_PROBE_SCORE_MULTIPLIER = 2.4
SCENT_PROBE_SCORE_CAP = 32.0
EVIDENCE_LITE_MIN_PROBE_SCORE = 6.0
CONCEPT_EXPANSION_MAX_TERMS = 14
SEMANTIC_GATE_CUE_DECISIONS = {"scent", "evidence"}
SEMANTIC_GATE_ALIAS_DECISIONS = {"background_only", "scent", "evidence"}
SEMANTIC_EVIDENCE_TERMS = {
    "最后",
    "latest",
    "last reply",
    "exact",
    "quote",
    "source",
    "evidence",
    "citation",
    "原文",
    "原话",
    "证据",
    "引用",
    "行号",
    "你之前说过",
    "我之前说过",
}


EXPLICIT_RECALL_TERMS = {
    "找回",
    "想起来",
    "想起",
    "原文",
    "原话",
    "那句",
    "这句",
    "最后回复",
    "最后的消息",
    "之前说过",
    "你说过",
    "我说过",
}

WEAK_DEICTIC_TERMS = {
    "之前",
    "前面",
    "刚才",
    "上次",
    "继续",
    "那个",
    "这个",
    "那篇",
    "这篇",
    "anchor",
    "vault",
    "graphify",
    "rag",
    "小海马体",
    "外置海马体",
    "记忆",
    "召回",
    "压缩",
    "compaction",
}

ASSOCIATIVE_CUES = {
    "联想",
    "触发",
    "钩子",
    "hook机制",
    "hook",
    "hooks",
    "海马体",
    "小海马体",
    "外置海马体",
    "被动触发",
    "触发式联想",
    "联想机制",
    "被动召回",
    "主动召回",
    "ambient recall",
    "active recall",
    "scent",
    "evidence",
    "记忆",
    "召回",
    "世界线",
    "自我连续性",
    "生命还能变成什么",
    "我还是我",
}

IMPORTANCE_CUES = {
    "我很喜欢",
    "很喜欢",
    "惊艳",
    "重要",
    "别忘",
    "记住",
    "记下来",
    "值得保留",
    "以后还会用",
}

CODE_SURFACE_CUES = {
    "按钮",
    "样式",
    "hover",
    "css",
    "组件",
    "dashboard",
    "测试",
    "test",
    "修 bug",
    "bug",
    "报错",
    "编译",
    "接口",
    "api",
    "实现",
    "改一下",
}


DECISION_CONTINUATION_CUES = {
    "该不该",
    "要不要",
    "是否",
    "是不是应该",
    "能不能",
    "哪个更适合",
    "怎么选",
    "还成立吗",
    "还成立",
    "现在怎么看",
    "怎么做比较好",
}

RECENCY_CUES = {
    "最近",
    "最后",
    "上次",
    "当前线程之外",
    "外面",
    "latest",
    "recent",
}

SEMANTIC_GATE_LIGHT_CUES = {
    "这个",
    "那个",
    "这些",
    "那些",
    "刚才",
    "之前",
    "上次",
    "继续",
    "进度",
    "状态",
    "怎么样",
    "做到哪",
    "还成立",
    "怎么处理",
}


TERM_WRAPPERS_RE = re.compile(
    r"(还记得|记得|之前|前面|刚才|上次|找回|想起来|想起|那句|这句|那个|这个|那篇|这篇|原话|原文|吗|嘛|呢|吧|还能|能不能)"
)

GENERIC_EVIDENCE_TERMS = {
    "之前",
    "前面",
    "刚才",
    "上次",
    "找回",
    "那句",
    "这句",
    "还能找回",
    "能不能还是",
    "还是",
    "而我",
    "还是我",
    "这个",
    "那个",
    "记得",
    "还记得",
}


CJK_CONTENT_MARKERS = {
    "重写",
    "搜索",
    "客户端",
    "市场",
    "迁移",
    "归档",
    "注册",
    "线程",
    "记忆库",
    "底座",
    "本地底座",
    "本地核心",
}


GENERIC_ASSOCIATION_TERMS = {
    "当前线程",
    "前线程",
    "线程",
    "当前",
    "主题是什么",
    "关于",
}


def hook_input_from_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def registry_json_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path
    json_path, _ = registry_paths(registry_dir)
    return json_path


def matched_terms(prompt: str, terms: set[str]) -> list[str]:
    low = prompt.casefold()
    return [term for term in sorted(terms, key=len, reverse=True) if term.casefold() in low]


def prompt_is_code_surface(prompt: str) -> bool:
    return bool(matched_terms(prompt, CODE_SURFACE_CUES))


def explicit_recall_terms(prompt: str) -> list[str]:
    # Retrieval-level triggers include useful weak deixis such as "这个/那个".
    # Those should help search phrasing, but they must not escalate a prompt to
    # evidence retrieval by themselves; otherwise ordinary continuation text can
    # summon exact snippets too eagerly.
    strong = (set(RECALL_TRIGGERS) | EXPLICIT_RECALL_TERMS) - WEAK_DEICTIC_TERMS
    return matched_terms(prompt, strong)


def expand_query_terms(prompt: str) -> list[str]:
    terms = split_query_terms([prompt]) if prompt else []
    expanded = list(terms)
    for phrase in re.findall(r"[A-Za-z][A-Za-z0-9_.+-]*(?:\s+[A-Za-z][A-Za-z0-9_.+-]*){1,3}", prompt):
        expanded.append(phrase.strip())
    for marker in CJK_CONTENT_MARKERS:
        if marker in prompt:
            expanded.append(marker)
    for term in terms:
        cleaned = TERM_WRAPPERS_RE.sub(" ", term)
        cleaned = re.sub(r"[，。；：！？,.!?/|+]+", " ", cleaned)
        for part in cleaned.split():
            part = part.strip()
            if 2 <= len(part) <= 40:
                expanded.append(part)
    return unique_preserve(expanded, limit=24)


def evidence_content_terms(query_terms: list[str]) -> list[str]:
    terms: list[str] = []
    for term in query_terms:
        low = term.casefold().strip()
        if low in GENERIC_EVIDENCE_TERMS or len(low) < 3:
            continue
        cleaned = TERM_WRAPPERS_RE.sub(" ", term)
        cleaned = re.sub(r"[，。；：！？,.!?/|+]+", " ", cleaned)
        for part in cleaned.split():
            part = part.strip()
            if len(part) >= 3 and part.casefold() not in GENERIC_EVIDENCE_TERMS:
                terms.append(part)
        if len(term) <= 40:
            terms.append(term)
    return unique_preserve(terms, limit=10)


def association_term_is_generic(match: dict[str, Any]) -> bool:
    term = str(match.get("term") or "").casefold().strip()
    if term in {value.casefold() for value in GENERIC_ASSOCIATION_TERMS}:
        return True
    return False


def candidate_summary(entry: dict[str, Any], score: float, query_terms: list[str]) -> dict[str, Any]:
    blob = "\n".join(
        [
            entry.get("title") or "",
            entry.get("workspace_name") or "",
            entry.get("summary") or "",
            " ".join(entry.get("anchor_titles") or []),
            " ".join(entry.get("keywords") or []),
        ]
    ).casefold()
    matched = [term for term in query_terms if term.casefold() in blob]
    return {
        "thread_key": entry.get("thread_key"),
        "title": entry.get("title") or entry.get("workspace_name") or entry.get("thread_key"),
        "timestamp": (entry.get("session_meta") or {}).get("timestamp") or entry.get("created_at") or entry.get("updated_at"),
        "project_label": entry.get("project_label") or entry.get("workspace_name"),
        "score": round(score, 3),
        "matched_terms": unique_preserve(matched, limit=8),
        "anchors": unique_preserve(entry.get("anchor_titles") or [], limit=3),
        "keywords": unique_preserve(entry.get("keywords") or [], limit=8),
        "_entry": entry,
    }


def sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            str(item.get("timestamp") or ""),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return candidates


def fuzzy_entry_score(entry: dict[str, Any], query_terms: list[str]) -> float:
    clues = unique_preserve(
        list(entry.get("keywords") or [])
        + list(entry.get("anchor_titles") or [])
        + [entry.get("title") or "", entry.get("summary") or ""],
        limit=80,
    )
    score = 0.0
    for term in query_terms:
        low = term.casefold().strip()
        if len(low) < 4:
            continue
        for clue in clues:
            clue_low = str(clue).casefold().strip()
            if len(clue_low) < 4:
                continue
            if low in clue_low or clue_low in low:
                score += 3.0
                break
    return min(score, 9.0)


def score_candidates(prompt: str, registry: dict[str, Any], query_terms: list[str]) -> list[dict[str, Any]]:
    explicit = explicit_recall_terms(prompt)
    associative = matched_terms(prompt, set(CONCEPT_TRIGGERS) | ASSOCIATIVE_CUES)
    important = matched_terms(prompt, IMPORTANCE_CUES)

    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        base = entry_search_score(entry, query_terms) + fuzzy_entry_score(entry, query_terms)
        if base <= 0:
            continue
        score = base
        if explicit:
            score += 4.0
        if associative:
            score += min(4.0, len(associative) * 1.5)
        if important:
            score += 2.5
        candidates.append(candidate_summary(entry, score, query_terms))
    return sort_candidates(candidates)


def association_document_frequency(match: dict[str, Any], total_threads: int) -> int:
    thread_count = len({source.get("thread_key") for source in match.get("threads") or [] if source.get("thread_key")})
    hit_count = int(match.get("hit_count") or 0)
    if total_threads <= 0:
        return max(1, thread_count or hit_count or 1)
    return max(1, min(total_threads, max(thread_count, hit_count, 1)))


def association_boost(match: dict[str, Any], total_threads: int) -> float:
    confidence = float(match.get("confidence") or 0.0)
    df = association_document_frequency(match, total_threads)
    n = max(total_threads, df, 1)
    idf = math.log((n + 1.0) / (df + 1.0)) + 1.0
    status_bonus = 1.25 if match.get("status") == "verified" else 1.0
    # A matched association is enough to produce a scent, but broad terms such
    # as a project name should not drown out rare source terms. IDF keeps the
    # gate open while moving ranking authority toward more specific memories.
    return round(SCENT_THRESHOLD + min(8.0, confidence * idf * status_bonus * 2.5), 3)


def merge_association_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    association_matches: list[dict[str, Any]],
    query_terms: list[str],
) -> list[dict[str, Any]]:
    if not association_matches:
        return candidates
    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    total_threads = len(by_thread)
    for match in association_matches:
        boost = association_boost(match, total_threads)
        seen_for_match: set[str] = set()
        for source in match.get("threads") or []:
            thread_key = source.get("thread_key")
            if not thread_key or thread_key in seen_for_match:
                continue
            seen_for_match.add(thread_key)
            entry = by_thread.get(thread_key)
            if not entry:
                continue
            existing = by_key.get(thread_key)
            if existing:
                existing["score"] = round(float(existing.get("score") or 0.0) + boost, 3)
                existing["matched_terms"] = unique_preserve(
                    list(existing.get("matched_terms") or []) + list(match.get("matched_terms") or []) + [match.get("term") or ""],
                    limit=8,
                )
                continue
            item = candidate_summary(entry, boost, query_terms)
            item["matched_terms"] = unique_preserve(
                list(item.get("matched_terms") or []) + list(match.get("matched_terms") or []) + [match.get("term") or ""],
                limit=8,
            )
            item["association_source"] = True
            candidates.append(item)
            by_key[thread_key] = item
    return sort_candidates(candidates)


def default_project_timeline_path(registry_path: Path) -> Path:
    return registry_path.resolve().parent / "project_timeline.json"


def load_project_timeline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def project_matches_prompt(project: dict[str, Any], prompt: str, cwd: Path) -> bool:
    low = prompt.casefold()
    labels = unique_preserve(
        [
            project.get("project_label") or "",
            project.get("project_key") or "",
            *list(project.get("project_tags") or []),
        ],
        limit=24,
    )
    if any(label and label.casefold() in low for label in labels):
        return True
    cwd_low = str(cwd).casefold()
    return any(label and label.casefold() in cwd_low for label in labels)


def merge_timeline_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    timeline: dict[str, Any],
    prompt: str,
    cwd: Path,
    query_terms: list[str],
) -> list[dict[str, Any]]:
    if not timeline or not matched_terms(prompt, RECENCY_CUES):
        return candidates
    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    for project in (timeline.get("projects") or {}).values():
        if not isinstance(project, dict) or not project_matches_prompt(project, prompt, cwd):
            continue
        latest_turns = project.get("latest_turns") or []
        if not latest_turns:
            continue
        latest = latest_turns[0]
        thread_key = latest.get("thread_key")
        entry = by_thread.get(thread_key)
        if not entry:
            continue
        boost = EVIDENCE_THRESHOLD + 2.0
        existing = by_key.get(thread_key)
        if existing:
            existing["score"] = round(float(existing.get("score") or 0.0) + boost, 3)
            existing["matched_terms"] = unique_preserve(
                list(existing.get("matched_terms") or []) + matched_terms(prompt, RECENCY_CUES) + [project.get("project_label") or ""],
                limit=8,
            )
            existing["timeline_source"] = True
            continue
        item = candidate_summary(entry, boost, query_terms)
        item["matched_terms"] = unique_preserve(
            list(item.get("matched_terms") or []) + matched_terms(prompt, RECENCY_CUES) + [project.get("project_label") or ""],
            limit=8,
        )
        item["timeline_source"] = True
        candidates.append(item)
        by_key[thread_key] = item
    return sort_candidates(candidates)


def rerank_candidates_with_probe(
    candidates: list[dict[str, Any]],
    query_terms: list[str],
    *,
    limit: int = SCENT_PROBE_LIMIT,
) -> list[dict[str, Any]]:
    if not candidates or not query_terms:
        return candidates
    for candidate in candidates[: max(0, limit)]:
        entry = candidate.get("_entry") or {}
        probe_score, hits = deep_search_entry(entry, query_terms, max_hits=1)
        if probe_score <= 0:
            continue
        candidate["probe_score"] = round(probe_score, 3)
        if hits:
            hit = hits[0]
            candidate["probe_line"] = hit.get("line")
            candidate["probe_phase"] = hit.get("phase") or ""
        candidate["score"] = round(
            float(candidate.get("score") or 0.0) + min(SCENT_PROBE_SCORE_CAP, probe_score * SCENT_PROBE_SCORE_MULTIPLIER),
            3,
        )
    return sort_candidates(candidates)


def fallback_search_candidates(registry: dict[str, Any], query_terms: list[str], limit: int = 5) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        paths = entry.get("paths") or {}
        sqlite_path = Path(paths.get("sqlite") or "")
        if not sqlite_path.exists():
            continue
        item = candidate_summary(entry, SCENT_THRESHOLD, query_terms)
        item["fallback"] = True
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def should_suppress(
    prompt: str,
    explicit: list[str],
    associative: list[str],
    candidates: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]] | None = None,
    *,
    semantic_memory_cue: bool = False,
) -> bool:
    if explicit:
        return False
    if associative and candidates:
        return False
    if semantic_memory_cue and candidates:
        # Semantic recall is allowed to replace brittle cue lists, but only
        # after the semantic gate has already run its anti-personalization
        # check. The local source search still has to find a candidate before
        # anything is surfaced.
        return False
    if working_memory_matches:
        # Working-memory routes already passed project scope and concrete-term
        # checks, so let them surface for relevant implementation work. This is
        # the ADHD-friendly path: use source-backed soft memory without turning
        # every coding prompt into a broad personal-memory prompt.
        return False
    if prompt_is_code_surface(prompt):
        # Global prompt hooks are expensive socially, not computationally: a
        # normal "fix the button" task should not suddenly summon old personal
        # or philosophical memories unless the user also gave a memory cue.
        return True
    return False


def collect_evidence(candidates: list[dict[str, Any]], query_terms: list[str], budget: int) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    remaining = max(0, budget)
    content_terms = evidence_content_terms(query_terms)
    for candidate in candidates[:3]:
        if remaining <= 0:
            break
        entry = candidate.get("_entry") or {}
        _, hits = deep_search_entry(entry, query_terms, max_hits=min(remaining, 2))
        for hit in hits:
            if not hit.get("line") or not hit.get("snippet"):
                continue
            snippet_low = str(hit.get("snippet") or "").casefold()
            hit_score = float(hit.get("score") or 0.0)
            clean_source_high_confidence = hit.get("source") == "clean_source" and hit_score >= 50
            if content_terms and not clean_source_high_confidence and not any(term.casefold() in snippet_low for term in content_terms):
                continue
            item = {
                "thread_key": candidate.get("thread_key"),
                "title": candidate.get("title"),
                "line": hit.get("line"),
                "role": hit.get("role"),
                "phase": hit.get("phase") or "",
                "turn_index": hit.get("turn_index"),
                "score": hit.get("score"),
                "source": hit.get("source"),
                "snippet": hit.get("snippet"),
            }
            evidence.append(item)
            remaining -= 1
            if remaining <= 0:
                break
    return evidence


def strip_private_fields(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in candidates:
        copy = dict(item)
        copy.pop("_entry", None)
        copy.pop("probe_line", None)
        copy.pop("probe_phase", None)
        out.append(copy)
    return out


def is_decision_continuation(prompt: str) -> bool:
    return bool(matched_terms(prompt, DECISION_CONTINUATION_CUES))


def concept_expansion_terms(expansions: list[dict[str, Any]]) -> list[str]:
    return unique_preserve([str(item.get("term") or "") for item in expansions], limit=CONCEPT_EXPANSION_MAX_TERMS)


def current_project_label(registry: dict[str, Any], cwd: Path) -> str | None:
    target = str(cwd.resolve()).casefold()
    sep = os.sep.casefold()
    best: tuple[int, str] | None = None
    for entry in registry.get("threads") or []:
        paths = entry.get("paths") or {}
        workspace = str(paths.get("workspace") or (entry.get("session_meta") or {}).get("cwd") or "")
        if not workspace:
            continue
        try:
            workspace_low = str(Path(workspace).resolve()).casefold()
        except Exception:
            workspace_low = workspace.casefold()
        if workspace_low == target:
            score = 3
        elif target.startswith(workspace_low + sep) or workspace_low.startswith(target + sep):
            score = 2
        else:
            continue
        label = str(entry.get("project_label") or entry.get("workspace_name") or "")
        if label and (best is None or score > best[0]):
            best = (score, label)
    return best[1] if best else None


def working_memory_terms(matches: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for match in matches:
        terms.extend(str(value) for value in match.get("matched_terms") or [])
        terms.extend(str(value) for value in match.get("trigger_terms") or [])
        terms.extend(split_query_terms([str(match.get("title") or ""), str(match.get("summary") or "")]))
    return unique_preserve([term for term in terms if term.strip()], limit=24)


def semantic_gate_terms(result: dict[str, Any] | None) -> list[str]:
    if not result or not result.get("available"):
        return []
    if str(result.get("decision") or "") not in SEMANTIC_GATE_ALIAS_DECISIONS:
        return []
    aliases = [str(value) for value in result.get("query_aliases") or []]
    scopes = [str(value) for value in result.get("memory_scope") or []]
    return unique_preserve(aliases + scopes, limit=24)


def semantic_gate_is_memory_cue(result: dict[str, Any] | None) -> bool:
    return bool(
        result
        and result.get("available")
        and str(result.get("decision") or "") in SEMANTIC_GATE_CUE_DECISIONS
        and float(result.get("confidence") or 0.0) >= 0.35
    )


def semantic_gate_can_request_evidence(prompt: str, result: dict[str, Any] | None) -> bool:
    if not result or not result.get("available") or result.get("decision") != "evidence":
        return False
    if float(result.get("confidence") or 0.0) < 0.5:
        return False
    # DeepSeek may understand vague status prompts semantically, but the hook
    # should not turn that into source snippets unless the user is asking for
    # exact/source-backed recall. Otherwise a fuzzy "how is that memory thing
    # going?" can surface old high-scoring fragments instead of staying as a
    # gentle scent for the foreground model to decide on.
    return bool(explicit_recall_terms(prompt) or matched_terms(prompt, SEMANTIC_EVIDENCE_TERMS))


def has_non_cjk_non_latin_letters(prompt: str) -> bool:
    for ch in prompt:
        code = ord(ch)
        if "A" <= ch <= "Z" or "a" <= ch <= "z":
            continue
        if ch.isalpha() and "LATIN" in unicodedata.name(ch, ""):
            continue
        if "\u4e00" <= ch <= "\u9fff":
            continue
        if ch.isalpha() and code > 0x7F:
            return True
    return False


def looks_like_multilingual_natural_language(prompt: str) -> bool:
    if not has_non_cjk_non_latin_letters(prompt):
        return False
    # If the user switches to Russian, Arabic, Japanese kana, Korean, etc.,
    # hard-coded Chinese/English cues cannot tell whether this is recall. Let
    # the semantic gate decide, unless the prompt is an obvious code surface
    # task handled by deterministic safeguards.
    stripped = prompt.strip()
    words = re.findall(r"\w+", prompt, flags=re.UNICODE)
    # Space-less scripts such as Japanese and Thai should not be penalized by
    # word-count gates. A moderately long non-CJK/non-Latin sentence is enough
    # for the semantic model to decide whether recall is relevant.
    return (len(words) >= 4 and len(stripped) >= 18) or len(stripped) >= 14


def looks_like_latin_long_question(prompt: str) -> bool:
    stripped = prompt.strip()
    if not re.search(r"[?？¿]", stripped):
        return False
    if has_non_cjk_non_latin_letters(prompt):
        return False
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", stripped)
    # This is another spend gate, not a recall rule. It lets Spanish/French/
    # German/etc. long questions reach the semantic gate, while short daily
    # questions such as "¿Qué tiempo hará mañana?" stay local and quiet.
    return len(words) >= 7 and len(stripped) >= 42


def should_run_semantic_gate(
    prompt: str,
    *,
    explicit: list[str],
    associative: list[str],
    important: list[str],
    association_matches: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
) -> bool:
    if prompt_is_code_surface(prompt) and not (explicit or associative or important or working_memory_matches):
        # This is a spend/latency brake, not the recall brain. Dynamic
        # associations can include ordinary implementation words such as
        # dashboard/hover/test; those should not make every code task call a
        # semantic model. Source-backed working memory still gets through.
        return False
    if explicit or associative or important or association_matches or working_memory_matches:
        return True
    if looks_like_multilingual_natural_language(prompt):
        return True
    if looks_like_latin_long_question(prompt):
        return True
    if matched_terms(prompt, SEMANTIC_GATE_LIGHT_CUES | DECISION_CONTINUATION_CUES | RECENCY_CUES):
        return True
    return False


def strip_semantic_gate(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    workers = []
    for worker in result.get("workers") or []:
        workers.append(
            {
                "worker": worker.get("worker"),
                "decision": worker.get("decision"),
                "confidence": worker.get("confidence"),
                "query_aliases": unique_preserve([str(value) for value in worker.get("query_aliases") or []], limit=8),
                "memory_scope": worker.get("memory_scope") or [],
                "anti_personalization_risk": worker.get("anti_personalization_risk"),
                "reason": worker.get("reason"),
            }
        )
    return {
        "available": bool(result.get("available")),
        "decision": result.get("decision"),
        "confidence": result.get("confidence"),
        "intent": result.get("intent"),
        "query_aliases": unique_preserve([str(value) for value in result.get("query_aliases") or []], limit=12),
        "memory_scope": result.get("memory_scope") or [],
        "negative_contexts": result.get("negative_contexts") or [],
        "anti_personalization_risk": result.get("anti_personalization_risk"),
        "reasons": result.get("reasons") or [],
        "cached": bool(result.get("cached")),
        "elapsed_ms": result.get("elapsed_ms"),
        "workers": workers,
        "errors": result.get("errors") or [],
    }


def assess_prompt(
    prompt: str,
    *,
    cwd: Path | str,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    associations_path: Path | str | None = None,
    concept_graph_path: Path | str | None = None,
    working_memory_path: Path | str | None = None,
    semantic_triggers_path: Path | str | None = None,
    semantic_cache_path: Path | str | None = None,
    semantic_gate_mode: str | None = None,
    semantic_timeout: int = DEFAULT_SEMANTIC_TIMEOUT,
    use_semantic_gate: bool = True,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None = None,
    use_concept_graph: bool = True,
    search_budget: int = DEFAULT_SEARCH_BUDGET,
) -> dict[str, Any]:
    start = time.perf_counter()
    cwd_path = Path(cwd).resolve()
    prompt = str(prompt or "").strip()
    path = registry_json_path(
        Path(registry_path).resolve() if registry_path else None,
        Path(registry_dir).resolve() if registry_dir else None,
    )
    association_file = (
        Path(associations_path).resolve()
        if associations_path
        else default_associations_path(registry_path=path)
    )
    concept_file = (
        Path(concept_graph_path).resolve()
        if concept_graph_path
        else default_concept_graph_path(registry_path=path)
    )
    working_memory_file = (
        Path(working_memory_path).resolve()
        if working_memory_path
        else default_working_memory_path(registry_path=path)
    )
    semantic_triggers_file = (
        Path(semantic_triggers_path).resolve()
        if semantic_triggers_path
        else default_semantic_triggers_path(registry_path=path)
    )
    if source_text_is_noise(prompt):
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "cwd": str(cwd_path),
            "registry": str(path),
            "associations": str(association_file),
            "concept_graph": str(concept_file),
            "working_memory_path": str(working_memory_file),
            "semantic_triggers_path": str(semantic_triggers_file),
            "query_terms": [],
            "concept_expansions": [],
            "reasons": ["suppressed system/goal noise"],
            "candidates": [],
            "evidence": [],
            "working_memory": [],
            "semantic_gate": None,
            "elapsed_ms": elapsed_ms,
        }
    registry = load_registry(path)
    project_label = current_project_label(registry, cwd_path)
    working_memory_rows = load_working_memory(working_memory_file) if working_memory_file.exists() else []
    working_memory_matches = (
        match_working_memory(
            prompt,
            working_memory_rows,
            project_label=project_label,
        )
        if prompt and working_memory_rows
        else []
    )
    associations = load_associations(association_file)
    association_matches = [
        match
        for match in (match_associations(prompt, associations) if prompt else [])
        if not association_term_is_generic(match)
    ]
    pre_explicit = explicit_recall_terms(prompt)
    pre_associative = matched_terms(prompt, set(CONCEPT_TRIGGERS) | ASSOCIATIVE_CUES)
    pre_important = matched_terms(prompt, IMPORTANCE_CUES)
    semantic_result: dict[str, Any] | None = None
    if use_semantic_gate and prompt and should_run_semantic_gate(
        prompt,
        explicit=pre_explicit,
        associative=pre_associative,
        important=pre_important,
        association_matches=association_matches,
        working_memory_matches=working_memory_matches,
    ):
        gate = semantic_gate_fn or run_semantic_gate
        try:
            semantic_result = gate(
                prompt,
                cwd=cwd_path,
                registry=registry,
                registry_path=path,
                associations=associations,
                working_memory=working_memory_rows,
                semantic_triggers_path=semantic_triggers_file,
                cache_path=Path(semantic_cache_path).resolve() if semantic_cache_path else None,
                mode=semantic_gate_mode,
                timeout=semantic_timeout,
            )
        except Exception as exc:
            semantic_result = {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "reasons": [f"semantic gate error: {exc}"],
                "errors": [str(exc)],
            }
    association_terms: list[str] = []
    for match in association_matches:
        association_terms.append(str(match.get("term") or ""))
        association_terms.extend(str(value) for value in match.get("matched_terms") or [])
        if match.get("status") == "verified":
            association_terms.extend(str(value) for value in match.get("related_terms") or [])

    seed_terms = unique_preserve(
        (expand_query_terms(prompt) if prompt else [])
        + association_terms
        + working_memory_terms(working_memory_matches)
        + semantic_gate_terms(semantic_result),
        limit=36,
    )
    concept_expansions: list[dict[str, Any]] = []
    query_terms = seed_terms
    explicit = pre_explicit
    associative = pre_associative
    important = pre_important

    candidates = score_candidates(prompt, registry, query_terms) if prompt else []
    candidates = merge_association_candidates(candidates, registry, association_matches, query_terms)
    timeline = load_project_timeline(default_project_timeline_path(path))
    candidates = merge_timeline_candidates(candidates, registry, timeline, prompt, cwd_path, query_terms)
    if not candidates and use_concept_graph and prompt and concept_file.exists():
        # Concept BFS is a recall bridge for prompts whose surface words miss
        # registry associations. Once direct association/timeline candidates
        # already exist, expanding concepts can easily introduce semantic drift
        # and corrupt clean-source probe ranking, so keep it as a fallback.
        concept_expansions = expand_concepts(concept_file, seed_terms, depth=2, max_terms=CONCEPT_EXPANSION_MAX_TERMS)
        if concept_expansions:
            query_terms = unique_preserve(seed_terms + concept_expansion_terms(concept_expansions), limit=40)
            candidates = score_candidates(prompt, registry, query_terms) if prompt else []
            candidates = merge_association_candidates(candidates, registry, association_matches, query_terms)
            candidates = merge_timeline_candidates(candidates, registry, timeline, prompt, cwd_path, query_terms)
    if not candidates and (explicit or associative):
        # Metadata can miss memorable wording that only exists inside the
        # SQLite message index. When the user explicitly asks to recover prior
        # speech, try a tiny recent-thread fallback before staying silent.
        candidates = fallback_search_candidates(registry, query_terms)
    semantic_memory_cue = semantic_gate_is_memory_cue(semantic_result)
    has_memory_cue = bool(
        explicit
        or associative
        or important
        or association_matches
        or concept_expansions
        or working_memory_matches
        or semantic_memory_cue
    )
    if candidates and has_memory_cue:
        candidates = rerank_candidates_with_probe(candidates, query_terms)
    suppressed = should_suppress(
        prompt,
        explicit,
        associative,
        candidates,
        working_memory_matches,
        semantic_memory_cue=semantic_memory_cue,
    )
    top_score = float(candidates[0]["score"]) if candidates else 0.0
    working_score = max([float(item.get("score") or 0.0) for item in working_memory_matches] or [0.0])
    reasons: list[str] = []
    if explicit:
        reasons.append("explicit recall cue: " + ", ".join(explicit[:4]))
    if associative:
        reasons.append("associative cue: " + ", ".join(associative[:4]))
    if association_matches:
        reasons.append(
            "dynamic association: "
            + ", ".join(str(item.get("term") or "") for item in association_matches[:4])
        )
    if concept_expansions:
        reasons.append(
            "concept graph expansion: "
            + ", ".join(str(item.get("term") or "") for item in concept_expansions[:4])
        )
    if important:
        reasons.append("importance cue: " + ", ".join(important[:3]))
    if candidates:
        reasons.append("registry overlap: " + ", ".join(str(item["title"]) for item in candidates[:2]))
    if any(item.get("probe_score") for item in candidates[:3]):
        reasons.append("clean-source probe rerank")
    if any(item.get("timeline_source") for item in candidates[:3]):
        reasons.append("project timeline recency cue")
    if working_memory_matches:
        reasons.append(
            "soft working memory: "
            + ", ".join(str(item.get("title") or "") for item in working_memory_matches[:2])
        )
    if semantic_result and semantic_result.get("available"):
        aliases = ", ".join(str(item) for item in (semantic_result.get("query_aliases") or [])[:4])
        semantic_reason = f"semantic gate: {semantic_result.get('decision')} confidence={semantic_result.get('confidence')}"
        if aliases:
            semantic_reason += f" aliases={aliases}"
        reasons.append(semantic_reason)
    if suppressed:
        reasons.append("suppressed ordinary code-surface prompt")

    evidence: list[dict[str, Any]] = []
    decision = "skip"
    if not suppressed and has_memory_cue and (candidates or working_memory_matches) and (
        top_score >= SCENT_THRESHOLD or working_score >= SCENT_THRESHOLD or explicit or associative
        or semantic_memory_cue
    ):
        decision = "scent"
        semantic_wants_evidence = bool(
            semantic_gate_can_request_evidence(prompt, semantic_result)
        )
        if candidates and search_budget > 0 and (explicit or important or semantic_wants_evidence):
            evidence = collect_evidence(candidates, query_terms, search_budget)
            if evidence:
                decision = "evidence"
        elif (
            candidates
            and search_budget > 0
            and association_matches
            and is_decision_continuation(prompt)
            and float(candidates[0].get("probe_score") or 0.0) >= EVIDENCE_LITE_MIN_PROBE_SCORE
        ):
            evidence = collect_evidence(candidates, query_terms, 1)
            if evidence:
                decision = "evidence"
                reasons.append("evidence-lite decision continuation")
        elif (
            candidates
            and search_budget > 0
            and working_memory_matches
            and is_decision_continuation(prompt)
            and float(candidates[0].get("probe_score") or 0.0) >= EVIDENCE_LITE_MIN_PROBE_SCORE
        ):
            evidence = collect_evidence(candidates, query_terms, 1)
            if evidence:
                decision = "evidence"
                reasons.append("working-memory evidence-lite decision continuation")

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "decision": decision,
        "score": round(max(top_score, working_score), 3),
        "confidence": "high" if decision == "evidence" else "medium" if decision == "scent" else "low",
        "cwd": str(cwd_path),
        "registry": str(path),
        "associations": str(association_file),
        "concept_graph": str(concept_file),
        "working_memory_path": str(working_memory_file),
        "semantic_triggers_path": str(semantic_triggers_file),
        "query_terms": query_terms[:16],
        "concept_expansions": concept_expansions[:8],
        "reasons": reasons or ["no ambient recall cue"],
        "candidates": strip_private_fields(candidates[:3]),
        "evidence": evidence[:search_budget],
        "working_memory": strip_for_hook(working_memory_matches[:3]),
        "semantic_gate": strip_semantic_gate(semantic_result),
        "elapsed_ms": elapsed_ms,
    }


def context_for_hook(result: dict[str, Any], *, max_chars: int = MAX_CONTEXT_CHARS) -> str | None:
    decision = result.get("decision")
    if decision == "skip":
        return None
    lines: list[str] = []
    if decision == "evidence":
        lines.append("Ambient recall evidence (aippocampus). Treat as retrieved hints, not automatic truth:")
        for item in result.get("evidence") or []:
            phase = f", {item.get('phase')}" if item.get("phase") else ""
            turn = f", turn {item.get('turn_index')}" if item.get("turn_index") is not None else ""
            lines.append(
                f"- {item.get('title')} line {item.get('line')}{phase}{turn}: "
                f"{compact_text(str(item.get('snippet') or ''), 240)}"
            )
        lines.append("Use these only when relevant; search the source thread before relying on exact wording.")
    else:
        lines.append("Ambient recall scent (aippocampus). Possible related old-thread memory, not evidence:")
        for item in result.get("candidates") or []:
            anchors = ", ".join(item.get("anchors") or [])
            terms = ", ".join(item.get("matched_terms") or item.get("keywords") or [])
            tail = f" | terms: {terms}" if terms else ""
            lines.append(f"- {item.get('title')}: {anchors}{tail}")
        lines.append("Use only if it helps; do not mention recalled content as fact unless backed by retrieved evidence.")
    if result.get("working_memory"):
        lines.append("Soft working memory candidates (source-backed staging, not formal truth):")
        for item in result.get("working_memory") or []:
            terms = ", ".join(item.get("matched_terms") or [])
            refs = item.get("source_refs") or []
            ref = refs[0] if refs else {}
            source = ""
            if ref:
                source = f" | source: {ref.get('title') or ref.get('thread_key')} line {ref.get('line')}"
            lines.append(
                f"- [{item.get('route')}] {item.get('title')} "
                f"(confidence {item.get('confidence')}, terms: {terms}): "
                f"{compact_text(str(item.get('summary') or ''), 220)}"
                f"{source}"
            )
            if item.get("route") == "confirm_when_relevant":
                lines.append("  Ask the user only if this would change the current action or sources conflict.")
        lines.append("For source-backed working memory, search clean source before presenting exact claims as facts.")
    if result.get("reasons"):
        lines.append("Why: " + "; ".join(str(reason) for reason in result.get("reasons", [])[:3]))
    context = "\n".join(lines)
    return compact_text(context, max_chars)


def hook_stdout_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    context = context_for_hook(result)
    if not context:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }


def write_debug_log(
    result: dict[str, Any],
    *,
    hook_input: dict[str, Any] | None = None,
    log_path: Path | None = None,
    include_skip: bool = False,
) -> None:
    if result.get("decision") == "skip" and not include_skip:
        return
    path = log_path or (codex_home() / "aippocampus-registry" / "aippocampus_prompt_hook.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": now_utc(),
        "session_id": (hook_input or {}).get("session_id"),
        "turn_id": (hook_input or {}).get("turn_id"),
        "decision": result.get("decision"),
        "score": result.get("score"),
        "confidence": result.get("confidence"),
        "query_terms": result.get("query_terms"),
        "concept_expansions": [
            {"term": item.get("term"), "score": item.get("score"), "depth": item.get("depth")}
            for item in result.get("concept_expansions", [])[:5]
        ],
        "candidate_threads": [
            {"thread_key": item.get("thread_key"), "title": item.get("title"), "score": item.get("score")}
            for item in result.get("candidates", [])[:3]
        ],
        "working_memory": [
            {"title": item.get("title"), "route": item.get("route"), "score": item.get("score")}
            for item in result.get("working_memory", [])[:3]
        ],
        "semantic_gate": {
            "decision": (result.get("semantic_gate") or {}).get("decision"),
            "confidence": (result.get("semantic_gate") or {}).get("confidence"),
            "cached": (result.get("semantic_gate") or {}).get("cached"),
            "aliases": (result.get("semantic_gate") or {}).get("query_aliases"),
        }
        if result.get("semantic_gate")
        else None,
        "evidence": [
            {"thread_key": item.get("thread_key"), "line": item.get("line"), "phase": item.get("phase")}
            for item in result.get("evidence", [])[:5]
        ],
        "elapsed_ms": result.get("elapsed_ms"),
    }
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="Dry-run prompt text. If omitted, read Codex hook JSON from stdin.")
    parser.add_argument("--cwd", help="Workspace cwd override for dry runs.")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--concept-graph")
    parser.add_argument("--working-memory")
    parser.add_argument("--semantic-triggers")
    parser.add_argument("--semantic-cache")
    parser.add_argument("--semantic-gate", choices=["auto", "on", "off"], default=None)
    parser.add_argument("--semantic-timeout", type=int, default=DEFAULT_SEMANTIC_TIMEOUT)
    parser.add_argument("--no-semantic-gate", action="store_true")
    parser.add_argument("--no-concept-graph", action="store_true")
    parser.add_argument("--search-budget", type=int, default=DEFAULT_SEARCH_BUDGET)
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print the decision JSON instead of hook stdout JSON.")
    parser.add_argument("--log", action="store_true", help="Write sanitized non-prompt debug events for scent/evidence decisions.")
    parser.add_argument("--log-skip", action="store_true", help="Also log skip decisions. Useful only while tuning.")
    parser.add_argument("--strict", action="store_true", help="Raise hook errors instead of silently continuing.")
    args = parser.parse_args()

    hook_input: dict[str, Any] = {}
    try:
        if args.prompt is None:
            hook_input = hook_input_from_stdin()
            prompt = str(hook_input.get("prompt") or "")
            cwd = Path(args.cwd or hook_input.get("cwd") or os.getcwd())
        else:
            prompt = args.prompt
            cwd = Path(args.cwd or os.getcwd())
        result = assess_prompt(
            prompt,
            cwd=cwd,
            registry_path=Path(args.registry) if args.registry else None,
            registry_dir=Path(args.registry_dir) if args.registry_dir else None,
            concept_graph_path=Path(args.concept_graph) if args.concept_graph else None,
            working_memory_path=Path(args.working_memory) if args.working_memory else None,
            semantic_triggers_path=Path(args.semantic_triggers) if args.semantic_triggers else None,
            semantic_cache_path=Path(args.semantic_cache) if args.semantic_cache else None,
            semantic_gate_mode="off" if args.no_semantic_gate else args.semantic_gate,
            semantic_timeout=args.semantic_timeout,
            use_semantic_gate=not args.no_semantic_gate,
            use_concept_graph=not args.no_concept_graph,
            search_budget=args.search_budget,
        )
        if args.log or args.log_skip:
            write_debug_log(result, hook_input=hook_input, include_skip=args.log_skip)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        payload = hook_stdout_payload(result)
        if payload:
            print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        if args.strict:
            raise
        if args.json_output:
            print(json.dumps({"decision": "skip", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
