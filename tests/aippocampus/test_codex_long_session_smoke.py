from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
sys.path.insert(0, str(SMOKE))

import smoke_codex_long_session_continuity as live_smoke  # noqa: E402


class CodexLongSessionSmokeTests(unittest.TestCase):
    def test_correction_survival_uses_hashes_without_raw_tokens(self) -> None:
        evidence = live_smoke.correction_survival_evidence(
            "The current route code is LIVEFIXABC12345.",
            "LIVEFIXABC12345",
            "LIVEOLDABC12345",
        )

        self.assertTrue(evidence["assistant_recalled_corrected_token"])
        self.assertTrue(evidence["assistant_avoided_obsolete_token"])
        self.assertNotIn("LIVEFIXABC12345", json.dumps(evidence))
        self.assertNotIn("LIVEOLDABC12345", json.dumps(evidence))

    def test_clean_source_evidence_detects_correction_and_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            turns = root / "turns.jsonl"
            messages.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "role": "user",
                                "text": (
                                    "Correction: LIVEOLD123 is stale. "
                                    "Use LIVEFIX123 instead."
                                ),
                            }
                        ),
                        json.dumps({"role": "assistant", "text": "LIVEFIX123"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            turns.write_text(json.dumps({"turn_id": "turn-1"}) + "\n", encoding="utf-8")
            manifest = {
                "message_count": 2,
                "turn_count": 1,
                "outputs": {
                    "messages_jsonl": str(messages),
                    "turns_jsonl": str(turns),
                },
            }

            evidence = live_smoke.clean_source_evidence(
                manifest,
                corrected_token="LIVEFIX123",
                obsolete_token="LIVEOLD123",
                target_pre_compact_turns=1,
            )

        self.assertTrue(evidence["built_from_real_rollout"])
        self.assertTrue(evidence["correction_message_found"])
        self.assertTrue(evidence["recall_answer_found"])
        self.assertFalse(evidence["stale_recall_answer_found"])

    def test_report_validation_requires_compaction_and_clean_source(self) -> None:
        report = live_smoke.result_skeleton("unit-run", 2)
        report["scenario"].update(
            {
                "completed_pre_compact_turn_count": 2,
                "completed_total_turn_count": 4,
                "correction_event_observed": True,
                "compaction_observed": True,
                "recall_turn_completed": True,
                "clean_source_verified": True,
            }
        )
        report["evidence"]["turn_count"].update(
            {"pre_compact_completed": 2, "total_completed": 4}
        )
        report["evidence"]["compaction_boundary"].update(
            {
                "compact_turn_completed": True,
                "context_compaction_item_observed": True,
                "pre_compact_hook_completed": True,
                "post_compact_hook_completed": True,
                "hook_events_observed": ["postCompact", "preCompact"],
            }
        )
        report["evidence"]["correction_survival"] = {
            "assistant_recalled_corrected_token": True,
            "assistant_avoided_obsolete_token": True,
        }
        report["evidence"]["clean_source"] = {
            "built_from_real_rollout": True,
            "correction_message_found": True,
            "recall_answer_found": True,
            "stale_recall_answer_found": False,
        }

        ok, failures = live_smoke.validate_report(report)

        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_public_payload_scan_catches_local_paths(self) -> None:
        synthetic_local_path = "E:" + r"\Private\rollout.jsonl"

        found = live_smoke.sensitive_string_issues({"value": synthetic_local_path})

        self.assertEqual(found[0]["code"], "local_path_in_public_payload")
        self.assertNotIn("Private", json.dumps(found))

    def test_run_id_segment_remains_filename_safe(self) -> None:
        segment = live_smoke.safe_run_id_segment(r"..\unsafe/private id")

        self.assertEqual(segment, "unsafe-private-id")

    def test_status_classifies_missing_codex_as_host_skip_before_thread_start(self) -> None:
        self.assertTrue(
            live_smoke.classify_unavailable(
                FileNotFoundError("could not find codex on PATH"),
                thread_started=False,
            )
        )
        self.assertFalse(
            live_smoke.classify_unavailable(
                RuntimeError("compaction did not preserve correction"),
                thread_started=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
