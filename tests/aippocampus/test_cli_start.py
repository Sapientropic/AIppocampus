from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.aippocampus.cli_fixtures import run_aippocampus_cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"


class AippocampusStartCliTests(unittest.TestCase):
    run_cli = staticmethod(run_aippocampus_cli)

    def write_clean_source(self, root: Path, *, stale: bool = False) -> Path:
        clean = root / "clean"
        clean.mkdir()
        manifest = {"message_count": 1 if stale else 2}
        if stale:
            manifest["stale"] = True
        (clean / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (clean / "messages.jsonl").write_text('{"text":"old route"}\n', encoding="utf-8")
        return clean

    def test_start_json_chooses_first_useful_continuity_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root)
            proc = self.run_cli("start", "--json", "--cwd", str(root), "--clean-source-dir", str(clean))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_start_card")
        self.assertEqual(payload["decision"], "continue_from_existing_source")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "recall_continuity_cue")
        self.assertIn("command_template", payload["foreground_action"])
        self.assertEqual(payload["first_recall_readiness"]["phase"], "steady_state_available")
        self.assertTrue(payload["first_recall_readiness"]["ordinary_first_recall_usable"])
        self.assertFalse(payload["first_recall_readiness"]["cold_start_expected"])
        self.assertLessEqual(len(payload["first_recall_readiness"]), 12)
        self.assertTrue(
            {
                "source_artifacts_present",
                "manifest_stale",
                "workspace_source_maintenance_required",
                "cue_specific_route_usefulness",
            }.isdisjoint(payload["first_recall_readiness"])
        )
        self.assertEqual(payload["performance_expectation"]["mode"], "steady_state")
        self.assertNotIn("state_summary", payload)
        self.assertEqual(payload["safe_next_actions"], [])
        self.assertNotIn("detail_actions_available", payload)
        self.assertTrue(payload["details_available"])

    def test_start_json_accepts_cue_and_returns_executable_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root)
            proc = self.run_cli(
                "start",
                "agent-native recall opt-in",
                "--json",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
            )
            full_proc = self.run_cli(
                "start",
                "agent-native recall opt-in",
                "--json",
                "--detail",
                "full",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(full_proc.returncode, 0, full_proc.stderr)
        payload = json.loads(proc.stdout)
        full_payload = json.loads(full_proc.stdout)
        self.assertTrue(payload["cue_supplied"])
        self.assertEqual(payload["foreground_action"]["id"], "recall_supplied_cue")
        self.assertIn("agent-native recall opt-in", payload["foreground_action"]["command"])
        self.assertNotIn("command_template", payload["foreground_action"])
        readiness = payload["first_recall_readiness"]
        self.assertNotIn("ordinary_first_recall_usable_scope", readiness)
        self.assertNotIn("cue_specific_route_usefulness", readiness)
        diagnostic = full_payload["operator_detail"]["first_recall_readiness_diagnostic"]
        self.assertEqual(
            diagnostic["ordinary_first_recall_usable_scope"],
            "cue_action_callable_not_previewed",
        )
        self.assertTrue(diagnostic["source_artifacts_present"])
        self.assertTrue(diagnostic["exact_source_search_available"])
        self.assertTrue(diagnostic["compact_agent_recall_action_callable"])
        self.assertFalse(diagnostic["cue_specific_route_usefulness"]["usefulness_verified_for_cue"])

    def test_start_json_routes_weak_cue_to_search_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root)
            proc = self.run_cli(
                "start",
                "--cue",
                "recall",
                "--json",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
            )
            full_proc = self.run_cli(
                "start",
                "--cue",
                "recall",
                "--json",
                "--detail",
                "full",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(full_proc.returncode, 0, full_proc.stderr)
        payload = json.loads(proc.stdout)
        full_payload = json.loads(full_proc.stdout)
        self.assertEqual(payload["decision"], "continue_from_existing_source_with_search_fallback")
        self.assertEqual(payload["foreground_action"]["id"], "search_current_source_for_supplied_cue")
        self.assertIn("aippocampus search", payload["foreground_action"]["command"])
        self.assertNotIn("cue_specific_route_usefulness", payload["first_recall_readiness"])
        self.assertEqual(
            full_payload["operator_detail"]["first_recall_readiness_diagnostic"]["cue_specific_route_usefulness"]["status"],
            "weak_cue_search_fallback_recommended",
        )
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("recall_supplied_cue", action_ids)
        self.assertNotIn("search_all_for_supplied_cue", action_ids)
        self.assertLessEqual(len(payload["safe_next_actions"]), 1)

    def test_start_json_redacts_operator_sensitive_fields(self) -> None:
        from aippocampus_runtime.cli import start as start_cli

        raw_card = {
            "kind": "aippocampus_start_card",
            "decision": "continue_from_existing_source",
            "foreground_action": {"why": "token=raw-start-token", "command": "aippocampus health --json"},
            "state_summary": {
                "secret": "raw-secret-value",
                "cwd": "/Users/example/private-project",
            },
        }

        stream = io.StringIO()
        with patch.object(start_cli, "build_start_card", return_value=raw_card):
            with contextlib.redirect_stdout(stream):
                rc = start_cli.main(["--json"])

        self.assertEqual(rc, 0)
        encoded = stream.getvalue()
        payload = json.loads(encoded)
        self.assertEqual(payload["state_summary"]["secret"], "<sensitive-value-redacted>")
        self.assertEqual(payload["state_summary"]["cwd"], "<local-path-redacted>")
        self.assertNotIn("raw-secret-value", encoded)
        self.assertNotIn("raw-start-token", encoded)
        self.assertNotIn("/Users/example/private-project", encoded)

    def test_start_text_redacts_operator_sensitive_fields(self) -> None:
        from aippocampus_runtime.cli import start as start_cli

        raw_card = {
            "kind": "aippocampus_start_card",
            "decision": "continue_from_existing_source",
            "foreground_action": {
                "why": "password=raw-start-password",
                "command": "aippocampus health --json",
            },
        }

        stream = io.StringIO()
        with patch.object(start_cli, "build_start_card", return_value=raw_card):
            with contextlib.redirect_stdout(stream):
                rc = start_cli.main([])

        self.assertEqual(rc, 0)
        rendered = stream.getvalue()
        self.assertNotIn("raw-start-password", rendered)
        self.assertIn("<redacted", rendered)

    def test_start_human_output_labels_templates_instead_of_printing_placeholder_as_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root)
            proc = self.run_cli("start", "--cwd", str(root), "--clean-source-dir", str(clean))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("first recall: ready", proc.stdout)
        self.assertIn("requires: continuity_cue", proc.stdout)
        self.assertIn('template: aippocampus agent recall "{continuity_cue}" --json', proc.stdout)
        self.assertNotIn('next: aippocampus agent recall "{continuity_cue}" --json', proc.stdout)

    def test_start_json_routes_no_source_to_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("start", "--json", "--cwd", tmp)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "register_source_before_continuity")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "register_codex_source")
        self.assertEqual(payload["first_recall_readiness"]["phase"], "cold_start_setup_required")
        self.assertFalse(payload["first_recall_readiness"]["ordinary_first_recall_usable"])
        self.assertTrue(payload["first_recall_readiness"]["cold_start_expected"])
        self.assertTrue(payload["first_recall_readiness"]["requires_user_consent_for_writes"])
        self.assertEqual(payload["first_recall_readiness"]["progress_signal"], "no_clean_source_registered")
        self.assertEqual(
            payload["foreground_action"]["command"],
            "aippocampus onboard --provider codex --cwd . --json",
        )
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "writes_local_clean_source")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertNotIn("register_codex_source", action_ids)
        write_action_ids = [action["id"] for action in payload["write_actions"]]
        self.assertIn("register_claude_code_source", write_action_ids)
        self.assertIn("import_generic_jsonl_source", write_action_ids)
        self.assertIn("inspect_onboarding_status", action_ids)
        self.assertNotIn("review_claude_code_hooks", action_ids)
        self.assertLessEqual(len(payload["safe_next_actions"]), 1)

    def test_trusted_personal_profile_groups_setup_and_first_recall_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli(
                "start",
                "--json",
                "--cwd",
                tmp,
                "--profile",
                "trusted-local-personal-continuity",
                "--cue",
                "old privacy product decision",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "register_source_before_continuity")
        self.assertEqual(payload["setup_profile"]["id"], "trusted-local-personal-continuity")
        self.assertEqual(
            payload["setup_profile"]["consent_model"],
            "consent_once_for_low_risk_local_personal_setup",
        )
        self.assertEqual(payload["foreground_action"]["id"], "register_codex_source")
        self.assertEqual(
            payload["foreground_action"]["consent_bundle_id"],
            "trusted-local-personal-continuity",
        )
        self.assertIn(
            "old privacy product decision",
            payload["foreground_action"]["after_success_command"],
        )
        self.assertEqual(payload["first_magic_path"]["target"], "first_useful_recall_receipt")
        self.assertIn(
            "old privacy product decision",
            payload["first_magic_path"]["after_setup_command"],
        )
        self.assertIn(
            "local_source_registration_or_refresh",
            payload["consent_bundle"]["low_risk_local_actions"],
        )
        self.assertIn(
            "destructive_cleanup",
            payload["consent_bundle"]["requires_separate_consent"],
        )
        self.assertEqual(payload["setup_profile"]["rollback_command"], "aippocampus uninstall --dry-run --json")
        self.assertLessEqual(len(payload["safe_next_actions"]), 3)
        self.assertNotIn("surfaces", payload)
        self.assertNotIn("operator_diagnostics", payload)

    def test_trusted_personal_text_shows_value_path_before_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli(
                "start",
                "--cwd",
                tmp,
                "--profile",
                "trusted-local-personal-continuity",
                "--cue",
                "old privacy product decision",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("profile: trusted-local-personal-continuity", proc.stdout)
        self.assertIn("after setup: aippocampus agent recall", proc.stdout)
        self.assertIn("old privacy product decision", proc.stdout)
        self.assertNotIn("operator_diagnostics", proc.stdout)

    def test_start_json_prefers_detected_non_codex_source_registration(self) -> None:
        from aippocampus_runtime.cli import start as start_cli

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                start_cli,
                "provider_status_report",
                return_value={
                    "data": {
                        "providers": [
                            {
                                "provider": "codex",
                                "detected": False,
                                "write_registration_available": True,
                            },
                            {
                                "provider": "claude-code",
                                "detected": True,
                                "write_registration_available": True,
                            },
                            {
                                "provider": "generic-jsonl",
                                "detected": False,
                                "write_registration_available": False,
                            },
                        ]
                    }
                },
            ):
                payload = start_cli.build_start_card(Path(tmp))

        self.assertEqual(payload["decision"], "register_source_before_continuity")
        self.assertEqual(payload["foreground_action"]["id"], "register_claude_code_source")
        self.assertEqual(
            payload["foreground_action"]["command"],
            "aippocampus onboard --provider claude-code --cwd . --json",
        )
        self.assertEqual(payload["foreground_action"]["id"], "register_claude_code_source")
        self.assertIn(
            "register_codex_source",
            [action["id"] for action in payload["write_actions"]],
        )

    def test_bare_aippocampus_in_new_workspace_shows_start_card_not_help_wall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                str(SCRIPTS)
                if not existing_pythonpath
                else str(SCRIPTS) + os.pathsep + existing_pythonpath
            )
            proc = subprocess.run(
                [sys.executable, "-m", "aippocampus_runtime.cli.facade"],
                cwd=tmp,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("AIppocampus start", proc.stdout)
        self.assertIn("next: aippocampus onboard --provider codex --cwd . --json", proc.stdout)
        self.assertNotIn("Commands:", proc.stdout)

    def test_start_json_routes_trusted_codex_workspace_to_read_only_first_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "plugins" / "aippocampus" / ".codex-plugin"
            manifest.mkdir(parents=True)
            (manifest / "plugin.json").write_text("{}", encoding="utf-8")
            proc = self.run_cli("start", "--json", "--cwd", str(root))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "try_read_only_continuity_before_setup")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "try_first_recall")
        self.assertEqual(payload["first_recall_readiness"]["phase"], "cold_start_probe_or_public_demo")
        self.assertFalse(payload["first_recall_readiness"]["private_source_ready"])
        self.assertFalse(payload["first_recall_readiness"]["ordinary_first_recall_usable"])
        self.assertTrue(payload["first_recall_readiness"]["read_only_probe_available"])
        self.assertTrue(payload["first_recall_readiness"]["public_demo_available"])
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("public_safe_demo_search", action_ids)
        self.assertLessEqual(len(payload["safe_next_actions"]), 1)
        public_demo = next(
            action for action in payload["safe_next_actions"] if action["id"] == "public_safe_demo_search"
        )
        self.assertIn(
            "--clean-source-dir ./examples/public-memory-bundle/clean-source",
            public_demo["command_template"],
        )
        self.assertIn(
            "verify_codex_plugin_secondary",
            [action["id"] for action in payload["write_actions"]],
        )
        self.assertNotEqual(payload["safe_next_actions"][0]["mutation_risk"], "writes_local_plugin_cache")

    def test_start_json_distinguishes_stale_source_from_first_recall_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root, stale=True)
            proc = self.run_cli("start", "--json", "--cwd", str(root), "--clean-source-dir", str(clean))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "continue_from_existing_source_latest_degraded")
        self.assertEqual(payload["status"], "ready_with_freshness_degraded")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "recall_continuity_cue")
        self.assertEqual(payload["first_recall_readiness"]["phase"], "steady_state_latest_degraded")
        self.assertTrue(payload["first_recall_readiness"]["ordinary_first_recall_usable"])
        self.assertFalse(payload["first_recall_readiness"]["cold_start_expected"])
        self.assertEqual(payload["first_recall_readiness"]["progress_signal"], "source_exists_but_stale")
        self.assertTrue(payload["first_recall_readiness"]["blocks_exact_latest_claims"])
        self.assertNotIn("manifest_stale", payload["first_recall_readiness"])
        self.assertNotIn("workspace_source_maintenance_required", payload["first_recall_readiness"])
        self.assertTrue(payload["blocks_exact_latest_claims"])
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(action_ids, ["review_maintenance_plan_before_exact_latest"])
        self.assertNotIn("write_actions", payload)
        self.assertNotIn("manage_command", payload)
        self.assertTrue(payload["details_available"])

    def test_start_uses_health_freshness_gap_when_manifest_is_not_stale(self) -> None:
        from aippocampus_runtime.cli import start as start_cli

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root, stale=False)
            with patch.object(
                start_cli,
                "_workspace_freshness_state",
                return_value={
                    "assessed": True,
                    "freshness_scope": "workspace_health_summary",
                    "freshness_degraded": True,
                    "latest_current_thread_may_be_missing": True,
                    "workspace_source_maintenance_required": True,
                    "blocks_exact_latest_claims": True,
                    "recommended_action_ids": ["build_clean_source", "build_index"],
                    "product_readiness_status": "ready_with_freshness_degraded",
                },
            ):
                payload = start_cli.build_start_card(
                    root,
                    clean_source_dir=str(clean),
                )
                full_payload = start_cli.build_start_card(
                    root,
                    clean_source_dir=str(clean),
                    detail="full",
                )

        self.assertEqual(payload["decision"], "continue_from_existing_source_latest_degraded")
        self.assertEqual(payload["status"], "ready_with_freshness_degraded")
        readiness = payload["first_recall_readiness"]
        self.assertEqual(readiness["phase"], "steady_state_latest_degraded")
        self.assertTrue(readiness["ordinary_first_recall_usable"])
        self.assertTrue(readiness["source_stale"])
        self.assertNotIn("manifest_stale", readiness)
        self.assertTrue(readiness["latest_current_thread_may_be_missing"])
        self.assertNotIn("workspace_source_maintenance_required", readiness)
        self.assertTrue(readiness["blocks_exact_latest_claims"])
        diagnostic = full_payload["operator_detail"]["first_recall_readiness_diagnostic"]
        self.assertFalse(diagnostic["manifest_stale"])
        self.assertTrue(diagnostic["workspace_source_maintenance_required"])
        source = full_payload["operator_detail"]["state_summary"]["clean_source"]
        self.assertFalse(source["manifest_stale"])
        self.assertTrue(source["latest_source_may_be_missing"])
        self.assertEqual(source["freshness_scope"], "workspace_health_summary")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(action_ids, ["review_maintenance_plan_before_exact_latest"])
        self.assertNotIn("write_actions", payload)
        self.assertEqual(payload["manage_command"], "aippocampus maintenance plan --summary-json")

if __name__ == "__main__":
    unittest.main()
