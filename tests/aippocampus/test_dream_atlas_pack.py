from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.dream import atlas_pack  # noqa: E402


class DreamAtlasPackTests(unittest.TestCase):
    def test_fixture_builds_cache_friendly_public_safe_atlas(self) -> None:
        report = atlas_pack.build_dream_atlas_report()
        atlas = report["atlas_pack"]

        self.assertEqual(report["kind"], "aippocampus_dream_long_context_atlas_report")
        self.assertTrue(report["contract_gate_ok"], json.dumps(report, indent=2))
        self.assertTrue(report["safety_gate_ok"], json.dumps(report, indent=2))
        self.assertEqual(atlas["kind"], "dream_long_context_atlas_pack")
        self.assertEqual(atlas["model_family"], "deepseek_v4")
        self.assertEqual(atlas["candidate_models"], ["deepseek-v4-flash", "deepseek-v4-pro"])
        self.assertEqual(atlas["context_window_tokens"], 1_000_000)
        self.assertEqual(atlas["cache_contract"], "deepseek_prefix_v1")
        self.assertEqual(
            atlas["prompt_order"],
            [
                "stable_dream_worker_contract",
                "stable_atlas_source_card_payload",
                "variable_run_directive",
            ],
        )
        self.assertEqual(atlas["privacy_mode"], "source_cards_only")
        self.assertEqual(atlas["selected_pack_count"], 4)
        self.assertEqual(atlas["source_ref_count"], 8)
        self.assertEqual(atlas["source_thread_count"], 4)
        self.assertGreater(atlas["estimated_token_budget"], 0)
        self.assertLess(atlas["estimated_token_budget"], atlas["context_window_tokens"])
        self.assertFalse(atlas["raw_source_text_included"])

        self.assertEqual(report["metrics"]["atlas_candidate_count"], 2)
        self.assertEqual(report["metrics"]["atlas_unique_candidate_count"], 2)
        self.assertEqual(report["metrics"]["source_ref_validity_rate"], 1.0)
        self.assertEqual(report["metrics"]["unsupported_candidate_count"], 0)
        self.assertEqual(report["metrics"]["bounded_pack_missed_bridge_or_cycle_count"], 2)
        self.assertIn(
            "python -m aippocampus_runtime.dream.atlas_pack",
            report["evaluation"]["command"],
        )
        self.assertEqual(report["evaluation"]["comparison"]["atlas_candidate_count"], 2)
        self.assertEqual(
            report["evaluation"]["comparison"]["bounded_pack_candidate_count"], 0
        )
        self.assertEqual(report["cache_telemetry"]["available"], False)
        self.assertIsNone(report["cache_telemetry"]["hit_rate"])

    def test_atlas_finds_cross_pack_bridge_and_cycle_that_bounded_packs_miss(self) -> None:
        report = atlas_pack.build_dream_atlas_report()
        candidates = {item["candidate_type"]: item for item in report["atlas_candidates"]}

        self.assertEqual(candidates["cross_pack_cycle"]["authority"], "dream_synthesized_candidate_not_fact")
        self.assertEqual(candidates["cross_pack_cycle"]["shape"], "cycle")
        self.assertEqual(candidates["cross_pack_cycle"]["source_ref_count"], 4)
        self.assertEqual(candidates["cross_pack_cycle"]["bounded_pack_detected"], False)

        self.assertEqual(candidates["cross_pack_bridge"]["shape"], "weak_bridge")
        self.assertEqual(candidates["cross_pack_bridge"]["source_thread_count"], 2)
        self.assertFalse(candidates["cross_pack_bridge"]["foreground_eligible"])
        self.assertTrue(candidates["cross_pack_bridge"]["source_reopen_required_before_claim"])

    def test_hard_negatives_and_live_cache_usage_boundary(self) -> None:
        rows = atlas_pack.fixture_pack_rows() + [
            {
                "pack_id": "source_free_symbolic",
                "status": "ready_for_dream_worker",
                "topic_epoch": "symbolic",
                "symbolic_claim": True,
                "source_refs": [],
            },
            {
                "pack_id": "profile_claim",
                "status": "ready_for_dream_worker",
                "topic_epoch": "profile",
                "profile_claim": True,
                "source_refs": ["public:profile:1"],
                "source_threads": ["thread-profile"],
            },
            {
                "pack_id": "missing_ref_candidate",
                "status": "ready_for_dream_worker",
                "topic_epoch": "missing-ref",
                "atlas_shape": "weak_bridge",
                "source_refs": [],
            },
        ]
        report = atlas_pack.build_dream_atlas_report(
            rows,
            provider_usage={
                "prompt_cache_hit_tokens": 120,
                "prompt_cache_miss_tokens": 30,
            },
        )
        rejected = {item["pack_id"]: item for item in report["rejected_packs"]}

        self.assertEqual(report["metrics"]["hard_negative_rejected_count"], 3)
        self.assertIn("source_free_symbolic_claim", rejected["source_free_symbolic"]["reasons"])
        self.assertIn("profile_claim", rejected["profile_claim"]["reasons"])
        self.assertIn("missing_source_refs", rejected["missing_ref_candidate"]["reasons"])
        self.assertEqual(report["cache_telemetry"]["available"], True)
        self.assertEqual(report["cache_telemetry"]["prompt_cache_hit_tokens"], 120)
        self.assertEqual(report["cache_telemetry"]["prompt_cache_miss_tokens"], 30)
        self.assertEqual(report["cache_telemetry"]["hit_rate"], 0.8)
        self.assertEqual(report["cache_telemetry"]["source"], "provider_usage")

    def test_cli_sanitizes_private_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "dream-atlas-private.json"
            rows = [
                {
                    "pack_id": "private_pack",
                    "status": "ready_for_dream_worker",
                    "topic_epoch": "private",
                    "source_refs": ["source://private/raw-ref"],
                    "source_threads": ["thread-private"],
                    "raw_source_text": "PRIVATE_DREAM_ATLAS_TEXT must not leave diagnostics",
                    "local_path": str(root / "private-rollout.jsonl"),
                }
            ]
            input_path.write_text(json.dumps(rows), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.dream.atlas_pack",
                    "--input",
                    str(input_path),
                    "--json",
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=REPO_ROOT,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["safety_gate_ok"])
        self.assertEqual(payload["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertNotIn("PRIVATE_DREAM_ATLAS_TEXT", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("source://private/raw-ref", encoded)


if __name__ == "__main__":
    unittest.main()
