from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.cli_fixtures import registry_env, run_aippocampus_cli


class AgentSelfNoteCliTests(unittest.TestCase):
    def run_self_note(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ):
        return run_aippocampus_cli("self-note", *args, env=env, stdin=stdin)

    def test_current_thread_append_round_trips_as_atmosphere(self) -> None:
        note = "future posture: move decisively, but keep source boundary explicit."
        raw_thread_id = "codex-raw-thread-id-should-not-escape"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_self_note(
                "append",
                "--current-thread",
                "--cwd",
                str(root),
                "--stdin",
                "--json",
                env=registry_env(root, CODEX_THREAD_ID=raw_thread_id),
                stdin=note,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        preview = payload["round_trip_preview"]
        atmosphere = preview["memory_atmosphere"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_append")
        self.assertTrue(payload["source_ref_attached"])
        self.assertEqual(preview["decision"], "context")
        self.assertEqual(preview["surface_counts"]["agent_self_notes"], 1)
        self.assertEqual(atmosphere[0]["action_grammar"], "direction_only")
        self.assertFalse(atmosphere[0]["trust_contract"]["treat_as_fact"])
        self.assertFalse(atmosphere[0]["claims_user_fact"])
        self.assertFalse(atmosphere[0]["claims_source_fact"])
        self.assertTrue(atmosphere[0]["source_reopen_required_before_claim"])
        self.assertNotIn(raw_thread_id, raw)
        self.assertNotIn(str(root), raw)
        self.assertNotIn("raw prompt", raw.casefold())

    def test_current_thread_long_append_returns_compact_projection_only(self) -> None:
        note = (
            "opening posture: be bold about the observed magic, "
            + "but keep the source boundary explicit and atmosphere-only; " * 14
            + "hidden tail marker should stay private."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_self_note(
                "append",
                "--current-thread",
                "--cwd",
                str(root),
                "--stdin",
                "--json",
                env=registry_env(root),
                stdin=note,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertLessEqual(len(payload["note"]["note_text"]), 280)
        self.assertTrue(payload["note"]["note_body_private_available"])
        self.assertFalse(payload["note"]["note_body_private_default_visible"])
        self.assertNotIn("note_body_private\":", raw)
        self.assertNotIn("hidden tail marker should stay private", raw)

    def test_plain_json_append_returns_compact_projection_only(self) -> None:
        note = (
            "plain append posture: keep private body out of default JSON; "
            + "visible-safe prefix, " * 18
            + "hidden plain append tail should stay private."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_self_note(
                "append",
                "--notes-path",
                str(root / "agent-self-notes.jsonl"),
                "--stdin",
                "--json",
                stdin=note,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_append")
        self.assertLessEqual(len(payload["note"]["note_text"]), 280)
        self.assertTrue(payload["note"]["note_body_private_available"])
        self.assertEqual(payload["note"]["action_grammar"], "direction_only")
        self.assertIn("source-less scent", payload["foreground_action"]["why"])
        self.assertNotIn("note_body_private\":", raw)
        self.assertNotIn("hidden plain append tail should stay private", raw)

    def test_plain_text_append_names_direction_only_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_self_note(
                "append",
                "--notes-path",
                str(root / "agent-self-notes.jsonl"),
                "keep this as a navigation breadcrumb",
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("agent self-note:", proc.stdout)
        self.assertIn("authority: direction_only", proc.stdout)

    def test_current_thread_append_rejects_raw_payload_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_self_note(
                "append",
                "--current-thread",
                "--cwd",
                str(root),
                "--stdin",
                "--json",
                env=registry_env(root),
                stdin="tool_result stdout stderr should not become a margin note",
            )

        raw = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "agent_self_note_raw_payload_rejected")
        self.assertNotIn(str(root), raw)

    def test_search_empty_returns_recovery_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_self_note(
                "search",
                "no matching posture",
                "--notes-path",
                str(root / "agent-self-notes.jsonl"),
                "--json",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["empty_state"]["decision"], "empty")
        self.assertEqual(payload["empty_state"]["foreground_action"]["id"], "search_notes")
        self.assertEqual(payload["empty_state"]["foreground_action"]["requires"], ["cue"])
        self.assertTrue(
            any(action["id"] == "source_backed_recall" for action in payload["empty_state"]["safe_next_actions"])
        )

    def test_read_is_intentional_not_phantom_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            append = self.run_self_note("append", "--notes-path", str(notes_path), "readable breadcrumb", "--json")
            note_id = json.loads(append.stdout)["note"]["note_id"]
            read = self.run_self_note("read", note_id, "--notes-path", str(notes_path), "--json")
            missing = self.run_self_note("read", "note_missing", "--notes-path", str(notes_path), "--json")
            help_proc = self.run_self_note("read", "--help")

        self.assertEqual(read.returncode, 0, read.stderr)
        payload = json.loads(read.stdout)
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_read")
        self.assertEqual(payload["note"]["note_id"], note_id)
        self.assertEqual(payload["note"]["action_grammar"], "direction_only")
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertTrue(any(action["id"] == "list_notes" for action in payload["safe_next_actions"]))
        self.assertEqual(payload["foreground_action"]["claim_boundary"], "direction_only_not_source_truth")
        self.assertTrue(payload["foreground_action"]["continue_without_command"])
        self.assertTrue(payload["source_boundary"]["source_reopen_required_before_claim"])
        self.assertNotEqual(missing.returncode, 0)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(missing_payload["error"]["code"], "agent_self_note_not_found")
        self.assertEqual(missing_payload["foreground_action"]["id"], "list_notes")
        self.assertTrue(any(action["id"] == "search_notes" for action in missing_payload["safe_next_actions"]))
        self.assertEqual(help_proc.returncode, 0)
        self.assertIn("usage: aippocampus self-note read", help_proc.stdout)
        self.assertIn("direction-only", help_proc.stdout)

    def test_default_list_is_workspace_scoped_with_registry_wide_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_a = root / "project-a"
            project_b = root / "project-b"
            project_a.mkdir()
            project_b.mkdir()
            env = registry_env(root)
            append = self.run_self_note("append", "--cwd", str(project_a), "scope breadcrumb", "--json", env=env)
            unrelated = self.run_self_note("list", "--cwd", str(project_b), "--json", env=env)
            registry_wide = self.run_self_note(
                "list",
                "--cwd",
                str(project_b),
                "--registry-wide",
                "--json",
                env=env,
            )
            human = self.run_self_note("list", "--cwd", str(project_a), env=env)

        self.assertEqual(append.returncode, 0, append.stderr)
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        self.assertEqual(registry_wide.returncode, 0, registry_wide.stderr)
        unrelated_payload = json.loads(unrelated.stdout)
        wide_payload = json.loads(registry_wide.stdout)
        self.assertEqual(unrelated_payload["scope"]["mode"], "current_workspace")
        self.assertEqual(unrelated_payload["count"], 0)
        self.assertEqual(wide_payload["scope"]["mode"], "registry_wide")
        self.assertEqual(wide_payload["count"], 1)
        self.assertEqual(wide_payload["rows"][0]["action_grammar"], "direction_only")
        self.assertTrue(wide_payload["rows"][0]["source_boundary"]["source_reopen_required_before_claim"])
        self.assertIn("direction_only atmosphere", human.stdout)
        self.assertIn("boundary: direction_only", human.stdout)


if __name__ == "__main__":
    unittest.main()
