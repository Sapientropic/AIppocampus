from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import why_diagnostics as why  # noqa: E402
from aippocampus_runtime.recall.associative_path_inputs import (  # noqa: E402
    build_associative_path_diagnostic,
    build_associative_path_input_pack,
)


class AssociativePathInputPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sidecars = self.root / ".aippocampus"
        self.sidecars.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_jsonl(self, name: str, rows: list[dict[str, object]], *, malformed: bool = False) -> Path:
        path = self.sidecars / name
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if malformed:
                fh.write("{not-json\n")
        return path

    def test_builds_read_only_pack_from_sidecars_without_raw_paths(self) -> None:
        self._write_jsonl(
            "semantic-bridges.jsonl",
            [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            malformed=True,
        )
        self._write_jsonl(
            "navigation-potential.jsonl",
            [
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                },
                {
                    "route_id": "route:private",
                    "route_terms": ["private route"],
                    "source_refs": [{"thread_key": "thread:private", "message_id": "msg-9"}],
                    "scope_bucket": "user_private",
                },
            ],
        )
        self._write_jsonl(
            "route-feedback.jsonl",
            [
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "user_private",
                }
            ],
        )

        pack = build_associative_path_input_pack(query="黏菌 联想回忆 探索算法", cwd=self.root)
        encoded = json.dumps(pack, ensure_ascii=False)

        self.assertEqual(pack["kind"], "aippocampus_associative_path_input_pack")
        self.assertFalse(pack["boundary"]["writes_files"])
        self.assertFalse(pack["boundary"]["changes_default_recall_ranking"])
        self.assertEqual(pack["metrics"]["candidate_count"], 2)
        self.assertEqual(pack["metrics"]["semantic_bridge_row_count"], 1)
        self.assertEqual(pack["metrics"]["feedback_row_count"], 1)
        self.assertGreaterEqual(pack["metrics"]["malformed_row_count"], 1)
        self.assertGreaterEqual(pack["metrics"]["private_or_stale_row_count"], 1)
        self.assertIn("malformed_sidecar_rows_ignored", pack["reason_codes"])
        self.assertNotIn(str(self.root), encoded)

    def test_diagnostic_blocks_cross_scope_positive_feedback_but_keeps_route(self) -> None:
        private_feedback = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            candidates=[
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            semantic_bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            feedback_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "user_private",
                }
            ],
        )
        project_feedback = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            candidates=[
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            semantic_bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌", "联想回忆"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            feedback_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "project",
                }
            ],
        )

        self.assertEqual(private_feedback["decision"], "route_candidates")
        self.assertFalse(private_feedback["applied_to_default_ranking"])
        self.assertIn("cross_scope_positive_feedback_ignored", private_feedback["reason_codes"])
        self.assertNotIn(
            "positive_feedback_same_scope",
            private_feedback["top_candidates"][0]["reason_codes"],
        )
        self.assertIn(
            "positive_feedback_same_scope",
            project_feedback["top_candidates"][0]["reason_codes"],
        )

    def test_diagnostic_does_not_count_materialized_navigation_sidecar_twice(self) -> None:
        bridge = {
            "candidate_id": "bridge:apw-cn",
            "from_terms": ["黏菌", "联想回忆", "探索算法"],
            "to_terms": ["associative path walker", "routing exploration"],
            "source_refs": [{"thread_key": "fixture:path-walker", "source_id": "src-apw"}],
            "scope_bucket": "project",
        }
        navigation = {
            "route_id": "route:apw-cn",
            "candidate_id": "bridge:apw-cn",
            "route_terms": ["associative path walker", "routing exploration"],
            "thread_key": "thread:apw",
            "source_refs": [{"thread_key": "fixture:path-walker", "source_id": "src-apw"}],
            "scope_bucket": "project",
        }
        pack = build_associative_path_input_pack(
            query="黏菌 联想回忆 探索算法",
            semantic_bridge_rows=[bridge],
            navigation_rows=[navigation],
        )

        diagnostic = build_associative_path_diagnostic(
            query="黏菌 联想回忆 探索算法",
            input_pack=pack,
        )

        self.assertEqual(pack["metrics"]["candidate_count"], 1)
        self.assertEqual(pack["metrics"]["navigation_row_count"], 1)
        self.assertEqual(diagnostic["candidate_count"], 1)
        self.assertEqual(
            [candidate.get("route_id") for candidate in diagnostic["top_candidates"]],
            ["route:apw-cn"],
        )

    def test_why_recall_apw_sidecar_is_opt_in(self) -> None:
        pack = build_associative_path_input_pack(
            query="黏菌 联想回忆 探索算法",
            candidates=[
                {
                    "route_id": "route:apw",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
            semantic_bridge_rows=[
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["黏菌"],
                    "to_terms": ["associative path walker"],
                    "source_refs": [{"thread_key": "thread:apw", "message_id": "msg-1"}],
                    "scope_bucket": "project",
                }
            ],
        )
        default_payload = why.recall_diagnostic_report(
            cue="黏菌 联想回忆 探索算法",
            mode="why-recall",
            cwd=self.root,
            clean_source_dir=self.root / "missing-clean-source",
            associative_path_input_pack=pack,
        )
        opt_in = why.recall_diagnostic_report(
            cue="黏菌 联想回忆 探索算法",
            mode="why-recall",
            cwd=self.root,
            clean_source_dir=self.root / "missing-clean-source",
            include_associative_path_diagnostics=True,
            associative_path_input_pack=pack,
        )

        self.assertNotIn("associative_path_diagnostics", default_payload)
        self.assertIn("associative_path_walker", opt_in["searched_surfaces"])
        self.assertEqual(opt_in["associative_path_diagnostics"]["decision"], "route_candidates")
        self.assertFalse(opt_in["privacy_boundary"]["associative_path_walker_changed_default_ranking"])


if __name__ == "__main__":
    unittest.main()
