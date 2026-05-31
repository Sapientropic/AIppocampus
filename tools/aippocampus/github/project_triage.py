"""Fill AIppocampus Roadmap Project fields for newly added issues.

This is intentionally rule-based. GitHub Project fields are planning metadata,
not source truth, so the script only infers conservative routing fields from
issue title/body/labels and preserves existing human-edited values.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_PROJECT_OWNER = "Sapientropic"
DEFAULT_PROJECT_NUMBER = 1
DEFAULT_REPOSITORY = "Sapientropic/AIppocampus"

PROJECT_FIELDS = ("Status", "Track", "Kind", "Stage", "Evidence", "Priority", "Source")
SINGLE_SELECT_FIELDS = ("Status", "Track", "Kind", "Stage", "Evidence", "Priority")
TEXT_FIELDS = ("Source",)
REPAIRABLE_MANAGED_FIELDS = ("Track", "Kind", "Stage", "Evidence", "Priority")
REPAIRABLE_STATUS_VALUES = ("Inbox", "Ready", "Archived")

PARENT_TRACK: dict[int, str] = {
    2: "Benchmarks & Research",
    4: "GB/TB scale",
    5: "External models",
    18: "Release verification",
    19: "Public readiness",
    20: "Life-wide memory",
    21: "Sync",
    22: "MCP & Plugin",
    23: "MCP & Plugin",
    158: "Life-wide memory",
    164: "Life-wide memory",
    216: "Benchmarks & Research",
    228: "Benchmarks & Research",
}

PARENT_STAGE: dict[int, str] = {
    2: "Research",
    4: "Cross-stage",
    5: "Stage 6",
    18: "Cross-stage",
    19: "Stage 1",
    20: "Stage 2",
    21: "Stage 3",
    22: "Stage 4",
    23: "Stage 5",
    158: "Research",
    164: "Stage 2",
    216: "Research",
    228: "Research",
}

PARENT_RE = re.compile(r"(?im)^\s*Parent:\s*#(\d+)\b")
EXPLICIT_PRIORITY_LINE_RE = re.compile(
    r"(?im)^\s*(?:priority|prio)\s*[:=-]\s*(P0|P1|P2|Later)\b"
)
TITLE_PRIORITY_RE = re.compile(r"(?i)^\s*\[?(P0|P1|P2|Later)\]?\s*[:\-]\s+")
STAGE_RE = re.compile(r"\bStage\s+([0-7])\b", re.IGNORECASE)
SOURCE_PATH_RE = re.compile(
    r"^(?:\.github|benchmarks|benchmark_corpus|docs|plugins|skills|sources|tests|tools)/"
)
SOURCE_ISSUE_PREFIX_RE = re.compile(r"^GitHub issue #(\d+)\b")


@dataclass(frozen=True)
class IssueContext:
    number: int
    title: str
    body: str
    state: str = "OPEN"
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class TriageResult:
    status: str
    track: str | None
    kind: str | None
    stage: str | None
    evidence: str
    priority: str
    source: str
    confidence: str
    reasons: tuple[str, ...]

    def field_values(self) -> dict[str, str]:
        values: dict[str, str] = {
            "Status": self.status,
            "Evidence": self.evidence,
            "Priority": self.priority,
            "Source": self.source,
        }
        if self.track:
            values["Track"] = self.track
        if self.kind:
            values["Kind"] = self.kind
        if self.stage:
            values["Stage"] = self.stage
        return values


def _text(issue: IssueContext) -> str:
    return f"{issue.title}\n{issue.body}\n{' '.join(issue.labels)}".lower()


def _parents(issue: IssueContext) -> list[int]:
    parents: list[int] = []
    for match in PARENT_RE.finditer(issue.body or ""):
        parents.append(int(match.group(1)))
    return parents


def _contains(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def _normalize_priority(value: str) -> str:
    return "Later" if value.lower() == "later" else value.upper()


def _explicit_priority(issue: IssueContext) -> tuple[str, str] | None:
    for label in issue.labels:
        if label.lower() in {"p0", "p1", "p2", "later"}:
            return _normalize_priority(label), "priority label"

    title_match = TITLE_PRIORITY_RE.search(issue.title or "")
    if title_match:
        return _normalize_priority(title_match.group(1)), "title prefix"

    line_match = EXPLICIT_PRIORITY_LINE_RE.search(issue.body or "")
    if line_match:
        return _normalize_priority(line_match.group(1)), "explicit priority line"

    return None


def _source_issue_number(source: str | None) -> int | None:
    match = SOURCE_ISSUE_PREFIX_RE.search((source or "").strip())
    if not match:
        return None
    return int(match.group(1))


def is_script_managed_current(current: dict[str, str], triage: TriageResult) -> bool:
    """Best-effort guard for repair mode.

    The Project API does not record field provenance, so repair mode only
    touches items whose Source field still looks like this script's generated
    value for the same issue. Human-authored Source values are treated as
    ownership markers and are not repaired.
    """

    current_source = (current.get("Source") or "").strip()
    if not current_source:
        return False

    lowered = current_source.lower()
    if any(marker in lowered for marker in ("manual", "human", "owner", "do not overwrite")):
        return False

    current_issue = _source_issue_number(current_source)
    inferred_issue = _source_issue_number(triage.source)
    if current_issue is None or current_issue != inferred_issue:
        return False

    if "managed-by: project_triage" in lowered:
        return True

    return current.get("Status") in {"Inbox", "Archived"}


def infer_track(issue: IssueContext, parents: list[int]) -> tuple[str | None, str | None]:
    for parent in parents:
        if parent in PARENT_TRACK:
            return PARENT_TRACK[parent], f"parent #{parent}"

    text = _text(issue)
    if _contains(text, "mem0", "zep", "graphiti", "letta", "arc-agi", "benchmark"):
        return "Benchmarks & Research", "benchmark/research keywords"
    if _contains(
        text,
        "topic-epoch",
        "topic epoch",
        "warm ambient",
        "ambient cache",
        "vague recall",
        "question-tracking",
        "question tracking",
        "repo familiarity",
        "decision-shadow",
        "dream",
    ):
        return "Life-wide memory", "memory-continuity keywords"
    if _contains(text, "deepseek", "external model", "provider-neutral", "offline provider", "local/offline"):
        return "External models", "external-model keywords"
    if _contains(text, "cross-device", "object-storage", "object storage", "encrypted sync", " sync "):
        return "Sync", "sync keywords"
    if _contains(text, "mcp", "plugin", "codex client"):
        return "MCP & Plugin", "MCP/plugin keywords"
    if _contains(text, "life-wide", "semantic label", "source-review", "pro-agent", "suppressed-label"):
        return "Life-wide memory", "life-wide keywords"
    if _contains(text, "gb/tb", "multi-gb", "vector", "registry query", "fanout", "index"):
        return "GB/TB scale", "scale/search keywords"
    if _contains(text, "public-readiness", "public install", "release-readiness", "release readiness"):
        return "Public readiness", "public-readiness keywords"
    if _contains(text, "docs cleanup", "archive", "stale doc", "ruff", "subpackages", "compatibility shims"):
        return "Docs cleanup", "docs-cleanup keywords"
    return None, None


def infer_stage(issue: IssueContext, track: str | None, parents: list[int]) -> tuple[str | None, str | None]:
    stage_match = STAGE_RE.search(f"{issue.title}\n{issue.body}")
    if stage_match:
        return f"Stage {stage_match.group(1)}", "explicit stage"

    for parent in parents:
        if parent in PARENT_STAGE:
            return PARENT_STAGE[parent], f"parent #{parent}"

    if track == "Life-wide memory":
        return "Stage 2", "track default"
    if track == "Sync":
        return "Stage 3", "track default"
    if track == "MCP & Plugin":
        if _contains(_text(issue), "distribution", "install", "uninstall", "rollback"):
            return "Stage 5", "plugin distribution keywords"
        return "Stage 4", "track default"
    if track == "External models":
        return "Stage 6", "track default"
    if track == "Benchmarks & Research":
        return "Research", "track default"
    if track in {"GB/TB scale", "Release verification"}:
        return "Cross-stage", "track default"
    if track == "Public readiness":
        return "Stage 1", "track default"
    return None, None


def infer_kind(issue: IssueContext) -> tuple[str | None, str | None]:
    title = issue.title.strip().lower()
    text = _text(issue)

    if title.startswith("umbrella:"):
        return "Umbrella", "title prefix"
    if _contains(
        text,
        "assess ",
        "evaluate whether",
        "feasibility",
        "inspect ",
        "explore",
        "research",
        "arc-agi",
    ):
        return "Research", "research keywords"
    if _contains(text, "hard-negative", "fixture schema", "recall-discrimination runner"):
        return "Implementation", "benchmark implementation keywords"
    if _contains(
        text,
        "anti-circular controls",
        "confidence intervals",
        "lower-bound gates",
        "small-sample",
        "stratified sampling",
        "sparse coverage",
        "trigger controls",
    ):
        return "Smoke", "benchmark-control keywords"
    if _contains(text, "smoke", "validate ", "verification", "scan", "install paths"):
        return "Smoke", "verification keywords"
    if _contains(text, "docs", "document ", "readme", "guide", "taxonomy", "claim-boundary"):
        return "Docs", "docs keywords"
    if _contains(
        text,
        "implement",
        "build",
        "harden",
        "wire",
        "define",
        "protocol",
        "improve",
        "refactor",
        "replace",
        "tighten",
        "redact",
        "prototype",
        "bug",
    ):
        return "Implementation", "implementation keywords"
    return None, None


def infer_priority(issue: IssueContext, track: str | None, kind: str | None) -> tuple[str, str]:
    text = _text(issue)
    explicit = _explicit_priority(issue)
    if explicit:
        return explicit

    if _contains(text, "physical second-machine", "managed cloud", "real object-storage"):
        return "P0", "external sync evidence"
    if _contains(text, "public install", "release-readiness", "public-boundary"):
        return "P0", "public readiness evidence"
    if _contains(text, "source-review failures", "suppressed-label", "high-risk life-wide"):
        return "P0", "life-wide evidence blocker"
    if track == "GB/TB scale" and _contains(text, "content-addressed", "query planner"):
        return "P0", "scale architecture blocker"
    if track == "Release verification":
        return "P0", "release verification umbrella"
    if kind == "Umbrella" and track in {"Public readiness", "Life-wide memory", "MCP & Plugin"}:
        return "P1", "umbrella default"
    if _contains(text, "local/offline", "questionvectorindex", "claim-boundary report", "demo"):
        return "P2", "later implementation slice"
    if _contains(text, "arc-agi"):
        return "Later", "parked research"
    if track:
        return "P1", "track default"
    return "P2", "fallback"


def infer_source(issue: IssueContext, parents: list[int]) -> str:
    source_parts = [f"GitHub issue #{issue.number}"]
    if parents:
        source_parts.append("parent issue #" + ", #".join(str(parent) for parent in parents))

    for line in (issue.body or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        cleaned = stripped[2:].strip().strip("`")
        if not SOURCE_PATH_RE.match(cleaned):
            continue
        if cleaned and cleaned not in source_parts:
            source_parts.append(cleaned)
        if len(source_parts) >= 6:
            break
    return "; ".join(source_parts)


def infer_triage(issue: IssueContext) -> TriageResult:
    parents = _parents(issue)
    reasons: list[str] = []

    track, track_reason = infer_track(issue, parents)
    if track_reason:
        reasons.append(f"track={track_reason}")

    stage, stage_reason = infer_stage(issue, track, parents)
    if stage_reason:
        reasons.append(f"stage={stage_reason}")

    kind, kind_reason = infer_kind(issue)
    if kind_reason:
        reasons.append(f"kind={kind_reason}")

    priority, priority_reason = infer_priority(issue, track, kind)
    reasons.append(f"priority={priority_reason}")

    complete_route = bool(track and kind and stage)
    if issue.state.upper() == "CLOSED":
        status = "Done"
        reasons.append("status=closed")
    elif priority == "Later":
        status = "Archived"
        reasons.append("status=later")
    elif complete_route:
        status = "Ready"
        reasons.append("status=complete route")
    else:
        status = "Inbox"
        reasons.append("status=needs triage")

    confidence = "high" if complete_route else "low"
    return TriageResult(
        status=status,
        track=track,
        kind=kind,
        stage=stage,
        evidence="None",
        priority=priority,
        source=infer_source(issue, parents),
        confidence=confidence,
        reasons=tuple(reasons),
    )


class GitHubProjectClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            GRAPHQL_URL,
            data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github+json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {body}") from exc
        if payload.get("errors"):
            raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))
        return payload["data"]


PROJECT_QUERY = """
query($owner: String!, $number: Int!, $after: String) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      fields(first: 100) {
        nodes {
          ... on ProjectV2Field { id name }
          ... on ProjectV2SingleSelectField { id name options { id name } }
        }
      }
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content {
            __typename
            ... on Issue {
              id
              number
              title
              body
              state
              repository { nameWithOwner }
              labels(first: 50) { nodes { name } }
            }
          }
          fieldValues(first: 50) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""

