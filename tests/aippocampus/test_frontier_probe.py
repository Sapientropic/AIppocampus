from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.navigation import concept_graph, frontier_probe

_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []

def source_ref(line: int, *, thread_key: str = "session:frontier") -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-06-07T00:00:00Z",
    }

def journey_row(
    journey_id: str = "journey-frontier",
    *,
    frontier: str = "source refs survive compaction",
    status: str = "traveling",
    thread_key: str = "session:frontier",
) -> dict[str, object]:
    return {
        "kind": "aippocampus_journey",
        "journey_id": journey_id,
        "path_label": "continuity after compaction",
        "core_inquiry": "How do source refs survive compaction?",
        "status": status,
        "current_frontier": frontier,
        "current_frontier_source_refs": [source_ref(10, thread_key=thread_key)],
        "source_refs": [source_ref(10, thread_key=thread_key)],
        "active_questions": ["Which route should reopen first?"],
        "expires_at": "2026-07-01T00:00:00Z",
        "waypoints": [
            {"labels": ["dynamics:stalled_then_reopen"], "source_refs": [source_ref(9)]}
        ],
    }

def make_graph(rows: list[tuple[str, str, str, float, str]]) -> Path:
    tmp = tempfile.TemporaryDirectory()
    _TEMP_DIRS.append(tmp)
    path = Path(tmp.name) / "concept.sqlite"
    con = concept_graph.connect(path)
    concept_graph.init_schema(con)
    for src, dst, edge_type, confidence, status in rows:
        src_id = concept_graph.upsert_concept(con, src, status="verified")
        dst_id = concept_graph.upsert_concept(con, dst, status="verified")
        assert src_id is not None and dst_id is not None
        concept_graph.upsert_edge(
            con,
            src_id,
            dst_id,
            edge_type=edge_type,
            confidence=confidence,
            status=status,
            evidence_count=3,
        )
    con.commit()
    con.close()
    return path

class FrontierProbeTests(unittest.TestCase):
    def test_frontier_probe_expands_to_adjacent_unexplored_concept(self) -> None:
        graph = make_graph(
            [
                ("source refs", "Active Path Packet", "same_decision_space", 0.94, "verified"),
                ("compaction", "handoff packet", "related", 0.82, "verified"),
            ]
        )

        probes = frontier_probe.build_frontier_probes(
            [journey_row()],
            graph,
            now="2026-06-07T00:00:00Z",
        )

        labels = [probe["candidate_concept"]["label"] for probe in probes]
        self.assertIn("Active Path Packet", labels)
        self.assertNotIn("source refs", labels)
        probe = next(item for item in probes if item["candidate_concept"]["label"] == "Active Path Packet")
        self.assertEqual(probe["kind"], "aippocampus_frontier_probe")
        self.assertEqual(probe["status"], "candidate")
        self.assertEqual(probe["support_level"], "bounded_probe")
        self.assertEqual(probe["suggested_use"], "prospective_scouting_seed")
        self.assertTrue(probe["source_refs"])
        self.assertTrue(probe["frontier_source_refs"])
        self.assertTrue(probe["claim_boundary"]["not_evidence"])
        self.assertTrue(probe["claim_boundary"]["does_not_mutate_journey"])

    def test_depth_two_probe_uses_existing_high_confidence_graph_limit(self) -> None:
        graph = make_graph(
            [
                ("source refs", "route bridge", "verified_related", 0.95, "verified"),
                ("route bridge", "Active Path Packet", "same_decision_space", 0.96, "verified"),
            ]
        )

        probes = frontier_probe.build_frontier_probes(
            [journey_row()],
            graph,
            now="2026-06-07T00:00:00Z",
            depth=2,
            max_probes_per_journey=4,
        )

        depth_two = [
            probe
            for probe in probes
            if probe["candidate_concept"]["label"] == "Active Path Packet"
        ]
        self.assertTrue(depth_two)
        self.assertEqual(depth_two[0]["depth"], 2)
        self.assertIn("route bridge", depth_two[0]["probe_path"])

    def test_shared_frontier_probe_emits_reviewable_resonance_candidate(self) -> None:
        graph = make_graph(
            [
                ("source refs", "Active Path Packet", "same_decision_space", 0.94, "verified"),
            ]
        )
        journeys = [
            journey_row("journey-a", thread_key="session:a"),
            journey_row("journey-b", thread_key="session:b"),
        ]
        probes = frontier_probe.build_frontier_probes(
            journeys,
            graph,
            now="2026-06-07T00:00:00Z",
        )

        candidates = frontier_probe.build_resonance_candidates(
            journeys,
            probes,
            now="2026-06-07T00:00:00Z",
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        encoded = json.dumps(candidate, ensure_ascii=False)
        self.assertEqual(candidate["kind"], "aippocampus_resonance_candidate")
        self.assertEqual(candidate["status"], "reviewable_hypothesis")
        self.assertEqual(candidate["match_kind"], "neighboring_frontier_concepts")
        self.assertEqual(set(candidate["journey_ids"]), {"journey-a", "journey-b"})
        self.assertIn("Active Path Packet", candidate["shared_or_neighboring_concepts"])
        self.assertTrue(candidate["claim_boundary"]["not_auto_merge"])
        self.assertNotIn("msg-10", encoded)

    def test_frontier_probe_converts_to_non_foreground_dream_seed(self) -> None:
        graph = make_graph(
            [
                ("source refs", "Active Path Packet", "same_decision_space", 0.94, "verified"),
            ]
        )
        probes = frontier_probe.build_frontier_probes(
            [journey_row()],
            graph,
            now="2026-06-07T00:00:00Z",
        )

        seeds = frontier_probe.frontier_probes_to_dream_seeds(probes)

        self.assertTrue(seeds)
        seed = seeds[0]
        self.assertEqual(seed["kind"], "aippocampus_dream_input_seed")
        self.assertEqual(seed["seed_kind"], "frontier_probe")
        self.assertFalse(seed["foreground_eligible"])
        self.assertFalse(seed["formal_memory_eligible"])
        self.assertFalse(seed["clean_source_mutation"])
        self.assertEqual(seed["eligible_dream_functions"], ["prospective"])
        self.assertEqual(seed["truth_boundary"], "dream_input_seed_not_fact")
        self.assertTrue(seed["claim_boundary"]["not_evidence"])

    def test_missing_terminal_or_dismissed_frontier_does_not_nag(self) -> None:
        graph = make_graph(
            [
                ("source refs", "Active Path Packet", "same_decision_space", 0.94, "verified"),
            ]
        )
        missing_refs = journey_row()
        missing_refs["current_frontier_source_refs"] = []
        arrived = journey_row("arrived", status="arrived")
        active = journey_row("active")
        feedback_key = frontier_probe._negative_feedback_key(active)

        probes = frontier_probe.build_frontier_probes(
            [missing_refs, arrived, active],
            graph,
            feedback_rows=[{"negative_feedback_key": feedback_key, "outcome": "dismissed"}],
            now="2026-06-07T00:00:00Z",
        )

        self.assertEqual(probes, [])

if __name__ == "__main__":
    unittest.main()
