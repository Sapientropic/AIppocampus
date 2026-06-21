from __future__ import annotations

import json
import unittest
from pathlib import Path

from aippocampus_runtime.navigation import repo_familiarity

REPO_ROOT = Path(__file__).resolve().parents[2]


def fixture_rows() -> list[dict[str, object]]:
    return [
        {
            "kind": "docs_boundary",
            "landmark": "source-backed memory boundary",
            "route_terms": ["source", "truth", "memory"],
            "boundary": "Source is ground; interpretation and scent remain navigation.",
            "route": {"docs": ["docs/research/source-as-world.md"]},
            "source_refs": [{"path": "docs/research/source-as-world.md", "line": 28}],
            "freshness": "current",
            "invalidation": {"files": [{"path": "docs/research/source-as-world.md", "sha256": "hash-source"}]},
            "why_now": "Relevant when a task may turn navigation hints into memory claims.",
            "action_delta_required": "Reopen source docs before making a memory-backed claim.",
            "first_source_to_reopen": "docs/research/source-as-world.md",
            "stop_after": "Stop once the source-vs-weather boundary is confirmed.",
            "do_not_use_for": ["current repo facts without reopening source"],
        },
        {
            "kind": "runtime_owner",
            "landmark": "foreground hook semantic budget",
            "route_terms": ["hook", "semantic", "budget"],
            "boundary": "Foreground hook must stay cheap and fail open.",
            "route": {
                "files": ["skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"],
                "tests": ["tests/aippocampus/test_aippocampus_prompt_hook.py"],
            },
            "source_refs": [{"path": "docs/architecture/runtime/cognitive-runtime-architecture.md", "line": 160}],
            "freshness": "current",
            "invalidation": {
                "commit": "abc123",
                "files": [
                    {
                        "path": "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py",
                        "sha256": "hash-hook",
                    }
                ],
            },
            "why_now": "May affect hook timeout and route visibility decisions.",
            "action_delta_required": "Inspect hook prompt owner and hook tests before changing semantic budget.",
            "first_source_to_reopen": "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py",
            "stop_after": "Stop after the hook owner and prompt-hook tests confirm the budget boundary.",
            "do_not_use_for": ["unrelated README/public readiness edits"],
        },
        {
            "kind": "compat_shim",
            "landmark": "compatibility shim cleanup",
            "route_terms": ["compat", "shim", "package owner"],
            "boundary": "Flat shims are temporary unless documented as direct commands.",
            "route": {
                "docs": ["docs/architecture/ops/compatibility-shim-inventory.md"],
                "tests": ["tests/aippocampus/test_compat_shim_inventory.py"],
            },
            "source_refs": [{"path": "docs/architecture/ops/compatibility-shim-inventory.md", "line": 1}],
            "freshness": "current",
            "invalidation": {"files": [{"path": "docs/architecture/ops/compatibility-shim-inventory.md", "sha256": "hash-shim"}]},
            "why_now": "Relevant when deleting flat runtime scripts or changing packaging exposure.",
            "action_delta_required": "Run the inventory before deleting another flat shim.",
            "first_source_to_reopen": "docs/architecture/ops/compatibility-shim-inventory.md",
            "stop_after": "Stop after inventory explains whether the shim is keep_cli, temporary_compat, or delete_now.",
            "do_not_use_for": ["current code claims without inventory output"],
        },
        {
            "kind": "test_boundary",
            "landmark": "storage governance rebuildable cache",
            "route_terms": ["storage", "governance", "cache"],
            "boundary": "Apply mode only evicts supported rebuildable caches with manifests.",
            "route": {
                "files": ["skills/aippocampus/scripts/aippocampus_runtime/ops/storage_governance.py"],
                "tests": ["tests/aippocampus/test_storage_governance.py"],
            },
            "source_refs": [{"path": "docs/architecture/ops/gb-scale-roadmap.md", "line": 90}],
            "freshness": "current",
            "invalidation": {"files": [{"path": "skills/aippocampus/scripts/aippocampus_runtime/ops/storage_governance.py", "sha256": "hash-storage"}]},
            "why_now": "Relevant when touching storage GC or cache eviction contracts.",
            "action_delta_required": "Inspect storage governance tests before changing apply behavior.",
            "first_source_to_reopen": "tests/aippocampus/test_storage_governance.py",
            "stop_after": "Stop after manifest and health degraded/rebuildable behavior are verified.",
            "do_not_use_for": ["raw source deletion"],
        },
        {
            "kind": "decision_shadow",
            "landmark": "rejected registry route card",
            "route_terms": ["registry", "rejected", "route"],
            "boundary": "Rejected-route hints require current source reopen before warning.",
            "route": {"tests": ["tests/aippocampus/test_coding_ticket_host_contract.py"]},
            "decision_shadow": {"status": "candidate", "source_thickness": "usable"},
            "source_refs": [{"path": "docs/research/agent-coding-context-analysis.md", "line": 313}],
            "freshness": "current",
            "invalidation": {"files": [{"path": "docs/research/agent-coding-context-analysis.md", "sha256": "hash-coding"}]},
            "why_now": "Relevant when a task may repeat an old rejected registry route.",
            "action_delta_required": "Check the host contract before surfacing a rejected-route warning.",
            "first_source_to_reopen": "docs/research/agent-coding-context-analysis.md",
            "stop_after": "Stop after source thickness and current visibility are checked.",
            "do_not_use_for": ["routine README edits", "unrelated public-readiness work"],
        },
    ]

