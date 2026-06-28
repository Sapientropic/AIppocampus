from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"

class SkillEntrypointDocsTests(unittest.TestCase):
    def test_skill_frontmatter_stays_codex_yaml_compatible(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill_text.startswith("---\n"))
        frontmatter = skill_text.split("---", 2)[1]

        for raw_line in frontmatter.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if ": " not in value:
                continue
            self.assertTrue(
                value.startswith(('"', "'", "|", ">")),
                f"{key.strip()} frontmatter value contains ': ' and must be quoted",
            )

    def test_agent_entrypoints_frame_early_route_first_continuity(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        agent_context = (REPO_ROOT / "docs" / "agent-context.md").read_text(
            encoding="utf-8"
        )
        coding_lane = (
            REPO_ROOT / "docs" / "guides" / "coding-agent-memory.md"
        ).read_text(encoding="utf-8")
        ambient_hooks = (ROOT / "references" / "ambient-hooks.md").read_text(
            encoding="utf-8"
        )

        for phrase in (
            "source-backed continuity scaffold",
            "not innate model memory",
            "when an agent knows it has AIppocampus",
            "relationship continuity",
            "Action grammar and hook packet decoding live in",
            "Active Path Packets",
            "Primary foreground loop",
            "CLI chooser/recovery card",
        ):
            self.assertIn(phrase, skill_text)
        for phrase in (
            "direction_only",
            "reopenable_route",
            "bounded_evidence",
            "source_open",
            "ignore_or_blocked",
            "suggested_agent_action",
            "not_enough_for_claim",
        ):
            self.assertIn(phrase, ambient_hooks)
        for phrase in (
            "python3 -m",
            "py -m",
            "python -m aippocampus_runtime",
            "<path>",
            "<rollout.jsonl>",
            "<label>",
            "`python -m aippocampus_runtime.",
        ):
            self.assertNotIn(phrase, skill_text)

        self.assertIn("before broad manual search", " ".join(skill_text.split()))
        self.assertLess(
            agent_context.index("## First Move For Agents"),
            agent_context.index("## What AIppocampus Is"),
        )
        recall_cmd = 'aippocampus agent recall "old decision or handoff cue" --json'
        selector_deepen_cmd = (
            "aippocampus agent deepen --request 1 "
            "--recall-selector <emitted-selector> --json"
        )
        repair_section = skill_text.index("Setup, repair, storage, provider")
        self.assertLess(
            skill_text.index(recall_cmd),
            skill_text.index(selector_deepen_cmd),
        )
        self.assertIn(
            "`--last-recall` is a mutable",
            skill_text,
        )
        for phrase in (
            recall_cmd,
            selector_deepen_cmd,
            "source search/open",
            "Primary foreground loop",
        ):
            self.assertLess(skill_text.index(phrase), repair_section)
        self.assertIn("## Runtime Posture For Agents", agent_context)
        self.assertIn("cheap orientation", agent_context.lower())
        self.assertIn("explicit source reopen", agent_context.lower())
        self.assertIn("## Agent Runtime Posture", coding_lane)
        self.assertIn("before broad manual search", " ".join(coding_lane.split()))

    def test_skill_hook_packet_decoder_maps_signals_to_actions(self) -> None:
        reference_text = (ROOT / "references" / "ambient-hooks.md").read_text(
            encoding="utf-8"
        )
        start = reference_text.index("### Hook Packet Decoder")
        end = reference_text.index("Foreground brief rendering")
        decoder = reference_text[start:end]
        decoder_flat = " ".join(decoder.split())

        self.assertIn("| Signal | Default action | Avoid |", decoder)
        for phrase in (
            "suggested_agent_action=agent_recall",
            "not_enough_for_claim=true",
            "direction_with_ref",
            "reopenable_route",
            "bounded_evidence",
            "ignore_or_blocked",
            "before broad manual search",
            "deepen",
            "reopen",
        ):
            self.assertIn(phrase, decoder_flat)
        self.assertLessEqual(decoder.count("| `"), 8)
        self.assertNotIn("full packet schema", decoder.lower())

if __name__ == "__main__":
    unittest.main()
