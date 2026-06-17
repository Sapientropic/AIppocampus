from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import spend_doctor  # noqa: E402
from aippocampus_runtime.warm_ambient import recall as warm_recall  # noqa: E402

FAKE_PRIVATE_MARKER = "spend-doctor-private-marker"
FAKE_LOCAL_PATH = "C:\\Users\\Private\\AIppocampus\\source.txt"


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class SpendDoctorTests(unittest.TestCase):
    def test_spend_report_aggregates_cost_and_yield_without_private_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warm_dir = root / "ambient_warm_jobs"
            warm_dir.mkdir()
            (warm_dir / "warm_a.result.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_warm_ambient_recall_job_result",
                        "created_at": "2026-06-05T12:00:00Z",
                        "status": "suppressed",
                        "available": True,
                        "observed_scout_result_count": 50,
                        "accepted_scout_count": 25,
                        "card_count": 12,
                        "topic_epoch_action": "suppress",
                        "cache_write": {"status": "withheld", "card_count": 12},
                        "usage": {
                            "prompt_tokens": 1000,
                            "completion_tokens": 500,
                            "total_tokens": 1500,
                            "prompt_cache_hit_tokens": 800,
                            "prompt_cache_miss_tokens": 200,
                        },
                        "cache": {"available": True, "hit_tokens": 800, "miss_tokens": 200},
                        "elapsed_ms": 1200,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (warm_dir / "warm_nested.result.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_warm_ambient_recall_job_result",
                        "created_at": "2026-06-05T12:10:00Z",
                        "status": "written",
                        "available": True,
                        "observed_scout_result_count": 1,
                        "card_count": 1,
                        "cache_write": {"status": "written", "card_count": 1},
                        "result": {
                            "usage": {
                                "prompt_cache_hit_tokens": 60,
                                "prompt_cache_miss_tokens": 40,
                            },
                            "cache": {
                                "kind": "deepseek_prefix",
                                "hit_tokens": 60,
                                "miss_tokens": 40,
                            },
                            "latency_ms": 300,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            write_jsonl(
                root / "subconscious_jobs.jsonl",
                [
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "created_at": "2026-06-05T13:00:00Z",
                        "status": "staging",
                        "job": "concept_edges",
                        "finding_kind": "concept_edges",
                        "title": FAKE_PRIVATE_MARKER,
                        "summary": FAKE_LOCAL_PATH,
                        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
                    }
                ],
            )
            write_jsonl(
                root / "subconscious_edges.jsonl",
                [
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-06-05T13:05:00Z",
                        "status": "staging",
                        "src": "private-src",
                        "usage": {"total_tokens": 0},
                    }
                ],
            )
            write_jsonl(
                root / "dream_queue.jsonl",
                [
                    {
                        "kind": "aippocampus_dream_queue_item",
                        "created_at": "2026-06-05T14:25:00Z",
                        "status": "completed",
                        "worker_status": "candidate_emitted",
                        "dream_function": "compensatory",
                        "usage": {"prompt_cache_hit_tokens": 20, "prompt_cache_miss_tokens": 10},
                        "cache": {
                            "kind": "deepseek_prefix",
                            "available": True,
                            "hit_tokens": 20,
                            "miss_tokens": 10,
                        },
                        "latency_ms": 900,
                    }
                ],
            )
            write_jsonl(
                root / "working_memory.jsonl",
                [
                    {
                        "kind": "aippocampus_working_memory",
                        "created_at": "2026-06-05T14:00:00Z",
                        "source_candidate_batch_id": "subconscious-review-123",
                        "support_level": "evidence",
                        "route": "use_with_source",
                    },
                    {
                        "kind": "aippocampus_working_memory",
                        "created_at": "2026-06-05T14:30:00Z",
                        "candidate_type": "dream_hypothesis",
                        "adjudication_source": "background_dream_adjudication",
                        "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                        "route": "use_with_source",
                    }
                ],
            )
            (root / "aippocampus_prompt_hook_skip_telemetry.json").write_text(
                json.dumps(
                    {
                        "updated_at": "2026-06-05T14:10:00Z",
                        "skip_events": 2,
                        "skip_reason_counts": {"foreground_budget_skipped": 1, "cache_miss": 1},
                        "semantic_diagnostic_counts": {
                            "semantic_skipped_under_foreground_budget": 1
                        },
                        "warm_background_status_counts": {"scheduled": 1},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "aippocampus_prompt_hook_last_status.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_prompt_hook_audit_status",
                        "status": "found",
                        "last_prompt_hook": {
                            "timestamp": "2026-06-05T14:20:00Z",
                            "memory_surface": "candidate",
                            "card_count": 3,
                            "source_backed_count": 0,
                            "candidate_count": 3,
                            "scent_count": 0,
                            "warm_background": {"status": "scheduled", "spawned": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = spend_doctor.build_spend_doctor_report(
                registry_dir=root,
                days=7,
                now="2026-06-06T12:00:00Z",
                warn_effective_tokens=1000,
                warn_min_foreground_value_rate=0.25,
            )

        warm = report["routes"]["warm_ambient"]
        subconscious = report["routes"]["subconscious"]
        dream = report["routes"]["dream"]
        semantic = report["routes"]["semantic_gate"]
        prompt_hook = report["routes"]["prompt_hook"]

        self.assertFalse(report["privacy_boundary"]["raw_prompts_included"])
        self.assertFalse(report["privacy_boundary"]["raw_source_text_included"])
        self.assertFalse(report["privacy_boundary"]["local_paths_included"])
        self.assertEqual(warm["spend"]["effective_tokens"], 1600)
        self.assertEqual(warm["yield"]["generated_candidates"], 13)
        self.assertEqual(warm["yield"]["suppressed_candidates"], 12)
        self.assertEqual(warm["yield"]["foreground_cards"], 0)
        self.assertTrue(warm["model_telemetry"]["usage_available"])
        self.assertEqual(warm["model_telemetry"]["cache_metrics_kind"], "deepseek_prefix")
        self.assertEqual(warm["model_telemetry"]["prompt_cache_hit_tokens"], 860)
        self.assertEqual(warm["model_telemetry"]["prompt_cache_miss_tokens"], 240)
        self.assertEqual(warm["model_telemetry"]["prompt_cache_hit_rate"], 0.7818)
        self.assertEqual(warm["model_telemetry"]["latency_ms"]["count"], 2)
        self.assertEqual(warm["model_telemetry"]["latency_ms"]["average"], 750.0)
        self.assertEqual(subconscious["spend"]["effective_tokens"], 70)
        self.assertEqual(subconscious["yield"]["staging_rows"], 2)
        self.assertEqual(subconscious["yield"]["materialized_rows"], 1)
        self.assertEqual(dream["spend"]["effective_tokens"], 30)
        self.assertEqual(dream["yield"]["materialized_rows"], 1)
        self.assertTrue(dream["model_telemetry"]["usage_available"])
        self.assertEqual(dream["model_telemetry"]["cache_metrics_kind"], "deepseek_prefix")
        self.assertEqual(dream["model_telemetry"]["prompt_cache_hit_tokens"], 20)
        self.assertEqual(dream["model_telemetry"]["prompt_cache_miss_tokens"], 10)
        self.assertEqual(dream["model_telemetry"]["prompt_cache_hit_rate"], 0.6667)
        self.assertEqual(semantic["yield"]["skip_events"], 2)
        self.assertEqual(prompt_hook["yield"]["foreground_cards"], 3)
        self.assertIn("low_yield_high_spend:warm_ambient", report["warning_codes"])
        self.assertIn("warm_ambient", report["budget_guardrails"]["routes_to_pause_or_inspect"])
        self.assertEqual(report["decision"]["action"], "inspect")
        self.assertEqual(report["decision"]["highest_spend_route"]["route"], "warm_ambient")
        self.assertEqual(report["decision"]["lowest_yield_route"]["route"], "warm_ambient")
        self.assertFalse(report["decision"]["estimated_cost_supported"])
        self.assertEqual(
            report["decision"]["safe_next_command"],
            "aippocampus doctor spend --detail full --json",
        )
        rendered = spend_doctor.render_text(report)
        self.assertIn("Decision: inspect", rendered)
        self.assertIn("Highest spend: warm_ambient", rendered)
        self.assertIn("Cost: token volume only", rendered)
        self.assertIn("Next: aippocampus doctor spend --detail full --json", rendered)
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(FAKE_PRIVATE_MARKER, encoded)
        self.assertNotIn(FAKE_LOCAL_PATH, encoded)
        self.assertNotIn(str(root), encoded)

    def test_spend_report_marks_legacy_model_artifacts_without_fabricating_usage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(
                root / "dream_queue.jsonl",
                [
                    {
                        "kind": "aippocampus_dream_queue_item",
                        "created_at": "2026-06-05T14:25:00Z",
                        "status": "completed",
                        "worker_status": "candidate_emitted",
                        "dream_function": "compensatory",
                    }
                ],
            )

            report = spend_doctor.build_spend_doctor_report(
                registry_dir=root,
                days=7,
                now="2026-06-06T12:00:00Z",
            )

        telemetry = report["routes"]["dream"]["model_telemetry"]
        self.assertFalse(telemetry["usage_available"])
        self.assertEqual(telemetry["usage_missing_reason"], "artifact_legacy_no_usage")
        self.assertEqual(report["decision"]["action"], "inspect_usage")
        self.assertEqual(
            telemetry["usage_missing_reason_counts"],
            {"artifact_legacy_no_usage": 1},
        )
        self.assertEqual(telemetry["prompt_cache_hit_tokens"], 0)
        self.assertEqual(telemetry["prompt_cache_miss_tokens"], 0)

    def test_foreground_value_rate_is_normalized_and_ratio_keeps_over_one_meaning(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aippocampus_prompt_hook_last_status.json").write_text(
                json.dumps(
                    {
                        "last_prompt_hook": {
                            "timestamp": "2026-06-05T14:20:00Z",
                            "memory_surface": "candidate",
                            "card_count": 4,
                            "source_backed_count": 0,
                            "candidate_count": 2,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = spend_doctor.build_spend_doctor_report(
                registry_dir=root,
                days=7,
                now="2026-06-06T12:00:00Z",
            )

        prompt_hook = report["routes"]["prompt_hook"]["yield"]

        self.assertEqual(prompt_hook["foreground_value_ratio"], 2.0)
        self.assertEqual(prompt_hook["foreground_value_rate"], 1.0)
        self.assertIn("metric_notes", prompt_hook)
        self.assertIn("foreground_value_ratio", prompt_hook["metric_notes"][0])

    def test_warm_job_result_summary_persists_public_usage_for_future_spend_reports(self) -> None:
        summary = warm_recall.warm_job_result_summary(
            {"job_id": "warm_1", "prompt_hash": "hash_1"},
            {
                "ok": True,
                "available": True,
                "status": "written",
                "scout_count": 1,
                "scouts": [],
                "cards": [{"theme": FAKE_PRIVATE_MARKER, "source_refs": [{"path": FAKE_LOCAL_PATH}]}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                    "prompt_cache_hit_tokens": 6,
                    "prompt_cache_miss_tokens": 4,
                },
                "cache": {"available": True, "hit_tokens": 6, "miss_tokens": 4},
            },
        )

        self.assertEqual(summary["usage"]["total_tokens"], 14)
        self.assertEqual(summary["usage"]["prompt_cache_hit_tokens"], 6)
        encoded = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn(FAKE_PRIVATE_MARKER, encoded)
        self.assertNotIn(FAKE_LOCAL_PATH, encoded)

    def test_cli_doctor_spend_runs_via_public_facade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aippocampus_prompt_hook_skip_telemetry.json").write_text(
                json.dumps({"updated_at": "2026-06-05T14:10:00Z", "skip_events": 1}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "doctor",
                    "spend",
                    "--registry-dir",
                    str(root),
                    "--days",
                    "7",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_spend_doctor_card")
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["surface"], "foreground_decision_card")
        self.assertNotIn("routes", payload)
        self.assertNotIn("budget_guardrails", payload)
        self.assertNotIn("cannot_claim", payload)
        self.assertEqual(
            payload["claim_boundary"]["can_use_for"],
            "foreground spend/navigation decision",
        )
        self.assertIn("decision", payload)
        self.assertNotIn(str(root), proc.stdout)

    def test_default_compact_json_warns_with_inspect_action_without_self_looping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warm_dir = root / "ambient_warm_jobs"
            warm_dir.mkdir()
            (warm_dir / "warm_a.result.json").write_text(
                json.dumps(
                    {
                        "status": "suppressed",
                        "observed_scout_result_count": 5,
                        "card_count": 5,
                        "usage": {"total_tokens": 1500},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "doctor",
                    "spend",
                    "--registry-dir",
                    str(root),
                    "--warning-effective-tokens",
                    "1000",
                    "--warning-min-foreground-value-rate",
                    "0.25",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["decision"]["action"], "inspect")
        self.assertEqual(
            payload["decision"]["safe_next_command"],
            "aippocampus doctor spend --detail full --json",
        )
        self.assertEqual(payload["foreground_action"]["action_id"], "inspect_spend_route")
        self.assertEqual(payload["foreground_action"]["route"], "warm_ambient")
        self.assertIn("warm_ambient", payload["routes_to_pause_or_inspect"])
        self.assertNotEqual(payload["decision"]["safe_next_command"], "aippocampus doctor spend --json")
        self.assertLess(len(proc.stdout.encode("utf-8")), 5000)

    def test_blocked_warm_queue_becomes_spend_inspect_action_even_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            warm_dir = root / "ambient_warm_jobs"
            warm_dir.mkdir()
            (warm_dir / "warm_stale.json").write_text(
                json.dumps({"created_at": "2026-06-05T12:00:00Z"}),
                encoding="utf-8",
            )
            stale_mtime = 1780660800
            (warm_dir / "warm_stale.json").touch()
            os.utime(warm_dir / "warm_stale.json", (stale_mtime, stale_mtime))
            (warm_dir / "warm_a.result.json").write_text(
                json.dumps(
                    {
                        "status": "written",
                        "observed_scout_result_count": 5,
                        "card_count": 5,
                        "cache_write": {"status": "written", "card_count": 5},
                        "usage": {"total_tokens": 900},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = spend_doctor.build_spend_doctor_report(
                registry_dir=root,
                now="2026-06-07T12:00:00Z",
                warn_effective_tokens=999999,
                warn_min_foreground_value_rate=0.0,
            )
            card = spend_doctor.compact_spend_doctor_card(report)

        self.assertEqual(report["status"], "warning")
        self.assertIn("blocked_warm_queue:warm_ambient", report["warning_codes"])
        self.assertEqual(report["decision"]["action"], "inspect")
        self.assertIn("blocked stale queue", report["decision"]["reason"])
        self.assertIn("warm_ambient", report["decision"]["routes_to_pause_or_inspect"])
        self.assertEqual(report["decision"]["warm_queue_health"]["queue_state"], "blocked_stale_pending")
        self.assertEqual(card["foreground_action"]["action_id"], "inspect_warm_ambient_queue")
        self.assertEqual(card["foreground_action"]["command"], "aippocampus warm status --json")
        self.assertEqual(card["decision"]["warm_queue_health"]["pending_stale_count"], 1)

    def test_explicit_full_spend_json_keeps_operator_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aippocampus_prompt_hook_skip_telemetry.json").write_text(
                json.dumps({"updated_at": "2026-06-05T14:10:00Z", "skip_events": 1}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "doctor",
                    "spend",
                    "--registry-dir",
                    str(root),
                    "--detail",
                    "full",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_spend_doctor")
        self.assertIn("routes", payload)
        self.assertIn("model_telemetry", payload["routes"]["semantic_gate"])

    def test_operator_json_alias_keeps_full_spend_telemetry_without_json_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "doctor",
                    "spend",
                    "--registry-dir",
                    str(root),
                    "--operator-json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_spend_doctor")
        self.assertIn("routes", payload)


if __name__ == "__main__":
    unittest.main()
