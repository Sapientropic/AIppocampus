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

from aippocampus_runtime.dream import input_pack, working_memory  # noqa: E402


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
        "concepts": ["continuity", "compaction", "source refs"],
        "source_refs": refs,
        "question_source_finding_ids": ["sf_q_a", "sf_q_b"],
        "linked_questions": [
            {
                "question_text": "How does continuity survive compaction?",
                "question_short": "continuity after compaction",
                "source_refs": [refs[0]],
            },
            {
                "question_text": "Why do source refs need to survive thread changes?",
                "question_short": "source refs across threads",
                "source_refs": [refs[1]],
            },
        ],
        "frontier_refs": [
            {
                "source_finding_id": "sf_frontier",
                "frontier_type": "blocked",
                "boundary_reason": "The boundary is unresolved until source refs survive replay.",
                "source_refs": refs,
            }
        ],
    }


def journey_row() -> dict[str, object]:
    refs = [
        source_ref("session:j-a", "msg-ja", 30),
        source_ref("session:j-b", "msg-jb", 40),
        source_ref("session:j-c", "msg-jc", 50),
    ]
    return {
        "kind": "aippocampus_journey",
        "journey_id": "jr_continuity",
        "path_label": "continuity after change",
        "core_inquiry": "How can continuity survive change without false memory claims?",
        "current_frontier": "Resume only after source refs survive compaction at the boundary.",
        "current_frontier_source_refs": [refs[-1]],
        "source_refs": refs,
        "active_questions": ["what survives compaction?"],
        "status": "traveling",
    }


def ambient_residue_row() -> dict[str, object]:
    return {
        "kind": "aippocampus_ambient_residue",
        "schema_version": 1,
        "status": "dream_seed",
        "residue_id": "ares_continuity",
        "themes": ["continuity", "quiet recurring concern"],
        "support_levels": ["candidate"],
        "source_ref_fingerprints": ["src_a", "src_b"],
        "negative_contexts": ["do not treat this as a user-profile fact"],
        "downstream_use": ["dream_task_seed"],
    }


def concept_edge_row() -> dict[str, object]:
    return {
        "kind": "concept_edge",
        "fingerprint": "sf_concept_edge",
        "src": "compaction",
        "dst": "continuity",
        "edge_type": "reinforces",
        "why": "Compaction repeatedly raises continuity as a design pressure.",
        "source_refs": [source_ref("session:concept", "msg-concept", 60)],
    }


def theme_candidate_row(*, source_backed: bool = True) -> dict[str, object]:
    row: dict[str, object] = {
        "kind": "theme_candidate",
        "theme": "continuity after context loss",
        "summary": "A recurring theme candidate around continuity after context loss.",
        "matched_terms": ["continuity", "context loss"],
    }
    if source_backed:
        row["source_refs"] = [source_ref("session:theme", "msg-theme", 70)]
    else:
        row["source_ref_fingerprints"] = ["weak-theme-ref"]
    return row


def correction_row() -> dict[str, object]:
    return {
        "kind": "correction_outcome_event",
        "event_id": "out_continuity_correction",
        "activation_event_id": "act_continuity_correction",
        "target_type": "route",
        "adoption_signal": "adopted",
        "outcome_summary": "The later answer adopted the source-backed correction.",
        "source_refs": [source_ref("session:correction", "msg-correction", 80)],
    }


def reflection_feedback_row() -> dict[str, object]:
    return {
        "kind": "aippocampus_reflection_adjustment",
        "adjustment_id": "reflection_adj_continuity",
        "feedback_action": "turning_point",
        "surface": "ranking",
        "reason": "A recall card changed the next question.",
        "source_refs": [source_ref("session:reflection", "msg-reflection", 90)],
    }


def agency_ticket_row() -> dict[str, object]:
    return {
        "kind": "aippocampus_agency_ticket",
        "ticket_id": "agency_ticket_continuity",
        "intervention_level": "light_nudge",
        "why_now": {"trigger": "compaction_loss"},
        "summary": "Offer a small state check when continuity evidence has dropped out of view.",
        "source_refs": [source_ref("session:agency", "msg-agency", 100)],
    }


def coding_decision_row() -> dict[str, object]:
    return {
        "kind": "aippocampus_coding_decision_candidate",
        "finding_kind": "decision_event",
        "decision_id": "decision_keep_source_refs",
        "event_type": "accepted_decision",
        "summary": "Keep source refs on continuity rows before surfacing them.",
        "trigger_terms": ["source refs", "continuity"],
        "source_refs": [source_ref("session:coding", "msg-coding", 110)],
    }


