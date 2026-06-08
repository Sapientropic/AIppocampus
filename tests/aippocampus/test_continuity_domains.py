from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.mcp import server as mcp  # noqa: E402
from aippocampus_runtime.recall import (  # noqa: E402
    active_recall,
    ambient_cards,
    prompt_context_render,
)
from aippocampus_runtime.recall.continuity_domains import (  # noqa: E402
    ACTION_DIRECTION_ONLY,
    ACTION_IGNORE_OR_BLOCKED,
    DERIVED_ONLY_STATUS,
    append_continuity_domain_event,
    continuity_domain_pointer,
    match_continuity_domain_pointers,
    materialize_continuity_domains,
    project_situation_glyph,
    publish_continuity_domains_snapshot,
)


def _write_clean_source(clean: Path) -> None:
    clean.mkdir(parents=True, exist_ok=True)
    messages = [
        {
            "message_id": "msg-a",
            "turn_id": "turn-a",
            "turn_index": 1,
            "source_line": 2,
            "role": "user",
            "phase": "",
            "text": "AIppocampus should keep source-backed continuity domains.",
        },
        {
            "message_id": "msg-b",
            "turn_id": "turn-b",
            "turn_index": 2,
            "source_line": 4,
            "role": "assistant",
            "phase": "final_answer",
            "text": "The working conclusion is navigation; clean source remains authority.",
        },
        {
            "message_id": "msg-c",
            "turn_id": "turn-c",
            "turn_index": 3,
            "source_line": 6,
            "role": "user",
            "phase": "",
            "text": "A later correction says hook output should stay pointer-only.",
        },
    ]
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in messages:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in messages:
            fh.write(
                json.dumps(
                    {
                        "turn_id": row["turn_id"],
                        "turn_index": row["turn_index"],
                        "message_ids": [row["message_id"]],
                        "assistant_phase": row["phase"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _domain_events() -> list[dict]:
    return [
        {
            "event_kind": "domain_created",
            "domain_id": "cd-source-trailed-continuity",
            "title": "Source-trailed continuity domain",
            "domain_type": "project_direction",
            "scale": "meso",
            "working_conclusion_short": (
                "AIppocampus needs a durable working conclusion layer that can reopen "
                "source instead of becoming ungrounded summary."
            ),
            "activation_cues": ["continuity", "source trail", "domain"],
            "scope_labels": ["source-backed abstraction"],
            "long_range_tendencies": ["source-backed abstraction"],
            "source_refs": [{"message_id": "msg-a"}],
        },
        {
            "event_kind": "support_source_added",
            "domain_id": "cd-source-trailed-continuity",
            "source_refs": [{"message_id": "msg-b"}],
        },
        {
            "event_kind": "counter_source_added",
            "domain_id": "cd-source-trailed-continuity",
            "source_refs": [{"message_id": "missing"}],
        },
        {
            "event_kind": "boundary_pinned",
            "domain_id": "cd-source-trailed-continuity",
            "boundary_kind": "explicit_user_correction",
            "effect": "require_source_reopen",
            "strength": "hard",
            "summary": "Hook output should stay pointer-only.",
            "source_refs": [{"message_id": "msg-c"}],
        },
        {
            "event_kind": "pathlet_created",
            "pathlet_id": "pathlet-ab",
            "title": "From domain need to source boundary",
            "scope_labels": ["source-backed abstraction"],
            "ordered_source_refs": [{"message_id": "msg-a"}, {"message_id": "msg-b"}],
        },
    ]


class ContinuityDomainTests(unittest.TestCase):
    def test_materializer_keeps_source_trail_and_rejects_unresolved_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(_domain_events(), clean_source_dir=clean)

        self.assertEqual(snapshot["metrics"]["domain_count"], 1)
        self.assertEqual(snapshot["metrics"]["pathlet_count"], 1)
        self.assertEqual(snapshot["metrics"]["rejected_event_count"], 1)
        domain = snapshot["domains"][0]
        self.assertEqual(domain["scale"], "meso")
        self.assertEqual(domain["claim_contract"]["action_grammar"], "reopenable_route")
        self.assertTrue(domain["claim_contract"]["scale_does_not_set_authority"])
        self.assertTrue(domain["source_boundary"]["domain_summary_not_source"])
        self.assertEqual(domain["evidence_trail"]["support_refs"][0]["message_id"], "msg-a")
        self.assertEqual(domain["evidence_trail"]["boundary_refs"][0]["message_id"], "msg-c")
        self.assertEqual(snapshot["macro_tendencies"][0]["persistence_state"], DERIVED_ONLY_STATUS)
        self.assertEqual(snapshot["macro_tendencies"][0]["action_grammar"], ACTION_DIRECTION_ONLY)

    def test_append_publish_is_append_only_and_latest_snapshot_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean-source"
            _write_clean_source(clean)
            events_path = clean / "continuity-domain-events.jsonl"
            snapshot_dir = root / "continuity-domain-snapshots"
            for event in _domain_events()[:2]:
                append_continuity_domain_event(events_path, event, clean_source_dir=clean)

            report = publish_continuity_domains_snapshot(
                events_path=events_path,
                snapshot_dir=snapshot_dir,
                clean_source_dir=clean,
            )

            self.assertEqual(report["status"], "ok")
            self.assertEqual(len(events_path.read_text(encoding="utf-8").splitlines()), 2)
            latest = json.loads((snapshot_dir / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["snapshot"]["metrics"]["accepted_event_count"], 2)
            self.assertTrue((snapshot_dir / f"{report['snapshot_id']}.json").exists())

    def test_blocking_boundary_suppresses_domain_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            _write_clean_source(clean)
            events = [
                _domain_events()[0],
                {
                    "event_kind": "boundary_pinned",
                    "domain_id": "cd-source-trailed-continuity",
                    "boundary_kind": "privacy_boundary",
                    "effect": "block_hook",
                    "strength": "hard",
                    "source_refs": [{"message_id": "msg-c"}],
                },
            ]
            snapshot = materialize_continuity_domains(events, clean_source_dir=clean)

        domain = snapshot["domains"][0]
        self.assertEqual(domain["lifecycle"]["status"], "blocked")
        self.assertEqual(domain["claim_contract"]["action_grammar"], ACTION_IGNORE_OR_BLOCKED)
        self.assertEqual(
            match_continuity_domain_pointers("continuity domain", snapshot, limit=3),
            [],
        )

    def test_stale_and_negative_cue_domains_do_not_surface_as_normal_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            _write_clean_source(clean)
            stale_event = {**_domain_events()[0], "status": "stale"}
            negative_event = {
                **_domain_events()[0],
                "domain_id": "cd-negative-cue",
                "negative_cues": ["wrong lane"],
            }
            stale_snapshot = materialize_continuity_domains([stale_event], clean_source_dir=clean)
            negative_snapshot = materialize_continuity_domains(
                [negative_event],
                clean_source_dir=clean,
            )

        self.assertEqual(match_continuity_domain_pointers("continuity domain", stale_snapshot), [])
        self.assertEqual(match_continuity_domain_pointers("wrong lane continuity", negative_snapshot), [])
        self.assertEqual(len(match_continuity_domain_pointers("continuity", negative_snapshot)), 1)

    def test_hook_renders_pointer_without_working_conclusion_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(_domain_events(), clean_source_dir=clean)
            pointer = continuity_domain_pointer(snapshot["domains"][0])

        payload = ambient_cards.ambient_recall_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "continuity_domains": [pointer],
            }
        )
        context = prompt_context_render.context_for_hook(
            {"decision": "scent", "ambient_recall": payload}
        ) or ""

        self.assertIn("continuity domain pointer", context)
        self.assertIn("Source-trailed continuity domain", context)
        self.assertNotIn("durable working conclusion layer", context)
        self.assertIn("pointer only", context)

    def test_active_recall_surfaces_domain_handle_without_summary_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(_domain_events(), clean_source_dir=clean)
            snapshot_path = root / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            notes = root / "notes.jsonl"
            notes.write_text("", encoding="utf-8")
            working = root / "working.jsonl"
            working.write_text("", encoding="utf-8")

            result = active_recall.active_recall_context(
                prompt="继续 continuity domain 的 source trail 设计",
                cwd=root,
                agent_self_notes_path=notes,
                working_memory_path=working,
                continuity_domains_snapshot_path=snapshot_path,
                max_matches=3,
            )
            raw = json.dumps(result, ensure_ascii=False)

        self.assertEqual(result["surface_counts"]["continuity_domains"], 1)
        self.assertEqual(result["working_continuity_brief"][0]["card_kind"], "continuity_domain_pointer")
        self.assertFalse(result["working_continuity_brief"][0]["trust_contract"]["treat_as_fact"])
        domain_routes = [
            route for route in result["source_reopen_routes"] if route.get("kind") == "continuity_domain"
        ]
        self.assertEqual(len(domain_routes), 1)
        self.assertIn("snapshot_fingerprint", domain_routes[0]["handle"])
        self.assertIn("expires_unix", domain_routes[0]["handle"])
        self.assertNotIn("durable working conclusion layer", raw)
        self.assertNotIn(str(root), raw)

    def test_active_recall_domain_handle_stales_when_snapshot_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(_domain_events(), clean_source_dir=clean)
            snapshot_path = root / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            empty = root / "empty.jsonl"
            empty.write_text("", encoding="utf-8")
            result = active_recall.active_recall_context(
                prompt="continuity domain source trail",
                cwd=root,
                agent_self_notes_path=empty,
                working_memory_path=empty,
                continuity_domains_snapshot_path=snapshot_path,
                max_matches=3,
            )
            handle = next(
                route["handle"]
                for route in result["source_reopen_routes"]
                if route.get("kind") == "continuity_domain"
            )
            mutated = {**snapshot, "generated_at": "2099-01-01T00:00:00Z"}
            snapshot_path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")

            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 928,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": handle,
                            "cwd": str(root),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "stale_recall_handle")

    def test_blocked_domain_does_not_enter_active_or_mcp_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            events = [
                _domain_events()[0],
                {
                    "event_kind": "boundary_pinned",
                    "domain_id": "cd-source-trailed-continuity",
                    "boundary_kind": "privacy_boundary",
                    "effect": "block_hook",
                    "strength": "hard",
                    "source_refs": [{"message_id": "msg-c"}],
                },
            ]
            snapshot = materialize_continuity_domains(events, clean_source_dir=clean)
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            empty = cwd / "empty.jsonl"
            empty.write_text("", encoding="utf-8")

            active = active_recall.active_recall_context(
                prompt="continuity domain",
                cwd=cwd,
                agent_self_notes_path=empty,
                working_memory_path=empty,
                continuity_domains_snapshot_path=snapshot_path,
                max_matches=3,
            )
            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 929,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_context",
                        "arguments": {
                            "intent": "continuity domain",
                            "cwd": str(cwd),
                            "continuity_domains_snapshot": str(snapshot_path),
                            "max": 5,
                        },
                    },
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])

        self.assertEqual(active["surface_counts"]["continuity_domains"], 0)
        self.assertNotIn("continuity_domain", {route.get("kind") for route in active["source_reopen_routes"]})
        self.assertNotIn("continuity_domain", {route.get("kind") for route in payload["routes"]})

    def test_mcp_context_returns_domain_route_and_deepen_opens_source_trail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(_domain_events(), clean_source_dir=clean)
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

            context_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 926,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_context",
                        "arguments": {
                            "intent": "source trail continuity domain",
                            "cwd": str(cwd),
                            "continuity_domains_snapshot": str(snapshot_path),
                            "max": 5,
                        },
                    },
                }
            )
            context_payload = json.loads(context_response["result"]["content"][0]["text"])
            raw_context = json.dumps(context_payload, ensure_ascii=False)
            handle = context_payload["routes"][0]["handle"]

            deepen_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 927,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": handle,
                            "cwd": str(cwd),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            deepen_payload = json.loads(deepen_response["result"]["content"][0]["text"])

        self.assertEqual(context_payload["routes"][0]["kind"], "continuity_domain")
        self.assertEqual(context_payload["routes"][0]["suggested_next"]["tool"], "recall_deepen")
        self.assertNotIn("durable working conclusion layer", raw_context)
        self.assertEqual(deepen_payload["support_level"], "evidence")
        self.assertEqual(deepen_payload["domain_brief"]["domain_id"], "cd-source-trailed-continuity")
        self.assertEqual(deepen_payload["domain_brief"]["source_refs"][0]["message_id"], "msg-c")
        self.assertIn("durable working conclusion layer", deepen_payload["domain_brief"]["working_conclusion_short"])
        self.assertIn(
            "pointer-only",
            json.dumps(deepen_payload["source_window"], ensure_ascii=False),
        )

    def test_mcp_rejects_bare_continuity_domain_handle_without_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)

            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 930,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": {
                                "kind": "continuity_domain",
                                "domain_id": "cd-source-trailed-continuity",
                            },
                            "cwd": str(cwd),
                        },
                    },
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "malformed_recall_handle")

    def test_situation_glyph_is_direction_only_and_pathlet_order_sensitive(self) -> None:
        signals = [
            {
                "producer": "dream",
                "signal_kind": "journey_bridge_hypothesis",
                "signal_labels": ["unfinished source trail"],
                "signal_detail": "This is a hypothesis, not a fact.",
                "source_refs": [{"message_id": "msg-a"}],
            },
            {
                "producer": "hexagram",
                "signal_kind": "hexagram_atmosphere_arc",
                "signal_labels": ["transition"],
                "source_refs": [{"message_id": "msg-b"}],
            },
            {
                "producer": "cognitive_map",
                "signal_kind": "topology_route",
                "signal_labels": ["continuity topology"],
                "source_refs": [{"message_id": "msg-c"}],
            },
        ]
        forward = [{"pathlet_id": "p", "ordered_source_refs": [{"message_id": "msg-a"}, {"message_id": "msg-b"}]}]
        backward = [{"pathlet_id": "p", "ordered_source_refs": [{"message_id": "msg-b"}, {"message_id": "msg-a"}]}]

        first = project_situation_glyph(signals=signals, pathlets=forward)
        second = project_situation_glyph(signals=signals, pathlets=backward)
        blocked = project_situation_glyph(
            signals=signals,
            pathlets=forward,
            pinned_boundaries=[{"kind": "privacy_boundary", "effect": "suppress_domain"}],
        )

        self.assertEqual(first["action_grammar"], ACTION_DIRECTION_ONLY)
        self.assertFalse(first["foreground_eligible"])
        self.assertIn("glyph_is_fact", first["cannot_claim"])
        self.assertNotEqual(first["glyph_id"], second["glyph_id"])
        self.assertEqual(blocked["action_grammar"], ACTION_IGNORE_OR_BLOCKED)


if __name__ == "__main__":
    unittest.main()
