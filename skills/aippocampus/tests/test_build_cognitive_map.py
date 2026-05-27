from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_cognitive_map as cognitive_map  # noqa: E402


class BuildCognitiveMapTests(unittest.TestCase):
    def test_registry_alone_does_not_create_routes(self) -> None:
        registry = {
            "schema_version": 1,
            "threads": [
                {
                    "thread_key": "session:map",
                    "title": "AIppocampus",
                    "project_label": "AIppocampus",
                    "keywords": ["心理地图", "认知地图"],
                    "anchor_titles": ["外置海马体"],
                    "summary": "A registry entry can locate an episode, but should not invent cognitive routes.",
                }
            ],
        }

        result = cognitive_map.build_cognitive_map(registry=registry, job_findings=[])

        self.assertEqual(result["route_count"], 0)
        self.assertEqual(result["landmark_count"], 0)
        self.assertEqual(result["episodes"][0]["thread_key"], "session:map")
        self.assertEqual(result["status"], "needs_subconscious")

    def test_deepseek_subconscious_finding_creates_source_backed_route(self) -> None:
        registry = {
            "schema_version": 1,
            "updated_at": "2026-05-26T00:00:00Z",
            "threads": [
                {
                    "thread_key": "session:map",
                    "title": "AIppocampus",
                    "project_label": "AIppocampus",
                    "keywords": ["心理地图"],
                    "anchor_titles": ["外置海马体"],
                    "summary": "The project is exploring hippocampus-like mental maps.",
                }
            ],
        }
        finding = {
            "kind": "aippocampus_subconscious_job_finding",
            "job": "cognitive_map",
            "finding_kind": "cognitive_map_route",
            "title": "AIppocampus mental map",
            "summary": "Use hippocampus spatial-memory metaphors as a route into the AIppocampus architecture thread.",
            "confidence": 0.9,
            "landmarks": ["AIppocampus", "外置海马体", "认知地图"],
            "regions": ["memory architecture"],
            "route_cues": ["心理地图", "位置细胞", "网格细胞"],
            "target_thread_keys": ["session:map"],
            "source_refs": [
                {
                    "thread_key": "session:map",
                    "title": "AIppocampus",
                    "project_label": "AIppocampus",
                    "line": 88,
                }
            ],
            "source": "deepseek_subconscious_jobs",
        }

        result = cognitive_map.build_cognitive_map(registry=registry, job_findings=[finding])

        self.assertEqual(result["route_count"], 1)
        self.assertEqual(result["landmark_count"], 3)
        self.assertEqual(result["routes"][0]["thread_keys"], ["session:map"])
        self.assertEqual(result["routes"][0]["source"], "deepseek_subconscious_jobs")

        matches = cognitive_map.match_cognitive_map("咱们继续心理地图和位置细胞这条升级", result)
        self.assertEqual(matches[0]["thread_keys"], ["session:map"])
        self.assertIn("心理地图", matches[0]["matched_cues"])

    def test_cli_writes_cognitive_map_from_jobs_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "threads.json"
            jobs_path = root / "subconscious_jobs.jsonl"
            output_path = root / "cognitive_map.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:map",
                                "title": "AIppocampus",
                                "project_label": "AIppocampus",
                                "paths": {},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            jobs_path.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "job": "cognitive_map",
                        "finding_kind": "cognitive_map_route",
                        "title": "AIppocampus mental map",
                        "summary": "Route mental-map prompts into the source thread.",
                        "confidence": 0.85,
                        "landmarks": ["AIppocampus"],
                        "regions": ["memory architecture"],
                        "route_cues": ["心理地图"],
                        "target_thread_keys": ["session:map"],
                        "source_refs": [{"thread_key": "session:map", "line": 5}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = cognitive_map.build_from_files(
                registry_path=registry_path,
                jobs_path=jobs_path,
                output_path=output_path,
            )

            self.assertEqual(result["route_count"], 1)
            self.assertTrue(output_path.exists())
            self.assertIn("cognitive_map_route", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
