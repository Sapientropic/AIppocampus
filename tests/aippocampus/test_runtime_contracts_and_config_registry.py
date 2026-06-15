from __future__ import annotations

import json
import os
import re
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
    public_envelope,
)

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
        self.assertEqual(summary["full_audit_command"], "aippocampus doctor config --json")
        self.assertTrue(summary["audit_json_available"])
        self.assertTrue(summary["recommended_actions"])
        self.assertFalse(summary["privacy"]["values_printed"])
        self.assertNotIn("C:/Users/example/private/aippocampus", rendered)
        self.assertNotIn("super-secret-value", rendered)
        self.assertNotIn("do-not-print", rendered)

    def test_config_registry_metadata_is_classified(self) -> None:
        for name, knob in CONFIG_BY_NAME.items():
            with self.subTest(name=name):
                self.assertTrue(knob.owner)
                self.assertIn(knob.stability, CONFIG_STABILITY_BUCKETS)
                self.assertTrue(knob.surface)
                self.assertTrue(knob.default)

    def test_doctor_config_cli_is_no_write_and_value_redacted(self) -> None:
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
        report = json.loads(rendered)
        self.assertEqual(report["data"]["kind"], "aippocampus_config_registry_report")
        self.assertTrue(report["data"]["no_write"])
        self.assertNotIn("C:/private/local/home", rendered)
        self.assertNotIn("private-token", rendered)

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
                self.assertNotIn("knobs", payload)
                self.assertNotIn("C:/private/local/home", rendered)
                self.assertNotIn("private-token", rendered)
