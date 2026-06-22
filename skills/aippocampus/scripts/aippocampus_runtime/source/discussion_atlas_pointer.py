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
from aippocampus_runtime.contracts import foreground_shell_action, shell_quote

ATLAS_REL_PATH = Path("docs") / "research" / "discussion-atlas.md"
_ROW_RE = re.compile(
    r"^\|\s*\[#(?P<number>\d+)\s+(?P<title>.+?)\]\((?P<url>https://github\.com/[^)]+/discussions/\d+)\)"
    r"\s*\|\s*(?P<layer>[^|]*)\|\s*(?P<status>[^|]*)\|\s*(?P<owner>[^|]*)\|"
    r"\s*(?P<execution>[^|]*)\|\s*(?P<next_action>[^|]*)\|\s*(?P<cannot_claim>[^|]*)\|"
)
_TERM_RE = re.compile(r"[\w#-]+", re.UNICODE)


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
    query_terms = _terms(query)
    number_terms = {int(term) for term in query_terms if term.isdigit()}
    scored: list[tuple[int, int, dict[str, str]]] = []
    for number, row in rows.items():
        haystack_terms = set(
            _terms(
                " ".join(
                    (
                        row.get("title", ""),
                        row.get("owner", ""),
                        row.get("execution", ""),
                        row.get("next_action", ""),
                    )
                )
            )
        )
        overlap = len(set(query_terms) & haystack_terms)
        if number in number_terms:
            overlap += 10
        if overlap:
            scored.append((overlap, number, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    score, number, row = scored[0]
    explicit_number = number in number_terms
    # Do not let broad "discussion" language hijack ordinary search. A title
    # overlap is useful, but one weak shared token is only background context.
    if not explicit_number and score < 2:
        return None
    pointer = {
        "kind": "aippocampus_discussion_atlas_navigation_pointer",
        "status": "atlas_pointer",
        "discussion": number,
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
    action = foreground_shell_action(
        action_id="open_discussion_atlas_pointer",
        label=f"Open Discussion #{pointer.get('discussion')} pointer",
        command=(
            "python tools/aippocampus/docs/discussion_atlas_guard.py "
            f"--pointer-query {shell_quote(query)} --json"
        ),
        why=(
            f"Explicit discussion cue matched {title}; use the atlas pointer before "
            "registry chatter or repo familiarity."
        ),
        mutation_risk="read_only",
        claim_boundary="discussion_atlas_navigation_only_until_external_source_opened",
    )
    action["tool_name"] = "shell"
    action["arguments"] = {
        "discussion": pointer.get("discussion"),
        "url": pointer.get("url"),
    }
    return action
