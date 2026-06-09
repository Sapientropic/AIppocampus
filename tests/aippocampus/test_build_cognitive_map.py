from __future__ import annotations

import json
import sys
import tempfile
import unittest
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

from aippocampus_runtime.navigation import cognitive_map as cognitive_map  # noqa: E402


class BuildCognitiveMapTests(unittest.TestCase):
    def build_multi_scale_fixture(self) -> dict:
        registry = {
            "schema_version": 1,
            "updated_at": "2026-06-01T00:00:00Z",
            "threads": [
                {
                    "thread_key": "session:map",
                    "title": "AIppocampus cognitive map",
                    "project_label": "AIppocampus",
                    "updated_at": "2026-01-15T00:00:00Z",
                    "keywords": ["cognitive map", "navigation"],
                    "anchor_titles": ["map scale"],
                    "summary": "Map-scale planning work.",
                },
                {
                    "thread_key": "session:dream",
                    "title": "Dream public workload",
                    "project_label": "Dream",
                    "updated_at": "2026-03-20T00:00:00Z",
                    "keywords": ["Dream", "coding decision"],
                    "anchor_titles": ["coding shadow"],
                    "summary": "Dream workload planning.",
                },
                {
                    "thread_key": "session:quiet",
                    "title": "Quiet registry-only note",
                    "project_label": "Private Notes",
                    "updated_at": "2026-04-05T00:00:00Z",
                    "keywords": ["background"],
                    "anchor_titles": ["unrouted note"],
                },
            ],
        }
        findings = [
            {
                "kind": "aippocampus_subconscious_job_finding",
                "job": "cognitive_map",
                "finding_kind": "cognitive_map_route",
                "title": "Cognitive map scale",
                "summary": "Use far and near map scales without treating overview as source truth.",
                "confidence": 0.91,
                "landmarks": ["map scale", "source reopen"],
                "regions": ["memory architecture"],
                "route_cues": ["cognitive map", "far view"],
                "target_thread_keys": ["session:map"],
                "source_refs": [
                    {
                        "thread_key": "session:map",
                        "title": "AIppocampus cognitive map",
                        "project_label": "AIppocampus",
                        "line": 9,
                    }
                ],
                "source": "deepseek_subconscious_jobs",
            },
            {
                "kind": "aippocampus_subconscious_job_finding",
                "job": "cognitive_map",
                "finding_kind": "cognitive_map_route",
                "title": "Dream coding shadow",
                "summary": "Use Dream coding traces to avoid repeated rejected routes.",
                "confidence": 0.86,
                "landmarks": ["coding shadow", "Dream workload"],
                "regions": ["dream quality"],
                "route_cues": ["Dream", "coding decision"],
                "target_thread_keys": ["session:dream"],
                "source_refs": [
                    {
                        "thread_key": "session:dream",
                        "title": "Dream public workload",
                        "project_label": "Dream",
                        "line": 11,
                    }
                ],
                "source": "deepseek_subconscious_jobs",
            },
        ]
        return cognitive_map.build_cognitive_map(registry=registry, job_findings=findings)

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
        self.assertEqual(result["status"], "needs_subconscious_with_registry_overview")
        self.assertEqual(result["registry_overview_count"], 1)

    def test_empty_registry_still_needs_subconscious_without_overview(self) -> None:
        result = cognitive_map.build_cognitive_map(
            registry={"schema_version": 1, "threads": []}, job_findings=[]
        )

        self.assertEqual(result["route_count"], 0)
        self.assertEqual(result["registry_overview_count"], 0)
        self.assertEqual(result["status"], "needs_subconscious")

    def test_registry_alone_builds_cold_start_overview_without_routes(self) -> None:
        registry = {
            "schema_version": 1,
            "threads": [
                {
                    "thread_key": "session:map",
                    "title": "AIppocampus continuity map",
                    "project_label": "AIppocampus",
                    "updated_at": "2026-06-01T00:00:00Z",
                    "keywords": ["心理地图", "认知地图"],
                    "anchor_titles": ["外置海马体"],
                    "summary": "This registry summary is not evidence.",
                },
                {
                    "thread_key": "session:dream",
                    "title": "Dream publication",
                    "project_label": "AIppocampus",
                    "updated_at": "2026-06-02T00:00:00Z",
                    "keywords": ["Dream", "working memory"],
                    "anchor_titles": ["reader-safe publication"],
                },
            ],
        }

        result = cognitive_map.build_cognitive_map(registry=registry, job_findings=[])

        self.assertEqual(result["route_count"], 0)
        self.assertEqual(result["landmark_count"], 0)
        self.assertEqual(result["status"], "needs_subconscious_with_registry_overview")
        self.assertEqual(result["registry_overview"]["kind"], "cognitive_map_registry_overview")
        self.assertEqual(result["registry_overview"]["source"], "registry_metadata")
        self.assertEqual(result["registry_overview"]["cluster_count"], 1)
        cluster = result["registry_overview"]["clusters"][0]
        self.assertEqual(cluster["label"], "AIppocampus")
        self.assertEqual(cluster["thread_keys"], ["session:dream", "session:map"])
        self.assertIn("心理地图", cluster["navigation_terms"])
        self.assertIn("外置海马体", cluster["anchor_titles"])
        self.assertTrue(cluster["source_boundary"]["registry_derived_navigation_only"])
        self.assertTrue(cluster["source_boundary"]["not_source_backed_route"])
        self.assertTrue(cluster["source_boundary"]["source_reopen_required_for_claims"])

    def test_registry_overview_matches_only_as_weak_navigation(self) -> None:
        registry = {
            "schema_version": 1,
            "threads": [
                {
                    "thread_key": "session:map",
                    "title": "AIppocampus continuity map",
                    "project_label": "AIppocampus",
                    "keywords": ["心理地图", "认知地图"],
                    "anchor_titles": ["外置海马体"],
                }
            ],
        }
        result = cognitive_map.build_cognitive_map(registry=registry, job_findings=[])

        matches = cognitive_map.match_cognitive_map("继续 AIppocampus 心理地图", result)

        self.assertEqual(matches[0]["kind"], "cognitive_map_registry_overview")
        self.assertEqual(matches[0]["provenance_class"], "cognitive_map_registry_overview")
        self.assertEqual(matches[0]["source"], "registry_metadata")
        self.assertEqual(matches[0]["source_refs"], [])
        self.assertEqual(matches[0]["thread_keys"], ["session:map"])
        self.assertTrue(matches[0]["source_boundary"]["registry_derived_navigation_only"])
        self.assertTrue(matches[0]["source_boundary"]["source_reopen_required_for_claims"])

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

    def test_query_cognitive_map_near_mode_preserves_route_packets(self) -> None:
        result = self.build_multi_scale_fixture()

        packet = cognitive_map.query_cognitive_map(
            "continue the cognitive map far view work",
            result,
            scale="near",
        )

        self.assertEqual(packet["scale"], "near")
        self.assertEqual(packet["matches"][0]["route_kind"], "association")
        self.assertEqual(packet["matches"][0]["thread_keys"], ["session:map"])
        self.assertEqual(
            packet["matches"][0]["source_refs"][0]["thread_key"],
            "session:map",
        )
        self.assertEqual(packet["coverage"]["route_count"], 2)
        self.assertTrue(packet["diagnostics"]["source_reopen_required_for_claims"])

    def test_query_cognitive_map_mid_mode_groups_regions_and_landmarks(self) -> None:
        result = self.build_multi_scale_fixture()

        packet = cognitive_map.query_cognitive_map("Dream coding decision work", result, scale="mid")

        self.assertEqual(packet["scale"], "mid")
        self.assertEqual(packet["regions"][0]["label"], "dream quality")
        self.assertIn("coding shadow", packet["regions"][0]["landmark_labels"])
        self.assertEqual(packet["regions"][0]["representative_threads"], ["session:dream"])
        self.assertEqual(packet["coverage"]["matched_region_count"], 1)
        self.assertTrue(packet["diagnostics"]["map_summary_is_navigation_only"])

    def test_query_cognitive_map_far_mode_returns_theme_project_time_overview(self) -> None:
        result = self.build_multi_scale_fixture()

        packet = cognitive_map.query_cognitive_map(
            "what directions did I spend time on over the last six months?",
            result,
            scale="far",
        )

        self.assertEqual(packet["scale"], "far")
        self.assertGreaterEqual(packet["coverage"]["episode_count"], 3)
        self.assertEqual(packet["coverage"]["route_count"], 2)
        self.assertIn("AIppocampus", packet["project_distribution"])
        self.assertIn("2026-03", packet["time_distribution"])
        self.assertIn("memory architecture", [theme["label"] for theme in packet["themes"]])
        self.assertIn("registry_only_episode_count", packet["coverage_gaps"])
        self.assertNotIn("source_refs", packet["themes"][0])
        self.assertTrue(packet["diagnostics"]["far_view_explicit_only"])

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
