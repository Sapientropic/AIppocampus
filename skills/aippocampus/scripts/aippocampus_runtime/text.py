"""Small text helpers shared across runtime packages."""

from __future__ import annotations

import re

CJK_RECALL_RANGES = "\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002ffff"
CJK_IDEOGRAPH_RE = re.compile(f"[{CJK_RECALL_RANGES}]")
CJK_SEQUENCE_RE = re.compile(f"[{CJK_RECALL_RANGES}]+")

CJK_CONNECTIVE_RE = re.compile(
    r"(?:以及|还有|或者|如果|然后|但是|所以|因为|关于|这个|那个|这些|那些|"
    r"我们|你们|他们|仍按|按照|通过|影响|很多|刚刚|是否|怎么|什么|"
    r"[的了和与或而但在把对给吗呢吧啊]|[、，。；：！？,.!?/|+])"
)

CJK_DEICTIC_PREFIXES = (
    "最早那条",
    "上次那个",
    "之前那个",
    "刚才那个",
    "这次这个",
    "那条",
    "这条",
    "那个",
    "这个",
    "一些",
    "很多",
    "实际都",
    "刚刚",
)

CJK_LOW_VALUE_TERMS = {
    "这个",
    "那个",
    "这些",
    "那些",
    "我们",
    "你们",
    "他们",
    "一下",
    "继续",
    "问题",
    "讨论",
    "事情",
    "东西",
    "办法",
    "帮助",
    "有帮助",
    "刚刚对",
    "事看来",
    "看来",
    "影响",
    "质量",
    "粗糙",
    "迟钝",
    "差劲",
    "不弱",
    "实际",
    "实际都",
    "手动触发",
    "动触发",
    "持手动触发",
    "程保持手动触发",
    "流程保持手动触发",
}

CJK_LOW_VALUE_SUBSTRINGS = (
    "按新流程",
    "新流程保持",
    "保持手动触发",
    "刚刚对你",
    "对你有帮助",
    "有帮助吗",
    "实际都好",
    "都好差劲",
    "基础层粗糙",
    "基础层粗",
    "础层粗糙",
)

CJK_LOW_VALUE_SUFFIXES = (
    "看来",
    "有帮助",
    "有帮助吗",
    "都好差劲",
    "好差劲",
    "粗糙",
    "迟钝",
    "不弱",
)

CJK_LOW_VALUE_PREFIXES = (
    "仍按",
    "按新",
    "影响",
    "很多",
    "刚刚",
    "实际都",
)

CJK_DOMAIN_ANCHORS = {
    "黏菌",
    "机械飞升",
    "基因飞升",
    "联想回忆",
    "探索算法",
    "海马体",
    "小海马体",
    "外置海马体",
    "外置小海马体",
    "未干的地图",
}

CJK_CONTENT_HINTS = {
    "记忆",
    "联想",
    "召回",
    "海马",
    "索引",
    "证据",
    "源头",
    "路线",
    "工程",
    "接口",
    "迁移",
    "账单",
    "算法",
    "图谱",
    "锚点",
    "触发式",
}


def compact_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 5:
        return text[:max_chars]
    separator = " ... "
    available = max_chars - len(separator)
    head = max(1, available // 2)
    tail = max(1, available - head)
    return text[:head].rstrip() + separator + text[-tail:].lstrip()


def has_cjk_ideograph(text: str) -> bool:
    return bool(CJK_IDEOGRAPH_RE.search(str(text or "")))


def cjk_ideograph_count(text: str) -> int:
    return len(CJK_IDEOGRAPH_RE.findall(str(text or "")))


def iter_cjk_sequences(text: str, *, min_len: int = 2, max_len: int = 32) -> list[str]:
    sequences: list[str] = []
    for match in CJK_SEQUENCE_RE.finditer(str(text or "")):
        value = match.group(0)
        if len(value) < min_len:
            continue
        if len(value) <= max_len:
            sequences.append(value)
            continue
        for start in range(0, len(value), max_len):
            chunk = value[start : start + max_len]
            if len(chunk) >= min_len:
                sequences.append(chunk)
    return sequences


def cjk_ngrams(sequence: str, sizes: tuple[int, ...] = (2, 3, 4)) -> list[str]:
    grams: list[str] = []
    for size in sizes:
        if len(sequence) < size:
            continue
        grams.extend(
            sequence[index : index + size] for index in range(0, len(sequence) - size + 1)
        )
    return grams


def normalize_cjk_term(term: str) -> str:
    return re.sub(r"\s+", "", str(term or "")).strip("，。；：！？、,.!?/|+()[]{}<>《》")


def strip_cjk_deictic_prefix(term: str) -> str:
    value = normalize_cjk_term(term)
    changed = True
    while changed:
        changed = False
        for prefix in CJK_DEICTIC_PREFIXES:
            if value.startswith(prefix) and len(value) > len(prefix) + 1:
                value = value[len(prefix) :]
                changed = True
                break
    return value


def is_low_value_cjk_fragment(term: str) -> bool:
    value = strip_cjk_deictic_prefix(term)
    if not value:
        return True
    if value in CJK_DOMAIN_ANCHORS:
        return False
    if value in CJK_LOW_VALUE_TERMS:
        return True
    if len(value) <= 1:
        return True
    if any(marker in value for marker in CJK_LOW_VALUE_SUBSTRINGS):
        return True
    if any(value.startswith(prefix) for prefix in CJK_LOW_VALUE_PREFIXES):
        return True
    if any(value.endswith(suffix) for suffix in CJK_LOW_VALUE_SUFFIXES):
        return True
    if len(value) <= 3 and value.endswith(("的", "了", "吗", "呢", "吧")):
        return True
    return False


def is_distinctive_cjk_anchor(term: str) -> bool:
    value = strip_cjk_deictic_prefix(term)
    if not value or is_low_value_cjk_fragment(value):
        return False
    if value in CJK_DOMAIN_ANCHORS:
        return True
    if 2 <= len(value) <= 8 and any(hint in value for hint in CJK_CONTENT_HINTS):
        return True
    if len(value) == 2:
        # Two-character CJK anchors are accepted only when they are not broad
        # discourse/adjective fragments. This keeps names such as "黏菌" useful
        # without letting "这个/粗糙/迟钝" pass source gates.
        return value not in CJK_LOW_VALUE_TERMS
    return 3 <= len(value) <= 10


def cjk_phrase_candidates(text: str, *, max_len: int = 12) -> list[str]:
    """Return CJK phrase candidates without sliding-window clause shards.

    The foreground and association producers share this boundary because CJK
    fuzzy sidecars are cheap to generate but expensive when they become source
    anchors. The helper keeps exact/domain-like phrases and strips deixis such
    as "最早那条", while template/status fragments remain fuzzy-search-only.
    """

    candidates: list[str] = []
    for phrase in iter_cjk_sequences(text, min_len=2, max_len=64):
        for domain in sorted(CJK_DOMAIN_ANCHORS, key=len, reverse=True):
            if domain in phrase:
                candidates.append(domain)
        for part in CJK_CONNECTIVE_RE.split(phrase):
            value = strip_cjk_deictic_prefix(part)
            if not value or len(value) > max_len:
                continue
            if is_distinctive_cjk_anchor(value):
                candidates.append(value)
    seen: set[str] = set()
    out: list[str] = []
    for value in candidates:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out
