from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import prompt as hook  # noqa: E402
from tests.aippocampus.redaction_fixtures import fake_test_windows_path  # noqa: E402


class QueryPatternRoutesPromptHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_semantic_gate = os.environ.get("AIPPOCAMPUS_SEMANTIC_GATE")
        os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = "off"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:test-old",
                            "title": "old-thread",
                            "workspace_name": "old-thread",
                            "keywords": ["外置海马体"],
                            "summary": "旧线程讨论过外置海马体和预热路由。",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_semantic_gate is None:
            os.environ.pop("AIPPOCAMPUS_SEMANTIC_GATE", None)
        else:
            os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = self.old_semantic_gate

    def test_default_hook_emits_scent_without_alias_as_evidence(self) -> None:
        routes = self.registry.parent / "query_pattern_routes.jsonl"
        private_alias = "内部 canonical 海马体预热"
        routes.write_text(
            json.dumps(
                {
                    "query_aliases": [
                        private_alias,
                        fake_test_windows_path("query-pattern-source.jsonl"),
                    ],
                    "source_generation_digest": "gen-alpha-v2",
                    "thread_key_hash": "thread_alpha_hash",
                    "source_refs": [
                        {
                            "source_id": "clean:qp:m7",
                            "thread_key": "session:test-old",
                            "message_id": "m7",
                            "line": 14,
                            "snippet": "raw private source text must not leak",
                            "path": fake_test_windows_path("private-query-pattern.jsonl"),
                        }
                    ],
                    "created_unix": 1_800_000_000,
                    "ttl_seconds": 600,
                    "confidence": 0.92,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "海马体预热",
            cwd=self.workspace,
            registry_path=self.registry,
            use_semantic_gate=False,
            search_budget=0,
        )
        public = hook.public_hook_debug_payload(result)
        encoded_public = json.dumps(public, ensure_ascii=False, sort_keys=True)
        context = hook.context_for_hook(result) or ""
        encoded_context = json.dumps(context, ensure_ascii=False)

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("query pattern routes", " ".join(result["reasons"]))
        self.assertEqual(result["candidates"][0]["thread_key"], "session:test-old")
        self.assertEqual(
            result["hot_path_funnel"]["query_pattern_routes"]["diagnostics"][
                "live_llm_call_count"
            ],
            0,
        )
        self.assertEqual(
            public["hot_path_funnel"]["query_pattern_routes"]["selected_count"],
            1,
        )
        self.assertIn("Ambient recall scent", context)
        self.assertNotIn(private_alias, encoded_public + encoded_context)
        self.assertNotIn("raw private source text", encoded_public + encoded_context)
        self.assertNotIn("private-query-pattern", encoded_public + encoded_context)


if __name__ == "__main__":
    unittest.main()
