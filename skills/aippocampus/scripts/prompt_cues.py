#!/usr/bin/env python3
"""Prompt cue and term policy for AIppocampus foreground recall."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from retrieval import RECALL_TRIGGERS, split_query_terms

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
    "cite",
    "source-backed",
    "source-backed evidence",
    "source evidence",
    "clean source",
    "verbatim",
    "exact wording",
    "original wording",
    "原文",
    "原话",
    "证据",
    "引用",
    "行号",
    "你之前说过",
    "我之前说过",
}

SOURCE_EVIDENCE_REQUEST_TERMS = {
    "cite",
    "cites",
    "cited",
    "citation",
    "source-backed",
    "source-backed evidence",
    "source evidence",
    "clean source",
    "verbatim",
    "exact wording",
    "original wording",
    "原文",
    "原话",
    "证据",
    "引用",
    "行号",
}

NATURAL_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(找一下|查一下|找找|查查|看看).{0,24}(之前|前面|刚才|上次|说过|那段|那句|结论|判断|原话|原文)",
        r"(之前|前面|刚才|上次).{0,64}(那段|那句|结论|判断|说法|怎么说|怎么表述|怎么定性|是什么|哪句|讲过|说过)",
        r"(那段|那句|那个|这个|那次|这次).{0,36}(结论|判断|说法|决定|怎么说|怎么表述|怎么定性|是什么|哪句)",
        r"(那个|这个|那条|这条).{0,24}(结论|判断|说法|决定).{0,12}(怎么说|怎么表述|是什么)",
        r"(继续).{0,36}(那个|这个|那条|这条).{0,18}(结论|判断|说法|决定)",
        r"(that|the|this).{0,24}(conclusion|decision|part|bit|quote|wording)",
        r"(last time|previously|earlier).{0,48}(conclusion|decision|said|quote|wording)",
    ]
]

NEGATIVE_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(不要|别|先别).{0,12}(引用|原话|原文|证据|source|evidence)",
        r"(只|先只).{0,8}(给|要)?\s*(scent|味道|线索)",
        r"(scent[- ]only).{0,12}(mode|context|output|please|即可|就行)",
        r"(no source|no evidence|no quote|no citation)",
        r"(do not|don't).{0,20}(cite|quote|give evidence|retrieve evidence)",
        r"(without|with no|lacking).{0,24}(source|evidence|citation|cite|cited|quote|clean source|source-backed)",
        r"(unsupported|downgrade|keep it unsupported).{0,36}(without|unless).{0,24}(source|evidence|citation|cite|cited|quote|clean source|source-backed)",
    ]
]

SOURCE_EVIDENCE_REQUEST_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(can you|could you|please)\s+(cite|quote)\b",
        r"\bcite\s+.+\?",
        r"(请给|给|找回|找一下|查一下).{0,18}(source-backed|source evidence|clean source|证据|引用|原话|原文)",
        r"(source-backed|source evidence|clean source).{0,18}(evidence|quote|citation|原话|原文|证据|引用)?",
    ]
]

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

RECALL_ACTION_TERMS = {
    "找回",
    "想起来",
    "想起",
    "最后回复",
    "最后的消息",
    "之前说过",
    "你说过",
    "我说过",
}

EXACT_WORDING_TOPIC_TERMS = {
    "原文",
    "原话",
    "那句",
    "这句",
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

# Bootstrap/fallback cues for foreground spend and scent gating. Keep this
# compact and language-light: new semantic paraphrases belong in
# `semantic_triggers.jsonl` or the learned `semantic_cues.jsonl` cache, which
# `prompt_recall_context.py` folds into the same pre-gate path.
ASSOCIATIVE_CUES = {
    "联想",
    "触发",
    "钩子",
    "hook机制",
    "prompt hook",
    "UserPromptSubmit",
    "记忆",
    "召回",
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
    "panel",
    "filter",
    "filters",
    "chart",
    "charts",
    "figma",
    "layout",
    "grid",
    "table",
    "route",
    "fixture",
    "modal",
    "navigation",
    "loading",
    "mobile",
    "断点",
    "视觉稿",
    "还原",
    "对齐",
    "接上",
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

SECRET_SURFACE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(authorization|bearer|cookie|set-cookie|api[_ -]?key|api\s+token|access[_ -]?token|private\s+key|oauth\s+secret|database\s+password|db\s+password|webhook\s+signature)\b.{0,36}\b(placeholder|mock|fixture|header|label|sample|env\.?sample|validation|ui)\b",
        r"\b(placeholder|mock|fixture|header|label|sample|validation)\b.{0,36}\b(cookie|bearer|api[_ -]?key|api\s+token|access[_ -]?token|private\s+key|oauth\s+secret|password|secret)\b",
        r"\b(authorization\s*:\s*bearer|bearer\s+[a-z0-9._~+/=-]{8,}|cookie\s*[:=]|set-cookie\b|api[_ -]?key\s*[:=]|secret\s*[:=]|password\s*[:=]|token\s*[:=])",
    ]
]

MEMORY_BOUNDARY_CONTEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(只|先只).{0,12}(看|处理|保留|要).{0,30}(外置海马体|小海马体|external hippocampus|memory boundary|recall gate|project[- ]scoped|上下文|边界)",
        r"(外置海马体|小海马体|external hippocampus|memory boundary|recall gate|project[- ]scoped).{0,20}(边界|上下文|context|scope)",
    ]
]

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

SEMANTIC_TRIGGER_CONTEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(只|先)?继续.{0,24}(上下文|那条线|这条线|那条|这条|线索)",
        r"(那条线|这条线|上下文|线索).{0,24}(继续|接着|推进|收口)",
        r"(那条线|这条线|上下文|线索).{0,16}(继续想|想一下|想想|想清楚|想明白)",
        r"(继续|接着)(看|想|推进|收口|处理)",
        r"(继续|接着).{0,16}(不给|不要|别|先别).{0,10}(source|evidence|原话|原文|引用|证据)",
        r"(不要|先别).{0,12}(展开实现|实现|改代码|写代码)",
        r"(only|just).{0,24}(continue|resume).{0,48}(context|thread|line)",
        r"(continue|resume).{0,48}(that context|the context|where we left off|thread|line)",
        r"(do not|don't).{0,24}(implement|code|change)",
    ]
]

RECENCY_CUES = {
    "最近",
    "最后",
    "上次",
    "当前线程之外",
    "外面",
    "latest",
    "recent",
}

LIFE_WIDE_SCOPE_LABEL_CUES = {
    "personal_reflection": {
        "焦虑",
        "困惑",
        "感觉",
        "感受",
        "自我",
        "reflection",
        "anxiety",
        "feeling",
    },
    "relationship_continuity": {
        "关系",
        "我们聊",
        "我和你",
        "陪伴",
        "continuity",
        "relationship",
    },
    "reading_notes": {
        "读到",
        "看过",
        "那篇",
        "这篇",
        "文章",
        "书",
        "reading",
        "article",
        "book",
    },
    "idea_seed": {
        "点子",
        "想法",
        "灵感",
        "脑洞",
        "idea",
        "spark",
    },
    "preference": {
        "偏好",
        "喜欢",
        "不喜欢",
        "以后",
        "preference",
        "prefer",
    },
    "life_context": {
        "生活",
        "日常",
        "人生",
        "近况",
        "life",
        "daily",
    },
    "open_question": {
        "问题",
        "疑问",
        "要不要",
        "该不该",
        "是否",
        "question",
    },
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


def matched_terms(prompt: str, terms: set[str]) -> list[str]:
    low = prompt.casefold()
    matches: list[str] = []
    for term in sorted(terms, key=len, reverse=True):
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


def prompt_is_secret_surface(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in SECRET_SURFACE_PATTERNS)


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
    return bool(
        result
        and result.get("available")
        and str(result.get("decision") or "") in SEMANTIC_GATE_CUE_DECISIONS
        and float(result.get("confidence") or 0.0) >= 0.35
    )


def semantic_gate_can_request_evidence(prompt: str, result: dict[str, Any] | None) -> bool:
    if not result or not result.get("available") or result.get("decision") != "evidence":
        return False
    if negative_evidence_intent(prompt):
        return False
    if float(result.get("confidence") or 0.0) < 0.5:
        return False
    # DeepSeek may understand vague status prompts semantically, but the hook
    # should not turn that into source snippets unless the user is asking for
    # exact/source-backed recall. Otherwise a fuzzy "how is that memory thing
    # going?" can surface old high-scoring fragments instead of staying as a
    # gentle scent for the foreground model to decide on.
    if (
        explicit_recall_terms(prompt)
        or source_evidence_intent(prompt)
        or natural_evidence_intent(prompt)
    ):
        return True

    risk = str(result.get("anti_personalization_risk") or "").strip().casefold()
    if risk == "high":
        return False
    intent = str(result.get("intent") or "").strip().casefold()
    if intent not in {"recall", "source_recall", "exact_recall"}:
        return False
    if float(result.get("confidence") or 0.0) < 0.82:
        return False
    # Subconscious/semantic context may decide a fuzzy status prompt is really a
    # bounded recall request. That signal can open a local evidence probe, but
    # the source hit still has to come from clean source/SQLite and pass normal
    # quality filtering before anything is injected.
    return bool(result.get("query_aliases") or result.get("memory_scope"))


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
    if prompt_is_code_surface(prompt) and not (
        explicit or associative or important or working_memory_matches
    ):
        # This is a spend/latency brake, not the recall brain. Dynamic
        # associations can include ordinary implementation words such as
        # dashboard/hover/test; those should not make every code task call a
        # semantic model. Source-backed working memory still gets through.
        return False
    if explicit and (association_matches or working_memory_matches):
        # Explicit memory cue plus local source/working-memory overlap is enough
        # for foreground evidence. Calling an external semantic model here tends
        # to spend the whole hook budget while adding little recall quality; use
        # semantic only when the local cue surface is too thin.
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
