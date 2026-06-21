from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.subconscious import staging_archive, staging_maintenance


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

class SubconsciousStagingMaintenanceTests(unittest.TestCase):
    def test_dry_run_report_classifies_active_review_and_archive_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deterministic_id = "a" * 64
            edges_path = root / "subconscious_edges.jsonl"
            jobs_path = root / "subconscious_jobs.jsonl"
            promotion_path = root / "promotion_candidates.jsonl"
            write_jsonl(
                edges_path,
                [
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-06-02T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "sf_edge_active",
                        "src": "AIppocampus",
                        "dst": "source-backed continuity",
                        "edge_type": "related",
                        "confidence": 0.86,
                        "source_refs": [{"thread_key": "session:edge", "line": 10}],
                        "dream_refs": ["dream:edge"],
                        "question_refs": ["question:edge"],
                        "review_refs": ["review:edge"],
                        "audit_provenance": {"provider": "deepseek"},
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "staging",
                        "fingerprint": deterministic_id,
                        "src": "duplicate",
                        "dst": "old",
                        "edge_type": "related",
                        "confidence": 0.62,
                        "source_refs": [{"thread_key": "session:dup-old", "line": 20}],
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-06-01T00:00:00Z",
                        "status": "staging",
                        "fingerprint": deterministic_id,
                        "src": "duplicate",
                        "dst": "new",
                        "edge_type": "related",
                        "confidence": 0.84,
                        "source_refs": [{"thread_key": "session:dup-new", "line": 21}],
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "rejected",
                        "fingerprint": "sf_rejected",
                        "src": "noise",
                        "dst": "noise",
                        "edge_type": "related",
                        "confidence": 0.21,
                        "source_refs": [{"thread_key": "session:reject", "line": 30}],
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-05-01T00:00:00Z",
                        "status": "promoted",
                        "fingerprint": "sf_promoted",
                        "src": "accepted",
                        "dst": "materialized",
                        "edge_type": "related",
                        "confidence": 0.91,
                        "source_refs": [{"thread_key": "session:promoted", "line": 31}],
                    },
                ],
            )
            write_jsonl(
                jobs_path,
                [
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "sf_question",
                        "job": "question_extraction",
                        "finding_kind": "question_candidate",
                        "source_refs": [{"thread_key": "session:q", "line": 40}],
                        "question_refs": ["question:cluster"],
                    }
                ],
            )
            write_jsonl(
                promotion_path,
                [
                    {
                        "kind": "aippocampus_promotion_candidate",
                        "status": "staging",
                        "source_finding_ids": ["sf_question"],
                    }
                ],
            )

            report = staging_maintenance.analyze_staging_queues(
                root,
                now="2026-06-03T00:00:00Z",
                old_after_days=30,
                pressure_thresholds=staging_maintenance.StagingPressureThresholds(
                    max_rows=10,
                    max_bytes=100_000,
                ),
            )

        self.assertEqual(report["kind"], "aippocampus_subconscious_staging_maintenance_report")
        self.assertEqual(report["mode"], "dry_run")
        self.assertFalse(report["safety"]["destructive_changes"])
        self.assertTrue(report["safety"]["source_refs_preserved"])
        self.assertEqual(report["compatibility"]["legacy_sf_id_count"], 4)
        self.assertEqual(report["compatibility"]["sha256_hex_id_count"], 2)

        question = next(row for row in report["row_actions"] if row["stable_id"] == "sf_question")
        self.assertEqual(question["maintenance_state"], "review")
        self.assertIn("referenced_by_promotion_candidate", question["reasons"])
        self.assertEqual(question["preserved_reference_counts"]["source_refs"], 1)
        self.assertEqual(question["preserved_reference_counts"]["question_refs"], 1)

        rejected = next(row for row in report["row_actions"] if row["stable_id"] == "sf_rejected")
        self.assertEqual(rejected["maintenance_state"], "archive_candidate")
        self.assertIn("status_rejected", rejected["reasons"])

        promoted = next(row for row in report["row_actions"] if row["stable_id"] == "sf_promoted")
        self.assertEqual(promoted["maintenance_state"], "archive_candidate")
        self.assertIn("materialized_or_promoted", promoted["reasons"])

        duplicate_group = next(
            group for group in report["duplicate_groups"] if group["stable_id"] == "a" * 64
        )
        self.assertEqual(duplicate_group["kept_line"], 3)
        self.assertEqual(duplicate_group["archive_candidate_lines"], [2])

        queues = report["queues"]
        self.assertEqual(queues["subconscious_edges"]["archive_candidate_count"], 3)
        self.assertEqual(queues["subconscious_jobs"]["review_count"], 1)

    def test_pressure_report_warns_without_applying_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(
                root / "subconscious_jobs.jsonl",
                [
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "created_at": "2026-06-03T00:00:00Z",
                        "status": "staging",
                        "fingerprint": f"sf_{idx}",
                        "source_refs": [{"thread_key": "session:pressure", "line": idx}],
                    }
                    for idx in range(3)
                ],
            )

            report = staging_maintenance.analyze_staging_queues(
                root,
                now="2026-06-03T00:00:00Z",
                pressure_thresholds=staging_maintenance.StagingPressureThresholds(
                    max_rows=1,
                    max_bytes=1,
                ),
            )

        self.assertTrue(report["backpressure"]["warning"])
        self.assertIn("row_threshold_exceeded", report["backpressure"]["warning_reasons"])
        self.assertIn("byte_threshold_exceeded", report["backpressure"]["warning_reasons"])
        self.assertFalse(report["safety"]["destructive_changes"])

    def test_apply_archives_candidates_and_rewrites_active_queues_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edges_path = root / "subconscious_edges.jsonl"
            jobs_path = root / "subconscious_jobs.jsonl"
            write_jsonl(
                edges_path,
                [
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-06-02T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "sf_active",
                        "src": "active",
                        "dst": "source-backed",
                        "edge_type": "related",
                        "source_refs": [{"thread_key": "session:active", "line": 1}],
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "b" * 64,
                        "src": "duplicate",
                        "dst": "old",
                        "edge_type": "related",
                        "source_refs": [{"thread_key": "session:dup-old", "line": 2}],
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-06-01T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "b" * 64,
                        "src": "duplicate",
                        "dst": "new",
                        "edge_type": "related",
                        "source_refs": [{"thread_key": "session:dup-new", "line": 3}],
                    },
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "promoted",
                        "fingerprint": "sf_promoted",
                        "src": "accepted",
                        "dst": "materialized",
                        "edge_type": "related",
                        "source_refs": [{"thread_key": "session:promoted", "line": 4}],
                        "promotion_trace": [{"candidate_id": "pc_promoted"}],
                        "dream_refs": ["dream:promoted"],
                        "question_refs": ["question:promoted"],
                        "review_refs": ["review:promoted"],
                        "private_audit_provenance": {"route": "local-private"},
                    },
                ],
            )
            write_jsonl(
                jobs_path,
                [
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "rejected",
                        "fingerprint": "sf_rejected_job",
                        "source_refs": [{"thread_key": "session:job", "line": 5}],
                        "audit_provenance": {"provider": "deepseek"},
                    },
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "sf_referenced_job",
                        "source_refs": [{"thread_key": "session:referenced", "line": 6}],
                        "question_refs": ["question:referenced"],
                    },
                ],
            )
            write_jsonl(
                root / "promotion_candidates.jsonl",
                [
                    {
                        "kind": "aippocampus_promotion_candidate",
                        "status": "staging",
                        "source_finding_ids": ["sf_referenced_job"],
                    }
                ],
            )

            report = staging_archive.apply_staging_maintenance(
                root,
                now="2026-06-03T00:00:00Z",
                old_after_days=30,
            )

            self.assertEqual(report["mode"], "apply")
            self.assertTrue(report["safety"]["writes_enabled"])
            self.assertTrue(report["apply"]["manifest_verification"]["ok"])
            self.assertEqual(report["apply"]["archived_row_count"], 3)

            remaining_edge_ids = [staging_maintenance.stable_row_id(row) for row in staging_maintenance.iter_jsonl_rows(edges_path)]
            remaining_job_ids = [staging_maintenance.stable_row_id(row) for row in staging_maintenance.iter_jsonl_rows(jobs_path)]
            self.assertEqual(remaining_edge_ids, ["sf_active", "b" * 64])
            self.assertEqual(remaining_job_ids, ["sf_referenced_job"])

            manifest_path = Path(report["apply"]["manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "aippocampus_subconscious_staging_archive_manifest")
            self.assertEqual(manifest["archive_status"], "verified")
            self.assertEqual(manifest["archived_row_count"], 3)
            self.assertEqual(manifest["retained_row_count"], 3)
            promoted = next(row for row in manifest["rows"] if row["stable_id"] == "sf_promoted")
            self.assertEqual(promoted["preserved_reference_counts"]["promotion_trace"], 1)
            self.assertEqual(promoted["preserved_reference_counts"]["dream_refs"], 1)
            self.assertEqual(promoted["preserved_reference_counts"]["question_refs"], 1)
            self.assertEqual(promoted["preserved_reference_counts"]["review_refs"], 1)
            self.assertEqual(promoted["preserved_reference_counts"]["private_audit_provenance"], 1)

            archive_files = {item["queue"]: root / item["relative_path"] for item in manifest["archive_files"]}
            archived_edges = [
                staging_maintenance.stable_row_id(row)
                for row in staging_maintenance.iter_jsonl_rows(archive_files["subconscious_edges"])
            ]
            archived_jobs = [
                staging_maintenance.stable_row_id(row)
                for row in staging_maintenance.iter_jsonl_rows(archive_files["subconscious_jobs"])
            ]
            self.assertEqual(archived_edges, ["b" * 64, "sf_promoted"])
            self.assertEqual(archived_jobs, ["sf_rejected_job"])

    def test_archive_manifest_verification_detects_tampered_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(
                root / "subconscious_edges.jsonl",
                [
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-04-01T00:00:00Z",
                        "status": "rejected",
                        "fingerprint": "sf_rejected",
                        "src": "noise",
                        "dst": "noise",
                        "edge_type": "related",
                        "source_refs": [{"thread_key": "session:reject", "line": 7}],
                    }
                ],
            )

            report = staging_archive.apply_staging_maintenance(
                root,
                now="2026-06-03T00:00:00Z",
                old_after_days=30,
            )
            manifest_path = Path(report["apply"]["manifest_path"])
            self.assertTrue(staging_archive.verify_staging_archive_manifest(root, manifest_path)["ok"])

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            archive_path = root / manifest["archive_files"][0]["relative_path"]
            with archive_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({"fingerprint": "sf_intruder"}, ensure_ascii=False) + "\n")

            verification = staging_archive.verify_staging_archive_manifest(root, manifest_path)
            self.assertFalse(verification["ok"])
            self.assertIn("archive_file_hash_mismatch", verification["error_codes"])

    def test_apply_noops_when_no_archive_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edges_path = root / "subconscious_edges.jsonl"
            write_jsonl(
                edges_path,
                [
                    {
                        "kind": "aippocampus_subconscious_edge",
                        "created_at": "2026-06-02T00:00:00Z",
                        "status": "staging",
                        "fingerprint": "sf_active",
                        "src": "active",
                        "dst": "source-backed",
                        "edge_type": "related",
                        "source_refs": [{"thread_key": "session:active", "line": 1}],
                    }
                ],
            )

            report = staging_archive.apply_staging_maintenance(
                root,
                now="2026-06-03T00:00:00Z",
                old_after_days=30,
            )

            self.assertEqual(report["apply"]["queue_rewrite_status"], "skipped_no_archive_candidates")
            self.assertEqual(report["apply"]["archived_row_count"], 0)
            self.assertFalse((root / staging_maintenance.ARCHIVE_DIR_NAME).exists())
            remaining_ids = [
                staging_maintenance.stable_row_id(row)
                for row in staging_maintenance.iter_jsonl_rows(edges_path)
            ]
            self.assertEqual(remaining_ids, ["sf_active"])

if __name__ == "__main__":
    unittest.main()
