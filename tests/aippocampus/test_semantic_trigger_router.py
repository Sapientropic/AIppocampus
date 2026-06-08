from __future__ import annotations

import hashlib
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
        seed_text = seed.read_text(encoding="utf-8")
        self.assertIn("外置小海马", seed_text)
        self.assertIn("hook worker handoff", seed_text)

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
        self.assertEqual(result["promoted_candidate_count"], 1)
        self.assertEqual(rows[0]["kind"], "aippocampus_semantic_trigger")
        self.assertIn("AIppocampus semantic recall gate", rows[0]["aliases"])
        self.assertEqual(rows[0]["source_refs"][0]["line"], 42)

    def test_trigger_key_uses_longer_sha256_identity(self) -> None:
        candidate = {
            "candidate_type": "hook_trigger",
            "title": "AIppocampus semantic recall gate",
            "source_finding_ids": ["finding-b", "finding-a"],
        }
        material = "\n".join(
            [
                "hook_trigger",
                "aippocampus semantic recall gate",
                "finding-a|finding-b",
            ]
        )

        self.assertEqual(
            router.trigger_key(candidate),
            "st_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24],
        )

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

    def test_fallback_aliases_drop_semigeneric_phrases_and_canonical_duplicates(self) -> None:
        self.write_candidates(
            [
                {
                    "kind": "aippocampus_promotion_candidate",
                    "status": "staging",
                    "candidate_type": "hook_trigger",
                    "title": "External Hippocampus",
                    "summary": (
                        "Project memory and source backed memory are too broad, "
                        "but external hippocampus is a specific routing cue."
                    ),
                    "recommendation": "Use external hippocampus when the prompt asks for recall.",
                    "concepts": [
                        "External Hippocampus",
                        "external hippocampus.",
                        "project memory",
                        "source backed memory",
                    ],
                    "confidence": 0.86,
                    "source_refs": [
                        {"thread_key": "session:a", "title": "AIppocampus", "line": 42}
                    ],
                }
            ]
        )

        result = router.build_semantic_triggers(
            candidates_path=self.candidates,
            output_path=self.output,
            seed_triggers_path=None,
        )
        rows = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]

        canonical_aliases = [alias.casefold() for alias in rows[0]["aliases"]]
        self.assertEqual(canonical_aliases.count("external hippocampus"), 1)
        self.assertNotIn("project memory", canonical_aliases)
        self.assertNotIn("source backed memory", canonical_aliases)
        self.assertGreater(result["dropped_alias_count"], 0)

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
                    "reviewed_at": "2026-06-02T00:00:00Z",
                    "reviewer": "AIppocampus maintainers",
                    "review_note": "Checked against the AIppocampus ambient-hook contract.",
                    "reviewed_seed_rationale": (
                        "Public AIppocampus architecture terms from the canonical docs."
                    ),
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

    def test_active_seed_requires_review_metadata_and_source_or_rationale(self) -> None:
        seed = self.root / "reviewed-seed.jsonl"
        rows = [
            {
                "schema_version": 1,
                "kind": "aippocampus_semantic_trigger",
                "trigger_id": "seed_missing_review",
                "status": "active",
                "source": "reviewed_seed",
                "title": "Missing review metadata",
                "aliases": ["external hippocampus"],
                "confidence": 0.88,
            },
            {
                "schema_version": 1,
                "kind": "aippocampus_semantic_trigger",
                "trigger_id": "seed_external_hippocampus_legacy",
                "status": "active",
                "source": "reviewed_seed",
                "title": "External hippocampus recall continuity",
                "aliases": ["external hippocampus"],
                "when_to_use": "Use when the user asks to continue AIppocampus memory work.",
                "when_not_to_use": "Do not use for plain implementation tasks.",
                "reviewed_at": "2026-06-02T00:00:00Z",
                "reviewer": "AIppocampus maintainers",
                "review_note": "Checked against the AIppocampus ambient-hook contract.",
                "reviewed_seed_rationale": (
                    "Seeded AIppocampus architecture terms are public product vocabulary."
                ),
                "confidence": 0.88,
            },
        ]
        seed.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        self.write_candidates([])

        result = router.build_semantic_triggers(
            candidates_path=self.candidates,
            output_path=self.output,
            seed_triggers_path=seed,
        )
        written = [
            json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()
        ]

        self.assertEqual(result["seed_trigger_count"], 1)
        self.assertEqual(result["skipped_missing_review_or_source_count"], 1)
        self.assertEqual(result["skipped_seed_reasons"], {"missing_reviewed_at": 1})
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["title"], "External hippocampus recall continuity")

    def test_seed_trigger_ids_migrate_to_sha256_with_legacy_id_retained(self) -> None:
        seed = self.root / "reviewed-seed.jsonl"
        seed.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_semantic_trigger",
                    "trigger_id": "seed_external_hippocampus_legacy",
                    "status": "active",
                    "source": "reviewed_seed",
                    "title": "External hippocampus recall continuity",
                    "aliases": ["external hippocampus"],
                    "when_to_use": "Use when the user asks to continue AIppocampus memory work.",
                    "when_not_to_use": "Do not use for plain implementation tasks.",
                    "reviewed_at": "2026-06-02T00:00:00Z",
                    "reviewer": "AIppocampus maintainers",
                    "review_note": "Checked against the AIppocampus ambient-hook contract.",
                    "reviewed_seed_rationale": (
                        "Seeded AIppocampus architecture terms are public product vocabulary."
                    ),
                    "confidence": 0.88,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_candidates([])

        router.build_semantic_triggers(
            candidates_path=self.candidates,
            output_path=self.output,
            seed_triggers_path=seed,
        )
        written = [
            json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()
        ]

        self.assertRegex(written[0]["trigger_id"], r"^st_[0-9a-f]{24}$")
        self.assertIn("seed_external_hippocampus_legacy", written[0]["legacy_trigger_ids"])

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
        self.assertEqual(result["promoted_candidate_count"], 0)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
