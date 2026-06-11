from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import state  # noqa: E402


class MacroOrientationStateTests(unittest.TestCase):
    def test_project_scoped_state_validates_and_projects_latest(self) -> None:
        entry = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="蹇",
            changing_lines=(3,),
            source_refs=({"source_id": "roadmap-shift-1"},),
            updated_at="2026-06-11T10:00:00Z",
        )

        validation = state.validate_macro_orientation_state(entry)
        projection = state.latest_project_macro_orientation(
            [entry],
            project="AIppocampus",
            now=datetime(2026, 6, 12, tzinfo=timezone.utc),
        )

        self.assertTrue(validation["ok"], validation)
        self.assertEqual(entry["scope"], {"kind": "project", "project": "AIppocampus"})
        self.assertEqual(entry["write_scale"], "project")
        self.assertEqual(entry["authority_level"], "navigation_only")
        self.assertEqual(entry["action_grammar"], "direction_only")
        self.assertEqual(entry["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(entry["hexagram"]["bits_bottom_to_top"], "001010")
        self.assertEqual(entry["relation_position"]["situation_role"], "世")
        self.assertEqual(entry["relation_position"]["current_agent_default_role"], "应")
        self.assertEqual(entry["momentum"]["authority_level"], "navigation_only")
        self.assertEqual(projection["status"], "current")
        self.assertTrue(projection["usable_as_current_navigation_pointer"])
        self.assertFalse(projection["usable_as_current_instruction"])
        self.assertEqual(
            projection["diagnostics"]["source_refs"],
            [{"source_id": "roadmap-shift-1"}],
        )

    def test_non_project_signal_requires_promotion(self) -> None:
        entry = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="屯",
            input_signal_scales=("journey",),
            updated_at="2026-06-11T10:00:00Z",
        )
        promoted = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="屯",
            input_signal_scales=("journey",),
            promotion_reason="explicit_review",
            updated_at="2026-06-11T10:00:00Z",
        )

        validation = state.validate_macro_orientation_state(entry)
        self.assertFalse(validation["ok"])
        self.assertIn("non_project_signal_requires_promotion", validation["errors"])
        self.assertTrue(state.validate_macro_orientation_state(promoted)["ok"])

    def test_stale_missing_source_and_conflicts_degrade_to_diagnostics(self) -> None:
        stale = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="屯",
            source_refs=({"source_id": "old-roadmap"},),
            updated_at="2026-01-01T00:00:00Z",
            stale_after_days=7,
        )
        missing_source = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="屯",
            updated_at="2026-06-11T10:00:00Z",
        )
        conflict_a = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="屯",
            source_refs=({"source_id": "a"},),
            updated_at="2026-06-11T11:00:00Z",
        )
        conflict_b = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="蒙",
            source_refs=({"source_id": "b"},),
            updated_at="2026-06-11T11:00:00Z",
        )

        stale_projection = state.latest_project_macro_orientation(
            [stale],
            project="AIppocampus",
            now=datetime(2026, 6, 11, tzinfo=timezone.utc),
        )
        missing_projection = state.latest_project_macro_orientation(
            [missing_source],
            project="AIppocampus",
            now=datetime(2026, 6, 11, tzinfo=timezone.utc),
        )
        conflict_projection = state.latest_project_macro_orientation(
            [conflict_a, conflict_b],
            project="AIppocampus",
            now=datetime(2026, 6, 11, tzinfo=timezone.utc),
        )

        self.assertEqual(stale_projection["status"], "stale")
        self.assertEqual(missing_projection["status"], "missing_source")
        self.assertEqual(conflict_projection["status"], "conflicting")
        for projection in (stale_projection, missing_projection, conflict_projection):
            self.assertFalse(projection["usable_as_current_navigation_pointer"])
            self.assertFalse(projection["usable_as_current_instruction"])
            self.assertTrue(projection["diagnostic_only"])

    def test_append_load_and_raw_private_text_rejection(self) -> None:
        entry = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="屯",
            source_refs=({"source_id": "source-1"},),
            updated_at="2026-06-11T10:00:00Z",
        )
        bad = dict(entry)
        bad["source_refs"] = [{"source_id": "source-1", "raw_text": "PRIVATE"}]
        bad_lines = dict(entry)
        bad_lines["changing_lines"] = ["1"]
        bad_promotion = dict(entry)
        bad_promotion["promotion"] = {"reason": "symbolic_hunch"}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "macro-orientation.jsonl"
            state.append_macro_orientation_state(path, entry)
            loaded = state.load_macro_orientation_states(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["state_id"], entry["state_id"])
        self.assertFalse(state.validate_macro_orientation_state(bad_lines)["ok"])
        self.assertIn(
            "promotion_reason_invalid",
            state.validate_macro_orientation_state(bad_promotion)["errors"],
        )
        with self.assertRaises(ValueError):
            state.append_macro_orientation_state(Path("ignored.jsonl"), bad)

    def test_momentum_block_is_reserved_not_claim_authority(self) -> None:
        momentum = state.default_momentum_block()

        self.assertEqual(set(momentum["basis"]), set(state.MOMENTUM_BASIS_KEYS))
        self.assertEqual(momentum["authority_level"], "navigation_only")
        self.assertEqual(momentum["phase"], "kun")
        self.assertEqual(momentum["direction"], "hibernating")
        self.assertEqual(momentum["claim_permission"], "no_claim_before_reopen")
        self.assertFalse(momentum["fact_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
