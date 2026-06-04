from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
CLI = SCRIPTS / "aippocampus_cli.py"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import provider_doctor  # noqa: E402

PROVIDER_ENV_NAMES = [
    "DEEPSEEK_API_KEY",
    "AIPPOCAMPUS_DEEPSEEK_BASE_URL",
    "DEEPSEEK_BASE_URL",
    "AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL",
    "AIPPOCAMPUS_DEEPSEEK_PRO_MODEL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_PRO_MODEL",
    "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK",
    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE",
    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER",
    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL",
    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL",
    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
    "LOCAL_PROVIDER_TEST_KEY",
]


@contextmanager
def provider_env(extra: dict[str, str] | None = None) -> Iterator[None]:
    old = {name: os.environ.get(name) for name in PROVIDER_ENV_NAMES}
    try:
        for name in PROVIDER_ENV_NAMES:
            os.environ.pop(name, None)
        if extra:
            os.environ.update(extra)
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class ProviderDoctorTests(unittest.TestCase):
    def test_missing_default_key_reports_hook_env_boundary_without_secret_values(self) -> None:
        with provider_env():
            report = provider_doctor.build_provider_doctor_report(model_route="default")
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "missing_provider_env_var")
        self.assertEqual(report["route"]["provider"], "deepseek")
        self.assertEqual(report["provider_env"]["env_var"], "DEEPSEEK_API_KEY")
        self.assertFalse(report["provider_env"]["visible_in_current_process"])
        self.assertFalse(report["provider_env"]["visible_in_child_process"])
        self.assertFalse(report["privacy"]["env_var_value_printed"])
        self.assertTrue(report["hook_relevance"]["prompt_hook_reads_process_env"])
        self.assertFalse(report["hook_relevance"]["actual_installed_hook_process_checked"])
        self.assertTrue(report["recommended_actions"])
        self.assertEqual(report["legacy_aliases"]["active_count"], 0)
        self.assertNotIn("sk-", encoded)

    def test_provider_doctor_reports_legacy_env_alias_names_without_values(self) -> None:
        with provider_env(
            {
                "DEEPSEEK_API_KEY": "sk-provider-doctor-test-secret",
                "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK": "0",
                "DEEPSEEK_MODEL": "legacy-flash-model",
            }
        ):
            report = provider_doctor.build_provider_doctor_report(model_route="default")
        alias_diagnostics = json.dumps(report["legacy_aliases"], ensure_ascii=False)
        aliases = {entry["alias"] for entry in report["legacy_aliases"]["active"]}

        self.assertEqual(aliases, {"AIIPPOCAMPUS_SUBCONSCIOUS_HOOK", "DEEPSEEK_MODEL"})
        self.assertFalse(report["legacy_aliases"]["value_printed"])
        self.assertFalse(report["legacy_aliases"]["local_paths_included"])
        self.assertFalse(report["privacy"]["legacy_alias_values_printed"])
        self.assertNotIn("legacy-flash-model", alias_diagnostics)
        self.assertNotIn('"0"', alias_diagnostics)
        self.assertNotIn("sk-provider-doctor-test-secret", json.dumps(report, ensure_ascii=False))

    def test_visible_default_key_reports_ready_without_leaking_value(self) -> None:
        secret = "sk-provider-doctor-test-secret"
        with provider_env({"DEEPSEEK_API_KEY": secret}):
            report = provider_doctor.build_provider_doctor_report(model_route="default")
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["provider_env"]["visible_in_current_process"])
        self.assertTrue(report["provider_env"]["visible_in_child_process"])
        self.assertTrue(report["hook_relevance"]["semantic_gate_enabled_for_route"])
        self.assertFalse(report["hook_relevance"]["actual_installed_hook_process_checked"])
        self.assertNotIn(secret, encoded)

    def test_provider_visibility_is_presence_only_and_does_not_read_empty_values(self) -> None:
        with provider_env({"DEEPSEEK_API_KEY": ""}):
            report = provider_doctor.build_provider_doctor_report(
                model_route="default",
                check_child_process=False,
            )

        self.assertTrue(report["ok"])
        self.assertTrue(report["provider_env"]["visible_in_current_process"])
        self.assertIsNone(report["provider_env"]["visible_in_child_process"])
        self.assertTrue(report["provider_env"]["presence_only"])
        self.assertFalse(report["provider_env"]["value_checked"])
        self.assertFalse(report["privacy"]["env_var_value_checked"])

    def test_custom_route_config_error_is_public_and_does_not_probe_secret_values(self) -> None:
        with provider_env(
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_semantic",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
            }
        ):
            report = provider_doctor.build_provider_doctor_report(model_route="local_semantic")
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "route_config_error")
        self.assertEqual(report["route"]["requested_route"], "local_semantic")
        self.assertIn("AIPPOCAMPUS_OPENAI_COMPAT_MODEL", report["route"]["error"]["message"])
        self.assertFalse(report["privacy"]["env_var_value_printed"])
        self.assertNotIn("LOCAL_PROVIDER_TEST_KEY", encoded)

    def test_cli_doctor_provider_runs_via_public_facade(self) -> None:
        env = dict(os.environ)
        for name in PROVIDER_ENV_NAMES:
            env.pop(name, None)
        env["DEEPSEEK_API_KEY"] = "sk-provider-doctor-cli-secret"
        proc = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "doctor",
                "provider",
                "--json",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_provider_doctor")
        self.assertTrue(payload["ok"])
        self.assertNotIn("sk-provider-doctor-cli-secret", proc.stdout)


if __name__ == "__main__":
    unittest.main()
