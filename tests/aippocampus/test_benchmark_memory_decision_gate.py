from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
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

import benchmark_memory_decision_gate as benchmark  # noqa: E402


class MemoryDecisionGateBenchmarkTests(unittest.TestCase):
    def test_summarize_results_counts_three_class_errors(self) -> None:
        results = [
            {"expected": "should_skip", "actual": "skip", "case_type": "ordinary_code"},
            {"expected": "should_scent", "actual": "evidence", "case_type": "weak_deictic"},
            {"expected": "should_evidence", "actual": "scent", "case_type": "explicit_recall"},
            {"expected": "should_skip", "actual": "evidence", "case_type": "secret_like"},
        ]

        metrics = benchmark.summarize_results(results)

        self.assertEqual(metrics["total_cases"], 4)
        self.assertEqual(metrics["confusion"]["should_scent"]["evidence"], 1)
        self.assertEqual(metrics["over_escalation_count"], 1)
        self.assertEqual(metrics["evidence_false_positive_count"], 2)
        self.assertGreater(metrics["weighted_false_positive_cost"], 0)

    def test_synthetic_gate_benchmark_is_sanitized_and_measures_current_behavior(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)

        self.assertEqual(payload["kind"], "aippocampus_memory_decision_gate_benchmark")
        self.assertGreaterEqual(payload["metrics"]["total_cases"], 5)
        self.assertIn("macro_f1", payload["metrics"])
        self.assertGreaterEqual(payload["metrics"]["scent_or_evidence_recall"], 0.9)
        self.assertGreaterEqual(payload["metrics"]["evidence_recall"], 0.85)
        self.assertLessEqual(payload["metrics"]["evidence_false_positive_count"], 1)
        self.assertLessEqual(payload["metrics"]["weighted_false_positive_cost"], 20.0)
        self.assertEqual(payload["privacy_boundary"]["raw_prompt_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_emitted"], False)
        for case in payload["cases"]:
            self.assertIn("prompt_sha1", case)
            self.assertNotIn("prompt", case)
            self.assertNotIn("registry", case)
            self.assertNotIn("evidence", case)
            self.assertIn(case["expected"], benchmark.EXPECTED_LABELS)
            self.assertIn(case["actual"], benchmark.ACTUAL_DECISIONS)

    def test_synthetic_gate_benchmark_can_emit_private_debug_text_explicitly(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=True)

        self.assertTrue(any("prompt" in case for case in payload["cases"]))
        self.assertEqual(payload["privacy_boundary"]["raw_prompt_emitted"], True)

    def test_synthetic_gate_benchmark_includes_harder_case_family(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)
        by_type = {case["case_type"]: case for case in payload["cases"]}

        self.assertEqual(by_type["hard_ambiguous_same_entity_should_skip"]["actual"], "skip")
        self.assertEqual(by_type["hard_cross_project_same_entity_should_scent"]["actual"], "scent")
        self.assertEqual(by_type["hard_mixed_language_continuation_should_scent"]["actual"], "scent")
        self.assertFalse(by_type["hard_ambiguous_same_entity_should_skip"]["semantic_gate_called"])
        self.assertTrue(
            by_type["hard_mixed_language_continuation_should_scent"]["semantic_gate_called"]
        )
        self.assertGreaterEqual(
            by_type["hard_cross_project_same_entity_should_scent"]["candidate_count"],
            1,
        )

    def test_synthetic_gate_benchmark_includes_adversarial_case_family(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)
        by_type = {case["case_type"]: case for case in payload["cases"]}

        self.assertEqual(
            by_type["adversarial_explicit_ambiguous_entity_should_scent"]["actual"],
            "scent",
        )
        self.assertEqual(
            by_type["adversarial_explicit_ambiguous_entity_should_scent"]["evidence_count"],
            0,
        )
        self.assertEqual(
            by_type["adversarial_cwd_reversal_current_project_should_scent"]["actual"],
            "scent",
        )
        self.assertEqual(
            by_type["adversarial_cwd_reversal_current_project_should_scent"]["cwd_role"],
            "other_project",
        )
        self.assertEqual(
            by_type["adversarial_mixed_language_explicit_evidence_should_evidence"]["actual"],
            "evidence",
        )
        self.assertGreaterEqual(
            by_type["adversarial_mixed_language_explicit_evidence_should_evidence"][
                "evidence_count"
            ],
            1,
        )

    def test_synthetic_gate_benchmark_includes_100_plus_harder_case_bank(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)
        hard_bank = [
            case
            for case in payload["cases"]
            if str(case["case_type"]).startswith("hard_bank_")
        ]
        family_counts = Counter(str(case["case_type"]).removeprefix("hard_bank_") for case in hard_bank)
        labels = Counter(case["expected"] for case in hard_bank)

        self.assertGreaterEqual(len(hard_bank), 100)
        self.assertGreaterEqual(labels["should_skip"], 30)
        self.assertGreaterEqual(labels["should_scent"], 30)
        self.assertGreaterEqual(labels["should_evidence"], 20)
        for family in {
            "hard_negative_high_overlap",
            "false_cue_code_surface",
            "scent_cross_project_trap",
            "semantic_overevidence_trap",
            "competing_source_evidence",
            "multilingual_paraphrase",
            "budget_timeout_degrade",
            "secret_like_suppression",
        }:
            self.assertGreaterEqual(family_counts[family], 5, family)
        self.assertGreaterEqual(
            sum(1 for case in hard_bank if case["search_budget"] > 0 and case["expected"] == "should_scent"),
            20,
        )
        self.assertGreaterEqual(
            sum(
                1
                for case in hard_bank
                if case["semantic_gate_fixture"] in {"overeager_evidence", "timeout"}
            ),
            15,
        )
        self.assertEqual(payload["harder_case_bank"]["total_cases"], len(hard_bank))
        self.assertGreaterEqual(
            payload["harder_case_bank"]["expected_evidence_source_cases"],
            20,
        )
        self.assertGreaterEqual(
            payload["harder_case_bank"]["semantic_failure_mode_cases"],
            15,
        )
        self.assertTrue(all("prompt" not in case for case in hard_bank))

    def test_synthetic_gate_benchmark_case_bank_has_hard_negative_twins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = benchmark.build_synthetic_fixture(Path(tmp))

        bank = [
            case
            for case in fixture.cases
            if case.case_type.startswith("hard_bank_")
        ]
        twin_groups: dict[str, set[str]] = {}
        prompt_hashes = set()
        for case in bank:
            prompt_hashes.add(benchmark.sha1_text(case.prompt))
            parts = case.case_id.split("__", 2)
            if len(parts) >= 3:
                twin_groups.setdefault(parts[1], set()).add(case.expected)

        self.assertGreaterEqual(len(prompt_hashes), 90)
        self.assertGreaterEqual(
            sum(
                1
                for labels in twin_groups.values()
                if {"should_skip", "should_scent"} <= labels
                or {"should_scent", "should_evidence"} <= labels
            ),
            20,
        )

    def test_scent_no_source_twins_strip_source_request_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = benchmark.build_synthetic_fixture(Path(tmp))

        scent_twins = [
            case.prompt.casefold()
            for case in fixture.cases
            if case.case_id.endswith("__scent_no_source_twin")
        ]

        self.assertTrue(scent_twins)
        self.assertFalse(any("can you cite" in prompt for prompt in scent_twins))
        self.assertFalse(any("那句原话" in prompt for prompt in scent_twins))
        self.assertFalse(any("source-backed evidence" in prompt for prompt in scent_twins))

    def test_multilingual_evidence_twins_include_source_request_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = benchmark.build_synthetic_fixture(Path(tmp))

        evidence_twins = [
            case.prompt.casefold()
            for case in fixture.cases
            if case.case_id.endswith("__evidence_multilingual")
        ]

        self.assertTrue(evidence_twins)
        self.assertTrue(all("source-backed evidence" in prompt for prompt in evidence_twins))

    def test_secret_like_suppression_cases_skip_without_semantic_calls(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)
        secret_cases = [
            case
            for case in payload["cases"]
            if case["case_type"] == "hard_bank_secret_like_suppression"
        ]

        self.assertTrue(secret_cases)
        self.assertEqual(
            [case["case_id"] for case in secret_cases if case["actual"] != "skip"],
            [],
        )
        self.assertEqual(
            [case["case_id"] for case in secret_cases if case["semantic_gate_called"]],
            [],
        )

    def test_synthetic_gate_benchmark_exposes_public_memory_pain_fixtures(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)

        fixture_summary = payload["memory_pain_fixtures"]
        required_families = {
            "write_time_pollution",
            "recalled_context_feedback_loop",
            "fabricated_profile_no_source",
            "transient_task_state",
            "deterministic_vs_fuzzy_memory",
            "metadata_round_trip",
            "large_document_no_foreground_llm",
            "invalid_structured_extraction",
            "compaction_continuity",
        }
        self.assertLessEqual(required_families, set(fixture_summary["families"]))
        self.assertEqual(
            fixture_summary["unsupported_evidence_false_positive_count"],
            0,
        )
        self.assertFalse(fixture_summary["raw_private_text_emitted"])
        self.assertEqual(fixture_summary["live_llm_required"], False)
        self.assertIn("competitor_superiority", payload["cannot_claim"])

        fixture_cases = [
            case
            for case in payload["cases"]
            if case.get("memory_pain_family") in required_families
        ]
        self.assertGreaterEqual(len(fixture_cases), len(required_families))
        self.assertFalse(any("prompt" in case for case in fixture_cases))
        self.assertFalse(any("raw_source" in case for case in fixture_cases))
        for row in fixture_cases:
            self.assertIn("public_sources", row)
            self.assertIn("memory_pain_track", row)
            self.assertIn(
                row["memory_pain_expectation"],
                {"unsupported_not_evidence", "source_backed_or_scent_only"},
            )
        self.assertFalse(
            [
                row["case_id"]
                for row in fixture_cases
                if row["memory_pain_expectation"] == "unsupported_not_evidence"
                and row["actual"] == "evidence"
            ]
        )

    def test_plain_implementation_twins_do_not_use_negative_evidence_as_scent(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)
        plain_tasks = [
            case
            for case in payload["cases"]
            if case["case_type"] == "hard_bank_budget_timeout_degrade"
            and case["case_id"].endswith("__skip_timeout_plain_task")
        ]

        self.assertTrue(plain_tasks)
        self.assertEqual(
            [case["case_id"] for case in plain_tasks if case["actual"] != "skip"],
            [],
        )

    def test_sharegpt_coding_fixture_runs_real_gate_cases_without_leaking_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            corpus.mkdir()
            messages = [
                {
                    "message_id": "m1",
                    "turn_id": "t1",
                    "source_id": "src_demo",
                    "source_line": 1,
                    "role": "user",
                    "phase": "",
                    "turn_index": 1,
                    "is_final": False,
                    "text": "How do I debug a Python list.sort function returning None?",
                    "_meta": {"category": "program and code"},
                },
                {
                    "message_id": "m2",
                    "turn_id": "t1",
                    "source_id": "src_demo",
                    "source_line": 2,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "text": "Use sorted(items, key=...) because list.sort mutates in place and returns None.",
                    "_meta": {"category": "program and code"},
                },
                {
                    "message_id": "m3",
                    "turn_id": "t2",
                    "source_id": "src_demo",
                    "source_line": 3,
                    "role": "user",
                    "phase": "",
                    "turn_index": 2,
                    "is_final": False,
                    "text": "How should I handle missing dictionary keys?",
                    "_meta": {"category": "program and code"},
                },
                {
                    "message_id": "m4",
                    "turn_id": "t2",
                    "source_id": "src_demo",
                    "source_line": 4,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 2,
                    "is_final": True,
                    "text": "Use dict.get(key, default) or raise a KeyError after checking missing keys.",
                    "_meta": {"category": "program and code"},
                },
            ]
            (corpus / "messages.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in messages),
                encoding="utf-8",
            )
            (corpus / "turns.jsonl").write_text(
                json.dumps({"source_id": "src_demo", "turn_count": 2}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                case_set="sharegpt-coding",
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=1,
                include_private_text=False,
            )

        self.assertEqual(payload["config"]["case_set"], "sharegpt-coding")
        self.assertEqual(payload["metrics"]["total_cases"], 5)
        self.assertIn("sharegpt_coding_public_real", payload["config"]["case_source"])
        self.assertEqual(
            payload["metrics"]["case_types"],
            {
                "sharegpt_coding_should_skip": 1,
                "sharegpt_coding_semantic_required_control_should_skip": 1,
                "sharegpt_coding_semantic_positive_zh_should_scent": 1,
                "sharegpt_coding_semantic_positive_en_should_scent": 1,
                "sharegpt_coding_should_evidence": 1,
            },
        )
        semantic_positive = [
            case
            for case in payload["cases"]
            if case["case_type"].startswith("sharegpt_coding_semantic_positive_")
        ]
        self.assertEqual(len(semantic_positive), 2)
        self.assertTrue(all(case["use_semantic_gate"] for case in semantic_positive))
        self.assertTrue(
            all(case["semantic_gate_fixture"] == "positive_scent" for case in semantic_positive)
        )
        self.assertEqual(payload["privacy_boundary"]["raw_prompt_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["case_ids_are_hashed"], True)
        for case in payload["cases"]:
            self.assertNotIn("prompt", case)
            self.assertTrue(str(case["case_id"]).startswith("sharegpt:"))
            self.assertIn(case["expected"], benchmark.EXPECTED_LABELS)
            self.assertIn(case["actual"], benchmark.ACTUAL_DECISIONS)


if __name__ == "__main__":
    unittest.main()
