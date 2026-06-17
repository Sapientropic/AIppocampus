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

from aippocampus_runtime.ops import telepathy_handoff_store  # noqa: E402


class TelepathyHandoffStoreTests(unittest.TestCase):
    def test_handoff_lifecycle_is_append_only_and_source_refs_stay_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            created = telepathy_handoff_store.create_handoff(
                scope="project:AIppocampus#issue:1287",
                owner="codex-a",
                source_support="reopenable_route",
                source_refs=[
                    {
                        "message_id": "msg_public",
                        "turn_id": "turn_public",
                        "path": str(root / "private-rollout.jsonl"),
                        "source": "source://private/raw-handle",
                    }
                ],
                store_path=store,
                cwd=root,
            )

            self.assertTrue(created["ok"], json.dumps(created, indent=2))
            card_id = created["card"]["card_id"]
            self.assertEqual(
                created["card"]["scope_label"],
                "project:AIppocampus#issue:1287",
            )
            self.assertEqual(
                created["card"]["scope_visibility"],
                "operator_supplied_public_safe",
            )
            self.assertEqual(len(store.read_text(encoding="utf-8").splitlines()), 1)

            listed = telepathy_handoff_store.list_handoffs_payload(store_path=store, cwd=root)
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["cards"][0]["card_id"], card_id)
            self.assertEqual(
                listed["cards"][0]["scope_label"],
                "project:AIppocampus#issue:1287",
            )
            self.assertEqual(listed["cards"][0]["claim_permission"], "navigation_only_not_fact")

            deepened = telepathy_handoff_store.deepen_handoff_payload(
                card_id=card_id,
                store_path=store,
                cwd=root,
            )
            encoded_source_refs = json.dumps(
                deepened["source_reopen"]["source_refs"],
                ensure_ascii=False,
                sort_keys=True,
            )
            self.assertTrue(deepened["ok"], json.dumps(deepened, indent=2))
            self.assertEqual(
                deepened["card"]["scope_label"],
                "project:AIppocampus#issue:1287",
            )
            self.assertIn("msg_public", encoded_source_refs)
            self.assertIn("source_ref_hash", encoded_source_refs)
            self.assertNotIn(str(root), encoded_source_refs)
            self.assertNotIn("source://private/raw-handle", encoded_source_refs)

            released = telepathy_handoff_store.release_handoff(
                card_id=card_id,
                store_path=store,
                cwd=root,
            )
            self.assertTrue(released["ok"], json.dumps(released, indent=2))
            self.assertEqual(len(store.read_text(encoding="utf-8").splitlines()), 2)
            self.assertEqual(
                telepathy_handoff_store.list_handoffs_payload(
                    store_path=store,
                    cwd=root,
                    status="active",
                )["count"],
                0,
            )
            self.assertEqual(
                telepathy_handoff_store.list_handoffs_payload(
                    store_path=store,
                    cwd=root,
                    status="released",
                )["count"],
                1,
            )

    def test_candidate_only_handoff_stays_navigation_only_in_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            created = telepathy_handoff_store.create_handoff(
                scope="project:AIppocampus#issue:candidate-only",
                owner="dream-scout",
                source_support="candidate_only",
                source_refs=[{"message_id": "msg_candidate"}],
                store_path=store,
                cwd=root,
            )
            card_id = created["card"]["card_id"]

            deepened = telepathy_handoff_store.deepen_handoff_payload(
                card_id=card_id,
                store_path=store,
                cwd=root,
            )
            diagnostic = telepathy_handoff_store.diagnose_handoffs_payload(
                store_path=store,
                cwd=root,
            )

            self.assertEqual(deepened["card"]["source_support"], "candidate_only")
            self.assertEqual(deepened["card"]["claim_permission"], "navigation_only_not_fact")
            self.assertEqual(deepened["card"]["next_safe_action"], "reopen_source_before_claim")
            self.assertEqual(diagnostic["red_lines"]["candidate_promoted_to_evidence_count"], 0)
            self.assertEqual(diagnostic["metrics"]["candidate_only_handoff_count"], 1)
            self.assertIn("source_truth_without_reopen", deepened["cannot_claim"])

    def test_cli_diagnose_human_output_is_handoff_status_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            telepathy_handoff_store.create_handoff(
                scope="project:AIppocampus#issue:candidate-only",
                owner="dream-scout",
                source_support="candidate_only",
                source_refs=[{"message_id": "msg_candidate"}],
                store_path=store,
                cwd=root,
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "diagnose",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("AIppocampus Telepathy handoff status", proc.stdout)
        self.assertIn("active: 1", proc.stdout)
        self.assertIn("candidate-only: 1", proc.stdout)
        self.assertIn("write mode: no_write_diagnostic_only", proc.stdout)
        self.assertIn("authority: navigation_only", proc.stdout)
        self.assertIn("reopen before reliance", proc.stdout)
        self.assertNotIn("aippocampus_telepathy_handoff_diagnostic: ok", proc.stdout)

    def test_cli_create_and_list_emit_public_safe_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            source_refs = json.dumps(
                [
                    {
                        "message_id": "msg_public",
                        "path": str(root / "private-rollout.jsonl"),
                    }
                ],
                ensure_ascii=False,
            )
            create_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "create",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                    "--scope",
                    "project:AIppocampus#issue:1287",
                    "--owner",
                    "codex-a",
                    "--source-ref-json",
                    source_refs,
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            create_payload = json.loads(create_proc.stdout)
            card_id = create_payload["card"]["card_id"]
            self.assertEqual(
                create_payload["card"]["scope_label"],
                "project:AIppocampus#issue:1287",
            )

            list_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "list",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            raw_output = create_proc.stdout + list_proc.stdout
            self.assertEqual(list_proc.returncode, 0, list_proc.stdout + list_proc.stderr)
            self.assertEqual(json.loads(list_proc.stdout)["cards"][0]["card_id"], card_id)
            self.assertNotIn(str(root), raw_output)
            self.assertNotIn("private-rollout.jsonl", raw_output)

    def test_cli_list_empty_state_tells_agent_what_to_do_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            json_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "list",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            text_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "list",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            bare_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(json_proc.returncode, 0, json_proc.stdout + json_proc.stderr)
            self.assertEqual(text_proc.returncode, 0, text_proc.stdout + text_proc.stderr)
            self.assertEqual(bare_proc.returncode, 2, bare_proc.stdout + bare_proc.stderr)
            payload = json.loads(json_proc.stdout)
            self.assertEqual(payload["count"], 0)
            self.assertEqual(
                payload["empty_state"]["state"],
                "no_matching_telepathy_handoffs",
            )
            self.assertEqual(
                payload["empty_state"]["agent_next_action"]["id"],
                "continue_with_normal_recall",
            )
            action_ids = [
                action["id"]
                for action in payload["empty_state"]["safe_next_actions"]
            ]
            self.assertIn("continue_with_normal_recall", action_ids)
            self.assertIn("create_explicit_handoff", action_ids)
            self.assertNotIn("create_examples", payload["empty_state"])
            self.assertIn("next:", text_proc.stdout)
            self.assertIn("telepathy create --preset handoff", text_proc.stdout)
            self.assertNotIn("{'", text_proc.stdout)
            self.assertIn("next: aippocampus telepathy list --json", bare_proc.stdout)
            self.assertNotIn("{'", bare_proc.stdout)

    def test_cli_create_preset_human_needed_hides_internal_enums_from_first_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            help_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "create",
                    "--help",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            create_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "create",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                    "--preset",
                    "human-needed",
                    "--scope",
                    "release decision",
                    "--owner",
                    "codex-a",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(help_proc.returncode, 0, help_proc.stdout + help_proc.stderr)
            self.assertIn("Preset examples", help_proc.stdout)
            self.assertIn("Advanced/operator schema flags", help_proc.stdout)
            self.assertIn("--preset", help_proc.stdout)
            self.assertIn("human-needed", help_proc.stdout)
            self.assertLess(
                help_proc.stdout.index("Preset examples"),
                help_proc.stdout.index("--coordination-mode"),
            )
            self.assertLess(
                help_proc.stdout.index("Advanced/operator schema flags"),
                help_proc.stdout.index("--coordination-mode"),
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            payload = json.loads(create_proc.stdout)
            self.assertEqual(payload["card"]["coordination_mode"], "human_needed")
            self.assertEqual(payload["card"]["status"], "blocked")
            self.assertEqual(payload["card"]["next_safe_action"], "ask_human_before_handoff")

    def test_read_alias_and_not_found_error_are_action_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            created = telepathy_handoff_store.create_handoff(
                scope="issue:#123",
                owner="codex-a",
                store_path=store,
                cwd=root,
            )
            read_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "read",
                    created["card"]["card_id"],
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            missing_json = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "read",
                    "missing-card",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            missing_text = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "telepathy",
                    "read",
                    "missing-card",
                    "--cwd",
                    str(root),
                    "--store-path",
                    str(store),
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(read_proc.returncode, 0, read_proc.stdout + read_proc.stderr)
        read_payload = json.loads(read_proc.stdout)
        self.assertEqual(read_payload["kind"], telepathy_handoff_store.DEEPEN_KIND)
        self.assertEqual(read_payload["card"]["card_id"], created["card"]["card_id"])
        self.assertEqual(missing_json.returncode, 1)
        missing_payload = json.loads(missing_json.stdout)
        self.assertEqual(missing_payload["error"]["code"], "handoff_not_found")
        self.assertIn("telepathy list --status all", missing_payload["agent_next_action"])
        self.assertIn("next:", missing_text.stdout)
        self.assertIn("telepathy list --status all", missing_text.stdout)

    def test_private_or_path_like_scope_uses_hash_only_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "handoffs.jsonl"
            private_scope = str(root / "private-scope.jsonl")

            created = telepathy_handoff_store.create_handoff(
                scope=private_scope,
                owner="codex-a",
                store_path=store,
                cwd=root,
            )
            listed = telepathy_handoff_store.list_handoffs_payload(store_path=store, cwd=root)
            deepened = telepathy_handoff_store.deepen_handoff_payload(
                card_id=created["card"]["card_id"],
                store_path=store,
                cwd=root,
            )

            encoded = json.dumps([created, listed, deepened], ensure_ascii=False, sort_keys=True)

        self.assertEqual(created["card"]["scope_visibility"], "redacted_hash_only")
        self.assertEqual(listed["cards"][0]["scope_visibility"], "redacted_hash_only")
        self.assertEqual(deepened["card"]["scope_visibility"], "redacted_hash_only")
        self.assertNotIn("private-scope.jsonl", encoded)
        self.assertNotIn(private_scope, encoded)


if __name__ == "__main__":
    unittest.main()
