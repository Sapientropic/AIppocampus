from __future__ import annotations

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

from aippocampus_runtime.recall import semantic_trigger_router as router  # noqa: E402


class SemanticTriggerRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.candidates = self.root / "promotion_candidates.jsonl"
        self.output = self.root / "semantic_triggers.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_candidates(self, rows: list[dict]) -> None:
        with self.candidates.open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_default_reviewed_seed_path_survives_package_layout(self) -> None:
        seed = router.default_seed_triggers_path()

        self.assertEqual(seed.name, "reviewed-semantic-triggers.seed.jsonl")
        self.assertTrue(seed.exists(), seed)

    def test_hook_trigger_candidate_becomes_semantic_trigger(self) -> None:
        self.write_candidates(
            [
                {
                    "kind": "aippocampus_promotion_candidate",
                    "status": "staging",
                    "candidate_type": "hook_trigger",
                    "title": "AIppocampus semantic recall gate",
                    "summary": "DeepSeek semantic gate replaces brittle hard-coded cue phrases for ambient recall.",
                    "recommendation": "Use semantic aliases when user paraphrases memory continuity.",
                    "confidence": 0.86,
                    "source_refs": [
                        {"thread_key": "session:a", "title": "AIppocampus", "line": 42}
                    ],
                }
            ]
        )

        result = router.build_semantic_triggers(
            candidates_path=self.candidates, output_path=self.output
        )
        rows = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["trigger_count"], 1)
        self.assertEqual(rows[0]["kind"], "aippocampus_semantic_trigger")
        self.assertIn("AIppocampus semantic recall gate", rows[0]["aliases"])
        self.assertEqual(rows[0]["source_refs"][0]["line"], 42)

    def test_activation_cues_drive_natural_friction_trigger_aliases(self) -> None:
        self.write_candidates(
            [
                {
                    "kind": "aippocampus_promotion_candidate",
                    "status": "staging",
                    "candidate_type": "hook_trigger",
                    "title": "Reviewed semantic hook",
                    "summary": "A source-backed hook that should be activated by model-authored cues.",
                    "recommendation": "Use the subconscious cue surface rather than summary prose.",
                    "activation_cues": [
                        "最近让我很烦",
                        "recent personal friction",
                        "что меня раздражало недавно",
                    ],
                    "confidence": 0.88,
                    "source_refs": [
                        {"thread_key": "session:friction", "title": "Friction thread", "line": 77}
                    ],
                }
            ]
        )

        result = router.build_semantic_triggers(
            candidates_path=self.candidates, output_path=self.output
        )
        rows = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["trigger_count"], 1)
        self.assertIn("最近让我很烦", rows[0]["aliases"])
        self.assertIn("recent personal friction", rows[0]["aliases"])
        self.assertIn("что меня раздражало недавно", rows[0]["aliases"])
        self.assertEqual(rows[0]["activation_cues"][0], "最近让我很烦")
        self.assertNotIn("source-backed hook", " ".join(rows[0]["aliases"]).casefold())

    def test_reviewed_seed_triggers_are_written_to_semantic_trigger_sidecar(self) -> None:
        seed = self.root / "reviewed-seed.jsonl"
        seed.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_semantic_trigger",
                    "trigger_id": "seed_external_hippocampus",
                    "status": "active",
                    "source": "reviewed_seed",
                    "title": "External hippocampus recall continuity",
                    "aliases": ["external hippocampus", "外置海马体"],
                    "when_to_use": "Use when the user asks to continue AIppocampus memory work.",
                    "when_not_to_use": "Do not use for plain implementation tasks.",
                    "confidence": 0.88,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_candidates([])

        result = router.build_semantic_triggers(
            candidates_path=self.candidates,
            output_path=self.output,
            seed_triggers_path=seed,
        )
        rows = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["seed_trigger_count"], 1)
        self.assertEqual(result["trigger_count"], 1)
        self.assertEqual(rows[0]["source"], "reviewed_seed")
        self.assertIn("external hippocampus", rows[0]["aliases"])

    def test_low_confidence_or_unsourced_candidate_is_not_foreground_trigger(self) -> None:
        self.write_candidates(
            [
                {
                    "kind": "aippocampus_promotion_candidate",
                    "candidate_type": "hook_trigger",
                    "title": "Too weak",
                    "summary": "Nope",
                    "confidence": 0.4,
                    "source_refs": [{"thread_key": "session:a", "line": 1}],
                },
                {
                    "kind": "aippocampus_promotion_candidate",
                    "candidate_type": "hook_trigger",
                    "title": "No source",
                    "summary": "Nope",
                    "confidence": 0.9,
                    "source_refs": [],
                },
            ]
        )

        result = router.build_semantic_triggers(
            candidates_path=self.candidates, output_path=self.output
        )
        self.assertEqual(result["trigger_count"], 0)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
