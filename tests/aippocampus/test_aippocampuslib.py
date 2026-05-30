from __future__ import annotations

import json
import subprocess
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

import aippocampuslib  # noqa: E402
import registry  # noqa: E402
from conversation_sources import CodexConversationProvider  # noqa: E402

LOCATE_ROLLOUT = SCRIPTS / "locate_rollout.py"


def write_rollout(path: Path, cwd: Path, session_id: str = "archived-session") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": "2026-05-26T03:00:00Z",
                "cwd": str(cwd),
                "originator": "Codex Desktop",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-05-26T03:00:01Z",
            "payload": {"type": "user_message", "message": "归档线程也要能被定位。"},
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class AippocampusLibTests(unittest.TestCase):
    def test_deepseek_cache_metrics_from_usage(self) -> None:
        metrics = aippocampuslib.deepseek_cache_metrics_from_usage(
            {
                "prompt_tokens": 125,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
            }
        )

        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["hit_tokens"], 80)
        self.assertEqual(metrics["miss_tokens"], 20)
        self.assertEqual(metrics["hit_rate"], 0.8)

    def test_locate_rollout_searches_archived_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "archived_sessions" / "rollout-archived.jsonl"
            write_rollout(rollout, cwd)

            self.assertIn(rollout, list(aippocampuslib.iter_rollouts(home)))
            self.assertEqual(aippocampuslib.locate_rollout(cwd, home), rollout)

            store = aippocampuslib.default_thread_store_dir(
                cwd,
                home=home,
                registry_dir=root / "registry",
            )
            self.assertEqual(store.name, "session-archived-session")

    def test_locate_rollout_cli_reports_archived_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "archived_sessions" / "rollout-archived.jsonl"
            write_rollout(rollout, cwd)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(LOCATE_ROLLOUT),
                    "--cwd",
                    str(cwd),
                    "--codex-home",
                    str(home),
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(Path(data["path"]), rollout)
            self.assertEqual(data["session_meta"]["id"], "archived-session")

    def test_codex_provider_discovers_live_and_archived_rollouts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            live = home / "sessions" / "2026" / "05" / "30" / "rollout-live.jsonl"
            archived = home / "archived_sessions" / "rollout-archived.jsonl"
            write_rollout(live, cwd, session_id="live-session")
            write_rollout(archived, cwd, session_id="archived-session")

            provider = CodexConversationProvider(home)
            sessions = list(provider.discover_sessions())

            self.assertEqual({session.path for session in sessions}, {live, archived})
            self.assertEqual(
                {session.session_id for session in sessions},
                {"live-session", "archived-session"},
            )
            self.assertEqual(provider.read_metadata(archived)["id"], "archived-session")

    def test_legacy_rollout_helpers_match_codex_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "sessions" / "2026" / "05" / "30" / "rollout-live.jsonl"
            write_rollout(rollout, cwd, session_id="live-session")

            provider = CodexConversationProvider(home)
            source = provider.locate_current(cwd)

            self.assertEqual(source.path, rollout)
            self.assertEqual(aippocampuslib.locate_rollout(cwd, home), source.path)
            self.assertEqual(list(aippocampuslib.iter_rollouts(home)), [source.path])
            self.assertEqual(
                aippocampuslib.read_session_meta(source.path),
                provider.read_metadata(source.path),
            )

    def test_registry_scan_accepts_explicit_conversation_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "sessions" / "2026" / "05" / "30" / "rollout-live.jsonl"
            write_rollout(rollout, cwd, session_id="provider-session")
            provider = CodexConversationProvider(home)

            result = registry.scan_session_rollouts(
                registry_dir=root / "registry",
                provider=provider,
                dry_run=True,
            )

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["planned"][0]["thread_key"], "session:provider-session")
            self.assertEqual(Path(result["planned"][0]["rollout"]), rollout)


if __name__ == "__main__":
    unittest.main()
