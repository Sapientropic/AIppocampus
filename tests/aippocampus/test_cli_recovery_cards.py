from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


class AippocampusCliRecoveryCardTests(unittest.TestCase):
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

    def test_status_help_is_decision_card_not_health_flag_wall(self) -> None:
        proc = self.run_cli("status", "--help")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Status decision card", proc.stdout)
        self.assertIn("aippocampus update status --agent-json", proc.stdout)
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

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
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
        self.assertIn("aippocampus plugin status --agent-json", family.stdout)

        self.assertEqual(install.returncode, 0)
        self.assertIn("Ordinary Codex setup path", install.stdout)
        self.assertIn("aippocampus plugin install --codex --verify", install.stdout)
        self.assertIn("aippocampus update status --agent-json", install.stdout)
        self.assertIn("aippocampus agent recall", install.stdout)
        self.assertLess(
            install.stdout.index("aippocampus plugin install --codex --verify"),
            install.stdout.index("--repo-root"),
        )

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
        self.assertIn("Do not use self-notes for factual claims", self_note.stdout)
        self.assertLess(self_note.stdout.index("Weak-memory"), self_note.stdout.index("--notes-path"))

    def test_warm_help_leads_with_safe_status_path(self) -> None:
        proc = self.run_cli("warm", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Warm ambient recall is optional", proc.stdout)
        self.assertIn("aippocampus warm status", proc.stdout)
        self.assertIn("does not make model calls", proc.stdout)
        self.assertIn("ordinary source-backed", proc.stdout.casefold())
        self.assertLess(proc.stdout.index("aippocampus warm status"), proc.stdout.index("--prompt"))

    def test_doctor_config_human_output_is_decision_grade(self) -> None:
        proc = self.run_cli("doctor", "config")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Configured env vars:", proc.stdout)
        self.assertIn("Sensitive env vars present:", proc.stdout)
        self.assertIn("Cannot claim:", proc.stdout)
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

    def test_questions_and_navigation_frontdoors_are_bounded_read_paths(self) -> None:
        questions = self.run_cli("questions", "status", "--json")
        navigate = self.run_cli("navigate", "--json")

        self.assertEqual(questions.returncode, 0, questions.stderr)
        question_payload = json.loads(questions.stdout)
        self.assertEqual(question_payload["kind"], "aippocampus_question_tracking_status")
        self.assertFalse(question_payload["source_boundary"]["model_job_started"])
        self.assertTrue(
            question_payload["source_boundary"]["source_reopen_required_before_claim"]
        )
        self.assertNotIn("jobs", question_payload["summary"])
        self.assertNotIn("registry", question_payload["summary"])
        self.assertFalse(question_payload["privacy_boundary"]["local_paths_serialized"])

        self.assertEqual(navigate.returncode, 0, navigate.stderr)
        navigation_payload = json.loads(navigate.stdout)
        self.assertEqual(navigation_payload["status"], "operator_only")
        self.assertFalse(navigation_payload["source_boundary"]["model_job_started"])
        self.assertIn(
            "aippocampus agent recall",
            navigation_payload["foreground_next_action"]["command"],
        )

    def test_continuity_domain_preview_alias_is_foreground_safe(self) -> None:
        proc = self.run_cli("continuity-domain", "preview", "--max-threads", "1", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
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
        doctor = self.run_cli("doctor")

        self.assertEqual(storage.returncode, 0, storage.stderr)
        self.assertIn("AIppocampus storage", storage.stdout)
        self.assertIn("choose an explicit storage action", storage.stdout)
        self.assertNotIn("Candidates:", storage.stdout)
        self.assertEqual(import_card.returncode, 0, import_card.stderr)
        self.assertIn("AIppocampus import", import_card.stdout)
        self.assertIn("import conversation", import_card.stdout)
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("AIppocampus doctor", doctor.stdout)
        self.assertIn("doctor provider", doctor.stdout)

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
        payload = json.loads(proc.stdout)
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
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["error"]["code"], "usage_error")
        self.assertEqual(
            payload["error"]["missing"],
            ["--input/--source", "--provider/--format"],
        )
        self.assertFalse(payload["error"]["written"])
        self.assertIn("--dry-run --json", payload["error"]["next_action"])

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

    def test_object_sync_json_missing_config_returns_structured_error(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AIPPOCAMPUS_OBJECT_")
        }
        proc = self.run_cli_with_env("object-sync", "status", "--json", env=env)

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr + proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["error"]["code"], "object_store_config_required")

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

    def test_bare_logs_command_is_read_only_status_card(self) -> None:
        proc = self.run_cli("logs")

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("logs:", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)

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
        local_payload = json.loads(local.stdout)
        object_payload = json.loads(object_plan.stdout)
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
        self.assertIn("Action card:", help_proc.stdout)
        self.assertNotIn(str(root), raw)
        self.assertNotIn("private/user", raw)
