"""Term extraction and noise filters for association indexes."""

from __future__ import annotations

import re

from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.text import (
    cjk_phrase_candidates,
    has_cjk_ideograph,
    is_low_value_cjk_fragment,
    iter_cjk_sequences,
    strip_cjk_deictic_prefix,
)

DEFAULT_MAX_TERMS_PER_SOURCE = 18

ASCII_STOP_TERMS = {
    "and",
    "are",
    "codex",
    "for",
    "from",
    "goal",
    "mode",
    "status",
    "that",
    "the",
    "this",
    "thread",
    "token",
    "true",
    "false",
    "with",
}

TRIVIAL_PHRASES = {
    "好",
    "好的",
    "好开干",
    "开干",
    "再想想",
    "继续",
    "好继续",
    "开始吧",
    "嗯",
    "关于",
    "当前线程",
    "前线程",
    "主题是什么",
    "ok",
    "okay",
}

SOURCE_NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"#\s*AGENTS\.md instructions",
        r"<permissions instructions>",
        r"<environment_context>",
        r"\bcurrent goal\b",
        r"\btoken budget\b",
        r"\bremaining token\b",
        r"\bgoal mode\b",
        r"\bstatus\s+(active|paused|complete)\b",
        r"\bhookSpecificOutput\b",
    ]
]

WHITESPACE_RE = re.compile(r"\s+")
ASCII_BOUNDARY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_.-"
)

CJK_BOUNDARY_WORDS = [
    "UserPromptSubmit",
    "associations",
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "一种",
    "一个",
    "把",
    "靠",
    "通过",
    "读取",
    "做成",
    "变成",
    "都要",
    "同一条",
    "需要",
    "可以",
    "已经",
    "以及",
    "然后",
    "接着",
    "最后",
    "和",
    "与",
    "的",
    "了",
]

CJK_GLUE_NOISE = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "把",
    "靠",
    "读取",
    "做成",
    "通过",
    "更像",
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "或",
    "而",
    "但",
}

DURABLE_CJK_HINTS = {
    "记忆",
    "联想",
    "召回",
    "海马",
    "触发",
    "钩子",
    "生命",
    "自我",
    "连续",
    "线程",
    "索引",
    "压缩",
    "归档",
    "证据",
    "结论",
    "轮次",
    "阶段",
    "工具",
}


def normalize_term(value: str) -> str:
    value = WHITESPACE_RE.sub(" ", str(value)).strip(
        " \t\r\n\"'`.,;:!?，。；：！？、()[]{}<>《》"
    )
    return value


def source_text_is_noise(text: str) -> bool:
    stripped = "".join(text.split()).casefold()
    if stripped in TRIVIAL_PHRASES:
        return True
    return any(pattern.search(text) for pattern in SOURCE_NOISE_PATTERNS)


def ascii_term_is_simple(term: str) -> bool:
    return bool(term) and all(ch in ASCII_BOUNDARY_CHARS for ch in term)


def has_local_path_marker(term: str) -> bool:
    low = term.casefold()
    if any(marker in low for marker in ("/users/", "/home/", "/tmp/", "/var/")):
        return True
    return any(
        index + 2 < len(term)
        and term[index].isalpha()
        and term[index + 1] == ":"
        and term[index + 2] == "\\"
        for index in range(len(term))
    )


def term_is_noise(term: str) -> bool:
    term = normalize_term(term)
    if not term:
        return True
    low = term.casefold()
    squashed = "".join(low.split())
    if squashed in TRIVIAL_PHRASES:
        return True
    if low in ASCII_STOP_TERMS:
        return True
    if low in {"goals", "budget", "remaining", "active", "paused", "complete"}:
        return True
    if has_cjk_ideograph(term):
        if squashed in CJK_GLUE_NOISE:
            return True
        if is_low_value_cjk_fragment(squashed):
            return True
        if any(squashed.startswith(marker) for marker in ("我们", "你们", "他们", "这个", "那个")):
            return True
        if len(squashed) <= 4 and any(squashed.endswith(marker) for marker in ("的", "了")):
            return True
        if any(marker in squashed for marker in ("更像", "读取", "做成", "通过")):
            return True
    if len(term) < 3 and not has_cjk_ideograph(term):
        return True
    if term.isdigit():
        return True
    if has_local_path_marker(term):
        return True
    return False


