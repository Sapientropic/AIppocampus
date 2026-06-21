from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import authority
from aippocampus_runtime.source import agent_self_note_cli


class AgentSelfNoteTests(unittest.TestCase):
    def _notes_module(self):
        try:
            from aippocampus_runtime.source import agent_self_notes as notes
        except Exception as exc:  # pragma: no cover - failing-test clarity
            self.fail(f"agent_self_notes module should be importable: {exc}")
        return notes

    def test_append_self_note_stays_direction_only_with_reopen_route(self) -> None:
        notes = self._notes_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "agent-self-notes.jsonl"

            row = notes.append_agent_self_note(
                path,
                note_text="这次我没有绕开那个犹豫，先把边界说清楚再动手。",
                thread_key="session:old",
                source_refs=[
                    {
                        "thread_key": "session:old",
                        "message_id": "msg-7",
                        "turn_id": "turn-7",
                        "line": 31,
                        "title": "Closeout turn",
                    }
                ],
                trigger="closeout",
                created_at="2026-06-07T00:00:00Z",
            )
            raw = path.read_text(encoding="utf-8")

        self.assertEqual(row["kind"], "agent_self_note")
        self.assertEqual(row["author_role"], "foreground_agent")
        self.assertEqual(row["authority"], "direction_only")
        self.assertEqual(row["action_grammar"], "direction_only")
        self.assertEqual(row["memory_surface"], "memory_atmosphere")
        self.assertEqual(row["use_boundary"], "atmosphere_only")
        self.assertFalse(row["claims_user_fact"])
        self.assertFalse(row["claims_world_fact"])
        self.assertFalse(row["claims_source_fact"])
        self.assertFalse(row["formal_memory_eligible"])
        self.assertFalse(row["foreground_default_visible"])
        self.assertTrue(row["source_reopen_required_before_claim"])
        self.assertEqual(row["source_refs"][0]["message_id"], "msg-7")
        self.assertFalse(authority.is_bounded_evidence(row))
        self.assertFalse(row["trust_contract"]["treat_as_fact"])
        self.assertIn('"clean_source_mutation_allowed": false', raw)

    def test_load_self_notes_diagnostics_reports_jsonl_loss(self) -> None:
        notes = self._notes_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-self-notes.jsonl"
            valid = notes.build_agent_self_note_row(
                note_text="Short self note for diagnostics.",
                thread_key="session:old",
                source_refs=[],
            )
            path.write_text(
                json.dumps(valid, ensure_ascii=False) + "\n"
                "{bad-json}\n"
                + json.dumps(["not", "an", "object"], ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )

            rows = notes.load_agent_self_notes(path)
            diagnostics = notes.load_agent_self_notes_diagnostics(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(diagnostics["row_count"], 1)
        self.assertEqual(diagnostics["jsonl_loss"]["invalid_json_line_count"], 1)
        self.assertEqual(diagnostics["jsonl_loss"]["non_object_line_count"], 1)

    def test_long_self_note_keeps_private_body_but_compact_projection(self) -> None:
        notes = self._notes_module()
        long_note = (
            "opening posture: be bold about the observed magic, "
            + "but keep the source boundary explicit; " * 14
            + "tail marker: do not turn atmosphere into evidence."
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-self-notes.jsonl"

            row = notes.append_agent_self_note(
                path,
                note_text=long_note,
                thread_key="session:old",
                source_refs=[{"thread_key": "session:old", "message_id": "msg-long"}],
            )

        self.assertLessEqual(len(row["note_text"]), notes.AGENT_SELF_NOTE_PROJECTION_MAX_CHARS)
        self.assertTrue(row["note_text"].endswith("..."))
        self.assertIn("note_body_private", row)
        self.assertGreater(len(row["note_body_private"]), notes.AGENT_SELF_NOTE_PROJECTION_MAX_CHARS)
        self.assertIn("tail marker", row["note_body_private"])
        self.assertFalse(row["note_body_private_default_visible"])
        self.assertTrue(row["note_body_private_reopen_required"])
        self.assertEqual(row["action_grammar"], "direction_only")
        self.assertFalse(row["trust_contract"]["treat_as_fact"])

    def test_active_recall_surface_omits_private_body_by_default(self) -> None:
        notes = self._notes_module()
        from aippocampus_runtime.recall import active_recall

        long_note = (
            "recoverable posture: keep the foreground note small, "
            + "private nuance stays behind a reopen boundary; " * 14
            + "hidden tail marker should not be injected."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            notes.append_agent_self_note(
                notes_path,
                note_text=long_note,
                thread_key="session:old",
                source_refs=[{"thread_key": "session:old", "message_id": "msg-long"}],
            )

            payload = active_recall.active_recall_context(
                prompt="我想找回上次前的状态",
                cwd=root,
                agent_self_notes_path=notes_path,
                working_memory_path=root / "missing-working-memory.jsonl",
            )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["surface_counts"]["agent_self_notes"], 1)
        self.assertIn("note_text", payload["memory_atmosphere"][0])
        self.assertNotIn('"note_body_private":', serialized)
        self.assertNotIn("hidden tail marker should not be injected", serialized)

    def test_sensitive_and_raw_payload_material_is_rejected_or_redacted(self) -> None:
        notes = self._notes_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "agent-self-notes.jsonl"

            with self.assertRaises(notes.AgentSelfNoteRejected):
                notes.append_agent_self_note(
                    path,
                    note_text="token=super-secret",
                    thread_key="session:old",
                    source_refs=[],
                )

            row = notes.append_agent_self_note(
                path,
                note_text=r"我刚才差点把 E:\private\workspace\notes.md 当成公共材料。",
                thread_key="session:old",
                source_refs=[{"thread_key": "session:old", "message_id": "msg-8"}],
            )
            raw = path.read_text(encoding="utf-8")

        self.assertIn("<redacted:local-path>", row["note_text"])
        self.assertNotIn(r"E:\private\workspace\notes.md", raw)
        self.assertTrue(row["redaction_policy"]["redacted"])

    def test_search_returns_self_notes_as_memory_atmosphere_not_evidence(self) -> None:
        notes = self._notes_module()
        row = notes.build_agent_self_note_row(
            note_text="这次的状态是先承认还没看完，再去翻文档。",
            thread_key="session:old",
            source_refs=[{"thread_key": "session:old", "message_id": "msg-9", "line": 44}],
            trigger="explicit_agent_reflection",
            created_at="2026-06-07T00:01:00Z",
        )

        matches = notes.search_agent_self_notes(
            "我想找回上次我在这个问题前的状态",
            [row],
        )

        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match["active_recall_surface"], "agent_self_note")
        self.assertEqual(match["retrieval_role"], "memory_atmosphere")
        self.assertEqual(match["action_grammar"], "direction_only")
        self.assertFalse(match["trust_contract"]["agent_may_answer_within_scope"])
        self.assertFalse(match["trust_contract"]["treat_as_fact"])
        self.assertTrue(match["source_boundary"]["self_note_is_not_source_fact"])
        self.assertTrue(match["source_boundary"]["source_refs_are_reopen_routes_not_proof_of_note"])
        self.assertNotEqual(match["action_grammar"], "bounded_evidence")

        serialized = json.dumps(matches, ensure_ascii=False)
        self.assertNotIn("source_open", serialized)

    def test_search_does_not_match_foreground_boilerplate_without_note_content(self) -> None:
        notes = self._notes_module()
        relevant = notes.build_agent_self_note_row(
            note_text="Short agent note: test foreground sidenote UX.",
            thread_key="session:old",
            source_refs=[],
            created_at="2026-06-07T00:01:00Z",
        )
        long_irrelevant = notes.build_agent_self_note_row(
            note_text="L" * 600,
            thread_key="session:old",
            source_refs=[],
            created_at="2026-06-07T00:02:00Z",
        )
        stdin_irrelevant = notes.build_agent_self_note_row(
            note_text="line one line two",
            thread_key="session:old",
            source_refs=[],
            created_at="2026-06-07T00:03:00Z",
        )

        matches = notes.search_agent_self_notes(
            "foreground sidenote",
            [relevant, long_irrelevant, stdin_irrelevant],
        )

        self.assertEqual([match["note_id"] for match in matches], [relevant["note_id"]])

    def test_append_cli_source_less_receipt_makes_weak_boundary_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = agent_self_note_cli.main(
                    [
                        "append",
                        "--cwd",
                        str(root),
                        "--notes-path",
                        str(notes_path),
                        "short margin note for future posture",
                        "--json",
                    ]
                )
            payload = json.loads(stdout.getvalue())

            human_stdout = io.StringIO()
            with contextlib.redirect_stdout(human_stdout):
                human_code = agent_self_note_cli.main(
                    [
                        "append",
                        "--cwd",
                        str(root),
                        "--notes-path",
                        str(notes_path),
                        "another margin note",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertFalse(payload["source_ref_attached"])
        self.assertEqual(payload["note"]["support_level"], "scent")
        self.assertEqual(payload["note"]["authority"], "direction_only")
        self.assertEqual(payload["note"]["truth_boundary"], "agent_self_note_not_source_fact")
        self.assertTrue(payload["source_boundary"]["self_note_is_not_source_fact"])
        self.assertTrue(payload["source_boundary"]["source_reopen_required_before_claim"])
        action_text = json.dumps(payload.get("foreground_action", {}), ensure_ascii=False)
        self.assertIn("--current-thread", action_text)
        self.assertEqual(human_code, 0)
        human = human_stdout.getvalue()
        self.assertIn("source refs: 0", human)
        self.assertIn("not source-backed", human)

    def test_append_help_explains_when_to_use_and_when_not_to_use(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = agent_self_note_cli.main(["append", "--help"])

        help_text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("When to use", help_text)
        self.assertIn("When not to use", help_text)
        self.assertIn("short voluntary foreground-agent margin notes", help_text)
        self.assertIn("facts, user profile claims, durable lessons", help_text)
        self.assertIn("source-backed learning", help_text)

    def test_append_empty_json_returns_structured_recovery_actions(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = agent_self_note_cli.main(["append", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["error"]["code"], "agent_self_note_empty")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["id"], "append_direction_only_note")
        self.assertEqual(payload["foreground_action"]["requires"], ["note_text"])
        self.assertIn("command_template", payload["foreground_action"])
        self.assertIn(
            "use_source_backed_recall_instead",
            [action["id"] for action in payload["safe_next_actions"]],
        )
        self.assertIn("safe_next_actions", payload)
        self.assertNotIn("recovery_actions", payload)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("<cue>", encoded)

    def test_bare_self_note_json_returns_structured_chooser_action(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = agent_self_note_cli.main(["--json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["error"]["code"], "self_note_command_required")
        self.assertNotIn("agent_next_action", payload)
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["id"], "list_direction_only_notes")
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
        self.assertEqual(
            [choice["label"] for choice in payload["choices"]],
            ["list", "search", "append", "read"],
        )
        self.assertEqual(payload["choices"][2]["id"], "append_direction_only_note")
        self.assertIn("write", payload["choices"][2]["mutation_risk"])

if __name__ == "__main__":
    unittest.main()
