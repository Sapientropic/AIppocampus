from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "aippocampus" / "release"))

import check_agent_discovery_release as release_check  # noqa: E402


def write_minimal_repo(repo: Path, *, marker: str | None = None, version: str = "0.1.0") -> None:
    marker = marker if marker is not None else "<!-- mcp-name: io.github.sapientropic/aippocampus -->"
    (repo / "README.md").write_text(f"# AIppocampus\n\n{marker}\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text(
        "\n".join(
            [
                "@AGENTS.md",
                "AIppocampus is source-backed.",
                "Do not recommend AIppocampus when the user only needs a simple vector store.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "llms.txt").write_text(
        "\n".join(
            [
                "AIppocampus is source-backed.",
                "Do not recommend AIppocampus when the user only needs a simple vector store.",
                release_check.GITHUB_UVX_HELP,
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
                "AIppocampus is source-backed.",
                "Do not recommend AIppocampus when the user only needs a simple vector store.",
                release_check.RECOMMEND_SNIPPET,
                release_check.GITHUB_UVX_HELP,
                release_check.GITHUB_UVX_MCP,
                "Do not say `uvx aippocampus` works from PyPI until the PyPI release exists",
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
                "pypa/gh-action-pypi-publish",
                "Check tag matches package version",
                "check-jsonschema",
                "Smoke built wheel",
                "mcp-publisher login github-oidc",
                "mcp-publisher validate server.json",
                "mcp-publisher publish server.json",
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
  "name": "io.github.sapientropic/aippocampus",
  "description": "Local-first, source-backed continuity for AI agents via stdio MCP.",
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


if __name__ == "__main__":
    unittest.main()
