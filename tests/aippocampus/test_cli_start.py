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

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


class AippocampusStartCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

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
        self.assertEqual(payload["agent_next_action"]["id"], "recall_continuity_cue")
        self.assertIn("command_template", payload["agent_next_action"])
        self.assertFalse(payload["state_summary"]["clean_source"]["path_serialized"])
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("choose_export_for_next_thread", action_ids)
        self.assertIn("choose_sync_for_next_device", action_ids)

    def test_start_json_redacts_operator_sensitive_fields(self) -> None:
        from aippocampus_runtime.cli import start as start_cli

        raw_card = {
            "kind": "aippocampus_start_card",
            "decision": "continue_from_existing_source",
            "agent_next_action": {"why": "token=raw-start-token", "command": "aippocampus health --json"},
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
            "agent_next_action": {
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
        self.assertIn("requires: continuity_cue", proc.stdout)
        self.assertIn('template: aippocampus agent recall "{continuity_cue}" --json', proc.stdout)
        self.assertNotIn('next: aippocampus agent recall "{continuity_cue}" --json', proc.stdout)

    def test_start_json_routes_no_source_to_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("start", "--json", "--cwd", tmp)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "register_source_before_continuity")
        self.assertEqual(payload["agent_next_action"]["id"], "register_codex_source")
        self.assertEqual(
            payload["agent_next_action"]["command"],
            "aippocampus onboard --provider codex --cwd . --json",
        )
        self.assertEqual(payload["agent_next_action"]["mutation_risk"], "writes_local_clean_source")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(action_ids[0], "register_codex_source")
        self.assertIn("register_claude_code_source", action_ids)
        self.assertIn("import_generic_jsonl_source", action_ids)
        self.assertIn("inspect_onboarding_status", action_ids)
        self.assertIn("review_claude_code_hooks", action_ids)

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
        self.assertEqual(payload["agent_next_action"]["id"], "register_claude_code_source")
        self.assertEqual(
            payload["agent_next_action"]["command"],
            "aippocampus onboard --provider claude-code --cwd . --json",
        )
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertLess(action_ids.index("register_claude_code_source"), action_ids.index("register_codex_source"))

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
        self.assertEqual(payload["agent_next_action"]["id"], "try_first_recall")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["agent_next_action"])
        self.assertEqual(payload["agent_next_action"]["mutation_risk"], "read_only")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("public_safe_demo_search", action_ids)
        public_demo = next(
            action for action in payload["safe_next_actions"] if action["id"] == "public_safe_demo_search"
        )
        self.assertIn(
            "--clean-source-dir ./examples/public-memory-bundle/clean-source",
            public_demo["command_template"],
        )
        exact_fallback = next(
            action for action in payload["safe_next_actions"] if action["id"] == "exact_search_fallback"
        )
        self.assertNotIn("--clean-source-dir", exact_fallback["command_template"])
        self.assertIn("configured local source", exact_fallback["why"])
        self.assertIn("public_safe_demo_search", exact_fallback["why"])
        self.assertIn("verify_codex_plugin_secondary", action_ids)
        self.assertNotEqual(payload["safe_next_actions"][0]["mutation_risk"], "writes_local_plugin_cache")

    def test_start_json_routes_stale_source_to_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = self.write_clean_source(root, stale=True)
            proc = self.run_cli("start", "--json", "--cwd", str(root), "--clean-source-dir", str(clean))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "repair_stale_source_before_continuity")
        self.assertEqual(payload["agent_next_action"]["id"], "repair_health_first")


if __name__ == "__main__":
    unittest.main()
