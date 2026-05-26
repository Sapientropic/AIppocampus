from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import subconscious_jobs as jobs  # noqa: E402


class SubconsciousJobsTests(unittest.TestCase):
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
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
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
            self.assertIn("aippocampus_subconscious_job_finding", jobs_output.read_text(encoding="utf-8"))
            self.assertIn("aippocampus_subconscious_edge", edges_output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
