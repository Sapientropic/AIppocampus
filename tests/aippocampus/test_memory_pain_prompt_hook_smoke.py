from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SMOKE))
sys.path.insert(0, str(BENCHMARKS))

import smoke_memory_pain_prompt_hook as smoke  # noqa: E402

import aippocampus_prompt_hook as hook  # noqa: E402
from build_index import make_sqlite  # noqa: E402


class MemoryPainPromptHookSmokeTests(unittest.TestCase):
    def test_real_history_smoke_output_is_hash_only_by_default(self) -> None:
        private_marker = "PRIVATE_REAL_HISTORY_PROMPT_MARKER"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry" / "threads.json"
            registry.parent.mkdir()
            registry.write_text(
                json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = smoke.run_memory_pain_smoke(
                [
                    {
                        "name": "private case name",
                        "kind": "negative",
                        "prompt": f"{private_marker}: keep this unsupported without a cited row",
                    }
                ],
                cwd=root,
                registry_path=registry,
                semantic_gate_mode="off",
                show_names=False,
            )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["privacy"], "aggregate_hash_only")
        self.assertNotIn(private_marker, rendered)
        self.assertNotIn("private case name", rendered)
        self.assertIn("case_hash", result["rows"][0])
        self.assertNotIn("prompt", result["rows"][0])

    def test_positive_misses_fail_smoke_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry" / "threads.json"
            registry.parent.mkdir()
            registry.write_text(
                json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(
                smoke,
                "assess_prompt",
                return_value={
                    "decision": "scent",
                    "confidence": "medium",
                    "score": 1.0,
                    "candidates": [],
                    "evidence": [],
                    "semantic_gate": {},
                    "elapsed_ms": 1.0,
                },
            ):
                result = smoke.run_memory_pain_smoke(
                    [{"name": "positive", "kind": "positive", "prompt": "找一下旧证据"}],
                    cwd=root,
                    registry_path=registry,
                )

        self.assertEqual(result["positive_miss_count"], 1)
        self.assertFalse(result["ok"])

    def test_russian_case_family_is_hash_only_and_tracks_expected_boundaries(self) -> None:
        cases = smoke.load_cases(None, case_family="russian")
        kinds = {str(case.get("kind") or "") for case in cases}
        self.assertIn("negative", kinds)
        self.assertIn("positive", kinds)

        by_prompt = {str(case.get("prompt") or ""): str(case.get("kind") or "") for case in cases}

        def fake_assess_prompt(prompt: str, **kwargs) -> dict:
            kind = by_prompt[prompt]
            if kind == "positive":
                return {
                    "decision": "evidence",
                    "confidence": "high",
                    "score": 8.0,
                    "candidates": [{"thread_key": "redacted"}],
                    "evidence": [{"line": 1, "snippet": "redacted"}],
                    "semantic_gate": {},
                    "elapsed_ms": 1.0,
                }
            return {
                "decision": "scent",
                "confidence": "medium",
                "score": 2.0,
                "candidates": [],
                "evidence": [],
                "semantic_gate": {},
                "elapsed_ms": 1.0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry" / "threads.json"
            registry.parent.mkdir()
            registry.write_text(
                json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch.object(smoke, "assess_prompt", side_effect=fake_assess_prompt):
                result = smoke.run_memory_pain_smoke(
                    cases,
                    cwd=root,
                    registry_path=registry,
                    show_names=False,
                )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"])
        self.assertNotIn("внешний гиппокамп", rendered)
        self.assertNotIn("Neon City", rendered)
        self.assertNotIn("ru_pos_external_hippocampus_wording", rendered)
        self.assertEqual(result["privacy"], "aggregate_hash_only")

    def test_russian_real_history_case_family_captures_stricter_probe_shapes(self) -> None:
        cases = smoke.load_cases(None, case_family="russian-real-history")
        names = {str(case.get("name") or "") for case in cases}

        self.assertIn("ru_real_pos_prior_raw_history_wording", names)
        self.assertIn("ru_real_neg_do_not_upgrade_without_source_row", names)
        self.assertIn("ru_real_vague_cross_project_plan", names)

    def test_vague_cross_project_natural_evidence_stays_scent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            registry = root / "registry" / "threads.json"
            registry.parent.mkdir()
            entries = []
            for name, label, line in (
                ("alpha", "Alpha project", "Alpha 方案的结论是保留本地优先。"),
                ("beta", "Beta project", "Beta 方案的结论是先做远端验证。"),
            ):
                sqlite_path = root / name / "index" / "source_index.sqlite"
                sqlite_path.parent.mkdir(parents=True)
                make_sqlite(
                    sqlite_path,
                    [
                        {
                            "line": 1,
                            "timestamp": "2026-05-30T00:00:00Z",
                            "role": "assistant",
                            "kind": "message",
                            "phase": "final_answer",
                            "turn_index": 1,
                            "is_final": True,
                            "sha1": name,
                            "text": line,
                        }
                    ],
                    anchors=[],
                    turns=[],
                )
                entries.append(
                    {
                        "thread_key": f"session:{name}",
                        "title": f"{label} planning",
                        "workspace_name": label,
                        "project_label": label,
                        "updated_at": "2026-05-30T00:00:00Z",
                        "anchor_titles": ["方案结论"],
                        "keywords": ["方案", "结论", "上次"],
                        "summary": f"{label} 方案结论",
                        "paths": {"workspace": str(workspace), "sqlite": str(sqlite_path)},
                    }
                )
            registry.write_text(
                json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = hook.assess_prompt(
                "上次我们讨论的那个方案怎么说来着？",
                cwd=workspace,
                registry_path=registry,
                search_budget=3,
                use_semantic_gate=False,
            )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])
        self.assertIn(
            "source evidence withheld: vague cross-project referent",
            result["reasons"],
        )


if __name__ == "__main__":
    unittest.main()
