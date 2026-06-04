"""Deterministic input gate for the question extraction subconscious job."""

from __future__ import annotations

import re
from typing import Any, Mapping

from aippocampus_runtime.core import compact_text

QUESTION_EXTRACTION_IMPLICIT_CUES = (
    "i don't understand",
    "i dont understand",
    "not sure",
    "uncertain",
    "confused",
    "stuck",
    "不明白",
    "不太明白",
    "不确定",
    "困惑",
    "卡住",
    "到底",
    "怎么判断",
)
# `question_extraction` also emits `frontier_marker` rows. Keep explicit
# stopping-signal turns in the model payload so the extraction gate does not
# starve source-backed boundaries while filtering ordinary noise.
QUESTION_EXTRACTION_FRONTIER_CUES = (
    "need external evidence",
    "external evidence before",
    "before claiming",
    "before closing",
    "not solved",
    "unresolved",
    "blocked",
    "deferred",
    "stopping point",
    "外部证据",
    "未解决",
)
QUESTION_EXTRACTION_INTERROGATIVE_CUES = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "which",
    "whether",
    "怎么",
    "为什么",
    "为何",
    "哪里",
    "哪",
    "是否",
)
QUESTION_EXTRACTION_NOISE_KEYS = {"好开干", "收到", "继续", "明白", "了解"}
CODE_BLOCK_RE = re.compile(r"```.*?```", flags=re.DOTALL)
TOOL_INVOCATION_RE = re.compile(
    r"^\s*(python|pytest|pip|uv|npm|pnpm|node|git|gh|cargo|pwsh|powershell|cmd)\b",
    flags=re.IGNORECASE,
)


def question_extraction_token_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text, flags=re.UNICODE))


def question_extraction_code_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 0.0
    code_chars = sum(
        len(re.sub(r"\s+", "", match.group(0))) for match in CODE_BLOCK_RE.finditer(text)
    )
    return code_chars / max(1, len(compact))


def normalized_noise_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold(), flags=re.UNICODE)


def question_extraction_has_question_cue(text: str) -> bool:
    lowered = text.casefold()
    return (
        "?" in text
        or "？" in text
        or any(cue in lowered for cue in QUESTION_EXTRACTION_INTERROGATIVE_CUES)
        or any(cue in lowered for cue in QUESTION_EXTRACTION_IMPLICIT_CUES)
        or any(cue in lowered for cue in QUESTION_EXTRACTION_FRONTIER_CUES)
    )


def question_extraction_skip_reason(turn: Mapping[str, Any]) -> str:
    text = str(turn.get("user") or "").strip()
    if not text:
        return "empty"
    if question_extraction_code_ratio(text) >= 0.80:
        return "code_heavy"
    if normalized_noise_key(text) in QUESTION_EXTRACTION_NOISE_KEYS:
        return "noise"
    if question_extraction_token_count(text) < 5:
        return "too_short"
    if TOOL_INVOCATION_RE.search(text):
        return "noise"
    if not question_extraction_has_question_cue(text):
        return "no_question_cue"
    return ""


def filter_question_extraction_turns(
    turns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    skipped_by_reason: dict[str, int] = {}
    for turn in turns:
        reason = question_extraction_skip_reason(turn)
        if reason:
            skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
            continue
        selected.append(turn)
    return selected, {
        "input_turn_count": len(turns),
        "selected_turn_count": len(selected),
        "skipped_by_reason": skipped_by_reason,
        "selected_user_previews": [
            compact_text(str(turn.get("user") or ""), 120) for turn in selected[:8]
        ],
    }
