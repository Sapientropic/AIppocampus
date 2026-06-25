from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.recall import continuity_domain_cli
from tests.aippocampus.cli_fixtures import write_continuity_domain_registry


class ContinuityDomainCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def write_registry(
        self,
        root: Path,
        *,
        thread_count: int,
    ) -> Path:
        return write_continuity_domain_registry(
            root,
            thread_count=thread_count,
            message_text=(
                "provider orchestration continuity route needs "
                "source-backed operator review before append publish"
            ),
        )

    def test_default_produce_json_is_bounded_preview_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = self.write_registry(Path(tmp), thread_count=12)
            proc = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--json",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["detail"], "agent_preview")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertIn("route_value", payload)
        self.assertIn("current_uncertainty", payload)
        self.assertIn("summary_metrics", payload)
        self.assertEqual(
            payload["preview_scan_policy"]["mode"],
            "foreground_bounded_default",
        )
        self.assertEqual(payload["metrics"]["registered_thread_count"], 12)
        self.assertEqual(payload["summary_metrics"]["registered_thread_count"], 12)
        self.assertEqual(payload["metrics"]["considered_thread_count"], 8)
        self.assertEqual(payload["metrics"]["scanned_thread_count"], 8)
        self.assertTrue(payload["metrics"]["scan_partial"])
        self.assertTrue(payload["candidate_previews"])
        self.assertIn("preview_boundary", payload)
        self.assertNotIn("candidate_events", payload)
        self.assertEqual(payload["mode"], "dry_run")

    def test_explicit_produce_scan_options_keep_operator_backfill_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_registry(root, thread_count=12)
            events_path = root / "continuity-domain-events.jsonl"
            broad = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--broad-scan",
                "--json",
            )
            bounded = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--max-threads",
                "3",
                "--json",
            )
            append = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "produce",
                "--append",
                "--events-path",
                str(events_path),
                "--json",
            )

        self.assertEqual(broad.returncode, 0, broad.stderr)
        broad_payload = json.loads(broad.stdout)
        self.assertEqual(broad_payload["metrics"]["considered_thread_count"], 12)
        self.assertFalse(broad_payload["metrics"]["scan_partial"])
        self.assertNotIn("candidate_events", broad_payload)

        self.assertEqual(bounded.returncode, 0, bounded.stderr)
        bounded_payload = json.loads(bounded.stdout)
        self.assertEqual(bounded_payload["metrics"]["considered_thread_count"], 3)
        self.assertTrue(bounded_payload["metrics"]["scan_partial"])
        self.assertEqual(bounded_payload["scan_policy"]["max_threads"], 3)
        self.assertNotIn("candidate_events", bounded_payload)

        self.assertEqual(append.returncode, 0, append.stderr)
        append_payload = json.loads(append.stdout)
        self.assertEqual(append_payload["mode"], "append")
        self.assertEqual(append_payload["metrics"]["considered_thread_count"], 12)
        self.assertFalse(append_payload["metrics"]["scan_partial"])
        self.assertGreater(append_payload["write_report"]["appended_event_count"], 0)

    def test_empty_snapshot_json_uses_structured_safe_next_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("continuity-domain", "--cwd", tmp, "list", "--json")
            latest = self.run_cli("continuity-domain", "--cwd", tmp, "latest", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(latest.returncode, 0, latest.stderr)
        for payload in (json.loads(proc.stdout), json.loads(latest.stdout)):
            self.assertEqual(payload["status"], "empty")
            self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
            self.assertNotIn("agent_next_action", payload)
            self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
            self.assertIsInstance(payload["foreground_action"], dict)
            self.assertIn("safe_next_actions", payload)
            self.assertNotIn("recovery_actions", payload)
            recall = next(
                action for action in payload["safe_next_actions"] if action["id"] == "ordinary_recall_path"
            )
            self.assertEqual(recall["requires"], ["cue"])
            self.assertIn("{cue}", recall["command_template"])
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("<cue>", encoded)

    def test_agent_preview_filters_path_and_identity_cues_from_default_projection(self) -> None:
        payload = {
            "ok": True,
            "mode": "dry_run",
            "metrics": {},
            "top_domain_labels": [],
            "candidate_events": [
                {
                    "domain_id": "private-path-route",
                    "title": "AIppocampus workspace route",
                    "domain_type": "maintenance",
                    "scale": "thread",
                    "activation_cues": [
                        "SDY",
                        "Claude长期空间",
                        "单道杨",
                        "provider orchestration route",
                    ],
                    "source_refs": [{"message_id": "msg-1"}],
                }
            ],
        }

        preview = continuity_domain_cli._producer_agent_preview(payload)
        encoded = json.dumps(preview["candidate_previews"], ensure_ascii=False)

        self.assertNotIn("SDY", encoded)
        self.assertNotIn("Claude长期空间", encoded)
        self.assertNotIn("单道杨", encoded)
        self.assertIn("provider orchestration route", encoded)
        self.assertIn(
            preview["candidate_previews"][0].get("candidate_detail_deferred", []),
            (["path_or_identity_cues_filtered"], ["some_activation_cues_filtered"]),
        )

    def test_agent_preview_does_not_promote_low_information_cues_to_recall_commands(self) -> None:
        payload = {
            "ok": True,
            "mode": "dry_run",
            "metrics": {},
            "top_domain_labels": [],
            "candidate_events": [
                {
                    "domain_id": "runtime-noise",
                    "title": "AIppocampus 锚点",
                    "domain_type": "maintenance",
                    "scale": "thread",
                    "activation_cues": ["锚点", "--append", "runtime-contract.md"],
                    "source_refs": [{"message_id": "msg-1"}],
                }
            ],
        }

        preview = continuity_domain_cli._producer_agent_preview(payload)

        self.assertEqual(preview["foreground_candidate_quality"], "needs_broader_scan")
        self.assertNotIn("agent_next_action", preview)
        self.assertEqual(preview["foreground_action"]["id"], "needs_broader_scan_or_cue")
        candidates = preview["candidate_previews"]
        self.assertEqual(candidates[0]["foreground_candidate_quality"], "low_information")
        self.assertEqual(candidates[0]["foreground_actions"], [])

    def test_agent_preview_rejects_hostname_and_cjk_continuation_cues(self) -> None:
        payload = {
            "ok": True,
            "mode": "dry_run",
            "metrics": {
                "scan_partial": True,
                "low_information_label_suppressed_count": 4,
            },
            "top_domain_labels": [],
            "candidate_events": [
                {
                    "domain_id": "hostname-route",
                    "title": "github.com",
                    "domain_type": "maintenance",
                    "scale": "thread",
                    "activation_cues": ["github.com", "不是", "刚才", "不过", "AIppocampus"],
                    "source_refs": [{"message_id": "msg-1"}],
                }
            ],
        }

        preview = continuity_domain_cli._producer_agent_preview(payload)

        self.assertEqual(preview["foreground_candidate_quality"], "needs_broader_scan")
        self.assertEqual(preview["foreground_action"]["id"], "needs_broader_scan_or_cue")
        self.assertIn("--broad-scan", preview["foreground_action"]["command"])
        encoded_action = json.dumps(preview["foreground_action"], ensure_ascii=False)
        self.assertNotIn("agent recall", encoded_action)
        candidate = preview["candidate_previews"][0]
        self.assertEqual(candidate["foreground_candidate_quality"], "low_information")
        self.assertEqual(candidate["foreground_actions"], [])
        self.assertIn(candidate["suppression_reason"], {"hostname_or_domain", "generic_tool_word"})

    def test_agent_preview_rejects_real_registry_noise_shape_from_issue_2668(self) -> None:
        payload = {
            "ok": True,
            "mode": "dry_run",
            "metrics": {
                "scan_partial": True,
                "missing_source_ref_count": 1573,
                "low_information_label_suppressed_count": 24122,
            },
            "top_domain_labels": [],
            "candidate_events": [
                {
                    "domain_id": "project-name-route",
                    "title": "AIppocampus",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["压缩"],
                    "source_refs": [{"message_id": "msg-1"}],
                },
                {
                    "domain_id": "hostname-route",
                    "title": "github.com",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["comment](https"],
                    "source_refs": [{"message_id": "msg-2"}],
                },
                {
                    "domain_id": "cjk-function-word-route",
                    "title": "不是",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["压缩"],
                    "source_refs": [{"message_id": "msg-3"}],
                },
                {
                    "domain_id": "broad-contract-word-route",
                    "title": "source-backed",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["压缩"],
                    "source_refs": [{"message_id": "msg-4"}],
                },
                {
                    "domain_id": "branch-token-route",
                    "title": "main",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["main"],
                    "source_refs": [{"message_id": "msg-6"}],
                },
                {
                    "domain_id": "local-env-route",
                    "title": "aippocampus",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["本机"],
                    "source_refs": [{"message_id": "msg-5"}],
                },
            ],
        }

        preview = continuity_domain_cli._producer_agent_preview(payload)

        self.assertEqual(preview["foreground_candidate_quality"], "needs_broader_scan")
        self.assertEqual(preview["foreground_action"]["id"], "needs_broader_scan_or_cue")
        self.assertIn("--broad-scan", preview["foreground_action"]["command"])
        encoded_action = json.dumps(preview["foreground_action"], ensure_ascii=False)
        self.assertNotIn("agent recall", encoded_action)
        for cue in ("压缩", "comment](https", "本机"):
            self.assertNotIn(cue, encoded_action)
        self.assertNotIn("agent recall main", encoded_action)
        for candidate in preview["candidate_previews"]:
            self.assertEqual(candidate["foreground_candidate_quality"], "low_information")
            self.assertEqual(candidate["foreground_actions"], [])
            self.assertIn("suppression_reason", candidate)

    def test_agent_preview_rejects_mixed_generic_weak_cues_from_issue_2717(self) -> None:
        payload = {
            "ok": True,
            "mode": "dry_run",
            "metrics": {
                "scan_partial": True,
                "low_information_label_suppressed_count": 24122,
            },
            "top_domain_labels": [],
            "candidate_events": [
                {
                    "domain_id": "generic-project-plus-weak-judgment",
                    "title": "AIppocampus",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["AIppocampus", "source-backed", "结论", "他又更新", "DeepSeek"],
                    "source_refs": [{"message_id": "msg-1"}],
                },
                {
                    "domain_id": "generic-source-plus-weak-truth",
                    "title": "source-backed",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["source-backed", "AIppocampus", "真实", "fresh-thread", "---"],
                    "source_refs": [{"message_id": "msg-2"}],
                },
                {
                    "domain_id": "punctuation-title-plus-weak-strength",
                    "title": "---",
                    "domain_type": "recurring_question",
                    "scale": "meso",
                    "activation_cues": ["---", "AIppocampus", "source-backed", "很强", "公开", "**AIppocampus"],
                    "source_refs": [{"message_id": "msg-3"}],
                },
            ],
        }

        preview = continuity_domain_cli._producer_agent_preview(payload)

        self.assertEqual(preview["foreground_candidate_quality"], "needs_broader_scan")
        self.assertEqual(preview["foreground_action"]["id"], "needs_broader_scan_or_cue")
        encoded = json.dumps(preview, ensure_ascii=False)
        for weak_command in (
            "agent recall '结论'",
            "agent recall '真实'",
            "agent recall '很强'",
            "agent recall 结论",
            "agent recall 真实",
            "agent recall 很强",
        ):
            self.assertNotIn(weak_command, encoded)
        for candidate in preview["candidate_previews"]:
            self.assertEqual(candidate["foreground_candidate_quality"], "low_information")
            self.assertEqual(candidate["foreground_actions"], [])
            self.assertIn("suppression_reason", candidate)

    def test_agent_preview_skips_low_information_cues_before_using_specific_route_cue(self) -> None:
        payload = {
            "ok": True,
            "mode": "dry_run",
            "metrics": {},
            "top_domain_labels": [],
            "candidate_events": [
                {
                    "domain_id": "provider-route",
                    "title": "AIppocampus maintenance",
                    "domain_type": "recurring_question",
                    "scale": "thread",
                    "activation_cues": ["锚点", "Sapientropic", "--append", "provider orchestration route"],
                    "source_refs": [{"message_id": "msg-1"}],
                }
            ],
        }

        preview = continuity_domain_cli._producer_agent_preview(payload)

        self.assertEqual(preview["foreground_candidate_quality"], "actionable")
        command = preview["foreground_action"]["command"]
        self.assertIn("provider orchestration route", command)
        self.assertNotIn("锚点", command)
        self.assertNotIn("Sapientropic", command)
        self.assertNotIn("--append", command)

    def test_latest_list_and_append_require_resolvable_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean-source"
            clean.mkdir()
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg_domain",
                        "source_id": "source_domain",
                        "text": "continuity domain source anchor",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            events = clean / "continuity-domain-events.jsonl"
            snapshots = root / "snapshots"
            event = json.dumps(
                {
                    "event_kind": "domain_created",
                    "title": "Durable route for domain read",
                    "domain_type": "recurring_question",
                    "source_refs": [{"message_id": "msg_domain"}],
                }
            )
            append = self.run_cli(
                "continuity-domain",
                "--cwd",
                str(root),
                "append",
                "--events-path",
                str(events),
                "--clean-source-dir",
                str(clean),
                "--snapshot-dir",
                str(snapshots),
                "--event-json",
                event,
                "--publish",
                "--json",
            )
            latest = self.run_cli(
                "continuity-domain",
                "--cwd",
                str(root),
                "latest",
                "--snapshot-dir",
                str(snapshots),
                "--json",
            )
            listed = self.run_cli(
                "continuity-domain",
                "--cwd",
                str(root),
                "list",
                "--snapshot-dir",
                str(snapshots),
                "--json",
            )
            missing = self.run_cli(
                "continuity-domain",
                "--cwd",
                str(root),
                "latest",
                "--snapshot-dir",
                str(root / "missing-snapshots"),
                "--json",
            )
            unresolved_events = root / "unresolved-events.jsonl"
            unresolved = self.run_cli(
                "continuity-domain",
                "--cwd",
                str(root),
                "append",
                "--events-path",
                str(unresolved_events),
                "--event-json",
                json.dumps(
                    {
                        "event_kind": "domain_created",
                        "title": "Fake unresolved refs",
                        "domain_type": "recurring_question",
                        "source_refs": [{"message_id": "fake-missing-message"}],
                    }
                ),
                "--json",
            )

        self.assertEqual(append.returncode, 0, append.stderr)
        self.assertEqual(latest.returncode, 0, latest.stderr)
        latest_payload = json.loads(latest.stdout)
        encoded_latest = json.dumps(latest_payload, ensure_ascii=False)
        self.assertEqual(latest_payload["status"], "ok")
        self.assertEqual(latest_payload["summary"]["domain_count"], 1)
        self.assertTrue(latest_payload["domains"][0]["source_reopen_required_before_claim"])
        self.assertNotIn(str(root), encoded_latest)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(json.loads(listed.stdout)["snapshot_count"], 1)
        self.assertEqual(missing.returncode, 0, missing.stderr)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(missing_payload["status"], "empty")
        self.assertIn("safe_next_actions", missing_payload)
        self.assertNotIn("recovery_actions", missing_payload)
        encoded_missing = json.dumps(missing_payload, ensure_ascii=False)
        self.assertIn("aippocampus agent recall", encoded_missing)
        self.assertNotIn("<cue>", encoded_missing)
        self.assertNotEqual(unresolved.returncode, 0)
        unresolved_payload = json.loads(unresolved.stdout)
        self.assertIn("--clean-source-dir", unresolved_payload["error"]["message"])
        self.assertFalse(unresolved_events.exists())

    def test_read_path_help_is_action_card_not_bare_argparse(self) -> None:
        latest = self.run_cli("continuity-domain", "latest", "--help")
        listed = self.run_cli("continuity-domain", "list", "--help")
        report = self.run_cli("continuity-domain", "report", "--help")

        for proc in (latest, listed, report):
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Read-path action card", proc.stdout)
            self.assertIn("reopenable routes", proc.stdout)
            self.assertIn("source truth", proc.stdout)

    def test_preview_is_foreground_bounded_with_broad_scan_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_registry(root, thread_count=12)
            bounded = self.run_cli("continuity-domain", "--registry-dir", str(registry_dir), "preview", "--json")
            human = self.run_cli("continuity-domain", "--registry-dir", str(registry_dir), "preview")
            broad = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "preview",
                "--broad-scan",
                "--max-candidates",
                "1",
                "--json",
            )

        self.assertEqual(bounded.returncode, 0, bounded.stderr)
        bounded_payload = json.loads(bounded.stdout)
        self.assertEqual(bounded_payload["preview_scan_policy"]["mode"], "foreground_bounded_default")
        preview = bounded_payload["candidate_previews"][0]
        self.assertNotIn("<cue>", json.dumps(preview, ensure_ascii=False))
        self.assertIn(preview["foreground_candidate_quality"], {"actionable", "low_information"})
        if preview["foreground_candidate_quality"] == "actionable":
            self.assertIn("agent recall", preview["foreground_actions"][0]["command"])
            self.assertEqual(preview["foreground_actions"][0]["claim_boundary"], "no_claim_before_reopen")
        else:
            self.assertEqual(preview["foreground_actions"], [])
            self.assertIn("suppression_reason", preview)
        self.assertEqual(bounded_payload["metrics"]["registered_thread_count"], 12)
        self.assertEqual(bounded_payload["metrics"]["considered_thread_count"], 8)
        self.assertEqual(bounded_payload["metrics"]["scanned_thread_count"], 8)
        self.assertTrue(bounded_payload["metrics"]["scan_partial"])
        self.assertTrue(bounded_payload["scan_policy"]["partial"])
        self.assertIn("--broad-scan", bounded_payload["scan_policy"]["broad_scan_command"])
        self.assertIn(
            bounded_payload["foreground_action"]["id"],
            {"use_candidate_preview_as_reopenable_route", "needs_broader_scan_or_cue"},
        )
        self.assertNotIn("--append", bounded_payload["foreground_action"]["command"])
        if bounded_payload["foreground_action"]["id"] == "use_candidate_preview_as_reopenable_route":
            self.assertIn("--append", bounded_payload["operator_next_action"]["command"])
        else:
            self.assertEqual(bounded_payload["foreground_candidate_quality"], "needs_broader_scan")

        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("scan: 8/12 threads", human.stdout)
        self.assertIn("partial", human.stdout)
        self.assertIn("low-info suppressed", human.stdout)
        self.assertIn("boundary: preview is a route card", human.stdout)

        self.assertEqual(broad.returncode, 0, broad.stderr)
        broad_payload = json.loads(broad.stdout)
        self.assertEqual(broad_payload["preview_scan_policy"]["mode"], "explicit_broad_scan")
        self.assertEqual(broad_payload["metrics"]["registered_thread_count"], 12)
        self.assertEqual(broad_payload["metrics"]["considered_thread_count"], 12)
        self.assertEqual(broad_payload["metrics"]["scanned_thread_count"], 12)
        self.assertFalse(broad_payload["metrics"]["scan_partial"])

    def test_preview_filters_low_information_titles_and_cues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = write_continuity_domain_registry(
                root,
                thread_count=1,
                title="AIppocampus issues from Candidate generated recent messages",
                message_text=(
                    "from recent messages rollout lines user Candidate generated issues 看看 "
                    "用户 角度 现在试 然后提 provider orchestration source-backed continuity route"
                ),
            )
            proc = self.run_cli("continuity-domain", "--registry-dir", str(registry_dir), "preview", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreater(payload["metrics"]["low_information_label_suppressed_count"], 0)
        self.assertTrue(payload["candidate_previews"])
        rejected = {
            "aippocampus",
            "candidate",
            "candidate generated",
            "checkpoint",
            "clean",
            "focus",
            "from",
            "generated",
            "health",
            "issue",
            "issues",
            "line",
            "lines",
            "message",
            "messages",
            "normalized",
            "plugin",
            "recent",
            "rollout",
            "user",
            "用户",
            "角度",
            "现在试",
            "然后提",
            "看看",
            "6-67",
        }
        for preview in payload["candidate_previews"]:
            self.assertNotIn(str(preview["title"]).casefold(), rejected)
            for cue in preview["activation_cues"]:
                self.assertNotIn(str(cue).casefold(), rejected)

    def test_preview_does_not_promote_generic_tool_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = write_continuity_domain_registry(
                root,
                thread_count=3,
                title="AIppocampus recall append maintenance runtime-contract.md",
                message_text=(
                    "recall append maintenance AIppocampus aippocampus runtime-contract.md "
                    "continuity-domain preview foreground action should prefer "
                    "provider orchestration source-backed continuity route"
                ),
            )
            proc = self.run_cli("continuity-domain", "--registry-dir", str(registry_dir), "preview", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded_action = json.dumps(payload["foreground_action"], ensure_ascii=False).casefold()
        self.assertNotIn('"recall"', encoded_action)
        self.assertNotIn('"append"', encoded_action)
        self.assertNotIn('"maintenance"', encoded_action)
        self.assertNotIn('"aippocampus"', encoded_action)
        self.assertIn("--broad-scan", encoded_action)
        self.assertEqual(payload["foreground_candidate_quality"], "needs_broader_scan")
        for preview in payload["candidate_previews"]:
            self.assertIn(preview["foreground_candidate_quality"], {"actionable", "low_information"})
            if preview["foreground_candidate_quality"] == "low_information":
                self.assertIn("suppression_reason", preview)

    def test_preview_noisy_candidates_return_broader_scan_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = write_continuity_domain_registry(
                root,
                thread_count=1,
                title="AIppocampus recall append maintenance",
                message_text="recall append maintenance AIppocampus aippocampus runtime-contract.md",
            )
            proc = self.run_cli("continuity-domain", "--registry-dir", str(registry_dir), "preview", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["foreground_candidate_quality"], "needs_broader_scan")
        self.assertEqual(payload["foreground_action"]["id"], "needs_broader_scan_or_cue")
        self.assertIn("--broad-scan", payload["foreground_action"]["command"])
        self.assertNotIn("agent recall", payload["foreground_action"]["command"])

if __name__ == "__main__":
    unittest.main()
