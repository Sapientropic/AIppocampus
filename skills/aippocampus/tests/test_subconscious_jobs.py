from __future__ import annotations

import importlib
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import build_semantic_scope_labels as semantic_scope_materializer  # noqa: E402
import subconscious_jobs as jobs  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_PASSWORD_VALUE,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


class SubconsciousJobsTests(unittest.TestCase):
    def test_job_circuit_catalog_is_separate_from_runner(self) -> None:
        circuits = importlib.import_module("subconscious_job_circuits")
        runner_source = (SCRIPTS / "subconscious_jobs.py").read_text(encoding="utf-8")

        self.assertNotIn("JOB_SPECS: dict", runner_source)
        self.assertEqual(jobs.JOB_SPECS, circuits.JOB_SPECS)
        self.assertEqual(jobs.job_names("all"), circuits.job_names("all"))
        self.assertEqual(
            json.loads(jobs.jobs_initial_payload("concept_edges", "objective", [], 2, 1)),
            json.loads(circuits.jobs_initial_payload("concept_edges", "objective", [], 2, 1)),
        )

    def test_job_sample_plan_is_separate_from_runner(self) -> None:
        plan = importlib.import_module("subconscious_job_plan")
        runner_source = (SCRIPTS / "subconscious_jobs.py").read_text(encoding="utf-8")

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

    def test_job_validation_is_separate_from_runner(self) -> None:
        validation = importlib.import_module("subconscious_job_validation")
        runner_source = (SCRIPTS / "subconscious_jobs.py").read_text(encoding="utf-8")

        self.assertIs(jobs.validate_findings, validation.validate_findings)
        self.assertEqual(jobs.QUESTION_TEXT_MAX_CHARS, validation.QUESTION_TEXT_MAX_CHARS)
        self.assertNotIn("def validate_findings", runner_source)
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
            }
        }

        findings = jobs.validate_findings("question_extraction", parsed, source_bank)

        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0]["kind"], "question_candidate")
        self.assertEqual(findings[0]["intent_orientation"], "architecture_decision")
        self.assertIn("cross-project recall", findings[0]["what_features"])
        self.assertEqual(findings[1]["kind"], "frontier_marker")
        self.assertEqual(findings[1]["frontier_type"], "scope_boundary")
        self.assertIn("injected instruction", findings[1]["boundary_reason"])

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
