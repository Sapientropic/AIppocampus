"""Live GitHub issue-state loading for successor evidence sweeps."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from typing import Any


def _parse_parent(body: str) -> int | None:
    match = re.search(r"(?im)^\s*(?:Parent|Umbrella|Predecessor):\s*#(\d+)", body)
    return int(match.group(1)) if match else None


def _closeout_pointer_kind(text: str) -> str:
    lowered = text.casefold()
    if re.search(r"\bpr\s+#\d+", lowered) or re.search(r"#\d+", lowered):
        if any(
            term in lowered
            for term in (
                "artifact",
                "receipt",
                "trace",
                "validation",
                "covered",
                "report",
                "evidence",
            )
        ):
            return "artifact_pointer"
    if any(
        term in lowered
        for term in (
            "artifact",
            "receipt",
            "trace artifact",
            "benchmark smoke",
            "provider artifact",
            "validation was extended",
        )
    ):
        return "artifact_pointer"
    if re.search(r"\b(successor|follow[- ]?up|child)\s+#\d+", lowered):
        return "explicit_deferral_pointer"
    if any(term in lowered for term in ("defer", "deferred", "current blocker", "remains open")):
        return "explicit_deferral_pointer"
    return "none"


def _github_issue_row(item: Mapping[str, Any]) -> dict[str, Any]:
    number = int(item.get("number") or 0)
    labels = [
        str(label.get("name") or "")
        for label in item.get("labels") or []
        if isinstance(label, Mapping)
    ]
    body = str(item.get("body") or "")
    body_parent = _parse_parent(body)
    comment_bodies = [
        str(comment.get("body") or "")
        for comment in item.get("comments") or []
        if isinstance(comment, Mapping)
    ]
    closeout_text = "\n".join([body, *comment_bodies])
    pointer_kind = _closeout_pointer_kind(closeout_text)
    return {
        "state": str(item.get("state") or "").casefold(),
        "title": str(item.get("title") or f"issue {number}"),
        "parent": body_parent,
        "body_parent": body_parent,
        "native_parent": None,
        "parent_relationship_source": "body_parent_fallback" if body_parent else "none",
        "native_sub_issue_numbers": [],
        "labels": labels,
        "closedAt": item.get("closedAt"),
        "closeout_pointer_kind": pointer_kind,
        "closeout_pointer_present": pointer_kind != "none",
        "source": "github_live",
    }


def _repo_owner_name(repo: str | None) -> tuple[str, str]:
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return owner, name
    return "Sapientropic", "AIppocampus"


def _chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _load_native_issue_relationships_via_gh(
    issue_numbers: list[int],
    *,
    repo: str | None = None,
) -> dict[int, dict[str, Any]]:
    owner, name = _repo_owner_name(repo)
    relationships: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(sorted(set(issue_numbers)), 40):
        aliases = "\n".join(
            (
                f"i{number}: issue(number:{number}) {{ "
                "number parent { number } "
                "subIssues(first:100) { totalCount nodes { number } } "
                "}"
            )
            for number in chunk
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
                f"repo={name}",
                "-f",
                f"query={query}",
            ],
            text=True,
            encoding="utf-8",
        )
        data = ((json.loads(payload).get("data") or {}).get("repository") or {})
        for number in chunk:
            node = data.get(f"i{number}")
            if not isinstance(node, Mapping):
                continue
            raw_parent = node.get("parent")
            parent = raw_parent if isinstance(raw_parent, Mapping) else {}
            raw_subissues = node.get("subIssues")
            subissues = raw_subissues if isinstance(raw_subissues, Mapping) else {}
            raw_subissue_nodes = subissues.get("nodes")
            subissue_nodes = raw_subissue_nodes if isinstance(raw_subissue_nodes, list) else []
            native_parent_number = parent.get("number")
            relationships[number] = {
                "native_parent": (
                    int(native_parent_number) if native_parent_number is not None else None
                ),
                "native_sub_issue_numbers": [
                    int(child_number)
                    for child in subissue_nodes
                    if isinstance(child, Mapping)
                    for child_number in [child.get("number")]
                    if child_number is not None
                ],
                "native_sub_issue_count": int(subissues.get("totalCount") or 0),
            }
    return relationships


def load_github_successor_issue_state(
    *,
    declared_issue_numbers: Iterable[int] = (),
    repo: str | None = None,
    min_issue_number: int = 1918,
    limit: int = 200,
) -> dict[int, dict[str, Any]]:
    """Return a GitHub issue-state snapshot for the successor range."""

    command = [
        "gh",
        "issue",
        "list",
        "--state",
        "all",
        "--limit",
        str(limit),
        "--json",
        "number,title,state,closedAt,body,labels",
    ]
    if repo:
        command[2:2] = ["-R", repo]
    payload = subprocess.check_output(command, text=True, encoding="utf-8")
    rows = json.loads(payload)
    result: dict[int, dict[str, Any]] = {}
    for item in rows if isinstance(rows, list) else []:
        number = int(item.get("number") or 0)
        if number < min_issue_number:
            continue
        result[number] = _github_issue_row(item)
    for number in sorted(set(int(item) for item in declared_issue_numbers)):
        if number in result:
            continue
        view_command = [
            "gh",
            "issue",
            "view",
            str(number),
            "--json",
            "number,title,state,closedAt,body,comments,labels",
        ]
        if repo:
            view_command[2:2] = ["-R", repo]
        try:
            item = json.loads(
                subprocess.check_output(view_command, text=True, encoding="utf-8")
            )
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        if isinstance(item, Mapping):
            result[number] = _github_issue_row(item)
    try:
        native = _load_native_issue_relationships_via_gh(sorted(result), repo=repo)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        native = {}
    for number, relationship in native.items():
        row = result.get(number)
        if not row:
            continue
        native_parent = relationship.get("native_parent")
        row["native_parent"] = native_parent
        row["native_sub_issue_numbers"] = relationship.get("native_sub_issue_numbers") or []
        row["native_sub_issue_count"] = relationship.get("native_sub_issue_count") or 0
        if native_parent is not None:
            row["parent"] = native_parent
            row["parent_relationship_source"] = "native_parent_graph"
    return result


__all__ = ["load_github_successor_issue_state"]
