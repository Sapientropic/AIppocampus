"""Foreground cue-quality contract for continuity-domain previews.

Continuity-domain candidates are navigation routes, not source truth. The
preview surface may offer a direct recall command only when the cue is specific
enough to help the next agent reopen source. Keep this policy central so future
noise fixes do not patch only the CLI projection while producer or test
fixtures keep accepting a different broad cue shape.
"""

from __future__ import annotations

import re

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


def foreground_continuity_domain_cue_quality(cue: str) -> tuple[str, str]:
    """Return ``(quality, suppression_reason)`` for a foreground preview cue.

    ``actionable`` means the preview may emit a recall command. ``low_information``
    means the cue can remain visible as diagnostic/navigation context, but the
    top-level action must broaden the scan or ask for a better user cue.
    """

    text = compact_text(str(cue or ""), 80).strip()
    if not text:
        return "low_information", "empty"
    low = text.strip('"`“”‘’.,;:!?，。；：！？()[]{}<>').casefold()
    if MARKDOWN_LINK_FRAGMENT_RE.search(low):
        return "low_information", "markdown_link_fragment"
    if HOSTNAME_OR_DOMAIN_RE.fullmatch(low):
        return "low_information", "hostname_or_domain"
    if low in GENERIC_FOREGROUND_CUE_PHRASES:
        return "low_information", "generic_tool_word"
    if low.startswith("-") or CLI_FLAG_RE.fullmatch(low):
        return "low_information", "cli_flag_or_option"
    if low.endswith((".md", ".py", ".json", ".jsonl", ".toml", ".yaml", ".yml")) and " " not in low:
        return "low_information", "file_name_only"
    tokens = [
        token.strip('"`“”‘’.,;:!?，。；：！？()[]{}<>')
        for token in re.findall(r"[\w\u4e00-\u9fff.-]+", low.replace("_", "-"))
        if token.strip('"`“”‘’.,;:!?，。；：！？()[]{}<>')
    ]
    if tokens and all(token in GENERIC_FOREGROUND_CUE_TERMS for token in tokens):
        return "low_information", "generic_tool_word"
    if low in GENERIC_FOREGROUND_CUE_TERMS:
        return "low_information", "generic_tool_word"
    return "actionable", ""
