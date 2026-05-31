from __future__ import annotations

import contextlib
import io
import json
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

import dream_input_pack as input_pack  # noqa: E402
from aippocampus_runtime.dream import queue as dream_queue  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def question_link_row() -> dict[str, object]:
    refs = [source_ref("session:q-a", "msg-a", 10), source_ref("session:q-b", "msg-b", 20)]
    return {
        "kind": "question_link",
        "finding_kind": "question_link",
        "fingerprint": "sf_question_link",
        "title": "Question continuity: continuity after compaction",
        "summary": "Tracked two source-backed question candidates as recurring.",
        "concepts": ["continuity", "compaction"],
        "source_refs": refs,
        "linked_questions": [
            {"question_text": "How does continuity survive compaction?", "source_refs": [refs[0]]},
            {"question_text": "Why should source refs survive?", "source_refs": [refs[1]]},
        ],
    }


def correction_row() -> dict[str, object]:
    return {
        "kind": "correction_outcome_event",
        "event_id": "out_queue",
        "activation_event_id": "act_queue",
        "target_type": "route",
        "adoption_signal": "adopted",
        "outcome_summary": "A source-backed correction changed the route.",
        "source_refs": [source_ref("session:corr", "msg-corr", 30)],
    }


def ambient_residue_row() -> dict[str, object]:
    return {
        "kind": "aippocampus_ambient_residue",
        "status": "dream_seed",
        "residue_id": "ares_queue",
        "themes": ["quiet residue"],
        "source_ref_fingerprints": ["weak-src"],
    }


def ready_pack(*rows: dict[str, object]) -> dict[str, object]:
    return input_pack.build_dream_input_pack(rows or [question_link_row()])


