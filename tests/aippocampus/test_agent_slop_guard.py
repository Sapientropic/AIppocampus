from __future__ import annotations

import json
import subprocess
import sys
import unittest
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

    def test_fixture_root_contract_has_bad_and_allowed_examples(self) -> None:
        results = agent_slop_guard.run_fixture_root(FIXTURES, baseline={})
        by_fixture = {item["fixture"]: item for item in results}

        self.assertGreaterEqual(len(results), 13)
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
        self.assertEqual(payload["findings"][0]["rule_id"], "compact_projector_bypass")
        self.assertEqual(hard.returncode, 1)

    def test_cli_fixture_self_check_fails_if_expected_bad_or_allowed_contract_breaks(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(GUARD), "--json", "--fixture-root", str(FIXTURES)],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["fixture_failure_count"], 0)
        self.assertTrue(all(item["passed"] for item in payload["fixture_results"]))

    def test_implicit_scans_do_not_treat_guard_fixtures_as_changed_surface(self) -> None:
        scan_roots = [agent_slop_guard.repo_relative(path) for path in agent_slop_guard._scan_roots()]
        git_changed = agent_slop_guard._git_changed_files()

        self.assertFalse(any("agent_slop_guard_fixtures" in path for path in scan_roots))
        self.assertFalse(any("agent_slop_guard_fixtures" in path for path in git_changed))


if __name__ == "__main__":
    unittest.main()
