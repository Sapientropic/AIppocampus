#!/usr/bin/env python3
"""Audit AIppocampus issue planning metadata without making noisy changes.

Project triage fills issue-level routing fields during intake. This audit is a
slower roadmap hygiene pass: it reports drift across milestones, source-doc
references, umbrella checklists, recently closed issue evidence, and unresolved
active docs. Repairs stay deliberately narrow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import project_triage
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import project_triage


DEFAULT_REPOSITORY = project_triage.DEFAULT_REPOSITORY
CHECKED_CHILD_RE = re.compile(r"(?m)^(\s*[-*]\s*)\[\s\]\s+(#(?P<number>\d+)\b[^\n]*)$")
ISSUE_REF_RE = re.compile(r"#(\d+)\b")
UNRESOLVED_DOC_RE = re.compile(
    r"\b(Open Questions|Next hardening|Cannot claim|future work|deferred|"
    r"missing proof|not yet implemented)\b",
    re.IGNORECASE,
)
CLOSURE_EVIDENCE_RE = re.compile(
    r"\b(closed by|closes|merged|pull request|pr #|not planned|wontfix|won't fix|"
    r"duplicate|superseded|verification|verified|tests? passed|follow-up #|parent #)\b",
    re.IGNORECASE,
)
DISCUSSION_DOC_REF_RE = re.compile(
    r"(?:^|[\s`'\"(<])(?P<path>docs/[^\s`'\"<>)]+)",
    re.IGNORECASE,
)
DISCUSSION_COMMITMENT_RE = re.compile(
    r"\b(implement|implementation|benchmark|product|roadmap|ship|publish|"
    r"release|public|evidence|install|api|privacy|milestone)\b",
    re.IGNORECASE,
)
IMPLEMENTATION_MAP_RE = re.compile(r"\bimplementation map\b", re.IGNORECASE)


@dataclass(frozen=True)
class IssueSnapshot:
    number: int
    title: str
    body: str = ""
    state: str = "OPEN"
    labels: tuple[str, ...] = ()
    milestone: str | None = None
    comments: tuple[str, ...] = ()
    closed_at: str | None = None

    @property
    def is_closed(self) -> bool:
        return self.state.upper() == "CLOSED"

    @property
    def is_open(self) -> bool:
        return not self.is_closed


@dataclass(frozen=True)
class DiscussionSnapshot:
    number: int
    title: str
    body: str = ""
    category: str = ""
    url: str = ""
    comments: tuple[str, ...] = ()
    node_id: str | None = None

    @property
    def text(self) -> str:
        return "\n".join([self.title, self.body, *self.comments])


def issue_context(issue: IssueSnapshot) -> project_triage.IssueContext:
    return project_triage.IssueContext(
        number=issue.number,
        title=issue.title,
        body=issue.body,
        state=issue.state,
        labels=issue.labels,
        milestone=issue.milestone,
    )


def parse_github_discussion(raw: dict[str, Any]) -> DiscussionSnapshot | None:
    comments: list[str] = []
    raw_comments = raw.get("comments")
    if isinstance(raw_comments, dict):
        nodes = raw_comments.get("nodes") or []
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("body"), str):
                comments.append(node["body"])
    category = raw.get("category")
    category_name = category.get("name") if isinstance(category, dict) else ""
    return DiscussionSnapshot(
        number=int(raw["number"]),
        title=str(raw.get("title") or ""),
        body=str(raw.get("body") or ""),
        category=str(category_name or ""),
        url=str(raw.get("url") or ""),
        comments=tuple(comments),
        node_id=str(raw["id"]) if raw.get("id") else None,
    )


def parse_github_issue(raw: dict[str, Any]) -> IssueSnapshot | None:
    if raw.get("pull_request"):
        return None
    labels: list[str] = []
    for label in raw.get("labels") or []:
        if isinstance(label, dict) and isinstance(label.get("name"), str):
            labels.append(label["name"])
        elif isinstance(label, str):
            labels.append(label)
    milestone = raw.get("milestone")
    milestone_title = None
    if isinstance(milestone, dict) and isinstance(milestone.get("title"), str):
        milestone_title = milestone["title"]
    raw_comments = raw.get("comments_text")
    if not isinstance(raw_comments, list):
        # The REST issues endpoint exposes comments as a count, not bodies.
        raw_comments = []
    comments = tuple(str(comment) for comment in raw_comments)
    return IssueSnapshot(
        number=int(raw["number"]),
        title=str(raw.get("title") or ""),
        body=str(raw.get("body") or ""),
        state=str(raw.get("state") or "OPEN").upper(),
        labels=tuple(labels),
        milestone=milestone_title,
        comments=comments,
        closed_at=str(raw["closed_at"]) if raw.get("closed_at") else None,
    )


def replace_closed_child_checklist(
    body: str, closed_issue_numbers: set[int]
) -> tuple[str, list[dict[str, Any]]]:
    repairs: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        child_number = int(match.group("number"))
        if child_number not in closed_issue_numbers:
            return match.group(0)
        repairs.append(
            {
                "child_issue": child_number,
                "old": match.group(0),
                "new": f"{match.group(1)}[x] {match.group(2)}",
            }
        )
        return f"{match.group(1)}[x] {match.group(2)}"

    return CHECKED_CHILD_RE.sub(replace, body), repairs


def closure_has_evidence(issue: IssueSnapshot) -> bool:
    text = "\n".join([issue.body, *issue.comments])
    return bool(CLOSURE_EVIDENCE_RE.search(text))


def closed_recently(issue: IssueSnapshot, recent_closed_days: int | None) -> bool:
    if not issue.is_closed:
        return False
    if recent_closed_days is None or not issue.closed_at:
        return True
    try:
        closed_at = datetime.fromisoformat(issue.closed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=recent_closed_days)
    return closed_at >= cutoff


def doc_has_owner(rel_path: str, line: str, issues: list[IssueSnapshot]) -> bool:
    open_issue_numbers = {issue.number for issue in issues if issue.is_open}
    if any(int(match.group(1)) in open_issue_numbers for match in ISSUE_REF_RE.finditer(line)):
        return True
    return any(issue.is_open and rel_path in issue.body for issue in issues)


def discussion_issue_refs(discussion: DiscussionSnapshot) -> set[int]:
    return {int(match.group(1)) for match in ISSUE_REF_RE.finditer(discussion.text)}


def discussion_doc_refs(discussion: DiscussionSnapshot) -> set[str]:
    refs: set[str] = set()
    for match in DISCUSSION_DOC_REF_RE.finditer(discussion.text):
        refs.add(match.group("path").rstrip(".,;:").replace("\\", "/"))
    return refs


def discussion_has_implementation_map(discussion: DiscussionSnapshot) -> bool:
    return bool(IMPLEMENTATION_MAP_RE.search(discussion.text))


def issue_title_map(issues: list[IssueSnapshot]) -> dict[int, str]:
    return {issue.number: issue.title for issue in issues}


def implementation_map_comment(
    discussion: DiscussionSnapshot,
    issues: list[IssueSnapshot],
) -> str:
    titles = issue_title_map(issues)
    lines = [
        "Implementation map:",
        "",
        "This Discussion is narrative context; executable work stays in issues.",
    ]
    for issue_number in sorted(discussion_issue_refs(discussion)):
        title = titles.get(issue_number, "linked issue")
        lines.append(f"- #{issue_number} {title}")
    return "\n".join(lines)


def audit_discussions(
    discussions: list[DiscussionSnapshot],
    issues: list[IssueSnapshot],
    *,
    repo_root: Path | None = None,
    generate_discussion_maps: bool = False,
) -> dict[str, Any]:
    safe_repairs: list[dict[str, Any]] = []
    needs_human_review: list[dict[str, Any]] = []

    open_issue_numbers = {issue.number for issue in issues if issue.is_open}
    all_issue_numbers = {issue.number for issue in issues}

    for discussion in discussions:
        issue_refs = discussion_issue_refs(discussion)
        doc_refs = discussion_doc_refs(discussion)
        known_issue_refs = sorted(issue_refs & all_issue_numbers)
        open_owner_refs = sorted(issue_refs & open_issue_numbers)

        if not issue_refs and not doc_refs:
            needs_human_review.append(
                {
                    "kind": "discussion_orphan",
                    "discussion": discussion.number,
                    "title": discussion.title,
                    "category": discussion.category,
                    "message": "discussion has no issue refs and no docs links",
                }
            )

        if (
            not open_owner_refs
            and discussion.category.casefold() in {"ideas", "idea", "evidence", "announcements", "q&a"}
            and DISCUSSION_COMMITMENT_RE.search(discussion.text)
        ):
            needs_human_review.append(
                {
                    "kind": "discussion_unowned_commitment",
                    "discussion": discussion.number,
                    "title": discussion.title,
                    "category": discussion.category,
                    "message": "discussion mentions implementation/product/evidence work without an open issue owner",
                }
            )

        if repo_root:
            for doc_ref in sorted(doc_refs):
                if not (repo_root / doc_ref).exists():
                    needs_human_review.append(
                        {
                            "kind": "discussion_stale_doc_link",
                            "discussion": discussion.number,
                            "title": discussion.title,
                            "doc": doc_ref,
                            "message": "discussion links to a docs path that is missing from the repository",
                        }
                    )

        if len(known_issue_refs) >= 2 and not discussion_has_implementation_map(discussion):
            review_item = {
                "kind": "discussion_missing_implementation_map",
                "discussion": discussion.number,
                "title": discussion.title,
                "issues": known_issue_refs,
                "message": "discussion links several issues but has no compact implementation map comment",
            }
            needs_human_review.append(review_item)
            if generate_discussion_maps:
                safe_repairs.append(
                    {
                        "kind": "add_discussion_implementation_map_comment",
                        "discussion": discussion.number,
                        "discussion_id": discussion.node_id,
                        "title": discussion.title,
                        "body": implementation_map_comment(discussion, issues),
                    }
                )

    return {"safe_repairs": safe_repairs, "needs_human_review": needs_human_review}


def docs_unresolved_hits(repo_root: Path, issues: list[IssueSnapshot]) -> list[dict[str, Any]]:
    docs_dir = repo_root / "docs"
    if not docs_dir.exists():
        return []
    hits: list[dict[str, Any]] = []
    for path in sorted(docs_dir.rglob("*.md")):
        rel_path = path.relative_to(repo_root).as_posix()
        if "archive" in path.relative_to(docs_dir).parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = UNRESOLVED_DOC_RE.search(line)
            if not match:
                continue
            if doc_has_owner(rel_path, line, issues):
                continue
            hits.append(
                {
                    "kind": "docs_unowned_design_hit",
                    "file": rel_path,
                    "line": line_no,
                    "phrase": match.group(1),
                    "message": "active doc has unresolved planning language without an open owner issue",
                }
            )
    return hits


def empty_summary() -> dict[str, int]:
    return {
        "open_without_milestone": 0,
        "inferable_missing_milestone": 0,
        "missing_source_refs": 0,
        "stale_checklist_items": 0,
        "suspicious_recent_closures": 0,
        "docs_unowned_design_hits": 0,
        "orphan_discussions": 0,
        "discussion_unowned_commitments": 0,
        "stale_discussion_links": 0,
        "missing_discussion_maps": 0,
        "safe_repairs": 0,
        "needs_human_review": 0,
        "suggested_followups": 0,
    }


def audit_issues(
    issues: list[IssueSnapshot],
    *,
    milestone_numbers: dict[str, int],
    repo_root: Path | None = None,
    recent_closed_days: int | None = None,
    discussions: list[DiscussionSnapshot] | None = None,
    generate_discussion_maps: bool = False,
) -> dict[str, Any]:
    summary = empty_summary()
    safe_repairs: list[dict[str, Any]] = []
    needs_human_review: list[dict[str, Any]] = []
    suggested_followups: list[dict[str, Any]] = []
    closed_numbers = {issue.number for issue in issues if issue.is_closed}

    for issue in issues:
        triage = project_triage.infer_triage(issue_context(issue))

        if issue.is_open and not issue.milestone:
            summary["open_without_milestone"] += 1
            milestone_update = project_triage.planned_milestone_update(
                issue_context(issue),
                triage,
                milestone_numbers,
            )
            if triage.milestone:
                summary["inferable_missing_milestone"] += 1
            if triage.confidence == "high" and milestone_update.get("milestone_number"):
                safe_repairs.append(
                    {
                        "kind": "assign_milestone",
                        "issue": issue.number,
                        "title": issue.title,
                        "milestone": triage.milestone,
                        "milestone_number": milestone_update["milestone_number"],
                        "reason": next(
                            (reason for reason in triage.reasons if reason.startswith("milestone=")),
                            "milestone=inferred",
                        ),
                    }
                )
            elif triage.milestone:
                needs_human_review.append(
                    {
                        "kind": "missing_milestone",
                        "issue": issue.number,
                        "title": issue.title,
                        "planned": triage.milestone,
                        "reason": milestone_update.get("error", "not_safe_to_apply"),
                    }
                )

        for warning in triage.warnings:
            summary["missing_source_refs"] += 1
            needs_human_review.append(
                {
                    "kind": "missing_source_docs",
                    "issue": issue.number,
                    "title": issue.title,
                    "warning": warning,
                }
            )

        updated_body, checklist_repairs = replace_closed_child_checklist(issue.body, closed_numbers)
        if checklist_repairs:
            summary["stale_checklist_items"] += len(checklist_repairs)
            safe_repairs.append(
                {
                    "kind": "check_closed_child",
                    "issue": issue.number,
                    "title": issue.title,
                    "child_issue": checklist_repairs[0]["child_issue"],
                    "child_issues": [repair["child_issue"] for repair in checklist_repairs],
                    "updated_body": updated_body,
                }
            )

        if closed_recently(issue, recent_closed_days) and not closure_has_evidence(issue):
            summary["suspicious_recent_closures"] += 1
            needs_human_review.append(
                {
                    "kind": "weak_closed_issue_evidence",
                    "issue": issue.number,
                    "title": issue.title,
                    "message": "closed issue has no obvious PR, test, not-planned, duplicate, or follow-up evidence",
                }
            )

    if repo_root:
        doc_hits = docs_unresolved_hits(repo_root, issues)
        summary["docs_unowned_design_hits"] = len(doc_hits)
        needs_human_review.extend(doc_hits)

    if discussions:
        discussion_report = audit_discussions(
            discussions,
            issues,
            repo_root=repo_root,
            generate_discussion_maps=generate_discussion_maps,
        )
        safe_repairs.extend(discussion_report["safe_repairs"])
        needs_human_review.extend(discussion_report["needs_human_review"])
        summary["orphan_discussions"] = sum(
            1 for item in discussion_report["needs_human_review"] if item["kind"] == "discussion_orphan"
        )
        summary["discussion_unowned_commitments"] = sum(
            1
            for item in discussion_report["needs_human_review"]
            if item["kind"] == "discussion_unowned_commitment"
        )
        summary["stale_discussion_links"] = sum(
            1
            for item in discussion_report["needs_human_review"]
            if item["kind"] == "discussion_stale_doc_link"
        )
        summary["missing_discussion_maps"] = sum(
            1
            for item in discussion_report["needs_human_review"]
            if item["kind"] == "discussion_missing_implementation_map"
        )

    summary["safe_repairs"] = len(safe_repairs)
    summary["needs_human_review"] = len(needs_human_review)
    summary["suggested_followups"] = len(suggested_followups)
    return {
        "ok": True,
        "summary": summary,
        "safe_repairs": safe_repairs,
        "needs_human_review": needs_human_review,
        "suggested_followups": suggested_followups,
    }


def load_issues_file(path: Path) -> tuple[list[IssueSnapshot], dict[str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw_issues = payload
        milestone_numbers: dict[str, int] = {}
    else:
        raw_issues = payload.get("issues") or []
        milestone_numbers = {
            str(key): int(value) for key, value in (payload.get("milestone_numbers") or {}).items()
        }
    issues = [issue for raw in raw_issues if (issue := parse_github_issue(raw))]
    return issues, milestone_numbers


DISCUSSIONS_QUERY = """
query($owner: String!, $repo: String!, $after: String) {
  repository(owner: $owner, name: $repo) {
    discussions(first: 100, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        id
        number
        title
        body
        url
        category { name }
        comments(first: 50) { nodes { body } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def fetch_repo_discussions(
    client: project_triage.GitHubProjectClient,
    repo: str,
) -> list[DiscussionSnapshot]:
    owner, name = repo.split("/", 1)
    discussions: list[DiscussionSnapshot] = []
    after: str | None = None
    while True:
        data = client.graphql(DISCUSSIONS_QUERY, {"owner": owner, "repo": name, "after": after})
        page = data["repository"]["discussions"]
        for raw in page["nodes"]:
            if isinstance(raw, dict) and (discussion := parse_github_discussion(raw)):
                discussions.append(discussion)
        if not page["pageInfo"]["hasNextPage"]:
            return discussions
        after = page["pageInfo"]["endCursor"]


def fetch_repo_issues(client: project_triage.GitHubProjectClient, repo: str) -> list[IssueSnapshot]:
    issues: list[IssueSnapshot] = []
    quoted_repo = urllib.parse.quote(repo, safe="/")
    page = 1
    while True:
        path = f"/repos/{quoted_repo}/issues?state=all&per_page=100&page={page}"
        payload = client.rest("GET", path)
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected GitHub issues response")
        parsed = [issue for raw in payload if isinstance(raw, dict) and (issue := parse_github_issue(raw))]
        issues.extend(parsed)
        if len(payload) < 100:
            return issues
        page += 1


def apply_safe_repairs(
    client: project_triage.GitHubProjectClient,
    repo: str,
    repairs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    quoted_repo = urllib.parse.quote(repo, safe="/")
    for repair in repairs:
        applied_repair = dict(repair)
        try:
            if repair.get("kind") == "assign_milestone":
                milestone_update = {
                    "planned": repair.get("milestone"),
                    "milestone_number": repair.get("milestone_number"),
                }
                project_triage.apply_milestone_update(
                    client,
                    repo,
                    int(repair["issue"]),
                    milestone_update,
                )
                applied_repair.update(milestone_update)
            elif repair.get("kind") == "check_closed_child":
                path = f"/repos/{quoted_repo}/issues/{int(repair['issue'])}"
                client.rest("PATCH", path, {"body": repair["updated_body"]})
            elif repair.get("kind") == "add_discussion_implementation_map_comment":
                discussion_id = repair.get("discussion_id")
                if not isinstance(discussion_id, str) or not discussion_id:
                    applied_repair["skipped"] = "missing_discussion_id"
                else:
                    client.graphql(
                        """
                        mutation($discussion: ID!, $body: String!) {
                          addDiscussionComment(input: {discussionId: $discussion, body: $body}) {
                            comment { id }
                          }
                        }
                        """,
                        {"discussion": discussion_id, "body": repair["body"]},
                    )
            else:
                applied_repair["skipped"] = "unsupported_repair"
        except project_triage.GitHubRestError as exc:
            applied_repair["skipped"] = "permission_denied" if exc.status == 403 else "rest_error"
            applied_repair["error"] = exc.body
        except Exception as exc:
            applied_repair["skipped"] = "graphql_error"
            applied_repair["error"] = str(exc)
        applied.append(applied_repair)
    return applied


def markdown_summary(report: dict[str, Any]) -> str:
    lines = ["# AIppocampus planning audit", "", "## Summary", ""]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Safe repairs", ""])
    for item in report["safe_repairs"][:20]:
        lines.append(f"- {item['kind']}: #{item.get('issue')}")
    if not report["safe_repairs"]:
        lines.append("- none")
    lines.extend(["", "## Needs human review", ""])
    for item in report["needs_human_review"][:30]:
        target = f"#{item['issue']}" if "issue" in item else item.get("file", "docs")
        lines.append(f"- {item['kind']}: {target}")
    if not report["needs_human_review"]:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--issues-file", type=Path, help="Offline issue fixture JSON for dry-run audits.")
    parser.add_argument("--discussions-file", type=Path, help="Offline Discussion fixture JSON.")
    parser.add_argument("--skip-discussions", action="store_true", help="Audit issues/docs only.")
    parser.add_argument("--recent-closed-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true", help="Do not apply safe repairs.")
    parser.add_argument("--repair", action="store_true", help="Apply only safe repairs.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown-summary", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    client = None
    discussions: list[DiscussionSnapshot] = []
    if args.issues_file:
        issues, milestone_numbers = load_issues_file(args.issues_file)
        if args.discussions_file:
            raw_discussions = json.loads(args.discussions_file.read_text(encoding="utf-8"))
            if isinstance(raw_discussions, dict):
                raw_discussions = raw_discussions.get("discussions") or []
            discussions = [
                discussion
                for raw in raw_discussions
                if isinstance(raw, dict) and (discussion := parse_github_discussion(raw))
            ]
    else:
        token = os.environ.get("AIPPOCAMPUS_PROJECTS_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "missing_token",
                        "message": "Set AIPPOCAMPUS_PROJECTS_TOKEN or GH_TOKEN for planning audit.",
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        client = project_triage.GitHubProjectClient(token)
        issues = fetch_repo_issues(client, args.repo)
        milestone_numbers = project_triage.open_milestone_numbers(client, args.repo)
        if not args.skip_discussions:
            try:
                discussions = fetch_repo_discussions(client, args.repo)
            except Exception as exc:
                discussions = []
                print(f"::warning::Discussion audit unavailable: {exc}", file=sys.stderr)

    report = audit_issues(
        issues,
        milestone_numbers=milestone_numbers,
        repo_root=args.repo_root,
        recent_closed_days=args.recent_closed_days,
        discussions=discussions,
        generate_discussion_maps=args.repair and not args.dry_run,
    )
    if args.repair and not args.dry_run:
        if client is None:
            token = os.environ.get("AIPPOCAMPUS_PROJECTS_TOKEN") or os.environ.get("GH_TOKEN")
            if not token:
                raise RuntimeError("Repair mode requires AIPPOCAMPUS_PROJECTS_TOKEN or GH_TOKEN")
            client = project_triage.GitHubProjectClient(token)
        report["applied_repairs"] = apply_safe_repairs(client, args.repo, report["safe_repairs"])
    else:
        report["applied_repairs"] = []

    if args.markdown_summary:
        args.markdown_summary.write_text(markdown_summary(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown_summary(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
