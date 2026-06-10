from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import prompt as hook  # noqa: E402
from tests.aippocampus.redaction_fixtures import FAKE_TEST_OPENAI_API_KEY  # noqa: E402


class PromptHookSemanticDiagnosticsTests(unittest.TestCase):
    def test_public_payload_explains_partial_semantic_success_without_raw_worker_details(
        self,
    ) -> None:
        private_result = {
            "decision": "scent",
            "score": 0.88,
            "confidence": "medium",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY],
            "candidates": [{"title": "private title", "thread_key": "session:private"}],
            "evidence": [{"snippet": "private source wording"}],
            "semantic_gate": {
                "available": True,
                "decision": "scent",
                "confidence": 0.82,
                "cached": False,
                "query_aliases": [f"alias {FAKE_TEST_OPENAI_API_KEY}"],
                "workers": [{"raw": "private worker output"}],
                "errors": ["private semantic error"],
                "error_buckets": {"read_timeout": 1, "private_raw_failure": 1},
                "worker_count": 2,
                "successful_worker_count": 1,
                "failed_worker_count": 1,
                "partial_success": True,
                "partial_failure_reasons": ["read_timeout", "private raw failure"],
                "budget": {
                    "requested_timeout": 4.0,
                    "effective_timeout": 2.0,
                    "overall_deadline_seconds": 4.0,
                    "effective_timeout_policy": "worker_socket_timeout_half_of_overall_deadline",
                    "budget_clip_reason": "worker_socket_timeout_policy",
                    "private_budget_note": "do not print",
                },
            },
            "route_delivery_diagnostic": {
                "foreground_profile": "ambient_hot_path",
                "semantic_reuse_source": "semantic_provider_timeout",
                "semantic_waited": True,
                "semantic_partial_failure": True,
                "raw_prompt": "private prompt text",
                "candidate_ids": ["session:private"],
            },
        }

        public = hook.public_hook_debug_payload(private_result)
        encoded = json.dumps(public, ensure_ascii=False)
        semantic = public["semantic_gate"]

        self.assertTrue(semantic["available"])
        self.assertTrue(semantic["partial_success"])
        self.assertEqual(semantic["successful_worker_count"], 1)
        self.assertEqual(semantic["failed_worker_count"], 1)
        self.assertEqual(semantic["partial_failure_reasons"], ["read_timeout"])
        self.assertEqual(semantic["error_buckets"], {"read_timeout": 1})
        self.assertEqual(
            semantic["budget"]["effective_timeout_policy"],
            "worker_socket_timeout_half_of_overall_deadline",
        )
        self.assertEqual(semantic["budget"]["budget_clip_reason"], "worker_socket_timeout_policy")
        self.assertTrue(public["route_delivery_diagnostic"]["semantic_partial_failure"])
        self.assertNotIn("private worker output", encoded)
        self.assertNotIn("private semantic error", encoded)
        self.assertNotIn("private_raw_failure", encoded)
        self.assertNotIn("private_budget_note", encoded)
        self.assertNotIn("private prompt text", encoded)

    def test_foreground_semantic_budget_exposes_timeout_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            registry_path = root / "registry" / "threads.json"
            registry_path.parent.mkdir()
            registry_path.write_text(
                json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            seen: dict[str, float | bool] = {}

            def fake_semantic_gate(prompt: str, **kwargs) -> dict:
                seen["timeout"] = float(kwargs["timeout"])
                seen["deadline_seconds"] = float(kwargs["deadline_seconds"])
                seen["foreground"] = bool(kwargs["foreground"])
                return {
                    "available": False,
                    "decision": "skip",
                    "confidence": 0.0,
                    "query_aliases": [],
                    "memory_scope": [],
                    "reasons": ["test"],
                    "workers": [],
                    "errors": [],
                    "cached": False,
                }

            result = hook.assess_prompt(
                "那个脑内续接器现在怎么样了？",
                cwd=workspace,
                registry_path=registry_path,
                semantic_gate_fn=fake_semantic_gate,
                semantic_timeout=3,
                max_elapsed_ms=3000,
                search_budget=0,
            )

        budget = result["semantic_gate"]["budget"]
        self.assertIn("timeout", seen)
        self.assertTrue(seen["foreground"])
        self.assertEqual(seen["deadline_seconds"], budget["overall_deadline_seconds"])
        self.assertEqual(budget["effective_timeout"], seen["timeout"])
        self.assertEqual(
            budget["effective_timeout_policy"],
            "worker_socket_timeout_half_of_overall_deadline",
        )
        self.assertEqual(budget["budget_clip_reason"], "foreground_post_semantic_reserve")


if __name__ == "__main__":
    unittest.main()
