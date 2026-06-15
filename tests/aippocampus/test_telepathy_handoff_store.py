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
