from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import prompt_recall_ambiguity as ambiguity  # noqa: E402
from aippocampus_runtime.recall import prompt_recall_core as core  # noqa: E402
from aippocampus_runtime.recall import prompt_recall_evidence as evidence  # noqa: E402
from aippocampus_runtime.recall.prompt_recall_policy import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
