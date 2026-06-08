from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import episode_arcs  # noqa: E402
from aippocampus_runtime.recall.narrative_packet import compile_narrative_packet  # noqa: E402


def source_ref(line: int, message_id: str) -> dict[str, object]:
    return {
        "thread_key": "thread:narrative-packet-test",
        "message_id": message_id,
        "turn_id": f"turn-{line}",
        "source_line": line,
    }


def event(
    event_id: str,
    event_kind: str,
    line: int,
    *,
    sequence_index: int | None = None,
    episode_id: str = "episode:route",
) -> dict[str, object]:
    row: dict[str, object] = {
        "episode_id": episode_id,
        "event_id": event_id,
        "event_kind": event_kind,
        "source_refs": [source_ref(line, f"m-{line}")],
        "turn_id": f"turn-{line}",
        "source_line": line,
    }
    if sequence_index is not None:
        row["sequence_index"] = sequence_index
    return row


def source_catalog_for_arc(arc: dict[str, object]) -> list[dict[str, object]]:
    event_ids = [str(item) for item in arc.get("source_event_ids", [])]
    source_hashes = [str(item) for item in arc.get("source_ref_hashes", [])]
    refs = [item for item in arc.get("source_refs", []) if isinstance(item, dict)]
    return [
        {
            "event_id": event_id,
            "source_ref_hash": source_hash,
            "source_refs": [ref],
            "raw_source_text": "RAW_SEQUENCE_REOPEN_SENTINEL",
        }
        for event_id, source_hash, ref in zip(event_ids, source_hashes, refs, strict=False)
    ]


