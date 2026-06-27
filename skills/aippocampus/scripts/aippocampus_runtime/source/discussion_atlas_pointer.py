"""Public-safe Discussion Atlas foreground pointers.

Discussion rows orient the agent to a public route, but they are not source
truth. Keep this helper deliberately metadata-only so recall/search can prefer
the atlas for explicit discussion cues without serializing discussion bodies or
turning the atlas into evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.command_policy import current_python_script_command
from aippocampus_runtime.contracts import foreground_shell_action, shell_quote

ATLAS_REL_PATH = Path("docs") / "research" / "discussion-atlas.md"
_ROW_RE = re.compile(
    r"^\|\s*\[#(?P<number>\d+)\s+(?P<title>.+?)\]\((?P<url>https://github\.com/[^)]+/discussions/\d+)\)"
    r"\s*\|\s*(?P<layer>[^|]*)\|\s*(?P<status>[^|]*)\|\s*(?P<owner>[^|]*)\|"
    r"\s*(?P<execution>[^|]*)\|\s*(?P<next_action>[^|]*)\|\s*(?P<cannot_claim>[^|]*)\|"
)
_TERM_RE = re.compile(r"[\w#-]+", re.UNICODE)
_LOW_SIGNAL_ATLAS_TERMS = {
    "agent",
    "apw",
    "benchmark",
    "ci",
    "closeout",
    "deepen",
    "dogfood",
    "issue",
    "issues",
    "known",
    "mcp",
    "memory",
    "pr",
    "recall",
    "reopen",
    "search",
    "source",
    "test",
    "tests",
    "tool",
    "tooling",
}


def _repo_root(cwd: str | Path | None) -> Path:
    start = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if (candidate / ATLAS_REL_PATH).is_file():
            return candidate
    return start


def _terms(value: str) -> list[str]:
    terms = []
    seen: set[str] = set()
    for match in _TERM_RE.finditer(str(value or "").casefold()):
        term = match.group(0).removeprefix("#")
        if len(term) < 3 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _distinctive_terms(value: str) -> set[str]:
    return {term for term in _terms(value) if term not in _LOW_SIGNAL_ATLAS_TERMS}


def _explicit_discussion_reference(query: str, number: int) -> bool:
    raw = str(query or "").casefold()
    return bool(
        re.search(rf"(?:discussion|discussions)\s*#?\s*{number}\b", raw)
        or re.search(rf"/discussions/{number}\b", raw)
        or re.search(rf"#\s*{number}\b", raw)
    )


def _row_match_basis(query: str, number: int, row: Mapping[str, str]) -> tuple[str, int]:
    query_terms = _distinctive_terms(query)
    if _explicit_discussion_reference(query, number):
        return "explicit_discussion_reference", 100
    title_terms = _distinctive_terms(row.get("title", ""))
    owner_terms = _distinctive_terms(row.get("owner", ""))
    execution_terms = _distinctive_terms(row.get("execution", ""))
    next_action_terms = _distinctive_terms(row.get("next_action", ""))
    title_overlap = query_terms & title_terms
    public_phrase_overlap = query_terms & (next_action_terms | execution_terms)
    # Owner labels like "agent-native recall facade" are deliberately weak:
    # they describe the atlas row owner, not the user's requested discussion.
    # Only use them as a tiny tie-breaker after a title or public phrase hit.
    owner_overlap = query_terms & owner_terms
    if len(title_overlap) >= 2:
        return "discussion_title_match", 20 + len(title_overlap) * 2 + min(len(owner_overlap), 1)
    if len(public_phrase_overlap) >= 2:
        return "discussion_public_phrase_match", 10 + len(public_phrase_overlap) + min(len(title_overlap), 1)
    return "", 0


def _parse_rows(text: str) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if not match:
            continue
        row = {key: value.strip() for key, value in match.groupdict().items()}
        rows[int(row["number"])] = row
    return rows


def _clean_owner(owner: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", str(owner or "")).strip()


def discussion_atlas_pointer_for_query(
    query: str,
    *,
    cwd: str | Path | None = None,
) -> dict[str, Any] | None:
    root = _repo_root(cwd)
    atlas = root / ATLAS_REL_PATH
    if not atlas.is_file():
        return None
    rows = _parse_rows(atlas.read_text(encoding="utf-8"))
    if not rows:
        return None
    scored: list[tuple[int, int, str, dict[str, str]]] = []
    for number, row in rows.items():
        basis, score = _row_match_basis(query, number, row)
        if basis:
            scored.append((score, number, basis, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    _score, number, basis, row = scored[0]
    pointer = {
        "kind": "aippocampus_discussion_atlas_navigation_pointer",
        "status": "atlas_pointer",
        "discussion": number,
        "match_basis": basis,
        "title": core.compact_text(row.get("title", ""), 120),
        "url": row.get("url", ""),
        "owner": _clean_owner(row.get("owner", "")),
        "next_action": core.compact_text(row.get("next_action", ""), 220),
        "claim_boundary": "discussion_atlas_navigation_only_until_external_source_opened",
        "public_boundary": {
            "discussion_body_serialized": False,
            "comment_body_serialized": False,
            "local_paths_serialized": False,
        },
    }
    return {key: value for key, value in pointer.items() if value not in (None, "", [], {})}


def discussion_atlas_action(
    pointer: Mapping[str, Any] | None,
    *,
    query: str,
) -> dict[str, Any] | None:
    if not isinstance(pointer, Mapping) or pointer.get("status") != "atlas_pointer":
        return None
    title = core.compact_text(str(pointer.get("title") or "discussion atlas row"), 80)
    basis = str(pointer.get("match_basis") or "")
    if basis == "explicit_discussion_reference":
        why = f"Explicit discussion cue matched {title}; open the atlas pointer before relying on it."
    elif basis == "discussion_title_match":
        why = f"Discussion title matched {title}; open the atlas pointer before relying on it."
    else:
        why = f"Discussion atlas public phrase matched {title}; open the atlas pointer before relying on it."
    action = foreground_shell_action(
        action_id="open_discussion_atlas_pointer",
        label=f"Open Discussion #{pointer.get('discussion')} pointer",
        command=current_python_script_command(
            "tools/aippocampus/docs/discussion_atlas_guard.py",
            f"--pointer-query {shell_quote(query)} --json",
        ),
        why=why,
        mutation_risk="read_only",
        claim_boundary="discussion_atlas_navigation_only_until_external_source_opened",
    )
    action["tool_name"] = "shell"
    action["arguments"] = {
        "discussion": pointer.get("discussion"),
        "url": pointer.get("url"),
    }
    return action
