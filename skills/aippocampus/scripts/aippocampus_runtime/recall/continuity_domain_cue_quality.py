"""Foreground cue-quality contract for continuity-domain previews.

Continuity-domain candidates are navigation routes, not source truth. The
preview surface may offer a direct recall command only when the cue is specific
enough to help the next agent reopen source. Keep this policy central so future
noise fixes do not patch only the CLI projection while producer or test
fixtures keep accepting a different broad cue shape.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from aippocampus_runtime.core import compact_text

GENERIC_FOREGROUND_CUE_TERMS = {
    "aippocampus",
    "aiippocampus",
    "sapientropic",
    "ai",
    "codex-hindsight-memory",
    "recall",
    "append",
    "anchor",
    "anchors",
    "锚点",
    "maintenance",
    "runtime",
    "runtime-contract",
    "continuity-domain",
    "continuity",
    "route",
    "clean-source",
    "fresh-thread",
    "source",
    "source-backed",
    "source backed",
    "foreground",
    "action",
    "candidate",
    "candidates",
    "preview",
    "plugin",
    "tool",
    "tools",
    "mcp",
    "github",
    "github.com",
    "http",
    "https",
    "www",
    "comment",
    "comments",
    "agent_callable",
    "agent-callable",
    "issue",
    "issues",
    "main",
    "master",
    "branch",
    "commit",
    "merge",
    "pr",
    "pull",
    "repo",
    "repository",
    "workflow",
    "log",
    "logs",
    "checkin-complete",
    "check-in",
    "user-visible",
    "silent",
    "codeksei",
    "python",
    "f-string",
    "result",
    "result-backstage-only",
    "backstage-only",
    "backstage",
    "macos",
    "deepseek",
    "openai",
    "claude",
    "gemini",
    "gpt",
    "---",
    "public",
    "用户",
    "角度",
    "不是",
    "不过",
    "刚才",
    "刚刚",
    "这个",
    "那个",
    "然后",
    "现在",
    "就是",
    "本机",
    "本地",
    "压缩",
    "结论",
    "真实",
    "本身",
    "感觉",
    "很强",
    "当前状态",
    "判断",
    "状态",
    "公开",
    "更新",
    "他又更新",
    "结果",
    "看法",
    "觉得",
    "设计",
    "实测结果",
}

GENERIC_FOREGROUND_CUE_PHRASES = {
    "runtime-contract.md",
    "old continuity cue",
    "continuity domain candidate",
    "aippocampus maintenance",
    "aippocampus 锚点",
    "github.com",
}

HOSTNAME_OR_DOMAIN_RE = re.compile(r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?")
CLI_FLAG_RE = re.compile(r"-{1,2}[\w][\w.-]*")
MARKDOWN_LINK_FRAGMENT_RE = re.compile(r"\]\(\s*https?")
TIMESTAMP_OR_DATE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[tT\s]\d{1,2}(?::\d{2}){0,2})?"
)
SHORT_TIME_TOKEN_RE = re.compile(r"[tT]\d{1,2}")
LOG_KEY_VALUE_RE = re.compile(r"[a-z][a-z0-9_.-]{1,40}=[a-z0-9_.-]{1,80}")
TERM_STRIP_CHARS = '"`“”‘’.,;:!?，。；：！？()[]{}<>*'


def _cue_tokens(text: str) -> list[str]:
    return [
        token.strip(TERM_STRIP_CHARS)
        for token in re.findall(r"[\w\u4e00-\u9fff.-]+", text.replace("_", "-"))
        if token.strip(TERM_STRIP_CHARS)
    ]


def _is_compound_distinctive_cue(cue: str) -> bool:
    low = cue.strip(TERM_STRIP_CHARS).casefold()
    tokens = _cue_tokens(low)
    non_generic = [token for token in tokens if token not in GENERIC_FOREGROUND_CUE_TERMS]
    if len(non_generic) >= 2:
        return True
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", low)
    return len(cjk_chars) >= 5 and low not in GENERIC_FOREGROUND_CUE_TERMS


def foreground_continuity_domain_cue_quality(cue: str) -> tuple[str, str]:
    """Return ``(quality, suppression_reason)`` for a foreground preview cue.

    ``actionable`` means the preview may emit a recall command. ``low_information``
    means the cue can remain visible as diagnostic/navigation context, but the
    top-level action must broaden the scan or ask for a better user cue.
    """

    text = compact_text(str(cue or ""), 80).strip()
    if not text:
        return "low_information", "empty"
    low = text.strip(TERM_STRIP_CHARS).casefold()
    if MARKDOWN_LINK_FRAGMENT_RE.search(low):
        return "low_information", "markdown_link_fragment"
    if HOSTNAME_OR_DOMAIN_RE.fullmatch(low):
        return "low_information", "hostname_or_domain"
    if TIMESTAMP_OR_DATE_RE.fullmatch(low) or SHORT_TIME_TOKEN_RE.fullmatch(low):
        return "low_information", "timestamp_or_log_time"
    if LOG_KEY_VALUE_RE.fullmatch(low):
        return "low_information", "log_key_value"
    if low in GENERIC_FOREGROUND_CUE_PHRASES:
        return "low_information", "generic_tool_word"
    if low.startswith("-") or CLI_FLAG_RE.fullmatch(low):
        return "low_information", "cli_flag_or_option"
    if low.endswith((".md", ".py", ".json", ".jsonl", ".toml", ".yaml", ".yml")) and " " not in low:
        return "low_information", "file_name_only"
    tokens = _cue_tokens(low)
    if tokens and all(token in GENERIC_FOREGROUND_CUE_TERMS for token in tokens):
        return "low_information", "generic_tool_word"
    if low in GENERIC_FOREGROUND_CUE_TERMS:
        return "low_information", "generic_tool_word"
    return "actionable", ""


def foreground_continuity_domain_candidate_quality(
    *,
    title: str,
    cues: Sequence[str],
) -> tuple[str, str, str]:
    """Return ``(cue, quality, reason)`` for one candidate preview.

    Continuity-domain producer output is noisy by design: it is mining possible
    future navigation routes from broad local history. A foreground recall
    command is allowed only when the candidate exposes at least one distinctive
    cue, not merely because a generic project/provider title happens to sit next
    to a weak judgment word such as "结论" or "真实".
    """

    first_visible = ""
    first_reason = ""
    low_information_seen = 0
    first_actionable: tuple[str, str] | None = None
    for raw in [*cues, title]:
        cue = compact_text(str(raw or ""), 80).strip()
        if not cue:
            continue
        if not first_visible:
            first_visible = cue
        quality, reason = foreground_continuity_domain_cue_quality(cue)
        if quality == "actionable":
            if _is_compound_distinctive_cue(cue):
                return cue, quality, reason
            first_actionable = first_actionable or (cue, reason)
            continue
        low_information_seen += 1
        first_reason = first_reason or reason
    if first_actionable and low_information_seen < 2:
        return first_actionable[0], "actionable", first_actionable[1]
    return (
        first_visible or compact_text(str(title or ""), 80),
        "low_information",
        (
            "generic_dominated_candidate_without_compound_cue"
            if first_actionable
            else first_reason or "generic_candidate_without_distinctive_cue"
        ),
    )
