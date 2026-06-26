from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.contracts import foreground_action_contract_violations
from aippocampus_runtime.recall import agent_continuity
from aippocampus_runtime.recall.agent_recall_cache import (
    write_last_recall_cache,
    write_recall_selector_snapshot,
)
from aippocampus_runtime.recall.continuity_domains import clean_source_fingerprint
from aippocampus_runtime.registry import api as registry
from aippocampus_runtime.source import search
from aippocampus_runtime.source.last_recall_search import search_last_recall_sources


class LastRecallSourceSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self._write_messages(
            self.clean,
            [
                {
                    "id": "msg_final",
                    "message_id": "msg_final",
                    "source_line": 13,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "text": "The baseline current-thread source.",
                }
            ],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_messages(self, clean_dir: Path, messages: list[dict[str, object]]) -> None:
        clean_dir.mkdir(parents=True, exist_ok=True)
        with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for message in messages:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def _write_registry(self, threads: list[dict[str, object]]) -> None:
        (self.cwd / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": threads}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_cache(self, requests: list[dict[str, object]], *, query: str = "route cue") -> Path:
        cache_path = self.cwd / "last-recall.json"
        ok = write_last_recall_cache(
            requests,
            query=query,
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.cwd,
            macro_state_path=None,
            project="fixture",
            max_matches=5,
            schema_version="agent-continuity-path-v1",
            path=cache_path,
        )
        self.assertTrue(ok)
        return cache_path

    def test_search_from_last_recall_returns_hits_from_multiple_routes(self) -> None:
        second_clean = self.cwd / "thread-two" / "clean-source"
        third_clean = self.cwd / "thread-three" / "clean-source"
        self._write_messages(
            second_clean,
            [
                {
                    "id": "msg_second",
                    "message_id": "msg_second",
                    "source_line": 7,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 2,
                    "is_final": True,
                    "text": "The last recall exact phrase lives in the second remembered route.",
                }
            ],
        )
        self._write_messages(
            third_clean,
            [
                {
                    "id": "msg_third",
                    "message_id": "msg_third",
                    "source_line": 8,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 3,
                    "is_final": True,
                    "text": "The last recall exact phrase also appears in the third remembered route.",
                }
            ],
        )
        self._write_registry(
            [
                {
                    "thread_key": "session:two",
                    "title": "Second remembered route",
                    "source_provider": "codex",
                    "paths": {
                        "clean_source_messages_jsonl": str(second_clean / "messages.jsonl")
                    },
                },
                {
                    "thread_key": "session:three",
                    "title": "Third remembered route",
                    "source_provider": "codex",
                    "paths": {
                        "clean_source_messages_jsonl": str(third_clean / "messages.jsonl")
                    },
                },
            ]
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_two",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:two",
                        "route_id": "route_two",
                    },
                },
                {
                    "request_index": 2,
                    "route_id": "route_three",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:three",
                        "route_id": "route_three",
                    },
                },
            ]
        )
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "--recall-selector",
                    str(selector),
                    "last recall exact phrase",
                    "--cwd",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_last_recall_source_search")
        self.assertEqual(payload["search_scope"], "last_recall_candidate_sources")
        self.assertEqual(payload["match_count"], 2)
        self.assertEqual({match["request_index"] for match in payload["matches"]}, {1, 2})
        self.assertEqual(
            payload["foreground_action"]["command"],
            "aippocampus search --open-source --thread-key session:two "
            "--message-id msg_second --line 7 --json",
        )
        self.assertEqual(payload["foreground_action"]["id"], "open_last_recall_search_hit_source_window")
        self.assertNotIn("agent deepen", payload["foreground_action"]["command"])
        self.assertEqual(
            payload["matches"][0]["source_window_command"],
            payload["foreground_action"]["command"],
        )
        self.assertEqual(payload["matches"][0]["source_route"]["recall_selector"], selector)
        self.assertIn(
            f"--recall-selector {selector}",
            payload["safe_next_actions"][0]["command_template"],
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("local_reopen_token", encoded)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(foreground_action_contract_violations(payload), [])

    def test_search_from_last_recall_request_limits_scope(self) -> None:
        one_clean = self.cwd / "thread-one" / "clean-source"
        two_clean = self.cwd / "thread-two" / "clean-source"
        self._write_messages(one_clean, [{"id": "one", "text": "shared exact phrase one"}])
        self._write_messages(two_clean, [{"id": "two", "text": "shared exact phrase two"}])
        self._write_registry(
            [
                {
                    "thread_key": "session:one",
                    "paths": {"clean_source_messages_jsonl": str(one_clean / "messages.jsonl")},
                },
                {
                    "thread_key": "session:two",
                    "paths": {"clean_source_messages_jsonl": str(two_clean / "messages.jsonl")},
                },
            ]
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_one",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:one",
                        "route_id": "route_one",
                    },
                },
                {
                    "request_index": 2,
                    "route_id": "route_two",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:two",
                        "route_id": "route_two",
                    },
                },
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "--request",
                    "2",
                    "shared exact phrase",
                    "--cwd",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["matches"][0]["request_index"], 2)
        self.assertIn("two", payload["matches"][0]["snippet"])

    def test_search_from_last_recall_ranks_exact_hit_before_loud_partial_hit(self) -> None:
        route_clean = self.cwd / "ranking-thread" / "clean-source"
        exact_phrase = "scarlet walnut cicada"
        self._write_messages(
            route_clean,
            [
                {
                    "id": "msg_partial_loud",
                    "message_id": "msg_partial_loud",
                    "source_line": 5,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "scarlet scarlet scarlet walnut walnut walnut "
                        "nearby topic text without the requested adjacent phrase"
                    ),
                },
                {
                    "id": "msg_exact_late",
                    "message_id": "msg_exact_late",
                    "source_line": 31,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": f"prefix filler prefix filler {exact_phrase} suffix filler",
                },
            ],
        )
        self._write_registry(
            [
                {
                    "thread_key": "session:ranking",
                    "paths": {"clean_source_messages_jsonl": str(route_clean / "messages.jsonl")},
                }
            ]
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_ranking",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:ranking",
                        "route_id": "route_ranking",
                    },
                }
            ],
            query=exact_phrase,
        )

        payload = search_last_recall_sources(
            [exact_phrase],
            cwd=self.cwd,
            last_recall_path=cache_path,
            per_route_limit=1,
            limit=1,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["matches"][0]["message_id"], "msg_exact_late")
        self.assertIn("--message-id msg_exact_late", payload["foreground_action"]["command"])
        self.assertNotIn("query_match_profile", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("_query_match_profile", json.dumps(payload, ensure_ascii=False))

    def test_search_from_last_recall_source_ref_hit_opens_exact_source_without_private_path(
        self,
    ) -> None:
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_current_source_ref",
                    "handle": {
                        "kind": "source_ref",
                        "route_id": "route_current_source_ref",
                        "source_refs": [{"message_id": "msg_final", "line": 13}],
                        "source_fingerprint": clean_source_fingerprint(self.clean),
                    },
                }
            ],
            query="baseline current-thread source",
        )
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "--recall-selector",
                    str(selector),
                    "baseline current-thread source",
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["matches"][0]["message_id"], "msg_final")
        self.assertEqual(
            payload["foreground_action"]["id"],
            "open_last_recall_search_hit_source_window",
        )
        self.assertIn(
            "aippocampus search --from-last-recall --open-source --request 1",
            payload["foreground_action"]["command"],
        )
        self.assertIn(f"--recall-selector {selector}", payload["foreground_action"]["command"])
        self.assertIn("--message-id msg_final", payload["foreground_action"]["command"])
        self.assertNotIn("agent deepen", payload["foreground_action"]["command"])
        self.assertNotIn(str(self.cwd), json.dumps(payload, ensure_ascii=False))

        reopen_stdout = io.StringIO()
        with contextlib.redirect_stdout(reopen_stdout):
            reopen_code = search.main(
                [
                    "--from-last-recall",
                    "--open-source",
                    "--request",
                    "1",
                    "--recall-selector",
                    str(selector),
                    "--message-id",
                    "msg_final",
                    "--line",
                    "13",
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        reopened = json.loads(reopen_stdout.getvalue())

        self.assertEqual(reopen_code, 0)
        self.assertEqual(reopened["kind"], "aippocampus_last_recall_source_window")
        self.assertEqual(reopened["source_boundary"]["authority"], "source_open")
        self.assertIn(
            "baseline current-thread source",
            json.dumps(reopened["source_window"], ensure_ascii=False),
        )
        self.assertGreaterEqual(reopened["source_anchor_profile"]["matched_anchor_count"], 1)
        self.assertTrue(reopened["source_anchor_profile"]["exact_phrase_match"])
        self.assertGreaterEqual(len(reopened["anchor_hits"]), 1)
        self.assertNotIn(str(self.cwd), json.dumps(reopened, ensure_ascii=False))

    def test_search_from_last_recall_unopenable_hit_labels_deepen_as_fallback(self) -> None:
        unopenable_clean = self.cwd / "unopenable" / "clean-source"
        self._write_messages(
            unopenable_clean,
            [
                {
                    "role": "assistant",
                    "text": "unopenable exact phrase has no message id or source line",
                }
            ],
        )
        cache_path = self.cwd / "unopenable-last-recall.json"
        ok = write_last_recall_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_unopenable",
                    "handle": {
                        "kind": "source_ref",
                        "route_id": "route_unopenable",
                        "source_refs": [{"turn_id": "missing-selector"}],
                    },
                }
            ],
            query="unopenable exact phrase",
            cwd=self.cwd,
            clean_source_dir=unopenable_clean,
            registry_dir=self.cwd,
            macro_state_path=None,
            project="fixture",
            max_matches=5,
            schema_version="agent-continuity-path-v1",
            path=cache_path,
        )
        self.assertTrue(ok)
        # The route context points to a non-default clean source. This creates a
        # real match but deliberately no selector that can reopen the exact row.
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "--recall-selector",
                    str(selector),
                    "unopenable exact phrase",
                    "--cwd",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["matches"][0]["source_open_state"], "exact_hit_unopenable")
        self.assertEqual(
            payload["foreground_action"]["id"],
            "deepen_unopenable_last_recall_search_hit",
        )
        self.assertIn("fallback", payload["foreground_action"]["why"])
        self.assertNotIn("opens the exact", payload["foreground_action"]["why"])

    def test_search_from_last_recall_no_match_stays_inside_recalled_routes(self) -> None:
        recalled_clean = self.cwd / "recalled" / "clean-source"
        outside_clean = self.cwd / "outside" / "clean-source"
        self._write_messages(recalled_clean, [{"id": "msg_recalled", "text": "only recalled route text"}])
        self._write_messages(
            outside_clean,
            [{"id": "msg_outside", "text": "outside registry phrase should not leak in"}],
        )
        self._write_registry(
            [
                {
                    "thread_key": "session:recalled",
                    "paths": {
                        "clean_source_messages_jsonl": str(recalled_clean / "messages.jsonl")
                    },
                },
                {
                    "thread_key": "session:outside",
                    "paths": {
                        "clean_source_messages_jsonl": str(outside_clean / "messages.jsonl")
                    },
                },
            ]
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_recalled",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:recalled",
                        "route_id": "route_recalled",
                    },
                }
            ]
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "outside registry phrase",
                    "--cwd",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_matches")
        self.assertEqual(payload["match_count"], 0)
        self.assertEqual(payload["searched_route_count"], 1)
        self.assertEqual(payload["source_boundary"]["authority"], "direction_only")
        self.assertEqual(payload["foreground_action"]["id"], "refine_last_recall_exact_search")
        self.assertNotIn("outside registry phrase should not leak in", json.dumps(payload))

    def test_search_from_last_recall_source_growth_warns_but_still_opens_hit(self) -> None:
        fingerprint = clean_source_fingerprint(self.clean)
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_stale",
                    "handle": {
                        "kind": "source_ref",
                        "route_id": "route_stale",
                        "source_refs": [{"message_id": "msg_final"}],
                        "source_fingerprint": fingerprint,
                    },
                }
            ],
            query="stale cue",
        )
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"id": "msg_new", "text": "changed source"}, ensure_ascii=False) + "\n")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "baseline",
                    "--cwd",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
        )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["matches"][0]["message_id"], "msg_final")
        self.assertEqual(
            payload["foreground_action"]["id"],
            "open_last_recall_search_hit_source_window",
        )
        self.assertIn(
            "stale_recall_handle",
            {warning["code"] for warning in payload["warnings"]},
        )
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertIn("--from-last-recall --open-source", payload["foreground_action"].get("command", ""))
        self.assertNotIn("--last-recall", payload["foreground_action"].get("command", ""))
        self.assertNotIn(str(self.cwd), json.dumps(payload, ensure_ascii=False))

    def test_search_from_last_recall_missing_source_returns_recovery(self) -> None:
        self._write_registry(
            [
                {
                    "thread_key": "session:missing-source",
                    "paths": {
                        "clean_source_messages_jsonl": str(
                            self.cwd / "missing" / "clean-source" / "messages.jsonl"
                        )
                    },
                }
            ]
        )
        cache_path = self._write_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_missing",
                    "handle": {
                        "kind": "thread_candidate",
                        "thread_key": "session:missing-source",
                        "route_id": "route_missing",
                    },
                }
            ],
            query="missing source cue",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "anything",
                    "--cwd",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "routes_not_searchable")
        self.assertEqual(payload["error"]["code"], "last_recall_sources_unavailable")
        self.assertEqual(payload["unavailable_request_count"], 1)
        self.assertEqual(
            payload["foreground_action"]["id"],
            "rerun_recall_for_fresh_search_set",
        )
        self.assertNotIn("agent deepen", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(str(self.cwd), json.dumps(payload, ensure_ascii=False))

    def test_search_from_last_recall_invalid_selector_uses_contextual_recovery(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--from-last-recall",
                    "foo",
                    "--recall-selector",
                    "sel_bogus",
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cannot_verify")
        self.assertEqual(payload["error"]["code"], "invalid_recall_selector")
        self.assertEqual(payload["foreground_action"]["id"], "rerun_recall_for_fresh_search_set")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("search_all_registered_sources", action_ids)
        self.assertIn("search_mutable_last_recall_without_selector", action_ids)
        self.assertNotIn("inspect_cli_help", action_ids)
        self.assertNotIn("aippocampus --help", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(foreground_action_contract_violations(payload), [])

    def test_registry_audit_reports_redacted_source_reachability_counts(self) -> None:
        raw = self.cwd / "raw-rollout.jsonl"
        raw.write_text("[]\n", encoding="utf-8")
        sqlite = self.cwd / "source_index.sqlite"
        sqlite.write_text("", encoding="utf-8")
        self._write_registry(
            [
                {
                    "thread_key": "session:reachable",
                    "source_provider": "codex",
                    "paths": {
                        "rollout": str(raw),
                        "clean_source_messages_jsonl": str(self.clean / "messages.jsonl"),
                        "sqlite": str(sqlite),
                    },
                },
                {
                    "thread_key": "session:missing",
                    "source_provider": "codex",
                    "paths": {"rollout": str(self.cwd / "missing.jsonl")},
                },
            ]
        )

        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["registry.py", "--registry-dir", str(self.cwd), "audit", "--json"],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = registry.main()
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_registry_source_reachability_audit")
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(
            payload["counts"],
            {
                "registry_rows": 2,
                "provider_known_rows": 2,
                "raw_source_reachable_rows": 1,
                "clean_source_reachable_rows": 1,
                "indexed_rows": 1,
                "deepenable_rows": 1,
            },
        )
        self.assertNotIn(str(self.cwd), json.dumps(payload, ensure_ascii=False))
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(foreground_action_contract_violations(payload), [])

    def test_registry_backed_recall_to_deepen_smoke_uses_fresh_last_recall_cache(self) -> None:
        registry_clean = self.cwd / "registry-smoke" / "clean-source"
        self._write_messages(
            registry_clean,
            [
                {
                    "id": "msg_registry_smoke",
                    "message_id": "msg_registry_smoke",
                    "source_line": 9,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 4,
                    "is_final": True,
                    "text": "The registry-backed recall deepen smoke phrase is reopenable.",
                }
            ],
        )
        self._write_registry(
            [
                {
                    "thread_key": "session:registry-smoke",
                    "title": "registry-backed recall deepen smoke phrase",
                    "source_provider": "codex",
                    "keywords": ["registry-backed", "smoke", "phrase"],
                    "paths": {
                        "clean_source_messages_jsonl": str(registry_clean / "messages.jsonl")
                    },
                }
            ]
        )
        cache_path = self.cwd / "fresh-last-recall.json"

        recall_stdout = io.StringIO()
        with contextlib.redirect_stdout(recall_stdout):
            recall_code = agent_continuity.main(
                [
                    "recall",
                    "registry-backed recall deepen smoke phrase",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.clean),
                    "--registry-dir",
                    str(self.cwd),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ]
            )
        recall_payload = json.loads(recall_stdout.getvalue())

        deepen_stdout = io.StringIO()
        with contextlib.redirect_stdout(deepen_stdout):
            deepen_code = agent_continuity.main(
                [
                    "deepen",
                    "--request",
                    "1",
                    "--last-recall",
                    "--last-recall-path",
                    str(cache_path),
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.clean),
                    "--registry-dir",
                    str(self.cwd),
                    "--json",
                    "--detail",
                    "full",
                ]
            )
        deepen_payload = json.loads(deepen_stdout.getvalue())

        self.assertEqual(recall_code, 0)
        self.assertTrue(cache_path.exists())
        self.assertNotIn("last_recall_cache_available", recall_payload)
        self.assertNotIn("route_count", recall_payload)
        self.assertGreaterEqual(len(recall_payload["routes"]), 1)
        self.assertEqual(recall_payload["routes"][0]["label"], "Registry source route")
        self.assertIn("agent deepen --request 1", recall_payload["foreground_action"]["command"])
        self.assertEqual(deepen_code, 0)
        self.assertEqual(deepen_payload["result"]["status"], "ok")
        self.assertTrue(deepen_payload["result"]["metrics"]["source_reopen_success"])
        self.assertIn(
            "registry-backed recall deepen smoke phrase",
            json.dumps(deepen_payload["result"]["source_window"], ensure_ascii=False),
        )

if __name__ == "__main__":
    unittest.main()
