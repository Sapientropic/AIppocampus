from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from aippocampus_runtime.recall import ambient_cache as cache
from aippocampus_runtime.recall import ambient_cache_compaction as compaction
from aippocampus_runtime.recall.ambient_cards import ambient_recall_from_decision


class AmbientThreadCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cache_fingerprints_use_sha256(self) -> None:
        self.assertEqual(
            cache._fingerprint("Thread A", prefix="atc"),
            "atc_" + hashlib.sha256("thread a".encode("utf-8")).hexdigest()[:16],
        )

    def test_thread_cache_reuses_cards_without_raw_prompt_or_workspace_text(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        card = {
            "card_id": "arc_1",
            "theme": "continuity",
            "support_level": "scent",
            "source_refs": [{"thread_key": "session:old"}],
        }

        written = cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-1",
            cards=[card],
            mode="active_gentle_nudge",
            confidence="medium",
        )
        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-1",
        )
        raw = cache_path.read_text(encoding="utf-8")

        self.assertEqual(written["status"], "written")
        self.assertEqual(loaded["status"], "hit")
        self.assertEqual(loaded["cards"][0]["theme"], "continuity")
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("prompt", raw.casefold())

    def test_no_source_self_echo_cards_are_silent_residue_not_active_nudges(self) -> None:
        ambient = ambient_recall_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [
                    {
                        "title": "刚刚对你有帮助吗",
                        "matched_terms": ["刚刚对你有帮助吗"],
                    }
                ],
            },
            prompt="刚刚对你有帮助吗",
        )

        self.assertEqual(ambient["mode"], "silent_tuning")
        self.assertEqual(ambient["cards"][0]["visibility"], "silent_tuning")
        self.assertEqual(ambient["cards"][0]["source_refs"], [])
        self.assertEqual(ambient["cards"][0]["foreground_residue_reason"], "no_source_ref_or_reopen_plan")
        self.assertEqual(ambient["brief_precision"]["no_ref_active_card_count"], 1)
        self.assertEqual(ambient["brief_precision"]["no_ref_residue_count"], 1)
        self.assertEqual(ambient["brief_precision"]["self_echo_suppressed_count"], 1)

    def test_candidate_with_thread_key_remains_active_reopenable_navigation(self) -> None:
        ambient = ambient_recall_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [
                    {
                        "title": "机械飞升源头",
                        "thread_key": "session:mechanical",
                        "message_id": "msg-1",
                        "matched_terms": ["机械飞升", "海马体"],
                    }
                ],
            },
            prompt="机械飞升和海马体",
        )

        self.assertEqual(ambient["mode"], "active_gentle_nudge")
        self.assertEqual(ambient["cards"][0]["source_refs"][0]["thread_key"], "session:mechanical")
        self.assertEqual(ambient["brief_precision"]["no_ref_active_card_count"], 0)

    def test_thread_cache_key_canonicalizes_equivalent_posix_workspace_paths(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        workspace = self.root / "workspace"
        workspace.mkdir()
        alias = self.root / "workspace-alias"
        try:
            os.symlink(workspace, alias)
        except (AttributeError, NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(alias),
            topic_epoch="epoch-path",
            cards=[{"card_id": "arc_path", "theme": "path alias"}],
        )
        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(workspace.resolve()),
            topic_epoch="epoch-path",
        )

        self.assertEqual(loaded["status"], "hit")
        self.assertEqual(loaded["cards"][0]["card_id"], "arc_path")

    def test_related_thread_cache_canonicalizes_workspace_fingerprint(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        workspace = self.root / "workspace"
        workspace.mkdir()
        alias = self.root / "workspace-alias"
        try:
            os.symlink(workspace, alias)
        except (AttributeError, NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        signals = cache.related_signal_fingerprints(
            candidates=[{"thread_key": "session:old-topic"}],
        )

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(alias),
            topic_epoch="epoch-first-phrasing",
            cards=[{"card_id": "arc_related_path", "theme": "path alias"}],
            related_fingerprints=signals,
        )
        related = cache.read_related_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(workspace.resolve()),
            topic_epoch="epoch-natural-paraphrase",
            related_fingerprints=signals,
        )

        self.assertEqual(related["status"], "related_hit")
        self.assertEqual(related["cards"][0]["card_id"], "arc_related_path")

    def test_thread_cache_normalizes_workspace_before_keying(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        workspace = self.root / "workspace"
        workspace.mkdir()
        card = {
            "card_id": "arc_normalized",
            "theme": "normalized workspace",
            "support_level": "candidate",
        }

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(workspace),
            topic_epoch="epoch-normalized",
            cards=[card],
        )
        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(workspace / ".." / "workspace"),
            topic_epoch="epoch-normalized",
        )

        self.assertEqual(loaded["status"], "hit")
        self.assertEqual(loaded["cards"][0]["card_id"], "arc_normalized")

    def test_thread_cache_preserves_validation_and_topic_metadata(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        card = {
            "card_id": "arc_validation",
            "theme": "validated ambient recall",
            "support_level": "evidence",
            "provenance_class": "source_backed_reopen",
            "source_reopen_required": True,
            "reopenable_ref_count": 1,
            "source_refs": [{"thread_key": "session:old", "line": 42, "message_id": "msg-1"}],
            "source_validation": {
                "status": "supported",
                "checked_ref_count": 1,
                "supported_ref_count": 1,
            },
        }

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-validation",
            cards=[card],
            mode="source_backed_recall_card",
            confidence="high",
            query_aliases=["ambient recall", "warm scout"],
            topic_epoch_decision={"action": "rotate", "label": "ambient recall", "confidence": 0.8},
            visibility_bias="source_backed_recall_card",
        )
        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-validation",
        )
        raw = cache_path.read_text(encoding="utf-8")

        self.assertEqual(loaded["status"], "hit")
        self.assertEqual(loaded["cards"][0]["source_validation"]["status"], "supported")
        self.assertEqual(loaded["cards"][0]["provenance_class"], "source_backed_reopen")
        self.assertTrue(loaded["cards"][0]["source_reopen_required"])
        self.assertEqual(loaded["cards"][0]["reopenable_ref_count"], 1)
        self.assertEqual(loaded["query_aliases"], ["ambient recall", "warm scout"])
        self.assertEqual(loaded["topic_epoch_decision"]["action"], "rotate")
        self.assertEqual(loaded["visibility_bias"], "source_backed_recall_card")
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("prompt", raw.casefold())

    def test_cache_entry_expires(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-1",
            cards=[{"card_id": "arc_1", "theme": "old"}],
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        first_key = next(iter(data["entries"]))
        data["entries"][first_key]["updated_unix"] = time.time() - 100
        cache_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-1",
            ttl_seconds=1,
        )

        self.assertEqual(loaded["status"], "expired")
        self.assertEqual(loaded["cards"], [])

    def test_related_thread_cache_uses_stable_candidate_fingerprints_after_exact_miss(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        signals = cache.related_signal_fingerprints(
            candidates=[{"thread_key": "session:old-topic"}],
        )
        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-first-phrasing",
            cards=[
                {
                    "card_id": "arc_related",
                    "theme": "same source-backed candidate",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                }
            ],
            related_fingerprints=signals,
            topic_epoch_decision={
                "action": "reuse",
                "label": "same source-backed candidate cluster",
            },
        )

        exact = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-natural-paraphrase",
        )
        related = cache.read_related_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-natural-paraphrase",
            related_fingerprints=signals,
        )
        raw = cache_path.read_text(encoding="utf-8")

        self.assertEqual(exact["status"], "miss")
        self.assertEqual(related["status"], "related_hit")
        self.assertEqual(related["topic_epoch"], "epoch-natural-paraphrase")
        self.assertEqual(related["matched_topic_epoch"], "epoch-first-phrasing")
        self.assertEqual(related["cards"][0]["card_id"], "arc_related")
        self.assertGreaterEqual(related["related_overlap_count"], 1)
        self.assertNotIn("old-topic", raw)
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))

    def test_related_thread_cache_rejects_same_session_different_candidate(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-old",
            cards=[{"card_id": "arc_old", "theme": "old candidate"}],
            related_fingerprints=cache.related_signal_fingerprints(
                candidates=[{"thread_key": "session:old-topic"}],
            ),
        )

        related = cache.read_related_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-new",
            related_fingerprints=cache.related_signal_fingerprints(
                candidates=[{"thread_key": "session:different-topic"}],
            ),
        )

        self.assertEqual(related["status"], "miss")
        self.assertEqual(related["cards"], [])

    def test_related_thread_cache_downgrades_cached_evidence_without_source_overlap(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        signals = cache.related_signal_fingerprints(
            candidates=[{"thread_key": "session:old-topic"}],
        )
        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-old",
            cards=[
                {
                    "card_id": "arc_evidence",
                    "theme": "old sourced detail",
                    "support_level": "evidence",
                    "visibility": "source_backed_recall_card",
                    "provenance_class": "source_backed_reopen",
                    "source_reopen_required": True,
                    "reopenable_ref_count": 1,
                    "source_refs": [
                        {"thread_key": "session:old-topic", "line": 42, "message_id": "msg-1"}
                    ],
                }
            ],
            related_fingerprints=signals,
        )

        related = cache.read_related_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-new",
            related_fingerprints=signals,
        )

        self.assertEqual(related["status"], "related_hit")
        self.assertEqual(related["cards"][0]["support_level"], "candidate")
        self.assertEqual(related["cards"][0]["visibility"], "active_gentle_nudge")
        self.assertEqual(related["cards"][0]["provenance_class"], "cached_warm_card")
        self.assertEqual(related["cards"][0]["cached_origin"], "source_backed_reopen")
        self.assertTrue(related["cards"][0]["source_reopen_required"])

    def test_topic_epoch_is_stable_without_raw_prompt_text(self) -> None:
        first = cache.topic_epoch_from_terms(["ambient recall", "Card/cache", "ambient"])
        second = cache.topic_epoch_from_terms(["ambient", "Card/cache", "ambient recall"])
        different = cache.topic_epoch_from_terms(["routine coding", "button"])

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertTrue(first.startswith("epoch_"))

    def test_topic_signal_accumulator_keeps_hashes_without_raw_prompt_text(self) -> None:
        signal_path = self.root / "ambient-signal-accumulator.json"
        raw_prompt = "候选 source refs 的中间层和过度保守这个问题"
        terms = [raw_prompt, "AIppocampus recall"]

        for _ in range(3):
            written = cache.record_topic_signal(
                signal_path,
                thread_id="thread-a",
                workspace="E:/private/workspace",
                topic_epoch="epoch-signal",
                terms=terms,
                outcome="weak_signal",
                reason_codes=["below_threshold"],
            )

        state = cache.read_topic_signal_state(
            signal_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-signal",
            terms=terms,
        )
        raw = signal_path.read_text(encoding="utf-8")

        self.assertEqual(written["status"], "written")
        self.assertEqual(state["status"], "hit")
        self.assertEqual(state["weak_signal_count"], 3)
        self.assertEqual(state["positive_strength"], 3.0)
        self.assertEqual(state["negative_strength"], 0.0)
        self.assertTrue(state["topic_fingerprint"].startswith("sig_"))
        self.assertNotIn(raw_prompt, raw)
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("thread-a", raw)

    def test_optional_residue_export_writes_dream_seed_without_raw_prompt_or_workspace(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        residue_path = self.root / "ambient-residue.jsonl"
        card = {
            "card_id": "arc_seed",
            "theme": "continuity after transformation",
            "support_level": "candidate",
            "visibility": "active_gentle_nudge",
            "source_refs": [{"thread_key": "session:old", "line": 42, "message_id": "msg-1"}],
        }

        result = cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-dream",
            cards=[card],
            residue_path=residue_path,
            residue_reason="topic_epoch_rotated",
        )
        rows = [
            json.loads(line)
            for line in residue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        raw = residue_path.read_text(encoding="utf-8")

        self.assertEqual(result["residue_export"]["status"], "written")
        self.assertEqual(rows[0]["kind"], "aippocampus_ambient_residue")
        self.assertEqual(rows[0]["status"], "dream_seed")
        self.assertEqual(rows[0]["reason"], "topic_epoch_rotated")
        self.assertEqual(rows[0]["topic_epoch"], "epoch-dream")
        self.assertEqual(rows[0]["card_ids"], ["arc_seed"])
        self.assertEqual(rows[0]["support_levels"], ["candidate"])
        self.assertIn("dream_task_seed", rows[0]["downstream_use"])
        self.assertTrue(rows[0]["source_ref_fingerprints"])
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("prompt", raw.casefold())

    def test_residue_export_skips_unsourced_single_scent(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        residue_path = self.root / "ambient-residue.jsonl"

        result = cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-scent",
            cards=[
                {
                    "card_id": "arc_scent",
                    "theme": "generic scent",
                    "support_level": "scent",
                    "visibility": "active_gentle_nudge",
                    "source_refs": [],
                }
            ],
            residue_path=residue_path,
            residue_reason="cache_expired",
        )

        self.assertEqual(result["residue_export"]["status"], "skipped_no_source_refs")
        self.assertFalse(residue_path.exists())

    def test_dead_letter_manifest_compacts_matching_ambient_card_payload(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        card_id = "arc_dead_lettered"
        surface_id_hash = hashlib.sha256(card_id.encode("utf-8")).hexdigest()[:16]

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-dead-letter",
            cards=[
                {
                    "card_id": card_id,
                    "theme": "raw activation theme should be compacted",
                    "key_line": "raw activation payload should be compacted",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "source_refs": [
                        {"thread_key": "session:old-topic", "line": 42, "message_id": "msg-1"}
                    ],
                    "source_validation": {"status": "supported", "checked_ref_count": 1},
                }
            ],
        )

        result = compaction.compact_ambient_cache_payloads_from_dead_letter_manifest(
            cache_path,
            {
                "kind": "aippocampus_activation_dead_letter_apply_manifest",
                "updates": [
                    {
                        "surface_id_hash": surface_id_hash,
                        "surface_kind": "ambient_card",
                        "lifecycle_action": "dead_lettered",
                        "source_ref_count": 1,
                        "provenance_pointer_hash": "prov123",
                        "reason_codes": ["wrong_route_drag_threshold"],
                        "applied_at": "2026-06-05T10:00:00Z",
                        "source_refs_preserved": True,
                        "clean_source_mutation": False,
                        "truth_status_changed": False,
                        "rebuild_or_review_note": "Rebuild from clean source if this card must be reviewed.",
                    }
                ],
            },
            compacted_at="2026-06-05T10:05:00Z",
        )
        stored = json.loads(cache_path.read_text(encoding="utf-8"))
        entry = next(iter(stored["entries"].values()))
        compacted_card = entry["cards"][0]
        raw = cache_path.read_text(encoding="utf-8")

        self.assertEqual(result["metrics"]["payload_compacted_count"], 1)
        self.assertEqual(result["compacted"][0]["surface_id_hash"], surface_id_hash)
        self.assertTrue(compacted_card["payload_compacted"])
        self.assertEqual(compacted_card["lifecycle_action"], "payload_compacted")
        self.assertEqual(compacted_card["source_ref_count"], 1)
        self.assertEqual(compacted_card["provenance_pointer_hash"], "prov123")
        self.assertEqual(entry["source_ref_fingerprints"], [])
        self.assertEqual(entry["related_fingerprints"], [])
        self.assertNotIn("theme", compacted_card)
        self.assertNotIn("key_line", compacted_card)
        self.assertNotIn("source_refs", compacted_card)
        self.assertNotIn(card_id, raw)
        self.assertNotIn("raw activation", raw)
        self.assertNotIn("session:old-topic", raw)

    def test_dead_letter_manifest_skips_unsafe_ambient_card_compaction(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        card_id = "arc_protected"
        surface_id_hash = hashlib.sha256(card_id.encode("utf-8")).hexdigest()[:16]

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-protected",
            cards=[
                {
                    "card_id": card_id,
                    "theme": "still needed for review",
                    "support_level": "candidate",
                    "source_refs": [{"thread_key": "session:review", "message_id": "msg-2"}],
                }
            ],
        )

        result = compaction.compact_ambient_cache_payloads_from_dead_letter_manifest(
            cache_path,
            {
                "kind": "aippocampus_activation_dead_letter_apply_manifest",
                "updates": [
                    {
                        "surface_id_hash": surface_id_hash,
                        "surface_kind": "ambient_card",
                        "lifecycle_action": "dead_lettered",
                        "source_ref_count": 1,
                        "reason_codes": ["wrong_route_drag_threshold"],
                        "protected_reference_count": 1,
                        "clean_source_mutation": False,
                        "truth_status_changed": False,
                    }
                ],
            },
            compacted_at="2026-06-05T10:05:00Z",
        )
        stored = json.loads(cache_path.read_text(encoding="utf-8"))
        entry = next(iter(stored["entries"].values()))

        self.assertEqual(result["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(result["skipped"][0]["skip_reason"], "unsafe_dead_letter_update")
        self.assertEqual(entry["cards"][0]["card_id"], card_id)
        self.assertEqual(entry["cards"][0]["theme"], "still needed for review")

if __name__ == "__main__":
    unittest.main()
