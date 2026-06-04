from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import ambient_policy as policy  # noqa: E402


class AmbientRecallPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def row(self, **overrides) -> dict:
        data = {
            "kind": "aippocampus_working_memory",
            "status": "active",
            "route": "use_with_source",
            "candidate_key": "wm_question_alignment",
            "candidate_type": "question_link",
            "title": "Agent alignment drift",
            "summary": "Recurring question about agent output drifting from user intent.",
            "trigger_terms": ["alignment drift", "agent intent"],
            "source_finding_ids": ["sf_a", "sf_b"],
        }
        data.update(overrides)
        return data

    def event(self, action: str, *, age_seconds: int = 0, **overrides) -> dict:
        created = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        data = {
            "kind": "aippocampus_ambient_policy_event",
            "schema_version": 1,
            "created_at": created.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "action": action,
            "target_key": "wm_question_alignment",
            "target_kind": "question_link",
            "target_title": "Agent alignment drift",
        }
        data.update(overrides)
        return data

    def test_surface_event_frequency_caps_nearby_question_hint(self) -> None:
        result = policy.apply_working_memory_policy(
            "alignment drift keeps happening",
            [self.row()],
            [self.event(policy.SURFACE, age_seconds=60)],
        )

        self.assertEqual(result["rows"], [])
        self.assertEqual(result["diagnostics"]["frequency_capped"], 1)

    def test_old_surface_event_does_not_cap_question_hint(self) -> None:
        result = policy.apply_working_memory_policy(
            "alignment drift keeps happening",
            [self.row()],
            [self.event(policy.SURFACE, age_seconds=policy.QUESTION_CAP_SECONDS + 60)],
        )

        self.assertEqual(len(result["rows"]), 1)

    def test_theme_candidate_uses_question_frequency_cap(self) -> None:
        row = self.row(
            candidate_key="wm_theme_alignment",
            candidate_type="theme_candidate",
            title="Theme: agent alignment drift",
        )
        event = self.event(
            policy.SURFACE,
            age_seconds=60,
            target_key="wm_theme_alignment",
            target_kind="theme_candidate",
        )

        result = policy.apply_working_memory_policy("alignment drift keeps happening", [row], [event])

        self.assertEqual(result["rows"], [])
        self.assertEqual(result["diagnostics"]["frequency_capped"], 1)

    def test_dismiss_and_reopen_latest_event_wins(self) -> None:
        dismissed = self.event(policy.DISMISS, age_seconds=60)
        reopened = self.event(policy.REOPEN, age_seconds=1)

        result = policy.apply_working_memory_policy(
            "alignment drift keeps happening",
            [self.row()],
            [dismissed, reopened],
        )

        self.assertEqual(len(result["rows"]), 1)

    def test_theme_candidate_dismiss_and_reopen_latest_event_wins(self) -> None:
        row = self.row(candidate_key="wm_theme_alignment", candidate_type="theme_candidate")
        dismissed = self.event(
            policy.DISMISS,
            age_seconds=60,
            target_key="wm_theme_alignment",
            target_kind="theme_candidate",
        )
        reopened = self.event(
            policy.REOPEN,
            age_seconds=1,
            target_key="wm_theme_alignment",
            target_kind="theme_candidate",
        )

        result = policy.apply_working_memory_policy("alignment drift keeps happening", [row], [dismissed, reopened])

        self.assertEqual(len(result["rows"]), 1)

    def test_dont_track_this_is_dismiss_not_reopen(self) -> None:
        self.assertEqual(policy.detect_policy_intent("don't track this").action, policy.DISMISS)
        self.assertEqual(policy.detect_policy_intent("do not track this").action, policy.DISMISS)
        self.assertEqual(policy.detect_policy_intent("reopen tracking this").action, policy.REOPEN)

    def test_reopen_resets_old_frequency_cap(self) -> None:
        surfaced = self.event(policy.SURFACE, age_seconds=120)
        dismissed = self.event(policy.DISMISS, age_seconds=60)
        reopened = self.event(policy.REOPEN, age_seconds=1)

        result = policy.apply_working_memory_policy(
            "alignment drift keeps happening",
            [self.row()],
            [surfaced, dismissed, reopened],
        )

        self.assertEqual(len(result["rows"]), 1)

    def test_frontier_marker_only_surfaces_for_resume_intent(self) -> None:
        row = self.row(
            candidate_key="wm_frontier_blocked",
            candidate_type="frontier_marker",
            title="Blocked external evidence boundary",
            summary="The work stopped at a missing external evidence boundary.",
            trigger_terms=["external evidence boundary"],
        )

        ordinary = policy.apply_working_memory_policy("external evidence notes", [row], [])
        resume = policy.apply_working_memory_policy(
            "resume the unresolved external evidence boundary", [row], []
        )

        self.assertEqual(ordinary["rows"], [])
        self.assertEqual(ordinary["diagnostics"]["frontier_not_requested"], 1)
        self.assertEqual(len(resume["rows"]), 1)

    def test_cached_frontier_card_requires_resume_intent(self) -> None:
        card = {
            "card_id": "card-frontier",
            "theme": "External evidence boundary",
            "ambient_policy": {
                "target_keys": ["wm_frontier_blocked"],
                "target_kind": "frontier_marker",
            },
        }

        ordinary = policy.filter_ambient_cards([card], [], prompt="external evidence notes")
        resume = policy.filter_ambient_cards(
            [card], [], prompt="resume the unresolved external evidence boundary"
        )

        self.assertEqual(ordinary["cards"], [])
        self.assertEqual(ordinary["diagnostics"]["frontier_not_requested"], 1)
        self.assertEqual(len(resume["cards"]), 1)

    def test_cached_theme_card_uses_question_frequency_cap(self) -> None:
        card = {
            "card_id": "card-theme",
            "theme": "Agent alignment drift",
            "ambient_policy": {
                "target_keys": ["wm_theme_alignment"],
                "target_kind": "theme_candidate",
            },
        }
        event = self.event(
            policy.SURFACE,
            age_seconds=60,
            target_key="wm_theme_alignment",
            target_kind="theme_candidate",
        )

        result = policy.filter_ambient_cards([card], [event], prompt="alignment drift")

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["diagnostics"]["frequency_capped"], 1)

    def test_stop_tracking_this_writes_hash_only_dismissal_for_cached_card(self) -> None:
        path = self.root / "ambient_policy.jsonl"
        update = policy.policy_update_for_prompt(
            prompt="stop tracking this",
            rows=[],
            cached_cards=[
                {
                    "card_id": "card-question",
                    "theme": "Agent alignment drift",
                    "ambient_policy": {
                        "target_keys": ["wm_question_alignment"],
                        "target_kind": "question_link",
                        "source_finding_ids": ["sf_a", "sf_b"],
                    },
                }
            ],
            policy_path=path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
        )
        raw = path.read_text(encoding="utf-8")
        row = json.loads(raw)

        self.assertEqual(update["status"], "written")
        self.assertEqual(row["action"], policy.DISMISS)
        self.assertEqual(row["target_key"], "wm_question_alignment")
        self.assertEqual(row["source_finding_ids"], ["sf_a", "sf_b"])
        self.assertNotIn("stop tracking", raw.casefold())
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))

    def test_explicit_target_dismissal_does_not_store_raw_target_text(self) -> None:
        path = self.root / "ambient_policy.jsonl"
        update = policy.policy_update_for_prompt(
            prompt="ignore question about secret lotus",
            rows=[
                self.row(
                    title="Quiet review row",
                    summary="The reviewed recurring question uses the secret lotus trigger.",
                    trigger_terms=["secret lotus"],
                )
            ],
            cached_cards=[],
            policy_path=path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
        )
        raw = path.read_text(encoding="utf-8")
        row = json.loads(raw)

        self.assertEqual(update["status"], "written")
        self.assertEqual(row["action"], policy.DISMISS)
        self.assertEqual(row["source_finding_ids"], ["sf_a", "sf_b"])
        self.assertIn("target_text_fingerprint", row)
        self.assertNotIn("secret lotus", raw.casefold())
        self.assertNotIn("ignore question", raw.casefold())

    def test_large_policy_overlay_fails_open_in_foreground_loader(self) -> None:
        path = self.root / "ambient_policy.jsonl"
        path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_ambient_policy_event",
                    "created_at": "2026-05-30T00:00:00Z",
                    "action": policy.DISMISS,
                    "target_key": "wm_question_alignment",
                    "target_kind": "question_link",
                    "padding": "x" * (policy.DEFAULT_POLICY_MAX_BYTES + 1),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(policy.load_policy_events(path), [])


if __name__ == "__main__":
    unittest.main()
