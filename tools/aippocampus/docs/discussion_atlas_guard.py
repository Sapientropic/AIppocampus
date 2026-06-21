#!/usr/bin/env python3
"""Public-safe drift guard for the Discussion Atlas."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ATLAS_REL_PATH = "docs/research/discussion-atlas.md"
DISCUSSION_LINK_RE = re.compile(r"\[#(?P<number>\d+)\s+(?P<title>[^\]]+)\]\((?P<url>[^)]*)\)")
ISSUE_REF_RE = re.compile(r"(?<![\w/])#(?P<number>\d+)")
LAST_CHECKED_RE = re.compile(r"(?im)^Last checked:\s*(?P<date>\d{4}-\d{2}-\d{2})")
ATLAS_STATUSES_REQUIRING_TRANSIT = {"active_design", "implemented_slice"}
CHECK_DEPTH_ORDER = [
    "row_presence_only",
    "metadata_transit",
    "issue_state_transit",
    "comment_pointer_review",
]


def parse_discussion_atlas_rows(text: str) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for line in text.splitlines():
        cells = _markdown_cells(line)
        if len(cells) < 7:
            continue
        match = DISCUSSION_LINK_RE.search(cells[0])
        if not match:
            continue
        number = int(match.group("number"))
        rows[number] = {
            "number": str(number),
            "title": match.group("title").strip(),
            "url": match.group("url").strip(),
            "layer": _strip_cell(cells[1]),
            "status": _strip_cell(cells[2]),
            "owner": cells[3].strip(),
            "execution": cells[4].strip(),
            "next_action": cells[5].strip(),
            "cannot_claim": cells[6].strip(),
        }
    return rows


def _markdown_cells(line: str) -> list[str]:
    if not line.lstrip().startswith("|"):
        return []
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _strip_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def _discussion_number(row: Mapping[str, Any]) -> int:
    return int(row.get("number") or 0)


def _atlas_last_checked(text: str) -> date | None:
    match = LAST_CHECKED_RE.search(text)
    if not match:
        return None
    return date.fromisoformat(match.group("date"))


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def _issue_refs(text: str) -> list[int]:
    refs: list[int] = []
    for match in ISSUE_REF_RE.finditer(text):
        number = int(match.group("number"))
        if number not in refs:
            refs.append(number)
    return refs


def _public_atlas_row(row: Mapping[str, str]) -> dict[str, Any]:
    return {
        "discussion": int(row.get("number") or 0),
        "title": row.get("title", ""),
        "url": row.get("url", ""),
        "atlas_layer": row.get("layer", ""),
        "atlas_status": row.get("status", ""),
        "owner": row.get("owner", ""),
        "next_action": row.get("next_action", ""),
        "claim_boundary": "discussion atlas rows are navigation pointers, not source-open evidence",
    }


def _query_terms(query: str) -> list[str]:
    terms = re.findall(r"[\w#-]+", query.casefold())
    return [term.removeprefix("#") for term in terms if len(term.removeprefix("#")) >= 3]


def discussion_atlas_navigation_pointer(atlas_text: str, query: str) -> dict[str, Any]:
    """Return a compact public-safe Discussion pointer for recall/orientation.

    This is deliberately title/URL/owner metadata only. Discussion bodies stay
    outside the atlas so a recall card can orient the agent without pretending
    the row is source-open evidence or a mirrored article.
    """

    rows = parse_discussion_atlas_rows(atlas_text)
    terms = _query_terms(query)
    number_terms = {int(term) for term in terms if term.isdigit()}
    scored: list[tuple[int, int, dict[str, str]]] = []
    for number, row in rows.items():
        title_terms = set(_query_terms(str(row.get("title") or "")))
        owner_terms = set(_query_terms(str(row.get("owner") or "")))
        next_action_terms = set(_query_terms(str(row.get("next_action") or "")))
        overlap = len(set(terms) & (title_terms | owner_terms | next_action_terms))
        if number in number_terms:
            overlap += 10
        if overlap:
            scored.append((overlap, number, row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored:
        return {
            "kind": "aippocampus_discussion_atlas_navigation_pointer",
            "ok": False,
            "status": "no_atlas_pointer",
            "query": query,
            "next_action": "Run discussion_atlas_guard with --live-github or tighten the cue with a discussion number/title.",
            "claim_boundary": "no discussion row surfaced; do not infer source truth from absence",
        }
    _, _, row = scored[0]
    return {
        "kind": "aippocampus_discussion_atlas_navigation_pointer",
        "ok": True,
        "status": "atlas_pointer",
        "query": query,
        "pointer": _public_atlas_row(row),
        "public_boundary": {
            "discussion_body_serialized": False,
            "comment_body_serialized": False,
            "local_paths_serialized": False,
        },
    }


def discussion_atlas_issue_refs(atlas_text: str) -> list[int]:
    refs: list[int] = []
    for row in parse_discussion_atlas_rows(atlas_text).values():
        for number in _issue_refs(row.get("execution", "")):
            if number not in refs:
                refs.append(number)
    return refs


def _issue_state(row: Any) -> str:
    if isinstance(row, Mapping):
        return str(row.get("state") or "").casefold()
    return str(row or "").casefold()


def _execution_has_tracking_artifact(row: Mapping[str, str]) -> bool:
    execution = row.get("execution", "").casefold()
    owner = row.get("owner", "").casefold()
    next_action = row.get("next_action", "").casefold()
    if _issue_refs(execution):
        return True
    artifact_tokens = (
        "test",
        "tests",
        "benchmark",
        "fixture",
        "report",
        "pilot",
        "field report",
        "roadmap",
        "support/q&a",
        "docs-health",
    )
    return any(token in execution for token in artifact_tokens) or ".md" in owner or "archive" in next_action


def _max_check_depth(depths: Sequence[str]) -> str:
    if not depths:
        return "row_presence_only"
    return max(depths, key=lambda item: CHECK_DEPTH_ORDER.index(item))


def discussion_atlas_drift_report(
    atlas_text: str,
    discussions: Sequence[Mapping[str, Any]],
    *,
    issue_state_by_number: Mapping[int, Any] | None = None,
) -> dict[str, Any]:
    atlas_rows = parse_discussion_atlas_rows(atlas_text)
    checked_at = _atlas_last_checked(atlas_text)
    issue_states = {int(key): value for key, value in (issue_state_by_number or {}).items()}
    findings: list[dict[str, Any]] = []
    depths = ["row_presence_only"]
    if discussions:
        depths.append("metadata_transit")
    if issue_state_by_number is not None:
        depths.append("issue_state_transit")
    if any(row.get("latestCommentAt") or row.get("latest_comment_at") for row in discussions):
        depths.append("comment_pointer_review")
    for discussion in discussions:
        number = _discussion_number(discussion)
        if number <= 0:
            continue
        atlas_row = atlas_rows.get(number)
        title = str(discussion.get("title") or f"discussion {number}")
        category = str(discussion.get("github_category") or discussion.get("category") or "")
        pointer = {
            "discussion": number,
            "title": title,
            "url": str(discussion.get("url") or f"https://github.com/Sapientropic/AIppocampus/discussions/{number}"),
            "github_category": category,
            "owner": "discussion_atlas_guard",
            "next_action": "Add or refresh a compact atlas row with owner/evidence metadata; do not mirror the discussion body.",
        }
        if atlas_row is None:
            finding = {**pointer, "code": "missing_row"}
            if checked_at:
                finding["atlas_last_checked"] = checked_at.isoformat()
            findings.append(finding)
            continue
        pointer.update(
            {
                "atlas_layer": atlas_row["layer"],
                "atlas_status": atlas_row["status"],
                "owner": atlas_row["owner"],
                "next_action": atlas_row["next_action"],
            }
        )
        expected_status = discussion.get("expected_status")
        if expected_status and str(expected_status) != atlas_row["status"]:
            findings.append(
                {
                    **pointer,
                    "code": "status_maybe_stale",
                    "atlas_status": atlas_row["status"],
                    "live_status": str(expected_status),
                }
            )
        owner = atlas_row["owner"].casefold()
        if "owner_missing" in owner or owner in {"none", "todo", ""}:
            findings.append({**pointer, "code": "owner_missing"})
        execution = atlas_row["execution"].casefold()
        refs = _issue_refs(atlas_row["execution"])
        if bool(discussion.get("requires_execution_issue")) and (
            execution in {"none", "todo", ""}
            or "issue" not in execution
            and "#" not in execution
        ):
            findings.append({**pointer, "code": "execution_issue_missing"})
        if atlas_row["status"] in ATLAS_STATUSES_REQUIRING_TRANSIT:
            if not _execution_has_tracking_artifact(atlas_row):
                findings.append({**pointer, "code": "active_design_execution_gap"})
            if issue_state_by_number is not None:
                missing_refs = [ref for ref in refs if ref not in issue_states]
                for ref in missing_refs:
                    findings.append(
                        {
                            **pointer,
                            "code": "execution_issue_missing",
                            "issue": ref,
                        }
                    )
                closed_refs = [ref for ref in refs if _issue_state(issue_states.get(ref)) == "closed"]
                open_refs = [ref for ref in refs if _issue_state(issue_states.get(ref)) == "open"]
                if closed_refs and not open_refs and "successor" not in execution and "next" not in execution:
                    findings.append(
                        {
                            **pointer,
                            "code": "successor_missing",
                            "closed_execution_issues": closed_refs,
                        }
                    )
        if bool(discussion.get("closed_execution_needs_successor")) and (
            "successor" not in execution and "next" not in execution
        ):
            findings.append({**pointer, "code": "successor_missing"})
        latest_comment = _parse_datetime(
            discussion.get("latestCommentAt") or discussion.get("latest_comment_at")
        )
        updated = _parse_datetime(discussion.get("updatedAt") or discussion.get("updated_at"))
        latest_pointer = latest_comment or updated
        if checked_at and latest_pointer and latest_pointer.date() > checked_at:
            findings.append(
                {
                    **pointer,
                    "code": "comment_review_needed",
                    "updated_at": latest_pointer.isoformat().replace("+00:00", "Z"),
                    "latest_comment_url": str(
                        discussion.get("latestCommentUrl")
                        or discussion.get("latest_comment_url")
                        or discussion.get("url")
                        or ""
                    ),
                }
            )

    by_code: dict[str, int] = {}
    for finding in findings:
        code = str(finding["code"])
        by_code[code] = by_code.get(code, 0) + 1
    skipped_dimensions = []
    if issue_state_by_number is None:
        skipped_dimensions.append("issue_state_transit")
    if "comment_pointer_review" not in depths:
        skipped_dimensions.append("comment_pointer_review")
    return {
        "kind": "aippocampus_discussion_atlas_drift_report",
        "schema_version": 1,
        "ok": not findings,
        "atlas_discussion_count": len(atlas_rows),
        "live_or_fixture_discussion_count": len(discussions),
        "live_check_depth": _max_check_depth(depths),
        "check_depths": depths,
        "skipped_live_dimensions": skipped_dimensions,
        "issue_state_transit_checked": issue_state_by_number is not None,
        "comment_pointer_review_checked": "comment_pointer_review" in depths,
        "github_category_distinct_from_atlas_layer": True,
        "atlas_last_checked": checked_at.isoformat() if checked_at else "",
        "findings": findings,
        "finding_counts": dict(sorted(by_code.items())),
        "public_boundary": {
            "discussion_bodies_serialized": False,
            "comment_bodies_serialized": False,
            "local_paths_serialized": False,
        },
        "claim_boundary": "discussion rows are navigation pointers, not source truth or current contracts",
    }


def discussion_atlas_static_issues(repo_root: Path) -> list[str]:
    atlas = repo_root / ATLAS_REL_PATH
    if not atlas.exists():
        return [f"missing Discussion Atlas: {ATLAS_REL_PATH}"]
    report = discussion_atlas_drift_report(atlas.read_text(encoding="utf-8"), [])
    if report["atlas_discussion_count"] <= 0:
        return [f"{ATLAS_REL_PATH} has no parseable discussion rows"]
    return []


def load_github_discussions_via_gh(
    *,
    owner: str = "Sapientropic",
    repo: str = "AIppocampus",
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = """
    query($owner:String!, $repo:String!, $limit:Int!) {
      repository(owner:$owner, name:$repo) {
        discussions(first:$limit, orderBy:{field:UPDATED_AT, direction:DESC}) {
          nodes {
            number
            title
            url
            updatedAt
            category { name }
            comments(last:1) {
              totalCount
              nodes {
                createdAt
                updatedAt
                url
              }
            }
          }
        }
      }
    }
    """
    payload = subprocess.check_output(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"owner={owner}",
            "-f",
            f"repo={repo}",
            "-F",
            f"limit={limit}",
            "-f",
            f"query={query}",
        ],
        text=True,
        encoding="utf-8",
    )
    data = json.loads(payload)
    nodes = (((data.get("data") or {}).get("repository") or {}).get("discussions") or {}).get("nodes")
    rows: list[dict[str, Any]] = []
    for node in nodes or []:
        if not isinstance(node, Mapping):
            continue
        raw_category = node.get("category")
        category = raw_category if isinstance(raw_category, Mapping) else {}
        raw_comments = node.get("comments")
        comments = raw_comments if isinstance(raw_comments, Mapping) else {}
        raw_comment_nodes = comments.get("nodes")
        comment_nodes = raw_comment_nodes if isinstance(raw_comment_nodes, list) else []
        latest = comment_nodes[-1] if comment_nodes and isinstance(comment_nodes[-1], Mapping) else {}
        rows.append(
            {
                "number": node.get("number"),
                "title": node.get("title"),
                "url": node.get("url"),
                "github_category": category.get("name"),
                "updatedAt": node.get("updatedAt"),
                "commentCount": comments.get("totalCount"),
                "latestCommentAt": latest.get("updatedAt") or latest.get("createdAt"),
                "latestCommentUrl": latest.get("url"),
            }
        )
    return rows


def load_github_issue_states_via_gh(
    issue_numbers: Sequence[int],
    *,
    owner: str = "Sapientropic",
    repo: str = "AIppocampus",
) -> dict[int, dict[str, Any]]:
    numbers = [int(number) for number in issue_numbers if int(number) > 0]
    if not numbers:
        return {}
    aliases = "\n".join(
        f"i{number}: issue(number:{number}) {{ number title state url }}"
        for number in numbers
    )
    query = f"""
    query($owner:String!, $repo:String!) {{
      repository(owner:$owner, name:$repo) {{
        {aliases}
      }}
    }}
    """
    payload = subprocess.check_output(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"owner={owner}",
            "-f",
            f"repo={repo}",
            "-f",
            f"query={query}",
        ],
        text=True,
        encoding="utf-8",
    )
    data = ((json.loads(payload).get("data") or {}).get("repository") or {})
    states: dict[int, dict[str, Any]] = {}
    for number in numbers:
        node = data.get(f"i{number}")
        if isinstance(node, Mapping):
            states[number] = {
                "number": node.get("number"),
                "title": node.get("title"),
                "state": str(node.get("state") or "").casefold(),
                "url": node.get("url"),
            }
    return states


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--fixture-json", type=Path)
    parser.add_argument("--live-github", action="store_true")
    parser.add_argument("--owner", default="Sapientropic")
    parser.add_argument("--repo", default="AIppocampus")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pointer-query", help="Return a compact atlas pointer for recall/orientation.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    atlas = args.repo_root / ATLAS_REL_PATH
    atlas_text = atlas.read_text(encoding="utf-8")
    if args.pointer_query:
        report = discussion_atlas_navigation_pointer(atlas_text, args.pointer_query)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            if report["ok"]:
                pointer = report["pointer"]
                print(f"discussion #{pointer['discussion']}: {pointer['title']}")
                print(f"url: {pointer['url']}")
                print(f"next: {pointer['next_action']}")
            else:
                print(report["next_action"])
        return 0 if report["ok"] else 1
    if args.live_github:
        discussions = load_github_discussions_via_gh(
            owner=args.owner,
            repo=args.repo,
            limit=args.limit,
        )
        issue_states = load_github_issue_states_via_gh(
            discussion_atlas_issue_refs(atlas_text),
            owner=args.owner,
            repo=args.repo,
        )
    elif args.fixture_json:
        loaded = json.loads(args.fixture_json.read_text(encoding="utf-8"))
        discussions = loaded if isinstance(loaded, list) else loaded.get("discussions", [])
        issue_states = {} if isinstance(loaded, list) else loaded.get("issue_states")
    else:
        discussions = []
        issue_states = None
    report = discussion_atlas_drift_report(
        atlas_text,
        discussions,
        issue_state_by_number=issue_states,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"discussion atlas rows: {report['atlas_discussion_count']}")
        print(f"findings: {len(report['findings'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
