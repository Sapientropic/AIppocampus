from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import action_hint_cache as cache  # noqa: E402
from aippocampus_runtime.learning_loop.core import project_action_time_guidance  # noqa: E402
from aippocampus_runtime.learning_loop.effectiveness_ledger import (  # noqa: E402
    append_ledger_rows,
    ledger_rows_from_guidance_outcomes,
)
from aippocampus_runtime.reflection.aar_v2 import build_aar_v2_report  # noqa: E402


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"clean:{name}", "segment_id": f"msg-{name}"}


class ActionHintCacheTests(unittest.TestCase):
    def test_materializes_two_existing_provider_families(self) -> None:
        aar_report = build_aar_v2_report(
            [
                {
                    "kind": "source_backed_correction",
                    "review_status": "accepted",
                    "source_refs": [source_ref("aar")],
                    "action_class": "specific_memory_source_claim",
                    "summary": "Weak context produced a specific source claim.",
                }
            ]
        )
        learning_guidance = project_action_time_guidance(
            [
                {
                    "finding_id": "learn-preflight",
                    "workflow_family": "cheap_preflight_before_broad_test",
                    "status": "open",
                    "scope": "project:AIppocampus",
                    "occurrence_count": 2,
                    "confidence": "high",
                    "foreground_eligible": True,
                    "source_refs": [source_ref("learn")],
                }
            ],
            query_terms=["pytest", "test"],
        )

        report = cache.build_action_hint_cache_report(
            aar_v2_records=aar_report["candidate_records"],
            learning_guidance=learning_guidance,
            now_unix=1000,
        )

        self.assertEqual(report["kind"], cache.CACHE_KIND)
        self.assertEqual(report["record_count"], 2)
        self.assertEqual(report["provider_counts"]["aar_v2"], 1)
        self.assertEqual(report["provider_counts"]["learning_loop"], 1)
        for record in report["records"]:
            self.assertTrue(record["navigation_only"])
            self.assertTrue(record["no_claim_before_reopen"])
            self.assertTrue(record["source_reopen_required"])
            self.assertFalse(record["can_support_factual_claim"])

    def test_read_filters_pending_action_features_and_suppression_boundaries(self) -> None:
        report = cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight",
                    "next_action": "run_preflight_before_broad_test",
                    "guidance_text": "Run ruff before pytest.",
                    "source_refs": [source_ref("learn")],
                    "reason_codes": ["learning_guidance_surface"],
                }
            ],
            now_unix=1000,
        )
        features = {
            "terms": ["pytest", "test", "preflight"],
            "tool_names": ["Bash"],
            "command_terms": ["pytest", "test"],
            "path_terms": [],
            "issue_ids": [],
            "risk_modes": [],
            "active_recall_locks": [],
            "anti_nag_token_ids": [],
            "visible_source_refs": [],
        }

        matches = cache.read_action_hint_records(report, features, now_unix=1001)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["provider_family"], "learning_loop")

        stale = {**matches[0], "freshness": "stale"}
        private = {**matches[0], "freshness": "private"}
        expired = {**matches[0], "expires_at_unix": 999}
        low_one_off = {**matches[0], "confidence": "low", "occurrence_count": 1}
        visible = {**features, "visible_source_refs": [source_ref("learn")]}
        anti_nag = {**features, "anti_nag_token_ids": [matches[0]["record_id"]]}

        self.assertEqual(cache.read_action_hint_records([stale], features, now_unix=1001), [])
        self.assertEqual(cache.read_action_hint_records([private], features, now_unix=1001), [])
        self.assertEqual(cache.read_action_hint_records([expired], features, now_unix=1001), [])
        self.assertEqual(cache.read_action_hint_records([low_one_off], features, now_unix=1001), [])
        self.assertEqual(cache.read_action_hint_records([matches[0]], visible, now_unix=1001), [])
        self.assertEqual(cache.read_action_hint_records([matches[0]], anti_nag, now_unix=1001), [])

    def test_source_claim_action_matches_aar_v2_record_without_authority_upgrade(self) -> None:
        report = cache.build_action_hint_cache_report(
            aar_v2_records=[
                {
                    "record_id": "aar-record",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [source_ref("aar")],
                    "nudge": {"recommended_action": "reopen_source_before_specific_claim"},
                }
            ],
            now_unix=1000,
        )
        features = {
            "terms": ["memory", "claim"],
            "tool_names": [],
            "command_terms": [],
            "path_terms": [],
            "issue_ids": [],
            "risk_modes": [],
            "active_recall_locks": [],
            "anti_nag_token_ids": [],
            "visible_source_refs": [],
            "action_class": "specific_memory_source_claim",
            "support_level": "candidate",
        }

        matches = cache.read_action_hint_records(report, features, now_unix=1001)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["provider_family"], "aar_v2")
        self.assertEqual(matches[0]["authority"], "navigation_only")

    def test_project_specific_learning_guidance_requires_target_or_path_match(self) -> None:
        report = cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight-other-repo",
                    "next_action": "run_preflight_before_broad_test",
                    "guidance_text": "Run ruff before pytest.",
                    "scope": "project:OtherRepo",
                    "target_fingerprint": "other-repo:specific-target",
                    "path_category_fingerprint": "other-repo:tests/payments",
                    "workspace_or_environment_profile": "linux-ci",
                    "source_refs": [source_ref("learn")],
                    "reason_codes": ["learning_guidance_surface"],
                }
            ],
            now_unix=1000,
        )
        record = report["records"][0]
        base_features = {
            "terms": ["pytest", "test", "preflight"],
            "tool_names": ["Bash"],
            "command_terms": ["pytest", "test"],
            "path_terms": [],
            "issue_ids": [],
            "risk_modes": [],
            "active_recall_locks": [],
            "anti_nag_token_ids": [],
            "visible_source_refs": [],
        }

        self.assertEqual(record["scope"], "project:OtherRepo")
        self.assertEqual(record["target_fingerprint"], "other-repo:specific-target")
        self.assertEqual(record["path_category_fingerprint"], "other-repo:tests/payments")
        self.assertTrue(record["requires_applicability_match"])
        self.assertEqual(cache.read_action_hint_records(report, base_features, now_unix=1001), [])

        target_features = {
            **base_features,
            "target_fingerprint": "other-repo:specific-target",
        }
        path_features = {
            **base_features,
            "path_category_fingerprint": "other-repo:tests/payments",
        }

        self.assertEqual(
            cache.read_action_hint_records(report, target_features, now_unix=1001)[0]["next_action"],
            "run_preflight_before_broad_test",
        )
        self.assertEqual(len(cache.read_action_hint_records(report, path_features, now_unix=1001)), 1)

    def test_empty_target_and_path_features_do_not_match_specific_guidance(self) -> None:
        base_features = {
            "terms": ["pytest", "test", "preflight"],
            "tool_names": ["Bash"],
            "command_terms": ["pytest", "test"],
            "path_terms": [],
            "issue_ids": [],
            "risk_modes": [],
            "active_recall_locks": [],
            "anti_nag_token_ids": [],
            "visible_source_refs": [],
        }
        path_only = cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight-payments",
                    "next_action": "run_preflight_before_broad_test",
                    "scope": "project:OtherRepo",
                    "path_category_fingerprint": "other-repo:tests/payments",
                    "source_refs": [source_ref("learn")],
                }
            ],
            now_unix=1000,
        )
        target_only = cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight-target",
                    "next_action": "run_preflight_before_broad_test",
                    "scope": "project:OtherRepo",
                    "target_fingerprint": "other-repo:specific-target",
                    "source_refs": [source_ref("learn")],
                }
            ],
            now_unix=1000,
        )

        self.assertEqual(cache.read_action_hint_records(path_only, base_features, now_unix=1001), [])
        self.assertEqual(cache.read_action_hint_records(target_only, base_features, now_unix=1001), [])
        self.assertEqual(
            len(
                cache.read_action_hint_records(
                    path_only,
                    {**base_features, "path_category_fingerprint": "tests/payments"},
                    now_unix=1001,
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                cache.read_action_hint_records(
                    target_only,
                    {**base_features, "target_fingerprint": "other-repo:specific-target"},
                    now_unix=1001,
                )
            ),
            1,
        )

    def test_missing_providers_are_explicit_without_becoming_errors(self) -> None:
        report = cache.build_action_hint_cache_report(now_unix=1000)

        self.assertEqual(report["record_count"], 0)
        self.assertEqual(report["missing_provider_count"], 6)
        self.assertFalse(report["privacy_boundary"]["raw_tool_args_serialized"])

    def test_aippo_verification_probe_materializes_tiny_navigation_hint(self) -> None:
        report = cache.build_action_hint_cache_report(
            aippo_verification_probes=[
                {
                    "probe_id": "probe-preflight",
                    "probe_kind": "workflow_order_probe",
                    "guidance": "Reopen the prior preflight source.",
                    "next_action": "reopen_probe_source_before_action",
                    "source_refs": [source_ref("probe")],
                    "source_handles": [{"deepen_route_id": "deepen:probe", "reopen_required": True}],
                },
                {
                    "probe_id": "probe-private",
                    "privacy": "private",
                    "source_refs": [source_ref("private")],
                },
            ],
            now_unix=1000,
        )

        self.assertEqual(report["provider_counts"]["aippo_verification_probe"], 1)
        record = report["records"][0]
        self.assertEqual(record["provider_family"], "aippo_verification_probe")
        self.assertTrue(record["navigation_only"])
        self.assertFalse(record["can_support_factual_claim"])

    def test_refresh_cache_write_round_trips_through_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "action-hints.jsonl"
            result = cache.refresh_action_hint_cache(
                cache_jsonl=path,
                write=True,
                learning_guidance=[
                    {
                        "guidance_id": "learn-preflight",
                        "next_action": "run_preflight_before_broad_test",
                        "source_refs": [source_ref("learn")],
                    }
                ],
                now_unix=1000,
            )
            records = cache.load_action_hint_records(path)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["wrote"])
        self.assertEqual(result["cache_status"], "with_cache_records")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["provider_family"], "learning_loop")

    def test_refresh_cache_loads_default_learning_findings_into_aippo_clauses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings_path = root / ".aippocampus" / "learning-loop" / "findings.jsonl"
            findings_path.parent.mkdir(parents=True)
            finding = {
                "finding_id": "learned-preflight",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "cheap_preflight_before_broad_test",
                "status": "open",
                "scope": "project:AIppocampus",
                "confidence": "high",
                "occurrence_count": 2,
                "source_ref_count": 2,
                "source_refs": [source_ref("learn-a"), source_ref("learn-b")],
            }
            findings_path.write_text(json.dumps(finding, ensure_ascii=False) + "\n", encoding="utf-8")
            cache_path = root / "action-hints.jsonl"

            result = cache.refresh_action_hint_cache(
                cwd=root,
                cache_jsonl=cache_path,
                write=True,
                now_unix=1000,
            )
            records = cache.load_action_hint_records(cache_path)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["learned_provider_intake"]["status"], "included")
        self.assertEqual(result["learned_provider_intake"]["finding_count"], 1)
        self.assertEqual(result["learned_provider_intake"]["included_count"], 1)
        self.assertEqual(result["learned_provider_intake"]["prepared_record_count"], 1)
        self.assertEqual(records[0]["provider_family"], "aippo_learned_clause")

    def test_refresh_cache_applies_effectiveness_ledger_before_hot_cache(self) -> None:
        guidance = [
            {
                "guidance_id": "useful-guidance",
                "next_action": "run_preflight_before_broad_test",
                "source_refs": [source_ref("useful")],
                "command_terms": ["pytest"],
            },
            {
                "guidance_id": "stale-guidance",
                "next_action": "run_preflight_before_broad_test",
                "source_refs": [source_ref("stale")],
                "command_terms": ["pytest"],
            },
        ]
        ledger_rows = ledger_rows_from_guidance_outcomes(
            guidance,
            [
                {
                    "lesson_id": "useful-guidance",
                    "outcome": "prevented_repeat",
                    "source_refs": [source_ref("useful-outcome")],
                },
                {
                    "lesson_id": "stale-guidance",
                    "outcome": "repeated_failure_after_surface",
                    "source_refs": [source_ref("stale-outcome")],
                },
            ],
        )

        result = cache.refresh_action_hint_cache(
            learning_guidance=guidance,
            effectiveness_ledger_rows=ledger_rows,
            now_unix=1000,
        )
        records = result["cache"]["records"]

        self.assertTrue(result["effectiveness_ledger_intake"]["applied_to_guidance_before_cache"])
        self.assertEqual(result["effectiveness_ledger_intake"]["summary"]["row_count"], 2)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_id"], "useful-guidance")
        self.assertEqual(records[0]["effectiveness_status"], "useful_signal")
        self.assertGreater(records[0]["navigation_priority_delta"], 0)

    def test_refresh_cache_loads_default_effectiveness_ledger_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_path = root / ".aippocampus" / "learning-loop" / "effectiveness-ledger.jsonl"
            guidance = [
                {
                    "guidance_id": "stale-guidance",
                    "next_action": "run_preflight_before_broad_test",
                    "source_refs": [source_ref("stale")],
                    "command_terms": ["pytest"],
                }
            ]
            rows = ledger_rows_from_guidance_outcomes(
                guidance,
                [
                    {
                        "lesson_id": "stale-guidance",
                        "outcome": "stale_superseded",
                        "source_refs": [source_ref("stale-outcome")],
                    }
                ],
            )
            append_ledger_rows(ledger_path, rows)

            result = cache.refresh_action_hint_cache(
                cwd=root,
                learning_guidance=guidance,
                now_unix=1000,
            )

        self.assertEqual(result["effectiveness_ledger_intake"]["status"], "found")
        self.assertTrue(result["effectiveness_ledger_intake"]["applied_to_guidance_before_cache"])
        self.assertEqual(result["cache"]["record_count"], 0)

    def test_refresh_cache_write_uses_default_cache_path_when_none_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry"
            with patch.dict(os.environ, {"AIPPOCAMPUS_REGISTRY_DIR": str(registry)}):
                result = cache.refresh_action_hint_cache(
                    cwd=root,
                    write=True,
                    learning_guidance=[
                        {
                            "guidance_id": "default-cache-guidance",
                            "next_action": "run_preflight_before_broad_test",
                            "source_refs": [source_ref("default-cache")],
                            "command_terms": ["pytest"],
                        }
                    ],
                    now_unix=1000,
                )
                default_path = cache.default_action_hint_cache_path(root)
            records = cache.load_action_hint_records(default_path)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["default_cache_path_used"])
        self.assertEqual(
            result["cache_path_label"],
            "registry/action-hints/<workspace-scope>/pretooluse-cache.jsonl",
        )
        self.assertEqual(result["cache_path_source"], "default_registry")
        self.assertEqual(result["cache_scope"], "current_workspace")
        self.assertTrue(default_path.is_relative_to(registry))
        self.assertFalse((root / ".aippocampus" / "action-hints").exists())
        self.assertEqual(result["cache_status"], "with_cache_records")
        self.assertEqual(len(records), 1)

    def test_empty_refresh_cache_reports_learning_input_recovery_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = cache.refresh_action_hint_cache(
                cwd=root,
                write=False,
                include_default_learning=True,
                include_default_effectiveness_ledger=True,
                now_unix=1000,
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["cache"]["record_count"], 0)
        self.assertEqual(result["foreground_action"]["id"], "discover_learning_sources")
        action_ids = [item["id"] for item in result["safe_next_actions"]]
        self.assertIn("discover_learning_sources", action_ids)
        self.assertIn("inspect_learning_guidance", action_ids)
        self.assertIn("activate_aippo_guidance", action_ids)
        self.assertEqual(result["empty_cache_recovery"]["reason"], "no_learning_or_effectiveness_inputs_found")
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("<events.jsonl>", encoded)
        self.assertNotIn(str(root), encoded)


if __name__ == "__main__":
    unittest.main()
