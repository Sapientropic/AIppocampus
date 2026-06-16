from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.source import provenance_codebook as codebook  # noqa: E402

FIXTURE = (
    REPO_ROOT
    / "benchmark_corpus"
    / "sparse_provenance"
    / "public_clean_source_like_events.jsonl"
)


class SparseProvenanceCodebookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = codebook._load_jsonl(FIXTURE)
        self.codebook = codebook.build_codebook(self.rows)

    def test_builds_content_addressed_chunks_with_dedupe_and_manifest_hash(self) -> None:
        metrics = self.codebook["metrics"]
        first_entry = self.codebook["entries"][0]

        self.assertEqual(metrics["source_entry_count"], 8)
        self.assertEqual(metrics["unique_chunk_count"], 6)
        self.assertEqual(metrics["deduped_entry_count"], 2)
        self.assertGreater(metrics["dedupe_saved_bytes"], 0)
        self.assertLess(metrics["compression_ratio"], 1.0)
        self.assertTrue(self.codebook["manifest_hash"].startswith("manifest_"))
        self.assertEqual(
            first_entry["source_fingerprint_fields"],
            [
                "content_hash",
                "source_id",
                "privacy_partition",
                "policy_version",
                "lifecycle_state",
            ],
        )

    def test_lookup_returns_route_handles_and_reduces_scan_work(self) -> None:
        lookup = codebook.lookup_routes(self.codebook, "route chain calibration")
        encoded = json.dumps(lookup, ensure_ascii=False)

        self.assertGreaterEqual(len(lookup["routes"]), 1)
        self.assertLess(
            lookup["metrics"]["route_index_candidate_count"],
            lookup["metrics"]["naive_scan_entry_count"],
        )
        self.assertGreater(lookup["metrics"]["lookup_candidate_reduction"], 0)
        self.assertGreater(lookup["metrics"]["blocked_candidate_match_count"], 0)
        self.assertTrue(lookup["routes"][0]["route_handle"].startswith("spc:manifest_"))
        self.assertNotIn("recovered all three public", encoded)
        self.assertNotIn("Quarantined private", encoded)
        self.assertNotIn("Deleted no-recall", encoded)

    def test_rehydrates_selected_route_with_manifest_and_hash_proof(self) -> None:
        lookup = codebook.lookup_routes(self.codebook, "route chain topk2")
        hydrated = codebook.rehydrate_route(self.codebook, lookup["routes"][0]["route_handle"])

        self.assertEqual(hydrated["status"], "ok")
        self.assertIn("Route-chain calibration top-k2", hydrated["text"])
        proof = hydrated["proof"]
        self.assertEqual(proof["manifest_hash"], self.codebook["manifest_hash"])
        self.assertTrue(proof["reconstruction_hash_match"])
        self.assertEqual(proof["source_fingerprint"], lookup["routes"][0]["source_fingerprint"])

    def test_blocked_lifecycle_and_privacy_partitions_do_not_rehydrate_or_emit(self) -> None:
        deleted = next(
            entry
            for entry in self.codebook["entries"]
            if entry["lifecycle_state"] == "deleted_no_recall"
        )
        blocked = codebook.rehydrate_route(
            self.codebook,
            codebook.route_handle_for(self.codebook, deleted),
        )
        report = codebook.build_report(self.rows, query="route chain agent facade")

        self.assertEqual(blocked["status"], "blocked")
        self.assertNotIn("text", blocked)
        self.assertTrue(
            all(value == 0 for value in report["quality"]["red_lines"].values()),
            report["quality"]["red_lines"],
        )
        self.assertEqual(report["quality"]["metrics"]["wrong_source_reconstruction_count"], 0)

    def test_topology_preservation_check_keeps_route_relations_below_truth_layer(self) -> None:
        report = codebook.build_report(self.rows, query="route chain")
        topology = report["quality"]["topology_preservation_check"]
        route = report["lookup"]["routes"][0]

        self.assertEqual(topology["status"], "ok")
        self.assertIn("source_support_chain", topology["preserves"])
        self.assertIn("topology_hash", route["topology"])
        self.assertEqual(route["claim_permission"], "no_claim_before_reopen")

    def test_v1_source_object_store_persists_and_rehydrates_stable_span_ids(self) -> None:
        store = codebook.build_source_object_store(self.rows)
        first_span = next(span for span in store["spans"] if span["status"] == "verified_present")
        summary = codebook.source_object_store_summary(store)

        self.assertEqual(store["schema_version"], "source-objects-v1")
        self.assertEqual(store["metrics"]["source_object_count"], 8)
        self.assertEqual(store["metrics"]["chunk_count"], 6)
        self.assertFalse(summary["public_safe"]["raw_text_serialized"])
        self.assertNotIn("Route-chain calibration", json.dumps(summary, ensure_ascii=False))

        hydrated = codebook.rehydrate_source_span(store, first_span["span_id"])
        self.assertEqual(hydrated["status"], "ok")
        self.assertIn("Route-chain calibration", hydrated["text"])
        self.assertTrue(hydrated["proof"]["reconstruction_hash_match"])

        with tempfile.TemporaryDirectory() as tmp:
            persist = codebook.persist_source_object_store(store, Path(tmp))
            manifest = codebook.load_source_object_manifest(Path(tmp))
            persisted = codebook.rehydrate_persistent_source_span(Path(tmp), first_span["span_id"])

        self.assertEqual(persist["source_object_count"], 8)
        self.assertEqual(manifest["manifest_hash"], store["manifest_hash"])
        self.assertEqual(persisted["status"], "ok")
        self.assertFalse(persisted["proof"]["unrelated_source_objects_loaded"])
        self.assertEqual(persisted["text"], hydrated["text"])

    def test_compression_proof_report_is_fixture_local_and_hash_checked(self) -> None:
        store = codebook.build_source_object_store(self.rows)
        report = codebook.compression_proof_report(store)

        self.assertEqual(report["fixture_scope"], "public_safe_fixture_local_measurement")
        self.assertIn("portable_deflate", report["compression"])
        self.assertFalse(report["compression"]["portable_deflate"]["native_dependency_required"])
        self.assertLess(
            report["compression"]["baseline_dedupe"]["compression_ratio"],
            1.0,
        )
        self.assertEqual(report["proof_levels"]["bounded_span_rehydration"]["status"], "ok")
        self.assertTrue(report["proof_levels"]["bounded_span_rehydration"]["hash_match"])
        self.assertEqual(report["proof_levels"]["whole_tree_audit"]["status"], "verified_present")
        self.assertIn("gb_tb_readiness", report["cannot_claim"])

    def test_structured_trace_template_residual_fixture_masks_sentinels(self) -> None:
        report = codebook.structured_trace_template_residual_report()
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["fixture_scope"], "public_safe_structured_trace_fixture")
        self.assertLess(
            report["template_residual"]["template_count"],
            report["template_residual"]["residual_chunk_count"],
        )
        self.assertGreater(report["template_residual"]["masked_slot_count"], 0)
        self.assertIn("baseline_dedupe_unique_bytes", report["comparison"])
        self.assertIn("portable_deflate_bytes", report["comparison"])
        self.assertEqual(report["proof_levels"]["bounded_rehydration"]["status"], "ok")
        self.assertTrue(report["proof_levels"]["bounded_rehydration"]["masked_slots_stay_masked"])
        self.assertGreater(report["red_lines"]["sentinel_input_count"], 0)
        self.assertEqual(report["red_lines"]["sentinel_public_leak_count"], 0)
        for sentinel in codebook.STRUCTURED_TRACE_SENTINELS:
            self.assertNotIn(sentinel, encoded)

    def test_source_fingerprint_reuse_verifier_rejects_stale_or_policy_mismatch(self) -> None:
        store = codebook.build_source_object_store(self.rows)
        current = next(
            item
            for item in store["source_objects"]
            if item["lifecycle_state"] == "current"
        )
        cached = {
            "source_fingerprint_payload": {
                **current["source_fingerprint_payload"],
                "policy_version": "old-policy",
            },
            "feedback_state": "agent_thumbs_up",
        }
        accepted = codebook.verify_source_fingerprint_reuse(current, current)
        rejected = codebook.verify_source_fingerprint_reuse(cached, current)
        blocked_current = next(
            item
            for item in store["source_objects"]
            if item["lifecycle_state"] == "deleted_no_recall"
        )
        blocked = codebook.verify_source_fingerprint_reuse(blocked_current, blocked_current)

        self.assertEqual(accepted["decision"], "accept_navigation_reuse")
        self.assertEqual(accepted["external_model_calls"], 0)
        self.assertEqual(rejected["decision"], "reject_cached_reuse")
        self.assertIn("policy_version_mismatch", rejected["reason_codes"])
        self.assertEqual(rejected["feedback_state"]["authority"], "unverified_agent_report")
        self.assertEqual(blocked["status"], "verified_present_but_blocked")
        self.assertIn("privacy_or_lifecycle_blocked", blocked["reason_codes"])
        self.assertEqual(blocked["red_line_counters"]["fingerprint_rejected_reuse"], 1)

    def test_durable_working_conclusions_and_pathlets_degrade_from_source_state(self) -> None:
        store = codebook.build_source_object_store(self.rows)
        allowed_span = next(span for span in store["spans"] if span["status"] == "verified_present")
        blocked_span = next(
            span for span in store["spans"] if span["status"] == "verified_present_but_blocked"
        )
        graph = codebook.build_durable_object_graph(
            store,
            conclusions=[
                {
                    "conclusion_id": "dwc-current",
                    "source_span_ids": [allowed_span["span_id"]],
                    "claim_classes": ["workflow_guidance"],
                    "cannot_claim": ["source_truth_without_reopen"],
                    "reopen_plan": [allowed_span["span_id"]],
                    "current_head": True,
                },
                {
                    "conclusion_id": "dwc-blocked",
                    "source_span_ids": [blocked_span["span_id"]],
                    "depends_on_conclusion_ids": ["dwc-current"],
                },
            ],
            pathlets=[
                {
                    "pathlet_id": "pathlet-blocked-edge",
                    "conclusion_ids": ["dwc-blocked"],
                    "edge_kind": "supersession",
                }
            ],
        )
        cycle = codebook.build_durable_object_graph(
            store,
            conclusions=[
                {"conclusion_id": "a", "depends_on_conclusion_ids": ["b"]},
                {"conclusion_id": "b", "depends_on_conclusion_ids": ["a"]},
            ],
            pathlets=[],
        )

        self.assertTrue(graph["ok"])
        statuses = {
            item["conclusion_id"]: item["status"]
            for item in graph["durable_working_conclusions"]
        }
        self.assertEqual(statuses["dwc-current"], "verified_present")
        self.assertEqual(statuses["dwc-blocked"], "verified_present_but_blocked")
        self.assertEqual(
            graph["object_families"]["durable_working_conclusions"]["current_head_ids"],
            ["dwc-current"],
        )
        self.assertTrue(
            graph["pathlets_and_edges"][0]["crosses_privacy_or_lifecycle_boundary"]
        )
        self.assertFalse(cycle["ok"])
        self.assertEqual(cycle["error"]["code"], "cyclic_durable_working_conclusion_graph")

    def test_codebook_health_projection_emits_four_public_safe_statuses(self) -> None:
        store = codebook.build_source_object_store(self.rows)
        allowed_span = next(span for span in store["spans"] if span["status"] == "verified_present")
        blocked_span = next(
            span for span in store["spans"] if span["status"] == "verified_present_but_blocked"
        )
        graph = codebook.build_durable_object_graph(
            store,
            conclusions=[
                {
                    "conclusion_id": "dwc-action",
                    "source_span_ids": [allowed_span["span_id"]],
                    "review": {
                        "action_required": True,
                        "who": "maintainer",
                        "why": "fixture freshness review",
                        "by_when": "2026-06-30",
                        "review_route": "fixture://quiet-room/dwc-action",
                    },
                },
                {"conclusion_id": "dwc-blocked", "source_span_ids": [blocked_span["span_id"]]},
                {"conclusion_id": "dwc-missing", "source_span_ids": ["span_missing"]},
            ],
            pathlets=[],
        )
        projection = codebook.codebook_health_projection(store, graph)
        encoded = json.dumps(projection, ensure_ascii=False)

        for status in codebook.CODEBOOK_HEALTH_STATUSES:
            self.assertIn(status, projection["status_counts"])
        self.assertGreater(projection["status_counts"]["verified_present"], 0)
        self.assertGreater(projection["status_counts"]["verified_present_but_blocked"], 0)
        self.assertGreater(projection["status_counts"]["cannot_verify"], 0)
        self.assertGreater(
            projection["status_counts"]["verified_present_with_action_required"],
            0,
        )
        quiet_item = projection["quiet_room"]["queue"][0]
        self.assertEqual(quiet_item["who"], "maintainer")
        self.assertEqual(quiet_item["by_when"], "2026-06-30")
        self.assertTrue(projection["boundary"]["campus_is_inspection_not_source_authority"])
        self.assertNotIn("Quarantined private", encoded)

    def test_adversarial_redline_fixture_uses_canonical_counters_and_negative_controls(self) -> None:
        report = codebook.adversarial_redline_report(self.rows)

        self.assertTrue(report["ok"])
        self.assertEqual(
            set(report["canonical_red_lines"]),
            {
                "privacy_bypass_count",
                "masked_source_resurrection_count",
                "source_backed_claim_without_reopen",
                "stale_as_current_count",
            },
        )
        self.assertTrue(all(value == 0 for value in report["canonical_red_lines"].values()))
        self.assertGreater(
            report["negative_controls"]["if_privacy_or_lifecycle_masks_disabled"][
                "privacy_bypass_count"
            ],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_source_reopen_gate_disabled"][
                "source_backed_claim_without_reopen"
            ],
            0,
        )
        self.assertIn("production_readiness", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
