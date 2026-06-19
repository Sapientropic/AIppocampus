from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


class AippocampusCliTests(unittest.TestCase):
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

    def run_cli_with_env(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def write_last_recall_cache(self, registry: Path, *route_ids: str) -> None:
        target = registry / "agent" / "last-recall.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_agent_last_recall",
                    "schema_version": "agent-continuity-path-v1",
                    "requests": [
                        {"request_index": index, "route_id": route_id}
                        for index, route_id in enumerate(route_ids, start=1)
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def write_continuity_domain_registry(
        self,
        root: Path,
        *,
        thread_count: int,
        message_text: str,
        title: str = "provider orchestration continuity route",
    ) -> Path:
        registry_dir = root / "registry"
        registry_dir.mkdir()
        threads = []
        for index in range(thread_count):
            clean = root / f"clean-source-{index}"
            clean.mkdir()
            rows = [
                {
                    "message_id": f"msg-{index}-{line}",
                    "turn_id": f"turn-{index}-{line}",
                    "turn_index": line,
                    "source_line": line,
                    "phase": "final_answer",
                    "text": message_text,
                }
                for line in (1, 2)
            ]
            (clean / "messages.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": f"session:{index}",
                    "title": title,
                    "summary": title,
                    "project_label": "AIppocampus",
                    "paths": {"clean_source_dir": str(clean)},
                }
            )
        (registry_dir / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "2026-06-16T00:00:00Z",
                    "threads": threads,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return registry_dir

    def test_help_leads_with_personal_path_before_operator_flows(self) -> None:
        proc = self.run_cli("--help")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Start here:", proc.stdout)
        self.assertIn("aippocampus start --json", proc.stdout)
        self.assertIn('aippocampus agent recall "old cue"', proc.stdout)
        self.assertIn('aippocampus search "exact phrase"', proc.stdout)
        self.assertIn("aippocampus agent deepen --request 1 --last-recall --json", proc.stdout)
        self.assertIn("Personal path", proc.stdout)
        self.assertIn("Advanced/operator diagnostics", proc.stdout)
        self.assertLess(proc.stdout.index("Start here:"), proc.stdout.index("Personal path"))
        self.assertLess(proc.stdout.index("Personal path"), proc.stdout.index("Advanced/operator"))
        start = proc.stdout[
            proc.stdout.index("Start here:") : proc.stdout.index("Recovery/readiness:")
        ]
        self.assertLess(start.index("start --json"), start.index("agent recall"))
        self.assertLess(start.index("agent recall"), start.index("agent deepen"))
        self.assertLess(start.index("agent deepen"), start.index("search"))
        self.assertNotIn("aippocampus health", start)
        self.assertIn("Recovery/readiness:", proc.stdout)
        self.assertLess(proc.stdout.index("agent deepen"), proc.stdout.index("Recovery/readiness:"))
        self.assertLess(proc.stdout.index("search"), proc.stdout.index("doctor provider"))
        self.assertIn("health", proc.stdout)
        self.assertIn("onboard", proc.stdout)
        self.assertIn("search", proc.stdout)
        self.assertIn("agent recall", proc.stdout)
        self.assertIn("Agent continuity pull path", proc.stdout)
        self.assertNotIn("Opt-in agent recall", proc.stdout)
        self.assertIn("learning", proc.stdout)
        self.assertIn("repro package", proc.stdout)
        self.assertIn("do-not-use-here", proc.stdout)
        self.assertIn("pause / forget", proc.stdout)
        self.assertIn("continuity-domain", proc.stdout)
        self.assertIn("work-guard", proc.stdout)
        self.assertIn("update status", proc.stdout)

    def test_personal_control_and_learning_frontdoors_are_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_registry = Path(tmp) / "registry"
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(empty_registry)}
            pause = self.run_cli_with_env("pause", "--json", env=env)
            forget_plan = self.run_cli_with_env("forget", "--json", env=env)
        pause_help = self.run_cli("pause", "--help")
        forget = self.run_cli("forget", "route:test", "--json")
        privacy = self.run_cli("privacy", "--help")
        why_not = self.run_cli("why-not", "old cue", "--json")
        learning = self.run_cli("learning", "--json")
        learning_replay = self.run_cli("learning", "replay", "--json")
        learning_human = self.run_cli("learning", "replay")
        learning_status = self.run_cli("learning", "status", "--json")
        learning_status_operator = self.run_cli("learning", "status", "--operator-json", "--json")
        learning_guidance = self.run_cli("learning", "guidance", "--json")
        learning_guidance_operator = self.run_cli("learning", "guidance", "--operator-json", "--json")

        self.assertEqual(pause_help.returncode, 0, pause_help.stderr)
        self.assertIn("usage: aippocampus pause [target] [options]", pause_help.stdout)
        self.assertIn("Boundary: feedback and quieting", pause_help.stdout)
        self.assertNotIn("{pause,forget,do-not-use-here}", pause_help.stdout)
        self.assertNotIn("<local-feedback.jsonl>", pause_help.stdout)

        self.assertEqual(pause.returncode, 0, pause.stderr)
        pause_payload = json.loads(pause.stdout)
        self.assertEqual(pause_payload["mode"], "pause")
        self.assertNotEqual(pause_payload["status"], "plan_card")
        pause_encoded = json.dumps(pause_payload, ensure_ascii=False)
        self.assertNotIn("<route-or-ticket-id>", pause_encoded)
        for action in pause_payload["safe_next_actions"]:
            if "command" in action:
                self.assertNotIn("route_to_", action["command"])
        self.assertNotIn("hooks --help", pause_encoded)
        self.assertIn("safe_next_actions", pause_payload)
        self.assertEqual(pause_payload["agent_next_action"], pause_payload["safe_next_actions"][0])
        self.assertEqual(pause_payload["foreground_action"], pause_payload["safe_next_actions"][0])
        self.assertNotIn("cannot_claim", pause_payload)
        self.assertIn("claim_boundary", pause_payload)
        self.assertIn("boundary_detail", pause_payload)
        self.assertIn(
            "ambient continuity is paused globally",
            pause_payload["boundary_detail"]["cannot_claim"],
        )
        self.assertEqual(
            pause_payload["agent_next_action"]["command_template"],
            'aippocampus agent recall "{cue_for_route_to_pause}" --json',
        )
        self.assertEqual(pause_payload["agent_next_action"]["requires"], ["cue_for_route_to_pause"])
        self.assertNotIn("route to pause", pause_encoded)

        self.assertEqual(forget_plan.returncode, 0, forget_plan.stderr)
        forget_plan_payload = json.loads(forget_plan.stdout)
        self.assertEqual(forget_plan_payload["mode"], "forget")
        self.assertEqual(forget_plan_payload["status"], "needs_scope")
        self.assertEqual(
            forget_plan_payload["agent_next_action"],
            forget_plan_payload["safe_next_actions"][0],
        )
        self.assertNotIn("cannot_claim", forget_plan_payload)
        self.assertIn(
            "raw audit history was physically deleted",
            forget_plan_payload["boundary_detail"]["cannot_claim"],
        )
        self.assertEqual(
            forget_plan_payload["agent_next_action"]["command_template"],
            'aippocampus agent recall "{cue_for_route_to_forget}" --json',
        )
        self.assertNotIn("route to forget here", forget_plan.stdout)
        self.assertNotIn("export --help", forget_plan.stdout)

        self.assertEqual(forget.returncode, 0, forget.stderr)
        forget_payload = json.loads(forget.stdout)
        self.assertEqual(forget_payload["mode"], "forget")
        self.assertEqual(forget_payload["target"], "route:test")
        self.assertNotEqual(forget_payload["status"], "plan_card")
        self.assertTrue(forget_payload["write_boundary"]["wrote_event"])
        self.assertTrue(forget_payload["quieted_future_routes"])
        self.assertNotIn("cannot_claim", forget_payload)
        self.assertIn("claim_boundary", forget_payload)
        self.assertIn("boundary_detail", forget_payload)
        self.assertIn("raw audit history was physically deleted", forget_payload["boundary_detail"]["cannot_claim"])
        self.assertNotIn("<route-or-ticket-id>", forget.stdout)

        self.assertEqual(privacy.returncode, 0, privacy.stderr)
        self.assertIn("aippocampus pause --json", privacy.stdout)
        self.assertIn("aippocampus forget --json", privacy.stdout)
        self.assertNotIn("route_to_", privacy.stdout)
        self.assertNotIn("aippocampus pause --help", privacy.stdout)
        self.assertNotIn("aippocampus forget --help", privacy.stdout)
        self.assertNotIn("aippocampus do-not-use-here --help", privacy.stdout)

        self.assertEqual(why_not.returncode, 0, why_not.stderr)
        self.assertEqual(json.loads(why_not.stdout)["mode"], "why-not-recall")

        self.assertEqual(learning.returncode, 0, learning.stderr)
        learning_payload = json.loads(learning.stdout)
        self.assertEqual(learning_payload["kind"], "aippocampus_learning_frontdoor")
        self.assertEqual(learning_payload["mode"], "status")
        self.assertEqual(learning_payload["agent_next_action"]["id"], "review_semantic_guidance_candidate")
        self.assertIn("learning guidance --json", learning_payload["agent_next_action"]["command"])
        self.assertTrue(learning_payload["privacy_boundary"]["raw_rollouts_serialized"] is False)

        self.assertEqual(learning_replay.returncode, 2, learning_replay.stderr)
        replay_payload = json.loads(learning_replay.stdout)
        replay_encoded = json.dumps(replay_payload, ensure_ascii=False)
        self.assertEqual(replay_payload["status"], "needs_source_selection")
        self.assertFalse(replay_payload["fixture_input"])
        self.assertEqual(replay_payload["agent_next_action"]["id"], "discover_eligible_learning_sources")
        self.assertNotIn("<events.jsonl>", replay_encoded)
        self.assertNotIn("<sanitized-events.jsonl>", replay_encoded)

        self.assertEqual(learning_human.returncode, 2, learning_human.stderr)
        self.assertIn("needs source selection", learning_human.stdout)
        self.assertEqual(learning_status.returncode, 0, learning_status.stderr)
        status_payload = json.loads(learning_status.stdout)
        status_encoded = json.dumps(status_payload, ensure_ascii=False)
        self.assertNotIn("cannot_claim", status_payload)
        self.assertIn("cannot_claim", status_payload["boundary_detail"])
        self.assertEqual(status_payload["lanes"]["prepared_guidance"]["status"], "not_found")
        self.assertEqual(status_payload["lanes"]["sanitized_replay"]["status"], "available_on_request")
        self.assertIn("effectiveness_ledger", status_payload["lanes"])
        self.assertEqual(status_payload["lanes"]["operator_diagnostics"]["status"], "operator_only")
        self.assertEqual(status_payload["agent_next_action"]["id"], "review_semantic_guidance_candidate")
        self.assertEqual(status_payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(status_payload["foreground_action"], status_payload["agent_next_action"])
        self.assertEqual(status_payload["safe_next_actions"][0], status_payload["foreground_action"])
        self.assertEqual(status_payload["next_actions"][0], status_payload["foreground_action"])
        self.assertEqual(
            len(status_payload["safe_next_actions"]),
            len(
                {
                    (
                        action.get("id"),
                        action.get("command"),
                        action.get("command_template"),
                    )
                    for action in status_payload["safe_next_actions"]
                }
            ),
        )
        self.assertEqual(
            status_payload["route_value"],
            "current_learning_guidance_is_navigation_for_next_action",
        )
        self.assertIn("current_uncertainty", status_payload)
        self.assertIn("summary_metrics", status_payload)
        self.assertGreaterEqual(len(status_payload["current_guidance"]), 1)
        self.assertEqual(
            status_payload["current_guidance"][0]["review_action"]["id"],
            "review_semantic_guidance_candidate",
        )
        self.assertNotIn("semantic_guidance_lifecycle", status_payload)
        self.assertNotIn("operator_detail", status_payload)
        self.assertEqual(
            status_payload["operator_detail_command"],
            "aippocampus learning guidance --operator-json",
        )
        self.assertEqual(learning_status_operator.returncode, 0, learning_status_operator.stderr)
        status_operator_payload = json.loads(learning_status_operator.stdout)
        self.assertNotIn(
            "guidance_lifecycle_ledger",
            status_operator_payload["semantic_guidance_lifecycle"],
        )
        self.assertIn("guidance_lifecycle_ledger", status_operator_payload["operator_detail"])
        self.assertNotIn("<events.jsonl>", status_encoded)
        self.assertNotIn("<sanitized-events.jsonl>", status_encoded)
        self.assertEqual(status_payload["semantic_loop"]["stage"], "action_time_capable")
        self.assertGreaterEqual(
            status_payload["semantic_loop"]["stage_counts"]["promoted_guidance_candidate_count"],
            1,
        )
        self.assertGreaterEqual(
            status_payload["semantic_loop"]["stage_counts"]["action_time_guidance_count"],
            1,
        )
        self.assertEqual(
            status_payload["semantic_loop"]["stage_counts"]["raw_private_text_leak_count"],
            0,
        )
        self.assertIn(
            "candidate_only_safety_is_not_sufficient",
            status_payload["semantic_loop"]["closeout_gate"],
        )
        self.assertNotIn("benchmark", status_payload["agent_next_action"]["command"])
        self.assertTrue(
            status_payload["lanes"]["current_history_extraction"]["requires_explicit_source"]
        )

        module_status = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.learning_loop.cli",
                "status",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        self.assertEqual(module_status.returncode, 0, module_status.stderr)
        module_payload = json.loads(module_status.stdout)
        self.assertEqual(module_payload["kind"], "aippocampus_learning_frontdoor")
        self.assertEqual(module_payload["mode"], "status")
        self.assertEqual(module_payload["foreground_action_contract"], "foreground-action-v1")

        self.assertEqual(learning_guidance.returncode, 0, learning_guidance.stderr)
        guidance_payload = json.loads(learning_guidance.stdout)
        self.assertEqual(guidance_payload["mode"], "guidance")
        self.assertNotIn("cannot_claim", guidance_payload)
        self.assertIn("cannot_claim", guidance_payload["boundary_detail"])
        self.assertIn("semantic_guidance", guidance_payload)
        self.assertGreaterEqual(guidance_payload["semantic_guidance"]["guidance_count"], 1)
        self.assertNotIn("semantic_guidance_lifecycle", guidance_payload)
        self.assertNotIn("operator_detail", guidance_payload)
        self.assertNotIn("lifecycle", guidance_payload["semantic_guidance"])
        self.assertEqual(
            guidance_payload["semantic_guidance"]["operator_detail_command"],
            "aippocampus learning guidance --operator-json",
        )
        self.assertEqual(
            learning_guidance_operator.returncode,
            0,
            learning_guidance_operator.stderr,
        )
        guidance_operator_payload = json.loads(learning_guidance_operator.stdout)
        self.assertEqual(
            guidance_operator_payload["semantic_guidance"]["lifecycle"]["contract"],
            "semantic-guidance-lifecycle-v1",
        )
        self.assertGreaterEqual(
            guidance_operator_payload["semantic_guidance"]["lifecycle"]["candidate_count"],
            1,
        )
        lifecycle = guidance_operator_payload["semantic_guidance"]["lifecycle"]
        self.assertEqual(lifecycle["row_lifecycle_contract"], "guidance-row-lifecycle-v1")
        self.assertNotIn("guidance_lifecycle_ledger", lifecycle)
        self.assertIn("guidance_lifecycle_ledger", guidance_operator_payload["operator_detail"])
        ledger_row = guidance_operator_payload["operator_detail"]["guidance_lifecycle_ledger"][0]
        self.assertEqual(
            {
                event["guidance_id"]
                for event in ledger_row["events"]
            },
            {ledger_row["guidance_id"]},
        )
        self.assertEqual(
            [event["stage"] for event in ledger_row["events"]],
            ["candidate", "reviewed", "prepared", "surfaced", "outcome"],
        )
        self.assertEqual(
            guidance_operator_payload["semantic_guidance"]["lifecycle"]["candidate_actions"][0][
                "materialization_gate"
            ],
            "requires_review_before_cache",
        )
        self.assertEqual(
            guidance_payload["agent_next_action"]["id"],
            "preview_action_hint_cache_bridge",
        )
        self.assertNotEqual(
            guidance_payload["agent_next_action"]["command"],
            "aippocampus learning guidance --json",
        )
        self.assertNotEqual(
            guidance_payload["agent_next_action"],
            "produce or provide sanitized learning findings before expecting action-time hints",
        )
        foreground_commands = " ".join(
            str(action.get("command", "")) for action in status_payload["next_actions"]
        )
        self.assertNotIn("benchmark_learning_loop_public_companion", foreground_commands)

    def test_do_not_use_here_writes_public_safe_feedback_rows_when_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feedback_path = Path(tmp) / "feedback.jsonl"
            registry = Path(tmp) / "registry"
            project = Path(tmp) / "project"
            project.mkdir()
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)}
            ticket_path = Path(tmp) / "ticket.json"
            ticket_path.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_coding_continuity_ticket",
                        "ticket_id": "ticket_test",
                        "trigger": "user_correction",
                        "intervention_level": "warning",
                        "relevant_decisions": ["avoid noisy repeated route"],
                        "proposed_use": "warn",
                        "evidence_refs": [{"source_id": "src_test", "message_id": "msg_test"}],
                        "source_thickness": "usable",
                        "derived_assessment": {
                            "basis_refs": [{"source_id": "src_test", "message_id": "msg_test"}]
                        },
                        "expires_at": "task_or_topic_epoch_end",
                        "annoyance_risk": "medium",
                        "preconditions": [],
                        "outcome_feedback_expected": ["dismissed", "ignored", "corrected"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            recall = self.run_cli_with_env(
                "do-not-use-here",
                "route_test",
                "--feedback-jsonl",
                str(feedback_path),
                "--json",
                env=env,
            )
            default_durable = self.run_cli_with_env(
                "do-not-use-here",
                "route_default",
                "--cwd",
                str(project),
                "--json",
                env=env,
            )
            ticket = self.run_cli_with_env(
                "do-not-use-here",
                "ticket_test",
                "--surface",
                "coding-ticket",
                "--feedback-jsonl",
                str(feedback_path),
                "--ticket-json",
                str(ticket_path),
                "--json",
                env=env,
            )
            rows = [
                json.loads(line)
                for line in feedback_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            default_rows = [
                json.loads(line)
                for path in registry.rglob("*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(recall.returncode, 0, recall.stderr)
        self.assertEqual(default_durable.returncode, 0, default_durable.stderr)
        self.assertEqual(ticket.returncode, 0, ticket.stderr)
        recall_payload = json.loads(recall.stdout)
        default_payload = json.loads(default_durable.stdout)
        ticket_payload = json.loads(ticket.stdout)
        self.assertEqual(default_payload["status"], "captured")
        self.assertTrue(default_payload["quieted_future_routes"])
        self.assertEqual(default_payload["write_boundary"]["storage"], "jsonl")
        self.assertEqual(default_payload["feedback_path_source"], "default_registry")
        self.assertFalse(default_payload["feedback_lane"]["raw_path_emitted"])
        self.assertEqual(default_payload["why_not_card"]["status"], "durable_feedback_available")
        self.assertEqual(default_rows[0]["route_id"], "route_default")
        self.assertNotIn(str(registry), default_durable.stdout)
        self.assertEqual(recall_payload["status"], "captured")
        self.assertTrue(recall_payload["quieted_future_routes"])
        self.assertEqual(recall_payload["feedback"]["write_boundary"]["storage"], "jsonl")
        self.assertEqual(recall_payload["write_boundary"]["storage"], "jsonl")
        self.assertEqual(recall_payload["why_not_card"]["status"], "durable_feedback_available")
        self.assertEqual(ticket_payload["status"], "quieted")
        self.assertEqual(ticket_payload["write_boundary"]["storage"], "jsonl")
        self.assertTrue(ticket_payload["action_time_consumed"])
        self.assertEqual(ticket_payload["action_time_decision"]["visibility"], "stay_silent")
        self.assertIn(
            "recent_feedback_suppressed",
            ticket_payload["action_time_decision"]["suppression_reasons"],
        )
        self.assertEqual(
            ticket_payload["activation_tuning"]["adjustments"][0]["activation_tuning"],
            "quieter",
        )
        self.assertEqual(rows[0]["signal"], "wrong_route_drag")
        self.assertEqual(rows[1]["kind"], "aippocampus_agency_ticket_feedback")
        self.assertEqual(rows[1]["outcome"], "dismissed")
        self.assertFalse(rows[1]["feedback_changes_source_truth"])

    def test_do_not_use_here_missing_target_offers_route_and_ticket_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(Path(tmp) / "registry")}
            proc = self.run_cli_with_env("do-not-use-here", "--json", env=env)

        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["status"], "needs_target")
        surfaces = {item["surface"] for item in payload["safe_next_actions"]}
        self.assertEqual(surfaces, {"recall-route", "coding-ticket"})
        self.assertIn("agent recall", payload["agent_next_action"]["command_template"])
        self.assertEqual(payload["agent_next_action"]["requires"], ["cue_for_route_to_quiet"])
        self.assertEqual(payload["safe_next_actions"][1]["requires"], ["route_id"])
        self.assertEqual(payload["safe_next_actions"][2]["requires"], ["ticket_id"])
        self.assertNotIn("<route_id>", encoded)
        self.assertNotIn("<ticket_id>", encoded)
        self.assertNotIn("route to quiet", encoded)

    def test_personal_controls_keep_last_recall_route_choices_secondary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry"
            self.write_last_recall_cache(registry, "route_cached_one", "route_cached_two")
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)}
            pause = self.run_cli_with_env("pause", "--json", env=env)
            forget = self.run_cli_with_env("forget", "--json", env=env)
            quiet = self.run_cli_with_env("do-not-use-here", "--json", env=env)

        for proc in (pause, forget, quiet):
            self.assertIn(proc.returncode, {0, 2}, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["agent_next_action"]["mutation_risk"], "read_only")
            self.assertIn("command_template", payload["agent_next_action"])
            cached_actions = [
                action
                for action in payload["safe_next_actions"]
                if action.get("source") == "last_recall_cache"
            ]
            self.assertTrue(cached_actions)
            self.assertEqual(cached_actions[0]["request_index"], 1)
            self.assertIn("route_cached_one", cached_actions[0]["command"])
            self.assertNotEqual(payload["agent_next_action"], cached_actions[0])
            self.assertNotIn("route to quiet", json.dumps(payload, ensure_ascii=False))

    def test_hooks_help_shows_family_not_raw_installer_parser(self) -> None:
        family = self.run_cli("hooks", "--help")
        prompt = self.run_cli("hooks", "prompt", "--help")
        lifecycle = self.run_cli("hooks", "lifecycle", "--help")
        action = self.run_cli("hooks", "action", "--help")
        refresh_cache = self.run_cli("hooks", "action", "refresh-cache", "--help")

        self.assertEqual(family.returncode, 0, family.stderr)
        self.assertIn("usage: aippocampus hooks [prompt|lifecycle|action|claude-code]", family.stdout)
        self.assertIn("Hook families:", family.stdout)
        self.assertIn("prompt", family.stdout)
        self.assertIn("lifecycle", family.stdout)
        self.assertIn("action", family.stdout)
        self.assertNotIn("usage: facade.py", family.stdout)

        self.assertIn("usage: aippocampus hooks prompt", prompt.stdout)
        self.assertIn("Prompt hook", prompt.stdout)
        self.assertIn("usage: aippocampus hooks lifecycle", lifecycle.stdout)
        self.assertIn("Lifecycle hooks", lifecycle.stdout)
        self.assertIn("usage: aippocampus hooks action", action.stdout)
        self.assertIn("refresh-cache", action.stdout)
        self.assertNotIn("usage: facade.py", action.stdout)
        self.assertIn("usage: aippocampus hooks action refresh-cache", refresh_cache.stdout)
        self.assertNotIn("[{report,refresh-cache}]", refresh_cache.stdout)
        self.assertIn("aippocampus hooks action refresh-cache --write --json", action.stdout)
        self.assertIn("aippocampus hooks action refresh-cache --write --json", refresh_cache.stdout)
        self.assertNotIn("<local-cache.jsonl>", action.stdout)
        self.assertNotIn("<local-cache.jsonl>", refresh_cache.stdout)

        prompt_install = self.run_cli("hooks", "prompt", "install", "--help")
        lifecycle_install = self.run_cli("hooks", "lifecycle", "install", "--help")
        action_install = self.run_cli("hooks", "action", "install", "--help")
        self.assertIn("Prompt hook install boundary", prompt_install.stdout)
        self.assertIn("Does not install provider keys", prompt_install.stdout)
        self.assertIn("Lifecycle hook install boundary", lifecycle_install.stdout)
        self.assertIn("Does not cold-archive", lifecycle_install.stdout)
        self.assertIn("Action-time hook install boundary", action_install.stdout)
        self.assertIn("prepared public-safe hint cache", action_install.stdout)
        self.assertIn("uninstall --json", action_install.stdout)
        self.assertNotIn("<local-cache.jsonl>", action_install.stdout)

    def test_config_alias_recovers_to_safe_doctor(self) -> None:
        help_proc = self.run_cli("config", "--help")
        human_proc = self.run_cli("config")
        json_proc = self.run_cli("config", "--compact-json")

        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("Config recovery card", help_proc.stdout)
        self.assertIn("knob catalog", help_proc.stdout)
        self.assertIn("local paths stay redacted", help_proc.stdout)
        self.assertIn("describe AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS", help_proc.stdout)
        self.assertIn("--resolved", help_proc.stdout)
        self.assertEqual(human_proc.returncode, 0, human_proc.stderr)
        self.assertIn("AIppocampus config doctor", human_proc.stdout)
        self.assertIn("values are not printed", human_proc.stdout.lower())
        self.assertIn("AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS", human_proc.stdout)
        self.assertIn("surface=prompt hook", human_proc.stdout)
        self.assertIn("default=3500", human_proc.stdout)
        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        payload = json.loads(json_proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_config_doctor_summary")

    def test_agent_recall_and_deepen_help_start_with_foreground_cards(self) -> None:
        recall = self.run_cli("agent", "recall", "--help")
        deepen = self.run_cli("agent", "deepen", "--help")

        self.assertEqual(recall.returncode, 0, recall.stderr)
        self.assertEqual(deepen.returncode, 0, deepen.stderr)
        self.assertIn("Agent recall task card", recall.stdout)
        self.assertIn("Default compact JSON is the foreground-safe surface", recall.stdout)
        self.assertIn('aippocampus search "exact phrase"', recall.stdout)
        self.assertIn("deepen/reopen before factual", recall.stdout)
        self.assertIn("Agent deepen task card", deepen.stdout)
        self.assertIn("aippocampus agent deepen --request 1 --last-recall --json", deepen.stdout)
        self.assertIn("Raw handles are local/private diagnostics", deepen.stdout)

    def test_lifecycle_hook_status_json_redacts_host_wiring_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_command = f"{sys.executable} -m aippocampus_runtime.hooks.lifecycle"
            hooks = {
                "hooks": {
                    event: [{"hooks": [{"type": "command", "command": private_command}]}]
                    for event in ("SessionStart", "Stop", "PreCompact", "PostCompact")
                }
            }
            (root / "hooks.json").write_text(
                json.dumps(hooks), encoding="utf-8", newline="\n"
            )
            public = self.run_cli(
                "hooks",
                "lifecycle",
                "status",
                "--codex-home",
                str(root),
                "--json",
            )
            operator = self.run_cli(
                "hooks",
                "lifecycle",
                "status",
                "--codex-home",
                str(root),
                "--json",
                "--operator-json",
            )

        self.assertEqual(public.returncode, 0, public.stderr)
        payload = json.loads(public.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["path"], "<local-path-redacted>")
        self.assertTrue(payload["path_redacted"])
        self.assertEqual(
            payload["events"]["SessionStart"]["commands"],
            ["<hook-command-redacted>"],
        )
        self.assertFalse(payload["privacy_boundary"]["hook_command_serialized"])
        self.assertNotIn(private_command, encoded)
        self.assertNotIn(str(root), encoded)
        self.assertEqual(operator.returncode, 0, operator.stderr)
        operator_payload = json.loads(operator.stdout)
        self.assertEqual(
            operator_payload["events"]["SessionStart"][0],
            private_command,
        )

    def test_version_command_is_available_without_local_paths(self) -> None:
        text = self.run_cli("--version")
        json_proc = self.run_cli("version", "--json")
        help_proc = self.run_cli("version", "--help")

        self.assertEqual(text.returncode, 0)
        self.assertIn("AIppocampus", text.stdout)
        self.assertEqual(help_proc.returncode, 0)
        self.assertIn("usage: aippocampus version", help_proc.stdout)
        self.assertNotIn("AIppocampus 0.", help_proc.stdout)
        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        payload = json.loads(json_proc.stdout)
        raw = json_proc.stdout + json_proc.stderr
        self.assertEqual(payload["kind"], "aippocampus_version")
        self.assertTrue(payload["version"])
        self.assertIn("pyproject", payload["versions"])
        self.assertIn("plugin_manifest", payload["versions"])
        self.assertNotIn(str(REPO_ROOT), raw)
        self.assertNotIn(str(SCRIPTS), raw)

    def test_latest_reply_facade_marks_commentary_as_not_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_rollout = root / "final.jsonl"
            commentary_rollout = root / "commentary.jsonl"
            final_rollout.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-06-16T00:00:00Z",
                                "type": "event_msg",
                                "payload": {"type": "user_message", "message": "continue vault dashboard mobile issue"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-06-16T00:00:01Z",
                                "type": "event_msg",
                                "payload": {
                                    "type": "agent_message",
                                    "phase": "final_answer",
                                    "message": "settled final closeout",
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            commentary_text = "I am still checking things; not final."
            commentary_rollout.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-06-16T00:00:00Z",
                                "type": "event_msg",
                                "payload": {"type": "user_message", "message": "continue vault dashboard mobile issue"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-06-16T00:00:01Z",
                                "type": "event_msg",
                                "payload": {
                                    "type": "agent_message",
                                    "phase": "commentary",
                                    "message": commentary_text,
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            final_proc = self.run_cli("latest-reply", "--rollout", str(final_rollout), "--json")
            commentary_proc = self.run_cli(
                "latest-reply",
                "--rollout",
                str(commentary_rollout),
                "--json",
            )
            operator_proc = self.run_cli(
                "latest-reply",
                "--rollout",
                str(commentary_rollout),
                "--operator-json",
            )

        self.assertEqual(final_proc.returncode, 0, final_proc.stderr)
        final_payload = json.loads(final_proc.stdout)
        self.assertTrue(final_payload["closeout_available"])
        self.assertEqual(final_payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(final_payload["foreground_action"], final_payload["agent_next_action"])
        self.assertEqual(final_payload["safe_next_actions"][0], final_payload["foreground_action"])
        self.assertNotIn("text", final_payload["message"])
        self.assertIn("settled final closeout", final_payload["message"]["preview"])
        self.assertEqual(
            final_payload["safe_next_actions"][0]["command"],
            "aippocampus latest-reply --detail full --operator-json",
        )
        self.assertEqual(
            final_payload["safe_next_actions"][0]["authority_after_running"],
            "source_open_within_local_rollout_scope",
        )
        self.assertNotEqual(commentary_proc.returncode, 0)
        commentary_payload = json.loads(commentary_proc.stdout)
        encoded_commentary = json.dumps(commentary_payload, ensure_ascii=False)
        self.assertEqual(commentary_payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(commentary_payload["foreground_action"], commentary_payload["agent_next_action"])
        self.assertEqual(commentary_payload["safe_next_actions"][0], commentary_payload["foreground_action"])
        self.assertTrue(commentary_payload["not_final_closeout"])
        self.assertTrue(commentary_payload["diagnostic_only"])
        self.assertNotIn(commentary_text, encoded_commentary)
        self.assertNotIn("preview", commentary_payload["message"])
        commentary_action = commentary_payload["safe_next_actions"][0]
        self.assertEqual(
            shlex.split(commentary_action["command"]),
            [
                "aippocampus",
                "agent",
                "recall",
                "continue vault dashboard mobile issue",
                "--json",
            ],
        )
        self.assertNotIn("command_template", commentary_action)
        self.assertEqual(operator_proc.returncode, 1)
        self.assertIn(commentary_text, operator_proc.stdout)

    def test_latest_reply_missing_rollout_is_recoverable_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_cwd = Path(tmp) / "empty-project"
            missing_cwd.mkdir()
            proc = self.run_cli(
                "latest-reply",
                "--cwd",
                str(missing_cwd),
                "--json",
                "--detail",
                "compact",
            )
            help_proc = self.run_cli("latest-reply", "--help")

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2, raw)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "no_latest_reply_source_found")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertEqual(payload["error"]["code"], "no_rollout_for_cwd")
        self.assertTrue(payload["error"]["path_redacted"])
        self.assertIn("agent recall", payload["agent_next_action"]["command_template"])
        self.assertEqual(payload["agent_next_action"]["requires"], ["cue"])
        self.assertTrue(payload["agent_next_action"]["template_only"])
        self.assertNotIn("command", payload["agent_next_action"])
        self.assertIn("source_backed_claim", payload["cannot_claim"])
        self.assertNotIn(str(missing_cwd), raw)
        self.assertNotIn("Traceback", raw)
        self.assertEqual(help_proc.returncode, 0)
        self.assertIn("Latest final-answer closeout recovery card", help_proc.stdout)
        self.assertIn("not in-progress commentary", help_proc.stdout)
        self.assertIn("reopen clean source", help_proc.stdout)

    def test_doctor_config_compact_json_is_foreground_agent_sized(self) -> None:
        proc = self.run_cli("doctor", "config", "--compact-json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_config_doctor_summary")
        self.assertLess(len(proc.stdout.splitlines()), 60)
        self.assertTrue(payload["audit_json_available"])
        self.assertFalse(payload["privacy"]["values_printed"])
        self.assertNotIn("knobs", payload)

    def test_nested_operator_help_uses_facade_command_prog(self) -> None:
        mcp = self.run_cli("mcp", "--help")
        maintenance = self.run_cli("maintenance", "--help")
        export = self.run_cli("export", "--help")
        import_bundle = self.run_cli("import", "--help")
        import_conversation = self.run_cli("import", "conversation", "--help")
        sync = self.run_cli("sync", "status", "--help")
        object_sync = self.run_cli("object-sync", "status", "--help")
        why = self.run_cli("why-recall", "--help")
        why_not = self.run_cli("why-not-recall", "--help")
        health = self.run_cli("health", "--help")
        self_note = self.run_cli("self-note", "append", "--help")
        vault = self.run_cli("vault", "sync", "--help")
        continuity = self.run_cli("continuity-domain", "report", "--help")
        work_guard = self.run_cli("work-guard", "--help")
        telepathy = self.run_cli("telepathy", "create", "--help")
        observatory = self.run_cli("observatory", "--help")
        episode_arcs = self.run_cli("episode-arcs", "--help")
        onboard = self.run_cli("onboard", "--help")
        provider_key = self.run_cli("onboard", "provider-key", "--help")

        self.assertEqual(mcp.returncode, 0)
        self.assertIn("usage: aippocampus mcp", mcp.stdout)
        self.assertNotIn("usage: facade.py", mcp.stdout)
        self.assertEqual(maintenance.returncode, 0)
        self.assertIn("usage: aippocampus maintenance", maintenance.stdout)
        self.assertNotIn("usage: facade.py", maintenance.stdout)
        self.assertIn("usage: aippocampus export", export.stdout)
        self.assertIn("usage: aippocampus import ", import_bundle.stdout)
        self.assertIn("usage: aippocampus import conversation", import_conversation.stdout)
        self.assertIn("usage: aippocampus sync status", sync.stdout)
        self.assertIn("--include-raw", sync.stdout)
        self.assertIn("requires an encrypted sync", sync.stdout)
        self.assertIn("--recipient-file", sync.stdout)
        self.assertIn("--identity-file", sync.stdout)
        self.assertIn("--require-encrypted", sync.stdout)
        self.assertIn("usage: aippocampus object-sync status", object_sync.stdout)
        self.assertIn("usage: aippocampus why-recall", why.stdout)
        self.assertIn("usage: aippocampus why-not-recall", why_not.stdout)
        self.assertIn("usage: aippocampus health", health.stdout)
        self.assertIn("usage: aippocampus self-note append", self_note.stdout)
        self.assertIn("example: aippocampus self-note append", self_note.stdout)
        self.assertIn("do not use them as source-backed", self_note.stdout)
        self.assertEqual(vault.returncode, 0)
        self.assertIn("usage: aippocampus vault sync", vault.stdout)
        self.assertIn("local human-readable vault and dashboard", vault.stdout)
        self.assertIn("usage: aippocampus continuity-domain report", continuity.stdout)
        self.assertIn("usage: aippocampus work-guard", work_guard.stdout)
        self.assertIn("usage: aippocampus telepathy create", telepathy.stdout)
        self.assertIn("usage: aippocampus observatory", observatory.stdout)
        self.assertIn("usage: aippocampus episode-arcs", episode_arcs.stdout)
        self.assertIn("aippocampus onboard --provider codex --status --json", onboard.stdout)
        self.assertIn("aippocampus onboard --status --operator-json", onboard.stdout)
        self.assertIn("--dry-run --json", onboard.stdout)
        self.assertNotIn("--provider codex --help", onboard.stdout)
        self.assertEqual(provider_key.returncode, 0)
        self.assertIn("usage: aippocampus onboard provider-key", provider_key.stdout)
        self.assertIn("--apply", provider_key.stdout)

    def test_mcp_list_tools_accepts_json_alias(self) -> None:
        proc = self.run_cli("mcp", "list-tools", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("tools", payload)
        self.assertTrue(any(tool.get("name") == "memory_health" for tool in payload["tools"]))
        by_name = {tool.get("name"): tool for tool in payload["tools"]}
        self.assertIn({"required": ["query"]}, by_name["agent_recall"]["inputSchema"]["anyOf"])
        self.assertIn({"required": ["intent"]}, by_name["agent_recall"]["inputSchema"]["anyOf"])
        self.assertEqual(
            by_name["get_turn_context"]["inputSchema"]["required_any"],
            ["turn_id", "message_id", "turn_index"],
        )

    def test_mcp_names_shortcut_matches_list_tools_names(self) -> None:
        shortcut = self.run_cli("mcp", "--names")
        explicit = self.run_cli("mcp", "list-tools", "--names")

        self.assertEqual(shortcut.returncode, 0, shortcut.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(json.loads(shortcut.stdout), json.loads(explicit.stdout))
        self.assertIn("agent_recall", json.loads(shortcut.stdout)["tool_names"])

    def test_mcp_list_tools_compact_summary_is_scan_friendly(self) -> None:
        proc = self.run_cli("mcp", "list-tools", "--compact")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_mcp_tool_readiness")
        self.assertTrue(payload["agent_native_tools_present"])
        self.assertIn("agent_recall", payload["key_tools_present"])
        self.assertEqual(payload["full_schema_command"], "aippocampus mcp list-tools --json")

    def test_mcp_status_is_compact_readiness_alias(self) -> None:
        proc = self.run_cli("mcp", "status")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_mcp_tool_readiness")
        self.assertIn("agent_recall", payload["key_tools_present"])
        self.assertNotIn("tools", payload)

    def test_bare_mcp_without_stdio_request_prints_readiness_card(self) -> None:
        proc = self.run_cli("mcp")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_mcp_tool_readiness")
        self.assertTrue(payload["agent_native_tools_present"])

    def test_update_and_plugin_status_help_start_with_foreground_cards(self) -> None:
        update_status = self.run_cli("update", "status", "--help")
        update_plan = self.run_cli("update", "plan", "--help")
        plugin_status = self.run_cli("plugin", "status", "--help")

        self.assertEqual(update_status.returncode, 0, update_status.stderr)
        self.assertIn("Update status readiness card", update_status.stdout)
        self.assertIn("aippocampus update status --json", update_status.stdout)
        self.assertIn("Advanced/operator overrides", update_status.stdout)
        self.assertLess(
            update_status.stdout.index("Update status readiness card"),
            update_status.stdout.index("Advanced/operator overrides"),
        )

        self.assertEqual(update_plan.returncode, 0, update_plan.stderr)
        self.assertIn("Update plan action card", update_plan.stdout)
        self.assertIn("aippocampus update plan --json", update_plan.stdout)
        self.assertIn("Advanced/operator overrides", update_plan.stdout)

        self.assertEqual(plugin_status.returncode, 0, plugin_status.stderr)
        self.assertIn("Plugin status readiness card", plugin_status.stdout)
        self.assertIn("aippocampus plugin status --json", plugin_status.stdout)

    def test_status_json_is_foreground_card_and_operator_json_is_full_detail(self) -> None:
        update_json = self.run_cli("update", "status", "--json", "--no-child-check")
        plugin_json = self.run_cli("plugin", "status", "--json", "--no-child-check")
        operator_json = self.run_cli("plugin", "status", "--operator-json", "--no-child-check")

        self.assertEqual(update_json.returncode, 0, update_json.stderr)
        update_payload = json.loads(update_json.stdout)
        self.assertEqual(update_payload["kind"], "aippocampus_update_status_agent_json")
        self.assertIn("foreground_status_cards", update_payload)
        self.assertNotIn("surfaces", update_payload)

        self.assertEqual(plugin_json.returncode, 0, plugin_json.stderr)
        plugin_payload = json.loads(plugin_json.stdout)
        self.assertEqual(plugin_payload["kind"], "aippocampus_update_status_agent_json")
        self.assertNotIn("surfaces", plugin_payload)

        self.assertEqual(operator_json.returncode, 0, operator_json.stderr)
        operator_payload = json.loads(operator_json.stdout)
        self.assertEqual(operator_payload["kind"], "aippocampus_update_status")
        self.assertIn("surfaces", operator_payload)

    def test_package_facade_is_the_public_python_entrypoint(self) -> None:
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.cli import facade as aippocampus_cli

        self.assertIs(aippocampus_cli.main, facade.main)
        self.assertIs(aippocampus_cli.run_script, facade.run_script)
        self.assertIs(aippocampus_cli.run_command, facade.run_command)
        self.assertIs(aippocampus_cli.resolve_command, facade.resolve_command)
        self.assertIs(aippocampus_cli.CommandInvocation, facade.CommandInvocation)
        self.assertIs(aippocampus_cli.CommandResult, facade.CommandResult)
        self.assertEqual(facade.SCRIPT_DIR, SCRIPTS)

    def test_package_facade_resolves_commands_without_running_child_processes(self) -> None:
        from aippocampus_runtime.cli import facade

        invocation = facade.resolve_command(["mcp", "list-tools", "--json"])

        self.assertEqual(invocation.command, "mcp")
        self.assertEqual(invocation.module_name, "aippocampus_runtime.mcp.server")
        self.assertEqual(invocation.script_name, "aippocampus_mcp_server.py")
        self.assertEqual(invocation.args, ["--list-tools", "--json"])

        search_invocation = facade.resolve_command(["search", "source", "--json"])
        self.assertEqual(search_invocation.command, "search")
        self.assertEqual(search_invocation.module_name, "aippocampus_runtime.source.search")
        self.assertEqual(search_invocation.script_name, "search_clean_source.py")

        agent_continuity_invocation = facade.resolve_command(
            ["agent", "recall", "continue project", "--json"]
        )
        self.assertEqual(agent_continuity_invocation.command, "agent")
        self.assertEqual(
            agent_continuity_invocation.module_name,
            "aippocampus_runtime.recall.agent_continuity",
        )
        self.assertEqual(agent_continuity_invocation.script_name, "agent_continuity.py")

        recall_alias = facade.resolve_command(["recall", "continue project", "--json"])
        self.assertEqual(recall_alias.command, "agent")
        self.assertEqual(recall_alias.module_name, "aippocampus_runtime.recall.agent_continuity")
        self.assertEqual(recall_alias.args, ["recall", "continue project", "--json"])

        aippo_alias = facade.resolve_command(["aippo", "--task", "ship the release", "--json"])
        self.assertEqual(aippo_alias.command, "agent")
        self.assertEqual(aippo_alias.args, ["aippo", "--task", "ship the release", "--json"])

        provider_key_alias = facade.resolve_command(["provider-key", "--help"])
        self.assertEqual(provider_key_alias.command, "provider-key")
        self.assertEqual(provider_key_alias.module_name, "aippocampus_runtime.onboarding.facade")
        self.assertEqual(provider_key_alias.args, ["provider-key", "--help"])

        export_invocation = facade.resolve_command(["export", "--cwd", "."])
        self.assertEqual(export_invocation.command, "export")
        self.assertEqual(export_invocation.module_name, "aippocampus_runtime.artifacts.export_bundle")
        self.assertEqual(export_invocation.script_name, "export_bundle.py")

        import_invocation = facade.resolve_command(["import", "bundle.zip"])
        self.assertEqual(import_invocation.command, "import")
        self.assertEqual(import_invocation.module_name, "aippocampus_runtime.artifacts.import_bundle")
        self.assertEqual(import_invocation.script_name, "import_bundle.py")

        doctor_invocation = facade.resolve_command(["doctor", "provider", "--json"])
        self.assertEqual(doctor_invocation.command, "doctor")
        self.assertEqual(doctor_invocation.module_name, "aippocampus_runtime.ops.provider_doctor")
        self.assertEqual(doctor_invocation.script_name, "provider_doctor.py")
        self.assertEqual(doctor_invocation.args, ["provider", "--json"])

        doctor_config_invocation = facade.resolve_command(["doctor", "config", "--json"])
        self.assertEqual(doctor_config_invocation.command, "doctor")
        self.assertEqual(
            doctor_config_invocation.module_name,
            "aippocampus_runtime.ops.provider_doctor",
        )
        self.assertEqual(doctor_config_invocation.script_name, "provider_doctor.py")
        self.assertEqual(doctor_config_invocation.args, ["config", "--json"])

        update_invocation = facade.resolve_command(["update", "status", "--json"])
        self.assertEqual(update_invocation.command, "update")
        self.assertEqual(update_invocation.module_name, "aippocampus_runtime.update.cli")
        self.assertEqual(update_invocation.script_name, "update.py")
        self.assertEqual(update_invocation.args, ["status", "--json"])

        plugin_invocation = facade.resolve_command(["plugin", "install", "--codex", "--verify"])
        self.assertEqual(plugin_invocation.command, "plugin")
        self.assertEqual(
            plugin_invocation.module_name,
            "aippocampus_runtime.update.plugin_installer",
        )
        self.assertEqual(plugin_invocation.script_name, "plugin.py")
        self.assertEqual(plugin_invocation.args, ["install", "--codex", "--verify"])

        smoke_invocation = facade.resolve_command(
            ["smoke", "recall-funnel", "progressive recall", "--json"]
        )
        self.assertEqual(smoke_invocation.command, "smoke")
        self.assertEqual(
            smoke_invocation.module_name,
            "aippocampus_runtime.ops.recall_funnel_smoke",
        )
        self.assertEqual(smoke_invocation.script_name, "recall_funnel_smoke.py")
        self.assertEqual(
            smoke_invocation.args,
            ["recall-funnel", "progressive recall", "--json"],
        )

        storage_invocation = facade.resolve_command(["storage", "gc", "--dry-run", "--json"])
        self.assertEqual(storage_invocation.command, "storage")
        self.assertEqual(
            storage_invocation.module_name,
            "aippocampus_runtime.ops.storage_governance",
        )
        self.assertEqual(storage_invocation.script_name, "storage_governance.py")
        self.assertEqual(storage_invocation.args, ["gc", "--dry-run", "--json"])

        warm_status = facade.resolve_command(["warm", "status", "--json"])
        self.assertEqual(warm_status.command, "warm")
        self.assertEqual(warm_status.module_name, "aippocampus_runtime.warm_ambient.cli")
        self.assertEqual(warm_status.script_name, "warm_ambient_cli.py")
        self.assertEqual(warm_status.args, ["status", "--json"])

        why_invocation = facade.resolve_command(["why-recall", "continue memory", "--json"])
        self.assertEqual(why_invocation.command, "why-recall")
        self.assertEqual(why_invocation.module_name, "aippocampus_runtime.recall.why_cli")
        self.assertEqual(why_invocation.script_name, "why_recall.py")
        self.assertEqual(why_invocation.args, ["why-recall", "continue memory", "--json"])

        why_not_invocation = facade.resolve_command(["why-not-recall", "continue memory"])
        self.assertEqual(why_not_invocation.command, "why-not-recall")
        self.assertEqual(why_not_invocation.module_name, "aippocampus_runtime.recall.why_cli")
        self.assertEqual(why_not_invocation.args, ["why-not-recall", "continue memory"])

        work_guard_invocation = facade.resolve_command(
            ["work-guard", "--title", "Fix LongMemEval source-side cache", "--json"]
        )
        self.assertEqual(work_guard_invocation.command, "work-guard")
        self.assertEqual(
            work_guard_invocation.module_name,
            "aippocampus_runtime.ops.issue_work_guard",
        )
        self.assertEqual(work_guard_invocation.script_name, "issue_work_guard.py")

        conversation_import = facade.resolve_command(
            [
                "import",
                "conversation",
                "--registry-dir",
                "registry",
                "--format",
                "generic-jsonl",
                "--input",
                "conversation.jsonl",
                "--json",
            ]
        )
        self.assertEqual(conversation_import.command, "import")
        self.assertEqual(conversation_import.module_name, "aippocampus_runtime.registry.api")
        self.assertEqual(conversation_import.script_name, "registry.py")
        self.assertEqual(
            conversation_import.args,
            [
                "--registry-dir",
                "registry",
                "register-source",
                "--provider",
                "generic-jsonl",
                "--input",
                "conversation.jsonl",
                "--json",
            ],
        )

        prompt_hook_status = facade.resolve_command(
            ["hooks", "prompt", "status", "--last", "--json"]
        )
        self.assertEqual(prompt_hook_status.command, "hooks")
        self.assertEqual(
            prompt_hook_status.module_name,
            "aippocampus_runtime.hooks.install_prompt",
        )
        self.assertEqual(
            prompt_hook_status.script_name,
            "install_aippocampus_prompt_hook.py",
        )
        self.assertEqual(prompt_hook_status.args, ["status", "--last", "--json"])

        action_hook_status = facade.resolve_command(
            ["hooks", "action", "status", "--json"]
        )
        self.assertEqual(action_hook_status.command, "hooks")
        self.assertEqual(
            action_hook_status.module_name,
            "aippocampus_runtime.hooks.install_action_hint",
        )
        self.assertEqual(
            action_hook_status.script_name,
            "install_aippocampus_action_hint_hook.py",
        )
        self.assertEqual(action_hook_status.args, ["status", "--json"])

        action_cache_refresh = facade.resolve_command(
            ["hooks", "action", "refresh-cache", "--cache-jsonl", "cache.jsonl", "--write", "--json"]
        )
        self.assertEqual(action_cache_refresh.command, "hooks")
        self.assertEqual(
            action_cache_refresh.module_name,
            "aippocampus_runtime.hooks.action_hint_cache",
        )
        self.assertEqual(action_cache_refresh.script_name, "action_hint_cache.py")
        self.assertEqual(
            action_cache_refresh.args,
            ["refresh-cache", "--cache-jsonl", "cache.jsonl", "--write", "--json"],
        )

        claude_hook_status = facade.resolve_command(
            ["hooks", "claude-code", "status", "--json"]
        )
        self.assertEqual(claude_hook_status.command, "hooks")
        self.assertEqual(
            claude_hook_status.module_name,
            "aippocampus_runtime.hooks.claude_code",
        )
        self.assertEqual(
            claude_hook_status.script_name,
            "aippocampus_claude_code_hooks.py",
        )
        self.assertEqual(claude_hook_status.args, ["status", "--json"])

        log_rotation = facade.resolve_command(["logs", "rotate", "--json"])
        self.assertEqual(log_rotation.command, "logs")
        self.assertEqual(
            log_rotation.module_name,
            "aippocampus_runtime.ops.log_retention",
        )
        self.assertEqual(log_rotation.script_name, "log_retention.py")
        self.assertEqual(log_rotation.args, ["rotate", "--json"])

        log_status = facade.resolve_command(["logs"])
        self.assertEqual(log_status.args, ["status"])

        storage_recovery = facade.resolve_command(["storage"])
        self.assertEqual(storage_recovery.script_name, "storage_governance.py")
        self.assertEqual(storage_recovery.args, ["--help"])

        questions = facade.resolve_command(["questions", "status", "--json"])
        self.assertEqual(questions.script_name, "questions.py")
        self.assertEqual(questions.module_name, "aippocampus_runtime.question.frontdoor")

        navigate = facade.resolve_command(["navigate", "--json"])
        self.assertEqual(navigate.script_name, "navigate.py")
        self.assertEqual(navigate.module_name, "aippocampus_runtime.navigation.frontdoor")

        sync_status = facade.resolve_command(["sync"])
        self.assertEqual(sync_status.script_name, "sync_bundle.py")
        self.assertEqual(sync_status.args, ["status"])

        object_sync_recovery = facade.resolve_command(["object-sync"])
        self.assertEqual(object_sync_recovery.script_name, "sync_object_storage.py")
        self.assertEqual(object_sync_recovery.args, ["--help"])

        self_note_append = facade.resolve_command(
            ["self-note", "append", "--current-thread", "--stdin", "--json"]
        )
        self.assertEqual(self_note_append.command, "self-note")
        self.assertEqual(
            self_note_append.module_name,
            "aippocampus_runtime.source.agent_self_note_cli",
        )
        self.assertEqual(self_note_append.script_name, "agent_self_note_cli.py")
        self.assertEqual(
            self_note_append.args,
            ["append", "--current-thread", "--stdin", "--json"],
        )

        continuity_domain_append = facade.resolve_command(
            ["continuity-domain", "append", "--event-json", "{}", "--json"]
        )
        self.assertEqual(continuity_domain_append.command, "continuity-domain")
        self.assertEqual(
            continuity_domain_append.module_name,
            "aippocampus_runtime.recall.continuity_domain_cli",
        )
        self.assertEqual(continuity_domain_append.script_name, "continuity_domain.py")
        self.assertEqual(
            continuity_domain_append.args,
            ["append", "--event-json", "{}", "--json"],
        )

        telepathy_list = facade.resolve_command(["telepathy", "list", "--json"])
        self.assertEqual(telepathy_list.command, "telepathy")
        self.assertEqual(
            telepathy_list.module_name,
            "aippocampus_runtime.ops.telepathy_handoff_store",
        )
        self.assertEqual(telepathy_list.script_name, "telepathy_handoff_store.py")
        self.assertEqual(telepathy_list.args, ["list", "--json"])

        continuity_domain_produce = facade.resolve_command(
            ["continuity-domain", "produce", "--dry-run", "--json"]
        )
        self.assertEqual(continuity_domain_produce.command, "continuity-domain")
        self.assertEqual(
            continuity_domain_produce.module_name,
            "aippocampus_runtime.recall.continuity_domain_cli",
        )
        self.assertEqual(continuity_domain_produce.script_name, "continuity_domain.py")
        self.assertEqual(continuity_domain_produce.args, ["produce", "--dry-run", "--json"])

    def test_self_note_current_thread_append_round_trips_as_atmosphere(self) -> None:
        note = "future posture: move decisively, but keep source boundary explicit."
        raw_thread_id = "codex-raw-thread-id-should-not-escape"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                **os.environ,
                "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry"),
                "CODEX_THREAD_ID": raw_thread_id,
            }
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--current-thread",
                    "--cwd",
                    str(root),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input=note,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        preview = payload["round_trip_preview"]
        atmosphere = preview["memory_atmosphere"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_append")
        self.assertTrue(payload["source_ref_attached"])
        self.assertEqual(preview["decision"], "context")
        self.assertEqual(preview["surface_counts"]["agent_self_notes"], 1)
        self.assertEqual(atmosphere[0]["action_grammar"], "direction_only")
        self.assertFalse(atmosphere[0]["trust_contract"]["treat_as_fact"])
        self.assertFalse(atmosphere[0]["claims_user_fact"])
        self.assertFalse(atmosphere[0]["claims_source_fact"])
        self.assertTrue(atmosphere[0]["source_reopen_required_before_claim"])
        self.assertNotIn(raw_thread_id, raw)
        self.assertNotIn(str(root), raw)
        self.assertNotIn("raw prompt", raw.casefold())

    def test_self_note_current_thread_long_append_returns_compact_projection_only(self) -> None:
        note = (
            "opening posture: be bold about the observed magic, "
            + "but keep the source boundary explicit and atmosphere-only; " * 14
            + "hidden tail marker should stay private."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry")}
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--current-thread",
                    "--cwd",
                    str(root),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input=note,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertLessEqual(len(payload["note"]["note_text"]), 280)
        self.assertTrue(payload["note"]["note_body_private_available"])
        self.assertFalse(payload["note"]["note_body_private_default_visible"])
        self.assertNotIn("note_body_private\":", raw)
        self.assertNotIn("hidden tail marker should stay private", raw)

    def test_self_note_plain_json_append_returns_compact_projection_only(self) -> None:
        note = (
            "plain append posture: keep private body out of default JSON; "
            + "visible-safe prefix, " * 18
            + "hidden plain append tail should stay private."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--notes-path",
                    str(notes_path),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input=note,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_append")
        self.assertLessEqual(len(payload["note"]["note_text"]), 280)
        self.assertTrue(payload["note"]["note_body_private_available"])
        self.assertEqual(payload["note"]["action_grammar"], "direction_only")
        self.assertIn("reopen attached source", payload["note"]["agent_next_action"])
        self.assertNotIn("note_body_private\":", raw)
        self.assertNotIn("hidden plain append tail should stay private", raw)

    def test_self_note_plain_text_append_names_direction_only_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--notes-path",
                    str(notes_path),
                    "keep this as a navigation breadcrumb",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("agent self-note:", proc.stdout)
        self.assertIn("authority: direction_only", proc.stdout)

    def test_self_note_current_thread_append_rejects_raw_payload_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry")}
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--current-thread",
                    "--cwd",
                    str(root),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input="tool_result stdout stderr should not become a margin note",
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

        raw = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "agent_self_note_raw_payload_rejected")
        self.assertNotIn(str(root), raw)

    def test_self_note_search_empty_returns_recovery_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            empty_search = self.run_cli(
                "self-note",
                "search",
                "no matching posture",
                "--notes-path",
                str(notes_path),
                "--json",
            )

        self.assertEqual(empty_search.returncode, 0, empty_search.stderr)
        search_payload = json.loads(empty_search.stdout)
        self.assertEqual(search_payload["count"], 0)
        self.assertEqual(search_payload["empty_state"]["decision"], "empty")
        self.assertEqual(search_payload["empty_state"]["agent_next_action"]["id"], "search_notes")
        self.assertEqual(
            search_payload["empty_state"]["agent_next_action"]["requires"],
            ["cue"],
        )
        self.assertTrue(
            any(
                action["id"] == "source_backed_recall"
                for action in search_payload["empty_state"]["safe_next_actions"]
            )
        )

    def test_self_note_read_is_intentional_not_phantom_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_path = root / "agent-self-notes.jsonl"
            append = self.run_cli(
                "self-note",
                "append",
                "--notes-path",
                str(notes_path),
                "readable low-authority breadcrumb",
                "--json",
            )
            note_id = json.loads(append.stdout)["note"]["note_id"]
            read = self.run_cli(
                "self-note",
                "read",
                note_id,
                "--notes-path",
                str(notes_path),
                "--json",
            )
            missing = self.run_cli(
                "self-note",
                "read",
                "note_missing",
                "--notes-path",
                str(notes_path),
                "--json",
            )
            help_proc = self.run_cli("self-note", "read", "--help")

        self.assertEqual(read.returncode, 0, read.stderr)
        payload = json.loads(read.stdout)
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_read")
        self.assertEqual(payload["note"]["note_id"], note_id)
        self.assertEqual(payload["note"]["action_grammar"], "direction_only")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertIn("source-backed facts", payload["agent_next_action"]["message"])
        self.assertNotEqual(missing.returncode, 0)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(missing_payload["error"]["code"], "agent_self_note_not_found")
        self.assertEqual(missing_payload["agent_next_action"]["id"], "list_notes")
        self.assertTrue(
            any(action["id"] == "search_notes" for action in missing_payload["safe_next_actions"])
        )
        self.assertEqual(help_proc.returncode, 0)
        self.assertIn("usage: aippocampus self-note read", help_proc.stdout)
        self.assertIn("direction-only", help_proc.stdout)

    def test_self_note_default_list_is_workspace_scoped_with_registry_wide_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_a = root / "project-a"
            project_b = root / "project-b"
            project_a.mkdir()
            project_b.mkdir()
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry")}
            append = self.run_cli_with_env(
                "self-note",
                "append",
                "--cwd",
                str(project_a),
                "scope breadcrumb for project a",
                "--json",
                env=env,
            )
            unrelated = self.run_cli_with_env(
                "self-note",
                "list",
                "--cwd",
                str(project_b),
                "--json",
                env=env,
            )
            registry_wide = self.run_cli_with_env(
                "self-note",
                "list",
                "--cwd",
                str(project_b),
                "--registry-wide",
                "--json",
                env=env,
            )
            human = self.run_cli_with_env(
                "self-note",
                "list",
                "--cwd",
                str(project_a),
                env=env,
            )

        self.assertEqual(append.returncode, 0, append.stderr)
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        self.assertEqual(registry_wide.returncode, 0, registry_wide.stderr)
        unrelated_payload = json.loads(unrelated.stdout)
        wide_payload = json.loads(registry_wide.stdout)
        self.assertEqual(unrelated_payload["scope"]["mode"], "current_workspace")
        self.assertEqual(unrelated_payload["count"], 0)
        self.assertEqual(wide_payload["scope"]["mode"], "registry_wide")
        self.assertEqual(wide_payload["count"], 1)
        self.assertEqual(wide_payload["rows"][0]["action_grammar"], "direction_only")
        self.assertTrue(
            wide_payload["rows"][0]["source_boundary"]["source_reopen_required_before_claim"]
        )
        self.assertIn("direction_only atmosphere", human.stdout)
        self.assertIn("boundary: direction_only", human.stdout)

    def test_continuity_domain_latest_list_and_append_require_resolvable_refs(self) -> None:
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
        self.assertTrue(
            latest_payload["domains"][0]["source_reopen_required_before_claim"]
        )
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

    def test_continuity_domain_read_path_help_is_action_card_not_bare_argparse(self) -> None:
        latest = self.run_cli("continuity-domain", "latest", "--help")
        listed = self.run_cli("continuity-domain", "list", "--help")
        report = self.run_cli("continuity-domain", "report", "--help")

        for proc in (latest, listed, report):
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Read-path action card", proc.stdout)
            self.assertIn("reopenable routes", proc.stdout)
            self.assertIn("source truth", proc.stdout)

    def test_continuity_domain_preview_is_foreground_bounded_with_broad_scan_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_continuity_domain_registry(
                root,
                thread_count=12,
                message_text=(
                    "provider orchestration continuity route needs source-backed "
                    "operator review before append publish"
                ),
            )
            bounded = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "preview",
                "--json",
            )
            human = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "preview",
            )
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
            self.assertEqual(
                preview["foreground_actions"][0]["claim_boundary"],
                "no_claim_before_reopen",
            )
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
            bounded_payload["agent_next_action"]["id"],
            {"use_candidate_preview_as_reopenable_route", "needs_broader_scan_or_cue"},
        )
        self.assertNotIn("--append", bounded_payload["agent_next_action"]["command"])
        if bounded_payload["agent_next_action"]["id"] == "use_candidate_preview_as_reopenable_route":
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

    def test_continuity_domain_preview_filters_low_information_titles_and_cues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_continuity_domain_registry(
                root,
                thread_count=1,
                title="AIppocampus issues from Candidate generated recent messages",
                message_text=(
                    "from recent messages rollout lines user Candidate generated issues 看看 "
                    "用户 角度 现在试 然后提 provider orchestration source-backed continuity route"
                ),
            )
            proc = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "preview",
                "--json",
            )

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

    def test_continuity_domain_preview_does_not_promote_generic_tool_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_continuity_domain_registry(
                root,
                thread_count=3,
                title="AIppocampus recall append maintenance runtime-contract.md",
                message_text=(
                    "recall append maintenance AIppocampus aippocampus runtime-contract.md "
                    "continuity-domain preview foreground action should prefer "
                    "provider orchestration source-backed continuity route"
                ),
            )
            proc = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "preview",
                "--json",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded_action = json.dumps(payload["agent_next_action"], ensure_ascii=False).casefold()
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

    def test_continuity_domain_preview_noisy_candidates_return_broader_scan_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_dir = self.write_continuity_domain_registry(
                root,
                thread_count=1,
                title="AIppocampus recall append maintenance",
                message_text="recall append maintenance AIppocampus aippocampus runtime-contract.md",
            )
            proc = self.run_cli(
                "continuity-domain",
                "--registry-dir",
                str(registry_dir),
                "preview",
                "--json",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["foreground_candidate_quality"], "needs_broader_scan")
        self.assertEqual(payload["agent_next_action"]["id"], "needs_broader_scan_or_cue")
        self.assertIn("--broad-scan", payload["agent_next_action"]["command"])
        self.assertNotIn("agent recall", payload["agent_next_action"]["command"])

    def test_onboard_status_text_points_to_first_recall_modes(self) -> None:
        from aippocampus_runtime.onboarding import facade as onboard_facade

        report = {
            "ok": True,
            "data": {
                "providers": [
                    {
                        "provider": "codex",
                        "state": "write_enabled",
                        "detected": True,
                        "transcript_count": 2,
                        "current_cwd_match": False,
                        "blockers": [],
                    }
                ],
                "auto": {"default_provider": "codex", "why": "safe default"},
                "storage": {"path": "C:/private/aippocampus/registry", "source": "AIPPOCAMPUS_HOME"},
            },
        }

        output = onboard_facade.render_status_text(report)

        self.assertIn("First recall", output)
        self.assertIn("exact phrase", output)
        self.assertIn("project cue", output)
        self.assertIn("time cue", output)
        self.assertIn("aippocampus search", output)
        self.assertIn("registry configured", output)
        self.assertIn("registration_available_after_consent", output)
        self.assertNotIn("write_enabled", output)
        self.assertNotIn("C:/private/aippocampus/registry", output)

    def test_onboard_status_default_is_frontstage_text_not_json_inventory(self) -> None:
        from aippocampus_runtime.onboarding import facade as onboard_facade

        report = {
            "ok": True,
            "data": {
                "provider_scope": "auto",
                "providers": [
                    {
                        "provider": "codex",
                        "state": "write_enabled",
                        "detected": True,
                        "transcript_count": 3,
                        "transcript_count_label": "3+",
                        "scan_status": "partial_frontstage_sample",
                        "current_cwd_match": False,
                        "blockers": [],
                    }
                ],
                "auto": {"default_provider": "codex", "why": "safe default"},
                "storage": {"path": "C:/private/aippocampus/registry", "source": "AIPPOCAMPUS_HOME"},
            },
        }

        with (
            patch.object(onboard_facade, "provider_status_report", return_value=report),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = onboard_facade.main(["--provider", "auto", "--status"])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("AIppocampus provider status", output)
        self.assertIn("partial frontstage sample", output)
        self.assertIn("use --operator-json for operator inventory", output)
        self.assertNotIn("use --json for operator inventory", output)
        self.assertIn("registration_available_after_consent", output)
        self.assertNotIn("write_enabled", output)
        self.assertNotIn('"providers"', output)
        self.assertNotIn("C:/private/aippocampus/registry", output)

    def test_onboard_status_frontstage_samples_provider_inventory(self) -> None:
        from aippocampus_runtime.onboarding import facade as onboard_facade

        class FakeProvider:
            def discover_sessions(self):
                for index in range(10):
                    yield types.SimpleNamespace(session_id=f"s{index}")

        with patch.object(
            onboard_facade,
            "create_conversation_provider",
            return_value=FakeProvider(),
        ):
            report = onboard_facade.provider_status_report(provider="codex", detailed=False)

        provider = report["data"]["providers"][0]
        self.assertTrue(provider["detected"])
        self.assertEqual(provider["frontstage_state"], "registration_available_after_consent")
        self.assertEqual(provider["transcript_count"], 3)
        self.assertEqual(provider["transcript_count_label"], "3+")
        self.assertEqual(provider["scan_status"], "partial_frontstage_sample")

    def test_package_facade_default_runner_is_in_process(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch("subprocess.run", side_effect=AssertionError("facade should not spawn")),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = facade.main(["mcp", "list-tools"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("tools", payload)
        self.assertTrue(any(tool["name"] == "agent_recall" for tool in payload["tools"]))
        self.assertIn("inputSchema", stdout.getvalue())

    def test_package_facade_exposes_captureable_python_api(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch("subprocess.run", side_effect=AssertionError("facade should not spawn")),
            patch("sys.stdout", new=StringIO()) as ambient_stdout,
            patch("sys.stderr", new=StringIO()) as ambient_stderr,
        ):
            result = facade.run_command(["mcp", "list-tools"], capture_output=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.invocation.command, "mcp")
        payload = json.loads(result.stdout)
        self.assertIn("tools", payload)
        self.assertTrue(any(tool["name"] == "agent_recall" for tool in payload["tools"]))
        self.assertNotIn("missing_key_tools", payload)
        self.assertEqual(result.stderr, "")
        self.assertEqual(ambient_stdout.getvalue(), "")
        self.assertEqual(ambient_stderr.getvalue(), "")

    def test_package_facade_prefers_argv_aware_main_without_sys_argv_shim(self) -> None:
        from aippocampus_runtime.cli import facade

        module_name = "tests._fake_facade_argv_main"
        fake_module = types.ModuleType(module_name)
        seen: dict[str, object] = {}

        def main(argv: list[str] | None = None) -> int:
            seen["argv"] = list(argv or [])
            seen["sys_argv"] = list(sys.argv)
            return 7

        fake_module.main = main  # type: ignore[attr-defined]
        old_module = sys.modules.get(module_name)
        old_argv = sys.argv[:]
        sys.modules[module_name] = fake_module
        sys.argv = ["outer-host", "--keep"]
        try:
            code = facade.run_module_main(module_name, "fake_child.py", ["--flag", "value"])
        finally:
            sys.argv = old_argv
            if old_module is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = old_module

        self.assertEqual(code, 7)
        self.assertEqual(seen["argv"], ["--flag", "value"])
        self.assertEqual(seen["sys_argv"], ["outer-host", "--keep"])

    def test_package_facade_public_bundle_and_sync_commands_are_argv_aware(self) -> None:
        from aippocampus_runtime.artifacts import export_bundle, import_bundle
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.sync import bundle
        from aippocampus_runtime.sync.object_storage import cli as object_storage_cli

        self.assertTrue(facade.main_accepts_argv(export_bundle.main))
        self.assertTrue(facade.main_accepts_argv(import_bundle.main))
        self.assertTrue(facade.main_accepts_argv(bundle.main))
        self.assertTrue(facade.main_accepts_argv(object_storage_cli.main))

    def test_package_facade_capture_api_handles_usage_and_unknown_commands(self) -> None:
        from aippocampus_runtime.cli import facade

        help_result = facade.run_command(["--help"], capture_output=True)
        unknown_result = facade.run_command(["nope"], capture_output=True)

        self.assertTrue(help_result.ok)
        self.assertIn("Commands:", help_result.stdout)
        self.assertIsNone(help_result.invocation)
        self.assertFalse(unknown_result.ok)
        self.assertEqual(unknown_result.exit_code, 2)
        self.assertIn("unknown command: nope", unknown_result.stderr)
        self.assertIn("Commands:", unknown_result.stderr)

        unknown_json = facade.run_command(["nope", "--json"], capture_output=True)
        payload = json.loads(unknown_json.stdout)
        self.assertFalse(unknown_json.ok)
        self.assertEqual(unknown_json.exit_code, 2)
        self.assertEqual(payload["error"]["code"], "unsupported_operation")
        self.assertEqual(payload["error"]["class"], "usage_error")
        self.assertEqual(payload["safe_next_actions"][0]["command"], "aippocampus --help")
        self.assertEqual(unknown_json.stderr, "")

    def test_background_routes_are_discoverable_without_raw_unknown_command(self) -> None:
        from aippocampus_runtime.cli import facade

        agent = facade.run_command(["agent", "--json"], capture_output=True)
        dream = facade.run_command(["dream", "--json"], capture_output=True)
        subconscious = facade.run_command(["subconscious", "--json"], capture_output=True)

        self.assertEqual(agent.exit_code, 0)
        agent_payload = json.loads(agent.stdout)
        self.assertIn(
            "background",
            {choice["id"] for choice in agent_payload["choices"]},
        )
        self.assertEqual(dream.exit_code, 2)
        dream_payload = json.loads(dream.stdout)
        self.assertEqual(dream_payload["agent_next_action"]["command"], 'aippocampus agent background "task cue" --json')
        self.assertEqual(subconscious.exit_code, 2)
        self.assertEqual(subconscious.stderr, "")
        self.assertNotIn("unknown command", dream.stderr)
        self.assertNotIn("unknown command", subconscious.stderr)

    def test_mcp_list_tools_default_is_schema_and_status_is_compact_readiness(self) -> None:
        proc = self.run_cli("mcp", "list-tools")
        status = self.run_cli("mcp", "status")
        full = self.run_cli("mcp", "list-tools", "--json")

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        default_tools = json.loads(proc.stdout)["tools"]
        self.assertTrue(any(tool["name"] == "agent_recall" for tool in default_tools))
        self.assertIn("inputSchema", proc.stdout)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        readiness = json.loads(status.stdout)
        self.assertEqual(readiness["kind"], "aippocampus_mcp_tool_readiness")
        self.assertIn("agent_recall", readiness["key_tools_present"])
        self.assertNotIn("inputSchema", status.stdout)
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        tools = json.loads(full.stdout)["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))

    def test_first_run_command_aliases_are_copy_pasteable(self) -> None:
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.mcp import server as mcp_server

        plugin_status = facade.resolve_command(["plugin", "status", "--json"])
        maintenance = facade.resolve_command(["maintenance", "--json"])

        self.assertEqual(plugin_status.module_name, "aippocampus_runtime.update.cli")
        self.assertEqual(plugin_status.args, ["status", "--json"])
        self.assertEqual(maintenance.module_name, "aippocampus_runtime.ops.maintenance")

        with patch("sys.stdout", new=StringIO()) as stdout:
            code = mcp_server.main(["list-tools"])
        self.assertEqual(code, 0)
        default_tools = json.loads(stdout.getvalue())["tools"]
        self.assertTrue(any(tool["name"] == "agent_recall" for tool in default_tools))

        with patch("sys.stdout", new=StringIO()) as full_stdout:
            code = mcp_server.main(["list-tools", "--json"])
        self.assertEqual(code, 0)
        tools = json.loads(full_stdout.getvalue())["tools"]
        self.assertTrue(any(tool["name"] == "memory_health" for tool in tools))

    def test_sync_status_without_sync_dir_matches_mcp_capability_truth(self) -> None:
        proc = self.run_cli("sync", "status", "--json")

        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "available_requires_sync_dir")
        self.assertEqual(data["backend"], "local_folder")
        self.assertIn("push", data["commands"])
        self.assertEqual(data["agent_next_action"]["command_template"], "aippocampus sync status --sync-dir {sync_dir} --json")
        self.assertTrue(all("command" not in action for action in data["safe_next_actions"]))

    def test_sync_status_without_sync_dir_human_output_is_not_configured_ok(self) -> None:
        proc = self.run_cli("sync", "status")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("capability available; no sync folder selected", proc.stdout)
        self.assertIn("template: aippocampus sync status --sync-dir {sync_dir} --json", proc.stdout)
        self.assertNotIn("sync status: ok", proc.stdout)

    def test_sync_status_preserves_child_exit_code_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("sync", "status", "--sync-dir", tmp, "--json")

        self.assertEqual(proc.returncode, 2)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertFalse(data["manifest_exists"])

    def test_operator_cli_expected_errors_return_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_proc = self.run_cli(
                "export",
                "--cwd",
                tmp,
                "--redaction-profile",
                "public-export",
                "--output",
                str(Path(tmp) / "bundle.zip"),
            )
            import_proc = self.run_cli(
                "import",
                str(Path(tmp) / "does-not-exist.zip"),
                "--dest",
                tmp,
                "--name",
                "missing",
            )

        self.assertEqual(export_proc.returncode, 2)
        self.assertNotIn("Traceback", export_proc.stderr + export_proc.stdout)
        export_payload = json.loads(export_proc.stdout)
        self.assertEqual(export_payload["error"]["code"], "public_export_requires_no_raw")

        self.assertEqual(import_proc.returncode, 2)
        self.assertNotIn("Traceback", import_proc.stderr + import_proc.stdout)
        import_payload = json.loads(import_proc.stdout)
        self.assertEqual(import_payload["error"]["code"], "bundle_not_found")
        self.assertIn("<local-path-redacted>", import_payload["error"]["message"])
        self.assertNotIn(str(Path(tmp)), import_proc.stdout)

    def test_search_limits_and_public_metadata_mode_do_not_expand_private_snippets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / ".aippocampus" / "clean-source"
            clean.mkdir(parents=True)
            private_marker = "private source tail should never appear in metadata mode"
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg_private",
                        "turn_id": "turn_private",
                        "source_id": "source_private",
                        "source_ref": "session:private#L1",
                        "source_line": 1,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 1,
                        "is_final": True,
                        "scope_labels": ["technical_work"],
                        "timestamp": "2026-06-15T00:00:00Z",
                        "text": "aippocampus " + ("context " * 80) + private_marker,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            zero = self.run_cli(
                "search",
                "aippocampus",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
                "--json",
                "--max",
                "1",
                "--snippet-chars",
                "0",
            )
            public = self.run_cli(
                "search",
                "aippocampus",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
                "--json",
                "--max",
                "1",
                "--snippet-chars",
                "20",
                "--public",
            )
            negative = self.run_cli("search", "aippocampus", "--max", "-1", "--json")
            no_match = self.run_cli(
                "search",
                "zzzz-no-such-phrase",
                "--cwd",
                str(root),
                "--clean-source-dir",
                str(clean),
                "--json",
            )

        self.assertEqual(zero.returncode, 0, zero.stderr)
        zero_payload = json.loads(zero.stdout)
        self.assertEqual(zero_payload["matches"][0]["snippet"], "")
        self.assertTrue(zero_payload["matches"][0]["snippet_omitted"])
        self.assertEqual(public.returncode, 0, public.stderr)
        public_payload = json.loads(public.stdout)
        encoded_public = json.dumps(public_payload, ensure_ascii=False)
        self.assertEqual(
            public_payload["output_boundary"],
            "public_metadata_with_capped_source_snippets_no_reopen_refs",
        )
        self.assertTrue(public_payload["privacy"]["metadata_only"])
        self.assertTrue(public_payload["matches"][0]["snippet"])
        self.assertLessEqual(len(public_payload["matches"][0]["snippet"]), 24)
        self.assertFalse(public_payload["matches"][0]["snippet_omitted"])
        self.assertTrue(public_payload["matches"][0]["source_refs_omitted"])
        self.assertNotIn("message_id", encoded_public)
        self.assertNotIn("turn_private", encoded_public)
        self.assertNotIn("session:private", encoded_public)
        self.assertNotIn(private_marker, encoded_public)
        self.assertNotEqual(negative.returncode, 0)
        negative_payload = json.loads(negative.stdout)
        self.assertEqual(negative_payload["error"]["code"], "usage_error")
        self.assertIn("must be >= 1", negative_payload["error"]["message"])
        self.assertNotEqual(no_match.returncode, 0)
        no_match_payload = json.loads(no_match.stdout)
        self.assertEqual(no_match_payload["match_count"], 0)
        self.assertEqual(no_match_payload["decision"], "no_source_backed_snippet_found")
        self.assertIn("agent recall", " ".join(no_match_payload["recovery_actions"]))
        self.assertFalse(
            no_match_payload["source_boundary"]["source_backed_claim_allowed"]
        )

    def test_warm_status_json_is_bounded_and_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = root / "private-warm-jobs"
            job_dir.mkdir()
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            (job_dir / "warm-public.json").write_text(
                json.dumps({"created_at": now.replace("+00:00", "Z")}),
                encoding="utf-8",
            )
            proc = self.run_cli("warm", "status", "--job-dir", str(job_dir), "--json")

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        activity = payload["job_activity"]
        self.assertEqual(payload["kind"], "aippocampus_warm_ambient_status")
        self.assertEqual(payload["status"], "pending")
        self.assertFalse(activity["worker_process_active"])
        self.assertFalse(activity["pending_jobs_are_worker_evidence"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_included"])
        self.assertNotIn(str(root), raw)

    def test_warm_status_human_keeps_optional_queue_from_blocking_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = root / "private-warm-jobs"
            job_dir.mkdir()
            stale_job = job_dir / "warm-stale.json"
            stale_job.write_text(
                json.dumps({"created_at": "2020-01-01T00:00:00Z"}),
                encoding="utf-8",
            )
            os.utime(stale_job, (1577836800, 1577836800))
            human = self.run_cli("warm", "status", "--job-dir", str(job_dir))
            strict = self.run_cli(
                "warm",
                "status",
                "--job-dir",
                str(job_dir),
                "--strict-exit-code",
            )

        raw = human.stdout + human.stderr + strict.stdout + strict.stderr
        self.assertEqual(human.returncode, 0, raw)
        self.assertEqual(strict.returncode, 2, raw)
        self.assertIn("AIppocampus warm ambient", human.stdout)
        self.assertIn("ordinary recall: usable", human.stdout)
        self.assertIn("next: provider_or_worker_unavailable_optional", human.stdout)
        self.assertIn("optional background warming", human.stdout)
        self.assertNotIn(str(root), raw)


if __name__ == "__main__":
    unittest.main()
