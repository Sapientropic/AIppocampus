from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import check_docs_health as docs_health  # noqa: E402


def write_origin_essays(repo: Path) -> None:
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "未干的地图.md").write_text(
        "生命还能变成什么，而我能不能在变化后仍然是我。",
        encoding="utf-8",
    )
    (docs / "the-unfinished-map.md").write_text(
        "What else can life become, and can I still be myself after the change?",
        encoding="utf-8",
    )


class DocsHealthTests(unittest.TestCase):
    def test_skill_entrypoint_stays_slim_and_linked(self) -> None:
        result = docs_health.check_docs(ROOT)

        self.assertTrue(result["ok"], result["issues"])
        self.assertLessEqual(result["metrics"]["skill_lines"], docs_health.MAX_SKILL_LINES)
        self.assertLessEqual(result["metrics"]["skill_words"], docs_health.MAX_SKILL_WORDS)

    def test_private_thread_anchor_artifact_is_gitignored(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("thread-anchors.md", gitignore)

    def test_public_readiness_docs_and_example_bundle_are_guarded(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.check_repo_docs(repo_root)[0]

        self.assertNotIn("missing public-readiness doc: CONTRIBUTING.md", result)
        self.assertNotIn("missing public-readiness doc: docs/architecture-overview.md", result)
        self.assertNotIn("missing public-readiness doc: docs/install-guide.md", result)
        self.assertNotIn("missing public-readiness doc: docs/demo-scenarios.md", result)
        self.assertNotIn("missing public-readiness doc: docs/privacy-security-checklist.md", result)
        self.assertNotIn(
            "missing public-readiness doc: docs/public-readiness-verification.md", result
        )
        self.assertNotIn("missing public example memory bundle", result)
        self.assertFalse(any("scope_label_policy" in issue for issue in result), result)
        self.assertFalse(any("missing scope_labels" in issue for issue in result), result)

    def test_public_doc_command_lint_rejects_default_windows_only_blocks(self) -> None:
        issues = docs_health.public_doc_command_issues(
            "README.md",
            "\n".join(
                [
                    "## First Checks",
                    "",
                    "```powershell",
                    "python tools\\aippocampus\\docs\\check_docs_health.py --json",
                    "```",
                ]
            ),
        )

        self.assertTrue(any("Windows-only command block" in issue for issue in issues), issues)

    def test_public_doc_command_lint_allows_explicit_windows_section(self) -> None:
        issues = docs_health.public_doc_command_issues(
            "README.md",
            "\n".join(
                [
                    "### Windows PowerShell",
                    "",
                    "```powershell",
                    'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\aippocampus_health.py"',
                    "```",
                ]
            ),
        )

        self.assertEqual(issues, [])

    def test_repo_markdown_scan_ignores_tmp_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)
            (repo / ".tmp").mkdir()
            (repo / ".tmp" / "review-prompt.md").write_text(
                "生命还能变成什么，而我能不能在变化后仍然是我。",
                encoding="utf-8",
            )

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertFalse(any("origin phrase should live only" in issue for issue in issues), issues)

    def test_public_readiness_guard_reports_missing_docs_in_repo_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn("missing public-readiness doc: CONTRIBUTING.md", issues)
        self.assertIn("missing public-readiness doc: docs/architecture-overview.md", issues)
        self.assertIn("missing public-readiness doc: docs/install-guide.md", issues)
        self.assertIn("missing public-readiness doc: docs/demo-scenarios.md", issues)
        self.assertIn("missing public-readiness doc: docs/privacy-security-checklist.md", issues)
        self.assertIn("missing public-readiness doc: docs/public-readiness-verification.md", issues)
        self.assertIn("missing public example memory bundle", issues)

    def test_public_example_guard_requires_scope_label_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)
            for rel_path in docs_health.REQUIRED_PUBLIC_READINESS_DOCS:
                path = repo / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Placeholder\n", encoding="utf-8")
            bundle = repo / "examples" / "public-memory-bundle"
            for rel_path in docs_health.PUBLIC_EXAMPLE_BUNDLE_FILES:
                path = bundle / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".jsonl":
                    path.write_text('{"message_id":"msg_missing_labels"}\n', encoding="utf-8")
                elif rel_path == "bundle_manifest.json":
                    path.write_text('{"raw_rollout_included":false}\n', encoding="utf-8")
                else:
                    path.write_text("{}\n", encoding="utf-8")

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn(
            "public example clean-source manifest must document scope_label_policy", issues
        )
        self.assertTrue(any("missing scope_labels" in issue for issue in issues), issues)

    def test_public_example_guard_rejects_extra_files_and_stale_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)
            for rel_path in docs_health.REQUIRED_PUBLIC_READINESS_DOCS:
                path = repo / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Placeholder\n", encoding="utf-8")
            bundle = repo / "examples" / "public-memory-bundle"
            for rel_path in docs_health.PUBLIC_EXAMPLE_BUNDLE_FILES:
                path = bundle / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if rel_path == "bundle_manifest.json":
                    path.write_text('{"raw_rollout_included":false}\n', encoding="utf-8")
                elif rel_path == "clean-source/manifest.json":
                    path.write_text('{"scope_label_policy":{"version":"test"}}\n', encoding="utf-8")
                elif rel_path == "clean-source/messages.jsonl":
                    path.write_text(
                        '{"message_id":"msg_1","text":"Should I keep this?","scope_labels":["idea_seed"]}\n',
                        encoding="utf-8",
                    )
                elif rel_path == "clean-source/turns.jsonl":
                    path.write_text(
                        '{"turn_id":"turn_1","message_ids":["msg_1"],"scope_labels":["idea_seed"]}\n',
                        encoding="utf-8",
                    )
                elif path.suffix == ".jsonl":
                    path.write_text("{}\n", encoding="utf-8")
                else:
                    path.write_text("{}\n", encoding="utf-8")
            (bundle / "raw-rollouts").mkdir()
            (bundle / "raw-rollouts" / "private.jsonl").write_text("{}\n", encoding="utf-8")

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertTrue(
            any("unexpected public example bundle file" in issue for issue in issues), issues
        )
        self.assertTrue(
            any("message scope_labels do not match current generator" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
