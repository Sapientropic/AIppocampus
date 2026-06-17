from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_start_json_routes_no_source_to_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("start", "--json", "--cwd", tmp)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "register_source_before_continuity")
        self.assertEqual(payload["agent_next_action"]["command"], "aippocampus onboard --provider auto --status --json")

    def test_start_json_routes_trusted_codex_setup_before_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "plugins" / "aippocampus" / ".codex-plugin"
            manifest.mkdir(parents=True)
            (manifest / "plugin.json").write_text("{}", encoding="utf-8")
            proc = self.run_cli("start", "--json", "--cwd", str(root))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "trusted_codex_setup_then_recall")
        self.assertEqual(payload["agent_next_action"]["id"], "install_or_verify_codex_plugin")
        self.assertTrue(any(action["id"] == "recall_after_setup" for action in payload["safe_next_actions"]))

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
