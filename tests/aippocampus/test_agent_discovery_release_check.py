from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "aippocampus" / "release"))

import check_agent_discovery_release as release_check  # noqa: E402


def write_minimal_repo(repo: Path, *, marker: str | None = None, version: str = "0.1.0") -> None:
    marker = marker if marker is not None else "<!-- mcp-name: io.github.Sapientropic/aippocampus -->"
    (repo / "README.md").write_text(f"# AIppocampus\n\n{marker}\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agents",
                "AIppocampus is source-backed continuity.",
                "Use source-reachable action guidance.",
                "AIppocampus is usually not the right fit when the user only needs a simple vector store.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "CLAUDE.md").write_text(
        "\n".join(
            [
                "@AGENTS.md",
                "AIppocampus is source-backed continuity.",
                "Use source-reachable action guidance.",
                "AIppocampus is usually not the right fit when the user only needs a simple vector store.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "llms.txt").write_text(
        "\n".join(
            [
                "AIppocampus is source-backed continuity.",
                "Use source-reachable action guidance.",
                "AIppocampus is usually not the right fit when the user only needs a simple vector store.",
                'uvx aippocampus agent recall "old decision or handoff cue" --json',
                release_check.PUBLIC_UVX_HELP,
                "",
            ]
        ),
        encoding="utf-8",
    )
    docs = repo / "docs"
    (docs / "planning").mkdir(parents=True)
    (docs / "agent-context.md").write_text(
        "\n\n".join(
            [
                "AIppocampus is source-backed continuity.",
                "Use source-reachable action guidance.",
                "AIppocampus is usually not the right fit when the user only needs a simple vector store.",
                release_check.RECOMMEND_SNIPPET,
                release_check.PUBLIC_UVX_HELP,
                release_check.PUBLIC_UVX_MCP,
                "Use the GitHub `uvx --from git+...` form only for unreleased main-branch",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "planning" / "agent-discoverability-release.md").write_text(
        "# Agent Discoverability Release Plan\n", encoding="utf-8"
    )
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "publish-agent-discovery.yml").write_text(
        "\n".join(
            [
                "environment: release",
                "workflow_dispatch",
                "release_tag",
                "pypa/gh-action-pypi-publish",
                'python -m pip install -e ".[release]"',
                "Check tag matches package version",
                'git", "rev-list", "-n", "1", tag',
                "check-jsonschema",
                "Fresh-venv wheel contract",
                "mcp-publisher login github-oidc",
                "mcp-publisher validate server.json",
                "mcp-publisher publish server.json",
                "Check public agent discovery",
                "--wait-ready",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "aippocampus"',
                f'version = "{version}"',
                'readme = "README.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "server.json").write_text(
        f"""\
{{
  "name": "io.github.Sapientropic/aippocampus",
  "description": "Local-first, source-backed continuity for AI agents: recall and deepen routes via stdio MCP.",
  "version": "{version}",
  "packages": [
    {{
      "registryType": "pypi",
      "identifier": "aippocampus",
      "version": "{version}",
      "transport": {{"type": "stdio"}}
    }}
  ]
}}
""",
        encoding="utf-8",
    )


class AgentDiscoveryReleaseCheckTests(unittest.TestCase):
    def test_offline_minimal_repo_passes_local_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_minimal_repo(repo)

            result = release_check.check_repo(repo, offline=True)

        self.assertTrue(result["ok"], result)
        self.assertTrue(
            any(check["id"] == "agent_truth_pack" and check["status"] == "pass" for check in result["checks"])
        )
        self.assertEqual(result["summary"].get("warn"), 2)

    def test_missing_mcp_marker_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_minimal_repo(repo, marker="")

            result = release_check.check_repo(repo, offline=True)

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(check["id"] == "readme_mcp_marker" and check["status"] == "fail" for check in result["checks"])
        )

    def test_llms_proof_first_or_stale_commands_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_minimal_repo(repo)
            (repo / "llms.txt").write_text(
                "\n".join(
                    [
                        "AIppocampus is source-backed continuity.",
                        "Use source-reachable action guidance.",
                        "AIppocampus is usually not the right fit when the user only needs a simple vector store.",
                        'uvx aippocampus search "a distinctive old phrase"',
                        "uvx aippocampus onboard --provider codex --all --format json",
                        release_check.PUBLIC_UVX_HELP,
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = release_check.check_repo(repo, offline=True)

        truth_pack = next(check for check in result["checks"] if check["id"] == "agent_truth_pack")
        self.assertEqual(truth_pack["status"], "fail")
        self.assertIn("llms.txt should not lead with broad exact search before recall/deepen", str(truth_pack["details"]))

    def test_version_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_minimal_repo(repo, version="0.2.0")
            (repo / "pyproject.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        'name = "aippocampus"',
                        'version = "0.1.0"',
                        'readme = "README.md"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = release_check.check_repo(repo, offline=True)

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(check["id"] == "pyproject" and check["status"] == "fail" for check in result["checks"])
        )

    def test_public_uvx_command_surface_rejects_source_checkout_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_minimal_repo(repo)
            (repo / "README.md").write_text(
                "\n".join(
                    [
                        "# AIppocampus",
                        "<!-- mcp-name: io.github.Sapientropic/aippocampus -->",
                        "```sh",
                        "uvx aippocampus plugin install --codex --verify",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = release_check.check_repo(repo, offline=True)

        self.assertFalse(result["ok"])
        check = next(
            check
            for check in result["checks"]
            if check["id"] == "public_uvx_command_surface"
        )
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["details"]["commands"][0]["tail"].split()[0], "plugin")

    def test_mcp_registry_accepts_nested_server_search_results(self) -> None:
        original_fetch_json = release_check.fetch_json

        def fake_fetch_json(url: str, timeout: float) -> tuple[int, object]:
            return 200, {
                "servers": [
                    {
                        "server": {
                            "name": "io.github.Sapientropic/aippocampus",
                            "version": "0.1.1",
                        },
                        "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}},
                    }
                ]
            }

        try:
            release_check.fetch_json = fake_fetch_json
            checks: list[release_check.Check] = []

            release_check.check_mcp_registry(checks, "0.1.1", timeout=0.01)
        finally:
            release_check.fetch_json = original_fetch_json

        self.assertEqual(checks[0].id, "mcp_registry")
        self.assertEqual(checks[0].status, "pass")

    def test_wait_for_ready_polls_pending_public_state_until_claimable(self) -> None:
        calls: list[tuple[Path, bool, float]] = []
        sleeps: list[float] = []
        times = iter([10.0, 10.0, 11.0])

        pending = {
            "ok": True,
            "ready_for_public_agent_claim": False,
            "summary": {"pending": 1},
            "checks": [
                {"id": "pypi_package", "status": "pending", "message": "not visible yet"},
            ],
        }
        ready = {
            "ok": True,
            "ready_for_public_agent_claim": True,
            "summary": {"pass": 1},
            "checks": [
                {"id": "pypi_package", "status": "pass", "message": "visible"},
            ],
        }

        def fake_check(repo: Path, *, offline: bool = False, timeout: float = 10.0) -> dict[str, object]:
            calls.append((repo, offline, timeout))
            return pending if len(calls) == 1 else ready

        result = release_check.wait_for_ready(
            Path("."),
            timeout=0.5,
            wait_seconds=30.0,
            poll_interval=1.0,
            check_once=fake_check,
            sleep=lambda seconds: sleeps.append(seconds),
            monotonic=lambda: next(times),
        )

        self.assertTrue(result["ready_for_public_agent_claim"], result)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(result["wait"]["attempts"], 2)
        self.assertFalse(result["wait"]["timed_out"])

    def test_wait_for_ready_returns_fail_without_retrying_local_contract_errors(self) -> None:
        calls = 0
        result_payload = {
            "ok": False,
            "ready_for_public_agent_claim": False,
            "summary": {"fail": 1},
            "checks": [
                {"id": "pyproject", "status": "fail", "message": "version mismatch"},
            ],
        }

        def fake_check(repo: Path, *, offline: bool = False, timeout: float = 10.0) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return result_payload

        result = release_check.wait_for_ready(
            Path("."),
            wait_seconds=30.0,
            check_once=fake_check,
            sleep=lambda seconds: None,
            monotonic=lambda: 0.0,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual(calls, 1)
        self.assertEqual(result["wait"]["attempts"], 1)
        self.assertFalse(result["wait"]["timed_out"])


if __name__ == "__main__":
    unittest.main()
