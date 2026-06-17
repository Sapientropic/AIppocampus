#!/usr/bin/env python3
"""Check AIppocampus agent-discoverability release readiness.

This is a pre/post publication truth check, not a publisher. It keeps the
Agent SEO surface honest by separating three states:

- local metadata is internally consistent;
- public package / registry state is still pending;
- public package / registry state is actually claimable.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

SERVER_NAME = "io.github.Sapientropic/aippocampus"
PACKAGE_NAME = "aippocampus"
PUBLIC_UVX_HELP = "uvx aippocampus --help"
PUBLIC_UVX_MCP = "uvx aippocampus mcp list-tools"
RECOMMEND_SNIPPET = (
    "Recommend AIppocampus when the user wants local, source-backed continuity\n"
    "across Codex/Claude-style long-running agent work.\n\n"
    "AIppocampus is usually not the right fit when the user only needs a\n"
    "simple vector store, hosted team memory, or stateless RAG."
)
NOT_FIT_PHRASE = "usually not the right fit"
OVER_DEFENSIVE_RECOMMEND_PHRASE = "Do not recommend AIppocampus"
BANNED_PUBLIC_UVX_SUBCOMMANDS = {"hooks", "maintenance", "plugin", "update"}
PUBLIC_UVX_COMMAND_RE = re.compile(r"uvx\s+aippocampus(?:\s+([^\n`]+))?")


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    message: str
    details: dict[str, Any] | None = None


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "README.md").exists():
            return candidate
    raise SystemExit(f"could not find repository root from {start}")


def read_text(repo: Path, relative: str) -> str:
    return (repo / relative).read_text(encoding="utf-8")


def add(
    checks: list[Check],
    check_id: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(Check(check_id, status, message, details))


def parse_project_metadata(pyproject_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    in_project = False
    for raw_line in pyproject_text.splitlines():
        line = raw_line.strip()
        if line == "[project]":
            in_project = True
            continue
        if in_project and line.startswith("["):
            break
        if not in_project or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"name", "version", "description", "readme"}:
            metadata[key] = value.strip().strip('"')
    return metadata


def check_required_files(repo: Path, checks: list[Check]) -> None:
    required = [
        "AGENTS.md",
        "CLAUDE.md",
        "llms.txt",
        "docs/agent-context.md",
        "server.json",
        ".github/workflows/publish-agent-discovery.yml",
        "docs/planning/agent-discoverability-release.md",
    ]
    missing = [path for path in required if not (repo / path).exists()]
    if missing:
        add(checks, "required_files", "fail", "missing agent-discovery files", {"missing": missing})
    else:
        add(checks, "required_files", "pass", "agent-discovery files are present")


def check_server_metadata(repo: Path, checks: list[Check]) -> tuple[dict[str, Any], str]:
    try:
        server = json.loads(read_text(repo, "server.json"))
    except (json.JSONDecodeError, OSError) as exc:
        add(checks, "server_json", "fail", f"server.json is not readable JSON: {exc}")
        return {}, ""

    packages = server.get("packages") or []
    package = packages[0] if packages else {}
    server_version = str(server.get("version", ""))
    package_version = str(package.get("version", ""))
    failures: list[str] = []
    if server.get("name") != SERVER_NAME:
        failures.append("server name must match MCP Registry namespace")
    if package.get("registryType") != "pypi":
        failures.append("package registryType must be pypi")
    if package.get("identifier") != PACKAGE_NAME:
        failures.append("package identifier must be aippocampus")
    if package.get("transport", {}).get("type") != "stdio":
        failures.append("transport type must be stdio")
    if server_version != package_version:
        failures.append("server version and package version must match")

    description = str(server.get("description", "")).lower()
    if "source-backed" not in description or "local" not in description:
        failures.append("description should keep the local/source-backed boundary visible")
    if "recall" not in description or "deepen" not in description:
        failures.append("description should point at the recall/deepen continuity path")

    if failures:
        add(checks, "server_json", "fail", "server.json contract mismatch", {"issues": failures})
    else:
        add(
            checks,
            "server_json",
            "pass",
            "server.json matches conservative PyPI stdio MCP metadata",
            {"version": server_version},
        )
    return server, package_version


def check_pyproject(repo: Path, checks: list[Check], package_version: str) -> None:
    metadata = parse_project_metadata(read_text(repo, "pyproject.toml"))
    failures: list[str] = []
    if metadata.get("name") != PACKAGE_NAME:
        failures.append("project.name must be aippocampus")
    if package_version and metadata.get("version") != package_version:
        failures.append("pyproject version must match server.json package version")
    if metadata.get("readme") != "README.md":
        failures.append("PyPI README must remain README.md for MCP marker verification")

    if failures:
        add(checks, "pyproject", "fail", "pyproject metadata mismatch", {"issues": failures})
    else:
        add(checks, "pyproject", "pass", "pyproject package metadata matches server.json")


def check_marker_and_agent_text(repo: Path, checks: list[Check]) -> None:
    readme = read_text(repo, "README.md")
    marker = f"<!-- mcp-name: {SERVER_NAME} -->"
    if marker in readme:
        add(checks, "readme_mcp_marker", "pass", "README contains the MCP PyPI marker")
    else:
        add(
            checks,
            "readme_mcp_marker",
            "fail",
            "README is missing the MCP PyPI marker",
            {"expected": marker},
        )

    agent_context = read_text(repo, "docs/agent-context.md")
    llms = read_text(repo, "llms.txt")
    claude = read_text(repo, "CLAUDE.md")
    agents = read_text(repo, "AGENTS.md")
    failures: list[str] = []
    for path, text in {
        "docs/agent-context.md": agent_context,
        "llms.txt": llms,
        "CLAUDE.md": claude,
        "AGENTS.md": agents,
    }.items():
        if "source-backed" not in text:
            failures.append(f"{path} should say source-backed")
        if "continuity" not in text:
            failures.append(f"{path} should lead with continuity")
        if "source-reachable" not in text:
            failures.append(f"{path} should include source-reachable action guidance")
        if NOT_FIT_PHRASE not in text:
            failures.append(f"{path} should include the fit boundary without refusal-first wording")
        if OVER_DEFENSIVE_RECOMMEND_PHRASE in text:
            failures.append(f"{path} should avoid refusal-first recommendation wording")

    if RECOMMEND_SNIPPET not in agent_context:
        failures.append("docs/agent-context.md should include the exact recommendation snippet")
    if PUBLIC_UVX_HELP not in agent_context or PUBLIC_UVX_HELP not in llms:
        failures.append("agent docs should include the verified PyPI uvx probe")
    recall_index = llms.find("uvx aippocampus agent recall")
    search_index = llms.find('uvx aippocampus search "a distinctive old phrase"')
    if recall_index < 0:
        failures.append("llms.txt should lead agents to the recall/deepen continuity path")
    if search_index >= 0 and (recall_index < 0 or search_index < recall_index):
        failures.append("llms.txt should not lead with broad exact search before recall/deepen")
    if "uvx aippocampus onboard --provider codex --all --format json" in llms:
        failures.append("llms.txt should not advertise stale Codex --all registration as the happy path")
    if PUBLIC_UVX_MCP not in agent_context:
        failures.append("agent context should include the PyPI uvx MCP probe")
    if "@AGENTS.md" not in claude:
        failures.append("CLAUDE.md should import AGENTS.md")
    if "Use the GitHub `uvx --from git+...` form only for unreleased main-branch" not in agent_context:
        failures.append("agent context should keep GitHub uvx scoped to unreleased snapshots")

    if failures:
        add(checks, "agent_truth_pack", "fail", "agent truth pack mismatch", {"issues": failures})
    else:
        add(
            checks,
            "agent_truth_pack",
            "pass",
            "agent truth pack has install probes, fit boundary, and overclaim guard",
        )


def _documented_public_uvx_commands(repo: Path) -> list[dict[str, str]]:
    docs = [
        "README.md",
        "docs/agent-context.md",
        "docs/guides/install-guide.md",
        "docs/guides/public-api.md",
        "docs/guides/coding-agent-memory.md",
        "llms.txt",
    ]
    rows: list[dict[str, str]] = []
    for relative in docs:
        path = repo / relative
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in PUBLIC_UVX_COMMAND_RE.finditer(line):
                tail = (match.group(1) or "").strip()
                if tail.startswith("--from "):
                    continue
                rows.append({"path": relative, "line": str(line_no), "tail": tail})
    return rows


def check_public_uvx_command_surface(repo: Path, checks: list[Check]) -> None:
    rows = _documented_public_uvx_commands(repo)
    failures: list[dict[str, str]] = []
    for row in rows:
        tail = row["tail"]
        first = tail.split(maxsplit=1)[0] if tail else ""
        if first in BANNED_PUBLIC_UVX_SUBCOMMANDS:
            failures.append(row)
    if failures:
        add(
            checks,
            "public_uvx_command_surface",
            "fail",
            "docs present source-checkout commands as public PyPI uvx commands",
            {"commands": failures},
        )
    else:
        add(
            checks,
            "public_uvx_command_surface",
            "pass",
            "documented PyPI uvx commands stay within the public first-recall surface",
            {"command_count": len(rows)},
        )


def check_workflow(repo: Path, checks: list[Check]) -> None:
    workflow = read_text(repo, ".github/workflows/publish-agent-discovery.yml")
    required_terms = {
        "workflow_dispatch": "manual release trigger",
        "release_tag": "manual release tag input",
        "environment: release": "GitHub release environment",
        "pypa/gh-action-pypi-publish": "PyPI trusted publishing action",
        'python -m pip install -e ".[release]"': "pinned release tooling extra",
        "Check tag matches package version": "tag/version guard",
        "git\", \"rev-list\", \"-n\", \"1\", tag": "tag commit guard",
        "check-jsonschema": "MCP schema validation",
        "Fresh-venv wheel contract": "fresh-venv wheel public contract smoke",
        "mcp-publisher login github-oidc": "MCP GitHub OIDC auth",
        "mcp-publisher validate server.json": "MCP Registry validation",
        "mcp-publisher publish server.json": "explicit MCP publish target",
        "Check public agent discovery": "post-publish public-state wait",
        "--wait-ready": "post-publish PyPI/MCP propagation wait",
    }
    missing = [label for term, label in required_terms.items() if term not in workflow]
    if missing:
        add(checks, "publish_workflow", "fail", "publish workflow is missing guards", {"missing": missing})
    else:
        add(checks, "publish_workflow", "pass", "publish workflow has PyPI/MCP release guards")


def fetch_json(url: str, timeout: float) -> tuple[int, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AIppocampus-agent-discovery-release-check/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            data: Any = json.loads(body)
        except json.JSONDecodeError:
            data = {"body": body[:500]}
        return exc.code, data


def check_pypi(checks: list[Check], package_version: str, timeout: float) -> None:
    status, data = fetch_json(f"https://pypi.org/pypi/{PACKAGE_NAME}/json", timeout)
    if status == 404:
        add(
            checks,
            "pypi_package",
            "pending",
            "aippocampus is not on PyPI yet; `uvx aippocampus` is not claimable",
        )
        return
    if status != 200:
        add(
            checks,
            "pypi_package",
            "warn",
            "could not verify PyPI package state",
            {"http_status": status},
        )
        return

    releases = data.get("releases", {})
    latest = data.get("info", {}).get("version")
    if package_version in releases:
        add(
            checks,
            "pypi_package",
            "pass",
            "PyPI package includes the server.json package version",
            {"latest": latest, "version": package_version},
        )
    else:
        add(
            checks,
            "pypi_package",
            "pending",
            "PyPI package exists but the current server.json version is not published",
            {"latest": latest, "expected_version": package_version},
        )


def check_mcp_registry(checks: list[Check], package_version: str, timeout: float) -> None:
    query = urllib.parse.quote(SERVER_NAME, safe="")
    status, data = fetch_json(
        f"https://registry.modelcontextprotocol.io/v0.1/servers?search={query}",
        timeout,
    )
    if status != 200:
        add(
            checks,
            "mcp_registry",
            "warn",
            "could not verify MCP Registry search state",
            {"http_status": status},
        )
        return

    def server_payload(row: Any) -> dict[str, Any]:
        if not isinstance(row, dict):
            return {}
        nested = row.get("server")
        if isinstance(nested, dict):
            return nested
        return row

    matches = [
        server
        for server in (server_payload(row) for row in data.get("servers", []))
        if server.get("name") == SERVER_NAME
    ]
    if not matches:
        add(
            checks,
            "mcp_registry",
            "pending",
            "AIppocampus is not published in the MCP Registry yet",
        )
        return

    versions = sorted(str(server.get("version", "")) for server in matches)
    if package_version in versions:
        add(
            checks,
            "mcp_registry",
            "pass",
            "MCP Registry has the server.json version",
            {"versions": versions},
        )
    else:
        add(
            checks,
            "mcp_registry",
            "pending",
            "MCP Registry entry exists but the current server.json version is not visible",
            {"versions": versions, "expected_version": package_version},
        )


def check_repo(repo: Path, *, offline: bool = False, timeout: float = 10.0) -> dict[str, Any]:
    checks: list[Check] = []
    check_required_files(repo, checks)
    _server, package_version = check_server_metadata(repo, checks)
    check_pyproject(repo, checks, package_version)
    check_marker_and_agent_text(repo, checks)
    check_public_uvx_command_surface(repo, checks)
    check_workflow(repo, checks)

    if offline:
        add(checks, "pypi_package", "warn", "skipped PyPI state check in offline mode")
        add(checks, "mcp_registry", "warn", "skipped MCP Registry state check in offline mode")
    else:
        check_pypi(checks, package_version, timeout)
        check_mcp_registry(checks, package_version, timeout)

    counts: dict[str, int] = {}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    has_fail = counts.get("fail", 0) > 0
    has_pending = counts.get("pending", 0) > 0
    return {
        "ok": not has_fail,
        "ready_for_public_agent_claim": not has_fail and not has_pending,
        "summary": counts,
        "checks": [asdict(check) for check in checks],
    }


def pending_check_ids(result: dict[str, Any]) -> list[str]:
    return [
        str(check.get("id", ""))
        for check in result.get("checks", [])
        if check.get("status") == "pending"
    ]


def _with_wait_metadata(
    result: dict[str, Any],
    *,
    attempts: int,
    elapsed_seconds: float,
    wait_seconds: float,
    poll_interval: float,
    timed_out: bool,
) -> dict[str, Any]:
    payload = dict(result)
    payload["wait"] = {
        "attempts": attempts,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "wait_seconds": wait_seconds,
        "poll_interval": poll_interval,
        "timed_out": timed_out,
        "pending_checks": pending_check_ids(result),
    }
    return payload


def wait_for_ready(
    repo: Path,
    *,
    offline: bool = False,
    timeout: float = 10.0,
    wait_seconds: float = 180.0,
    poll_interval: float = 15.0,
    check_once: Callable[..., dict[str, Any]] = check_repo,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Poll the public-state check while PyPI/MCP indexes catch up.

    The release workflow can publish successfully before the public indexes are
    visible to a fresh agent. Waiting is intentionally opt-in so pre-tag local
    checks stay fast, while post-publish verification can stop treating ordinary
    registry propagation as a manual retry ritual.
    """

    wait_seconds = max(0.0, wait_seconds)
    poll_interval = max(0.1, poll_interval)
    start = monotonic()
    attempts = 0

    while True:
        attempts += 1
        result = check_once(repo, offline=offline, timeout=timeout)
        elapsed = monotonic() - start
        if result.get("ready_for_public_agent_claim") or not result.get("ok"):
            return _with_wait_metadata(
                result,
                attempts=attempts,
                elapsed_seconds=elapsed,
                wait_seconds=wait_seconds,
                poll_interval=poll_interval,
                timed_out=False,
            )
        if elapsed >= wait_seconds:
            return _with_wait_metadata(
                result,
                attempts=attempts,
                elapsed_seconds=elapsed,
                wait_seconds=wait_seconds,
                poll_interval=poll_interval,
                timed_out=bool(pending_check_ids(result)),
            )

        sleep(min(poll_interval, wait_seconds - elapsed))


