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
    "prompt hook",
    "UserPromptSubmit",
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
    "source evidence",
    "source-backed evidence",
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
    cognitive_map_matches: list[dict[str, Any]],
) -> bool:
    if cognitive_map_matches:
        # A materialized cognitive route is already the result of detached
        # DeepSeek work. Do not spend foreground hook time asking DeepSeek again.
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
