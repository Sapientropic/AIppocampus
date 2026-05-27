from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_stage_0_5_smoke as smoke  # noqa: E402


class Stage05SmokeRunnerTests(unittest.TestCase):
    def test_command_plan_covers_stage_0_5_public_readiness_gates(self) -> None:
        repo_root = Path("repo").resolve()
        labels = [item.label for item in smoke.build_command_plan(repo_root)]

        self.assertIn("docs_health", labels)
        self.assertIn("unit_suite", labels)
        self.assertIn("compileall", labels)
        self.assertIn("ruff", labels)
        self.assertIn("public_timeline", labels)
        self.assertIn("scope_search", labels)
        self.assertIn("casual_important_search", labels)
        self.assertIn("life_wide_registry_smoke", labels)
        self.assertIn("semantic_scope_real_history_smoke", labels)
        self.assertIn("source_evidence_recall_eval", labels)
        self.assertIn("mcp_tool_list", labels)
        self.assertIn("plugin_build", labels)
        self.assertIn("plugin_install_smoke", labels)
        self.assertIn("cross_device_sync_smoke", labels)
        self.assertIn("object_storage_sync_smoke", labels)
        self.assertIn("alternate_runtime_sync_smoke", labels)
        self.assertNotIn("semantic_scope_source_review_live", labels)

    def test_command_plan_can_explicitly_include_live_stage2_source_review(self) -> None:
        repo_root = Path("repo").resolve()
        labels = [
            item.label
            for item in smoke.build_command_plan(
                repo_root,
                include_live_stage2_source_review=True,
            )
        ]

        self.assertIn("source_evidence_recall_eval", labels)
        self.assertIn("semantic_scope_source_review_live", labels)

    def test_casual_important_validator_requires_semantic_sidecar_top_hit(self) -> None:
        passing = {
            "matches": [
                {
                    "message_id": "msg_public_005",
                    "semantic_scope_labels": ["personal_reflection", "idea_seed", "life_context"],
                }
            ]
        }
        fallback_only = {
            "matches": [
                {
                    "message_id": "msg_public_006",
                    "semantic_scope_labels": [],
                }
            ]
        }

        self.assertTrue(smoke.validate_casual_important_search(passing)["ok"])
        failed = smoke.validate_casual_important_search(fallback_only)
        self.assertFalse(failed["ok"])
        self.assertIn("msg_public_005", failed["message"])

    def test_command_validation_uses_full_stdout_not_truncated_tail(self) -> None:
        payload = json.dumps(
            {
                "matches": [
                    {
                        "message_id": "msg_public_005",
                        "semantic_scope_labels": ["personal_reflection", "idea_seed"],
                    }
                ]
            },
            indent=2,
        )
        result = {
            "label": "casual_important_search",
            "ok": True,
            "returncode": 0,
            "_stdout": payload,
            "stdout_tail": payload[-24:],
            "stderr_tail": "",
        }

        validated = smoke.validate_command_result(
            smoke.SmokeCommand("casual_important_search", [sys.executable], Path.cwd()),
            result,
        )

        self.assertTrue(validated["ok"])
        self.assertNotIn("_stdout", validated)
        self.assertTrue(validated["validation"]["ok"])

    def test_cleanup_targets_are_fixed_inside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp).resolve()
            run_id = "test-run"
            inside = smoke.cleanup_targets(repo_root, run_id)

            self.assertIn(repo_root / "dist" / f"aippocampus-plugin-{run_id}", inside)
            self.assertIn(repo_root / ".tmp" / f"stage-0-5-public-project-timeline-{run_id}.json", inside)
            for target in inside:
                self.assertTrue(smoke.path_is_within(repo_root, target))

    def test_cleanup_does_not_remove_preexisting_fixed_plugin_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp).resolve()
            preexisting = repo_root / "dist" / "aippocampus-plugin"
            run_artifact = repo_root / "dist" / "aippocampus-plugin-test-run"
            preexisting.mkdir(parents=True)
            run_artifact.mkdir(parents=True)
            (preexisting / "keep.txt").write_text("keep", encoding="utf-8")

            removed = smoke.cleanup_smoke_outputs(repo_root, "test-run")

            self.assertEqual(removed, ["dist/aippocampus-plugin-test-run"])
            self.assertTrue((preexisting / "keep.txt").exists())
            self.assertFalse(run_artifact.exists())

    def test_repo_root_validation_rejects_unrelated_directory_before_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            unrelated = Path(tmp).resolve()

            with mock.patch.object(smoke, "cleanup_smoke_outputs") as cleanup:
                with self.assertRaises(ValueError):
                    smoke.repo_root_from_arg(unrelated)

            self.assertFalse(cleanup.called)

    def test_run_stage_0_5_smoke_validates_repo_root_before_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            unrelated = Path(tmp).resolve()

            with mock.patch.object(smoke, "cleanup_smoke_outputs") as cleanup:
                with self.assertRaises(ValueError):
                    smoke.run_stage_0_5_smoke(unrelated, run_id="test-run")

            self.assertFalse(cleanup.called)

    def test_secret_scan_allows_fake_fixtures_but_flags_real_secret_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            tests_dir = repo_root / "skills" / "aippocampus" / "tests"
            tests_dir.mkdir(parents=True)
            (tests_dir / "fixture.py").write_text(
                'FAKE_TEST_OPENAI_API_KEY = "sk-FAKE_TEST_OPENAI_REDACTION_1234567890"\n',
                encoding="utf-8",
            )
            leaked = "sk-" + "realSecretValueThatShouldBeRejected123456"
            (repo_root / "leak.py").write_text(
                f'token = "{leaked}"\n',
                encoding="utf-8",
            )

            hits = smoke.scan_secret_like_strings(repo_root)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "leak.py")
        self.assertIn("sk-realSecret", hits[0]["line"])

    def test_secret_scan_flags_real_secret_even_with_fake_test_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            leaked = "sk-" + "realSecretValueThatShouldBeRejected123456"
            (repo_root / "leak.py").write_text(
                f'api_key = "{leaked}"  # fake_test\n',
                encoding="utf-8",
            )

            hits = smoke.scan_secret_like_strings(repo_root)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "leak.py")

    def test_secret_scan_flags_real_secret_as_env_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            leaked = "sk-" + "realSecretValueThatShouldBeRejected123456"
            (repo_root / "leak.py").write_text(
                f'api_key = os.environ.get("OPENAI_API_KEY", "{leaked}")\n',
                encoding="utf-8",
            )

            hits = smoke.scan_secret_like_strings(repo_root)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "leak.py")


if __name__ == "__main__":
    unittest.main()
