"""Deterministic scope labels for clean-source navigation."""

from __future__ import annotations

import re

SCOPE_LABEL_ORDER = (
    "personal_reflection",
    "relationship_continuity",
    "reading_notes",
    "idea_seed",
    "preference",
    "life_context",
    "technical_work",
    "open_question",
)

# Keep this list for explicit, low-risk lexical cues only. Fuzzy judgments such
# as "this metaphor feels pivotal" or "this dissatisfaction matters" belong in
# the DeepSeek/subconscious `semantic_scope_labeling` sidecar, not here; otherwise
# the deterministic layer slowly turns into an unreviewable phrase list.
SCOPE_LABEL_RULES: dict[str, tuple[str, ...]] = {
    "personal_reflection": (
        "我在想",
        "我觉得",
        "我感觉",
        "我意识到",
        "我总是",
        "焦虑",
        "困惑",
        "害怕",
        "怀疑",
        "reflection",
        "reflecting",
        "anxiety",
        "doubt",
    ),
    "relationship_continuity": (
        "上次",
        "之前聊",
        "继续",
        "长期陪伴",
        "长期连续",
        "长期关系",
        "记得",
        "旧线程",
        "old thread",
        "continuity",
        "relationship",
        "catch up",
        "continue",
    ),
    "reading_notes": (
        "读到",
        "读了",
        "文章",
        "论文",
        "书里",
        "摘录",
        "reading",
        "read this",
        "article",
        "paper",
        "quote",
    ),
    "idea_seed": (
        "点子",
        "想法",
        "灵感",
        "可以做",
        "脑洞",
        "idea",
        "seed",
        "spark",
        "sparks",
        "prototype",
    ),
    "preference": (
        "偏好",
        "我喜欢",
        "我不喜欢",
        "更喜欢",
        "不要",
        "希望你",
        "默认",
        "prefer",
        "preference",
    ),
    "life_context": (
        "最近",
        "今天",
        "昨天",
        "生活",
        "家里",
        "睡眠",
        "身体",
        "长期问题",
        "adhd",
        "lately",
        "today",
        "yesterday",
        "life",
        "sleep",
    ),
    "technical_work": (
        "aippocampus",
        "clean source",
        "mcp",
        "plugin",
        "codex",
        "typescript",
        "rust",
        "python",
        "repo",
        "repository",
        "cli",
        "api",
        "roadmap",
        "代码",
        "测试",
        "脚本",
        "仓库",
        "插件",
        "文档",
    ),
}

ASCII_NEEDLE_RE = re.compile(r"^[a-z0-9_+-]+$")


def _scope_needle_matches(lowered_text: str, needle: str) -> bool:
    lowered_needle = needle.casefold()
    if ASCII_NEEDLE_RE.match(lowered_needle):
        return (
            re.search(rf"(?<![a-z0-9_+-]){re.escape(lowered_needle)}(?![a-z0-9_+-])", lowered_text)
            is not None
        )
    return lowered_needle in lowered_text


def _looks_like_open_question(text: str) -> bool:
    stripped = str(text or "").strip()
    if stripped.endswith(("?", "？")):
        return True
    return (
        re.match(
            r"^(why|how|what|when|where|who|which|can i|could i|should i|do i|does|is|are|am)\b",
            stripped.casefold(),
        )
        is not None
    )


def infer_scope_labels(text: str) -> list[str]:
    """Return conservative life-wide navigation labels for visible text.

    These labels are deterministic hints for filtering and timeline sidecars,
    not model claims about the user's interior state. Keep the rules explicit
    and source-backed so future semantic classifiers can be compared against
    the same clean text instead of replacing it.
    """

    lowered = str(text or "").casefold()
    labels: list[str] = []
    for label in SCOPE_LABEL_ORDER:
        if label == "open_question":
            if _looks_like_open_question(text):
                labels.append(label)
            continue
        needles = SCOPE_LABEL_RULES.get(label, ())
        if any(_scope_needle_matches(lowered, needle) for needle in needles):
            labels.append(label)
    return labels


def merge_scope_labels(items: list[dict]) -> list[str]:
    present = {
        label
        for item in items
        for label in item.get("scope_labels", [])
        if label in SCOPE_LABEL_ORDER
    }
    return [label for label in SCOPE_LABEL_ORDER if label in present]
