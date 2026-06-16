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
        self.assertIn("aippocampus update status --agent-json", setup.stdout)
        self.assertIn("First-run install card", install.stdout)
        self.assertIn("aippocampus agent recall", install.stdout)
        self.assertIn("Memory action card", memory.stdout)
        self.assertIn("source-backed", memory.stdout)
        self.assertIn("aippocampus search", memory.stdout)
        self.assertIn("Privacy and control card", privacy.stdout)
        self.assertIn("pause", privacy.stdout)
        self.assertIn("provider-key", privacy.stdout)
        self.assertIn("Personal controls card", controls.stdout)
        self.assertIn("do-not-use-here", controls.stdout)

    def test_plugin_install_status_recovers_to_plugin_status(self) -> None:
        proc = self.run_cli("plugin", "install", "--status")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Plugin status readiness card", proc.stdout)
        self.assertIn("aippocampus plugin status --agent-json", proc.stdout)

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

    def test_navigate_default_hides_internal_module_commands(self) -> None:
        human = self.run_cli("navigate")
        compact = self.run_cli("navigate", "--json")
        operator = self.run_cli("navigate", "--operator-json")

        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn("operator details: aippocampus navigate --operator-json", human.stdout)
        self.assertNotIn("python -m aippocampus_runtime", human.stdout)

        self.assertEqual(compact.returncode, 0, compact.stderr)
        compact_payload = json.loads(compact.stdout)
        self.assertEqual(compact_payload["detail"], "compact")
        self.assertIn("operator_detail_command", compact_payload["lanes"][0])
        self.assertNotIn("diagnostic_command", json.dumps(compact_payload))

        self.assertEqual(operator.returncode, 0, operator.stderr)
        operator_payload = json.loads(operator.stdout)
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
            rows = [
                question_row("open", "open route", "2026-06-16T00:00:00Z"),
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
                    "2026-06-16T00:00:00Z",
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
        payload = json.loads(json_proc.stdout)
        by_title = {row["title"]: row for row in payload["rows"]}
        self.assertEqual(by_title["open route"]["action_grammar"], "reopenable_route")
        self.assertEqual(by_title["open route"]["route_state"], "ready_to_reopen")
        self.assertIn("aippocampus search", by_title["open route"]["agent_next_action"])
        self.assertEqual(by_title["dormant route"]["route_state"], "dormant_recheck_before_reviving")
        self.assertEqual(by_title["resolved route"]["action_grammar"], "bounded_evidence")
        self.assertEqual(
            by_title["resolved route"]["route_state"],
            "resolved_recheck_before_use",
        )
        blocked = by_title["1 question rows need source-ref repair"]
        self.assertEqual(blocked["action_grammar"], "ignore_or_blocked")
        self.assertEqual(blocked["route_state"], "blocked_missing_source_refs")
        self.assertIsNone(blocked["source_route"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn(str(jobs), json_proc.stdout)

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

    def test_import_conversation_help_is_preview_first(self) -> None:
        proc = self.run_cli("import", "conversation", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Preview an explicit conversation transcript", proc.stdout)
        self.assertIn("Start with --dry-run --json", proc.stdout)
        self.assertIn("no registry write happens", proc.stdout)
        self.assertIn("Safe first step:", proc.stdout)
        self.assertIn("--format generic-jsonl --input <path> --dry-run --json", proc.stdout)
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
