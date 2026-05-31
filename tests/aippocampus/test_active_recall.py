from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import active_recall  # noqa: E402
import retrieval  # noqa: E402
from aippocampus_runtime.recall import active_recall as packaged_active_recall  # noqa: E402


class ActiveRecallTests(unittest.TestCase):
    def test_main_uses_health_report_api_without_health_script_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            old_argv = sys.argv[:]
            sys.argv = [
                "active_recall.py",
                "继续刚才那个状态",
                "--cwd",
                str(cwd),
                "--search",
                "never",
                "--json",
            ]
            try:
                with mock.patch.object(
                    packaged_active_recall,
                    "health_report",
                    return_value={
                        "status": "ok",
                        "index": {"stale": False},
                        "segments": {"exists": False, "needed": False},
                        "checkpoint": {"due": False},
                        "graphify": {"stale": False},
                        "recommended_actions": [],
                    },
                ) as health, mock.patch.object(packaged_active_recall, "run_json") as run_json:
                    with mock.patch("sys.stdout") as stdout:
                        code = packaged_active_recall.main()
            finally:
                sys.argv = old_argv

        self.assertEqual(code, 0)
        health.assert_called_once_with(cwd)
        run_json.assert_not_called()
        output = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertFalse(json.loads(output)["searched"])

    def test_profile_prompt_searches_with_stale_checkpoint_and_alias_terms(self) -> None:
        prompt = "你知道我的简历和领英资料吗？"
        health = {
            "index": {"stale": True},
            "checkpoint": {"due": True},
            "recommended_actions": [],
        }

        decision = retrieval.active_recall_decision(prompt, [], health)
        query_terms = active_recall.active_recall_query_terms(prompt)
        search_terms = active_recall.search_terms_from_query(query_terms, prompt)

        self.assertEqual(decision["decision"], "search")
        self.assertIn("personal-profile recall cue", " ".join(decision["reasons"]))
        self.assertIn("resume", query_terms)
        self.assertIn("LinkedIn", query_terms)
        self.assertIn("resume", search_terms)
        self.assertIn("LinkedIn", search_terms)

    def test_life_wide_work_prompt_searches_with_stale_checkpoint_and_alias_terms(self) -> None:
        prompt = "最近工作上那些摩擦和压力，我们后来怎么处理比较好？"
        health = {
            "index": {"stale": True},
            "checkpoint": {"due": True},
            "recommended_actions": [],
        }

        decision = retrieval.active_recall_decision(prompt, [], health)
        query_terms = active_recall.active_recall_query_terms(prompt)
        search_terms = active_recall.search_terms_from_query(query_terms, prompt)

        self.assertEqual(decision["decision"], "search")
        self.assertIn("life-wide recall cue", " ".join(decision["reasons"]))
        self.assertIn("workflow friction", query_terms)
        self.assertIn("work pressure", query_terms)
        self.assertIn("burnout", query_terms)
        self.assertIn("workflow friction", search_terms)
        self.assertIn("work pressure", search_terms)

    def test_recent_work_status_alone_does_not_become_life_wide_route(self) -> None:
        prompt = "最近工作进度怎么样？"
        health = {
            "index": {"stale": False},
            "checkpoint": {"due": False},
            "recommended_actions": [],
        }

        decision = retrieval.active_recall_decision(prompt, [], health)
        query_terms = active_recall.active_recall_query_terms(prompt)

        self.assertEqual(decision["decision"], "skip")
        self.assertNotIn("workflow friction", query_terms)
        self.assertNotIn("work pressure", query_terms)


if __name__ == "__main__":
    unittest.main()
