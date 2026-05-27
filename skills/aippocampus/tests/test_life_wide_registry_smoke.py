from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import smoke_life_wide_registry as smoke  # noqa: E402


class LifeWideRegistrySmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry_dir = self.root / "registry"
        self.registry_dir.mkdir()
        self.registry_path = self.registry_dir / "threads.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_thread(
        self,
        name: str,
        *,
        labels: list[str] | None = None,
        semantic_sidecar: bool = False,
        bad_jsonl: bool = False,
    ) -> dict:
        clean = self.root / name / "clean-source"
        index = self.root / name / "index"
        clean.mkdir(parents=True)
        index.mkdir(parents=True)
        (clean / "manifest.json").write_text(
            json.dumps({"schema_version": 2}, ensure_ascii=False),
            encoding="utf-8",
        )
        message = {
            "message_id": f"{name}-u",
            "turn_id": f"{name}-turn",
            "source_line": 10,
            "timestamp": "2026-05-27T00:00:00Z",
            "role": "user",
            "turn_index": 1,
            "scope_labels": labels or [],
            "text": f"private text for {name} should not appear",
        }
        messages_text = json.dumps(message, ensure_ascii=False) + "\n"
        if bad_jsonl:
            messages_text += "{bad json\n"
        (clean / "messages.jsonl").write_text(messages_text, encoding="utf-8")
        (clean / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": f"{name}-turn",
                    "turn_index": 1,
                    "message_ids": [f"{name}-u"],
                    "scope_labels": labels or [],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if semantic_sidecar:
            (clean / "semantic-scope-labels.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": f"{name}-u",
                        "source": "deepseek_subconscious_scope_labels",
                        "scope_labels": ["idea_seed"],
                        "source_refs": [{"message_id": f"{name}-u", "source_line": 10}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        (index / "graph.json").write_text(json.dumps({"nodes": []}), encoding="utf-8")
        (index / "source_index.sqlite").write_bytes(b"sqlite")
        return {
            "thread_key": f"session:{name}",
            "title": f"Private title {name}",
            "project_key": f"project:{name}",
            "project_label": f"Private project {name}",
            "paths": {
                "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                "clean_source_turns_jsonl": str(clean / "turns.jsonl"),
                "sqlite": str(index / "source_index.sqlite"),
                "graph_json": str(index / "graph.json"),
            },
        }

    def _write_registry(self, entries: list[dict]) -> None:
        self.registry_path.write_text(json.dumps({"threads": entries}, ensure_ascii=False), encoding="utf-8")

    def test_smoke_reports_counts_without_private_text_or_refs(self) -> None:
        self._write_registry(
            [
                self._write_thread("reflection", labels=["personal_reflection", "open_question"]),
                self._write_thread("idea", labels=["idea_seed"], semantic_sidecar=True),
            ]
        )

        result = smoke.run_life_wide_registry_smoke(
            self.registry_path,
            require_evidence=True,
            min_life_labels=2,
            min_life_threads=2,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["stage2_evidence_status"], "sufficient")
        self.assertFalse(result["privacy_boundary"]["raw_text_emitted"])
        self.assertIn("personal_reflection", result["scope_label_coverage"]["labels"])
        self.assertIn("idea_seed", result["timeline_coverage"]["labels"])
        self.assertNotIn("private text", rendered)
        self.assertNotIn("Private title", rendered)
        self.assertNotIn("source_refs", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertEqual(result["claim_level"], "first_pass_real_history_slice")
        self.assertIn("full_history_refresh", result["cannot_claim"])
        self.assertEqual(result["coverage_ratios"]["labeled_message_ratio"], 1.0)
        self.assertEqual(result["coverage_ratios"]["life_labeled_thread_ratio"], 1.0)
        self.assertEqual(result["coverage_ratios"]["semantic_sidecar_thread_ratio"], 0.5)
        self.assertEqual(result["coverage_ratios"]["semantic_sidecar_row_count"], 1)

    def test_missing_labels_are_diagnostic_unless_evidence_required(self) -> None:
        self._write_registry([self._write_thread("old-schema")])

        diagnostic = smoke.run_life_wide_registry_smoke(self.registry_path, require_evidence=False)
        required = smoke.run_life_wide_registry_smoke(self.registry_path, require_evidence=True)

        self.assertTrue(diagnostic["ok"])
        self.assertEqual(diagnostic["stage2_evidence_status"], "insufficient_scope_label_coverage")
        self.assertEqual(diagnostic["claim_level"], "diagnostic_only")
        self.assertFalse(required["ok"])

    def test_bad_jsonl_is_counted_without_leaking_path(self) -> None:
        self._write_registry([self._write_thread("bad", labels=["preference"], bad_jsonl=True)])

        result = smoke.run_life_wide_registry_smoke(
            self.registry_path,
            require_evidence=False,
            compute_timeline=False,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["warnings"]["bad_clean_source_message_rows"], 1)
        self.assertIsNone(result["timeline_coverage"])
        self.assertNotIn(str(self.root), rendered)

    def test_missing_registry_can_be_skipped_for_public_environments(self) -> None:
        missing = self.root / "missing" / "threads.json"

        diagnostic = smoke.run_life_wide_registry_smoke(missing, require_evidence=False)
        required = smoke.run_life_wide_registry_smoke(missing, require_evidence=True)

        self.assertTrue(diagnostic["ok"])
        self.assertEqual(diagnostic["stage2_evidence_status"], "skipped_missing_registry")
        self.assertFalse(required["ok"])

    def test_timeline_computation_does_not_write_project_timeline(self) -> None:
        self._write_registry([self._write_thread("life", labels=["life_context", "preference"])])

        smoke.run_life_wide_registry_smoke(self.registry_path, compute_timeline=True)

        self.assertFalse((self.registry_dir / "project_timeline.json").exists())


if __name__ == "__main__":
    unittest.main()
