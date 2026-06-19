from __future__ import annotations

import json
import os
import re
import shlex
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.config.registry import (  # noqa: E402
    CONFIG_BY_NAME,
    CONFIG_STABILITY_BUCKETS,
    config_registry_names,
    config_report,
    config_summary_report,
)
from aippocampus_runtime.contracts import (  # noqa: E402
    PUBLIC_CONTRACT_SUBPACKAGES,
    PUBLIC_RUNTIME_ENVELOPE_FIELDS,
    PUBLIC_RUNTIME_STATUSES,
    PUBLIC_RUNTIME_SURFACE_CLASSES,
    RUNTIME_FAILURE_FAMILIES,
    canonical_foreground_action_fields,
    foreground_action_contract_violations,
    foreground_chooser_card,
    public_envelope,
    shell_quote,
)
from aippocampus_runtime.registry import store as registry_store  # noqa: E402

ENV_PATTERN = re.compile(r"\bAIPPOCAMPUS_[A-Z0-9_]+\b")


def aippocampus_env_names_from(paths: list[Path]) -> set[str]:
    names: set[str] = set()
    for path in paths:
        if path.is_dir():
            files = path.rglob("*.py")
        else:
            files = [path]
        for file in files:
            text = file.read_text(encoding="utf-8")
            names.update(name for name in ENV_PATTERN.findall(text) if not name.endswith("_"))
    return names