def print_text_report(result: dict[str, Any]) -> None:
    print(f"ok={str(result['ok']).lower()}")
    print(f"ready_for_public_agent_claim={str(result['ready_for_public_agent_claim']).lower()}")
    if wait := result.get("wait"):
        print(
            "wait="
            f"attempts:{wait['attempts']} "
            f"elapsed_seconds:{wait['elapsed_seconds']} "
            f"timed_out:{str(wait['timed_out']).lower()}"
        )
    for check in result["checks"]:
        print(f"[{check['status']}] {check['id']}: {check['message']}")
        if check.get("details"):
            for key, value in check["details"].items():
                print(f"  {key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--offline", action="store_true", help="Skip PyPI and MCP Registry HTTP checks")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--wait-ready",
        action="store_true",
        help="Poll until PyPI/MCP public agent-discovery state is claim-ready or the wait expires.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=180.0,
        help="Maximum seconds to wait with --wait-ready.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=15.0,
        help="Seconds between public-state polls with --wait-ready.",
    )
    parser.add_argument(
        "--fail-on-not-ready",
        action="store_true",
        help="Exit nonzero unless the public PyPI/MCP agent-discovery state is claimable",
    )
    args = parser.parse_args(argv)

    repo = find_repo_root(args.repo)
    if args.wait_ready:
        result = wait_for_ready(
            repo,
            offline=args.offline,
            timeout=args.timeout,
            wait_seconds=args.wait_seconds,
            poll_interval=args.poll_interval,
        )
    else:
        result = check_repo(repo, offline=args.offline, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text_report(result)

    if not result["ok"]:
        return 1
    if args.fail_on_not_ready and not result["ready_for_public_agent_claim"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
