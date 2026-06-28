from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import prompt_cues
from aippocampus_runtime.recall import semantic_cue_cache as cues
from aippocampus_runtime.recall import semantic_recall_gate as semantic_gate
from aippocampus_runtime.recall.semantic import confidence_policy
from aippocampus_runtime.recall.semantic import cue_learning as semantic_cue_learning


class SemanticCueCacheTests(unittest.TestCase):
    def test_semantic_cue_cache_keys_use_sha256(self) -> None:
        prompt = "继续 外置海马体"
        cue = "外置海马体"
        route = "semantic_gate"
        normalized_prompt = " ".join(prompt.split())
        cue_material = f"{route}\n{cue.casefold()}"

        self.assertEqual(
            cues.prompt_hash(prompt),
            hashlib.sha256(normalized_prompt.encode("utf-8")).hexdigest()[:16],
        )
        self.assertEqual(
            cues.cue_key(cue, route),
            "sc_" + hashlib.sha256(cue_material.encode("utf-8")).hexdigest()[:18],
        )

    def test_repeated_source_backed_hits_promote_multilingual_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            semantic_result = {
                "available": True,
                "decision": "scent",
                "confidence": 0.86,
                "query_aliases": [
                    "memoria externa",
                    "外置海马体",
                    "внешний гиппокамп",
                    "ذاكرة سياقية",
                ],
            }
            source_refs = [
                {
                    "thread_key": "session:aippocampus",
                    "message_id": "m1",
                    "source_line": 12,
                }
            ]

            first = cues.record_semantic_cue_hits(
                cache_path,
                prompt="¿Seguimos con la memoria externa?",
                semantic_result=semantic_result,
                source_refs=source_refs,
                route="semantic_gate",
            )
            second = cues.record_semantic_cue_hits(
                cache_path,
                prompt="¿Puedes continuar esa memoria externa?",
                semantic_result=semantic_result,
                source_refs=source_refs,
                route="semantic_gate",
            )

            self.assertEqual(first["active_count"], 0)
            self.assertEqual(second["active_count"], 4)
            rows = cues.load_semantic_cues(cache_path)
            by_cue = {row["cue"]: row for row in rows}
            self.assertEqual(
                set(by_cue),
                {"memoria externa", "外置海马体", "внешний гиппокамп", "ذاكرة سياقية"},
            )
            self.assertEqual(by_cue["memoria externa"]["script"], "Latn")
            self.assertEqual(by_cue["外置海马体"]["script"], "Hani")
            self.assertEqual(by_cue["внешний гиппокамп"]["script"], "Cyrl")
            self.assertEqual(by_cue["ذاكرة سياقية"]["script"], "Arab")
            self.assertEqual(by_cue["memoria externa"]["training_role"], "positive_demo")
            self.assertEqual(
                by_cue["memoria externa"]["candidate_lifecycle_state"],
                "actionable_reopenable_route",
            )
            self.assertEqual(
                by_cue["memoria externa"]["trace_admission_level"],
                "reopenable_route",
            )
            self.assertIn(
                by_cue["外置海马体"]["learning_priority"]["bucket"],
                {"medium", "high_information"},
            )

            triggers = cues.semantic_cue_triggers(cache_path)
            trigger_aliases = {
                alias for trigger in triggers for alias in trigger.get("aliases") or []
            }
            self.assertIn("memoria externa", trigger_aliases)
            self.assertIn("внешний гиппокамп", trigger_aliases)

    def test_false_positive_pressure_keeps_noisy_cue_out_of_trigger_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            semantic_result = {
                "available": True,
                "decision": "scent",
                "confidence": 0.9,
                "query_aliases": ["generic continuity"],
            }
            source_refs = [{"thread_key": "session:aippocampus", "message_id": "m1"}]
            for _ in range(2):
                cues.record_semantic_cue_hits(
                    cache_path,
                    prompt="continue the generic continuity thread",
                    semantic_result=semantic_result,
                    source_refs=source_refs,
                    route="semantic_gate",
                )

            cues.record_semantic_cue_misses(
                cache_path,
                cues=["generic continuity"],
                reason="matched an unrelated project",
            )
            cues.record_semantic_cue_misses(
                cache_path,
                cues=["generic continuity"],
                reason="matched an unrelated project again",
            )

            triggers = cues.semantic_cue_triggers(cache_path)

            self.assertEqual(triggers, [])

    def test_recall_source_open_cue_promotes_and_demotes_route_locally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            refs = [{"thread_key": "session:hot", "message_id": "msg-hot", "line": 12}]
            query = "小海马体 transport hot reload source anchor SECRET_TOKEN=abc"

            first = semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query=query,
                source_refs=refs,
                route_id="route:hot-reload",
            )
            second = semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query="小海马体 transport hot reload source anchor",
                source_refs=refs,
                route_id="route:hot-reload",
            )

            self.assertEqual(first["active_count"], 0)
            self.assertGreater(second["active_count"], 0)
            active = cues.load_semantic_cues(cache_path)
            self.assertGreaterEqual(len(active), 1)
            self.assertTrue(all(row["alias_source"] == "agent_recall_source_open" for row in active))
            self.assertTrue(all(row["source_reopen_required_before_claim"] for row in active))
            self.assertTrue(all(row["training_role"] == "positive_demo" for row in active))
            self.assertTrue(all(row["source_refs"] for row in active))

            demoted = semantic_cue_learning.demote_recall_cue_route(
                cache_path,
                route_id="route:hot-reload",
                reason="wrong_route_drag",
                preferred_route_id="route:better",
            )
            suppressed = cues.all_semantic_cues(cache_path)
            encoded = json.dumps(suppressed, ensure_ascii=False)

            self.assertGreater(demoted["updated_count"], 0)
            self.assertEqual(cues.semantic_cue_triggers(cache_path), [])
            self.assertTrue(all(row["status"] == "suppressed_hard_negative" for row in suppressed))
            self.assertTrue(all(row["training_role"] == "hard_negative" for row in suppressed))
            self.assertIn("msg-hot", encoded)
            self.assertNotIn("SECRET_TOKEN", encoded)
            self.assertNotIn("abc", encoded)

            restored = semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query="小海马体 transport hot reload source anchor",
                source_refs=refs,
                route_id="route:hot-reload",
            )

            self.assertGreater(restored["active_count"], 0)
            self.assertGreater(len(cues.semantic_cue_triggers(cache_path)), 0)

    def test_alternating_recall_cue_feedback_requires_net_score_before_foreground(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            refs = [{"thread_key": "session:hot", "message_id": "msg-hot", "line": 12}]

            semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query="transport hot reload anchor",
                source_refs=refs,
                route_id="route:hot-reload",
            )
            semantic_cue_learning.demote_recall_cue_route(
                cache_path,
                route_id="route:hot-reload",
                reason="wrong_route_drag",
            )
            semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query="transport hot reload anchor",
                source_refs=refs,
                route_id="route:hot-reload",
            )
            semantic_cue_learning.demote_recall_cue_route(
                cache_path,
                route_id="route:hot-reload",
                reason="wrong_route_drag",
            )
            final = semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query="transport hot reload anchor",
                source_refs=refs,
                route_id="route:hot-reload",
            )
            rows = cues.all_semantic_cues(cache_path)

            self.assertEqual(final["active_count"], 0)
            self.assertEqual(cues.semantic_cue_triggers(cache_path), [])
            self.assertTrue(all(row["status"] == "staging" for row in rows))
            self.assertEqual({row["feedback_score"] for row in rows}, {1})
            self.assertTrue(
                all(
                    row["active_feedback_score_threshold"]
                    == cues.MIN_ACTIVE_CUE_FEEDBACK_SCORE
                    for row in rows
                )
            )

    def test_semantic_confidence_policy_owner_preserves_threshold_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            row = {
                "status": "staging",
                "hit_count": cues.MIN_PROMOTION_HITS,
                "false_positive_count": 0,
                "confidence": confidence_policy.ACTIVE_CUE_CONFIDENCE - 0.01,
                "source_refs": [{"thread_key": "session:low", "message_id": "msg-low"}],
            }

            cues.refresh_status(row)
            first = semantic_cue_learning.promote_recall_cue_after_source_open(
                cache_path,
                query="source reopen confidence owner",
                source_refs=[{"thread_key": "session:owner", "message_id": "msg-owner"}],
                route_id="route:owner",
            )
            stored = cues.all_semantic_cues(cache_path)[0]
            below = {
                "available": True,
                "decision": "evidence",
                "confidence": confidence_policy.SOURCE_REOPEN_CONFIDENCE - 0.01,
                "anti_personalization_risk": "medium",
                "intent": "continuation",
                "query_aliases": ["source reopen confidence owner"],
            }
            at_threshold = {**below, "confidence": confidence_policy.SOURCE_REOPEN_CONFIDENCE}
            high_risk = semantic_gate.merge_workers(
                [
                    {
                        "worker": "probe",
                        "decision": "scent",
                        "confidence": confidence_policy.SOURCE_REOPEN_CONFIDENCE - 0.01,
                        "anti_personalization_risk": "high",
                    }
                ],
                [],
            )

            self.assertEqual(row["status"], "staging")
            self.assertEqual(first["active_count"], 0)
            self.assertEqual(stored["confidence"], confidence_policy.SOURCE_REOPEN_CONFIDENCE)
            self.assertFalse(
                prompt_cues.semantic_gate_can_request_source_reopen(
                    "continue that old thread",
                    below,
                )
            )
            self.assertTrue(
                prompt_cues.semantic_gate_can_request_source_reopen(
                    "continue that old thread",
                    at_threshold,
                )
            )
            self.assertEqual(high_risk["decision"], "background_only")

    def test_semantic_cue_cache_report_is_count_only_and_source_backed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            semantic_result = {
                "available": True,
                "decision": "scent",
                "confidence": 0.9,
                "query_aliases": ["private cue text"],
            }
            source_refs = [{"thread_key": "session:aippocampus", "message_id": "m1"}]
            for _ in range(2):
                cues.record_semantic_cue_hits(
                    cache_path,
                    prompt="private prompt text",
                    semantic_result=semantic_result,
                    source_refs=source_refs,
                    route="semantic_gate",
                )
            cues.record_semantic_cue_misses(
                cache_path,
                cues=["private cue text"],
                reason="matched an unrelated project",
            )

            report = cues.semantic_cue_cache_report(cache_path)
            encoded = json.dumps(report, ensure_ascii=False)

            self.assertEqual(report["entry_count"], 1)
            self.assertEqual(report["active_count"], 1)
            self.assertEqual(report["source_backed_count"], 1)
            self.assertEqual(report["false_positive_count"], 1)
            self.assertEqual(report["training_role_counts"]["positive_demo"], 1)
            self.assertIn("learning_priority_counts", report)
            self.assertIn("net_hit_buckets", report)
            self.assertNotIn("private cue text", encoded)
            self.assertNotIn("private prompt text", encoded)

    def test_recall_semantic_position_records_no_hit_without_source_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"

            result = cues.record_recall_semantic_position(
                cache_path,
                prompt="activation live shadow PARK latest turn SECRET_TOKEN=abc",
                terms=["activation", "live shadow", "PARK", "SECRET_TOKEN=abc"],
                cwd=Path(tmp) / "workspace",
                thread_key="session:current-thread",
                source_generation={"message_count": 3, "source_thread_key": "session:current-thread"},
                recall_status="no_routes",
                route_count=0,
            )
            rows = cues.all_recall_positions(cache_path)
            report = cues.semantic_cue_cache_report(cache_path)
            encoded = json.dumps(rows + [report], ensure_ascii=False)

            self.assertEqual(result["updated_count"], 1)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["kind"], "aippocampus_recall_semantic_position")
            self.assertEqual(row["status"], "staging")
            self.assertEqual(row["authority_level"], "direction_only")
            self.assertEqual(row["training_role"], "replay_sample")
            self.assertEqual(row["candidate_lifecycle_state"], "draft_candidate_staging")
            self.assertEqual(row["route_count_bucket"], "no_hit")
            self.assertTrue(row["source_reopen_required_before_claim"])
            self.assertEqual(report["recall_position_count"], 1)
            self.assertEqual(report["recall_position_training_role_counts"]["replay_sample"], 1)
            self.assertNotIn("SECRET_TOKEN", encoded)
            self.assertNotIn("abc", encoded)
            self.assertNotIn(str(Path(tmp) / "workspace"), encoded)

    def test_recall_positioning_preserves_source_backed_cues_in_same_owner_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"

            cues.record_recall_semantic_position(
                cache_path,
                prompt="no hit current thread positioning",
                terms=["current thread positioning"],
                thread_key="session:current-thread",
                recall_status="no_routes",
                route_count=0,
            )
            for _ in range(2):
                cues.record_semantic_cue_hits(
                    cache_path,
                    prompt="source backed alias",
                    semantic_result={
                        "available": True,
                        "decision": "scent",
                        "confidence": 0.9,
                        "query_aliases": ["source backed alias"],
                    },
                    source_refs=[{"thread_key": "session:old", "message_id": "msg-old"}],
                )

            self.assertEqual(len(cues.all_recall_positions(cache_path)), 1)
            self.assertEqual(len(cues.load_semantic_cues(cache_path)), 1)

if __name__ == "__main__":
    unittest.main()
