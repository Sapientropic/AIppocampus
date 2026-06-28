from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_tool_root_module

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "tools" / "aippocampus" / "agent_slop_guard.py"
FIXTURES = REPO_ROOT / "tests" / "aippocampus" / "agent_slop_guard_fixtures"

agent_slop_guard = import_tool_root_module("agent_slop_guard")


class AgentSlopGuardTests(unittest.TestCase):
    def test_compact_projector_bypass_rule_catches_mcp_text_result_public_payload(self) -> None:
        bad = """
def handler(text_result, public_payload):
    return text_result(public_payload({"status": "needs_input"}))
"""
        allowed = """
def handler(render_profiled_result, public_payload):
    return render_profiled_result(public_payload({"status": "needs_input"}), detail="compact")
"""

        bad_findings = agent_slop_guard.analyze_text(
            bad,
            path="skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py",
            changed_files={"skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py"},
        )
        allowed_findings = agent_slop_guard.analyze_text(
            allowed,
            path="skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py",
            changed_files={"skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py"},
        )

        self.assertEqual([item["rule_id"] for item in bad_findings], ["compact_projector_bypass"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2696")
        self.assertEqual(bad_findings[0]["baseline_status"], "new")
        self.assertEqual(allowed_findings, [])

    def test_hot_path_silent_fallback_rule_catches_empty_broad_exception(self) -> None:
        bad = """
def load(rows):
    try:
        return [row.strip() for row in rows]
    except Exception:
        return []
"""
        allowed = """
def load(rows):
    try:
        return [row.strip() for row in rows]
    except Exception as exc:
        return {"status": "degraded", "error_type": type(exc).__name__, "rows": []}
"""
        hot_path = "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_core.py"

        bad_findings = agent_slop_guard.analyze_text(
            bad,
            path=hot_path,
            changed_files={hot_path},
        )
        allowed_findings = agent_slop_guard.analyze_text(
            allowed,
            path=hot_path,
            changed_files={hot_path},
        )

        self.assertEqual([item["rule_id"] for item in bad_findings], ["hot_path_silent_fallback"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2697")
        self.assertEqual(allowed_findings, [])

    def test_source_jsonl_owner_bypass_rule_catches_direct_line_parse(self) -> None:
        bad = """
import json

def load(path):
    rows = []
    for line in path.read_text().splitlines():
        rows.append(json.loads(line))
    return rows
"""
        allowed = """
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

def load(path):
    return load_jsonl_dict_rows(path).rows
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_bridge_map.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in bad_findings], ["source_jsonl_owner_bypass"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2698")
        self.assertEqual(allowed_findings, [])

    def test_atomic_write_owner_bypass_rule_catches_fixed_tmp_and_replace(self) -> None:
        bad = """
def write(path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload)
    tmp.replace(path)
"""
        allowed = """
from aippocampus_runtime.io_integrity import atomic_write_text

def write(path, payload):
    atomic_write_text(path, payload)
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/source/agent_self_notes.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual(
            [item["rule_id"] for item in bad_findings],
            ["atomic_write_owner_bypass", "atomic_write_owner_bypass"],
        )
        self.assertTrue(all(item["owner_issue"] == "#2698" for item in bad_findings))
        self.assertEqual(allowed_findings, [])

    def test_source_ref_helper_duplicate_rule_points_to_owner(self) -> None:
        bad = """
def clean_source_ref(ref):
    return {"thread_key": ref.get("thread_key"), "line": ref.get("line")}
"""
        allowed_owner = """
def clean_source_ref(ref):
    return {"thread_key": ref.get("thread_key"), "line": ref.get("line")}
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/recall/search_decision_adapter.py"
        owner_path = "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        owner_findings = agent_slop_guard.analyze_text(
            allowed_owner,
            path=owner_path,
            changed_files={owner_path},
        )

        self.assertEqual([item["rule_id"] for item in bad_findings], ["source_ref_helper_duplicate"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2698")
        self.assertEqual(owner_findings, [])

    def test_owner_layer_contract_inventory_points_to_known_rules(self) -> None:
        report = agent_slop_guard.build_report(paths=[], changed_files=set(), baseline={})
        contracts = {item["contract_id"]: item for item in report["owner_layer_contracts"]}

        self.assertGreaterEqual(len(contracts), 5)
        self.assertEqual(
            set(contracts),
            {
                "mcp_foreground_projection_owner",
                "source_io_kernel_owner",
                "registry_writer_owner",
                "local_lock_owner",
                "followthrough_test_owner",
            },
        )
        known_rules = set(agent_slop_guard.RULES)
        for contract in contracts.values():
            with self.subTest(contract=contract["contract_id"]):
                self.assertTrue(set(contract["rule_ids"]) <= known_rules)
                self.assertTrue(contract["owner"])
                self.assertTrue(contract["why"])

    def test_rule_catalog_owns_rule_config_and_hazard_mapping(self) -> None:
        rules = agent_slop_guard.RULES

        self.assertIn(
            "skills/aippocampus/scripts/aippocampus_runtime/source/",
            rules["hot_path_silent_fallback"].config.hot_path_prefixes,
        )
        self.assertIn(
            "source_ref_key",
            rules["source_ref_helper_duplicate"].config.source_ref_helper_names,
        )
        self.assertIn(
            "source-state-durability",
            {rules["source_jsonl_owner_bypass"].hazard_id, rules["local_lock_owner_bypass"].hazard_id},
        )
        for rule in rules.values():
            with self.subTest(rule=rule.rule_id):
                self.assertTrue(rule.hazard_id or rule.tooling_only)

    def test_hazard_card_coverage_references_existing_doc_ids(self) -> None:
        report = agent_slop_guard.build_report(paths=[], changed_files=set(), baseline={})
        coverage = report["hazard_card_coverage"]

        self.assertEqual(coverage["missing_hazard_ids"], [])
        self.assertEqual(coverage["unmapped_rule_ids"], [])
        by_card = {item["hazard_id"]: item["rule_ids"] for item in coverage["cards"]}
        self.assertIn("compact_projector_bypass", by_card["foreground-recall-follow-through"])
        self.assertIn("source_jsonl_owner_bypass", by_card["source-state-durability"])
        self.assertIn("performance_hot_path_nested_loop", by_card["mined-navigation-terms"])

    def test_registry_writer_owner_bypass_rule_catches_load_save_copy(self) -> None:
        bad = """
from aippocampus_runtime.registry.store import load_registry, save_registry

def mutate(json_path, md_path, entry):
    registry = load_registry(json_path)
    registry.setdefault("threads", []).append(entry)
    save_registry(registry, json_path, md_path)
"""
        allowed = """
from aippocampus_runtime.registry.store import update_registry

def mutate(json_path, md_path, entry):
    def updater(registry):
        registry.setdefault("threads", []).append(entry)
        return registry
    return update_registry(json_path, md_path, updater)
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/update/cli.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in bad_findings], ["registry_writer_owner_bypass"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2682")
        self.assertIn("registry_writer_lease", bad_findings[0]["owner_hint"])
        self.assertEqual(allowed_findings, [])

    def test_local_lock_owner_bypass_rule_catches_os_o_excl_copy(self) -> None:
        bad = """
import os

def acquire(path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
"""
        allowed = """
from aippocampus_runtime.artifacts.publish import artifact_lease

def publish(path, payload):
    with artifact_lease(path.parent, f".{path.name}.lease"):
        path.write_text(payload, encoding="utf-8")
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/hooks/skip_telemetry.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in bad_findings], ["local_lock_owner_bypass"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2681")
        self.assertIn("artifact_lease", bad_findings[0]["owner_hint"])
        self.assertEqual(allowed_findings, [])

    def test_compat_field_rule_requires_owner_removal_and_exposure_metadata(self) -> None:
        bad = """
def payload():
    return {"legacy_recall_selector": "sel_123"}
"""
        allowed = """
def payload():
    # compatibility owner: #2699; removal: after legacy clients stop reading it;
    # default exposure: detail/operator only, never compact foreground.
    return {"legacy_recall_selector": "sel_123"}
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in bad_findings], ["compat_field_metadata_missing"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2699")
        self.assertEqual(allowed_findings, [])

    def test_field_only_test_rule_requires_recall_deepen_followthrough(self) -> None:
        bad = """
import unittest

class RecallTests(unittest.TestCase):
    def test_recall_selector_exists(self):
        recall = {"recall_selector_id": "sel_123", "route_count": 1}
        self.assertIn("recall_selector_id", recall)
        self.assertGreater(recall["route_count"], 0)
"""
        allowed = """
import unittest
from tests.aippocampus.product_probe_helpers import assert_cli_recall_deepens_to_source

class RecallTests(unittest.TestCase):
    def test_recall_selector_opens_source(self):
        recall, deepen = assert_cli_recall_deepens_to_source(self, cue="x")
        self.assertIn("recall_selector_id", recall)
"""
        path = "tests/aippocampus/test_agent_recall.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in bad_findings], ["field_only_followthrough_test"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2699")
        self.assertEqual(allowed_findings, [])

    def test_compact_debug_field_test_rule_catches_detail_field_requirement(self) -> None:
        bad = """
import unittest

class RecallTests(unittest.TestCase):
    def test_compact_recall_contains_operator_command(self):
        compact = {"operator_detail_command": "agent recall --detail full"}
        self.assertIn("operator_detail_command", compact)
"""
        allowed = """
import unittest

class RecallTests(unittest.TestCase):
    def test_compact_recall_hides_operator_command(self):
        compact = {}
        self.assertNotIn("operator_detail_command", compact)
"""
        path = "tests/aippocampus/test_agent_recall_compact.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in bad_findings], ["compact_debug_field_test"])
        self.assertEqual(bad_findings[0]["owner_issue"], "#2699")
        self.assertEqual(allowed_findings, [])

    def test_public_compact_field_classification_allows_contract_fields(self) -> None:
        text = """
def compact_card():
    return {
        "kind": "demo",
        "status": "pass",
        "gate_class": "hard",
        "blocker_count": 1,
        "error": {"code": "demo"},
        "likely_cause": "demo cause",
        "source_boundary": {"local_paths_serialized": False},
        "detail_command": "python tool.py --detail full",
    }
"""
        path = "tools/aippocampus/test_plan_projection.py"

        findings = agent_slop_guard.analyze_text(text, path=path, changed_files={path})

        self.assertEqual(findings, [])

    def test_public_compact_field_classification_blocks_detail_fields(self) -> None:
        text = """
def compact_card():
    return {
        "kind": "demo",
        "status": "pass",
        "runtime_provenance": {"selector": "debug"},
    }
"""
        path = "tools/aippocampus/test_plan_projection.py"

        findings = agent_slop_guard.analyze_text(text, path=path, changed_files={path})

        self.assertEqual([item["rule_id"] for item in findings], ["public_compact_field_misplaced"])
        self.assertEqual(findings[0]["owner_issue"], "#2782")

    def test_public_compact_field_classification_ignores_internal_helpers(self) -> None:
        text = """
def internal_helper():
    return {
        "runtime_provenance": {"selector": "debug"},
        "unclassified_internal": True,
    }
"""
        path = "tools/aippocampus/test_plan_projection.py"

        findings = agent_slop_guard.analyze_text(text, path=path, changed_files={path})

        self.assertEqual(findings, [])

    def test_performance_rules_catch_unbounded_nested_loop_materialization_and_db_work(self) -> None:
        bad = """
def mine(candidates, raw_stats, con):
    out = []
    for candidate in candidates:
        for other in raw_stats.values():
            out.extend(sorted(raw_stats.values()))
            con.execute("SELECT 1", (candidate,))
    return out
"""
        allowed = """
def report(candidates, raw_stats, con, limit):
    counts = {}
    for status in ("active", "parked"):
        counts[status] = counts.get(status, 0) + 1
    for candidate in candidates[:limit]:
        counts[candidate] = counts.get(candidate, 0) + 1
    for item in raw_stats[:limit]:
        rows = list(item.get("sample_terms") or [])
        counts[str(item)] = len(rows)
    return {"diagnostic": counts}
"""
        path = (
            "skills/aippocampus/scripts/aippocampus_runtime/navigation/"
            "association_phrase_mining.py"
        )

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual(
            [item["rule_id"] for item in bad_findings],
            [
                "performance_hot_path_nested_loop",
                "performance_hot_path_loop_materialization",
                "performance_hot_path_repeated_db_work",
            ],
        )
        self.assertEqual({item["owner_issue"] for item in bad_findings}, {"#2705"})
        self.assertEqual(allowed_findings, [])

    def test_performance_db_rule_points_concept_upsert_amplification_to_owner(self) -> None:
        bad = """
def build(related_terms, con):
    for related in related_terms:
        upsert_concept(con, related, status="staging")
"""
        allowed = """
def build(related_terms, resolver, con):
    for related in related_terms[:MAX_RELATED_PER_TERM]:
        resolver.resolve(con, related, status="staging")
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/navigation/concept_graph.py"

        bad_findings = agent_slop_guard.analyze_text(bad, path=path, changed_files={path})
        allowed_findings = agent_slop_guard.analyze_text(allowed, path=path, changed_files={path})

        self.assertEqual(
            [item["rule_id"] for item in bad_findings],
            ["performance_hot_path_repeated_db_work"],
        )
        self.assertEqual(bad_findings[0]["owner_issue"], "#2706")
        self.assertEqual(allowed_findings, [])

    def test_baseline_marks_historical_finding_without_hiding_changed_surface(self) -> None:
        text = """
def load(rows):
    try:
        return [row.strip() for row in rows]
    except Exception:
        return []
"""
        path = "skills/aippocampus/scripts/aippocampus_runtime/recall/retrieval.py"
        finding = agent_slop_guard.analyze_text(text, path=path, changed_files={path})[0]
        baseline = {finding["fingerprint"]: "#2629"}

        baselined = agent_slop_guard.analyze_text(
            text,
            path=path,
            baseline=baseline,
            changed_files={path},
        )[0]

        self.assertEqual(baselined["baseline_status"], "baselined")
        self.assertTrue(baselined["changed_surface"])
        self.assertEqual(baselined["owner_issue"], "#2629")

    def test_load_baseline_preserves_exact_fingerprint_whitespace(self) -> None:
        fingerprint = (
            "performance_hot_path_repeated_db_work:runtime.py:12:"
            "loop_db_work:con.execute inside row fetchall \n        select 1        "
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "baseline.json"
            path.write_text(
                json.dumps(
                    {
                        "baseline": [
                            {
                                "fingerprint": fingerprint,
                                "owner_issue": "#2707",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            baseline = agent_slop_guard.load_baseline(path)

        self.assertEqual(baseline[fingerprint], "#2707")

    def test_baseline_lifecycle_reports_missing_expired_closed_and_last_seen(self) -> None:
        text = """
def load(rows):
    try:
        return [row.strip() for row in rows]
    except Exception:
        return []
"""
        hot_path = "skills/aippocampus/scripts/aippocampus_runtime/recall/retrieval.py"
        finding = agent_slop_guard.analyze_text(text, path=hot_path, changed_files={hot_path})[0]
        expired = (date.today() - timedelta(days=1)).isoformat()

        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = Path(temp_dir) / "baseline.json"
            baseline_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "baseline": [
                            {
                                "fingerprint": finding["fingerprint"],
                                "owner_issue": "#2697",
                                "reason": "historical hot-path debt",
                                "accepted_source": "#2835 lifecycle test",
                                "accepted_date": "2026-06-01",
                                "review_after": expired,
                                "review_condition": "remove when owner path is touched",
                                "owner_issue_state": "closed",
                            },
                            {
                                "fingerprint": "source_jsonl_owner_bypass:gone.py:1:stale",
                                "owner_issue": "#2698",
                                "reason": "legacy row before lifecycle metadata",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            _ = agent_slop_guard.load_baseline(baseline_path)
            summary = agent_slop_guard.baseline_lifecycle_summary(
                agent_slop_guard.load_baseline_entries(baseline_path),
                current_fingerprints={finding["fingerprint"]},
            )

        self.assertEqual(summary["total_entry_count"], 2)
        self.assertEqual(summary["missing_lifecycle_metadata_count"], 1)
        self.assertEqual(summary["expired_entry_count"], 1)
        self.assertEqual(summary["review_due_entry_count"], 1)
        self.assertEqual(summary["closed_owner_entry_count"], 1)
        self.assertEqual(summary["last_seen_entry_count"], 1)
        self.assertEqual(summary["stale_entry_count"], 1)

    def test_fixture_root_contract_has_bad_and_allowed_examples(self) -> None:
        results = agent_slop_guard.run_fixture_root(FIXTURES, baseline={})
        by_fixture = {item["fixture"]: item for item in results}

        self.assertGreaterEqual(len(results), 17)
        self.assertTrue(all(item["passed"] for item in results))
        self.assertEqual(
            by_fixture["mcp/projector_bypass.py"]["rule_ids"],
            ["compact_projector_bypass"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/recall/silent_fallback.py"
            ]["rule_ids"],
            ["hot_path_silent_fallback"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/recall/source_jsonl_bypass.py"
            ]["rule_ids"],
            ["source_jsonl_owner_bypass"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/source/ad_hoc_atomic_write.py"
            ]["rule_ids"],
            ["atomic_write_owner_bypass"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/source/source_ref_helper_copy.py"
            ]["rule_ids"],
            ["source_ref_helper_duplicate"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/update/registry_writer_copy.py"
            ]["rule_ids"],
            ["registry_writer_owner_bypass"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/local_os_excl_lock.py"
            ]["rule_ids"],
            ["local_lock_owner_bypass"],
        )
        self.assertEqual(
            by_fixture[
                "skills/aippocampus/scripts/aippocampus_runtime/mcp/compat_alias_payload.py"
            ]["rule_ids"],
            ["compat_field_metadata_missing"],
        )
        self.assertEqual(
            by_fixture["tests/aippocampus/test_recall_field_only.py"]["rule_ids"],
            ["field_only_followthrough_test"],
        )
        self.assertEqual(
            by_fixture["tests/aippocampus/test_compact_debug_field.py"]["rule_ids"],
            ["compact_debug_field_test"],
        )

    def test_cli_json_is_advisory_unless_fail_on_violations_is_requested(self) -> None:
        bad_file = (
            "tests/aippocampus/agent_slop_guard_fixtures/bad/"
            "mcp/projector_bypass.py"
        )
        advisory = subprocess.run(
            [sys.executable, str(GUARD), "--json", "--changed-file", bad_file],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        hard = subprocess.run(
            [
                sys.executable,
                str(GUARD),
                "--json",
                "--changed-file",
                bad_file,
                "--fail-on-violations",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(advisory.returncode, 0, advisory.stderr)
        payload = json.loads(advisory.stdout)
        self.assertEqual(payload["kind"], "aippocampus_agent_slop_guard")
        self.assertTrue(payload["advisory"])
        self.assertEqual(payload["changed_surface_unbaselined_count"], 1)
        self.assertNotIn("rules", payload)
        self.assertNotIn("owner_layer_contracts", payload)
        self.assertEqual(payload["blockers"][0]["rule_id"], "compact_projector_bypass")
        self.assertEqual(payload["blockers"][0]["path"], bad_file)
        self.assertEqual(hard.returncode, 1)
        hard_payload = json.loads(hard.stdout)
        self.assertFalse(hard_payload["ok"])
        self.assertFalse(hard_payload["advisory"])
        self.assertEqual(hard_payload["gate_status"], "failed")
        self.assertEqual(hard_payload["status"], "fail")
        self.assertEqual(hard_payload["blockers"][0]["rule_id"], "compact_projector_bypass")

    def test_cli_changed_file_manifest_matches_repeated_changed_file(self) -> None:
        bad_file = (
            "tests/aippocampus/agent_slop_guard_fixtures/bad/"
            "mcp/projector_bypass.py"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "changed-files.txt"
            manifest.write_text(f"{bad_file}\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(GUARD),
                    "--json",
                    "--fail-on-violations",
                    "--changed-file-list",
                    str(manifest),
                ],
                cwd=REPO_ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["blockers"][0]["path"], bad_file)
        self.assertEqual(payload["blockers"][0]["rule_id"], "compact_projector_bypass")

    def test_cli_fixture_self_check_fails_if_expected_bad_or_allowed_contract_breaks(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(GUARD),
                "--json",
                "--detail",
                "full",
                "--fixture-root",
                str(FIXTURES),
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("rules", payload)
        self.assertIn("owner_layer_contracts", payload)
        self.assertEqual(payload["fixture_failure_count"], 0)
        self.assertTrue(all(item["passed"] for item in payload["fixture_results"]))

    def test_implicit_scans_do_not_treat_guard_fixtures_as_changed_surface(self) -> None:
        scan_roots = [agent_slop_guard.repo_relative(path) for path in agent_slop_guard._scan_roots()]
        git_changed = agent_slop_guard._git_changed_files()

        self.assertFalse(any("agent_slop_guard_fixtures" in path for path in scan_roots))
        self.assertFalse(any("agent_slop_guard_fixtures" in path for path in git_changed))


if __name__ == "__main__":
    unittest.main()