class RuntimeContractsAndConfigRegistryTests(unittest.TestCase):
    def test_thread_registry_rejects_future_schema_instead_of_silent_downgrade(self) -> None:
        path = REPO_ROOT / ".tmp" / "test-thread-registry-future-schema" / "threads.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"schema_version": 999, "threads": []}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                registry_store.RegistryReadError,
                "unsupported schema_version",
            ):
                registry_store.load_registry(path)
        finally:
            if path.parent.exists():
                import shutil

                shutil.rmtree(path.parent, ignore_errors=True)

    def test_public_envelope_uses_shared_status_and_failure_vocabulary(self) -> None:
        envelope = public_envelope(
            ok=True,
            status="partial",
            data={"kind": "fixture"},
            errors=[{"code": "provider_unavailable"}],
            cannot_claim=["source_not_open"],
        )

        self.assertEqual(tuple(envelope), PUBLIC_RUNTIME_ENVELOPE_FIELDS)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["status"], "partial")
        self.assertIn("provider_unavailable", RUNTIME_FAILURE_FAMILIES)
        self.assertIn("foreground_budget", RUNTIME_FAILURE_FAMILIES)
        self.assertIn("public_api", PUBLIC_RUNTIME_SURFACE_CLASSES)
        self.assertIn("mcp", PUBLIC_CONTRACT_SUBPACKAGES)
        self.assertIn("error", PUBLIC_RUNTIME_STATUSES)

    def test_public_envelope_unknown_status_fails_closed(self) -> None:
        envelope = public_envelope(ok=True, status="invented_status")

        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["status"], "error")

    def test_canonical_foreground_action_fields_keep_compat_aliases_identical(self) -> None:
        primary = {
            "id": "inspect_detail",
            "label": "Inspect provider detail",
            "command": "aippocampus doctor provider --detail full --json",
            "why": "Open local provider diagnostics without treating them as memory evidence.",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_detail_not_memory_evidence",
        }
        secondary = {
            "id": "check_hook_visibility",
            "label": "Check prompt hook visibility",
            "command": "aippocampus hooks prompt status --last --json",
            "why": "Check whether the launcher scope can see the prompt hook state.",
            "mutation_risk": "read_only",
            "claim_boundary": "launcher_scope_not_running_hook_process",
        }

        fields = canonical_foreground_action_fields(
            primary,
            safe_next_actions=[primary, secondary],
        )

        self.assertEqual(fields["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(fields["foreground_action"], primary)
        self.assertEqual(fields["agent_next_action"], primary)
        self.assertEqual(fields["safe_next_actions"][0], primary)
        self.assertEqual(foreground_action_contract_violations(fields), [])

    def test_shell_quote_keeps_recall_cues_single_argument(self) -> None:
        cue = 'a";$(echo PWNED); #'
        command = f"aippocampus agent recall {shell_quote(cue)} --json"

        self.assertEqual(
            shlex.split(command),
            ["aippocampus", "agent", "recall", cue, "--json"],
        )
        self.assertIn(shell_quote(cue), command)

    def test_foreground_action_contract_lint_rejects_competing_aliases(self) -> None:
        payload = {
            "foreground_action": {"id": "primary", "command": "aippocampus health --json"},
            "agent_next_action": {"id": "other", "command": "aippocampus doctor provider --json"},
            "safe_next_actions": [{"id": "third", "command": "aippocampus mcp status"}],
        }

        violations = foreground_action_contract_violations(payload)

        self.assertIn(
            {
                "field": "agent_next_action",
                "reason": "alias_must_match_foreground_action",
            },
            violations,
        )
        self.assertIn(
            {
                "field": "safe_next_actions.0",
                "reason": "primary_safe_action_must_match_foreground_action",
            },
            violations,
        )

    def test_foreground_action_contract_lint_rejects_skeletal_cards(self) -> None:
        payload = {
            "foreground_action_contract": "foreground-action-v1",
            "foreground_action": {
                "id": "continue_with_nonblocking_maintenance",
                "continue_without_command": True,
            },
            "agent_next_action": {
                "id": "continue_with_nonblocking_maintenance",
                "continue_without_command": True,
            },
            "safe_next_actions": [
                {
                    "id": "continue_with_nonblocking_maintenance",
                    "continue_without_command": True,
                }
            ],
        }

        reasons = {
            (violation["field"], violation["reason"])
            for violation in foreground_action_contract_violations(payload)
        }

        self.assertIn(
            ("foreground_action.label", "required_foreground_action_field_missing"),
            reasons,
        )
        self.assertIn(
            ("foreground_action.why", "required_foreground_action_field_missing"),
            reasons,
        )
        self.assertIn(
            ("foreground_action.mutation_risk", "required_foreground_action_field_missing"),
            reasons,
        )
        self.assertIn(
            ("foreground_action.claim_boundary", "required_foreground_action_field_missing"),
            reasons,
        )

    def test_foreground_action_contract_lint_rejects_unmarked_command_templates(self) -> None:
        action = {
            "id": "recall_with_cue",
            "label": "Recall with cue",
            "command_template": 'aippocampus agent recall "{cue}" --json',
            "requires": ["cue"],
            "why": "Use after the caller supplies a concrete continuity cue.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        }
        payload = canonical_foreground_action_fields(action)

        self.assertIn(
            {
                "field": "foreground_action.template_only",
                "reason": "command_template_requires_template_only_true",
            },
            foreground_action_contract_violations(payload),
        )

    def test_foreground_action_contract_lint_rejects_unmarked_secondary_templates(self) -> None:
        primary = {
            "id": "open_detail",
            "label": "Open detail",
            "command": "aippocampus agent deepen --request 1 --last-recall --json",
            "why": "Open the selected source before claims.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
            "secondary_action": {
                "id": "recall_with_cue",
                "label": "Recall with cue",
                "command_template": 'aippocampus agent recall "{cue}" --json',
                "why": "Use after the caller supplies a cue.",
                "mutation_risk": "read_only",
                "claim_boundary": "no_claim_before_reopen",
            },
        }
        payload = canonical_foreground_action_fields(primary)

        self.assertIn(
            {
                "field": "foreground_action.secondary_action.template_only",
                "reason": "command_template_requires_template_only_true",
            },
            foreground_action_contract_violations(payload),
        )

    def test_foreground_chooser_card_exposes_canonical_action_fields(self) -> None:
        primary = {
            "id": "check_sync_status",
            "label": "Check sync status",
            "command": "aippocampus sync status --json",
            "why": "Choose a read-only sync status before push or pull.",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
        }
        secondary = {
            "id": "check_object_sync_status",
            "label": "Check object sync status",
            "command": "aippocampus object-sync status --json",
            "why": "Check object sync state before choosing a write path.",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
        }

        card = foreground_chooser_card(
            kind="aippocampus_sync_chooser",
            decision="choose a read-only sync status before push or pull",
            choices=[primary, secondary],
        )

        self.assertEqual(card["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(card["foreground_action"], primary)
        self.assertEqual(card["agent_next_action"], primary)
        self.assertEqual(card["safe_next_actions"][0], primary)
        self.assertEqual(card["safe_next_actions"], card["choices"])
        self.assertEqual(foreground_action_contract_violations(card), [])

    def test_runtime_aippocampus_env_names_are_registered(self) -> None:
        runtime_names = aippocampus_env_names_from(
            [
                SCRIPTS / "aippocampus_runtime",
                SCRIPTS / "conversation_sources",
            ]
        )

        self.assertEqual(sorted(runtime_names - config_registry_names()), [])

    def test_public_env_docs_do_not_outgrow_config_registry(self) -> None:
        documented_names = aippocampus_env_names_from(
            [
                REPO_ROOT / ".env.example",
                REPO_ROOT / "docs" / "guides" / "public-api.md",
            ]
        )

        self.assertEqual(sorted(documented_names - config_registry_names()), [])

    def test_env_example_matches_runtime_hook_defaults_and_canonical_provider_knobs(self) -> None:
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        env_lines = dict(
            line.split("=", 1)
            for line in text.splitlines()
            if line and not line.startswith("#") and "=" in line
        )

        self.assertEqual(env_lines["AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS"], "3500")
        self.assertEqual(env_lines["AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS"], "15000")
        self.assertEqual(env_lines["AIPPOCAMPUS_SEMANTIC_GATE"], "auto")
        self.assertEqual(env_lines["AIPPOCAMPUS_SUBCONSCIOUS_HOOK"], "off")
        self.assertEqual(env_lines["AIPPOCAMPUS_BACKGROUND_MODEL_CONSENT"], "off")
        self.assertIn("AIPPOCAMPUS_DEEPSEEK_API_KEY", env_lines)
        self.assertNotIn("DEEPSEEK_API_KEY", env_lines)
        for name in (
            "AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING",
            "AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT",
            "AIPPOCAMPUS_OPENAI_COMPAT_REASONING_CONTENT_HANDLING",
            "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT",
        ):
            self.assertIn(name, env_lines)

    def test_config_report_redacts_values_paths_and_unknown_values(self) -> None:
        env = {
            "AIPPOCAMPUS_HOME": "C:/Users/example/private/aippocampus",
            "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY": "super-secret-value",
            "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "https://private-provider.example/v1",
            "AIPPOCAMPUS_UNKNOWN_LOCAL_FLAG": "do-not-print",
        }

        report = config_report(env)
        rendered = json.dumps(report, ensure_ascii=False)
        by_name = {entry["name"]: entry for entry in report["data"]["knobs"]}

        self.assertEqual(report["status"], "partial")
        self.assertIn(
            {"code": "unregistered_aippocampus_env", "name": "AIPPOCAMPUS_UNKNOWN_LOCAL_FLAG"},
            report["warnings"],
        )
        self.assertTrue(by_name["AIPPOCAMPUS_HOME"]["configured"])
        self.assertTrue(by_name["AIPPOCAMPUS_HOME"]["value_redacted"])
        self.assertTrue(by_name["AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY"]["sensitive"])
        self.assertTrue(by_name["AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY"]["value_redacted"])
        for forbidden in (
            "C:/Users/example/private/aippocampus",
            "super-secret-value",
            "https://private-provider.example/v1",
            "do-not-print",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_config_summary_report_is_compact_and_action_first(self) -> None:
        env = {
            "AIPPOCAMPUS_HOME": "C:/Users/example/private/aippocampus",
            "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY": "super-secret-value",
            "AIPPOCAMPUS_UNKNOWN_LOCAL_FLAG": "do-not-print",
        }

        summary = config_summary_report(config_report(env))
        rendered = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["kind"], "aippocampus_config_doctor_summary")
        self.assertEqual(summary["status"], "partial")
        self.assertGreater(summary["registered_knob_count"], 0)
        self.assertEqual(summary["unknown_env_var_count"], 1)
        self.assertEqual(summary["configured_count"], 2)
        self.assertEqual(summary["configured_sensitive_count"], 1)
        self.assertEqual(summary["detail"], "compact")
        self.assertEqual(summary["surface"], "foreground_decision_card")
        self.assertEqual(summary["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(summary["foreground_action"], summary["agent_next_action"])
        self.assertEqual(summary["safe_next_actions"][0], summary["foreground_action"])
        self.assertEqual(summary["foreground_action"]["id"], "review_unknown_config_env")
        self.assertNotIn("action_id", summary["foreground_action"])
        self.assertEqual(summary["safe_next_actions"][0]["command"], "aippocampus doctor config --detail full --json")
        self.assertEqual(summary["full_audit_command"], "aippocampus doctor config --detail full --json")
        self.assertTrue(summary["audit_json_available"])
        self.assertTrue(summary["recommended_actions"])
        self.assertNotIn("cannot_claim", summary)
        self.assertFalse(summary["privacy"]["values_printed"])
        self.assertNotIn("C:/Users/example/private/aippocampus", rendered)
        self.assertNotIn("super-secret-value", rendered)
        self.assertNotIn("do-not-print", rendered)

    def test_config_registry_metadata_is_classified(self) -> None:
        deepseek_key = CONFIG_BY_NAME["AIPPOCAMPUS_DEEPSEEK_API_KEY"]

        self.assertTrue(deepseek_key.sensitive)
        self.assertEqual(deepseek_key.owner, "model/routing")

        for name, knob in CONFIG_BY_NAME.items():
            with self.subTest(name=name):
                self.assertTrue(knob.owner)
                self.assertIn(knob.stability, CONFIG_STABILITY_BUCKETS)
                self.assertTrue(knob.surface)
                self.assertTrue(knob.default)

    def test_doctor_config_default_json_is_compact_decision_card(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch.dict(
                os.environ,
                {
                    "AIPPOCAMPUS_HOME": "C:/private/local/home",
                    "AIPPOCAMPUS_OBJECT_STORE_TOKEN": "private-token",
                },
                clear=True,
            ),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = facade.main(["doctor", "config", "--json"])

        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        payload = json.loads(rendered)
        self.assertEqual(payload["kind"], "aippocampus_config_doctor_summary")
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["surface"], "foreground_decision_card")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["id"], "no_action_needed")
        self.assertNotIn("action_id", payload["foreground_action"])
        self.assertNotIn("command", payload["foreground_action"])
        self.assertEqual(payload["agent_next_action"]["id"], "no_action_needed")
        self.assertEqual(
            payload["safe_next_actions"][1]["command"],
            "aippocampus doctor config --detail full --json",
        )
        self.assertNotIn("data", payload)
        self.assertNotIn("knobs", payload)
        self.assertNotIn("cannot_claim", payload)
        self.assertFalse(payload["privacy"]["values_printed"])
        self.assertNotIn("C:/private/local/home", rendered)
        self.assertNotIn("private-token", rendered)

    def test_doctor_config_full_operator_json_keeps_inventory_and_boundaries(self) -> None:
        from aippocampus_runtime.cli import facade

        for args in (
            ["doctor", "config", "--detail", "full", "--json"],
            ["doctor", "config", "--operator-json"],
        ):
            with self.subTest(args=args):
                with (
                    patch.dict(
                        os.environ,
                        {
                            "AIPPOCAMPUS_HOME": "C:/private/local/home",
                            "AIPPOCAMPUS_OBJECT_STORE_TOKEN": "private-token",
                        },
                        clear=True,
                    ),
                    patch("sys.stdout", new=StringIO()) as stdout,
                ):
                    code = facade.main(args)

                self.assertEqual(code, 0)
                rendered = stdout.getvalue()
                report = json.loads(rendered)
                self.assertEqual(report["data"]["kind"], "aippocampus_config_registry_report")
                self.assertTrue(report["data"]["no_write"])
                self.assertIn("knobs", report["data"])
                self.assertIn("cannot_claim", report)
        self.assertNotIn("C:/private/local/home", rendered)
        self.assertNotIn("private-token", rendered)

    def test_config_report_can_include_non_sensitive_resolved_values_and_validation(self) -> None:
        env = {
            "AIPPOCAMPUS_HOME": "C:/Users/example/private/aippocampus",
            "AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT": "abc",
            "AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS": "4200",
            "AIPPOCAMPUS_DEEPSEEK_API_KEY": "secret-key",
        }

        report = config_report(env, include_resolved=True)
        by_name = {entry["name"]: entry for entry in report["data"]["knobs"]}
        rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(by_name["AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS"]["resolved_value"], "4200")
        self.assertEqual(by_name["AIPPOCAMPUS_HOME"]["resolved_value"], "<local-path-redacted>")
        self.assertTrue(by_name["AIPPOCAMPUS_HOME"]["value_redacted"])
        self.assertEqual(by_name["AIPPOCAMPUS_DEEPSEEK_API_KEY"]["resolved_value"], "<redacted>")
        self.assertTrue(by_name["AIPPOCAMPUS_DEEPSEEK_API_KEY"]["value_redacted"])
        self.assertIn(
            {
                "code": "malformed_numeric_env",
                "name": "AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT",
                "value_kind": "positive_integer",
            },
            report["warnings"],
        )
        self.assertNotIn("C:/Users/example/private/aippocampus", rendered)
        self.assertNotIn("secret-key", rendered)

    def test_doctor_config_describe_one_knob_with_resolved_value(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch.dict(
                os.environ,
                {
                    "AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS": "4200",
                    "AIPPOCAMPUS_DEEPSEEK_API_KEY": "secret-key",
                },
                clear=True,
            ),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = facade.main(
                [
                    "doctor",
                    "config",
                    "describe",
                    "AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS",
                    "--resolved",
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        payload = json.loads(rendered)
        self.assertEqual(payload["kind"], "aippocampus_config_knob_detail")
        self.assertEqual(payload["knob"]["name"], "AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS")
        self.assertEqual(payload["knob"]["resolved_value"], "4200")
        self.assertIn("prompt hook", payload["knob"]["surface"])
        self.assertNotIn("secret-key", rendered)

    def test_doctor_config_compact_json_aliases_are_foreground_bounded(self) -> None:
        from aippocampus_runtime.cli import facade

        for flag in ("--compact-json", "--summary"):
            with self.subTest(flag=flag):
                with (
                    patch.dict(
                        os.environ,
                        {
                            "AIPPOCAMPUS_HOME": "C:/private/local/home",
                            "AIPPOCAMPUS_OBJECT_STORE_TOKEN": "private-token",
                        },
                        clear=True,
                    ),
                    patch("sys.stdout", new=StringIO()) as stdout,
                ):
                    code = facade.main(["doctor", "config", flag])

                self.assertEqual(code, 0)
                rendered = stdout.getvalue()
                payload = json.loads(rendered)
                self.assertEqual(payload["kind"], "aippocampus_config_doctor_summary")
                self.assertGreater(payload["registered_knob_count"], 0)
                self.assertEqual(payload["configured_count"], 2)
                self.assertEqual(payload["foreground_action"]["id"], "no_action_needed")
                self.assertNotIn("command", payload["foreground_action"])
                self.assertIn("safe_next_actions", payload)
                self.assertNotIn("knobs", payload)
                self.assertNotIn("C:/private/local/home", rendered)
                self.assertNotIn("private-token", rendered)
