from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.coding import (
    code_state_anchors,
    host_contract,
)
from aippocampus_runtime.coding import decision_events as decisions
from tests.aippocampus.redaction_fixtures import (
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


def message(
    *,
    message_id: str,
    turn_id: str,
    role: str,
    text: str,
    line: int,
    phase: str = "",
    is_final: bool = False,
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "turn_id": turn_id,
        "source_id": "src-test",
        "clean_ordinal": line,
        "source_line": line,
        "role": role,
        "phase": phase,
        "is_final": is_final,
        "timestamp": "2026-05-30T00:00:00Z",
        "text": text,
    }

class CodingDecisionEventsTests(unittest.TestCase):
    def _repo_scoped_candidate(self) -> dict[str, object]:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="Do not replace the src/widget.py guard with summary-only lookup.",
            )
        ]
        candidates = decisions.review_decision_candidates(
            decisions.extract_decision_candidates(rows, thread_key="session:code-anchor")
        )
        for candidate in candidates:
            if candidate["event_type"] == "rejected_route":
                return candidate
        self.fail("expected rejected_route coding decision candidate")

    def test_extracts_accepted_rejected_superseded_and_local_candidates(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="Do not replace source refs with summaries in skills/aippocampus/scripts/retrieval.py.",
            ),
            message(
                message_id="m2",
                turn_id="t1",
                role="assistant",
                line=2,
                phase="final_answer",
                is_final=True,
                text="We decided to keep clean source as truth and implemented the retrieval.py guard.",
            ),
            message(
                message_id="m3",
                turn_id="t2",
                role="user",
                line=3,
                text="This branch-local workaround only applies to this task; do not repeat it globally.",
            ),
            message(
                message_id="m4",
                turn_id="t3",
                role="user",
                line=4,
                text="The old rejected route is superseded; no longer treat that cache split as current.",
            ),
            message(
                message_id="m5",
                turn_id="t4",
                role="user",
                line=5,
                text="Random coding chatter about maybe reading files later.",
            ),
        ]

        candidates = decisions.review_decision_candidates(
            decisions.extract_decision_candidates(
                rows,
                thread_key="session:decision-test",
                workspace="AIppocampus",
            )
        )
        by_type = {candidate["event_type"]: candidate for candidate in candidates}
        statuses = {candidate["review_status"] for candidate in candidates}

        self.assertIn("accepted_decision", by_type)
        self.assertIn("rejected_route", by_type)
        self.assertIn("do_not_repeat", by_type)
        self.assertIn("local_only", statuses)
        self.assertIn("superseded", statuses)
        self.assertFalse(any("Random coding chatter" in c["summary"] for c in candidates))
        for candidate in candidates:
            self.assertEqual(candidate["kind"], decisions.DECISION_KIND)
            self.assertEqual(candidate["finding_kind"], "decision_event")
            self.assertEqual(candidate["evidence_status"], "source_backed")
            self.assertEqual(candidate["formal_memory_promoted"], False)
            self.assertNotIn("freshness", candidate)
            self.assertNotIn("confidence", candidate)
            self.assertIn("extraction_confidence", candidate)
            self.assertTrue(candidate["source_refs"])
            self.assertEqual(candidate["source_refs"][0]["thread_key"], "session:decision-test")
            self.assertFalse(candidate["review_boundary"]["current_validity_weather_stored_on_event"])
            for rejected in candidate["rejected_paths"]:
                self.assertNotIn("still_rejected", rejected)

    def test_privacy_scan_redacts_secret_and_local_path_surfaces(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text=(
                    f"Do not repeat token={FAKE_TEST_SECRET_VALUE} from "
                    f"{fake_test_windows_path('secret.txt')} in a decision event."
                ),
            )
        ]

        candidates = decisions.extract_decision_candidates(rows, thread_key="session:privacy")
        encoded = json.dumps(candidates, ensure_ascii=False)

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["privacy_scan"]["redacted"])
        self.assertEqual(candidates[0]["privacy_scan"]["raw_text_stored"], False)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, encoded)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, encoded)

    def test_missing_source_ref_shape_is_not_extracted(self) -> None:
        rows = [
            {
                "role": "user",
                "text": "Do not repeat this route.",
                "turn_id": "t1",
                "source_line": 1,
            }
        ]

        candidates = decisions.extract_decision_candidates(rows)

        self.assertEqual(candidates, [])

    def test_broad_branch_ambiguous_decision_needs_confirmation(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="Do not do it that way.",
            )
        ]

        candidates = decisions.extract_decision_candidates(rows, thread_key="session:broad")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["review_status"], "needs_confirmation")
        self.assertNotIn("freshness", candidates[0])
        assessment = decisions.build_decision_state_assessment(candidates[0])
        self.assertEqual(assessment["kind"], decisions.ASSESSMENT_KIND)
        self.assertEqual(assessment["freshness"], "needs_confirmation")
        self.assertEqual(assessment["still_rejected"], "unknown")
        self.assertEqual(assessment["truth_boundary"], "derived_weather_not_source_fact")

    def test_ticket_warns_after_compaction_without_over_nagging(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="Do not replace the registry_search.py split with direct registry imports.",
            )
        ]
        candidates = decisions.review_decision_candidates(
            decisions.extract_decision_candidates(rows, thread_key="session:ticket")
        )

        ticket = decisions.render_coding_continuity_ticket(
            candidates,
            prompt="Let's patch registry_search.py and maybe move logic back into registry imports.",
            trigger="compaction_loss",
            visible_context_has_source=False,
        )
        visible_ticket = decisions.render_coding_continuity_ticket(
            candidates,
            prompt="Let's patch registry_search.py.",
            trigger="compaction_loss",
            visible_context_has_source=True,
        )
        unrelated_ticket = decisions.render_coding_continuity_ticket(
            candidates,
            prompt="Let's update the README typography.",
            trigger="compaction_loss",
            visible_context_has_source=False,
        )

        self.assertEqual(len(ticket), 1)
        self.assertEqual(ticket[0]["kind"], decisions.TICKET_KIND)
        self.assertEqual(ticket[0]["intervention_level"], "warning")
        self.assertEqual(ticket[0]["proposed_use"], "warn")
        self.assertEqual(ticket[0]["source_thickness"], "usable")
        self.assertEqual(ticket[0]["derived_assessment"]["still_rejected"], "unknown")
        self.assertEqual(ticket[0]["derived_assessment"]["truth_boundary"], "derived_weather_not_source_fact")
        self.assertEqual(ticket[0]["basis_refs"], ticket[0]["evidence_refs"])
        contract = host_contract.describe_host_contract(ticket[0])
        self.assertEqual(contract["validation"]["missing_required_ai_fields"], [])
        self.assertEqual(ticket[0]["source_visibility"], "host_runtime_input")
        self.assertIn("host confirms the ticket source is not already visible", ticket[0]["preconditions"])
        self.assertIn("dismissed", ticket[0]["outcome_feedback_expected"])
        self.assertEqual(visible_ticket, [])
        self.assertEqual(unrelated_ticket, [])

    def test_thin_source_refreshes_instead_of_warning(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="Do not replace the search_clean_source.py source-ref checks with summary-only lookup.",
            )
        ]
        candidates = decisions.review_decision_candidates(
            decisions.extract_decision_candidates(rows, thread_key="session:thin")
        )
        thin_candidate = {
            **candidates[0],
            "source_thickness": "thin",
            "source_refs": [],
        }

        tickets = decisions.render_coding_continuity_ticket(
            [thin_candidate],
            prompt="Patch search_clean_source.py by using summary-only lookup.",
            trigger="compaction_loss",
        )

        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["source_thickness"], "thin")
        self.assertEqual(tickets[0]["proposed_use"], "refresh_sources")
        self.assertEqual(tickets[0]["intervention_level"], "state_check")
        self.assertNotEqual(tickets[0]["proposed_use"], "warn")
        self.assertEqual(tickets[0]["diagnostics"]["decision"], "degraded_to_refresh_sources")
        self.assertIn("refresh_sources", tickets[0]["derived_assessment"]["policy"]["thin_source_safe_uses"])

    def test_refuted_and_superseded_candidates_do_not_surface_as_tickets(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="The rejected registry split was wrong and refuted by tests.",
            ),
            message(
                message_id="m2",
                turn_id="t2",
                role="user",
                line=2,
                text="The old rejected vector route is superseded and no longer current.",
            ),
        ]
        candidates = decisions.review_decision_candidates(
            decisions.extract_decision_candidates(rows, thread_key="session:stale")
        )

        tickets = decisions.render_coding_continuity_ticket(
            candidates,
            prompt="Try the registry split and vector route again.",
            trigger="compaction_loss",
        )

        self.assertEqual({candidate["review_status"] for candidate in candidates}, {"refuted", "superseded"})
        self.assertEqual(tickets, [])

    def test_append_rows_and_run_extraction_are_append_only(self) -> None:
        rows = [
            message(
                message_id="m1",
                turn_id="t1",
                role="user",
                line=1,
                text="Do not replace clean source with generated summaries.",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = root / "messages.jsonl"
            output = root / "decisions.jsonl"
            messages.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            result = decisions.run_extraction(
                messages_path=messages,
                output_path=output,
                thread_key="session:append",
                ticket_prompt="generated summaries",
            )
            first_snapshot = output.read_text(encoding="utf-8")
            second = decisions.run_extraction(
                messages_path=messages,
                output_path=output,
                thread_key="session:append",
                ticket_prompt="generated summaries",
            )
            lines = output.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["assessment_count"], 1)
        self.assertEqual(result["ticket_count"], 1)
        self.assertEqual(result["assessments"][0]["kind"], decisions.ASSESSMENT_KIND)
        self.assertIn("host_agent_intervention_timing", result["cannot_claim"])
        self.assertEqual(second["wrote_count"], 1)
        self.assertEqual(len(lines), 2)
        self.assertEqual(first_snapshot.splitlines()[0], lines[0])

    def test_code_state_anchor_populates_repo_scope_and_public_safe_metadata(self) -> None:
        candidate = self._repo_scoped_candidate()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "src" / "widget.py"
            file_path.parent.mkdir(parents=True)
            file_path.write_text("def guard():\n    return 'source-backed'\n", encoding="utf-8")

            anchor = code_state_anchors.build_checkout_code_state_anchor(
                candidate,
                repo_root=root,
                repo_commit="abc123",
                branch_or_head_ref="sapientropic/issue-847-code-state-anchors",
                pr_ref="#873",
                issue_ref="#847",
                test_or_check_refs=[
                    {
                        "id": "check-1",
                        "name": "unit tests",
                        "status": "success",
                        "raw_log": "raw test log should not serialize",
                    }
                ],
            )
            anchored = decisions.attach_code_state_anchors(candidate, [anchor])
            encoded = json.dumps(anchored, ensure_ascii=False)

        stored_anchor = anchored["code_state_anchors"][0]
        file_scope = stored_anchor["file_diff_scope"][0]
        self.assertEqual(stored_anchor["repo_commit"], "abc123")
        self.assertEqual(stored_anchor["pr_ref"], "#873")
        self.assertEqual(stored_anchor["issue_ref"], "#847")
        self.assertEqual(file_scope["path"], "src/widget.py")
        self.assertEqual(file_scope["change_kind"], "observed")
        self.assertTrue(file_scope["new_file_fingerprint"].startswith("sha256:"))
        self.assertEqual(stored_anchor["test_or_check_refs"][0]["status"], "success")
        self.assertNotIn("raw test log", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertFalse(stored_anchor["privacy_boundary"]["raw_diffs_serialized"])

    def test_missing_code_state_anchor_fails_open_for_existing_decision_weather(self) -> None:
        candidate = self._repo_scoped_candidate()

        assessment = decisions.build_decision_state_assessment(
            candidate,
            current_code_state={
                "repo_commit": "different-commit",
                "file_fingerprints": {"src/widget.py": "sha256:different"},
            },
        )

        self.assertEqual(assessment["proposed_use"], "warn")
        self.assertEqual(assessment["code_state_currentness"]["status"], "no_anchors")
        self.assertFalse(assessment["code_state_currentness"]["requires_refresh"])

    def test_code_state_mismatch_degrades_assessment_to_refresh_sources(self) -> None:
        candidate = self._repo_scoped_candidate()
        anchor = {
            "kind": code_state_anchors.CODE_STATE_ANCHOR_KIND,
            "repo_commit": "abc123",
            "file_diff_scope": [
                {
                    "path": "src/widget.py",
                    "change_kind": "observed",
                    "new_file_fingerprint": "sha256:oldhash",
                }
            ],
            "privacy_boundary": {"raw_diffs_serialized": False, "raw_test_logs_serialized": False},
        }
        anchored = decisions.attach_code_state_anchors(candidate, [anchor])

        assessment = decisions.build_decision_state_assessment(
            anchored,
            current_code_state={
                "repo_commit": "def456",
                "file_fingerprints": {"src/widget.py": "sha256:newhash"},
            },
        )

        self.assertEqual(assessment["proposed_use"], "refresh_sources")
        self.assertEqual(assessment["freshness"], "stale")
        self.assertTrue(assessment["code_state_currentness"]["requires_refresh"])
        self.assertIn("commit_mismatch", assessment["code_state_currentness"]["signals"])
        self.assertIn("file_hash_mismatch", assessment["code_state_currentness"]["signals"])

    def test_ticket_carries_compact_code_state_anchors_without_raw_logs_or_diffs(self) -> None:
        candidate = self._repo_scoped_candidate()
        anchor = {
            "kind": code_state_anchors.CODE_STATE_ANCHOR_KIND,
            "repo_commit": "abc123",
            "branch_or_head_ref": "sapientropic/issue-847-code-state-anchors",
            "pr_ref": "#873",
            "issue_ref": "#847",
            "file_diff_scope": [
                {
                    "path": "src/widget.py",
                    "change_kind": "observed",
                    "new_file_fingerprint": "sha256:oldhash",
                    "raw_diff": "raw diff should not serialize",
                }
            ],
            "test_or_check_refs": [
                {"name": "unit tests", "status": "success", "raw_log": "raw log should not serialize"}
            ],
            "privacy_boundary": {"raw_diffs_serialized": False, "raw_test_logs_serialized": False},
        }
        anchored = decisions.attach_code_state_anchors(candidate, [anchor])

        tickets = decisions.render_coding_continuity_ticket(
            [anchored],
            prompt="Patch src/widget.py by using summary-only lookup.",
            trigger="compaction_loss",
            current_code_state={"repo_commit": "def456"},
        )
        encoded = json.dumps(tickets, ensure_ascii=False)

        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["proposed_use"], "refresh_sources")
        self.assertEqual(tickets[0]["intervention_level"], "state_check")
        self.assertEqual(tickets[0]["code_state_anchors"][0]["pr_ref"], "#873")
        self.assertTrue(tickets[0]["code_state_currentness"]["requires_refresh"])
        self.assertNotIn("raw diff", encoded)
        self.assertNotIn("raw log", encoded)

if __name__ == "__main__":
    unittest.main()