class DreamQueueTests(unittest.TestCase):
    def test_ready_pack_enqueues_bounded_detached_items(self) -> None:
        pack = ready_pack(question_link_row())

        payload = dream_queue.build_dream_queue([pack], now="2026-05-30T00:00:00Z")

        self.assertEqual(payload["kind"], "aippocampus_dream_queue")
        self.assertEqual(payload["counts"]["queued"], 2)
        self.assertEqual(payload["counts"]["skipped_duplicate"], 0)
        self.assertEqual([item["dream_function"] for item in payload["items"]], ["compensatory", "amplification"])
        first = payload["items"][0]
        self.assertEqual(first["pack_id"], pack["pack_id"])
        self.assertEqual(first["trigger_family"], "ready_source_pack")
        self.assertEqual(first["execution_mode"], "detached_background")
        self.assertFalse(first["foreground_eligible"])
        self.assertFalse(first["live_model_allowed_in_foreground"])
        self.assertEqual(first["cache_contract"], "deepseek_prefix_v1")
        self.assertEqual(
            first["prompt_order"],
            ["stable_dream_worker_contract", "source_pack_payload", "variable_run_directive"],
        )
        self.assertGreater(first["cost_budget"]["max_model_calls"], 0)
        self.assertTrue(first["expires_at"].endswith("Z"))
        self.assertTrue(first["dedup_key"].startswith("dream_dedup_"))

    def test_trigger_family_prefers_correction_and_residue_context(self) -> None:
        correction_pack = ready_pack(correction_row(), question_link_row())
        residue_pack = ready_pack(ambient_residue_row(), question_link_row())

        payload = dream_queue.build_dream_queue(
            [correction_pack, residue_pack],
            now="2026-05-30T00:00:00Z",
        )
        families = {item["pack_id"]: item["trigger_family"] for item in payload["items"]}

        self.assertEqual(families[correction_pack["pack_id"]], "correction_outcome")
        self.assertEqual(families[residue_pack["pack_id"]], "topic_epoch_residue")
        self.assertEqual(payload["counts"]["trigger_families"]["correction_outcome"], 2)
        self.assertEqual(payload["counts"]["trigger_families"]["topic_epoch_residue"], 2)

    def test_dedup_suppresses_previous_queue_and_adjudicated_findings(self) -> None:
        pack = ready_pack(question_link_row())
        first = dream_queue.build_dream_queue([pack], now="2026-05-30T00:00:00Z")
        previous_amp = next(item for item in first["items"] if item["dream_function"] == "amplification")
        existing_compensatory = {
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "source_pack_id": pack["pack_id"],
            "review_state": "agent_adjudicated",
        }

        payload = dream_queue.build_dream_queue(
            [pack],
            previous_items=[previous_amp],
            existing_findings=[existing_compensatory],
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["counts"]["queued"], 0)
        self.assertEqual(payload["counts"]["skipped_duplicate"], 2)
        reasons = {item["reason"] for item in payload["skipped_items"]}
        self.assertEqual(reasons, {"previous_queue", "existing_adjudicated_finding"})

    def test_parked_findings_suppress_regenerating_same_hypothesis(self) -> None:
        pack = ready_pack(question_link_row())
        parked = {
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "source_pack_id": pack["pack_id"],
            "review_state": "needs_review",
            "adjudication_result": {"status": "parked"},
        }

        payload = dream_queue.build_dream_queue(
            [pack],
            existing_findings=[parked],
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(payload["counts"]["parked_findings"], 1)
        self.assertEqual(payload["counts"]["skipped_duplicate"], 1)
        self.assertNotIn("compensatory", [item["dream_function"] for item in payload["items"]])
        self.assertIn("amplification", [item["dream_function"] for item in payload["items"]])
        self.assertEqual(payload["skipped_items"][0]["reason"], "existing_parked_finding")

    def test_expired_completed_queue_item_does_not_suppress_new_work(self) -> None:
        pack = ready_pack(question_link_row())
        expired_completed = {
            "kind": "aippocampus_dream_queue_item",
            "queue_item_id": "dreamq_completed",
            "pack_id": pack["pack_id"],
            "dream_function": "compensatory",
            "status": "completed",
            "expires_at": "2026-05-29T00:00:00Z",
            "dedup_key": dream_queue.dedup_key_for(pack["pack_id"], "compensatory"),
        }

        payload = dream_queue.build_dream_queue(
            [pack],
            previous_items=[expired_completed],
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(payload["counts"]["expired"], 1)
        self.assertIn("compensatory", [item["dream_function"] for item in payload["items"]])

    def test_expired_queue_items_and_parked_findings_are_reported(self) -> None:
        expired_item = {
            "kind": "aippocampus_dream_queue_item",
            "queue_item_id": "dreamq_old",
            "pack_id": "old_pack",
            "dream_function": "compensatory",
            "status": "queued",
            "expires_at": "2026-05-29T00:00:00Z",
            "dedup_key": "dream_dedup_old",
        }
        parked = {
            "finding_kind": "dream_synthesized",
            "dream_function": "amplification",
            "source_pack_id": "old_pack",
            "review_state": "needs_review",
            "adjudication_result": {"status": "parked"},
        }

        payload = dream_queue.build_dream_queue(
            [],
            previous_items=[expired_item],
            existing_findings=[parked],
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(payload["counts"]["expired"], 1)
        self.assertEqual(payload["counts"]["parked_findings"], 1)
        self.assertEqual(payload["expired_items"][0]["status"], "expired")
        self.assertEqual(payload["expired_items"][0]["dedup_key"], "dream_dedup_old")

    def test_max_items_respects_global_trigger_priority_before_function_order(self) -> None:
        low_priority = ready_pack(question_link_row())
        high_priority = ready_pack(correction_row(), question_link_row())
        high_compensatory_done = {
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "source_pack_id": high_priority["pack_id"],
            "review_state": "agent_adjudicated",
        }

        payload = dream_queue.build_dream_queue(
            [low_priority, high_priority],
            existing_findings=[high_compensatory_done],
            now="2026-05-30T00:00:00Z",
            max_items=1,
        )

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["pack_id"], high_priority["pack_id"])
        self.assertEqual(payload["items"][0]["dream_function"], "amplification")
        self.assertEqual(payload["items"][0]["trigger_family"], "correction_outcome")

    def test_public_summary_reports_counts_without_private_refs(self) -> None:
        pack = ready_pack(question_link_row())

        payload = dream_queue.build_dream_queue([pack], now="2026-05-30T00:00:00Z")
        summary = dream_queue.public_queue_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["queued"], 2)
        self.assertIn("ready_source_pack", summary["trigger_families"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)

    def test_cli_summary_writes_aggregate_counts_without_source_refs(self) -> None:
        pack = ready_pack(question_link_row())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packs_path = root / "packs.jsonl"
            output_path = root / "summary.json"
            packs_path.write_text(json.dumps(pack, ensure_ascii=False) + "\n", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                code = dream_queue.main(
                    [
                        "--packs-jsonl",
                        str(packs_path),
                        "--summary",
                        "--json",
                        "--output",
                        str(output_path),
                        "--now",
                        "2026-05-30T00:00:00Z",
                    ]
                )
            summary = json.loads(output_path.read_text(encoding="utf-8"))
            encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertEqual(summary["queued"], 2)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)


if __name__ == "__main__":
    unittest.main()
