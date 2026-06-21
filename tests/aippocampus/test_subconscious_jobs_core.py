from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aippocampus_runtime.subconscious import (
    job_circuits as circuits,
)
from aippocampus_runtime.subconscious import (
    job_storage,
    jobs,
)
from aippocampus_runtime.subconscious import (
    jobs_config as config_module,
)
from aippocampus_runtime.subconscious.staging_maintenance import (
    StagingPressureThresholds,
)
from tests.aippocampus.redaction_fixtures import (
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_PASSWORD_VALUE,
    fake_test_windows_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
JOBS_RUNNER = SCRIPTS / "aippocampus_runtime" / "subconscious" / "jobs.py"

class SubconsciousJobsCoreTests(unittest.TestCase):
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
                    "api_key_env": "AIPPOCAMPUS_DEEPSEEK_API_KEY",
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

    def test_job_storage_returns_backpressure_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "subconscious_jobs.jsonl"

            result = job_storage.append_job_findings(
                output,
                [
                    {
                        "kind": "question_candidate",
                        "title": "Queue pressure",
                        "summary": "A source-backed finding should still warn on pressure.",
                        "source_refs": [{"thread_key": "thread:one", "line": 12}],
                    }
                ],
                model="deepseek-test",
                batch_id="batch-one",
                usage={},
                pressure_thresholds=StagingPressureThresholds(max_rows=0, max_bytes=0),
            )

        self.assertTrue(result["staging_pressure"]["warning"])
        self.assertIn("row_threshold_exceeded", result["staging_pressure"]["warning_reasons"])

    def test_job_circuit_catalog_is_separate_from_runner(self) -> None:
        runner_source = JOBS_RUNNER.read_text(encoding="utf-8")

        self.assertNotIn("JOB_SPECS: dict", runner_source)
        self.assertEqual(jobs.JOB_SPECS, circuits.JOB_SPECS)
        self.assertEqual(jobs.job_names("all"), circuits.job_names("all"))
        self.assertEqual(
            json.loads(jobs.jobs_initial_payload("concept_edges", "objective", [], 2, 1)),
            json.loads(circuits.jobs_initial_payload("concept_edges", "objective", [], 2, 1)),
        )

    def test_job_circuit_dependency_contract_is_validated(self) -> None:
        ordered = circuits.job_names("all")

        self.assertLess(ordered.index("question_extraction"), ordered.index("question_tracking"))
        self.assertLess(ordered.index("question_tracking"), ordered.index("theme_emergence"))
        self.assertLess(ordered.index("question_tracking"), ordered.index("question_resolution"))
        with patch.dict(
            circuits.JOB_SPECS,
            {
                "bad_followup": {
                    "purpose": "bad dependent job",
                    "finding_kind": "bad",
                    "depends_on": ["missing_producer"],
                    "must_include": [],
                }
            },
        ):
            with self.assertRaisesRegex(ValueError, "bad_followup.*missing_producer"):
                circuits.validate_job_dependency_contract()

    def test_job_sample_plan_is_separate_from_runner(self) -> None:
        from aippocampus_runtime.subconscious import job_plan as plan

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
        self.assertTrue(config.event_salience_gate)
        self.assertTrue(config.dry_run)

    def test_jobs_run_config_can_opt_out_of_default_salience_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            class Args:
                registry = None
                registry_dir = str(root)
                timeline = None
                concept_graph = None
                jobs_output = None
                edges_output = None
                event_salience_output = None
                job = "concept_edges"
                project = "AIppocampus"
                objective = "test"
                max_turns = 4
                max_steps = 2
                min_tool_steps = 1
                model_route = None
                model = "deepseek-v4-flash"
                base_url = "https://example.invalid"
                api_key_env = "MISSING_TEST_KEY"
                max_tokens = None
                timeout = 9
                temperature = 0.2
                concurrency = 3
                samples_per_job = 2
                event_salience_gate = False
                continuity_domain_salience_mode = "off"
                continuity_domain_events_output = None
                continuity_domain_snapshot_dir = None
                continuity_domain_clean_source_dir = None
                continuity_domain_publish = False
                dry_run = True
                no_write = False

            config = jobs.jobs_run_config_from_args(Args())

        self.assertFalse(config.event_salience_gate)

    def test_job_validation_is_separate_from_runner(self) -> None:
        from aippocampus_runtime.subconscious import job_validation as validation
        from aippocampus_runtime.subconscious import validation_audit

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

    def test_deepseek_jobs_send_thinking_contract_through_shared_chat_wrapper(self) -> None:
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
                                        "thread_key": "session:jobs",
                                        "title": "AIppocampus",
                                        "timestamp": "2026-05-25T00:00:00Z",
                                        "turn_index": 1,
                                        "user": "继续 subconscious jobs。",
                                        "assistant": "需要统一 DeepSeek thinking contract。",
                                    }
                                ],
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            def fake_chat(
                messages: list[dict[str, str]],
                api_key: str,
                model: str,
                base_url: str,
                max_tokens: int | None,
                timeout: int,
                temperature: float,
                *,
                thinking: str | None = None,
                reasoning_effort: str | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                del messages, api_key, model, base_url, max_tokens, timeout, temperature, kwargs
                captured["thinking"] = thinking
                captured["reasoning_effort"] = reasoning_effort
                content = {
                    "action": "final",
                    "findings": [
                        {
                            "kind": "project_drift",
                            "title": "DeepSeek contract alignment",
                            "summary": "The source-backed job notes a thinking-mode contract alignment.",
                            "confidence": 0.86,
                            "source_refs": ["t0"],
                            "concepts": ["DeepSeek thinking contract"],
                        }
                    ],
                }
                return {"choices": [{"message": {"content": json.dumps(content)}}]}

            with patch.object(jobs, "call_chat_json", fake_chat):
                result = jobs.run_one_job(
                    job="project_drift",
                    registry_path=root / "threads.json",
                    timeline_path=timeline_path,
                    concept_graph_path=root / "missing.sqlite",
                    jobs_output_path=root / "subconscious_jobs.jsonl",
                    edges_output_path=root / "subconscious_edges.jsonl",
                    project="AIppocampus",
                    objective="test DeepSeek thinking contract",
                    max_turns=1,
                    max_steps=1,
                    min_tool_steps=0,
                    model=jobs.DEFAULT_MODEL,
                    base_url=jobs.DEFAULT_BASE_URL,
                    api_key="test",
                    max_tokens=None,
                    timeout=1,
                    temperature=0.2,
                    chat_fn=jobs.call_chat_json,
                    no_write=True,
                )

            self.assertEqual(captured["thinking"], "enabled")
            self.assertEqual(captured["reasoning_effort"], "high")
            self.assertEqual(result["thinking"], "enabled")
            self.assertEqual(result["reasoning_effort"], "high")

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

if __name__ == "__main__":
    unittest.main()