def extract_ascii_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", text):
        if not term_is_noise(token):
            terms.append(token)
        if re.search(r"[._-]", token):
            for part in re.split(r"[._-]+", token):
                part = normalize_term(part)
                if len(part) >= 4 and not term_is_noise(part):
                    terms.append(part)
    return terms


def component_aliases(term: str) -> list[str]:
    if not re.search(r"[._-]", term):
        return []
    aliases: list[str] = []
    for part in re.split(r"[._-]+", term):
        part = normalize_term(part)
        if len(part) >= 4 and not term_is_noise(part):
            aliases.append(part)
    return unique_preserve(aliases, limit=6)


def _bump(diagnostics: dict[str, int] | None, key: str) -> None:
    if diagnostics is not None:
        diagnostics[key] = int(diagnostics.get(key) or 0) + 1


def extract_cjk_terms(text: str, *, diagnostics: dict[str, int] | None = None) -> list[str]:
    terms: list[str] = []
    for seq in iter_cjk_sequences(text, min_len=2, max_len=48):
        if source_text_is_noise(seq):
            continue
        for part in re.split(r"[\s，。；：！？、,.!?/|+]+", seq):
            if part and is_low_value_cjk_fragment(part):
                _bump(diagnostics, "cjk_fragment_suppressed_count")
    for phrase in cjk_phrase_candidates(text, max_len=12):
        if not term_is_noise(phrase):
            terms.append(phrase)
            _bump(diagnostics, "salient_cjk_phrase_count")
    boundary_pattern = "|".join(
        re.escape(word) for word in sorted(CJK_BOUNDARY_WORDS, key=len, reverse=True)
    )
    for seq in iter_cjk_sequences(text, min_len=3, max_len=48):
        if source_text_is_noise(seq):
            continue
        for phrase in re.split(boundary_pattern, seq):
            phrase = strip_cjk_deictic_prefix(normalize_term(phrase))
            if 3 <= len(phrase) <= 12:
                if not term_is_noise(phrase):
                    terms.append(phrase)
                elif has_cjk_ideograph(phrase):
                    _bump(diagnostics, "cjk_fragment_suppressed_count")
            if len(phrase) > 12:
                for hint in DURABLE_CJK_HINTS:
                    index = phrase.find(hint)
                    if index < 0:
                        continue
                    start = max(0, index - 4)
                    end = min(len(phrase), index + len(hint) + 2)
                    term = normalize_term(phrase[start:end])
                    if 3 <= len(term) <= 12 and not term_is_noise(term):
                        terms.append(term)
                    elif has_cjk_ideograph(term):
                        _bump(diagnostics, "cjk_fragment_suppressed_count")
    return terms


def term_rank(term: str) -> tuple[int, int, str]:
    cjk_bonus = 3 if has_cjk_ideograph(term) else 0
    durable_bonus = 4 if any(hint in term for hint in DURABLE_CJK_HINTS) else 0
    tech_bonus = 2 if re.search(r"[A-Z][A-Za-z]+|[._-]", term) else 0
    return (durable_bonus + tech_bonus + cjk_bonus, min(len(term), 24), term.casefold())


def extract_terms_from_text(
    text: str,
    *,
    limit: int = DEFAULT_MAX_TERMS_PER_SOURCE,
    diagnostics: dict[str, int] | None = None,
    source_role: str | None = None,
) -> list[str]:
    if not text or source_text_is_noise(text):
        return []
    terms = extract_ascii_terms(text) + extract_cjk_terms(text, diagnostics=diagnostics)
    terms = unique_preserve([term for term in terms if not term_is_noise(term)], limit=None)
    terms.sort(key=term_rank, reverse=True)
    selected = terms[:limit]
    if diagnostics is not None and source_role:
        metric = "user_turn_term_count" if source_role == "user" else "assistant_final_term_count"
        diagnostics[metric] = int(diagnostics.get(metric) or 0) + len(selected)
    aliases: list[str] = []
    for term in selected:
        aliases.extend(component_aliases(term))
    return unique_preserve(selected + aliases, limit=limit + 8)


__all__ = [
    "ASCII_BOUNDARY_CHARS",
    "ascii_term_is_simple",
    "extract_terms_from_text",
    "normalize_term",
    "source_text_is_noise",
    "term_is_noise",
]
