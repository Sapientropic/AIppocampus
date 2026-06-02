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
        self.assertEqual(metrics["rate_estimates"]["accuracy"]["numerator"], 1)
        self.assertEqual(metrics["rate_estimates"]["accuracy"]["denominator"], 4)
        self.assertEqual(
            metrics["rate_estimates"]["evidence_recall"]["confidence_interval"]["method"],
            "wilson_score",
        )

    def test_synthetic_gate_benchmark_is_sanitized_and_measures_current_behavior(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)

        self.assertEqual(payload["kind"], "aippocampus_memory_decision_gate_benchmark")
        self.assertGreaterEqual(payload["metrics"]["total_cases"], 5)
        self.assertIn("macro_f1", payload["metrics"])
        self.assertIn("rate_estimates", payload["metrics"])
        self.assertIn("scent_or_evidence_recall", payload["metrics"]["rate_estimates"])
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

    def test_source_free_twins_are_explicit_fixture_contracts(self) -> None:
        twins = benchmark.source_free_scent_twin_fixtures()

        self.assertGreaterEqual(len(twins), 8)
        self.assertTrue(all(twin.expected_support_level == "scent" for twin in twins))
        for twin in twins:
            twin.validate()
            self.assertTrue(twin.required_topic_terms, twin.twin)
            self.assertTrue(
                any(term in twin.scent_prompt for term in twin.required_topic_terms),
                twin.twin,
            )
            self.assertNotEqual(
                benchmark.source_free_scent_twin_prompt(twin.evidence_prompt),
                twin.scent_prompt,
                twin.twin,
            )

    def test_alias_ablated_trigger_fixture_removes_exact_seed_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry" / "threads.json"
            registry_path.parent.mkdir(parents=True)

            benchmark.write_synthetic_reviewed_semantic_triggers(
                registry_path,
                alias_mode="ablated",
            )

            trigger_rows = [
                json.loads(line)
                for line in (registry_path.parent / "semantic_triggers.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]

        aliases = {
            str(alias).casefold()
            for row in trigger_rows
            for alias in row.get("aliases", [])
        }
        activation_surface = "\n".join(
            str(value)
            for row in trigger_rows
            for value in [row.get("title"), row.get("when_to_use"), *(row.get("aliases", []))]
        ).casefold()
        self.assertTrue(benchmark.EXACT_ALIAS_ABLATION_TERMS)
        self.assertFalse(
            aliases & {term.casefold() for term in benchmark.EXACT_ALIAS_ABLATION_TERMS}
        )
        self.assertFalse(
            [
                term
                for term in benchmark.EXACT_ALIAS_ABLATION_TERMS
                if term.casefold() in activation_surface
            ]
        )

    def test_alias_ablation_controls_avoid_exact_prompt_aliases(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)

        controls = payload["semantic_trigger_alias_ablation"]
        control_cases = [
            case
            for case in payload["cases"]
            if case["case_type"] == "hard_bank_alias_ablation"
        ]

        self.assertGreaterEqual(controls["case_count"], 4)
        self.assertEqual(controls["case_count"], len(control_cases))
        self.assertEqual(controls["correct_count"], controls["case_count"])
        self.assertEqual(controls["exact_prompt_alias_violation_count"], 0)
        self.assertGreaterEqual(controls["semantic_gate_fixture_cases"], 3)
        self.assertEqual(
            set(controls["removed_exact_aliases"]),
            set(benchmark.EXACT_ALIAS_ABLATION_TERMS),
        )
        self.assertTrue(all("prompt" not in case for case in control_cases))

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

    def test_summarize_results_counts_evidence_false_negatives(self) -> None:
        results = [
            {"expected": "should_evidence", "actual": "skip", "case_type": "natural_oral"},
            {"expected": "should_evidence", "actual": "scent", "case_type": "natural_oral"},
            {"expected": "should_scent", "actual": "skip", "case_type": "weak_deictic"},
            {"expected": "should_skip", "actual": "evidence", "case_type": "ordinary_code"},
        ]

        metrics = benchmark.summarize_results(results)

        self.assertEqual(metrics["evidence_false_negative_count"], 2)
        self.assertEqual(metrics["surface_false_negative_count"], 2)
        self.assertEqual(metrics["evidence_false_negative_rate"], 0.5)

    def test_expected_source_mismatch_counts_as_incorrect(self) -> None:
        case = benchmark.GateCase(
            case_id="source_mismatch",
            case_type="source_quality",
            expected="should_evidence",
            prompt="找回那句原话",
            search_budget=1,
            expected_evidence_thread_key="session:expected",
        )

        row = benchmark.grade_case(
            case,
            {
                "decision": "evidence",
                "evidence": [{"thread_key": "session:wrong", "line": 12}],
            },
            semantic_gate_called=False,
        )
        metrics = benchmark.summarize_results([row])

        self.assertFalse(row["correct"])
        self.assertTrue(row["evidence_source_mismatch"])
        self.assertEqual(metrics["evidence_source_mismatch_count"], 1)

    def test_mixed_wrong_source_evidence_counts_as_incorrect(self) -> None:
        case = benchmark.GateCase(
            case_id="mixed_source_mismatch",
            case_type="source_quality",
            expected="should_evidence",
            prompt="找回那句原话",
            search_budget=2,
            expected_evidence_thread_key="session:expected",
        )

        row = benchmark.grade_case(
            case,
            {
                "decision": "evidence",
                "evidence": [
                    {"thread_key": "session:expected", "line": 12},
                    {"thread_key": "session:wrong", "line": 34},
                ],
            },
            semantic_gate_called=False,
        )
        metrics = benchmark.summarize_results([row])

        self.assertFalse(row["correct"])
        self.assertFalse(row["evidence_source_match"])
        self.assertTrue(row["evidence_source_mismatch"])
        self.assertEqual(row["unexpected_evidence_source_count"], 1)
        self.assertEqual(metrics["evidence_source_mismatch_count"], 1)

    def test_synthetic_gate_benchmark_includes_natural_oral_case_bank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = benchmark.build_synthetic_fixture(Path(tmp))

        natural_cases = [
            case
            for case in fixture.cases
            if case.case_type == "hard_bank_natural_oral_prompt"
        ]
        labels = Counter(case.expected for case in natural_cases)

        self.assertGreaterEqual(len(natural_cases), 30)
        self.assertGreaterEqual(labels["should_skip"], 8)
        self.assertGreaterEqual(labels["should_scent"], 8)
        self.assertGreaterEqual(labels["should_evidence"], 10)
        self.assertTrue(
            any("上次那个 bug 怎么说" in case.prompt for case in natural_cases)
        )
        self.assertTrue(
            any(
                case.expected == "should_evidence"
                and "source-backed evidence" not in case.prompt.casefold()
                and "原话" not in case.prompt
                for case in natural_cases
            )
        )

        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)

        self.assertGreaterEqual(payload["harder_case_bank"]["natural_oral_prompt_cases"], 30)
        self.assertGreaterEqual(
            payload["harder_case_bank"]["natural_oral_expected_evidence_cases"],
            10,
        )
        self.assertEqual(
            payload["harder_case_bank"]["natural_oral_evidence_false_negative_count"],
            0,
        )
        self.assertEqual(
            payload["harder_case_bank"]["expected_evidence_source_match_count"],
            payload["harder_case_bank"]["expected_evidence_source_cases"],
        )
        self.assertEqual(payload["metrics"]["evidence_source_mismatch_count"], 0)
        self.assertTrue(payload["ok"])

    def test_synthetic_gate_benchmark_declares_fixture_live_boundary(self) -> None:
        payload = benchmark.run_benchmark(case_set="synthetic", include_private_text=False)

        boundary = payload["semantic_gate_boundary"]

        self.assertEqual(boundary["mode"], "deterministic_fixture")
        self.assertFalse(boundary["live_llm_required"])
        self.assertEqual(
            set(boundary["fixture_decisions"]),
            {
                "positive_scent",
                "overeager_evidence",
                "timeout",
                "paraphrase_scent",
                "paraphrase_evidence",
                "paraphrase_project_scent",
                "paraphrase_project_evidence",
            },
        )
        self.assertIn("benchmark_live_semantic_gate.py", boundary["live_track"])
        self.assertIn("live_semantic_model_quality", payload["cannot_claim"])

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

    def test_sharegpt_coding_sampling_is_seeded_and_reports_population(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            corpus.mkdir()
            rows = []
            for conv_index in range(6):
                source_id = f"src_demo_{conv_index}"
                rows.extend(
                    [
                        {
                            "message_id": f"{source_id}_m1",
                            "turn_id": f"{source_id}_t1",
                            "source_id": source_id,
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": f"How do I debug Rust async parser issue {conv_index}?",
                            "_meta": {
                                "source_file": "sharegpt-sample.jsonl",
                                "category": "program and code",
                            },
                        },
                        {
                            "message_id": f"{source_id}_m2",
                            "turn_id": f"{source_id}_t1",
                            "source_id": source_id,
                            "source_line": 2,
                            "role": "assistant",
                            "phase": "final_answer",
                            "turn_index": 1,
                            "is_final": True,
                            "text": f"Use owned parser buffers and explicit lifetimes {conv_index}.",
                            "_meta": {
                                "source_file": "sharegpt-sample.jsonl",
                                "category": "program and code",
                            },
                        },
                        {
                            "message_id": f"{source_id}_m3",
                            "turn_id": f"{source_id}_t2",
                            "source_id": source_id,
                            "source_line": 3,
                            "role": "user",
                            "turn_index": 2,
                            "text": f"Continue the parser explanation {conv_index}.",
                            "_meta": {
                                "source_file": "sharegpt-sample.jsonl",
                                "category": "program and code",
                            },
                        },
                        {
                            "message_id": f"{source_id}_m4",
                            "turn_id": f"{source_id}_t2",
                            "source_id": source_id,
                            "source_line": 4,
                            "role": "assistant",
                            "phase": "final_answer",
                            "turn_index": 2,
                            "is_final": True,
                            "text": f"Return owned tokens from the parser task {conv_index}.",
                            "_meta": {
                                "source_file": "sharegpt-sample.jsonl",
                                "category": "program and code",
                            },
                        },
                    ]
                )
            (corpus / "messages.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            first = benchmark.run_benchmark(
                case_set="sharegpt-coding",
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=2,
                sharegpt_seed=218,
            )
            repeated = benchmark.run_benchmark(
                case_set="sharegpt-coding",
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=2,
                sharegpt_seed=218,
            )
            different_seed = benchmark.run_benchmark(
                case_set="sharegpt-coding",
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=2,
                sharegpt_seed=219,
            )

        sampling = first["sharegpt_sampling"]
        self.assertEqual(sampling["method"], "seeded_stratified")
        self.assertEqual(sampling["seed"], 218)
        self.assertTrue(sampling["population_scan_complete"])
        self.assertEqual(sampling["eligible_population_count"], 6)
        self.assertEqual(sampling["selected_conversation_count"], 2)
        self.assertEqual(len(sampling["selected_conversation_ids"]), 2)
        self.assertEqual(
            sampling["selected_conversation_ids"],
            repeated["sharegpt_sampling"]["selected_conversation_ids"],
        )
        self.assertNotEqual(
            sampling["selected_conversation_ids"],
            different_seed["sharegpt_sampling"]["selected_conversation_ids"],
        )
        self.assertEqual(sampling["strata"][0]["eligible_conversations"], 6)
        self.assertEqual(sampling["strata"][0]["selected_conversations"], 2)
        dumped = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("Rust async parser issue", dumped)
        self.assertNotIn("sharegpt-sample.jsonl", dumped)

    def test_sharegpt_coding_first_n_is_explicit_smoke_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            corpus.mkdir()
            rows = []
            for conv_index in range(3):
                source_id = f"src_first_{conv_index}"
                rows.extend(
                    [
                        {
                            "message_id": f"{source_id}_m1",
                            "turn_id": f"{source_id}_t1",
                            "source_id": source_id,
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": f"How do I debug TypeScript issue {conv_index}?",
                        },
                        {
                            "message_id": f"{source_id}_m2",
                            "turn_id": f"{source_id}_t1",
                            "source_id": source_id,
                            "source_line": 2,
                            "role": "assistant",
                            "phase": "final_answer",
                            "turn_index": 1,
                            "is_final": True,
                            "text": f"Use a discriminated union {conv_index}.",
                        },
                        {
                            "message_id": f"{source_id}_m3",
                            "turn_id": f"{source_id}_t2",
                            "source_id": source_id,
                            "source_line": 3,
                            "role": "user",
                            "turn_index": 2,
                            "text": f"Continue TypeScript issue {conv_index}.",
                        },
                        {
                            "message_id": f"{source_id}_m4",
                            "turn_id": f"{source_id}_t2",
                            "source_id": source_id,
                            "source_line": 4,
                            "role": "assistant",
                            "phase": "final_answer",
                            "turn_index": 2,
                            "is_final": True,
                            "text": f"Keep exhaustive checks {conv_index}.",
                        },
                    ]
                )
            (corpus / "messages.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            payload = benchmark.run_benchmark(
                case_set="sharegpt-coding",
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=1,
                sharegpt_sampling_mode="first-n",
            )

        sampling = payload["sharegpt_sampling"]
        self.assertEqual(sampling["method"], "first_n")
        self.assertFalse(sampling["population_scan_complete"])
        self.assertIn("seeded_stratified_population_sampling", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
