from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "release"
sys.path.insert(0, str(RELEASE_TOOLS))

import check_public_boundary as boundary  # noqa: E402


class PublicBoundaryCheckTests(unittest.TestCase):
    def test_scan_text_allows_fake_test_fixtures(self) -> None:
        text = "\n".join(
            [
                r"api_key=FAKE_TEST_OPENAI_API_KEY_1234567890",
                r"local path C:\FAKE_TEST_LOCAL_PATH\Secrets\note.md",
                "source_handle=source://private/fixture",
                "",
            ]
        )

        findings = boundary.scan_text(text, source="tracked", path="tests/example.py")

        self.assertEqual(findings, [])

    def test_scan_text_detects_secret_and_local_path_shapes(self) -> None:
        text = "\n".join(
            [
                "token=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
                r"notes live at C:\Users\RealName\Vault\note.md",
                "",
            ]
        )

        findings = boundary.scan_text(text, source="tracked", path="README.md")
        check_ids = {finding.check_id for finding in findings}

        self.assertIn("openai_token", check_ids)
        self.assertIn("windows_local_path", check_ids)
        self.assertFalse(any("abcdefghijklmnopqrstuvwxyz0123456789" in finding.match_preview for finding in findings))

    def test_private_needles_are_opt_in_and_redacted(self) -> None:
        findings = boundary.scan_text(
            "release notes accidentally mention single-use-private-phrase",
            source="tracked",
            path="CHANGELOG.md",
            private_needles=["single-use-private-phrase"],
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].check_id, "private_needle")
        self.assertEqual(findings[0].match_preview, "<private-needle:25 chars>")

    def test_build_report_excludes_default_fixture_zones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            readme = repo / "README.md"
            test_file = repo / "tests" / "aippocampus" / "test_fixture.py"
            test_file.parent.mkdir(parents=True)
            readme.write_text("# clean\n", encoding="utf-8")
            test_file.write_text("token=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789\n", encoding="utf-8")

            report = boundary.build_report(repo, paths=[readme, test_file])

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["scanned_files"], 1)
        self.assertEqual(report["finding_count"], 0)

    def test_build_report_scans_zip_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            artifact = repo / "dist" / "aippocampus-0.0.0-py3-none-any.whl"
            artifact.parent.mkdir()
            with zipfile.ZipFile(artifact, "w") as zf:
                zf.writestr(
                    "aippocampus/leak.txt",
                    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
                )

            report = boundary.build_report(repo, paths=[], dist_paths=[artifact])

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["scanned_artifact_files"], 1)
        self.assertEqual(report["findings"][0]["source"], "artifact")
        self.assertEqual(report["findings"][0]["check_id"], "authorization_bearer")

    def test_cli_json_returns_nonzero_for_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            readme = repo / "README.md"
            readme.write_text("token=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789\n", encoding="utf-8")
            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                exit_code = boundary.main(["--repo", str(repo), "--path", "README.md", "--json"])
                payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["finding_count"], 1)


if __name__ == "__main__":
    unittest.main()
