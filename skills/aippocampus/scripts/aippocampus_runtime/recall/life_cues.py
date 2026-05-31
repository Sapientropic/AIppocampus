#!/usr/bin/env python3
"""Life-wide and profile cue catalog for foreground prompt recall."""

from __future__ import annotations

import re

LIFE_WIDE_SCOPE_LABEL_CUES = {
    "personal_reflection": {
        "焦虑",
        "困惑",
        "困扰",
        "摩擦",
        "压力",
        "卡住",
        "感觉",
        "感受",
        "自我",
        "reflection",
        "anxiety",
        "feeling",
        "friction",
        "stress",
        "stuck",
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
        "工作",
        "职场",
        "职业",
        "life",
        "daily",
        "work",
        "career",
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

PROFILE_RECALL_ALIASES = [
    "resume",
    "CV",
    "curriculum vitae",
    "LinkedIn",
    "profile",
    "professional profile",
    "job search",
    "career history",
    "简历",
    "履历",
    "领英",
    "求职",
    "个人资料",
]

PROFILE_RECALL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(你|你们|agent|ai|助手).{0,18}(知道|了解|记得|认识).{0,18}(我|我的).{0,18}(简历|履历|领英|个人资料|求职|resume|cv|linkedin|profile)",
        r"(我|我的|my).{0,10}(简历|履历|领英|个人资料|求职|resume|cv|linkedin|profile)",
        r"(简历|履历|领英|个人资料|求职|resume|cv|linkedin|profile).{0,18}(在你那|你知道|你记得|之前|以前|档案|资料)",
    ]
]


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


def profile_recall_terms(prompt: str) -> list[str]:
    """Return deterministic aliases only for personal-profile prompts.

    This is a narrow foreground fallback for prompts like "你知道我的简历吗".
    It deliberately stays outside the global retrieval alias table: profile
    aliases are privacy-sensitive search routes, not reusable evidence or broad
    semantic truth. Source-backed claims still require the normal clean-source
    evidence path.
    """

    text = str(prompt or "").strip()
    if not text:
        return []
    if not any(pattern.search(text) for pattern in PROFILE_RECALL_PATTERNS):
        return []
    return unique_preserve(PROFILE_RECALL_ALIASES, limit=18)
