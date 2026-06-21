from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.recall import prompt_context_render as render
from aippocampus_runtime.recall import prompt_recall_ambiguity as ambiguity
from aippocampus_runtime.recall import prompt_recall_core as core
from aippocampus_runtime.recall import prompt_recall_evidence as evidence
from aippocampus_runtime.recall.prompt_recall_policy import (
    PROMPT_EVIDENCE_POLICY,
    PROMPT_RECALL_GATE_POLICY,
    PromptRecallGatePolicy,
)


class PromptRecallPolicyTests(unittest.TestCase):
    def test_prompt_gate_policy_names_skip_scent_evidence_boundaries(self) -> None:
        self.assertLess(
            PROMPT_RECALL_GATE_POLICY.scent_threshold,
            PROMPT_RECALL_GATE_POLICY.evidence_threshold,
        )
        self.assertEqual(core.SCENT_THRESHOLD, PROMPT_RECALL_GATE_POLICY.scent_threshold)
        self.assertEqual(core.EVIDENCE_THRESHOLD, PROMPT_RECALL_GATE_POLICY.evidence_threshold)
        self.assertEqual(
            core.EVIDENCE_LITE_MIN_PROBE_SCORE,
            PROMPT_RECALL_GATE_POLICY.evidence_lite_min_probe_score,
        )

        core_tree = ast.parse(
            (SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_core.py").read_text(
                encoding="utf-8"
            )
        )
        literal_policy_assignments = []
        for node in ast.walk(core_tree):
            if not isinstance(node, ast.Assign):
                continue
            target_names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if set(target_names) & {
                "SCENT_THRESHOLD",
                "EVIDENCE_THRESHOLD",
                "EVIDENCE_LITE_MIN_PROBE_SCORE",
            } and isinstance(node.value, ast.Constant):
                literal_policy_assignments.extend(target_names)

        self.assertEqual(literal_policy_assignments, [])

    def test_ambiguity_margin_is_named_policy_not_hidden_magic_number(self) -> None:
        candidates = [
            {
                "thread_key": "session:a",
                "project_label": "Alpha",
                "matched_terms": ["shared-plan"],
                "score": 12.0,
            },
            {
                "thread_key": "session:b",
                "project_label": "Beta",
                "matched_terms": ["shared-plan"],
                "score": 10.25,
            },
        ]

        strict_policy = PromptRecallGatePolicy(
            cross_project_tie_absolute_margin=0.5,
            cross_project_tie_relative_margin=0.0,
        )
        loose_policy = PromptRecallGatePolicy(
            cross_project_tie_absolute_margin=2.0,
            cross_project_tie_relative_margin=0.0,
        )

        self.assertFalse(
            ambiguity.explicit_evidence_request_is_ambiguous(
                "上次那个方案怎么说",
                candidates,
                policy=strict_policy,
            )
        )
        self.assertTrue(
            ambiguity.explicit_evidence_request_is_ambiguous(
                "上次那个方案怎么说",
                candidates,
                policy=loose_policy,
            )
        )

    def test_evidence_quality_uses_named_policy_values(self) -> None:
        clean_final = {
            "source": "clean_source",
            "score": 3.0,
            "phase": "final_answer",
            "snippet": "The actual source-backed answer.",
        }
        process_noise = {
            "source": "raw",
            "score": 900.0,
            "search_noise": True,
            "snippet": "<tool_call> noisy carrier",
        }

        self.assertEqual(
            evidence._evidence_hit_quality(clean_final),
            3.0
            + PROMPT_EVIDENCE_POLICY.clean_source_quality_bonus
            + PROMPT_EVIDENCE_POLICY.final_answer_quality_bonus,
        )
        self.assertEqual(
            evidence._evidence_hit_quality(process_noise),
            900.0 - PROMPT_EVIDENCE_POLICY.process_noise_penalty,
        )

    def test_source_texture_stays_quiet_in_default_foreground_rendering(self) -> None:
        result = {
            "decision": "scent",
            "score": 4.0,
            "confidence": "low",
            "query_terms": ["texture-only-probe"],
            "candidates": [{"title": "Clean-source route", "anchors": ["source-backed anchor"]}],
            "texture_signals": [
                {
                    "kind": "aippocampus_texture_signal",
                    "texture_id": "tex_prompt",
                    "signal_kind": "tool_failure_texture",
                    "signal_detail": "texture_only_probe",
                    "signal_labels": ["texture_only_probe"],
                    "truth_boundary": "texture_signal_not_source_fact",
                    "source_refs": [{"thread_key": "session:tex", "message_id": "msg-tex"}],
                    "event_refs": [{"event_id": "evt-tex", "status": "failed"}],
                }
            ],
        }

        context = render.context_for_hook(result)
        public = render.public_hook_debug_payload(result)
        encoded = f"{context}\n{public}"

        self.assertIn("Clean-source route", context or "")
        self.assertNotIn("texture_only_probe", encoded)
        self.assertNotIn("msg-tex", encoded)
        self.assertNotIn("evt-tex", encoded)
        self.assertNotIn("texture_signal_not_source_fact", encoded)

    def test_dream_draft_and_invitation_render_as_optional_questions_not_facts(self) -> None:
        result = {
            "decision": "scent",
            "score": 4.0,
            "confidence": "medium",
            "candidates": [],
            "working_memory": [
                {
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "title": "Blank-starting-point invitation",
                    "summary": "A prospective invitation about AGI and blankness.",
                    "confidence": 0.66,
                    "matched_terms": ["AGI blank starting point"],
                    "source_refs": [
                        {
                            "thread_key": "session:dream",
                            "title": "Dream invitation",
                            "line": 12,
                        }
                    ],
                    "dream_hypothesis_use": {
                        "action": "deliver_as_optional_question",
                        "reason": "matched_prospective_invitation_trigger",
                    },
                    "constructive_artifact": {
                        "status": "dream_draft_not_source",
                        "artifact_kind": "draft_question",
                        "draft_text": "What would a blank starting point preserve and what would it forget?",
                    },
                    "prospective_invitation": {
                        "status": "dream_invitation_not_source_fact",
                        "suggested_opening": "Is the blank starting point question live here?",
                        "invitation_type": "light_question",
                    },
                }
            ],
        }

        context = render.context_for_hook(result)

        self.assertIn("Prospective Dream invitation, not source fact", context)
        self.assertIn("Is the blank starting point question live here?", context)
        self.assertIn("Dream draft, not source fact", context)
        self.assertIn("optional probe", context)
        self.assertIn("reopen source before any strong claim", context)

    def test_journey_bridge_renders_as_optional_unblock_probe_not_fact(self) -> None:
        result = {
            "decision": "scent",
            "score": 4.0,
            "confidence": "medium",
            "candidates": [],
            "working_memory": [
                {
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "title": "Safety-boundary bridge",
                    "summary": "A Dream bridge over two camped journeys.",
                    "confidence": 0.64,
                    "matched_terms": ["rollback boundary before rebuild"],
                    "source_refs": [
                        {
                            "thread_key": "session:dream",
                            "title": "Dream bridge",
                            "line": 44,
                        }
                    ],
                    "dream_hypothesis_use": {
                        "action": "deliver_as_optional_unblock_probe",
                        "reason": "journey_bridge_trigger_matched",
                    },
                    "journey_bridge_hypothesis": {
                        "status": "dream_bridge_not_source_fact",
                        "bridge_kind": "shared_unblock_condition",
                        "shared_pattern": "both routes camp before replacing an old structure",
                        "possible_reason": "each journey may be waiting for a reversible boundary",
                        "unblock_condition": "define the rollback, snapshot, or recovery boundary before rebuilding",
                    },
                }
            ],
        }

        context = render.context_for_hook(result)

        self.assertIn("Journey bridge Dream hypothesis, not source fact", context)
        self.assertIn("optional unblock probe", context)
        self.assertIn("define the rollback", context)
        self.assertIn("reopen source before any strong claim", context)

if __name__ == "__main__":
    unittest.main()
