from __future__ import annotations

import json
import subprocess
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
from aippocampus_runtime.recall.continuity_domain_producer import (  # noqa: E402
    propose_continuity_domain_events_from_registry,
)
from aippocampus_runtime.recall.continuity_domains import (  # noqa: E402
    ACTION_DIRECTION_ONLY,
    ACTION_IGNORE_OR_BLOCKED,
    DERIVED_ONLY_STATUS,
    append_continuity_domain_event,
    continuity_domain_handle,
    continuity_domain_pointer,
    continuity_domain_public_safety_report,
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


def _write_registry_clean_source_fixture(root: Path) -> tuple[Path, Path]:
    registry_dir = root / "registry"
    clean = registry_dir / "threads" / "little-thread" / "clean-source"
    clean.mkdir(parents=True, exist_ok=True)
    messages = [
        {
            "message_id": "msg-real-a",
            "turn_id": "turn-real-a",
            "turn_index": 1,
            "source_line": 2,
            "role": "user",
            "phase": "",
            "text": "AIppocampus 的小海马体应该减少手搜，让 agent 可以沿着 source trail 回来。",
        },
        {
            "message_id": "msg-real-b",
            "turn_id": "turn-real-b",
            "turn_index": 2,
            "source_line": 4,
            "role": "assistant",
            "phase": "final_answer",
            "is_final": True,
            "text": "我理解，小海马体不是无源总结；它要让后来的 agent 少手搜，多回到源头。",
        },
    ]
    with (clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in messages:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (clean / "turns.jsonl").write_text("", encoding="utf-8")
    (registry_dir / "threads.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": "little-thread",
                        "title": "小海马体真实体验",
                        "keywords": ["小海马体", "手搜", "source trail"],
                        "paths": {"clean_source_dir": str(clean)},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return registry_dir, clean


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

    def test_chinese_domain_cues_match_without_spaces(self) -> None:
        events = [
            {
                "event_kind": "domain_created",
                "domain_id": "cd-zh-continuity",
                "title": "长期连续性抽象层",
                "working_conclusion_short": "长期连续性需要能回到源头的抽象层。",
                "activation_cues": ["长期连续性", "找回源头", "抽象层"],
                "scope_labels": ["源头可追溯"],
                "source_refs": [{"message_id": "msg-a"}],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(events, clean_source_dir=clean)

        matches = match_continuity_domain_pointers(
            "我们继续聊长期连续性怎么找回源头",
            snapshot,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["domain_id"], "cd-zh-continuity")

    def test_chinese_domain_cues_do_not_overmatch_unrelated_broad_prompt(self) -> None:
        events = [
            {
                "event_kind": "domain_created",
                "domain_id": "cd-little-hippocampus",
                "title": "小海马体真实体验",
                "activation_cues": ["小海马体", "手搜"],
                "source_refs": [{"message_id": "msg-a"}],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(events, clean_source_dir=clean)

        matches = match_continuity_domain_pointers(
            "今天我们先聊晚饭安排和天气变化",
            snapshot,
        )

        self.assertEqual(matches, [])

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
                            "clean_source_dir": str(clean),
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

    def test_mcp_rejects_fresh_continuity_domain_handle_without_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            snapshot = materialize_continuity_domains(_domain_events(), clean_source_dir=clean)
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            handle = continuity_domain_handle(
                snapshot["domains"][0],
                clean_source_dir=clean,
                snapshot_path=snapshot_path,
            )
            handle["source_refs"] = []

            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 941,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": handle,
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "malformed_recall_handle")

    def test_mcp_deepen_rejects_blocked_domain_handle_even_with_freshness(self) -> None:
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
            handle = continuity_domain_handle(
                snapshot["domains"][0],
                clean_source_dir=clean,
                snapshot_path=snapshot_path,
            )

            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 931,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": handle,
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])

        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "continuity_domain_blocked")

    def test_mcp_deepen_rejects_inactive_domain_statuses_even_with_freshness(self) -> None:
        for status in ("stale", "superseded", "retired"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                cwd = Path(tmp)
                clean = cwd / ".aippocampus" / "clean-source"
                _write_clean_source(clean)
                snapshot = materialize_continuity_domains(
                    [{**_domain_events()[0], "status": status}],
                    clean_source_dir=clean,
                )
                snapshot_path = cwd / "snapshot.json"
                snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
                handle = continuity_domain_handle(
                    snapshot["domains"][0],
                    clean_source_dir=clean,
                    snapshot_path=snapshot_path,
                )

                response = mcp.handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 938,
                        "method": "tools/call",
                        "params": {
                            "name": "recall_deepen",
                            "arguments": {
                                "handle": handle,
                                "cwd": str(cwd),
                                "clean_source_dir": str(clean),
                                "continuity_domains_snapshot": str(snapshot_path),
                            },
                        },
                    }
                )
                payload = json.loads(response["result"]["content"][0]["text"])

                self.assertTrue(response["result"]["isError"])
                self.assertEqual(payload["error"]["code"], "continuity_domain_blocked")

    def test_mcp_deepen_uses_registry_for_cross_thread_domain_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            registry_dir = root / "registry"
            foreign_clean = registry_dir / "threads" / "foreign-thread" / "clean-source"
            foreign_clean.mkdir(parents=True, exist_ok=True)
            foreign_message = {
                "message_id": "foreign-msg",
                "turn_id": "foreign-turn",
                "turn_index": 8,
                "source_line": 12,
                "role": "user",
                "phase": "",
                "text": "Cross-thread source says continuity domains must reopen registry clean source.",
            }
            (foreign_clean / "messages.jsonl").write_text(
                json.dumps(foreign_message, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (foreign_clean / "turns.jsonl").write_text(
                json.dumps(
                    {
                        "turn_id": "foreign-turn",
                        "turn_index": 8,
                        "message_ids": ["foreign-msg"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (registry_dir / "threads.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "foreign-thread",
                                "title": "Foreign thread",
                                "paths": {
                                    "clean_source_dir": str(foreign_clean),
                                    "clean_source_messages_jsonl": str(foreign_clean / "messages.jsonl"),
                                    "clean_source_turns_jsonl": str(foreign_clean / "turns.jsonl"),
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = materialize_continuity_domains(
                [
                    {
                        "event_kind": "domain_created",
                        "domain_id": "cd-cross-thread",
                        "title": "Cross-thread continuity domain",
                        "activation_cues": ["cross-thread", "registry clean source"],
                        "working_conclusion_short": "The route crosses thread stores.",
                        "source_refs": [
                            {
                                "thread_key": "foreign-thread",
                                "message_id": "foreign-msg",
                            }
                        ],
                    }
                ],
            )
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

            context_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 932,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_context",
                        "arguments": {
                            "intent": "cross-thread registry clean source",
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            context_payload = json.loads(context_response["result"]["content"][0]["text"])
            deepen_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 933,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": context_payload["routes"][0]["handle"],
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            deepen_payload = json.loads(deepen_response["result"]["content"][0]["text"])

        self.assertEqual(deepen_payload["status"], "ok")
        self.assertEqual(deepen_payload["source_refs"][0]["thread_key"], "foreign-thread")
        self.assertIn(
            "registry clean source",
            json.dumps(deepen_payload["source_window"], ensure_ascii=False),
        )

    def test_cross_thread_ref_does_not_fall_back_to_current_source_on_id_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            current_rows = [
                {
                    "message_id": "same-msg",
                    "turn_id": "current-turn",
                    "turn_index": 9,
                    "source_line": 14,
                    "role": "user",
                    "phase": "",
                    "text": "CURRENT THREAD TEXT should not satisfy foreign-thread refs.",
                }
            ]
            with (clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
                for row in current_rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            registry_dir = root / "registry"
            foreign_clean = registry_dir / "threads" / "foreign-thread" / "clean-source"
            foreign_clean.mkdir(parents=True, exist_ok=True)
            (foreign_clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "same-msg",
                        "turn_id": "foreign-turn",
                        "turn_index": 8,
                        "source_line": 12,
                        "role": "user",
                        "phase": "",
                        "text": "FOREIGN THREAD TEXT is the only valid evidence.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (foreign_clean / "turns.jsonl").write_text("", encoding="utf-8")
            (registry_dir / "threads.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "foreign-thread",
                                "paths": {"clean_source_dir": str(foreign_clean)},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = materialize_continuity_domains(
                [
                    {
                        "event_kind": "domain_created",
                        "domain_id": "cd-cross-thread-collision",
                        "title": "Cross-thread collision domain",
                        "activation_cues": ["collision domain"],
                        "source_refs": [
                            {
                                "thread_key": "foreign-thread",
                                "message_id": "same-msg",
                            }
                        ],
                    }
                ],
            )
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            context_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 934,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_context",
                        "arguments": {
                            "intent": "collision domain",
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            context_payload = json.loads(context_response["result"]["content"][0]["text"])
            deepen_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 935,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": context_payload["routes"][0]["handle"],
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            deepen_payload = json.loads(deepen_response["result"]["content"][0]["text"])
            encoded_window = json.dumps(deepen_payload["source_window"], ensure_ascii=False)

        self.assertIn("FOREIGN THREAD TEXT", encoded_window)
        self.assertNotIn("CURRENT THREAD TEXT", encoded_window)

    def test_cross_thread_domain_handle_stales_when_registry_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            registry_dir = root / "registry"
            foreign_clean = registry_dir / "threads" / "foreign-thread" / "clean-source"
            foreign_clean.mkdir(parents=True, exist_ok=True)
            foreign_messages = foreign_clean / "messages.jsonl"
            foreign_messages.write_text(
                json.dumps(
                    {
                        "message_id": "foreign-msg",
                        "turn_id": "foreign-turn",
                        "turn_index": 8,
                        "source_line": 12,
                        "role": "user",
                        "phase": "",
                        "text": "Original foreign source text.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (foreign_clean / "turns.jsonl").write_text("", encoding="utf-8")
            (registry_dir / "threads.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "foreign-thread",
                                "paths": {"clean_source_dir": str(foreign_clean)},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = materialize_continuity_domains(
                [
                    {
                        "event_kind": "domain_created",
                        "domain_id": "cd-cross-thread-freshness",
                        "title": "Cross-thread freshness domain",
                        "activation_cues": ["freshness domain"],
                        "source_refs": [
                            {
                                "thread_key": "foreign-thread",
                                "message_id": "foreign-msg",
                            }
                        ],
                    }
                ],
            )
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            context_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 936,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_context",
                        "arguments": {
                            "intent": "freshness domain",
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            context_payload = json.loads(context_response["result"]["content"][0]["text"])
            foreign_messages.write_text(
                json.dumps(
                    {
                        "message_id": "foreign-msg",
                        "turn_id": "foreign-turn",
                        "turn_index": 8,
                        "source_line": 12,
                        "role": "user",
                        "phase": "",
                        "text": "Changed foreign source text.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            deepen_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 937,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": context_payload["routes"][0]["handle"],
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            payload = json.loads(deepen_response["result"]["content"][0]["text"])

        self.assertTrue(deepen_response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "stale_recall_handle")
        self.assertIn(
            "registry_clean_source_fingerprint_changed",
            payload["error"]["details"]["invalidated_by"],
        )

    def test_cross_thread_domain_deepen_validates_only_handle_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            clean = cwd / ".aippocampus" / "clean-source"
            _write_clean_source(clean)
            registry_dir = root / "registry"
            threads = []
            source_refs = []
            for index in range(4):
                thread_key = f"foreign-thread-{index}"
                foreign_clean = registry_dir / "threads" / thread_key / "clean-source"
                foreign_clean.mkdir(parents=True, exist_ok=True)
                (foreign_clean / "messages.jsonl").write_text(
                    json.dumps(
                        {
                            "message_id": f"foreign-msg-{index}",
                            "turn_id": f"foreign-turn-{index}",
                            "turn_index": index + 1,
                            "source_line": index + 2,
                            "role": "user",
                            "phase": "",
                            "text": f"Foreign source text {index}.",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (foreign_clean / "turns.jsonl").write_text("", encoding="utf-8")
                threads.append(
                    {
                        "thread_key": thread_key,
                        "paths": {"clean_source_dir": str(foreign_clean)},
                    }
                )
                source_refs.append(
                    {
                        "thread_key": thread_key,
                        "message_id": f"foreign-msg-{index}",
                    }
                )
            (registry_dir / "threads.json").write_text(
                json.dumps({"schema_version": 1, "threads": threads}, ensure_ascii=False),
                encoding="utf-8",
            )
            snapshot = materialize_continuity_domains(
                [
                    {
                        "event_kind": "domain_created",
                        "domain_id": "cd-many-foreign-refs",
                        "title": "Many foreign refs domain",
                        "activation_cues": ["many foreign refs"],
                        "source_refs": source_refs,
                    }
                ],
            )
            snapshot_path = cwd / "snapshot.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            context_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 939,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_context",
                        "arguments": {
                            "intent": "many foreign refs",
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            context_payload = json.loads(context_response["result"]["content"][0]["text"])
            deepen_response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 940,
                    "method": "tools/call",
                    "params": {
                        "name": "recall_deepen",
                        "arguments": {
                            "handle": context_payload["routes"][0]["handle"],
                            "cwd": str(cwd),
                            "clean_source_dir": str(clean),
                            "registry_dir": str(registry_dir),
                            "continuity_domains_snapshot": str(snapshot_path),
                        },
                    },
                }
            )
            payload = json.loads(deepen_response["result"]["content"][0]["text"])

        self.assertFalse(deepen_response["result"]["isError"])
        self.assertEqual(payload["status"], "ok")
        self.assertLessEqual(len(payload["source_refs"]), 3)

    def test_public_safety_report_counts_redactions(self) -> None:
        snapshot = materialize_continuity_domains(
            [
                {
                    "event_kind": "domain_created",
                    "domain_id": "cd-redaction",
                    "title": "Credential-shaped input",
                    "working_conclusion_short": "api_key=sk-testcontinuitydomainsecret",
                    "source_refs": [{"message_id": "msg-a"}],
                }
            ]
        )

        report = continuity_domain_public_safety_report(snapshot)

        self.assertGreater(report["metrics"]["redaction_count"], 0)

    def test_continuity_domain_cli_append_publish_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean-source"
            _write_clean_source(clean)
            events_path = clean / "continuity-domain-events.jsonl"
            snapshot_dir = root / "continuity-domain-snapshots"

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "continuity-domain",
                    "append",
                    "--events-path",
                    str(events_path),
                    "--clean-source-dir",
                    str(clean),
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--event-json",
                    json.dumps(_domain_events()[0]),
                    "--publish",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            latest = json.loads((snapshot_dir / "latest.json").read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertEqual(latest["snapshot"]["metrics"]["domain_count"], 1)

    def test_continuity_domain_producer_dry_run_reports_public_safe_registry_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_registry_clean_source_fixture(root)

            public_report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=False,
            )
            local_report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=2,
                include_local_detail=True,
            )
            encoded_public = json.dumps(public_report, ensure_ascii=False)

        self.assertTrue(public_report["ok"])
        self.assertEqual(public_report["metrics"]["registered_thread_count"], 1)
        self.assertGreaterEqual(public_report["metrics"]["candidate_domain_count"], 1)
        self.assertEqual(public_report["metrics"]["privacy_suppressed_count"], 0)
        self.assertIn("label_hash", public_report["top_domain_labels"][0])
        self.assertNotIn("小海马体", encoded_public)
        self.assertTrue(local_report["candidate_events"])
        event = local_report["candidate_events"][0]
        self.assertEqual(event["event_kind"], "domain_created")
        self.assertTrue(event["source_refs"])
        self.assertTrue(all(ref.get("thread_key") == "little-thread" for ref in event["source_refs"]))
        self.assertIn("小海马体", event["activation_cues"])

    def test_continuity_domain_producer_uses_signal_rows_only_as_candidate_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_registry_clean_source_fixture(root)
            (registry_dir / "query_pattern_routes.jsonl").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_query_pattern_route",
                        "query_aliases": ["自然召回"],
                        "source_refs": [{"thread_key": "little-thread", "message_id": "msg-real-a"}],
                        "output_authority": "navigation_only",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=1,
                include_local_detail=True,
            )

        signal_events = [
            event for event in report["candidate_events"] if event.get("title") == "自然召回"
        ]
        self.assertEqual(len(signal_events), 1)
        event = signal_events[0]
        self.assertEqual(event["source_refs"][0]["message_id"], "msg-real-a")
        self.assertIn("Registered clean-source history", event["working_conclusion_short"])
        self.assertNotIn("aippocampus_query_pattern_route", json.dumps(event, ensure_ascii=False))

    def test_continuity_domain_producer_can_refresh_reviewed_query_pattern_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_registry_clean_source_fixture(root)
            (registry_dir / "semantic_triggers.jsonl").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_semantic_trigger",
                        "status": "active",
                        "aliases": ["外置小海马"],
                        "source_refs": [{"thread_key": "little-thread", "message_id": "msg-real-a"}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            report = propose_continuity_domain_events_from_registry(
                registry_path=registry_dir / "threads.json",
                min_support=1,
                include_local_detail=True,
                refresh_query_pattern_routes=True,
            )

        refreshed_events = [
            event for event in report["candidate_events"] if event.get("title") == "外置小海马"
        ]
        self.assertEqual(len(refreshed_events), 1)
        self.assertEqual(refreshed_events[0]["source_refs"][0]["message_id"], "msg-real-a")
        self.assertEqual(
            report["query_pattern_refresh"]["metrics"]["alias_source_route_counts"][
                "reviewed_semantic"
            ],
            1,
        )

    def test_continuity_domain_producer_append_publish_enables_real_history_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_registry_clean_source_fixture(root)
            events_path = root / "continuity-domain-events.jsonl"
            snapshot_dir = root / "continuity-domain-snapshots"
            empty = root / "empty.jsonl"
            empty.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "continuity-domain",
                    "produce",
                    "--registry-dir",
                    str(registry_dir),
                    "--events-path",
                    str(events_path),
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--append",
                    "--publish",
                    "--include-local-detail",
                    "--min-support",
                    "2",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            snapshot_path = snapshot_dir / "latest.json"
            result = active_recall.active_recall_context(
                prompt="小海马体现在到底有什么用，能不能别让我手搜？",
                cwd=root,
                registry_path=registry_dir / "threads.json",
                agent_self_notes_path=empty,
                working_memory_path=empty,
                continuity_domains_snapshot_path=snapshot_path,
                max_matches=3,
            )
            raw = json.dumps(result, ensure_ascii=False)

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertGreaterEqual(result["surface_counts"]["continuity_domains"], 1)
        self.assertEqual(result["source_reopen_routes"][-1]["kind"], "continuity_domain")
        self.assertTrue(result["source_boundary"]["source_reopen_required_for_facts"])
        self.assertNotIn("减少手搜", raw)

    def test_continuity_domain_cli_append_auto_refreshes_query_pattern_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir, _clean = _write_registry_clean_source_fixture(root)
            (registry_dir / "semantic_triggers.jsonl").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_semantic_trigger",
                        "status": "active",
                        "aliases": ["外置小海马"],
                        "source_refs": [{"thread_key": "little-thread", "message_id": "msg-real-a"}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            events_path = root / "continuity-domain-events.jsonl"

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "continuity-domain",
                    "produce",
                    "--registry-dir",
                    str(registry_dir),
                    "--events-path",
                    str(events_path),
                    "--append",
                    "--include-local-detail",
                    "--min-support",
                    "1",
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            payload = json.loads(proc.stdout)
            event_rows = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("query_pattern_refresh", payload)
        self.assertTrue(any(row.get("title") == "外置小海马" for row in event_rows))

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