ISSUE_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      id
      number
      title
      body
      state
      labels(first: 50) { nodes { name } }
    }
  }
}
"""

ADD_ITEM_MUTATION = """
mutation($project: ID!, $content: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
    item { id }
  }
}
"""

SET_SELECT_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: $project
      itemId: $item
      fieldId: $field
      value: {singleSelectOptionId: $option}
    }
  ) { projectV2Item { id } }
}
"""

SET_TEXT_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $text: String!) {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: $project
      itemId: $item
      fieldId: $field
      value: {text: $text}
    }
  ) { projectV2Item { id } }
}
"""


def _field_name(value_node: dict[str, Any]) -> str | None:
    field = value_node.get("field")
    if isinstance(field, dict):
        name = field.get("name")
        if isinstance(name, str):
            return name
    return None


def collect_project(
    client: GitHubProjectClient, project_owner: str, project_number: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    first_project: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        data = client.graphql(
            PROJECT_QUERY,
            {"owner": project_owner, "number": project_number, "after": after},
        )
        project = data["user"]["projectV2"]
        if first_project is None:
            first_project = project
        page = project["items"]
        items.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    if first_project is None:
        raise RuntimeError(f"Project not found: {project_owner}/{project_number}")
    return first_project, items


def project_fields(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for node in project["fields"]["nodes"]:
        if isinstance(node, dict) and isinstance(node.get("name"), str):
            fields[node["name"]] = node
    return fields


def item_field_values(item: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in item["fieldValues"]["nodes"]:
        if not isinstance(node, dict):
            continue
        name = _field_name(node)
        if not name:
            continue
        value = node.get("name") if "name" in node else node.get("text")
        if isinstance(value, str) and value:
            values[name] = value
    return values


def issue_context_from_node(node: dict[str, Any]) -> IssueContext:
    labels = tuple(label["name"] for label in node["labels"]["nodes"] if isinstance(label.get("name"), str))
    return IssueContext(
        number=int(node["number"]),
        title=str(node["title"]),
        body=str(node.get("body") or ""),
        state=str(node.get("state") or "OPEN"),
        labels=labels,
    )


def find_project_item(
    items: list[dict[str, Any]], repo: str, issue_number: int
) -> dict[str, Any] | None:
    for item in items:
        content = item.get("content")
        if not isinstance(content, dict) or content.get("__typename") != "Issue":
            continue
        repository = content.get("repository")
        if (
            isinstance(repository, dict)
            and repository.get("nameWithOwner") == repo
            and int(content["number"]) == issue_number
        ):
            return item
    return None


def fetch_issue(client: GitHubProjectClient, repo: str, issue_number: int) -> tuple[str, IssueContext]:
    owner, name = repo.split("/", 1)
    data = client.graphql(ISSUE_QUERY, {"owner": owner, "repo": name, "number": issue_number})
    issue = data["repository"]["issue"]
    labels = tuple(label["name"] for label in issue["labels"]["nodes"] if isinstance(label.get("name"), str))
    return issue["id"], IssueContext(
        number=int(issue["number"]),
        title=str(issue["title"]),
        body=str(issue.get("body") or ""),
        state=str(issue.get("state") or "OPEN"),
        labels=labels,
    )


def planned_updates(
    current: dict[str, str],
    triage: TriageResult,
    *,
    fill_missing: bool = True,
    repair_managed_fields: bool = False,
) -> dict[str, str]:
    updates: dict[str, str] = {}
    inferred = triage.field_values()
    repair_allowed = (
        repair_managed_fields
        and triage.confidence == "high"
        and is_script_managed_current(current, triage)
    )

    for field, value in inferred.items():
        existing = current.get(field)
        if field == "Status":
            if fill_missing and existing in (None, "", "Inbox") and value:
                updates[field] = value
            elif repair_allowed and existing in REPAIRABLE_STATUS_VALUES and existing != value:
                updates[field] = value
            continue
        if fill_missing and existing in (None, "") and value:
            updates[field] = value
            continue
        if repair_allowed and field in REPAIRABLE_MANAGED_FIELDS and existing != value:
            updates[field] = value
            continue
    return updates


def single_select_option_id(field: dict[str, Any], option_name: str) -> str:
    for option in field.get("options") or []:
        if option.get("name") == option_name:
            return str(option["id"])
    raise RuntimeError(f"Missing option {option_name!r} for field {field.get('name')!r}")


def apply_updates(
    client: GitHubProjectClient,
    project_id: str,
    item_id: str,
    fields: dict[str, dict[str, Any]],
    updates: dict[str, str],
) -> None:
    for field_name, value in updates.items():
        field = fields[field_name]
        if field_name in SINGLE_SELECT_FIELDS:
            option_id = single_select_option_id(field, value)
            client.graphql(
                SET_SELECT_MUTATION,
                {"project": project_id, "item": item_id, "field": field["id"], "option": option_id},
            )
        elif field_name in TEXT_FIELDS:
            client.graphql(
                SET_TEXT_MUTATION,
                {"project": project_id, "item": item_id, "field": field["id"], "text": value},
            )


def triage_item(
    client: GitHubProjectClient,
    project_id: str,
    fields: dict[str, dict[str, Any]],
    item: dict[str, Any],
    *,
    dry_run: bool,
    fill_missing: bool = True,
    repair_managed_fields: bool = False,
) -> dict[str, Any]:
    content = item.get("content")
    if not isinstance(content, dict) or content.get("__typename") != "Issue":
        return {"skipped": "not_issue", "item_id": item.get("id")}
    issue = issue_context_from_node(content)
    triage = infer_triage(issue)
    current = item_field_values(item)
    managed_by_triage = is_script_managed_current(current, triage)
    updates = planned_updates(
        current,
        triage,
        fill_missing=fill_missing,
        repair_managed_fields=repair_managed_fields,
    )
    if updates and not dry_run:
        apply_updates(client, project_id, item["id"], fields, updates)
    return {
        "issue": issue.number,
        "title": issue.title,
        "confidence": triage.confidence,
        "reasons": triage.reasons,
        "current": current,
        "updates": updates,
        "fill_missing": fill_missing,
        "managed_by_triage": managed_by_triage,
        "repair_managed_fields": repair_managed_fields,
        "dry_run": dry_run,
    }


def ensure_issue_item(
    client: GitHubProjectClient,
    project_id: str,
    items: list[dict[str, Any]],
    repo: str,
    issue_number: int,
    *,
    dry_run: bool,
) -> tuple[dict[str, Any] | None, IssueContext]:
    issue_id, issue = fetch_issue(client, repo, issue_number)
    item = find_project_item(items, repo, issue_number)
    if item or dry_run:
        return item, issue
    data = client.graphql(ADD_ITEM_MUTATION, {"project": project_id, "content": issue_id})
    item_id = data["addProjectV2ItemById"]["item"]["id"]
    return {"id": item_id, "content": None, "fieldValues": {"nodes": []}}, issue


def triage_single_issue(
    client: GitHubProjectClient,
    project_id: str,
    fields: dict[str, dict[str, Any]],
    items: list[dict[str, Any]],
    repo: str,
    issue_number: int,
    *,
    dry_run: bool,
    fill_missing: bool = True,
    repair_managed_fields: bool = False,
) -> dict[str, Any]:
    item, issue = ensure_issue_item(client, project_id, items, repo, issue_number, dry_run=dry_run)
    triage = infer_triage(issue)
    current = item_field_values(item) if item else {}
    managed_by_triage = is_script_managed_current(current, triage)
    updates = planned_updates(
        current,
        triage,
        fill_missing=fill_missing,
        repair_managed_fields=repair_managed_fields,
    )
    if item is None:
        updates["_project_item"] = "would_add"
    elif updates and not dry_run:
        apply_updates(client, project_id, item["id"], fields, updates)
    return {
        "issue": issue.number,
        "title": issue.title,
        "confidence": triage.confidence,
        "reasons": triage.reasons,
        "current": current,
        "updates": updates,
        "fill_missing": fill_missing,
        "managed_by_triage": managed_by_triage,
        "repair_managed_fields": repair_managed_fields,
        "dry_run": dry_run,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY))
    parser.add_argument("--project-owner", default=os.environ.get("AIPPOCAMPUS_PROJECT_OWNER", DEFAULT_PROJECT_OWNER))
    parser.add_argument(
        "--project-number",
        type=int,
        default=int(os.environ.get("AIPPOCAMPUS_PROJECT_NUMBER", str(DEFAULT_PROJECT_NUMBER))),
    )
    parser.add_argument("--issue-number", type=int)
    parser.add_argument(
        "--all-missing",
        action="store_true",
        help="Triage all project issues that still miss one or more configured fields.",
    )
    parser.add_argument(
        "--repair-managed-fields",
        action="store_true",
        help=(
            "Repair high-confidence fields that look generated by this script. "
            "Use with --dry-run first to inspect the report."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    token = os.environ.get("AIPPOCAMPUS_PROJECTS_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_token",
                    "message": "Set AIPPOCAMPUS_PROJECTS_TOKEN or GH_TOKEN with GitHub Projects write access.",
                },
                ensure_ascii=False,
            )
        )
        return 2

    client = GitHubProjectClient(token)
    project, items = collect_project(client, args.project_owner, args.project_number)
    fields = project_fields(project)
    missing_fields = [name for name in PROJECT_FIELDS if name not in fields]
    if missing_fields:
        raise RuntimeError(f"Project is missing expected fields: {', '.join(missing_fields)}")

    project_id = project["id"]
    if args.issue_number:
        results = [
            triage_single_issue(
                client,
                project_id,
                fields,
                items,
                args.repo,
                args.issue_number,
                dry_run=args.dry_run,
                fill_missing=True,
                repair_managed_fields=args.repair_managed_fields,
            )
        ]
    elif args.all_missing or args.repair_managed_fields:
        results = []
        for item in items:
            current = item_field_values(item)
            has_missing_fields = any(not current.get(field) for field in PROJECT_FIELDS)
            if not args.all_missing and not args.repair_managed_fields:
                continue
            if not has_missing_fields and not args.repair_managed_fields:
                continue
            result = triage_item(
                client,
                project_id,
                fields,
                item,
                dry_run=args.dry_run,
                fill_missing=args.all_missing,
                repair_managed_fields=args.repair_managed_fields,
            )
            if result["updates"] or (args.all_missing and has_missing_fields):
                results.append(result)
    else:
        raise RuntimeError("Pass --issue-number, --all-missing, or --repair-managed-fields.")

    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
