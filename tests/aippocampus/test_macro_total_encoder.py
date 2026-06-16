from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import total_encoder  # noqa: E402
from aippocampus_runtime.recall import macro_live_recall  # noqa: E402


def ref(name: str) -> dict[str, str]:
    return {"source_id": f"macro-source:{name}", "message_id": f"msg:{name}"}


class MacroTotalEncoderTests(unittest.TestCase):
    def test_total_encoder_derives_complete_state_with_per_line_provenance(self) -> None:
        report = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            line_signals=[
                {"line": 1, "value": 1, "source_refs": [ref("line-1")]},
                {"line": 2, "value": 0, "source_refs": [ref("line-2")]},
                {"line": 3, "value": 1, "source_refs": [ref("line-3")]},
                {"line": 4, "value": 0, "source_refs": [ref("line-4")]},
                {"line": 5, "value": 1, "source_refs": [ref("line-5")]},
                {"line": 6, "value": 0, "source_refs": [ref("line-6")]},
            ],
            changing_line_signals=[{"line": 2, "source_refs": [ref("changing-2")]}],
            active_layer_signal={"active_layer": "earth", "source_refs": [ref("layer")]},
            momentum_signal={"phase_hint": "rising", "source_refs": [ref("momentum")]},
        )
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["status"], "derived_complete")
        self.assertEqual(report["hexagram"]["bits_bottom_to_top"], "101010")
        self.assertEqual(len(report["line_provenance"]), 6)
        self.assertEqual(report["line_provenance"][0]["authority"], "source_backed")
        self.assertTrue(report["usable_for_recall_fanout"])
        self.assertTrue(report["usable_for_recheck_timing"])
        self.assertEqual(report["authority"], "navigation_only")
        self.assertIn("macro_state_hint", report)
        self.assertNotIn("PRIVATE_MACRO_TEXT", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_total_encoder_degrades_partial_ambiguous_explicit_and_blocked_inputs(self) -> None:
        partial = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            line_signals=[{"line": 1, "value": 1, "source_refs": [ref("line-1")]}],
        )
        ambiguous = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            line_signals=[
                {"line": 1, "value": 1, "source_refs": [ref("a")]},
                {"line": 1, "value": 0, "source_refs": [ref("b")]},
            ],
        )
        explicit = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            explicit_reviewed_state={
                "lines_bottom_to_top": [1, 1, 1, 0, 0, 0],
                "source_refs": [ref("reviewed")],
            },
        )
        blocked = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            line_signals=[
                {
                    "line": 1,
                    "value": 1,
                    "source_refs": [ref("private")],
                    "privacy_scope": "private_local",
                }
            ],
        )

        self.assertEqual(partial["status"], "derived_partial")
        self.assertFalse(partial["usable_for_recall_fanout"])
        self.assertIn("unknown", {line["state"] for line in partial["line_provenance"]})
        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertFalse(ambiguous["usable_for_recall_fanout"])
        self.assertEqual(explicit["status"], "explicit_reviewed")
        self.assertTrue(explicit["explicit_reviewed_input"])
        self.assertFalse(explicit["automatic_derivation"])
        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(blocked["usable_for_recall_fanout"])

    def test_macro_live_recall_uses_total_encoding_only_when_complete_or_reviewed(self) -> None:
        complete = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            line_signals=[
                {"line": 1, "value": 1, "source_refs": [ref("line-1")]},
                {"line": 2, "value": 1, "source_refs": [ref("line-2")]},
                {"line": 3, "value": 1, "source_refs": [ref("line-3")]},
                {"line": 4, "value": 1, "source_refs": [ref("line-4")]},
                {"line": 5, "value": 1, "source_refs": [ref("line-5")]},
                {"line": 6, "value": 1, "source_refs": [ref("line-6")]},
            ],
            active_layer_signal={"active_layer": "heaven", "source_refs": [ref("layer")]},
        )
        partial = total_encoder.build_total_hexagram_encoding(
            project="AIppocampus",
            line_signals=[{"line": 1, "value": 1, "source_refs": [ref("line-1")]}],
        )

        context = macro_live_recall.context_from_projection(
            {"status": "current", "macro_total_encoding": complete}
        )
        degraded = macro_live_recall.context_from_projection(
            {"status": "current", "macro_total_encoding": partial}
        )
        diagnostics = macro_live_recall.navigation_diagnostics(
            projection={"status": "current", "macro_total_encoding": partial},
            context=degraded,
            requested_limit=2,
        )

        self.assertIsNotNone(context)
        self.assertIn("macro_state_derived_complete", macro_live_recall.reason_codes(context=context, projection_status="current"))
        self.assertIsNone(degraded)
        self.assertEqual(macro_live_recall.effective_route_limit(requested_limit=2, context=degraded), 2)
        self.assertIn("macro_state_degraded", diagnostics["reason_codes"])


if __name__ == "__main__":
    unittest.main()