class DreamInputPackTests(unittest.TestCase):
    def test_cross_thread_pack_combines_question_journey_and_residue_seed(self) -> None:
        pack = input_pack.build_dream_input_pack(
            [question_link_row(), journey_row(), ambient_residue_row()],
            objective="find dream seeds that improve cross-thread recall",
        )

        self.assertEqual(pack["kind"], "aippocampus_dream_input_pack")
        self.assertEqual(pack["status"], "ready_for_dream_worker")
        self.assertEqual(pack["pack_kind"], "cross_thread_resonance_seed")
        self.assertEqual(pack["source_ref_audit"]["status"], "structural_cross_thread")
        self.assertGreaterEqual(pack["source_ref_audit"]["source_thread_count"], 3)
        self.assertIn("question_link", pack["source_seed_kinds"])
        self.assertIn("journey", pack["source_seed_kinds"])
        self.assertIn("ambient_residue", pack["source_seed_kinds"])
        self.assertIn("compensatory", pack["eligible_dream_functions"])
        self.assertIn("amplification", pack["eligible_dream_functions"])
        self.assertIn("continuity", pack["themes"])
        self.assertIn("what survives compaction?", pack["questions"])
        self.assertIn("do not treat this as a user-profile fact", pack["negative_contexts"])
        self.assertFalse(pack["foreground_eligible"])
        self.assertFalse(pack["human_review_required"])
        self.assertFalse(pack["formal_memory_eligible"])
        self.assertEqual(pack["truth_boundary"], "dream_input_pack_seed_not_fact")

    def test_extended_source_backed_rows_can_seed_ready_pack(self) -> None:
        rows = [
            concept_edge_row(),
            theme_candidate_row(),
            correction_row(),
            reflection_feedback_row(),
            agency_ticket_row(),
            coding_decision_row(),
        ]

        pack = input_pack.build_dream_input_pack(rows)

        self.assertEqual(pack["status"], "ready_for_dream_worker")
        self.assertEqual(pack["source_ref_audit"]["status"], "structural_cross_thread")
        self.assertIn("concept_edge", pack["source_seed_kinds"])
        self.assertIn("theme_candidate", pack["source_seed_kinds"])
        self.assertIn("correction", pack["source_seed_kinds"])
        self.assertIn("reflection_feedback", pack["source_seed_kinds"])
        self.assertIn("agency_ticket", pack["source_seed_kinds"])
        self.assertIn("coding_ticket", pack["source_seed_kinds"])
        self.assertIn("continuity after context loss", pack["themes"])
        self.assertIn("turning_point", pack["themes"])
        self.assertTrue(
            all(item["readiness_role"] == "clean_anchor" for item in pack["source_contributions"])
        )
        self.assertGreaterEqual(pack["source_ref_audit"]["source_thread_count"], 6)

    def test_pack_rejects_single_thread_clean_refs(self) -> None:
        row = {
            "kind": "question_link",
            "finding_kind": "question_link",
            "fingerprint": "sf_single_thread",
            "title": "Question continuity: local only",
            "source_refs": [
                source_ref("session:one", "msg-1", 1),
                source_ref("session:one", "msg-2", 2),
            ],
            "linked_questions": [{"question_text": "Does this repeat locally?"}],
        }

        pack = input_pack.build_dream_input_pack([row])

        self.assertEqual(pack["status"], "no_cross_thread_source_pattern")
        self.assertEqual(pack["source_ref_audit"]["status"], "insufficient_source_threads")
        self.assertEqual(pack["eligible_dream_functions"], [])
        self.assertFalse(pack["foreground_eligible"])

    def test_ambient_residue_alone_is_not_clean_source(self) -> None:
        pack = input_pack.build_dream_input_pack([ambient_residue_row()])

        self.assertEqual(pack["status"], "no_clean_source_refs")
        self.assertEqual(pack["source_ref_audit"]["status"], "missing_clean_source_refs")
        self.assertEqual(pack["source_refs"], [])
        self.assertEqual(pack["weak_source_handle_count"], 2)
        self.assertEqual(pack["eligible_dream_functions"], [])

    def test_weak_theme_candidate_adds_context_but_cannot_make_pack_ready(self) -> None:
        pack = input_pack.build_dream_input_pack([theme_candidate_row(source_backed=False)])

        self.assertEqual(pack["status"], "no_clean_source_refs")
        self.assertEqual(pack["source_refs"], [])
        self.assertEqual(pack["source_ref_audit"]["status"], "missing_clean_source_refs")
        self.assertIn("theme_candidate", pack["source_seed_kinds"])
        self.assertEqual(pack["source_ref_fingerprints"], ["weak-theme-ref"])
        self.assertEqual(pack["source_contributions"][0]["readiness_role"], "weak_context")
        self.assertEqual(pack["eligible_dream_functions"], [])

    def test_plain_theme_card_without_candidate_cues_is_not_a_dream_seed(self) -> None:
        pack = input_pack.build_dream_input_pack(
            [
                {
                    "kind": "aippocampus_ambient_recall_card",
                    "theme": "visible foreground card",
                    "support_level": "candidate",
                    "matched_terms": ["visible", "foreground"],
                    "source_refs": [source_ref("session:visible", "msg-visible", 120)],
                }
            ]
        )

        self.assertEqual(pack["status"], "no_clean_source_refs")
        self.assertEqual(pack["source_seed_kinds"], [])
        self.assertEqual(pack["source_contributions"], [])

    def test_plain_action_row_without_reflection_kind_is_not_a_dream_seed(self) -> None:
        pack = input_pack.build_dream_input_pack(
            [
                {
                    "kind": "unrelated_action_event",
                    "action": "turning_point",
                    "summary": "This is not a reflection feedback row.",
                    "source_refs": [source_ref("session:action", "msg-action", 130)],
                }
            ]
        )

        self.assertEqual(pack["status"], "no_clean_source_refs")
        self.assertEqual(pack["source_seed_kinds"], [])
        self.assertEqual(pack["source_contributions"], [])

    def test_source_refs_are_reduced_to_structural_fields(self) -> None:
        ref_a = {
            **source_ref("session:safe-a", "msg-safe-a", 140),
            "workspace": "private workspace label",
            "raw_text": "private source text",
            "path": "private path label",
        }
        ref_b = {
            **source_ref("session:safe-b", "msg-safe-b", 150),
            "text": "another private text field",
            "raw_payload": {"secret": "nope"},
        }
        pack = input_pack.build_dream_input_pack(
            [
                {**concept_edge_row(), "source_refs": [ref_a]},
                {
                    **concept_edge_row(),
                    "fingerprint": "sf_concept_edge_b",
                    "source_refs": [ref_b],
                },
            ]
        )
        encoded_refs = json.dumps(pack["source_refs"], ensure_ascii=False)

        self.assertEqual(pack["status"], "ready_for_dream_worker")
        self.assertNotIn("workspace", encoded_refs)
        self.assertNotIn("raw_text", encoded_refs)
        self.assertNotIn("path", encoded_refs)
        self.assertNotIn("text", encoded_refs)
        self.assertNotIn("raw_payload", encoded_refs)
        self.assertIn("project_label", pack["source_refs"][0])

    def test_cli_defaults_to_public_summary_without_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "rows.jsonl"
            output_path = root / "pack-summary.json"
            input_path.write_text(
                json.dumps(question_link_row(), ensure_ascii=False) + "\n"
                + json.dumps(journey_row(), ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                code = input_pack.main(
                    [
                        str(input_path),
                        "--json",
                        "--output",
                        str(output_path),
                    ]
                )
            summary = json.loads(output_path.read_text(encoding="utf-8"))
            encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertEqual(summary["kind"], "aippocampus_dream_input_pack_summary")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)
        self.assertNotIn("question_text", encoded)

    def test_background_adjudication_accepts_pack_backed_candidate_without_user_review(self) -> None:
        pack = input_pack.build_dream_input_pack([question_link_row(), journey_row()])
        refs = pack["source_refs"][:2]
        finding = {
            "kind": "aippocampus_dream_finding",
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "dream_phase": "phase2_cross_thread",
            "compensatory_kind": "silently_recurring",
            "support_level": "candidate",
            "review_state": "needs_review",
            "confidence": 0.72,
            "title": "Compensatory check: continuity concern keeps returning",
            "summary": "A source-backed dream hypothesis that continuity keeps reappearing across threads.",
            "source_refs": refs,
            "source_ref_audit": {"status": "structural_cross_thread"},
            "bridge_claims": [
                {"claim": "Question continuity appears across threads.", "source_refs": [refs[0]]},
                {"claim": "Journey frontier still points at compaction boundaries.", "source_refs": [refs[1]]},
            ],
            "downstream_use": ["review_queue"],
        }

        adjudicated = working_memory.background_adjudicate_dream_finding(
            finding,
            source_pack=pack,
            adjudication_source="deterministic_p2_adjudicator",
        )
        working_rows = working_memory.adjudicated_dream_findings_to_working_memory([adjudicated])

        self.assertEqual(adjudicated["review_state"], "agent_adjudicated")
        self.assertEqual(adjudicated["adjudication_source"], "deterministic_p2_adjudicator")
        self.assertEqual(adjudicated["adjudication_result"]["status"], "accepted")
        self.assertFalse(adjudicated["human_review_required"])
        self.assertEqual(len(working_rows), 1)
        self.assertEqual(working_rows[0]["candidate_type"], "dream_hypothesis")

    def test_background_adjudication_parks_unsourced_bridge_claims(self) -> None:
        pack = input_pack.build_dream_input_pack([question_link_row(), journey_row()])
        refs = pack["source_refs"][:2]
        finding = {
            "kind": "aippocampus_dream_finding",
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "review_state": "needs_review",
            "confidence": 0.9,
            "title": "Bad candidate",
            "summary": "This should not pass even if a model says it is confident.",
            "source_refs": refs,
            "source_ref_audit": {"status": "structural_cross_thread"},
            "bridge_claims": [{"claim": "A claim without source refs."}],
        }

        adjudicated = working_memory.background_adjudicate_dream_finding(finding, source_pack=pack)
        forced = {**finding, "review_state": "agent_adjudicated"}

        self.assertEqual(adjudicated["review_state"], "needs_review")
        self.assertEqual(adjudicated["adjudication_result"]["status"], "parked")
        self.assertIn("bridge_claims_source_refs", adjudicated["adjudication_result"]["failed_checks"])
        self.assertEqual(working_memory.adjudicated_dream_findings_to_working_memory([adjudicated]), [])
        self.assertEqual(working_memory.adjudicated_dream_findings_to_working_memory([forced]), [])


if __name__ == "__main__":
    unittest.main()
