from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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

from aippocampus_runtime.source import semantic_scope_builder as builder  # noqa: E402
from aippocampus_runtime.source import semantic_scope_labels as semantic  # noqa: E402


class SemanticScopeLabelsTests(unittest.TestCase):
    def write_jsonl(self, path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_materializer_accepts_only_source_backed_existing_message_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_source = root / "clean-source"
            self.write_jsonl(
                clean_source / "messages.jsonl",
                [
                    {
                        "message_id": "msg_keep",
                        "turn_id": "turn_1",
                        "role": "user",
                        "source_line": 7,
                        "text": "This casual metaphor feels like a pivot.",
                        "scope_labels": [],
                    }
                ],
            )
            jobs_output = root / "subconscious_jobs.jsonl"
            self.write_jsonl(
                jobs_output,
                [
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "source": "deepseek_subconscious_jobs",
                        "message_id": "msg_keep",
                        "scope_labels": ["idea_seed", "personal_reflection", "unknown_label"],
                        "confidence": 0.84,
                        "summary": "The source is a casual metaphor plus turning-point signal.",
                        "label_evidence": [
                            {
                                "label": "idea_seed",
                                "reason": "The source frames the metaphor as a turning-point idea.",
                                "confidence": 0.82,
                            },
                            {
                                "label": "personal_reflection",
                                "reason": "The source treats the metaphor as personally meaningful.",
                                "confidence": 0.86,
                            },
                        ],
                        "source_refs": [
                            {
                                "ref": "t0",
                                "thread_key": "public-example-thread",
                                "message_id": "msg_keep",
                                "turn_id": "turn_1",
                                "source_line": 7,
                                "role": "user",
                            }
                        ],
                    },
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": "msg_missing",
                        "scope_labels": ["idea_seed"],
                        "confidence": 0.95,
                        "source_refs": [{"message_id": "msg_missing"}],
                    },
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": "msg_keep",
                        "scope_labels": ["life_context"],
                        "confidence": 0.9,
                        "source_refs": [{"message_id": "other"}],
                    },
                ],
            )

            result = builder.build_semantic_scope_labels(
                jobs_output_path=jobs_output,
                clean_source_dir=clean_source,
            )
            sidecar = semantic.load_semantic_scope_labels(clean_source)

        self.assertTrue(result["ok"])
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(sidecar["msg_keep"]["scope_labels"], ["personal_reflection", "idea_seed"])
        self.assertEqual(sidecar["msg_keep"]["source"], "deepseek_subconscious_scope_labels")
        self.assertIn("clean source", sidecar["msg_keep"]["boundary"])

    def test_materializer_requires_label_evidence_for_every_materialized_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_source = root / "clean-source"
            self.write_jsonl(
                clean_source / "messages.jsonl",
                [
                    {
                        "message_id": "msg_mixed",
                        "turn_id": "turn_1",
                        "role": "user",
                        "source_line": 7,
                        "text": "This feels like a durable direction for the project.",
                        "scope_labels": [],
                    },
                    {
                        "message_id": "msg_reading",
                        "turn_id": "turn_2",
                        "role": "user",
                        "source_line": 8,
                        "text": "The book note changed how I think about continuity.",
                        "scope_labels": [],
                    },
                ],
            )
            jobs_output = root / "subconscious_jobs.jsonl"
            self.write_jsonl(
                jobs_output,
                [
                    {
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": "msg_mixed",
                        "scope_labels": ["idea_seed", "life_context", "preference"],
                        "confidence": 0.95,
                        "summary": "Mixed legacy-style semantic labels without per-label evidence.",
                        "source_refs": [{"message_id": "msg_mixed", "source_line": 7}],
                    },
                    {
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": "msg_reading",
                        "scope_labels": ["reading_notes"],
                        "confidence": 0.9,
                        "summary": "Reading note with explicit label support.",
                        "label_evidence": [
                            {
                                "label": "reading_notes",
                                "reason": "The source explicitly describes a book note changing the user's thinking.",
                                "confidence": 0.92,
                            }
                        ],
                        "source_refs": [{"message_id": "msg_reading", "source_line": 8}],
                    },
                ],
            )

            result = builder.build_semantic_scope_labels(
                jobs_output_path=jobs_output,
                clean_source_dir=clean_source,
            )
            sidecar = semantic.load_semantic_scope_labels(clean_source)

        self.assertEqual(result["row_count"], 1)
        self.assertNotIn("msg_mixed", sidecar)
        self.assertEqual(sidecar["msg_reading"]["scope_labels"], ["reading_notes"])
        self.assertEqual(sidecar["msg_reading"]["label_evidence"][0]["label"], "reading_notes")

    def test_continuity_and_open_question_require_stronger_label_evidence(self) -> None:
        loose_item = {
            "scope_labels": ["relationship_continuity", "open_question", "technical_work"],
            "label_evidence": [
                {
                    "label": "relationship_continuity",
                    "reason": "The source mentions memory moving across time.",
                    "confidence": 0.8,
                },
                {
                    "label": "open_question",
                    "reason": "The source is philosophically exploratory.",
                    "confidence": 0.85,
                },
                {
                    "label": "technical_work",
                    "reason": "The source discusses a concrete implementation plan.",
                    "confidence": 0.82,
                },
            ],
        }
        strong_item = {
            "scope_labels": ["relationship_continuity", "open_question"],
            "label_evidence": [
                {
                    "label": "relationship_continuity",
                    "reason": "The source explicitly asks the assistant to preserve continuity across prior conversations.",
                    "confidence": 0.97,
                },
                {
                    "label": "open_question",
                    "reason": "The source names an unresolved question the user wants to continue later.",
                    "confidence": 0.95,
                },
            ],
        }

        self.assertEqual(semantic.filtered_semantic_scope_labels(loose_item), ["technical_work"])
        self.assertEqual(
            semantic.filtered_semantic_scope_labels(strong_item),
            ["relationship_continuity", "open_question"],
        )

    def test_materializer_merges_duplicate_findings_by_message(self) -> None:
        messages = {
            "msg_keep": {
                "message_id": "msg_keep",
                "turn_id": "turn_1",
                "source_line": 7,
            }
        }
        rows = semantic.semantic_scope_label_rows_from_findings(
            [
                {
                    "finding_kind": "semantic_scope_labels",
                    "job": "semantic_scope_labeling",
                    "message_id": "msg_keep",
                    "scope_labels": ["idea_seed"],
                    "confidence": 0.6,
                    "summary": "Idea seed.",
                    "label_evidence": [
                        {
                            "label": "idea_seed",
                            "reason": "The source names a concrete early idea.",
                            "confidence": 0.86,
                        }
                    ],
                    "source_refs": [{"message_id": "msg_keep", "source_line": 7}],
                },
                {
                    "finding_kind": "semantic_scope_labels",
                    "job": "semantic_scope_labeling",
                    "message_id": "msg_keep",
                    "scope_labels": ["personal_reflection"],
                    "confidence": 0.86,
                    "summary": "Personal reflection.",
                    "label_evidence": [
                        {
                            "label": "personal_reflection",
                            "reason": "The source is explicitly about personal reflection.",
                            "confidence": 0.86,
                        }
                    ],
                    "source_refs": [{"message_id": "msg_keep", "source_line": 7}],
                },
            ],
            messages,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scope_labels"], ["personal_reflection", "idea_seed"])
        self.assertEqual(rows[0]["confidence"], 0.86)
        self.assertEqual(rows[0]["rationale"], "Personal reflection.")

    def test_loader_rejects_sidecar_rows_without_matching_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean_source = Path(tmp) / "clean-source"
            self.write_jsonl(
                clean_source / "messages.jsonl",
                [
                    {
                        "message_id": "msg_keep",
                        "source_line": 7,
                        "text": "A metaphor.",
                        "scope_labels": [],
                    }
                ],
            )
            self.write_jsonl(
                clean_source / "semantic-scope-labels.jsonl",
                [
                    {
                        "message_id": "msg_keep",
                        "scope_labels": ["idea_seed"],
                        "confidence": 0.95,
                    },
                    {
                        "message_id": "msg_keep",
                        "scope_labels": ["personal_reflection"],
                        "confidence": 0.95,
                        "source_refs": [{"message_id": "other"}],
                    },
                    {
                        "message_id": "msg_keep",
                        "scope_labels": ["idea_seed"],
                        "confidence": 0.95,
                        "source_refs": [{"message_id": "msg_keep", "source_line": 7}],
                        "label_evidence": [
                            {
                                "label": "idea_seed",
                                "reason": "The source records a metaphor as an early idea.",
                                "confidence": 0.86,
                            }
                        ],
                    },
                ],
            )

            sidecar = semantic.load_semantic_scope_labels(clean_source)

        self.assertEqual(sidecar["msg_keep"]["scope_labels"], ["idea_seed"])

    def test_registry_materializer_processes_project_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = root / "registry"
            clean_source = root / "threads" / "thread-one" / "clean-source"
            self.write_jsonl(
                clean_source / "messages.jsonl",
                [
                    {
                        "message_id": "msg_keep",
                        "turn_id": "turn_1",
                        "source_line": 7,
                        "text": "A casual metaphor turns into a project direction.",
                        "scope_labels": [],
                    }
                ],
            )
            registry_dir.mkdir()
            (registry_dir / "threads.json").write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "thread_key": "thread-one",
                                "project_label": "Life Chat",
                                "paths": {
                                    "clean_source_messages_jsonl": str(
                                        clean_source / "messages.jsonl"
                                    )
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            jobs_output = registry_dir / "subconscious_jobs.jsonl"
            self.write_jsonl(
                jobs_output,
                [
                    {
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": "msg_keep",
                        "scope_labels": ["idea_seed"],
                        "confidence": 0.86,
                        "summary": "Source-backed semantic label.",
                        "label_evidence": [
                            {
                                "label": "idea_seed",
                                "reason": "The source explicitly turns a metaphor into project direction.",
                                "confidence": 0.82,
                            }
                        ],
                        "source_refs": [{"message_id": "msg_keep", "source_line": 7}],
                    }
                ],
            )

            result = builder.build_semantic_scope_labels_for_registry(
                registry_path=registry_dir / "threads.json",
                jobs_output_path=jobs_output,
                project="Life Chat",
            )

            self.assertEqual(result["target_count"], 1)
            self.assertEqual(result["row_count"], 1)
            self.assertEqual(list(clean_source.glob(".semantic-scope-labels.jsonl.*.tmp")), [])
            self.assertIn(
                "msg_keep",
                (clean_source / "semantic-scope-labels.jsonl").read_text(encoding="utf-8"),
            )

    def test_registry_materializer_text_cli_does_not_require_single_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = root / "registry"
            clean_source = root / "threads" / "thread-one" / "clean-source"
            self.write_jsonl(
                clean_source / "messages.jsonl",
                [
                    {
                        "message_id": "msg_keep",
                        "turn_id": "turn_1",
                        "source_line": 7,
                        "text": "A life-wide idea.",
                        "scope_labels": [],
                    }
                ],
            )
            registry_dir.mkdir()
            registry_path = registry_dir / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "thread_key": "thread-one",
                                "project_label": "Life Chat",
                                "paths": {
                                    "clean_source_messages_jsonl": str(
                                        clean_source / "messages.jsonl"
                                    )
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            jobs_output = registry_dir / "subconscious_jobs.jsonl"
            self.write_jsonl(
                jobs_output,
                [
                    {
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": "msg_keep",
                        "scope_labels": ["idea_seed"],
                        "confidence": 0.86,
                        "summary": "Source-backed semantic label.",
                        "label_evidence": [
                            {
                                "label": "idea_seed",
                                "reason": "The source states a life-wide idea.",
                                "confidence": 0.82,
                            }
                        ],
                        "source_refs": [{"message_id": "msg_keep", "source_line": 7}],
                    }
                ],
            )
            stdout = StringIO()

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "build_semantic_scope_labels.py",
                        "--registry",
                        str(registry_path),
                        "--project",
                        "Life Chat",
                    ],
                ),
                redirect_stdout(stdout),
            ):
                code = builder.main()

        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("semantic scope-label rows: 1", rendered)
        self.assertIn("targets: 1", rendered)


if __name__ == "__main__":
    unittest.main()
