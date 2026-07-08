from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.cli import facade
from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    render_recall_human,
)
from tests.aippocampus.cli_fixtures import parse_cli_json, run_aippocampus_cli
from tests.aippocampus.frontstage_assertions import (
    assert_compact_detail_affordances,
    assert_compact_frontstage_payload,
    assert_semantic_human_output,
)


class TtyStringIO(StringIO):
    def isatty(self) -> bool:
        return True


class AippocampusCliRecoveryCardTests(unittest.TestCase):
    run_cli = staticmethod(run_aippocampus_cli)

    def run_cli_with_env(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return run_aippocampus_cli(*args, env=env)

    def test_status_help_is_decision_card_not_health_flag_wall(self) -> None:
        proc = self.run_cli("status", "--help")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Status decision card", proc.stdout)
        self.assertIn("pulse: one-line readiness", proc.stdout)
        self.assertIn("status: summary/current posture", proc.stdout)
        self.assertIn("health: full diagnostics/operator view", proc.stdout)
        self.assertIn("aippocampus update status --json", proc.stdout)
        self.assertNotIn("--index-dir", proc.stdout)
        self.assertNotIn("--deep-graph-bytes", proc.stdout)

    def test_health_help_is_task_first_and_operator_json_implies_json(self) -> None:
        help_proc = self.run_cli("health", "--help")
        self.assertEqual(help_proc.returncode, 0)
        self.assertIn("Task-first health card", help_proc.stdout)
        self.assertIn("aippocampus health --agent-json", help_proc.stdout)
        self.assertIn("--operator-json", help_proc.stdout)
        self.assertIn("implies JSON output", help_proc.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("health", "--cwd", tmp, "--operator-json")

        payload = parse_cli_json(self, proc, expected_returncode=0, label="health operator")
        self.assertIn("recommended_actions", payload)

    def test_doctor_help_is_task_first(self) -> None:
        doctor = self.run_cli("doctor", "--help")
        provider = self.run_cli("doctor", "provider", "--help")
        spend = self.run_cli("doctor", "spend", "--help")
        config = self.run_cli("doctor", "config", "--help")

        self.assertEqual(doctor.returncode, 0)
        self.assertIn("Task-first diagnostics", doctor.stdout)
        self.assertIn("provider  Check whether optional LLM/provider keys", doctor.stdout)
        self.assertIn("spend     Review local model-spend/yield", doctor.stdout)
        self.assertIn("config    Audit registered AIPPOCAMPUS_* knobs", doctor.stdout)

        self.assertEqual(provider.returncode, 0)
        self.assertIn("Provider doctor answers", provider.stdout)
        self.assertIn("No-key source-backed recall/search remains usable", provider.stdout)
        self.assertLess(provider.stdout.index("Provider doctor answers"), provider.stdout.index("--model-route"))

        self.assertEqual(spend.returncode, 0)
        self.assertIn("Spend doctor answers", spend.stdout)
        self.assertIn("aggregate counts only", spend.stdout)

        self.assertEqual(config.returncode, 0)
        self.assertIn("Config doctor answers", config.stdout)
        self.assertIn("values are never printed", config.stdout)

    def test_plugin_help_leads_with_codex_install_and_lists_status(self) -> None:
        family = self.run_cli("plugin", "--help")
        install = self.run_cli("plugin", "install", "--help")

        self.assertEqual(family.returncode, 0)
        self.assertIn("aippocampus plugin install --codex --verify", family.stdout)
        self.assertIn("status", family.stdout)
        self.assertIn("aippocampus plugin status --json", family.stdout)

        self.assertEqual(install.returncode, 0)
        self.assertIn("Ordinary Codex setup path", install.stdout)
        self.assertIn("aippocampus plugin install --codex --verify", install.stdout)
        self.assertIn("aippocampus update status --json", install.stdout)
        self.assertIn("aippocampus agent recall", install.stdout)
        self.assertLess(
            install.stdout.index("aippocampus plugin install --codex --verify"),
            install.stdout.index("--repo-root"),
        )

    def test_natural_setup_memory_privacy_controls_commands_recover_to_cards(self) -> None:
        setup = self.run_cli("setup", "--help")
        install = self.run_cli("install", "--help")
        memory = self.run_cli("memory", "--help")
        privacy = self.run_cli("privacy", "--help")
        controls = self.run_cli("controls", "--help")

        for proc in (setup, install, memory, privacy, controls):
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("unknown command", proc.stderr)

        self.assertIn("First-run setup card", setup.stdout)
        self.assertIn("aippocampus plugin install --codex --verify", setup.stdout)
        self.assertIn("aippocampus update status --json", setup.stdout)
        self.assertIn("First-run install card", install.stdout)
        self.assertIn("aippocampus agent recall", install.stdout)
        self.assertIn("Memory action card", memory.stdout)
        self.assertIn("source-backed", memory.stdout)
        self.assertIn("aippocampus search", memory.stdout)
        self.assertIn("agent recall finds fuzzy continuity routes", memory.stdout)
        self.assertIn("search finds exact/source wording", memory.stdout)
        self.assertIn("Privacy and control card", privacy.stdout)
        self.assertIn("pause", privacy.stdout)
        self.assertIn("provider-key", privacy.stdout)
        self.assertIn("same-user local conversation source stays usable", privacy.stdout)
        self.assertIn("raw external projection", privacy.stdout)
        self.assertIn("do-not-use-here is current-scope exclusion", privacy.stdout)
        self.assertNotIn("approve every recall", privacy.stdout.casefold())
        self.assertNotIn("confirm every memory", privacy.stdout.casefold())
        self.assertIn("Personal controls card", controls.stdout)
        self.assertIn("do-not-use-here", controls.stdout)
        self.assertIn("forget is an explicit target workflow", controls.stdout)

    def test_agent_parent_json_is_foreground_chooser_not_argparse(self) -> None:
        proc = self.run_cli("agent", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = parse_cli_json(self, proc, expected_returncode=0, label="agent parent")
        self.assertEqual(payload["kind"], "aippocampus_agent_recovery")
        self.assertEqual(payload["status"], "command_required")
        self.assertEqual(payload["choices"][0]["id"], "recall")
        self.assertEqual(payload["choices"][1]["id"], "aippo")
        self.assertIn("aippocampus agent recall", payload["choices"][0]["command_template"])
        self.assertIn("aippocampus agent aippo", payload["choices"][1]["command"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn("command_template", encoded)
        for choice in payload["choices"]:
            if "command" in choice:
                self.assertNotIn("<", choice["command"])
                self.assertNotIn(">", choice["command"])

    def test_memory_privacy_controls_json_frontdoors_are_status_cards(self) -> None:
        cards = {
            "memory": self.run_cli("memory", "--json"),
            "privacy": self.run_cli("privacy", "--json"),
            "controls": self.run_cli("controls", "--json"),
        }

        for name, proc in cards.items():
            payload = parse_cli_json(self, proc, expected_returncode=0, label=name)
            self.assertNotIn("unknown command", proc.stderr)
            self.assertEqual(payload["surface_class"], "foreground_chooser_card")
            self.assertIn("safe_next_actions", payload)
            self.assertNotIn("agent_next_action", payload)
            self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
            for action in payload["safe_next_actions"]:
                self.assertIn("mutation_risk", action)
                self.assertIn("claim_boundary", action)
                if "command" in action:
                    self.assertNotIn("<", action["command"])
                    self.assertNotIn(">", action["command"])

        memory_payload = parse_cli_json(self, cards["memory"], expected_returncode=0, label="memory")
        self.assertEqual(memory_payload["kind"], "aippocampus_memory_chooser")
        self.assertIn(
            "aippocampus agent recall",
            memory_payload["foreground_action"]["command_template"],
        )
        self.assertEqual(
            memory_payload["command_gradient"]["agent_recall"],
            "fuzzy continuity route finding from old decisions, corrections, or handoffs",
        )
        self.assertEqual(
            memory_payload["intent_gradient"]["search"],
            "exact/source wording search when a distinctive phrase is known",
        )

        privacy_payload = parse_cli_json(self, cards["privacy"], expected_returncode=0, label="privacy")
        self.assertEqual(privacy_payload["kind"], "aippocampus_privacy_chooser")
        self.assertEqual(
            privacy_payload["control_gradient"]["do_not_use_here"],
            "current-scope exclusion for a bad route",
        )
        privacy_action_ids = {
            action["id"]
            for action in [privacy_payload["foreground_action"], *privacy_payload["safe_next_actions"]]
        }
        self.assertIn("open_controls", privacy_action_ids)
        privacy_actions = {action["id"]: action for action in privacy_payload["safe_next_actions"]}
        self.assertEqual(privacy_actions["export_boundary"]["command"], "aippocampus export --json")
        self.assertEqual(
            privacy_payload["default_posture"]["ordinary_conversation_source"],
            "private_route_or_reopenable",
        )
        self.assertEqual(
            privacy_payload["default_posture"]["secret_like"],
            "hard_block",
        )
        self.assertEqual(
            privacy_payload["default_posture"]["unprovided_background_scan"],
            "hard_block",
        )
        self.assertEqual(
            privacy_payload["default_posture"]["raw_external_projection"],
            "blocked_without_explicit_opt_in",
        )
        self.assertEqual(
            privacy_payload["default_posture"]["cross_domain_sensitive_use"],
            "purpose_check",
        )
        encoded_privacy = json.dumps(privacy_payload, ensure_ascii=False).casefold()
        self.assertIn("public-core-boundary.md#personalcore-default", encoded_privacy)
        self.assertNotIn("--help", encoded_privacy)
        self.assertNotIn("approve every recall", encoded_privacy)
        self.assertNotIn("confirm every memory", encoded_privacy)

        controls_payload = parse_cli_json(self, cards["controls"], expected_returncode=0, label="controls")
        self.assertEqual(controls_payload["kind"], "aippocampus_controls_chooser")
        self.assertTrue(any(action["id"] == "do_not_use_here" for action in controls_payload["safe_next_actions"]))
        self.assertEqual(
            controls_payload["control_gradient"]["forget"],
            "stronger explicit target workflow; no surprise deletion from the chooser",
        )

    def test_frontdoor_accept_runs_only_concrete_read_only_actions(self) -> None:
        executed = self.run_cli("logs", "--accept", "status", "--json")
        executed_payload = parse_cli_json(self, executed, expected_returncode=0, label="logs accept")
        self.assertEqual(executed_payload["kind"], "aippocampus_logs_chooser_accept_result")
        self.assertTrue(executed_payload["accepted_action_ran"])
        self.assertEqual(executed_payload["accepted_action_id"], "status")
        self.assertEqual(executed_payload["status"], "accepted_action_ran")
        self.assertEqual(executed_payload["result"]["kind"], "aippocampus_logs_status_card")
        self.assertTrue(executed_payload["write_boundary"]["no_write_happened"])
        self.assertFalse(executed_payload["write_boundary"]["explicit_write_required"])

        template = self.run_cli("memory", "--accept", "--json")
        template_payload = parse_cli_json(self, template, expected_returncode=2, label="memory accept")
        self.assertFalse(template_payload["accepted_action_ran"])
        self.assertEqual(template_payload["status"], "needs_input")
        self.assertEqual(template_payload["reason"], "selected_action_needs_input")
        self.assertEqual(template_payload["requires"], ["continuity_cue"])
        self.assertTrue(template_payload["action"]["template_only"])
        self.assertTrue(template_payload["write_boundary"]["no_write_happened"])

        write_like = self.run_cli("logs", "--accept", "rotate_apply", "--json")
        write_payload = parse_cli_json(self, write_like, expected_returncode=2, label="logs write accept")
        self.assertFalse(write_payload["accepted_action_ran"])
        self.assertEqual(write_payload["status"], "explicit_write_required")
        self.assertEqual(write_payload["reason"], "selected_action_is_not_read_only")
        self.assertEqual(write_payload["accepted_action_id"], "rotate_apply")
        self.assertTrue(write_payload["write_boundary"]["explicit_write_required"])

    def test_plugin_install_status_recovers_to_plugin_status(self) -> None:
        proc = self.run_cli("plugin", "install", "--status")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Plugin status readiness card", proc.stdout)
        self.assertIn("aippocampus plugin status --json", proc.stdout)

    def test_status_alias_routes_to_health_instead_of_unknown_command(self) -> None:
        help_proc = self.run_cli("status", "--help")

        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("usage: aippocampus health", help_proc.stdout)
        self.assertNotIn("unknown command", help_proc.stderr)

    def test_search_and_self_note_top_help_are_decision_first(self) -> None:
        search = self.run_cli("search", "--help")
        self_note = self.run_cli("self-note", "--help")

        self.assertEqual(search.returncode, 0, search.stderr)
        self.assertIn("Search local clean source", search.stdout)
        self.assertIn("exact phrase", search.stdout)
        self.assertIn("aippocampus agent recall", search.stdout)
        self.assertIn("No match", search.stdout)
        self.assertLess(search.stdout.index("exact phrase"), search.stdout.index("--clean-source-dir"))

        self.assertEqual(self_note.returncode, 0, self_note.stderr)
        self.assertIn("Weak-memory decision card", self_note.stdout)
        self.assertIn("direction_only", self_note.stdout)
        self.assertIn("weak scent", self_note.stdout)
        self.assertIn("factual", self_note.stdout.casefold())
        self.assertIn("aippocampus agent recall", self_note.stdout)
        self.assertLess(self_note.stdout.index("Weak-memory"), self_note.stdout.index("--notes-path"))

    def test_bare_self_note_is_action_card_not_argparse(self) -> None:
        human = self.run_cli("self-note")
        machine = self.run_cli("self-note", "--json")

        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertNotIn("usage:", human.stdout + human.stderr)
        self.assertIn("AIppocampus self-note", human.stdout)
        self.assertIn("direction_only", human.stdout)
        self.assertIn("aippocampus self-note append", human.stdout)
        self.assertIn("aippocampus agent recall", human.stdout)

        self.assertEqual(machine.returncode, 0, machine.stderr)
        payload = parse_cli_json(self, machine, expected_returncode=0, label="self-note bare")
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_recovery")
        self.assertEqual(payload["error"]["code"], "self_note_command_required")
        self.assertFalse(payload["write_boundary"]["written"])
        self.assertTrue(payload["source_boundary"]["direction_only_is_not_source_truth"])
        command_values = {
            choice.get("command") or choice.get("command_template")
            for choice in payload["choices"]
        }
        self.assertEqual(
            command_values,
            {
                'aippocampus self-note append --current-thread "{note_text}"',
                'aippocampus self-note search "{cue}" --json',
                "aippocampus self-note list --json",
                "aippocampus self-note read {note_id} --json",
            },
        )
        for choice in payload["choices"]:
            if choice.get("label") != "list":
                self.assertTrue(choice.get("template_only"))
                self.assertIn("requires", choice)
        self.assertEqual(executable_command_violations(payload), [])

    def test_self_note_list_empty_state_uses_structured_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "empty-self-notes.jsonl"
            proc = self.run_cli(
                "self-note",
                "list",
                "--notes-path",
                str(notes_path),
                "--json",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = parse_cli_json(self, proc, expected_returncode=0, label="self-note list empty")
        empty_state = payload["empty_state"]
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(empty_state["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", empty_state)
        self.assertIsInstance(empty_state["foreground_action"], dict)
        self.assertNotIn(empty_state["foreground_action"], empty_state["safe_next_actions"])
        self.assertEqual(empty_state["foreground_action"]["id"], "continue_without_self_notes")
        self.assertTrue(empty_state["foreground_action"]["continue_without_command"])
        self.assertNotIn("command", empty_state["foreground_action"])
        self.assertEqual(
            empty_state["safe_next_actions"][0]["command_template"],
            'aippocampus agent recall "{cue}" --json',
        )
        self.assertNotEqual(empty_state["foreground_action"].get("id"), "list_notes")
        self.assertNotIn("Append a short direction-only note", json.dumps(empty_state))

    def test_self_note_read_missing_id_is_not_not_found(self) -> None:
        proc = self.run_cli("self-note", "read", "--json")

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = parse_cli_json(self, proc, expected_returncode=2, label="self-note read missing id")
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_read")
        self.assertEqual(payload["error"]["code"], "needs_note_id")
        self.assertFalse(payload["write_boundary"]["written"])
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "list_notes")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(action_ids, ["search_notes", "source_backed_recall"])
        self.assertEqual(payload["foreground_action"]["command"], "aippocampus self-note list --json")
        self.assertEqual(payload["safe_next_actions"][0]["requires"], ["cue"])
        self.assertIn("command_template", payload["safe_next_actions"][0])

    def test_self_note_search_missing_cue_is_recovery_card(self) -> None:
        proc = self.run_cli("self-note", "search", "--json")

        self.assertEqual(proc.returncode, 2)
        payload = parse_cli_json(self, proc, expected_returncode=2, label="self-note search missing cue")
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["status"], "needs_cue")
        self.assertEqual(payload["error"]["code"], "needs_cue")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "search_notes")
        self.assertEqual(payload["foreground_action"]["requires"], ["cue"])
        self.assertNotIn('"query": ""', encoded)
        self.assertNotIn("<cue>", encoded)

    def test_warm_help_leads_with_safe_status_path(self) -> None:
        proc = self.run_cli("warm", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Warm ambient recall is optional", proc.stdout)
        self.assertIn("aippocampus warm status", proc.stdout)
        self.assertIn("does not make model calls", proc.stdout)
        self.assertIn("ordinary source-backed", proc.stdout.casefold())
        self.assertLess(proc.stdout.index("aippocampus warm status"), proc.stdout.index("--prompt"))

    def test_bare_warm_json_is_safe_status_chooser(self) -> None:
        proc = self.run_cli("warm", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = parse_cli_json(self, proc, expected_returncode=0, label="warm chooser")
        self.assertEqual(payload["kind"], "aippocampus_warm_chooser")
        self.assertEqual(payload["status"], "command_or_prompt_required")
        self.assertEqual(payload["choices"][0]["id"], "status")
        self.assertEqual(payload["choices"][0]["command"], "aippocampus warm status --json")
        self.assertTrue(any(choice.get("operator_only") for choice in payload["choices"]))
        for choice in payload["choices"]:
            if "command" in choice:
                self.assertNotIn("<", choice["command"])
                self.assertNotIn(">", choice["command"])

    def test_doctor_config_human_output_is_decision_grade(self) -> None:
        proc = self.run_cli("doctor", "config")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Configured env vars:", proc.stdout)
        self.assertNotIn("Sensitive env vars present:", proc.stdout)
        self.assertNotIn("Registered knobs:", proc.stdout)
        self.assertNotIn("Cannot claim:", proc.stdout)
        self.assertIn("provider connectivity", proc.stdout)
        self.assertIn("doctor provider", proc.stdout)
        self.assertIn("values are not printed", proc.stdout)

    def test_storage_gc_help_explains_apply_and_high_risk_flags(self) -> None:
        proc = self.run_cli("storage", "gc", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Safe first step", proc.stdout)
        self.assertIn("storage gc --dry-run --summary-json --cwd .", proc.stdout)
        self.assertIn("performs no writes", proc.stdout)
        self.assertIn("deterministic source, manifest", proc.stdout)
        self.assertIn("--apply --class rebuildable", proc.stdout)
        self.assertIn("Private/high-risk", proc.stdout)
        self.assertIn("local filesystem paths", proc.stdout)
        self.assertLess(proc.stdout.index("Safe first step"), proc.stdout.index("--include-active"))

    def test_storage_gc_tty_no_flag_runs_human_dry_run_but_pipe_stays_recovery(self) -> None:
        module_name = "aippocampus_runtime.ops.storage_governance"
        fake_module = types.ModuleType(module_name)
        seen_argv: list[list[str] | None] = []

        def main(argv: list[str] | None = None) -> int:
            seen_argv.append(argv)
            print("AIppocampus storage governance dry-run")
            return 0

        fake_module.main = main
        previous = sys.modules.get(module_name)
        sys.modules[module_name] = fake_module
        stdout = TtyStringIO()
        stderr = StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                invocation, code = facade.dispatch(["storage", "gc"])
        finally:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIsNotNone(invocation)
        self.assertEqual([["gc", "--dry-run"]], seen_argv)
        self.assertIn("AIppocampus storage governance dry-run", stdout.getvalue())

        piped = facade.run_command(["storage", "gc"], capture_output=True)
        self.assertTrue(piped.ok, piped.stderr)
        self.assertIn("storage gc --dry-run --summary-json --cwd .", piped.stdout)

        json_recovery = facade.run_command(["storage", "gc", "--json"], capture_output=True)
        self.assertTrue(json_recovery.ok, json_recovery.stderr)
        payload = json.loads(json_recovery.stdout)
        self.assertEqual(payload["kind"], "aippocampus_storage_gc_recovery")

    def test_questions_and_navigation_frontdoors_are_bounded_read_paths(self) -> None:
        questions = self.run_cli("questions", "status", "--json")
        navigate = self.run_cli("navigate", "--json")

        self.assertEqual(questions.returncode, 0, questions.stderr)
        question_payload = parse_cli_json(self, questions)
        self.assertEqual(question_payload["kind"], "aippocampus_question_tracking_status")
        self.assertFalse(question_payload["source_boundary"]["model_job_started"])
        self.assertTrue(
            question_payload["source_boundary"]["source_reopen_required_before_claim"]
        )
        self.assertNotIn("jobs", question_payload["summary"])
        self.assertNotIn("registry", question_payload["summary"])
        self.assertFalse(question_payload["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn("agent_next_action", question_payload)
        self.assertIsInstance(question_payload["foreground_action"], dict)
        self.assertIn("safe_next_actions", question_payload)
        if question_payload["summary"].get("open_question_count"):
            self.assertEqual(question_payload["foreground_action"]["id"], "list_open_question_routes")
            self.assertEqual(
                question_payload["foreground_action"]["command"],
                "aippocampus questions list --max 8 --json",
            )

        self.assertEqual(navigate.returncode, 0, navigate.stderr)
        navigation_payload = parse_cli_json(self, navigate)
        self.assertEqual(navigation_payload["status"], "needs_cue")
        self.assertEqual(navigation_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertFalse(navigation_payload["source_boundary"]["model_job_started"])
        self.assertNotIn("old cue", json.dumps(navigation_payload, ensure_ascii=False))
        self.assertNotIn("foreground_next_action", navigation_payload)
        self.assertNotIn("foreground_next_actions", navigation_payload)
        self.assertNotIn("agent_next_action", navigation_payload)
        self.assertNotIn(navigation_payload["foreground_action"], navigation_payload["safe_next_actions"])
        navigate_action = navigation_payload["foreground_action"]
        self.assertEqual(navigate_action["requires"], ["cue"])
        self.assertIn("command_template", navigate_action)
        self.assertNotIn("command", navigate_action)
        self.assertEqual(executable_command_violations(navigation_payload), [])

    def test_navigate_default_hides_internal_module_commands(self) -> None:
        human = self.run_cli("navigate")
        compact = self.run_cli("navigate", "--json")
        cued = self.run_cli("navigate", "provider orchestration", "--json")
        operator = self.run_cli("navigate", "--operator-json")

        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("operator details: aippocampus navigate --operator-json", human.stdout)
        self.assertNotIn("python -m aippocampus_runtime", human.stdout)

        self.assertEqual(compact.returncode, 0, compact.stderr)
        compact_payload = parse_cli_json(self, compact)
        self.assertEqual(compact_payload["detail"], "compact")
        self.assertEqual(compact_payload["status"], "needs_cue")
        self.assertNotIn("old cue", json.dumps(compact_payload, ensure_ascii=False))
        assert_compact_detail_affordances(self, compact_payload, surface="cli.navigate.needs_cue")
        self.assertNotIn("diagnostic_command", json.dumps(compact_payload))

        self.assertEqual(cued.returncode, 0, cued.stderr)
        cued_payload = parse_cli_json(self, cued)
        self.assertEqual(cued_payload["status"], "foreground_route_available")
        self.assertTrue(cued_payload["cue_supplied"])
        self.assertEqual(cued_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", cued_payload)
        self.assertIn("provider orchestration", cued_payload["foreground_action"]["command"])

        self.assertEqual(operator.returncode, 0, operator.stderr)
        operator_payload = parse_cli_json(self, operator)
        self.assertEqual(operator_payload["detail"], "operator")
        self.assertIn("diagnostic_command", operator_payload["lanes"][0])
        self.assertIn("python -m aippocampus_runtime", operator.stdout)

    def test_questions_list_rows_are_actionable_cards(self) -> None:
        def question_row(
            fingerprint: str,
            title: str,
            created_at: str,
            *,
            source_refs: list[dict[str, object]] | None = None,
            extra: dict[str, object] | None = None,
        ) -> dict[str, object]:
            row: dict[str, object] = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_job_finding",
                "created_at": created_at,
                "job": "question_extraction",
                "finding_kind": "question_candidate",
                "fingerprint": fingerprint,
                "title": title,
                "summary": f"The user asked about {title}.",
                "confidence": 0.9,
                "source_refs": source_refs
                if source_refs is not None
                else [
                    {
                        "thread_key": f"thread:{fingerprint}",
                        "message_id": f"msg_{fingerprint}",
                        "source_line": 10,
                        "timestamp": created_at,
                    }
                ],
                "question_text": f"How should we handle {title}?",
                "question_short": title,
            }
            row.update(extra or {})
            return row

        with tempfile.TemporaryDirectory() as tmp:
            jobs = Path(tmp) / "subconscious_jobs.jsonl"
            synthetic_registry = Path(tmp) / "synthetic-registry.json"
            fresh_timestamp = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            rows = [
                question_row("open", "open route", fresh_timestamp),
                question_row("dormant", "dormant route", "2000-01-01T00:00:00Z"),
                question_row(
                    "resolved",
                    "resolved route",
                    "2026-06-14T00:00:00Z",
                    extra={
                        "lifecycle_state": "resolved",
                        "resolved_at": "2026-06-15T00:00:00Z",
                        "resolution_source_refs": [
                            {
                                "thread_key": "thread:resolution",
                                "message_id": "msg_resolution",
                                "source_line": 20,
                                "timestamp": "2026-06-15T00:00:00Z",
                            }
                        ],
                    },
                ),
                question_row(
                    "missing",
                    "missing source route",
                    fresh_timestamp,
                    source_refs=[],
                ),
            ]
            jobs.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            human = self.run_cli(
                "questions",
                "list",
                "--jobs",
                str(jobs),
                "--registry",
                str(synthetic_registry),
                "--dormant-after-days",
                "1",
                "--max",
                "10",
            )
            json_proc = self.run_cli(
                "questions",
                "list",
                "--jobs",
                str(jobs),
                "--registry",
                str(synthetic_registry),
                "--dormant-after-days",
                "1",
                "--max",
                "10",
                "--json",
            )

        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("open [reopenable_route]: open route", human.stdout)
        self.assertIn("dormant [reopenable_route]: dormant route", human.stdout)
        self.assertIn("resolved [bounded_evidence]: resolved route", human.stdout)
        self.assertIn("blocked [ignore_or_blocked]: 1 question rows need source-ref repair", human.stdout)
        self.assertNotIn(str(jobs), human.stdout)

        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        payload = parse_cli_json(self, json_proc)
        by_title = {row["title"]: row for row in payload["rows"]}
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(by_title["open route"]["action_grammar"], "reopenable_route")
        self.assertEqual(by_title["open route"]["route_state"], "ready_to_reopen")
        open_action = by_title["open route"]["foreground_action"]
        self.assertIsInstance(open_action, dict)
        self.assertEqual(open_action["id"], "reopen_question_source")
        self.assertIn("aippocampus search", open_action["command"])
        self.assertEqual(open_action["mutation_risk"], "read_only")
        self.assertEqual(
            open_action["claim_boundary"],
            "question_rows_are_navigation_only_reopen_source_before_claims",
        )
        for key in ("label", "why"):
            self.assertIn(key, open_action)
        self.assertEqual(by_title["dormant route"]["route_state"], "dormant_recheck_before_reviving")
        self.assertEqual(by_title["resolved route"]["action_grammar"], "bounded_evidence")
        self.assertIsInstance(by_title["resolved route"]["foreground_action"], dict)
        self.assertEqual(
            by_title["resolved route"]["route_state"],
            "resolved_recheck_before_use",
        )
        blocked = by_title["1 question rows need source-ref repair"]
        self.assertEqual(blocked["action_grammar"], "ignore_or_blocked")
        self.assertEqual(blocked["route_state"], "blocked_missing_source_refs")
        self.assertIsInstance(blocked["foreground_action"], dict)
        self.assertEqual(blocked["foreground_action"]["id"], "repair_question_source_refs")
        self.assertIsNone(blocked["source_route"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn(str(jobs), json_proc.stdout)

    def test_continuity_domain_preview_alias_is_foreground_safe(self) -> None:
        proc = self.run_cli("continuity-domain", "preview", "--max-threads", "1", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = parse_cli_json(self, proc)
        self.assertEqual(payload["detail"], "agent_preview")
        self.assertEqual(payload["mode"], "dry_run")
        self.assertTrue(payload["preview_boundary"]["preview_is_not_source_truth"])
        self.assertFalse(payload["preview_boundary"]["raw_source_refs_emitted"])

    def test_continuity_domain_top_help_points_to_ordinary_recall_path(self) -> None:
        proc = self.run_cli("continuity-domain", "--help")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage: aippocampus continuity-domain", proc.stdout)
        self.assertIn("Ordinary path", proc.stdout)
        self.assertIn("aippocampus agent recall", proc.stdout)
        self.assertIn("manual append", proc.stdout)
        self.assertIn("operator/debug", proc.stdout)

    def test_bare_storage_import_and_doctor_are_recovery_cards(self) -> None:
        storage = self.run_cli("storage")
        import_card = self.run_cli("import")
        import_json = self.run_cli("import", "--json")
        doctor = self.run_cli("doctor")

        self.assertEqual(storage.returncode, 0, storage.stderr)
        self.assertIn("AIppocampus storage", storage.stdout)
        self.assertIn("choose an explicit storage action", storage.stdout)
        self.assertNotIn("Candidates:", storage.stdout)
        self.assertEqual(import_card.returncode, 0, import_card.stderr)
        self.assertIn("AIppocampus import", import_card.stdout)
        self.assertIn("import conversation", import_card.stdout)
        self.assertEqual(import_json.returncode, 0, import_json.stderr)
        payload = parse_cli_json(self, import_json)
        self.assertEqual(payload["kind"], "aippocampus_import_recovery")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "choose_action")
        self.assertEqual(payload["surface_class"], "foreground_chooser_card")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertFalse(payload["write_boundary"]["written"])
        self.assertTrue(payload["write_boundary"]["explicit_write_required"])
        self.assertTrue(payload["safety"]["no_write_happened"])
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["id"], "preview_conversation_import")
        self.assertEqual(payload["foreground_action"]["requires"], ["input_path"])
        self.assertNotIn(
            "import_private_bundle",
            {action["id"] for action in payload["safe_next_actions"]},
        )
        self.assertIn(
            "import_private_bundle",
            {action["id"] for action in payload["write_actions"]},
        )
        self.assertIsInstance(payload["choices"], list)
        choices = {action["id"]: action for action in payload["choices"]}
        self.assertIn("import_private_bundle", choices)
        self.assertTrue(choices["import_private_bundle"]["template_only"])
        self.assertIn("preview_conversation_import", choices)
        conversation_choice = choices["preview_conversation_import"]
        self.assertIn("--dry-run --json", conversation_choice["command_template"])
        self.assertEqual(conversation_choice["requires"], ["input_path"])
        self.assertEqual(executable_command_violations(payload), [])
        self.assertFalse(payload["privacy_boundary"]["raw_local_paths_emitted"])
        self.assertIn(doctor.returncode, {0, 2}, doctor.stderr)
        self.assertIn("AIppocampus doctor", doctor.stdout)
        self.assertIn("preflight", doctor.stdout)

    def test_import_conversation_missing_input_is_structured_and_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "private-missing-input.jsonl"
            proc = self.run_cli(
                "import",
                "conversation",
                "--format",
                "generic-jsonl",
                "--input",
                str(missing),
                "--json",
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2)
        payload = parse_cli_json(self, proc)
        self.assertEqual(payload["error"]["code"], "input_not_found")
        self.assertEqual(payload["error"]["class"], "missing_prerequisite")
        self.assertTrue(payload["error"]["path_redacted"])
        self.assertIn("import conversation --help", payload["error"]["next_action"])
        self.assertNotIn("Traceback", raw)
        self.assertNotIn(str(missing), raw)

    def test_import_conversation_missing_args_returns_recovery_card(self) -> None:
        proc = self.run_cli("import", "conversation", "--json")

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = parse_cli_json(self, proc)
        self.assertEqual(payload["kind"], "aippocampus_import_conversation_recovery")
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["error"]["code"], "usage_error")
        self.assertEqual(
            payload["error"]["missing"],
            ["--input/--source", "--provider/--format"],
        )
        self.assertEqual(payload["missing"], ["input_path", "format_or_provider"])
        self.assertFalse(payload["error"]["written"])
        self.assertNotIn("<path>", payload["error"]["next_action"])
        self.assertNotIn("recovery_actions", payload)
        actions = [payload["foreground_action"], *payload["safe_next_actions"]]
        commands = [
            item.get("command", "")
            for item in actions
            if item.get("command")
        ]
        templates = [
            item.get("command_template", "")
            for item in actions
            if item.get("command_template")
        ]
        self.assertIn("aippocampus import --json", commands)
        self.assertTrue(any("--dry-run --json" in item for item in templates))
        self.assertTrue(all("<path>" not in item for item in commands))

    def test_import_conversation_missing_args_distinguishes_input_and_format(self) -> None:
        missing_input = self.run_cli("import", "conversation", "--format", "generic-jsonl", "--json")
        missing_format = self.run_cli(
            "import",
            "conversation",
            "--input",
            "conversation.jsonl",
            "--json",
        )

        self.assertEqual(missing_input.returncode, 2)
        self.assertEqual(missing_format.returncode, 2)
        input_payload = parse_cli_json(self, missing_input)
        format_payload = parse_cli_json(self, missing_format)

        self.assertEqual(input_payload["missing"], ["input_path"])
        self.assertEqual(format_payload["missing"], ["format_or_provider"])
        for payload in (input_payload, format_payload):
            actions = [payload["foreground_action"], *payload["safe_next_actions"]]
            commands = [
                item.get("command", "")
                for item in actions
                if item.get("command")
            ]
            templates = [
                item.get("command_template", "")
                for item in actions
                if item.get("command_template")
            ]
            self.assertIn("aippocampus import --json", commands)
            self.assertTrue(any("{input_path}" in item for item in templates))
            self.assertTrue(all("<path>" not in item for item in commands))

    def test_import_conversation_help_is_preview_first(self) -> None:
        proc = self.run_cli("import", "conversation", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Preview an explicit conversation transcript", proc.stdout)
        self.assertIn("Start with --dry-run --json", proc.stdout)
        self.assertIn("no registry write happens", proc.stdout)
        self.assertIn("Safe first step:", proc.stdout)
        self.assertIn(
            "--format generic-jsonl --input ./conversation.jsonl --dry-run --json",
            proc.stdout,
        )
        self.assertIn("The input file stays local operator material", proc.stdout)
        self.assertIn("local paths are redacted by default", proc.stdout)

    def test_import_conversation_missing_file_human_output_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "private-missing-input.jsonl"
            proc = self.run_cli(
                "import",
                "conversation",
                "--format",
                "generic-jsonl",
                "--input",
                str(missing),
                "--dry-run",
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2)
        self.assertIn("AIppocampus import conversation", raw)
        self.assertIn("next:", raw)
        self.assertIn("written: false", raw)
        self.assertIn("local input paths are redacted", raw)
        self.assertNotIn("usage:", raw)
        self.assertNotIn(str(missing), raw)

    def test_import_generic_jsonl_recovers_to_transcript_import(self) -> None:
        for format_guess in ("generic-jsonl", "jsonl"):
            with self.subTest(format_guess=format_guess):
                proc = self.run_cli("import", format_guess)

                self.assertEqual(proc.returncode, 2)
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)
                payload = parse_cli_json(self, proc)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"]["code"], "transcript_import_intent_detected")
                self.assertTrue(payload["safety"]["no_write_happened"])
                self.assertIn(
                    'aippocampus import conversation --format generic-jsonl --input "{input_path}" --dry-run --json',
                    payload["error"]["next_command"],
                )
                self.assertIn("private", payload["privacy_boundary"]["operator_input"])

    def test_update_natural_guesses_recover_to_plan_first_cards(self) -> None:
        cases = [
            ((), "update_command_required", "aippocampus update status --json"),
            (("check",), "update_status_alias", "aippocampus update status --json"),
            (("dry-run",), "update_plan_alias", "aippocampus update plan --json"),
        ]
        for argv, code, command in cases:
            with self.subTest(argv=argv):
                proc = self.run_cli("update", *argv)

                self.assertEqual(proc.returncode, 2)
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)
                self.assertEqual(proc.stdout, "")
                self.assertIn("no write happened", proc.stderr.casefold())
                self.assertIn(code, proc.stderr)
                self.assertIn(command, proc.stderr)

    def test_update_missing_subcommand_recovery_is_stderr_diagnostic(self) -> None:
        proc = self.run_cli("update")

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("AIppocampus update recovery card", proc.stderr)
        self.assertIn("Try: aippocampus update status --json", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_agent_recall_plain_missing_cue_is_stderr_without_traceback(self) -> None:
        proc = self.run_cli("agent", "recall")

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("AIppocampus agent recall: cue required", proc.stderr)
        self.assertIn("Try:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_agent_recall_bad_registry_returns_error_card_not_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry"
            registry.mkdir()
            (registry / "threads.json").write_text("{bad json", encoding="utf-8")
            proc = self.run_cli(
                "agent",
                "recall",
                "old cue",
                "--registry-dir",
                str(registry),
                "--json",
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", raw)
        self.assertNotIn(str(registry), raw)
        payload = parse_cli_json(self, proc)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_json")
        self.assertEqual(payload["error"]["class"], "validation_error")
        self.assertIn("safe_next_actions", payload)

    def test_facade_unhandled_json_exception_returns_recovery_card(self) -> None:
        module_name = "aippocampus_runtime._test_unhandled_cli_error"
        fake_module = types.ModuleType(module_name)

        def main(argv: list[str]) -> int:
            self.assertIn("--json", argv)
            raise OSError(r"cannot open C:\private\registry\threads.json")

        fake_module.main = main
        sys.modules[module_name] = fake_module
        stdout = StringIO()
        stderr = StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = facade.run_module_main(
                    module_name,
                    "agent_continuity.py",
                    ["recall", "old cue", "--json"],
                )
        finally:
            sys.modules.pop(module_name, None)

        raw = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("Traceback", raw)
        self.assertNotIn(r"C:\private\registry", raw)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_cli_recovery_error")
        self.assertIn("safe_next_actions", payload)
        self.assertEqual(payload["foreground_action"]["command_template"], 'aippocampus agent recall "{cue}" --json')

    def test_search_all_registry_failure_recovers_to_registry_audit_not_generic_help(self) -> None:
        module_name = "aippocampus_runtime._test_search_registry_error"
        fake_module = types.ModuleType(module_name)

        def main(argv: list[str]) -> int:
            self.assertIn("--all", argv)
            raise PermissionError(r"denied C:\private\aippocampus\threads.json")

        fake_module.main = main
        sys.modules[module_name] = fake_module
        stdout = StringIO()
        stderr = StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = facade.run_module_main(
                    module_name,
                    "search_clean_source.py",
                    ["--all", "distinctive cue", "--json"],
                )
        finally:
            sys.modules.pop(module_name, None)

        raw = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("Traceback", raw)
        self.assertNotIn(r"C:\private\aippocampus", raw)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "source_search_blocked")
        self.assertEqual(payload["blocker"], "registered source index could not be read; registry-wide search did not run")
        self.assertEqual(payload["foreground_action"]["id"], "audit_registry_sources")
        self.assertEqual(payload["foreground_action"]["command"], "aippocampus registry audit --json")
        self.assertNotEqual(payload["foreground_action"]["id"], "inspect_cli_help")
        self.assertEqual(payload["safe_next_actions"][0]["id"], "fallback_current_thread_search")
        self.assertTrue(payload["recovery_boundary"]["search_error_is_not_absence_of_memory"])

    def test_delegated_invalid_actions_with_json_return_recovery_cards(self) -> None:
        cases = [
            ("agent", "bad", "--json"),
            ("sync", "bad", "--json"),
            ("object-sync", "bad", "--json"),
            ("mcp", "bad", "--json"),
            ("doctor", "bad", "--json"),
            ("learning", "bad", "--json"),
            ("questions", "bad", "--json"),
            ("warm", "bad", "--json"),
            ("logs", "bad", "--json"),
            ("maintenance", "bad", "--json"),
            ("storage", "bad", "--json"),
            ("hooks", "bad", "--json"),
            ("hooks", "prompt", "bad", "--json"),
        ]

        for args in cases:
            with self.subTest(args=args):
                proc = self.run_cli(*args)
                raw = proc.stdout + proc.stderr
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stderr, "")
                self.assertNotIn("usage:", raw)
                self.assertNotIn("facade.py", raw)
                payload = parse_cli_json(self, proc)
                self.assertIn("error", payload)
                self.assertTrue(payload.get("foreground_action") or payload.get("safe_next_actions"))
                self.assertNotIn("agent_next_action", payload)

    def test_delegated_invalid_plain_action_is_friendly_not_argparse_wall(self) -> None:
        proc = self.run_cli("agent", "bad")

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("Error:", proc.stderr)
        self.assertIn("Try:", proc.stderr)
        assert_semantic_human_output(self, proc.stderr, max_lines=6)
        self.assertNotIn("usage:", proc.stderr)
        self.assertNotIn("facade.py", proc.stderr)

    def test_why_cli_module_uses_real_argv_for_json(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.recall.why_cli",
                "old setup",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = parse_cli_json(self, proc)
        self.assertNotEqual((payload.get("error") or {}).get("code"), "cue_required")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIn("foreground_action", payload)
        self.assertNotIn("agent_next_action", payload)

    def test_facade_unhandled_plain_exception_is_stderr_try_hint(self) -> None:
        module_name = "aippocampus_runtime._test_unhandled_storage_error"
        fake_module = types.ModuleType(module_name)

        def main(argv: list[str]) -> int:
            self.assertIn("--dry-run", argv)
            raise PermissionError(r"denied C:\private\aippocampus\capacity.json")

        fake_module.main = main
        sys.modules[module_name] = fake_module
        stdout = StringIO()
        stderr = StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = facade.run_module_main(
                    module_name,
                    "storage_governance.py",
                    ["gc", "--dry-run"],
                )
        finally:
            sys.modules.pop(module_name, None)

        raw = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Try: aippocampus storage gc --dry-run --summary-json --cwd .", stderr.getvalue())
        self.assertNotIn("Traceback", raw)
        self.assertNotIn(r"C:\private\aippocampus", raw)

    def test_agent_macro_bad_jsonl_skips_bad_row_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            macro_state = Path(tmp) / "macro_state.jsonl"
            macro_state.write_text("{bad json\n", encoding="utf-8")
            proc = self.run_cli(
                "agent",
                "macro",
                "--macro-state-jsonl",
                str(macro_state),
                "--json",
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("Traceback", raw)
        self.assertNotIn(str(macro_state), raw)
        payload = parse_cli_json(self, proc)
        self.assertIn(payload["status"], {"missing", "missing_macro_state", "no_macro_projection"})
        self.assertIn("warnings", payload)
        self.assertEqual(payload["warnings"][0]["code"], "invalid_jsonl_row_skipped")

    def test_agent_recall_human_fallback_uses_real_command_not_continue_normally(self) -> None:
        text = render_recall_human(
            {
                "status": "ok",
                "memory_packets": [],
                "deepen_requests": [],
                "suggested_next": "continue_normally",
            }
        )

        self.assertIn('Next: aippocampus agent recall "old decision or handoff cue" --json', text)
        self.assertNotIn("continue_normally", text)

    def test_sync_plain_issues_redact_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sync_dir = Path(tmp) / "sync"
            sync_dir.mkdir()
            (sync_dir / "aippocampus-sync-manifest.json").write_text("{bad json", encoding="utf-8")
            proc = self.run_cli("sync", "status", "--sync-dir", str(sync_dir))

        raw = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertNotIn(str(sync_dir), raw)
        self.assertIn("<local-path-redacted>", raw)
        self.assertIn('Try: aippocampus sync repair --plan --sync-dir "{sync_dir}" --json', proc.stderr)

    def test_update_apply_without_surface_returns_no_write_recovery_json(self) -> None:
        human = self.run_cli("update", "apply")
        agent = self.run_cli("update", "apply", "--agent-json")

        self.assertEqual(human.returncode, 2)
        self.assertIn("No write happened", human.stdout)
        self.assertIn("valid surfaces", human.stdout)
        self.assertIn("aippocampus update plan --json", human.stdout)
        self.assertNotIn("update_failed", human.stdout + human.stderr)

        self.assertEqual(agent.returncode, 2)
        payload = parse_cli_json(self, agent)
        self.assertEqual(payload["error"]["code"], "update_apply_surface_required")
        self.assertTrue(payload["safety"]["no_write_happened"])
        self.assertIn("skill", payload["valid_surfaces"])
        self.assertNotIn("next_actions", payload)
        self.assertIn(
            "aippocampus update plan --json",
            {action["command"] for action in payload["safe_next_actions"]},
        )

    def test_object_sync_json_missing_config_returns_backend_chooser(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AIPPOCAMPUS_OBJECT_")
        }
        proc = self.run_cli_with_env("object-sync", "status", "--json", env=env)

        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("Traceback", proc.stderr + proc.stdout)
        payload = parse_cli_json(self, proc)
        self.assertEqual(payload["kind"], "aippocampus_object_sync_backend_chooser")
        self.assertEqual(payload["status"], "needs_object_backend_before_plan")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertTrue(payload["foreground_action"]["template_only"])
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(
            payload["privacy_boundary"]["writes_performed"],
            False,
        )

    def test_object_sync_help_is_action_first_and_command_specific(self) -> None:
        top = self.run_cli("object-sync", "--help")
        push = self.run_cli("object-sync", "push", "--help")
        pull = self.run_cli("object-sync", "pull", "--help")
        repair = self.run_cli("object-sync", "repair", "--help")

        self.assertEqual(top.returncode, 0, top.stderr)
        self.assertLess(top.stdout.index("Action card:"), top.stdout.index("--object-store-url"))
        self.assertIn("push --plan", top.stdout)
        self.assertIn("operator object-store configuration", top.stdout)
        self.assertIn("raw and encryption options", top.stdout)
        self.assertIn("requires an encrypted sync decision", top.stdout)

        for proc, command, read_side, write_side in (
            (push, "push", "local_registry", "object_store_prefix"),
            (pull, "pull", "object_store_prefix", "local_registry"),
            (repair, "repair", "object_store_prefix", "object_store_manifest"),
        ):
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(f"Read side: {read_side}.", proc.stdout)
            self.assertIn(f"Write side: {write_side}.", proc.stdout)
            self.assertIn(f"aippocampus object-sync {command} --plan --json", proc.stdout)
            self.assertIn(f"aippocampus object-sync {command} --json may mutate", proc.stdout)
            self.assertNotIn("Status is always non-mutating", proc.stdout)

    def test_local_sync_help_is_action_first_and_command_specific(self) -> None:
        top = self.run_cli("sync", "--help")
        push = self.run_cli("sync", "push", "--help")
        pull = self.run_cli("sync", "pull", "--help")
        repair = self.run_cli("sync", "repair", "--help")

        self.assertEqual(top.returncode, 0, top.stderr)
        self.assertLess(top.stdout.index("Action card:"), top.stdout.index("--sync-dir"))
        self.assertIn("push --plan", top.stdout)
        self.assertIn("raw and encryption options", top.stdout)
        self.assertIn("requires an encrypted sync decision", top.stdout)

        for proc, command, read_side, write_side in (
            (push, "push", "local_registry", "sync_dir"),
            (pull, "pull", "sync_dir", "local_registry"),
            (repair, "repair", "sync_dir", "sync_dir_manifest"),
        ):
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(f"Read side: {read_side}.", proc.stdout)
            self.assertIn(f"Write side: {write_side}.", proc.stdout)
            self.assertIn(f"aippocampus sync {command} --sync-dir <folder> --plan --json", proc.stdout)
            self.assertIn(f"aippocampus sync {command} --sync-dir <folder> --json may mutate", proc.stdout)
            self.assertNotIn("Status is always non-mutating", proc.stdout)

    def test_bare_parent_plain_commands_render_chooser_cards(self) -> None:
        cases = {
            "agent": "aippocampus agent recall",
            "logs": "aippocampus logs status --json",
            "warm": "aippocampus warm status --json",
        }

        for command, try_command in cases.items():
            with self.subTest(command=command):
                proc = self.run_cli(command)

                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("AIppocampus", proc.stdout)
                self.assertIn("decision:", proc.stdout)
                self.assertIn("Try:", proc.stdout)
                self.assertIn(try_command, proc.stdout)
                self.assertNotIn("usage:", proc.stdout.lower())
                self.assertNotIn("Traceback", proc.stdout + proc.stderr)

    def test_compact_foreground_cards_detail_gate_operator_diagnostics(self) -> None:
        deepen = self.run_cli("agent", "deepen", "--json")
        provider = self.run_cli("doctor", "provider", "--json")
        aippo = self.run_cli("agent", "aippo", "--json")

        self.assertNotEqual(deepen.returncode, 0)
        deepen_payload = parse_cli_json(self, deepen)
        self.assertEqual(deepen_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("cannot_claim", deepen_payload)
        self.assertNotIn("policy_boundary", deepen_payload)
        self.assertNotIn("result", deepen_payload)
        self.assertNotIn("boundary_detail", deepen_payload)
        self.assertNotIn("operator_detail", deepen_payload)
        assert_compact_frontstage_payload(self, deepen_payload, max_top_level_diagnostics=1)

        self.assertEqual(provider.returncode, 0, provider.stderr)
        provider_payload = parse_cli_json(self, provider)
        self.assertEqual(provider_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("cannot_claim", provider_payload)
        self.assertNotIn("boundary_detail", provider_payload)
        self.assertNotIn("boundary_summary", provider_payload)
        self.assertTrue(provider_payload["details_available"])
        self.assertEqual(
            provider_payload["safe_next_actions"][-1]["id"],
            "inspect_provider_doctor_detail",
        )

        self.assertEqual(aippo.returncode, 2, aippo.stderr)
        aippo_payload = parse_cli_json(self, aippo)
        self.assertEqual(aippo_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(aippo_payload["status"], "needs_input")
        self.assertNotIn("contract_status", aippo_payload)
        self.assertNotIn("match_diagnostics", aippo_payload)
        self.assertNotIn("contract_action", aippo_payload)
        self.assertNotIn("operator_detail", aippo_payload)
        assert_compact_detail_affordances(self, aippo_payload, surface="cli.agent_aippo.needs_input")

    def test_bare_parent_json_commands_return_recovery_or_chooser_cards(self) -> None:
        cases = {
            ("search", "--json"): "aippocampus_search_recovery",
            ("plugin", "--json"): "aippocampus_plugin_chooser",
            ("hooks", "--json"): "aippocampus_hooks_readiness",
            ("sync", "--json"): "aippocampus_sync_chooser",
            ("object-sync", "--json"): "aippocampus_object_sync_chooser",
            ("storage", "--json"): "aippocampus_storage_chooser",
            ("storage", "gc", "--json"): "aippocampus_storage_gc_recovery",
            ("doctor", "--json"): "aippocampus_doctor_preflight",
            ("smoke", "--json"): "aippocampus_smoke_chooser",
            ("logs", "--json"): "aippocampus_logs_chooser",
            ("continuity-domain", "--json"): "aippocampus_continuity_domain_recovery",
            ("work-guard", "--json"): "aippocampus_issue_work_orientation_packet",
            ("telepathy", "--json"): "aippocampus_telepathy_handoff_error",
        }

        for args, kind in cases.items():
            with self.subTest(args=args):
                proc = self.run_cli(*args)
                self.assertNotIn("usage:", proc.stdout + proc.stderr)
                payload = parse_cli_json(self, proc)
                self.assertEqual(payload["kind"], kind)
                self.assertIn("foreground-action-v2", payload["foreground_action_contract"])
                self.assertIsInstance(payload["foreground_action"], dict)
                self.assertNotIn("agent_next_action", payload)
                self.assertIn("safe_next_actions", payload)
                self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
                if args == ("plugin", "--json"):
                    self.assertEqual(payload["foreground_action"]["id"], "check_codex_plugin_status")
                    self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
                actions = [
                    payload.get("foreground_action"),
                    *(payload.get("safe_next_actions") or []),
                    *(payload.get("choices") or []),
                ]
                actions = [action for action in actions if isinstance(action, dict)]
                if args == ("smoke", "--json"):
                    encoded = json.dumps(payload, ensure_ascii=False)
                    self.assertNotIn("old decision or handoff cue", encoded)
                    recall_funnel = next(
                        action for action in actions if action.get("id") == "recall_funnel"
                    )
                    self.assertNotIn("command", recall_funnel)
                    self.assertIn("command_template", recall_funnel)
                for action in actions:
                    if isinstance(action, dict) and "command" in action:
                        command = str(action["command"])
                        if command.startswith("python -m pip install -e"):
                            self.assertEqual(args, ("doctor", "--json"))
                            continue
                        self.assertIn("aippocampus ", command)
                        resolved = facade.resolve_command(command.split()[1:])
                        self.assertIsNotNone(resolved.script_name)

    def test_continuity_domain_json_does_not_put_placeholders_in_executable_commands(self) -> None:
        proc = self.run_cli("continuity-domain", "--json")

        self.assertIn(proc.returncode, {0, 2}, proc.stderr)
        payload = parse_cli_json(self, proc)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("<local-path-redacted>", encoded)
        for action in payload.get("safe_next_actions") or []:
            if isinstance(action, dict):
                command = str(action.get("command") or "")
                self.assertNotIn("<", command)
                self.assertNotIn("old continuity cue", command)
                if action.get("command_template"):
                    self.assertEqual(action.get("requires"), ["cue"])

    def test_work_guard_json_uses_templates_for_missing_issue_context(self) -> None:
        proc = self.run_cli("work-guard", "--json")

        self.assertEqual(proc.returncode, 2)
        payload = parse_cli_json(self, proc)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_issue_work_orientation_packet")
        self.assertEqual(payload["error"]["code"], "work_guard_issue_or_title_required")
        self.assertEqual(executable_command_violations(payload), [])
        self.assertNotIn("<issue-number>", encoded)
        self.assertNotIn("issue title and key terms", encoded)
        for action in payload["safe_next_actions"]:
            self.assertIn("command_template", action)
            self.assertNotIn("command", action)
            self.assertIsInstance(action["requires"], list)

    def test_bare_onboard_json_is_status_first_and_read_only(self) -> None:
        proc = self.run_cli("onboard", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = parse_cli_json(self, proc)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_onboard_status_card")
        self.assertTrue(payload["read_only"])
        self.assertIn("primary_next_action", payload)
        self.assertIn("provider_summary", payload)
        self.assertNotIn("data", payload)
        self.assertNotIn("stats_after", json.dumps(payload, ensure_ascii=False))
        self.assertTrue(
            "command" in payload["primary_next_action"]
            or "command_template" in payload["primary_next_action"]
        )
        self.assertEqual(executable_command_violations(payload), [])

    def test_agent_macro_positional_cue_returns_recall_recovery_card(self) -> None:
        proc = self.run_cli("agent", "macro", "old cue", "--json")

        self.assertEqual(proc.returncode, 2)
        payload = parse_cli_json(self, proc)
        self.assertEqual(payload["error"]["code"], "macro_positional_cue_not_supported")
        self.assertEqual(
            shlex.split(payload["foreground_action"]["command"]),
            ["aippocampus", "agent", "recall", "old cue", "--json"],
        )
        self.assertLessEqual(len(payload.get("safe_next_actions") or []), 1)
        self.assertNotIn("macro --explain-schema", json.dumps(payload, ensure_ascii=False))
        assert_compact_frontstage_payload(self, payload, max_safe_actions=1)

    def test_sync_plan_outputs_direction_cards_without_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry"
            sync_dir = root / "sync"
            registry.mkdir()
            (registry / "threads.json").write_text(
                json.dumps({"threads": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            local = self.run_cli(
                "sync",
                "push",
                "--sync-dir",
                str(sync_dir),
                "--registry-dir",
                str(registry),
                "--plan",
                "--json",
            )
            object_plan = self.run_cli(
                "object-sync",
                "pull",
                "--object-store-url",
                "https://example.invalid/private-prefix",
                "--object-prefix",
                "private/user",
                "--plan",
                "--json",
            )
            help_proc = self.run_cli("sync", "push", "--help")

        raw = local.stdout + object_plan.stdout + help_proc.stdout
        self.assertEqual(local.returncode, 0, local.stderr)
        self.assertEqual(object_plan.returncode, 0, object_plan.stderr)
        local_payload = parse_cli_json(self, local)
        object_payload = parse_cli_json(self, object_plan)
        self.assertEqual(local_payload["kind"], "aippocampus_sync_direction_plan")
        self.assertEqual(local_payload["source_side"], "local_registry")
        self.assertEqual(local_payload["destination_side"], "sync_dir")
        self.assertEqual(local_payload["mutates"], ["sync_dir"])
        self.assertEqual(
            [item["category"] for item in local_payload["estimated_file_breakdown"]],
            [
                "registry_metadata_and_indexes",
                "clean_source_files",
                "raw_rollout_audit_files",
            ],
        )
        self.assertEqual(
            local_payload["raw_rollout_boundary"],
            "excluded_unless_include_raw_and_encrypted_sync_are_explicitly_requested",
        )
        self.assertIn("plan mode performs no writes", local_payload["conflict_boundary"])
        self.assertEqual(object_payload["kind"], "aippocampus_object_sync_direction_plan")
        self.assertEqual(object_payload["source_side"], "object_store_prefix")
        self.assertEqual(object_payload["destination_side"], "local_registry")
        self.assertEqual(object_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", object_payload)
        self.assertNotIn(object_payload["foreground_action"], object_payload["safe_next_actions"])
        self.assertNotIn("next_command", object_payload)
        self.assertIn("{object_store_url}", object_payload["next_command_template"])
        self.assertEqual(object_payload["requires"], ["object_store_url"])
        self.assertIn("Action card:", help_proc.stdout)
        self.assertNotIn(str(root), raw)
        self.assertNotIn("private/user", raw)