class RepoFamiliarityTests(unittest.TestCase):
    def test_builds_source_backed_cards_with_action_delta_contract(self) -> None:
        cards = repo_familiarity.build_repo_familiarity_cards(
            {"source_rows": fixture_rows(), "repo_commit": "abc123"}
        )

        self.assertGreaterEqual(len(cards), 5)
        self.assertLessEqual(len(cards), 12)
        for card in cards:
            self.assertEqual(card["kind"], "source_backed_familiarity_card")
            self.assertEqual(card["domain"], "repo")
            self.assertTrue(card["source_refs"])
            self.assertTrue(card["freshness"])
            self.assertTrue(card["invalidation"])
            self.assertTrue(card["injection_policy"]["source_reopen_required"])
            self.assertTrue(card["why_now"])
            self.assertTrue(card["action_delta_required"])
            self.assertTrue(card["first_source_to_reopen"])
            self.assertTrue(card["stop_after"])

    def test_selector_caps_packet_and_reports_only_deterministic_cost_proxy(self) -> None:
        cards = repo_familiarity.build_repo_familiarity_cards(
            {"source_rows": fixture_rows(), "repo_commit": "abc123"}
        )

        packet = repo_familiarity.select_repo_familiarity_packet(
            cards,
            task="Change prompt hook semantic budget without increasing foreground latency",
            current_fingerprints={
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": "hash-hook",
                "docs/architecture/runtime/cognitive-runtime-architecture.md": "hash-architecture",
            },
            current_commit="abc123",
            max_cards=2,
            max_packet_bytes=1600,
        )

        self.assertEqual(packet["kind"], "aippocampus_repo_familiarity_packet")
        self.assertLessEqual(len(packet["selected_cards"]), 2)
        self.assertLessEqual(packet["packet_bytes"], 1600)
        self.assertGreaterEqual(len(packet["selected_cards"]), 1)
        for card in packet["selected_cards"]:
            self.assertTrue(card["action_delta_required"])
            self.assertTrue(card["stop_after"])
            self.assertTrue(card["first_source_to_reopen"])
        report = packet["cost_delta_report"]
        self.assertTrue(report["deterministic_proxy_only"])
        self.assertTrue(report["cannot_claim_live_cost_reduction"])
        self.assertIn("selected_card_count", report)
        self.assertIn("estimated_reopen_count", report)

    def test_stale_and_irrelevant_cards_fast_reject_without_authority(self) -> None:
        cards = repo_familiarity.build_repo_familiarity_cards(
            {"source_rows": fixture_rows(), "repo_commit": "abc123"}
        )

        stale_packet = repo_familiarity.select_repo_familiarity_packet(
            cards,
            task="Change prompt hook semantic budget",
            current_fingerprints={
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": "new-hash"
            },
            current_commit="abc123",
            max_cards=3,
        )

        self.assertFalse(
            any(card["landmark"] == "foreground hook semantic budget" for card in stale_packet["selected_cards"])
        )
        stale_rejections = [
            item for item in stale_packet["rejected_cards"] if item["reason"] == "stale_invalidation"
        ]
        self.assertTrue(stale_rejections)
        self.assertEqual(stale_packet["cost_delta_report"]["fast_reject_count"], len(stale_rejections))

        readme_packet = repo_familiarity.select_repo_familiarity_packet(
            cards,
            task="Polish README public readiness copy",
            current_fingerprints={},
            current_commit="abc123",
            max_cards=3,
        )
        serialized = json.dumps(readme_packet["selected_cards"], ensure_ascii=False)
        self.assertNotIn("rejected registry route card", serialized)
        self.assertTrue(
            any(item["reason"] == "irrelevant_to_task" for item in readme_packet["rejected_cards"])
        )

    def test_current_checkout_selects_compatibility_inventory_for_natural_cue(self) -> None:
        packet = repo_familiarity.select_current_checkout_packet(
            REPO_ROOT,
            task="compatibility historical fields inventory report",
            max_cards=1,
        )

        self.assertEqual(packet["kind"], "aippocampus_repo_familiarity_packet")
        self.assertEqual(len(packet["selected_cards"]), 1)
        card = packet["selected_cards"][0]
        self.assertEqual(card["landmark"], "compatibility and legacy-alias inventory")
        self.assertEqual(
            card["first_source_to_reopen"],
            "docs/architecture/ops/compatibility-shim-inventory.md",
        )
        self.assertTrue(card["invalidation"]["files"])
        self.assertTrue(card["injection_policy"]["source_reopen_required"])

if __name__ == "__main__":
    unittest.main()
