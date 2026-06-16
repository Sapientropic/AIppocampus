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
from aippocampus_runtime.source import provenance_codebook_economics as economics  # noqa: E402

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

    def test_source_family_economics_report_splits_families_without_raw_text(self) -> None:
        generated_rows = [
            {
                "source_id": "generated-report-1",
                "text": "benchmark generated report shows workflow candidate route pressure",
                "privacy_partition": "public",
                "policy_version": "policy-v1",
                "lifecycle_state": "current",
                "source_family": "generated_report",
            }
        ]
        mixed_rows = [
            {
                "source_id": "mixed-agent-1",
                "text": "mixed long agent bundle with correction pathlet and environment workaround",
                "privacy_partition": "public",
                "policy_version": "policy-v1",
                "lifecycle_state": "current",
                "source_family": "mixed_agent_bundle",
            }
        ]

        report = economics.source_family_economics_report(
            [
                {"family_id": "natural-clean-source", "rows": self.rows},
                {
                    "family_id": "structured-tool-traces",
                    "rows": codebook.structured_trace_fixture_rows(),
                },
                {"family_id": "generated-reports", "rows": generated_rows},
                {"family_id": "mixed-long-agent-bundle", "rows": mixed_rows},
            ]
        )
        encoded = json.dumps(report, ensure_ascii=False)
        by_family = {item["family_id"]: item for item in report["by_source_family"]}

        self.assertTrue(report["read_only"])
        self.assertEqual(report["family_count"], 4)
        self.assertIn("natural-clean-source", by_family)
        for row in by_family.values():
            for field in (
                "raw_bytes",
                "encoded_store_bytes",
                "build_time_ms",
                "lookup_latency_ms",
                "lookup_candidate_reduction",
                "template_count",
                "residual_bytes",
                "rehydration_latency_ms",
                "rehydration_hash_correct",
                "ordinary_compression",
                "supports",
                "material_limits",
                "evidence_candidate_usefulness",
            ):
                self.assertIn(field, row)
        self.assertIn("gb_tb_readiness", report["cannot_claim"])
        self.assertFalse(report["privacy_boundary"]["paths_included"])
        self.assertNotIn("Route-chain calibration top-k2", encoded)
        for sentinel in codebook.STRUCTURED_TRACE_SENTINELS:
            self.assertNotIn(sentinel, encoded)

    def test_source_family_economics_report_includes_codec_matrix_and_storage_gate(self) -> None:
        report = economics.source_family_economics_report(
            [
                {"family_id": "natural-clean-source", "rows": self.rows},
                {
                    "family_id": "structured-tool-traces",
                    "rows": codebook.structured_trace_fixture_rows(),
                },
            ]
        )
        encoded = json.dumps(report, ensure_ascii=False)
        structured = {
            item["family_id"]: item for item in report["by_source_family"]
        }["structured-tool-traces"]
        matrix = structured["codec_matrix"]

        self.assertIn("baseline_content_addressed_dedupe", matrix)
        self.assertIn("portable_deflate", matrix)
        self.assertIn("zstd_no_dictionary", matrix)
        self.assertIn("zstd_dictionary", matrix)
        self.assertIn("template_residual", matrix)
        self.assertIn(matrix["zstd_no_dictionary"]["status"], {"available", "skipped"})
        self.assertIn(matrix["zstd_dictionary"]["status"], {"available", "skipped"})
        self.assertFalse(matrix["zstd_dictionary"]["raw_dictionary_bytes_serialized"])
        self.assertEqual(matrix["zstd_dictionary"]["training_privacy_partition"], "public")
        self.assertEqual(matrix["template_residual"]["status"], "available")
        self.assertIn("storage_primitive_decision_gate", report)
        self.assertEqual(
            report["storage_primitive_decision_gate"]["cdc"]["decision"],
            "defer",
        )
        self.assertEqual(
            report["storage_primitive_decision_gate"]["lmdb"]["decision"],
            "defer",
        )
        self.assertIn("reopen_thresholds", report["storage_primitive_decision_gate"]["cdc"])
        for sentinel in codebook.STRUCTURED_TRACE_SENTINELS:
            self.assertNotIn(sentinel, encoded)

    def test_compression_artifact_contract_blocks_cross_partition_reuse(self) -> None:
        contract = codebook.compression_artifact_contract_report()
        fields = set(contract["required_metadata_fields"])

        self.assertTrue(set(codebook.COMPRESSION_FINGERPRINT_FIELDS).issubset(fields))
        self.assertIn("dictionary_privacy_partition", fields)
        self.assertIn("source_family", fields)
        self.assertIn("public_projection_allowlist", contract)
        self.assertNotIn("raw_dictionary_bytes", contract["public_projection_allowlist"])

        trace = codebook.structured_trace_template_residual_report()
        current = trace["public_projection"]["residuals"][0]
        payload = current["source_fingerprint_payload"]
        self.assertIn("dictionary_privacy_partition", payload)
        rejected = codebook.verify_source_fingerprint_reuse(
            {
                "source_fingerprint_payload": {
                    **payload,
                    "dictionary_privacy_partition": "private-local",
                }
            },
            current,
        )

        self.assertEqual(rejected["decision"], "reject_cached_reuse")
        self.assertIn("dictionary_privacy_partition_mismatch", rejected["reason_codes"])

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

    def test_compression_aware_fingerprint_verifier_rejects_policy_mismatches(self) -> None:
        trace = codebook.structured_trace_template_residual_report()
        current = trace["public_projection"]["residuals"][0]
        payload = current["source_fingerprint_payload"]
        cases = {
            "template_id": "template_id_mismatch",
            "schema_version": "schema_version_mismatch",
            "redaction_policy_version": "redaction_policy_version_mismatch",
            "mask_policy_version": "mask_policy_version_mismatch",
            "visibility_scope": "visibility_scope_mismatch",
            "codec_id": "codec_id_mismatch",
            "codec_version": "codec_version_mismatch",
            "dictionary_id": "dictionary_id_mismatch",
            "dictionary_training_scope": "dictionary_training_scope_mismatch",
            "dictionary_privacy_partition": "dictionary_privacy_partition_mismatch",
            "dictionary_redaction_policy_version": "dictionary_redaction_policy_version_mismatch",
            "source_family": "source_family_mismatch",
        }

        self.assertTrue(
            set(codebook.COMPRESSION_FINGERPRINT_FIELDS).issubset(set(payload))
        )
        for field, reason in cases.items():
            with self.subTest(field=field):
                cached = {"source_fingerprint_payload": {**payload, field: "old-value"}}
                rejected = codebook.verify_source_fingerprint_reuse(cached, current)

                self.assertEqual(rejected["decision"], "reject_cached_reuse")
                self.assertIn(reason, rejected["reason_codes"])
                self.assertEqual(rejected["external_model_calls"], 0)
                self.assertEqual(
                    rejected["red_line_counters"]["fingerprint_rejected_reuse"],
                    1,
                )

        missing = codebook.verify_source_fingerprint_reuse(
            {
                "source_fingerprint_payload": {
                    key: value for key, value in payload.items() if key != "residual_policy_id"
                }
            },
            current,
        )
        self.assertIn("missing_residual_policy_id", missing["reason_codes"])

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
                    "ordering_authority": "clean_source_turn_order",
                    "ordered_source_refs": [{"turn_index": 1}, {"turn_index": 2}],
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
        self.assertEqual(
            graph["pathlets_and_edges"][0]["ordering_status"],
            "source_backed_order",
        )
        self.assertFalse(cycle["ok"])
        self.assertEqual(cycle["error"]["code"], "cyclic_durable_working_conclusion_graph")

    def test_pathlets_with_ambiguous_or_model_ordering_degrade_to_cannot_verify(self) -> None:
        store = codebook.build_source_object_store(self.rows)
        allowed_span = next(span for span in store["spans"] if span["status"] == "verified_present")
        graph = codebook.build_durable_object_graph(
            store,
            conclusions=[
                {"conclusion_id": "dwc-current", "source_span_ids": [allowed_span["span_id"]]},
            ],
            pathlets=[
                {
                    "pathlet_id": "pathlet-model-order",
                    "conclusion_ids": ["dwc-current"],
                    "edge_kind": "correction",
                    "ordering_authority": "model_generated",
                    "ordered_source_refs": [{"turn_index": 1}, {"turn_index": 2}],
                },
                {
                    "pathlet_id": "pathlet-wrong-order",
                    "conclusion_ids": ["dwc-current"],
                    "edge_kind": "supersession",
                    "ordering_authority": "clean_source_turn_order",
                    "ordered_source_refs": [{"turn_index": 3}, {"turn_index": 2}],
                },
            ],
        )
        by_id = {item["pathlet_id"]: item for item in graph["pathlets_and_edges"]}

        self.assertEqual(by_id["pathlet-model-order"]["status"], "cannot_verify")
        self.assertIn(
            "ordering_authority_not_source_backed",
            by_id["pathlet-model-order"]["reason_codes"],
        )
        self.assertEqual(by_id["pathlet-wrong-order"]["status"], "cannot_verify")
        self.assertIn("ambiguous_or_wrong_order", by_id["pathlet-wrong-order"]["reason_codes"])
        self.assertIn("route back to source", by_id["pathlet-wrong-order"]["public_projection_note"])

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
            report["negative_controls"]["if_privacy_lifecycle_masks_disabled"][
                "canonical_red_lines"
            ]["privacy_bypass_count"],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_source_reopen_gate_disabled"][
                "canonical_red_lines"
            ]["source_backed_claim_without_reopen"],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_stale_current_filter_disabled"][
                "canonical_red_lines"
            ]["stale_as_current_count"],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_template_residual_redaction_disabled"][
                "canonical_red_lines"
            ]["masked_source_resurrection_count"],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_dictionary_trained_from_unredacted_samples"][
                "subtype_diagnostics"
            ]["dictionary_sensitive_training_sample_count"],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_cross_privacy_partition_dictionary_reuse"][
                "subtype_diagnostics"
            ]["cross_partition_dictionary_reuse_count"],
            0,
        )
        self.assertGreater(
            report["negative_controls"]["if_public_projection_serializes_sensitive_artifacts"][
                "canonical_red_lines"
            ]["masked_source_resurrection_count"],
            0,
        )
        for control in report["negative_controls"].values():
            self.assertTrue(control["observed_failure"])
        self.assertIn("production_readiness", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