class NarrativePacketTests(unittest.TestCase):
    def test_merges_pathlet_domain_sequence_and_active_route_without_becoming_evidence(self) -> None:
        arc = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 10, sequence_index=0),
                event("e-failed", "failed_check", 11, sequence_index=1),
                event("e-rejected", "route_rejected", 12, sequence_index=2),
            ]
        )[0]
        sequence_packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")

        packet = compile_narrative_packet(
            trigger="fresh_thread",
            current_query="继续 #700 里的 narrative mesh",
            pathlets=[
                {
                    "pathlet_id": "pathlet-story-back-to-source",
                    "title": "Story goes back to source",
                    "status": "active",
                    "ordered_source_refs": [source_ref(1, "m-path-a"), source_ref(2, "m-path-b")],
                    "summary": "This raw summary must not be copied into the packet.",
                }
            ],
            continuity_domain_pointers=[
                {
                    "card_kind": "continuity_domain_pointer",
                    "domain_id": "cd-narrative-mesh",
                    "label": "Narrative mesh as route",
                    "status": "active",
                    "action_grammar": "reopenable_route",
                    "source_refs": [source_ref(3, "m-domain")],
                    "working_conclusion_short": "Do not serialize this domain conclusion.",
                    "reopen_plan": {"status": "ready", "recommended_tool": "recall_deepen"},
                }
            ],
            sequence_packets=[sequence_packet],
            active_path_packet={
                "kind": "aippocampus_active_path_packet",
                "paths": [
                    {
                        "route": "reopen",
                        "title": "Active source reopen path",
                        "action_grammar": "reopenable_route",
                        "source_refs": [source_ref(20, "m-active")],
                        "source_boundary": {"source_reopen_required": True},
                    }
                ],
            },
            source_catalog=source_catalog_for_arc(arc),
        )

        self.assertEqual(packet["kind"], "aippocampus_narrative_packet")
        self.assertEqual(packet["source_discussion"], 700)
        self.assertTrue(packet["no_write"])
        self.assertEqual(packet["use_boundary"]["action_grammar"], "reopenable_route")
        self.assertTrue(packet["source_boundary"]["narrative_packet_is_not_source_truth"])
        self.assertIn("exact_factual_claim_without_source_reopen", packet["use_boundary"]["cannot_claim"])
        self.assertEqual(
            [ref["message_id"] for ref in packet["route_shape"]["pathlets"][0]["ordered_source_refs"]],
            ["m-path-a", "m-path-b"],
        )
        self.assertEqual(packet["route_shape"]["continuity_domains"][0]["domain_id"], "cd-narrative-mesh")
        self.assertNotIn("working_conclusion_short", packet["route_shape"]["continuity_domains"][0])

        recommended = [ref["message_id"] for ref in packet["source_reopen"]["recommended_refs"]]
        self.assertLess(recommended.index("m-path-a"), recommended.index("m-path-b"))
        self.assertLess(recommended.index("m-path-b"), recommended.index("m-domain"))
        self.assertLess(recommended.index("m-10"), recommended.index("m-11"))
        self.assertLess(recommended.index("m-11"), recommended.index("m-12"))
        self.assertIn("m-active", recommended)

        raw = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw summary", raw)
        self.assertNotIn("domain conclusion", raw)
        self.assertNotIn("RAW_SEQUENCE_REOPEN_SENTINEL", raw)

    def test_missing_middle_sequence_becomes_sequence_risk(self) -> None:
        arc = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 25, sequence_index=0, episode_id="episode:missing"),
                event("e-rejected", "rejected_route", 27, sequence_index=2, episode_id="episode:missing"),
            ]
        )[0]
        sequence_packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")

        packet = compile_narrative_packet(
            trigger="pre_patch",
            sequence_packets=[sequence_packet],
            source_catalog=source_catalog_for_arc(arc),
        )

        self.assertEqual(packet["use_boundary"]["action_grammar"], "reopenable_route")
        self.assertEqual(
            packet["sequence_risks"]["missing_middle_events"][0]["sequence_gaps"],
            ["missing_middle_event"],
        )
        self.assertIn("sequence_order_uncertain", packet["use_boundary"]["cannot_claim"])
        self.assertEqual(packet["source_reopen"]["sequence_reopen_plans"][0]["recommended_use"], "refresh_sources")

    def test_stale_or_superseded_route_stays_blocker(self) -> None:
        packet = compile_narrative_packet(
            trigger="route_reentry",
            pathlets=[
                {
                    "pathlet_id": "pathlet-old-route",
                    "title": "Old route",
                    "status": "superseded",
                    "ordered_source_refs": [source_ref(30, "m-old-path")],
                    "action_grammar": "ignore_or_blocked",
                }
            ],
            continuity_domain_pointers=[
                {
                    "card_kind": "continuity_domain_pointer",
                    "domain_id": "cd-stale",
                    "label": "Stale domain",
                    "status": "stale",
                    "action_grammar": "ignore_or_blocked",
                    "source_refs": [source_ref(31, "m-stale-domain")],
                }
            ],
            active_path_packet={
                "kind": "aippocampus_active_path_packet",
                "paths": [
                    {
                        "route": "ignore",
                        "title": "Superseded active path",
                        "currentness": "superseded",
                        "action_grammar": "ignore_or_blocked",
                        "source_refs": [source_ref(32, "m-superseded-active")],
                    }
                ],
            },
        )

        self.assertEqual(packet["use_boundary"]["action_grammar"], "ignore_or_blocked")
        self.assertEqual(packet["route_shape"]["pathlets"][0]["status"], "superseded")
        self.assertEqual(packet["route_shape"]["continuity_domains"][0]["status"], "stale")
        self.assertEqual(packet["route_shape"]["active_path_blockers"][0]["currentness"], "superseded")
        self.assertIn("stale_or_superseded_route_is_not_current_fact", packet["use_boundary"]["cannot_claim"])
        self.assertEqual(packet["source_reopen"]["recommended_refs"], [])

    def test_glyph_only_packet_is_direction_only_atmosphere(self) -> None:
        packet = compile_narrative_packet(
            trigger="fresh_thread",
            optional_glyphs=[
                {
                    "glyph_id": "glyph-transition",
                    "label": "transition atmosphere",
                    "action_grammar": "direction_only",
                    "signal_labels": ["transition"],
                    "raw_prompt": "Do not serialize prompt text.",
                }
            ],
        )

        self.assertEqual(packet["use_boundary"]["action_grammar"], "direction_only")
        self.assertEqual(packet["source_reopen"]["recommended_refs"], [])
        self.assertEqual(packet["source_reopen"]["required_before_claim"], [])
        self.assertFalse(packet["use_boundary"]["agent_may_answer_within_scope"])
        self.assertIn("glyph_only_atmosphere_not_evidence", packet["use_boundary"]["cannot_claim"])
        self.assertIn("glyph_is_fact", packet["use_boundary"]["cannot_claim"])
        self.assertNotIn("raw_prompt", packet["route_shape"]["optional_glyphs"][0])

    def test_blocked_boundary_forces_packet_ignore_or_blocked(self) -> None:
        packet = compile_narrative_packet(
            trigger="explicit_recall",
            continuity_domain_pointers=[
                {
                    "card_kind": "continuity_domain_pointer",
                    "domain_id": "cd-private",
                    "label": "Private continuity boundary",
                    "status": "active",
                    "action_grammar": "reopenable_route",
                    "source_refs": [source_ref(40, "m-private-boundary")],
                    "pinned_boundary_conditions": [
                        {
                            "kind": "privacy_boundary",
                            "strength": "hard",
                            "effect": "block_hook",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(packet["use_boundary"]["action_grammar"], "ignore_or_blocked")
        self.assertIn("hard_boundary_blocks_narrative_packet_use", packet["use_boundary"]["cannot_claim"])
        self.assertEqual(packet["source_reopen"]["recommended_refs"], [])

    def test_raw_text_local_paths_and_secret_shaped_values_do_not_leak(self) -> None:
        packet = compile_narrative_packet(
            trigger="explicit_recall",
            pathlets=[
                {
                    "pathlet_id": "pathlet-sensitive",
                    "title": "Sensitive route api_key=sk-test-secret-value",
                    "status": "active",
                    "ordered_source_refs": [
                        {
                            "thread_key": "E:\\Users\\Private\\thread.jsonl",
                            "message_id": "m-sensitive",
                            "source_line": 50,
                            "raw_source_text": "RAW_PATHLET_TEXT_SENTINEL",
                            "path": "E:\\Users\\Private\\source.md",
                        }
                    ],
                    "summary": "C:\\Private\\notes.md and token=secret-token must not leak.",
                }
            ],
        )

        raw = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("RAW_PATHLET_TEXT_SENTINEL", raw)
        self.assertNotIn("C:\\", raw)
        self.assertNotIn("E:\\", raw)
        self.assertNotIn("Private", raw)
        self.assertNotIn("sk-test-secret-value", raw)
        self.assertNotIn("secret-token", raw)
        self.assertIn("<redacted-sensitive-label>", raw)
        self.assertIn("<sensitive-value-redacted>", raw)


if __name__ == "__main__":
    unittest.main()
