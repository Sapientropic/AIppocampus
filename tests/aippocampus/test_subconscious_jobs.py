from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
JOBS_RUNNER = SCRIPTS / "aippocampus_runtime" / "subconscious" / "jobs.py"
sys.path.insert(0, str(TESTS))
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import build_concept_graph as concept_graph  # noqa: E402
import build_semantic_scope_labels as semantic_scope_materializer  # noqa: E402
import subconscious_jobs as jobs  # noqa: E402
from aippocampus_runtime.subconscious import job_storage  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_PASSWORD_VALUE,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


class SubconsciousJobsTests(unittest.TestCase):
    def test_job_storage_writes_sanitized_private_staging_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "subconscious_jobs.jsonl"
            local_path = fake_test_windows_path("subconscious-job-secret.txt")

            job_storage.append_job_findings(
                output,
                [
                    {
                        "kind": "question_candidate",
                        "title": f"Bearer {FAKE_TEST_BEARER_TOKEN}",
                        "summary": f"review {local_path}",
                        "source_refs": [{"thread_key": "thread:one", "line": 12}],
                    }
                ],
                model="deepseek-test",
                batch_id="batch-one",
                usage={"prompt_tokens": 11},
                model_route={
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.example/v1",
                    "api_key_env": "DEEPSEEK_API_KEY",
                },
            )

            raw = output.read_text(encoding="utf-8")
            event = json.loads(raw)

            self.assertEqual(event["source_refs"], [{"thread_key": "thread:one", "line": 12}])
            self.assertEqual(event["model_route"], {"provider": "deepseek"})
            self.assertNotIn("base_url", event["model_route"])
            self.assertNotIn("api_key_env", event["model_route"])
            self.assertNotIn(FAKE_TEST_BEARER_TOKEN, raw)
            self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, raw)
            self.assertIn("<redacted:bearer-token>", raw)
            self.assertIn("<redacted:local-path>", raw)

    def test_job_circuit_catalog_is_separate_from_runner(self) -> None:
        circuits = importlib.import_module("subconscious_job_circuits")
        runner_source = JOBS_RUNNER.read_text(encoding="utf-8")

        self.assertNotIn("JOB_SPECS: dict", runner_source)
        self.assertEqual(jobs.JOB_SPECS, circuits.JOB_SPECS)
        self.assertEqual(jobs.job_names("all"), circuits.job_names("all"))
        self.assertEqual(
            json.loads(jobs.jobs_initial_payload("concept_edges", "objective", [], 2, 1)),
            json.loads(circuits.jobs_initial_payload("concept_edges", "objective", [], 2, 1)),
        )

    def test_job_sample_plan_is_separate_from_runner(self) -> None:
        plan = importlib.import_module("subconscious_job_plan")
        runner_source = JOBS_RUNNER.read_text(encoding="utf-8")

        tasks = plan.plan_job_run_tasks(["project_drift", "trigger_mining"], samples_per_job=2)

        self.assertEqual(
            [(task.index, task.job, task.sample_index, task.sample_count) for task in tasks],
            [
                (0, "project_drift", 1, 2),
                (1, "project_drift", 2, 2),
                (2, "trigger_mining", 1, 2),
                (3, "trigger_mining", 2, 2),
            ],
        )
        self.assertEqual(plan.worker_count(concurrency=99, task_count=len(tasks)), 4)
        self.assertNotIn("for sample_index in range", runner_source)

    def test_jobs_run_config_factory_derives_default_paths_from_registry_dir(self) -> None:
        config_module = importlib.import_module("subconscious_jobs_config")
        runner_source = JOBS_RUNNER.read_text(encoding="utf-8")

        self.assertIs(jobs.JobsRunConfig, config_module.JobsRunConfig)
        self.assertIs(jobs.jobs_run_config_from_args, config_module.jobs_run_config_from_args)
        self.assertIs(jobs.default_jobs_output_path, config_module.default_jobs_output_path)
        self.assertNotIn("class JobsRunConfig", runner_source)
        self.assertNotIn("def jobs_run_config_from_args", runner_source)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            class Args:
                registry = None
                registry_dir = str(root)
                timeline = None
                concept_graph = None
                jobs_output = None
                edges_output = None
                job = "concept_edges"
                project = "AIppocampus"
                objective = "test"
                max_turns = 4
                max_steps = 2
                min_tool_steps = 1
                model = "deepseek-v4-flash"
                base_url = "https://example.invalid"
                api_key_env = "MISSING_TEST_KEY"
                max_tokens = None
                timeout = 9
                temperature = 0.2
                concurrency = 3
                samples_per_job = 2
                dry_run = True
                no_write = False

            config = jobs.jobs_run_config_from_args(Args())

        self.assertEqual(config.registry_path, (root / "threads.json").resolve())
        self.assertEqual(config.timeline_path, (root / "project_timeline.json").resolve())
        self.assertEqual(config.jobs_output_path, (root / "subconscious_jobs.jsonl").resolve())
        self.assertEqual(config.edges_output_path, (root / "subconscious_edges.jsonl").resolve())
        self.assertEqual(config.jobs, ["concept_edges"])
        self.assertEqual(config.api_key, None)
        self.assertTrue(config.dry_run)

    def test_job_validation_is_separate_from_runner(self) -> None:
        validation = importlib.import_module("subconscious_job_validation")
        validation_audit = importlib.import_module("subconscious_validation_audit")
        runner_source = JOBS_RUNNER.read_text(encoding="utf-8")

        self.assertIs(jobs.validate_findings, validation.validate_findings)
        self.assertIs(jobs.validation_audit, validation_audit.validation_audit)
        self.assertEqual(jobs.QUESTION_TEXT_MAX_CHARS, validation.QUESTION_TEXT_MAX_CHARS)
        self.assertNotIn("def validate_findings", runner_source)
        self.assertNotIn("def validation_audit", runner_source)
        self.assertNotIn("def estimate_finding_quality", runner_source)

    def test_jobs_initial_payload_keeps_static_contract_before_turns_and_variable_objective_after_turns(
        self,
    ) -> None:
        payload = json.loads(
            jobs.jobs_initial_payload(
                "concept_edges",
                "Use a distinct sample angle.",
                [{"turn_ref": "t0", "user": "A", "assistant": "B"}],
                max_steps=4,
                min_tool_steps=1,
            )
        )
        keys = list(payload.keys())

        self.assertLess(keys.index("job"), keys.index("initial_turns"))
        self.assertLess(keys.index("job_spec"), keys.index("initial_turns"))
        self.assertLess(keys.index("final_schema"), keys.index("initial_turns"))
        self.assertLess(keys.index("available_tools"), keys.index("initial_turns"))
        self.assertLess(keys.index("tool_budget"), keys.index("initial_turns"))
        self.assertLess(keys.index("initial_turns"), keys.index("objective"))

    def test_initial_payload_redacts_external_model_sensitive_text(self) -> None:
        payload = jobs.jobs_initial_payload(
            "project_drift",
            "review memory routing",
            [
                {
                    "turn_ref": "t0",
                    "user": f"帮我看 password={FAKE_TEST_PASSWORD_VALUE} 和 {fake_test_windows_path('jobs.txt')}",
                    "assistant": f"Bearer {FAKE_TEST_BEARER_TOKEN}",
                }
            ],
            max_steps=1,
            min_tool_steps=0,
        )

        self.assertNotIn(FAKE_TEST_PASSWORD_VALUE, payload)
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, payload)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, payload)
        self.assertIn("<redacted:secret>", payload)
        self.assertIn("<redacted:local-path>", payload)

    def test_validate_findings_accepts_string_refs(self) -> None:
        parsed = {
            "findings": [
                {
                    "kind": "project_drift",
                    "title": "Runtime drift",
                    "summary": "T-Sense shifted from scanner script toward desktop runtime work.",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                    "concepts": ["T-Sense", "Go runtime"],
                }
            ]
        }
        source_bank = {
            "t0": {
                "turn_ref": "t0",
                "thread_key": "session:one",
                "title": "T-Sense",
                "turn_index": 40,
                "assistant_line": 1202,
            }
        }

        findings = jobs.validate_findings("project_drift", parsed, source_bank)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["source_refs"][0]["ref"], "t0")
        self.assertEqual(findings[0]["concepts"], ["T-Sense", "Go runtime"])

    def test_validation_audit_reports_drop_reasons_without_raw_text(self) -> None:
        parsed = {
            "findings": [
                {
                    "kind": "project_drift",
                    "title": "Missing confidence",
                    "summary": "Would be useful but has no confidence.",
                    "source_refs": ["t0"],
                },
                {
                    "kind": "project_drift",
                    "title": "Missing ref",
                    "summary": "Would be useful but points nowhere.",
                    "confidence": 0.86,
                    "source_refs": ["missing"],
                },
                {
                    "kind": "project_drift",
                    "title": "Missing summary",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                },
                {
                    "kind": "project_drift",
                    "title": "Accepted",
                    "summary": "A source-backed project drift finding survives.",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                },
            ]
        }
        source_bank = {
            "t0": {
                "turn_ref": "t0",
                "thread_key": "session:one",
                "title": "T-Sense",
                "turn_index": 40,
                "assistant_line": 1202,
            }
        }

        audit = jobs.validation_audit("project_drift", parsed, source_bank)

        self.assertEqual(audit["raw_finding_count"], 4)
        self.assertEqual(audit["accepted_count"], 1)
        self.assertEqual(
            audit["rejection_reasons"],
            {
                "missing_or_low_confidence": 1,
                "missing_or_unresolved_source_refs": 1,
                "missing_summary": 1,
            },
        )
        self.assertNotIn("Would be useful", json.dumps(audit, ensure_ascii=False))

    def test_cognitive_map_job_preserves_route_fields(self) -> None:
        parsed = {
            "findings": [
                {
                    "kind": "cognitive_map_route",
                    "title": "AIppocampus mental map",
                    "summary": "The hippocampus metaphor should become a navigable mental map, not only a keyword index.",
                    "confidence": 0.88,
                    "source_refs": ["t0"],
                    "landmarks": ["AIppocampus", "认知地图", "心理地图"],
                    "regions": ["memory architecture"],
                    "route_cues": ["海马体空间定位", "位置细胞", "网格细胞"],
                    "target_thread_keys": ["session:map"],
                    "negative_cues": ["ordinary coding task"],
                    "route_kind": "preplay",
                }
            ]
        }
        source_bank = {
            "t0": {
                "turn_ref": "t0",
                "thread_key": "session:map",
                "title": "AIppocampus",
                "project_label": "AIppocampus",
                "turn_index": 9,
                "assistant_line": 88,
            }
        }

        findings = jobs.validate_findings("cognitive_map", parsed, source_bank)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["route_kind"], "preplay")
        self.assertIn("心理地图", findings[0]["landmarks"])
        self.assertIn("位置细胞", findings[0]["route_cues"])
        self.assertEqual(findings[0]["target_thread_keys"], ["session:map"])

    def test_question_extraction_preserves_question_and_frontier_fields(self) -> None:
        parsed = {
            "findings": [
                {
                    "kind": "question_candidate",
                    "title": "Global memory placement",
                    "summary": "The user asked whether AIppocampus should be global instead of project-local.",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                    "question_text": "Should AIppocampus generated memory live under CodexHome globally?",
                    "intent_orientation": "architecture_decision",
                    "what_features": ["storage", "cross-project recall"],
                    "where_context": ["AIppocampus thread"],
                    "phase_context": "new-project startup",
                    "collaboration_context": ["Codex"],
                    "scope_labels": ["preference"],
                },
                {
                    "kind": "frontier_marker",
                    "title": "Ranking noise after full import",
                    "summary": "After full import, injected skill text could outrank real project evidence.",
                    "confidence": 0.84,
                    "source_refs": ["t0"],
                    "frontier_type": "scope_boundary",
                    "boundary_reason": "Search ranking treated injected instruction blocks as normal source evidence.",
                    "linked_question_short": "global memory placement",
                    "semantic_scope_labels": ["relationship_continuity"],
                },
            ]
        }
        source_bank = {
            "t0": {
                "turn_ref": "t0",
                "thread_key": "session:map",
                "title": "AIppocampus",
                "project_label": "AIppocampus",
                "turn_index": 4,
                "assistant_line": 88,
                "scope_labels": ["personal_reflection", "idea_seed", "open_question"],
                "semantic_scope_labels": ["personal_reflection", "idea_seed"],
            }
        }

        findings = jobs.validate_findings("question_extraction", parsed, source_bank)

        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0]["kind"], "question_candidate")
        self.assertEqual(findings[0]["intent_orientation"], "architecture_decision")
        self.assertIn("cross-project recall", findings[0]["what_features"])
        self.assertEqual(
            findings[0]["scope_labels"],
            ["personal_reflection", "idea_seed", "open_question"],
        )
        self.assertEqual(
            findings[0]["semantic_scope_labels"],
            ["personal_reflection", "idea_seed"],
        )
        self.assertNotIn("preference", findings[0]["scope_labels"])
        self.assertEqual(findings[1]["kind"], "frontier_marker")
        self.assertEqual(findings[1]["frontier_type"], "scope_boundary")
        self.assertIn("injected instruction", findings[1]["boundary_reason"])
        self.assertEqual(
            findings[1]["scope_labels"],
            ["personal_reflection", "idea_seed", "open_question"],
        )
        self.assertNotIn("relationship_continuity", findings[1]["scope_labels"])
        self.assertEqual(findings[1]["where_context"], ["AIppocampus"])

    def test_question_extraction_payload_marks_axes_expected(self) -> None:
        payload = json.loads(
            jobs.jobs_initial_payload(
                "question_extraction",
                "extract questions",
                [],
                max_steps=4,
                min_tool_steps=1,
            )
        )

        contract = payload["job_field_contract"]["question_candidate"]
        self.assertIn("what_features", contract["expected_unless_unavailable"])
        self.assertIn("where_context", contract["expected_unless_unavailable"])
        self.assertIn("phase_context", contract["expected_unless_unavailable"])
        self.assertIn("generic filler", payload["job_field_contract"]["quality_gate"])
        frontier_contract = payload["job_field_contract"]["frontier_marker"]
        self.assertIn("recommendation", frontier_contract["expected_unless_unavailable"])
        schema = payload["final_schema"]["findings"][0]
        self.assertIn("expected", schema["what_features"])
        self.assertIn("expected", schema["where_context"])

    def test_question_extraction_diagnostics_split_frontier_recommendations(self) -> None:
        diagnostics_module = importlib.import_module("subconscious_question_diagnostics")
        findings = [
            {
                "kind": "question_candidate",
                "question_text": "How should question extraction expose frontiers?",
                "question_short": "frontier recommendations",
                "intent_orientation": "architecture",
                "what_features": ["frontier markers"],
                "where_context": ["AIppocampus"],
                "phase_context": "source_review",
                "recommendation": "Feed question_tracking.",
            },
            {
                "kind": "frontier_marker",
                "frontier_type": "blocked",
                "where_context": ["AIppocampus"],
                "phase_context": "source_review",
            },
            {
                "kind": "frontier_marker",
                "frontier_type": "needs_external_evidence",
                "where_context": ["AIppocampus"],
                "phase_context": "source_review",
            },
        ]

        diagnostics = diagnostics_module.question_extraction_quality_diagnostics(
            [{"action": "final", "findings": findings}],
            findings,
        )
        presence = diagnostics["question_extraction_field_presence"]["validated"]

        self.assertEqual(presence["recommendation"]["count"], 1)
        self.assertEqual(
            presence["recommendation_by_kind"]["question_candidate"],
            {"count": 1, "rate": 1.0},
        )
        self.assertEqual(
            presence["recommendation_by_kind"]["frontier_marker"],
            {"count": 0, "rate": 0.0},
        )
        self.assertIn(
            "question_extraction_missing_frontier_recommendations",
            [warning["code"] for warning in diagnostics["warnings"]],
        )
        self.assertTrue(diagnostics_module.should_request_question_axis_repair(diagnostics))

    def test_question_extraction_repairs_raw_frontiers_dropped_by_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:frontier",
                                        "title": "Frontier map",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "assistant_line": 10,
                                        "user": "We need external evidence before claiming this is solved.",
                                        "assistant": "Treat it as a frontier marker.",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            call_count = 0

            def frontier(index: int, *, with_confidence: bool) -> dict[str, Any]:
                row: dict[str, Any] = {
                    "kind": "frontier_marker",
                    "title": f"External evidence frontier {index}",
                    "summary": "The user says external evidence is needed before a claim is solved.",
                    "source_refs": ["t0"],
                    "frontier_type": "needs_external_evidence",
                    "boundary_reason": "The source requires external evidence before closing the claim.",
                    "where_context": ["AIppocampus"],
                    "phase_context": "source_review",
                    "recommendation": "Keep as frontier until source review or external evidence is available.",
                }
                if with_confidence:
                    row["confidence"] = 0.86
                return row

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                nonlocal call_count
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                call_count += 1
                content = {
                    "action": "final",
                    "findings": [
                        frontier(index, with_confidence=call_count >= 2)
                        for index in range(2)
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["question_extraction"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="extract external evidence frontiers",
                max_turns=4,
                max_steps=3,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=1,
                samples_per_job=1,
                chat_fn=fake_chat,
                no_write=True,
            )

        job = result["jobs"][0]
        retention = job["quality_diagnostics"]["accepted_final_to_validated_retention"][
            "frontier_marker"
        ]
        required_presence = job["quality_diagnostics"]["raw_required_field_presence"]

        self.assertTrue(result["ok"], result)
        self.assertEqual(call_count, 2)
        self.assertEqual(job["finding_count"], 2)
        self.assertEqual(retention["validated_count"], 2)
        self.assertEqual(required_presence["frontier_marker"]["confidence"]["rate"], 0.5)
        self.assertEqual(
            job["validation_diagnostics"]["final_attempts"][0]["rejection_reasons"],
            {"missing_or_low_confidence": 2},
        )
        self.assertEqual(job["validation_diagnostics"]["accepted_final"]["accepted_count"], 2)
        self.assertEqual(
            job["quality_diagnostics"]["question_extraction_field_presence"]["validated"][
                "recommendation_by_kind"
            ]["frontier_marker"]["rate"],
            1.0,
        )

    def test_question_extraction_repairs_partial_final_with_dropped_frontiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:partial-frontier",
                                        "title": "Partial frontier",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "assistant_line": 10,
                                        "user": "How do we notice unresolved external-evidence gaps?",
                                        "assistant": "Track them as frontier markers.",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            call_count = 0

            def question() -> dict[str, Any]:
                return {
                    "kind": "question_candidate",
                    "title": "Unresolved evidence gaps",
                    "summary": "The user asks how unresolved evidence gaps are noticed.",
                    "confidence": 0.88,
                    "source_refs": ["t0"],
                    "question_text": "How do we notice unresolved external-evidence gaps?",
                    "question_short": "notice evidence gaps",
                    "intent_orientation": "architecture",
                    "what_features": ["frontier markers", "external evidence"],
                    "where_context": ["AIppocampus"],
                    "phase_context": "architecture_review",
                    "recommendation": "Feed question tracking and frontier review.",
                }

            def frontier(index: int, *, with_confidence: bool) -> dict[str, Any]:
                row: dict[str, Any] = {
                    "kind": "frontier_marker",
                    "title": f"Evidence gap frontier {index}",
                    "summary": "The source marks an unresolved evidence gap.",
                    "source_refs": ["t0"],
                    "frontier_type": "needs_external_evidence",
                    "boundary_reason": "The source says evidence is still needed.",
                    "where_context": ["AIppocampus"],
                    "phase_context": "architecture_review",
                    "recommendation": "Keep as frontier until evidence is available.",
                }
                if with_confidence:
                    row["confidence"] = 0.86
                return row

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                nonlocal call_count
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                call_count += 1
                content = {
                    "action": "final",
                    "findings": [
                        question(),
                        frontier(0, with_confidence=call_count >= 2),
                        frontier(1, with_confidence=call_count >= 2),
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["question_extraction"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="extract partial frontier final",
                max_turns=4,
                max_steps=3,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=1,
                samples_per_job=1,
                chat_fn=fake_chat,
                no_write=True,
            )

        job = result["jobs"][0]
        retention = job["quality_diagnostics"]["accepted_final_to_validated_retention"]
        all_attempt_required = job["quality_diagnostics"][
            "raw_required_field_presence_all_attempts"
        ]
        accepted_required = job["quality_diagnostics"][
            "accepted_final_required_field_presence"
        ]

        self.assertTrue(result["ok"], result)
        self.assertEqual(call_count, 2)
        self.assertEqual(job["finding_count"], 3)
        self.assertEqual(retention["frontier_marker"]["validated_count"], 2)
        self.assertEqual(all_attempt_required["frontier_marker"]["confidence"]["rate"], 0.5)
        self.assertEqual(accepted_required["frontier_marker"]["confidence"]["rate"], 1.0)

    def test_question_extraction_repairs_sparse_axis_final_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "Question map",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "assistant_line": 10,
                                        "user": "How do we keep question tracking semantic instead of lexical?",
                                        "assistant": "Use source-backed axes.",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            call_count = 0

            def candidate(index: int, *, rich: bool) -> dict[str, Any]:
                row: dict[str, Any] = {
                    "kind": "question_candidate",
                    "title": f"Question map {index}",
                    "summary": "The user asks how question tracking can stay semantic.",
                    "confidence": 0.88,
                    "source_refs": ["t0"],
                    "question_text": f"How can question tracking stay semantic {index}?",
                    "question_short": f"semantic question tracking {index}",
                    "intent_orientation": "architecture",
                }
                if rich:
                    row.update(
                        {
                            "what_features": ["question tracking", "semantic axes"],
                            "where_context": ["AIppocampus"],
                            "phase_context": "architecture_review",
                            "recommendation": "Feed question_tracking with axis-rich candidates.",
                        }
                    )
                return row

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                nonlocal call_count
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                call_count += 1
                rich = call_count >= 2
                content = {
                    "action": "final",
                    "findings": [candidate(index, rich=rich) for index in range(4)],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["question_extraction"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="extract semantic question axes",
                max_turns=4,
                max_steps=3,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=1,
                samples_per_job=1,
                chat_fn=fake_chat,
                no_write=True,
            )

        job = result["jobs"][0]
        diagnostics = job["quality_diagnostics"]["question_extraction_field_presence"]

        self.assertTrue(result["ok"], result)
        self.assertEqual(call_count, 2)
        self.assertEqual(len(job["final_attempts"]), 2)
        self.assertEqual(job["finding_count"], 4)
        self.assertEqual(diagnostics["validated"]["complete_core_axes"]["rate"], 1.0)
        self.assertEqual(
            diagnostics["validated"]["recommendation_by_kind"]["question_candidate"]["rate"],
            1.0,
        )
        self.assertEqual(
            diagnostics["validated"]["recommendation_by_kind"]["frontier_marker"]["rate"],
            0.0,
        )
        self.assertEqual(result["quality_diagnostics"][0], job["quality_diagnostics"])

    def test_run_jobs_runs_question_tracking_after_extraction_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "assistant_line": 10,
                                        "user": "Codex compaction 后怎么保持上下文？",
                                        "assistant": "用 source-backed continuity。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "question_candidate",
                            "title": "Agent context continuity",
                            "summary": "The user asks how agent context survives compaction.",
                            "confidence": 0.88,
                            "source_refs": ["t0"],
                            "question_text": "How do I keep agent context across compaction?",
                            "question_short": "agent context continuity",
                            "intent_orientation": "implementation",
                            "what_features": ["agent memory", "context continuity", "compaction"],
                            "where_context": ["AIppocampus"],
                            "phase_context": "post_compaction",
                        },
                        {
                            "kind": "question_candidate",
                            "title": "Codex context loss",
                            "summary": "The user asks why Codex loses context after compaction.",
                            "confidence": 0.88,
                            "source_refs": ["t0"],
                            "question_text": "Why does Codex forget context after compaction?",
                            "question_short": "Codex context loss after compaction",
                            "intent_orientation": "implementation",
                            "what_features": ["agent memory", "context continuity", "compaction"],
                            "where_context": ["AIppocampus"],
                            "phase_context": "post_compaction",
                        },
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["question_extraction", "question_tracking"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="extract then track questions",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=2,
                samples_per_job=1,
                chat_fn=fake_chat,
            )
            rows = [
                json.loads(line)
                for line in jobs_output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(result["ok"], result)
        self.assertEqual([item["job"] for item in result["jobs"]], ["question_extraction", "question_tracking"])
        self.assertEqual(rows[-1]["finding_kind"], "question_link")
        self.assertEqual(rows[-1]["source"], "deterministic_question_tracking")
        self.assertEqual(rows[-1]["question_count"], 2)

    def test_question_tracking_job_materializes_confirmed_borderline_artifacts(self) -> None:
        deterministic_jobs = importlib.import_module("subconscious_deterministic_jobs")
        confirmation = importlib.import_module("question_confirmation")

        def question_row(suffix: str, **overrides: Any) -> dict[str, Any]:
            row = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_job_finding",
                "created_at": f"2026-05-2{suffix}T00:00:00Z",
                "job": "question_extraction",
                "finding_kind": "question_candidate",
                "fingerprint": f"sf_question_{suffix}",
                "title": "Agent context continuity",
                "summary": "The user is asking about source-backed continuity.",
                "confidence": 0.86,
                "source_refs": [
                    {
                        "thread_key": f"session:{suffix}",
                        "message_id": f"msg_{suffix}",
                        "source_line": int(suffix) * 10,
                        "timestamp": f"2026-05-2{suffix}T00:00:00Z",
                    }
                ],
                "question_text": "How do I keep agent context across compaction?",
                "question_short": "agent context continuity",
                "intent_orientation": "implementation",
                "what_features": ["agent memory", "context continuity", "compaction"],
                "where_context": ["AIppocampus"],
                "phase_context": "post_compaction",
                "collaboration_context": ["Codex"],
                "concepts": ["AIppocampus", "context continuity"],
            }
            row.update(overrides)
            return row

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs_output = root / "subconscious_jobs.jsonl"
            jobs_output.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        question_row("1"),
                        question_row(
                            "2",
                            question_text="What should the memory router do when context is missing?",
                            question_short="memory router missing context",
                            what_features=["memory router", "context continuity"],
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            requests_path = confirmation.default_confirmation_requests_path(jobs_output)
            artifacts_path = confirmation.default_confirmation_artifacts_path(jobs_output)

            first = deterministic_jobs.run_question_tracking_job(
                registry_path=None,
                jobs_output_path=jobs_output,
                edges_output_path=root / "subconscious_edges.jsonl",
                no_write=False,
                dry_run=False,
            )

            requests = [
                json.loads(line)
                for line in requests_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(first["finding_count"], 0)
            self.assertEqual(first["tracking"]["pending_confirmation_wrote_count"], 1)
            self.assertEqual(first["confirmation_requests_path"], str(requests_path))
            self.assertEqual(first["confirmation_artifacts_path"], str(artifacts_path))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["kind"], "question_pair_confirmation_request")

            artifacts_path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "question_pair_confirmation_artifact",
                        "pair_id": requests[0]["pair_id"],
                        "source_finding_ids": requests[0]["source_finding_ids"],
                        "decision": "accept",
                        "link_type": "recurring",
                        "confidence": 0.86,
                        "model": "offline-fixture-reviewer",
                        "source": "offline_fixture_question_confirmation",
                        "prompt_version": "test-question-confirmation-v1",
                        "rationale": "The compact request shows both questions concern context continuity.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            second = deterministic_jobs.run_question_tracking_job(
                registry_path=None,
                jobs_output_path=jobs_output,
                edges_output_path=root / "subconscious_edges.jsonl",
                no_write=False,
                dry_run=False,
            )
            rows = [
                json.loads(line)
                for line in jobs_output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            links = [row for row in rows if row.get("finding_kind") == "question_link"]

        self.assertEqual(second["finding_count"], 1)
        self.assertEqual(second["tracking"]["borderline_confirmation_accepted_pair_count"], 1)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["source"], "deterministic_question_tracking")
        self.assertEqual(
            links[0]["match_evidence"]["accepted_pairs"][0]["confirmation"]["artifact_audit"][
                "prompt_version"
            ],
            "test-question-confirmation-v1",
        )

    def test_run_jobs_runs_theme_emergence_after_question_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs_output = root / "subconscious_jobs.jsonl"
            jobs_output.write_text(
                "".join(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "aippocampus_subconscious_job_finding",
                            "created_at": f"2026-05-2{suffix}T00:00:00Z",
                            "job": "question_tracking",
                            "finding_kind": "question_link",
                            "fingerprint": f"sf_link_{suffix}",
                            "title": f"Question continuity {suffix}",
                            "summary": "Tracked recurring question continuity.",
                            "confidence": 0.86,
                            "source": "deterministic_question_tracking",
                            "question_cluster_id": f"ql_{suffix}",
                            "linked_question_short": f"context continuity {suffix}",
                            "question_count": 2,
                            "link_type": "recurring",
                            "first_seen": f"2026-05-2{suffix}T00:00:00Z",
                            "last_seen": f"2026-05-2{suffix}T12:00:00Z",
                            "concepts": ["context continuity", "agent alignment"],
                            "source_refs": [
                                {
                                    "thread_key": f"session:{suffix}",
                                    "message_id": f"msg_{suffix}",
                                    "source_line": int(suffix) * 10,
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                    for suffix in ("1", "2", "3")
                ),
                encoding="utf-8",
            )
            associations = root / "associations.json"
            associations.write_text(
                json.dumps(
                    {
                        "terms": {
                            "context continuity": {
                                "term": "context continuity",
                                "status": "verified",
                                "confidence": 0.95,
                                "hit_count": 12,
                                "related_terms": ["source-backed recall", "continuity map"],
                                "threads": [],
                            },
                            "agent alignment": {
                                "term": "agent alignment",
                                "status": "verified",
                                "confidence": 0.94,
                                "hit_count": 12,
                                "related_terms": ["source-backed recall", "continuity map"],
                                "threads": [],
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            concept_graph_path = root / "concept_index.sqlite"
            concept_graph.build_concept_graph(associations, concept_graph_path)
            result = jobs.run_jobs(
                jobs=["question_tracking", "theme_emergence"],
                registry_path=root / "threads.json",
                timeline_path=root / "project_timeline.json",
                concept_graph_path=concept_graph_path,
                jobs_output_path=jobs_output,
                edges_output_path=root / "subconscious_edges.jsonl",
                project=None,
                objective="deterministic follow-up chain",
                max_turns=0,
                max_steps=0,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
            )
            rows = [
                json.loads(line)
                for line in jobs_output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(result["ok"], result)
        self.assertEqual([item["job"] for item in result["jobs"]], ["question_tracking", "theme_emergence"])
        self.assertEqual(rows[-1]["finding_kind"], "theme_candidate")
        self.assertEqual(rows[-1]["source"], "deterministic_theme_emergence")

    def test_run_jobs_runs_question_resolution_after_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_dir = root / "clean"
            clean_dir.mkdir()
            messages_path = clean_dir / "messages.jsonl"
            messages_path.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {
                            "message_id": "msg_question",
                            "turn_id": "turn_1",
                            "turn_index": 1,
                            "source_line": 10,
                            "timestamp": "2026-02-10T00:00:00Z",
                            "role": "user",
                            "text": "How do I keep agent context across compaction?",
                        },
                        {
                            "message_id": "msg_resolution",
                            "turn_id": "turn_2",
                            "turn_index": 2,
                            "source_line": 20,
                            "timestamp": "2026-02-12T00:00:00Z",
                            "role": "user",
                            "text": "The compaction context question is solved.",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "thread_key": "session:context",
                                "paths": {"clean_source_messages_jsonl": str(messages_path)},
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            jobs_output = root / "subconscious_jobs.jsonl"
            jobs_output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_subconscious_job_finding",
                        "created_at": "2026-02-10T00:00:00Z",
                        "job": "question_extraction",
                        "finding_kind": "question_candidate",
                        "fingerprint": "sf_context_question",
                        "title": "Agent context continuity",
                        "summary": "The user asks how context survives compaction.",
                        "confidence": 0.88,
                        "source_refs": [
                            {
                                "thread_key": "session:context",
                                "message_id": "msg_question",
                                "turn_id": "turn_1",
                                "source_line": 10,
                                "timestamp": "2026-02-10T00:00:00Z",
                            }
                        ],
                        "question_text": "How do I keep agent context across compaction?",
                        "question_short": "agent context continuity",
                        "intent_orientation": "implementation",
                        "what_features": ["context", "compaction"],
                        "where_context": ["AIppocampus"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = jobs.run_jobs(
                jobs=["question_resolution"],
                registry_path=registry_path,
                timeline_path=root / "project_timeline.json",
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=root / "subconscious_edges.jsonl",
                project=None,
                objective="deterministic resolution follow-up",
                max_turns=0,
                max_steps=0,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
            )
            rows = [
                json.loads(line)
                for line in jobs_output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertTrue(result["ok"], result)
        self.assertEqual([item["job"] for item in result["jobs"]], ["question_resolution"])
        self.assertEqual(rows[-1]["finding_kind"], "question_resolution_signal")
        self.assertEqual(rows[-1]["source"], "deterministic_question_resolution")
        self.assertEqual(rows[-1]["resolved_source_finding_ids"], ["sf_context_question"])

    def test_semantic_scope_labeling_validates_exact_message_refs_and_labels(self) -> None:
        parsed = {
            "findings": [
                {
                    "kind": "semantic_scope_labels",
                    "title": "Lighthouse metaphor",
                    "summary": "A casual metaphor is being treated as a turning-point idea.",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                    "message_id": "msg_metaphor",
                    "scope_labels": ["idea_seed", "personal_reflection", "unknown"],
                    "label_evidence": [
                        {
                            "label": "idea_seed",
                            "reason": "The source describes the metaphor as a pivot idea.",
                            "confidence": 0.86,
                        },
                        {
                            "label": "personal_reflection",
                            "reason": "The source describes the metaphor as personally meaningful.",
                            "confidence": 0.86,
                        },
                    ],
                },
                {
                    "kind": "semantic_scope_labels",
                    "title": "Hallucinated target",
                    "summary": "This one points at a message not present in source refs.",
                    "confidence": 0.95,
                    "source_refs": ["t0"],
                    "message_id": "msg_missing",
                    "scope_labels": ["idea_seed"],
                },
            ]
        }
        source_bank = {
            "t0": {
                "ref": "t0",
                "turn_ref": "t0",
                "thread_key": "session:life",
                "title": "Casual idea",
                "project_label": "AIppocampus",
                "turn_id": "turn_1",
                "turn_index": 1,
                "source_refs": [
                    {
                        "message_id": "msg_metaphor",
                        "turn_id": "turn_1",
                        "source_line": 7,
                        "role": "user",
                    }
                ],
            }
        }

        findings = jobs.validate_findings("semantic_scope_labeling", parsed, source_bank)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "semantic_scope_labels")
        self.assertEqual(findings[0]["message_id"], "msg_metaphor")
        self.assertEqual(findings[0]["scope_labels"], ["personal_reflection", "idea_seed"])
        self.assertEqual(findings[0]["source_refs"][0]["message_id"], "msg_metaphor")
        self.assertEqual(
            [item["label"] for item in findings[0]["label_evidence"]],
            ["personal_reflection", "idea_seed"],
        )

    def test_semantic_scope_labeling_filters_labels_without_per_label_evidence(self) -> None:
        parsed = {
            "findings": [
                {
                    "kind": "semantic_scope_labels",
                    "title": "Mixed label support",
                    "summary": "The source supports an idea seed and a reading note, but not a preference.",
                    "confidence": 0.9,
                    "source_refs": ["t0"],
                    "message_id": "msg_note",
                    "scope_labels": ["idea_seed", "reading_notes", "preference"],
                    "label_evidence": [
                        {
                            "label": "reading_notes",
                            "reason": "The user explicitly discusses a book note and how it changed the thread.",
                            "confidence": 0.9,
                        },
                        {
                            "label": "preference",
                            "reason": "Weak preference guess.",
                            "confidence": 0.4,
                        },
                    ],
                }
            ]
        }
        source_bank = {
            "t0": {
                "ref": "t0",
                "turn_ref": "t0",
                "thread_key": "session:life",
                "turn_id": "turn_1",
                "source_refs": [
                    {
                        "message_id": "msg_note",
                        "turn_id": "turn_1",
                        "source_line": 7,
                        "role": "user",
                    }
                ],
            }
        }

        findings = jobs.validate_findings("semantic_scope_labeling", parsed, source_bank)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["scope_labels"], ["reading_notes"])
        self.assertEqual(
            [item["label"] for item in findings[0]["label_evidence"]], ["reading_notes"]
        )

    def test_semantic_scope_labeling_payload_exposes_message_source_refs(self) -> None:
        timeline = {
            "projects": {
                "project:life": {
                    "project_label": "Life-wide",
                    "latest_turns": [
                        {
                            "thread_key": "session:life",
                            "title": "Casual idea",
                            "turn_id": "turn_1",
                            "turn_index": 1,
                            "user": "This lighthouse metaphor feels like a pivot.",
                            "assistant": "That image is worth preserving.",
                            "source_refs": [
                                {
                                    "thread_key": "session:life",
                                    "message_id": "msg_metaphor",
                                    "turn_id": "turn_1",
                                    "source_line": 7,
                                    "role": "user",
                                }
                            ],
                        }
                    ],
                }
            }
        }

        turns = jobs.select_timeline_turns(timeline, project="Life-wide", max_turns=4)
        payload = json.loads(
            jobs.jobs_initial_payload("semantic_scope_labeling", "label fuzzy turns", turns, 2, 0)
        )

        self.assertEqual(payload["job"], "semantic_scope_labeling")
        self.assertEqual(
            payload["initial_turns"][0]["source_refs"][0]["message_id"], "msg_metaphor"
        )
        self.assertIn("scope_labels", payload["final_schema"]["findings"][0])
        self.assertIn("label_evidence", payload["final_schema"]["findings"][0])
        self.assertIn("label_evidence", payload["job_spec"]["notes"])

    def test_theme_emergence_payload_exposes_quiet_candidate_contract(self) -> None:
        payload = json.loads(
            jobs.jobs_initial_payload("theme_emergence", "cluster recurring questions", [], 2, 0)
        )
        schema = payload["final_schema"]["findings"][0]

        self.assertEqual(payload["job"], "theme_emergence")
        self.assertEqual(payload["job_spec"]["runner"], "deterministic_theme_emergence")
        self.assertIn("theme_cluster_id", schema)
        self.assertIn("shared_concepts", schema)
        self.assertIn("source_question_link_ids", schema)
        self.assertIn("LLMs may later name deterministic clusters", payload["job_spec"]["notes"])

    def test_theme_emergence_validation_rejects_llm_or_invented_labels(self) -> None:
        source_bank = {
            "t0": {
                "turn_ref": "t0",
                "thread_key": "session:theme",
                "message_id": "msg_theme",
                "source_line": 42,
            }
        }
        base_finding = {
            "kind": "theme_candidate",
            "title": "Recurring question theme: context continuity",
            "summary": "Three recurring links share source-backed concepts.",
            "confidence": 0.86,
            "source_refs": ["t0"],
            "theme_cluster_id": "th_context",
            "theme_label": "Recurring question theme: context continuity",
            "theme_short": "context continuity",
            "cluster_method": "deterministic_shared_concept_neighbors_v1",
            "shared_concepts": ["context continuity", "source-backed recall"],
            "source_question_link_ids": ["sf_link_1", "sf_link_2", "sf_link_3"],
            "linked_question_count": 6,
            "thread_span": 3,
        }

        accepted = jobs.validate_findings(
            "theme_emergence",
            {"findings": [base_finding]},
            source_bank,
        )
        llm_discovery = dict(base_finding, cluster_method="llm_theme_discovery")
        invented_label = dict(base_finding, theme_short="deep identity continuity")

        rejected = jobs.validate_findings(
            "theme_emergence",
            {"findings": [llm_discovery, invented_label]},
            source_bank,
        )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["theme_short"], "context continuity")
        self.assertEqual(accepted[0]["source_refs"][0]["message_id"], "msg_theme")
        self.assertEqual(rejected, [])

    def test_question_extraction_compresses_or_rejects_overlong_raw_questions(self) -> None:
        long_raw = (
            "我自己的感觉可能更多一点，大概一周40多个小时，中间也有很多摸鱼和粗暴一句话让AI迭代，"
            "然后我验收的时候，但即使如此还是感觉有点失控。我有在想这个AI集群的事情，就是比如说"
            "我自己这个tSense，我想弄成就是我想要做商业化嘛，然后有很多的步骤很多的地方需要去协调需要去做，"
            "尤其是我是独立开发者嘛，然后我想的是让Agent..."
        )
        parsed = {
            "findings": [
                {
                    "kind": "question_candidate",
                    "title": "独立开发者如何搭建AI Agent团队",
                    "summary": "用户在追问独立开发者商业化时如何组织 AI Agent 团队。",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                    "question_text": long_raw,
                    "question_short": "独立开发者如何搭建 AI Agent 团队？",
                },
                {
                    "kind": "question_candidate",
                    "title": "",
                    "summary": "这条只有长段原话，没有稳定短问句。",
                    "confidence": 0.86,
                    "source_refs": ["t0"],
                    "question_text": long_raw,
                },
            ]
        }
        source_bank = {
            "t0": {
                "turn_ref": "t0",
                "thread_key": "session:agent-team",
                "title": "tSense",
                "project_label": "tSense",
                "turn_index": 7,
                "assistant_line": 99,
            }
        }

        findings = jobs.validate_findings("question_extraction", parsed, source_bank)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["question_text"], "独立开发者如何搭建 AI Agent 团队？")
        self.assertTrue(findings[0]["question_text_compressed"])
        self.assertLessEqual(len(findings[0]["question_text"]), jobs.QUESTION_TEXT_MAX_CHARS)

    def test_run_concept_edges_job_writes_job_and_edge_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:t": {
                                "project_label": "T-Sense",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:one",
                                        "title": "T-Sense",
                                        "project_label": "T-Sense",
                                        "turn_index": 1,
                                        "user": "本地底座改 Go 吗？",
                                        "assistant": "Go runtime spike 用 gotd 验证。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"
            edges_output = root / "subconscious_edges.jsonl"

            calls: list[list[dict[str, str]]] = []

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                calls.append(messages)
                if len(calls) == 1:
                    content = {
                        "action": "tool",
                        "tool": "expand_concepts",
                        "args": {"terms": ["Go runtime"], "limit": 3},
                        "why": "Inspect existing graph before proposing edge.",
                    }
                else:
                    content = {
                        "action": "final",
                        "findings": [
                            {
                                "kind": "concept_edge",
                                "title": "Go runtime -> gotd",
                                "summary": "Go runtime spike uses gotd.",
                                "src": "Go runtime",
                                "dst": "gotd",
                                "edge_type": "depends_on",
                                "confidence": 0.9,
                                "source_refs": ["t0"],
                            }
                        ],
                    }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "prompt_cache_hit_tokens": 8,
                        "prompt_cache_miss_tokens": 2,
                    },
                }

            result = jobs.run_one_job(
                job="concept_edges",
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project="T-Sense",
                objective="test",
                max_turns=4,
                max_steps=4,
                min_tool_steps=1,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                chat_fn=fake_chat,
            )

            self.assertEqual(result["finding_count"], 1)
            self.assertEqual(result["edge_count"], 1)
            self.assertTrue(jobs_output.exists())
            self.assertTrue(edges_output.exists())
            self.assertEqual(result["cache"]["hit_rate"], 0.8)
            self.assertIn(
                "aippocampus_subconscious_job_finding", jobs_output.read_text(encoding="utf-8")
            )
            self.assertIn("aippocampus_subconscious_edge", edges_output.read_text(encoding="utf-8"))

    def test_semantic_scope_labeling_job_materializes_dynamic_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_source_dir = root / "clean-source"
            clean_source_dir.mkdir()
            (clean_source_dir / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg_metaphor",
                        "turn_id": "turn_1",
                        "source_line": 7,
                        "role": "user",
                        "text": "This lighthouse metaphor feels like a pivot.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:life": {
                                "project_label": "Life-wide",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life",
                                        "title": "Casual idea",
                                        "project_label": "Life-wide",
                                        "turn_id": "turn_1",
                                        "turn_index": 1,
                                        "user": "This lighthouse metaphor feels like a pivot.",
                                        "assistant": "That image is worth preserving.",
                                        "source_refs": [
                                            {
                                                "thread_key": "session:life",
                                                "message_id": "msg_metaphor",
                                                "turn_id": "turn_1",
                                                "source_line": 7,
                                                "role": "user",
                                            }
                                        ],
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"
            edges_output = root / "subconscious_edges.jsonl"
            calls: list[list[dict[str, str]]] = []

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                calls.append(messages)
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "semantic_scope_labels",
                            "title": "Lighthouse metaphor pivot",
                            "summary": "A casual metaphor is being treated as a personally meaningful idea pivot.",
                            "confidence": 0.88,
                            "source_refs": ["t0"],
                            "message_id": "msg_metaphor",
                            "scope_labels": ["personal_reflection", "idea_seed", "life_context"],
                            "label_evidence": [
                                {
                                    "label": "personal_reflection",
                                    "reason": "The source frames the metaphor as personally meaningful.",
                                    "confidence": 0.88,
                                },
                                {
                                    "label": "idea_seed",
                                    "reason": "The source frames the metaphor as an idea pivot.",
                                    "confidence": 0.86,
                                },
                                {
                                    "label": "life_context",
                                    "reason": "The source frames the metaphor as personally meaningful lived context.",
                                    "confidence": 0.94,
                                },
                            ],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_one_job(
                job="semantic_scope_labeling",
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project="Life-wide",
                objective="label fuzzy life-wide messages",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                chat_fn=fake_chat,
            )

            self.assertEqual(len(calls), 1)
            self.assertEqual(result["finding_count"], 1)
            self.assertEqual(result["edge_count"], 0)
            self.assertFalse(edges_output.exists())
            staged = json.loads(jobs_output.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(staged["source"], "deepseek_subconscious_jobs")
            self.assertEqual(staged["finding_kind"], "semantic_scope_labels")
            self.assertEqual(staged["message_id"], "msg_metaphor")
            self.assertEqual(
                [item["label"] for item in staged["label_evidence"]],
                ["personal_reflection", "idea_seed", "life_context"],
            )

            materialized = semantic_scope_materializer.build_semantic_scope_labels(
                jobs_output_path=jobs_output,
                clean_source_dir=clean_source_dir,
            )

            self.assertEqual(materialized["row_count"], 1)
            sidecar = json.loads(
                (clean_source_dir / "semantic-scope-labels.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(sidecar["message_id"], "msg_metaphor")
            self.assertEqual(sidecar["source_job"], "deepseek_subconscious_jobs")
            self.assertEqual(
                sidecar["scope_labels"], ["personal_reflection", "idea_seed", "life_context"]
            )

    def test_run_jobs_can_execute_samples_concurrently_without_parallel_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "心理地图要怎样做？",
                                        "assistant": "用潜意识层提出地标和路线。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"
            edges_output = root / "subconscious_edges.jsonl"
            active = 0
            max_active = 0
            lock = threading.Lock()
            call_count = 0

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                nonlocal active, max_active, call_count
                with lock:
                    active += 1
                    call_count += 1
                    max_active = max(max_active, active)
                    current = call_count
                time.sleep(0.05)
                with lock:
                    active -= 1
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": f"Concurrent finding {current}",
                            "summary": "DeepSeek sample produced a source-backed finding.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["project_drift", "trigger_mining"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project="AIppocampus",
                objective="test concurrent jobs",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=4,
                samples_per_job=2,
                chat_fn=fake_chat,
            )

            self.assertEqual(result["job_count"], 4)
            self.assertGreater(max_active, 1)
            self.assertTrue(jobs_output.exists())
            lines = jobs_output.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4)
            self.assertTrue(all("aippocampus_subconscious_job_finding" in line for line in lines))

    def test_openai_compatible_route_caps_subconscious_job_concurrency_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "provider route 怎么收口？",
                                        "assistant": "用 local/offline capability 做保守 fallback。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, base_url, max_tokens, timeout, temperature
                self.assertEqual(model, "local-jobs-model")
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Provider boundary",
                            "summary": "Local provider route keeps conservative defaults.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            with patch.dict(
                os.environ,
                {
                    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_jobs",
                    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-jobs-model",
                    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_JOBS_KEY",
                    "LOCAL_JOBS_KEY": "present",
                },
                clear=False,
            ):
                result = jobs.run_jobs(
                    jobs=["project_drift", "trigger_mining"],
                    registry_path=registry_path,
                    timeline_path=timeline_path,
                    concept_graph_path=root / "missing.sqlite",
                    jobs_output_path=root / "subconscious_jobs.jsonl",
                    edges_output_path=root / "subconscious_edges.jsonl",
                    project="AIppocampus",
                    objective="test local provider boundary",
                    max_turns=4,
                    max_steps=1,
                    min_tool_steps=0,
                    model=jobs.DEFAULT_MODEL,
                    base_url=jobs.DEFAULT_BASE_URL,
                    api_key=None,
                    max_tokens=None,
                    timeout=1,
                    temperature=0.2,
                    concurrency=4,
                    samples_per_job=1,
                    model_route="local_jobs",
                    chat_fn=fake_chat,
                )

            self.assertEqual(result["concurrency"], 1)
            self.assertEqual(result["model_route"]["provider"], "local-test")
            self.assertEqual(result["cache"], {"available": False, "kind": "none"})
            self.assertEqual(result["jobs"][0]["model"], "local-jobs-model")
            staged = json.loads(
                (root / "subconscious_jobs.jsonl").read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(staged["source"], "external_model_subconscious_jobs")
            self.assertEqual(staged["model_route"]["provider"], "local-test")

    def test_run_jobs_warms_first_sample_before_same_prefix_followups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "心理地图要怎样做？",
                                        "assistant": "用潜意识层提出地标和路线。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            jobs_output = root / "subconscious_jobs.jsonl"
            edges_output = root / "subconscious_edges.jsonl"
            sample1_finished = threading.Event()
            sample2_started_before_warm = False
            lock = threading.Lock()

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                nonlocal sample2_started_before_warm
                payload = json.loads(messages[1]["content"])
                sample_two = "Diversity sample 2/2" in str(payload.get("objective") or "")
                with lock:
                    if sample_two and not sample1_finished.is_set():
                        sample2_started_before_warm = True
                time.sleep(0.02)
                if not sample_two:
                    sample1_finished.set()
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Warmup finding",
                            "summary": "DeepSeek sample produced a source-backed finding.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["project_drift"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project="AIppocampus",
                objective="test cache warmup ordering",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=2,
                samples_per_job=2,
                chat_fn=fake_chat,
            )

            self.assertTrue(result["ok"], result)
            self.assertFalse(sample2_started_before_warm)

    def test_run_one_job_repairs_malformed_json_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "心理地图要怎样做？",
                                        "assistant": "用潜意识层提出地标和路线。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")
            calls = 0

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature
                nonlocal calls
                calls += 1
                if calls == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"action":"final","findings":[{"title":"broken"'
                                }
                            }
                        ],
                        "usage": {"total_tokens": 1},
                    }
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Repaired finding",
                            "summary": "The malformed first response was repaired into source-backed JSON.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_one_job(
                job="project_drift",
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="test malformed repair",
                max_turns=4,
                max_steps=2,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                chat_fn=fake_chat,
                no_write=True,
            )

            self.assertEqual(calls, 2)
            self.assertEqual(result["finding_count"], 1)
            self.assertEqual(result["findings"][0]["title"], "Repaired finding")

    def test_tool_observations_are_redacted_before_second_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages_path = root / "messages.jsonl"
            messages_path.write_text(
                json.dumps(
                    {
                        "message_id": "m1",
                        "turn_id": "turn-1",
                        "source_line": 10,
                        "role": "user",
                        "phase": "",
                        "turn_index": 1,
                        "text": f"token={FAKE_TEST_SECRET_VALUE} {fake_test_windows_path('jobs-tool.txt')}",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "thread_key": "session:one",
                                "title": "Secret job test",
                                "project_label": "AIppocampus",
                                "project_tags": ["AIppocampus"],
                                "paths": {"clean_source_messages_jsonl": str(messages_path)},
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:one",
                                        "title": "Secret job test",
                                        "turn_id": "turn-1",
                                        "turn_index": 1,
                                        "user": "find token source",
                                        "assistant": "ok",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            calls: list[list[dict[str, str]]] = []

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                calls.append(messages)
                content = (
                    {
                        "action": "tool",
                        "tool": "search_clean_source",
                        "args": {"terms": ["token"], "limit": 1},
                    }
                    if len(calls) == 1
                    else {"action": "final", "findings": []}
                )
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            jobs.run_one_job(
                job="project_drift",
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="test redaction",
                max_turns=4,
                max_steps=2,
                min_tool_steps=1,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                chat_fn=fake_chat,
                no_write=True,
            )

        second_call = json.dumps(calls[1], ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, second_call)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, second_call)
        self.assertIn("<redacted:secret>", second_call)
        self.assertIn("<redacted:local-path>", second_call)

    def test_run_jobs_isolates_failed_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline_path = root / "project_timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "projects": {
                            "project:ai": {
                                "project_label": "AIppocampus",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:map",
                                        "title": "AIppocampus",
                                        "project_label": "AIppocampus",
                                        "turn_index": 1,
                                        "user": "多线程 hook 会不会重复启动？",
                                        "assistant": "scheduler 用 lease 折叠重复启动。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry_path = root / "threads.json"
            registry_path.write_text(json.dumps({"threads": []}), encoding="utf-8")

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
            ) -> dict[str, Any]:
                del api_key, model, base_url, max_tokens, timeout, temperature
                if "Diversity sample 1/2" in messages[1]["content"]:
                    raise RuntimeError("simulated malformed provider response")
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "Surviving sample",
                            "summary": "A second sample should survive even when the first fails.",
                            "confidence": 0.82,
                            "source_refs": ["t0"],
                        }
                    ],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            result = jobs.run_jobs(
                jobs=["project_drift"],
                registry_path=registry_path,
                timeline_path=timeline_path,
                concept_graph_path=root / "missing.sqlite",
                jobs_output_path=root / "subconscious_jobs.jsonl",
                edges_output_path=root / "subconscious_edges.jsonl",
                project="AIppocampus",
                objective="test failure isolation",
                max_turns=4,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                api_key="test",
                max_tokens=None,
                timeout=1,
                temperature=0.2,
                concurrency=2,
                samples_per_job=2,
                chat_fn=fake_chat,
                no_write=True,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["partial_failure"])
            self.assertEqual(result["successful_job_count"], 1)
            self.assertEqual(result["failure_count"], 1)
            self.assertEqual(result["finding_count"], 1)


if __name__ == "__main__":
    unittest.main()
