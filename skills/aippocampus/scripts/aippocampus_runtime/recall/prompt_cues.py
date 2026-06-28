#!/usr/bin/env python3
"""Prompt cue and term policy for AIppocampus foreground recall."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from aippocampus_runtime.recall import prompt_cue_catalog as _cue_catalog
from aippocampus_runtime.recall.life_cues import (
    LIFE_WIDE_SCOPE_LABEL_CUES,
    profile_recall_terms,
)
from aippocampus_runtime.recall.prompt_route_blocks import (
    old_route_negation_has_later_source_request,
)
from aippocampus_runtime.recall.query_policy import RECALL_TRIGGERS, split_query_terms
from aippocampus_runtime.recall.semantic.confidence_policy import (
    meets_background_warm_cache_confidence,
    meets_memory_cue_confidence,
    meets_source_reopen_confidence,
)
from aippocampus_runtime.text import has_cjk_ideograph, is_low_value_cjk_fragment

# Keep these assignments as the legacy public surface for callers that imported
# static cue catalogs from prompt_cues.py before the hot-path split.
ASSOCIATIVE_CUES = _cue_catalog.ASSOCIATIVE_CUES
CJK_CONTENT_MARKERS = _cue_catalog.CJK_CONTENT_MARKERS
CJK_SHORT_EVIDENCE_TERMS = _cue_catalog.CJK_SHORT_EVIDENCE_TERMS
CODE_SURFACE_CUES = _cue_catalog.CODE_SURFACE_CUES
CONCEPT_EXPANSION_MAX_TERMS = _cue_catalog.CONCEPT_EXPANSION_MAX_TERMS
CURRENT_CHECKOUT_FACT_PATTERNS = _cue_catalog.CURRENT_CHECKOUT_FACT_PATTERNS
CURRENT_CHECKOUT_SCOPE_PATTERNS = _cue_catalog.CURRENT_CHECKOUT_SCOPE_PATTERNS
DECISION_CONTINUATION_CUES = _cue_catalog.DECISION_CONTINUATION_CUES
EXACT_WORDING_TOPIC_TERMS = _cue_catalog.EXACT_WORDING_TOPIC_TERMS
EXPLICIT_RECALL_TERMS = _cue_catalog.EXPLICIT_RECALL_TERMS
GENERIC_ASSOCIATION_TERMS = _cue_catalog.GENERIC_ASSOCIATION_TERMS
GENERIC_EVIDENCE_TERMS = _cue_catalog.GENERIC_EVIDENCE_TERMS
IMPORTANCE_CUES = _cue_catalog.IMPORTANCE_CUES
MEMORY_BOUNDARY_CONTEXT_PATTERNS = _cue_catalog.MEMORY_BOUNDARY_CONTEXT_PATTERNS
MEMORY_WRITE_NEGATION_PATTERNS = _cue_catalog.MEMORY_WRITE_NEGATION_PATTERNS
NATURAL_EVIDENCE_PATTERNS = _cue_catalog.NATURAL_EVIDENCE_PATTERNS
NEGATIVE_EVIDENCE_PATTERNS = _cue_catalog.NEGATIVE_EVIDENCE_PATTERNS
PRIOR_HISTORY_MARKER_PATTERNS = _cue_catalog.PRIOR_HISTORY_MARKER_PATTERNS
RECALL_ACTION_TERMS = _cue_catalog.RECALL_ACTION_TERMS
RECENCY_CUES = _cue_catalog.RECENCY_CUES
SECRET_SURFACE_PATTERNS = _cue_catalog.SECRET_SURFACE_PATTERNS
SEMANTIC_EVIDENCE_TERMS = _cue_catalog.SEMANTIC_EVIDENCE_TERMS
SEMANTIC_GATE_ALIAS_DECISIONS = _cue_catalog.SEMANTIC_GATE_ALIAS_DECISIONS
SEMANTIC_GATE_CUE_DECISIONS = _cue_catalog.SEMANTIC_GATE_CUE_DECISIONS
SEMANTIC_GATE_LIGHT_CUES = _cue_catalog.SEMANTIC_GATE_LIGHT_CUES
SEMANTIC_TRIGGER_CONTEXT_PATTERNS = _cue_catalog.SEMANTIC_TRIGGER_CONTEXT_PATTERNS
SOURCE_EVIDENCE_REQUEST_PATTERNS = _cue_catalog.SOURCE_EVIDENCE_REQUEST_PATTERNS
SOURCE_EVIDENCE_REQUEST_TERMS = _cue_catalog.SOURCE_EVIDENCE_REQUEST_TERMS
TERM_WRAPPERS_RE = _cue_catalog.TERM_WRAPPERS_RE
WEAK_DEICTIC_TERMS = _cue_catalog.WEAK_DEICTIC_TERMS


def unique_preserve(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", str(item)).strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def merge_unique_terms(*groups: Iterable[Any], limit: int = 8) -> list[str]:
    """Merge already-bounded term groups without loop-local list materialization."""

    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group:
            value = re.sub(r"\s+", " ", str(item or "")).strip()
            folded = value.casefold()
            if not value or folded in seen:
                continue
            seen.add(folded)
            out.append(value)
            if len(out) >= limit:
                return out
    return out


def matched_terms(prompt: str, bounded_terms: set[str]) -> list[str]:
    low = prompt.casefold()
    matches: list[str] = []
    for term in sorted(bounded_terms, key=len, reverse=True):
        needle = term.casefold()
        if not needle:
            continue
        if re.search(r"[A-Za-z0-9_]", needle):
            # Short English cues such as "rag", "api", and "hook" are useful
            # when they appear as terms, but dangerous as raw substrings:
            # "paragraphs", "leveraging", and "webhook" should not become
            # memory cues. Non-ASCII cue words keep the existing substring
            # behavior because Chinese does not have whitespace token
            # boundaries.
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])"
            if re.search(pattern, low):
                matches.append(term)
        elif needle in low:
            matches.append(term)
    return matches


def prompt_is_code_surface(prompt: str) -> bool:
    return bool(matched_terms(prompt, CODE_SURFACE_CUES))


def memory_write_negation_intent(prompt: str) -> list[str]:
    """Return cues where the user rejects creating or persisting memory.

    This protects ordinary implementation and metadata prompts from becoming
    ambient recall just because they contain words like "记住" or "memory".
    It is intentionally narrower than negative evidence: "no source" can still
    be a scent-only continuation, but "not a memory write" is a write-path
    boundary and should keep foreground recall quiet.
    """

    text = str(prompt or "").strip()
    if not text:
        return []
    if source_evidence_intent(text) or natural_evidence_intent(text):
        return []
    matches: list[str] = []
    for pattern in MEMORY_WRITE_NEGATION_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(found.group(0))
    return unique_preserve(matches, limit=4)


def prompt_is_secret_surface(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in SECRET_SURFACE_PATTERNS)


def current_checkout_fact_intent(prompt: str) -> bool:
    """Return whether the prompt asks for facts about the current checkout.

    This is a source-boundary guard, not a semantic memory classifier. When it
    fires, old project memories may still inform portable preferences, but they
    must not be promoted as evidence for facts that should be read from the
    files and config in the checkout currently under the agent's hands.
    """

    text = str(prompt or "").strip()
    if not text:
        return False
    if not any(pattern.search(text) for pattern in CURRENT_CHECKOUT_SCOPE_PATTERNS):
        return False
    return prompt_is_code_surface(text) or any(
        pattern.search(text) for pattern in CURRENT_CHECKOUT_FACT_PATTERNS
    )


def current_checkout_live_fact_intent(prompt: str) -> bool:
    """Return whether local files/config must outrank old memory evidence.

    This deliberately keys on an explicit current-checkout surface first. It is
    not trying to infer the user's whole semantic intent from a frozen label
    list; it only prevents a narrow failure mode where source-backed history
    about another project gets treated as proof for facts that should be read
    from the checkout currently open in front of the agent.
    """

    if not current_checkout_fact_intent(prompt):
        return False
    text = str(prompt or "").strip()
    if any(pattern.search(text) for pattern in PRIOR_HISTORY_MARKER_PATTERNS):
        return False
    prior_history_terms = {
        "之前说过",
        "你之前说过",
        "我之前说过",
        "最后回复",
        "最后的消息",
    }
    return not bool(set(explicit_recall_terms(prompt)) & prior_history_terms)


def memory_boundary_context_intent(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in MEMORY_BOUNDARY_CONTEXT_PATTERNS)


def explicit_recall_terms(prompt: str) -> list[str]:
    # Retrieval-level triggers include useful weak deixis such as "这个/那个".
    # Those should help search phrasing, but they must not escalate a prompt to
    # evidence retrieval by themselves; otherwise ordinary continuation text can
    # summon exact snippets too eagerly.
    strong = (set(RECALL_TRIGGERS) | EXPLICIT_RECALL_TERMS) - WEAK_DEICTIC_TERMS
    matches = matched_terms(prompt, strong)
    if not matches:
        return []
    has_recall_action = bool(set(matches) & RECALL_ACTION_TERMS)
    if has_recall_action:
        return matches
    if matched_terms(prompt, DECISION_CONTINUATION_CUES) or re.search(
        r"(继续|还要怎么|怎么处理|怎么收|怎么推进|怎么接)", prompt, flags=re.IGNORECASE
    ):
        # Exact-wording nouns are often the topic being discussed ("那句 quote
        # 怎么处理"), not a request to surface source snippets. Keep them as
        # evidence cues when paired with a recall action, but do not let them
        # override a continuation/decision prompt by themselves.
        matches = [term for term in matches if term not in EXACT_WORDING_TOPIC_TERMS]
    return matches


def expand_query_terms(prompt: str) -> list[str]:
    terms = split_query_terms([prompt]) if prompt else []
    expanded = list(terms)
    expanded.extend(profile_recall_terms(prompt))
    for phrase in re.findall(
        r"[A-Za-z][A-Za-z0-9_.+-]*(?:\s+[A-Za-z][A-Za-z0-9_.+-]*){1,3}", prompt
    ):
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


def _evidence_min_len(term: str) -> int:
    if term in CJK_SHORT_EVIDENCE_TERMS:
        return 2
    return 3


def evidence_content_terms(query_terms: list[str]) -> list[str]:
    terms: list[str] = []
    for term in query_terms:
        low = term.casefold().strip()
        min_len = _evidence_min_len(term)
        if low in GENERIC_EVIDENCE_TERMS or len(low) < min_len:
            continue
        cleaned = TERM_WRAPPERS_RE.sub(" ", term)
        cleaned = re.sub(r"[，。；：！？,.!?/|+]+", " ", cleaned)
        for part in cleaned.split():
            part = part.strip()
            part_min_len = _evidence_min_len(part)
            if len(part) >= part_min_len and part.casefold() not in GENERIC_EVIDENCE_TERMS:
                terms.append(part)
        if len(term) <= 40:
            terms.append(term)
    return unique_preserve(terms, limit=10)


def natural_evidence_intent(prompt: str) -> list[str]:
    """Return natural-language source intent cues, not broad memory scent.

    This is deliberately narrower than weak deixis. A bare "继续/那个/上次"
    should not summon snippets, but ordinary human requests like "上次关于 X 的
    结论是什么" or "找一下之前说 X 的那段" should be allowed to try a small
    clean-source evidence upgrade when candidate and hit quality are strong.
    """

    text = str(prompt or "").strip()
    if not text:
        return []
    matches: list[str] = []
    for pattern in NATURAL_EVIDENCE_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(found.group(0))
    return unique_preserve(matches, limit=4)


def source_evidence_intent(prompt: str) -> list[str]:
    """Return explicit source/evidence request cues across common languages.

    Unlike ``SEMANTIC_EVIDENCE_TERMS``, this deliberately excludes bare
    ``quote``/``evidence`` as standalone topic words. Prompts such as
    "self-continuity quote 继续" are continuation about a theme; prompts such
    as "Can you cite..." or "请给 source-backed evidence" are requests for
    foreground source snippets.
    """

    text = str(prompt or "").strip()
    if not text:
        return []
    matches = matched_terms(text, SOURCE_EVIDENCE_REQUEST_TERMS)
    for pattern in SOURCE_EVIDENCE_REQUEST_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(found.group(0))
    return unique_preserve(matches, limit=6)


def negative_evidence_intent(prompt: str) -> list[str]:
    text = str(prompt or "").strip()
    if not text:
        return []
    if old_route_negation_has_later_source_request(text):
        return []
    matches: list[str] = []
    for pattern in NEGATIVE_EVIDENCE_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(found.group(0))
    return unique_preserve(matches, limit=4)


def association_term_is_generic(match: dict[str, Any]) -> bool:
    term = str(match.get("term") or "").casefold().strip()
    if term in {value.casefold() for value in GENERIC_ASSOCIATION_TERMS}:
        return True
    if term in {
        "source",
        "sources",
        "plugin",
        "plugins",
        "hook",
        "hooks",
        "runtime",
        "agent",
        "agents",
        "system",
        "health",
        "clean",
        "maintenance",
        "rollout",
        "graph",
        "test",
        "tests",
        "issue",
        "issues",
    }:
        return True
    if has_cjk_ideograph(term) and is_low_value_cjk_fragment(term):
        return True
    return False


def matched_life_wide_timeline_cues(prompt: str) -> tuple[list[str], list[str]]:
    if not matched_terms(prompt, RECENCY_CUES):
        return [], []
    # Life-wide timeline is global and personal by nature. Require both a
    # recency cue and a scope-label scent so ordinary status/code prompts do not
    # get over-personalized by ambient recall.
    labels: list[str] = []
    cue_terms: list[str] = []
    for label, cues in LIFE_WIDE_SCOPE_LABEL_CUES.items():
        hits = matched_life_wide_cue_terms(prompt, cues)
        if not hits:
            continue
        labels.append(label)
        cue_terms.extend(hits)
    # "问题/question" is common in task and status prompts. It can help once
    # another life-wide label is present, but must not summon personal memory
    # by itself.
    if labels and set(labels).issubset({"open_question"}):
        return [], []
    return labels, unique_preserve(cue_terms, limit=8)


def matched_life_wide_cue_terms(prompt: str, cues: set[str]) -> list[str]:
    low = prompt.casefold()
    hits: list[str] = []
    for cue in sorted(cues, key=len, reverse=True):
        cue_text = cue.casefold()
        if re.fullmatch(r"[a-z0-9_]+(?:\s+[a-z0-9_]+)*", cue_text):
            pattern = (
                r"(?<![a-z0-9_])"
                + r"\s+".join(re.escape(part) for part in cue_text.split())
                + r"(?![a-z0-9_])"
            )
            if re.search(pattern, low):
                hits.append(cue)
            continue
        if cue_text in low:
            hits.append(cue)
    return hits


def is_decision_continuation(prompt: str) -> bool:
    return bool(matched_terms(prompt, DECISION_CONTINUATION_CUES))


def semantic_trigger_context_intent(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text:
        return False
    if memory_boundary_context_intent(text):
        return True
    return any(pattern.search(text) for pattern in SEMANTIC_TRIGGER_CONTEXT_PATTERNS)


def concept_expansion_terms(expansions: list[dict[str, Any]]) -> list[str]:
    return unique_preserve(
        [str(item.get("term") or "") for item in expansions], limit=CONCEPT_EXPANSION_MAX_TERMS
    )


def working_memory_terms(matches: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for match in matches:
        terms.extend(str(value) for value in match.get("matched_terms") or [])
        terms.extend(str(value) for value in match.get("trigger_terms") or [])
        terms.extend(
            split_query_terms([str(match.get("title") or ""), str(match.get("summary") or "")])
        )
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
    confidence = float((result or {}).get("confidence") or 0.0)
    return bool(
        result
        and result.get("available")
        and str(result.get("decision") or "") in SEMANTIC_GATE_CUE_DECISIONS
        and meets_memory_cue_confidence(confidence)
    )


def semantic_gate_can_warm_cue_cache(result: dict[str, Any] | None) -> bool:
    if not result or not result.get("available"):
        return False
    decision, confidence = str(result.get("decision") or ""), float(result.get("confidence") or 0.0)
    # `background_only` can warm reusable aliases, but it stays below the
    # foreground memory-cue/evidence line and still needs local candidates plus
    # repeated source-backed hits before `semantic_cue_cache` promotes it.
    return (
        decision in SEMANTIC_GATE_CUE_DECISIONS
        and meets_memory_cue_confidence(confidence)
    ) or (
        decision == "background_only"
        and meets_background_warm_cache_confidence(confidence)
    )


def semantic_gate_can_request_evidence(prompt: str, result: dict[str, Any] | None) -> bool:
    if not result or not result.get("available") or result.get("decision") != "evidence":
        return False
    if negative_evidence_intent(prompt):
        return False
    if current_checkout_live_fact_intent(prompt):
        return False
    if float(result.get("confidence") or 0.0) < 0.5:
        return False
    # DeepSeek may understand vague status prompts semantically, but the hook
    # should not turn that into source snippets unless the user is asking for
    # exact/source-backed recall. Otherwise a fuzzy "how is that memory thing
    # going?" can surface old high-scoring fragments instead of staying as a
    # gentle scent for the foreground model to decide on.
    return bool(
        explicit_recall_terms(prompt)
        or source_evidence_intent(prompt)
        or natural_evidence_intent(prompt)
    )


def semantic_gate_can_request_source_reopen(prompt: str, result: dict[str, Any] | None) -> bool:
    if semantic_gate_can_request_evidence(prompt, result):
        return True
    if not result or not result.get("available") or result.get("decision") != "evidence":
        return False
    if negative_evidence_intent(prompt) or current_checkout_live_fact_intent(prompt):
        return False
    if not meets_source_reopen_confidence(float(result.get("confidence") or 0.0)):
        return False
    risk = str(result.get("anti_personalization_risk") or "").strip().casefold()
    intent = str(result.get("intent") or "").strip().casefold()
    # Live semantic workers often label vague "continue that old thread" prompts
    # as `continuation`: source truth still blocks factual evidence, but a
    # paid/high-confidence route should give the foreground agent a reopen plan
    # instead of collapsing back to ordinary scent/manual grep.
    has_route_surface = bool(result.get("query_aliases") or result.get("memory_scope"))
    return bool(
        risk != "high"
        and intent in {"continuation", "recall", "source_recall", "exact_recall"}
        and has_route_surface
    )


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


LOW_VALUE_CASUAL_PATTERNS = (
    re.compile(r"(今天天气怎么样|天气怎么样|天气如何|weather\s+(today|tomorrow)|what'?s\s+the\s+weather)", re.IGNORECASE),
    re.compile(r"(最近有什么值得聊的|有什么值得聊|聊点什么|what\s+should\s+we\s+talk\s+about)", re.IGNORECASE),
    re.compile(r"^(谢谢|谢啦|多谢|thanks|thank\s+you|thx|ok|好的|嗯|嗯嗯)[.!。！\s]*$", re.IGNORECASE),
)


def low_value_casual_prompt(prompt: str) -> bool:
    """Return obvious daily chat prompts that should stay cheap and silent.

    This is a foreground spend brake, not a memory-quality classifier. If the
    prompt contains any explicit recall, evidence, source, or importance cue,
    semantic recall may still run; the brake only covers bare weather/chat
    prompts where waiting on a model and then emitting nothing feels broken.
    """

    text = str(prompt or "").strip()
    if not text:
        return False
    if (
        explicit_recall_terms(text)
        or natural_evidence_intent(text)
        or source_evidence_intent(text)
        or matched_terms(text, IMPORTANCE_CUES)
        or semantic_trigger_context_intent(text)
    ):
        return False
    return any(pattern.search(text) for pattern in LOW_VALUE_CASUAL_PATTERNS)


def should_run_semantic_gate(
    prompt: str,
    *,
    explicit: list[str],
    associative: list[str],
    important: list[str],
    association_matches: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    cognitive_map_matches: list[dict[str, Any]],
) -> bool:
    if cognitive_map_matches:
        # A materialized cognitive route is already the result of detached
        # DeepSeek work. Do not spend foreground hook time asking DeepSeek again.
        return False
    if prompt_is_secret_surface(prompt):
        # Placeholder/header/cookie prompts are common places for real secrets
        # to get pasted by accident. Keep them on the deterministic local path:
        # a safe memory-boundary prompt may still surface scent locally, but it
        # must not be sent to an external semantic model.
        return False
    if memory_write_negation_intent(prompt):
        return False
    if current_checkout_live_fact_intent(prompt):
        # The current checkout boundary is a live-source problem, not a memory
        # classification problem. Let the foreground agent inspect the repo
        # files/config instead of spending semantic recall budget.
        return False
    if low_value_casual_prompt(prompt):
        return False
    if prompt_is_code_surface(prompt) and not (
        explicit
        or associative
        or important
        or working_memory_matches
        or semantic_trigger_context_intent(prompt)
    ):
        # This is a spend/latency brake, not the recall brain. Dynamic
        # associations can include ordinary implementation words such as
        # dashboard/hover/test; those should not make every code task call a
        # semantic model. Source-backed working memory and explicit continuation
        # wording still get through.
        return False
    if explicit and (association_matches or working_memory_matches):
        # Explicit memory cue plus local source/working-memory overlap is enough
        # for foreground evidence. Calling an external semantic model here tends
        # to spend the whole hook budget while adding little recall quality; use
        # semantic only when the local cue surface is too thin.
        return False
    if explicit or associative or important or association_matches or working_memory_matches:
        return True
    if semantic_trigger_context_intent(prompt):
        return True
    if looks_like_multilingual_natural_language(prompt):
        return True
    if looks_like_latin_long_question(prompt):
        return True
    if matched_terms(prompt, SEMANTIC_GATE_LIGHT_CUES | DECISION_CONTINUATION_CUES | RECENCY_CUES):
        return True
    return False
