from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import provider_doctor  # noqa: E402

PROVIDER_ENV_NAMES = [
    "DEEPSEEK_API_KEY",
    "PROVIDER_DOCTOR_TEST_VALUE",
    "LOCAL_PROVIDER_ROUTE_VALUE",
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
    "AIPPOCAMPUS_COGNITIVE_WORKER_MODE",
    "AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE",
]
DOTENV_PROVIDER_ENV_VAR = "PROVIDER_DOCTOR_TEST_VALUE"
LOCAL_ROUTE_PROVIDER_ENV_VAR = "LOCAL_PROVIDER_ROUTE_VALUE"


def fake_provider_doctor_value(label: str) -> str:
    prefix = "".join(chr(code) for code in (115, 107, 45))
    return prefix + f"FAKE_TEST_PROVIDER_DOCTOR_{label}_1234567890"


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
        self.assertEqual(
            report["cognitive_worker"]["status"],
            "deterministic_only_missing_provider_and_agent",
        )
        self.assertFalse(report["privacy"]["env_var_value_printed"])
        self.assertTrue(report["hook_relevance"]["prompt_hook_reads_process_env"])
        self.assertFalse(report["hook_relevance"]["actual_installed_hook_process_checked"])
        self.assertTrue(report["recommended_actions"])
        self.assertEqual(report["legacy_aliases"]["active_count"], 0)
        self.assertNotIn("sk-", encoded)

    def test_provider_doctor_reports_legacy_env_alias_names_without_values(self) -> None:
        fixture_value = fake_provider_doctor_value("LEGACY")
        with provider_env(
            {
                "DEEPSEEK_API_KEY": fixture_value,
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
        self.assertNotIn(fixture_value, json.dumps(report, ensure_ascii=False))

    def test_visible_default_key_reports_ready_without_leaking_value(self) -> None:
        fixture_value = fake_provider_doctor_value("VISIBLE")
        with provider_env({"DEEPSEEK_API_KEY": fixture_value}):
            report = provider_doctor.build_provider_doctor_report(model_route="default")
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["provider_env"]["visible_in_current_process"])
        self.assertTrue(report["provider_env"]["visible_in_child_process"])
        self.assertTrue(report["hook_relevance"]["semantic_gate_enabled_for_route"])
        self.assertEqual(report["cognitive_worker"]["status"], "external_model_active")
        self.assertFalse(report["hook_relevance"]["actual_installed_hook_process_checked"])
        self.assertNotIn(fixture_value, encoded)

    def test_provider_doctor_reports_agent_fallback_mode_without_key_value(self) -> None:
        with provider_env({"AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE": "1"}):
            report = provider_doctor.build_provider_doctor_report(
                model_route="default",
                check_child_process=False,
            )
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "missing_provider_env_var")
        self.assertEqual(report["cognitive_worker"]["resolved_mode"], "agent_fallback")
        self.assertEqual(report["cognitive_worker"]["status"], "agent_fallback_active")
        self.assertTrue(report["cognitive_worker"]["agent_fallback_available"])
        self.assertNotIn("secret", encoded.casefold())

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
        self.assertNotIn(LOCAL_ROUTE_PROVIDER_ENV_VAR, encoded)

    def test_cli_doctor_provider_runs_via_public_facade(self) -> None:
        fixture_value = fake_provider_doctor_value("CLI")
        env = dict(os.environ)
        for name in PROVIDER_ENV_NAMES:
            env.pop(name, None)
        env["DEEPSEEK_API_KEY"] = fixture_value
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "doctor",
                "provider",
                "--json",
            ],
            cwd=SCRIPTS,
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
        self.assertNotIn(fixture_value, proc.stdout)

    def test_explicit_dotenv_discovery_reports_candidate_without_secret_or_path_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            dotenv = Path(tmp) / ".env"
            fixture_value = fake_provider_doctor_value("DOTENV")
            dotenv.write_text(
                f"{DOTENV_PROVIDER_ENV_VAR}={fixture_value}\nIGNORED=value\n",
                encoding="utf-8",
            )
            report = provider_doctor.build_provider_doctor_report(
                model_route="default",
                provider_env_var=DOTENV_PROVIDER_ENV_VAR,
                check_child_process=False,
                discover_credential_sources=True,
                credential_dotenv_paths=[dotenv],
            )
        encoded = json.dumps(report, ensure_ascii=False)
        discovery = report["credential_discovery"]
        dotenv_candidates = [
            item for item in discovery["candidates"] if item["source"] == "explicit_dotenv"
        ]

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "missing_provider_env_var")
        self.assertTrue(discovery["checked"])
        self.assertTrue(discovery["explicit_command_required"])
        self.assertFalse(discovery["privacy"]["secret_values_printed"])
        self.assertFalse(discovery["privacy"]["local_paths_included"])
        self.assertEqual(len(dotenv_candidates), 1)
        self.assertEqual(dotenv_candidates[0]["env_var"], DOTENV_PROVIDER_ENV_VAR)
        self.assertEqual(dotenv_candidates[0]["status"], "candidate_present")
        self.assertEqual(dotenv_candidates[0]["validation_status"], "unknown_not_probed")
        self.assertFalse(dotenv_candidates[0]["value_printed"])
        self.assertFalse(dotenv_candidates[0]["path_included"])
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_credential_discovery_never_scans_dotenv_without_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            dotenv = Path(tmp) / ".env"
            fixture_value = fake_provider_doctor_value("UNREQUESTED")
            default_env_var = "_".join(("DEEPSEEK", "API", "KEY"))
            dotenv.write_text(f"{default_env_var}={fixture_value}\n", encoding="utf-8")
            old_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                report = provider_doctor.build_provider_doctor_report(
                    model_route="default",
                    check_child_process=False,
                    discover_credential_sources=True,
                )
            finally:
                os.chdir(old_cwd)
        encoded = json.dumps(report, ensure_ascii=False)
        discovery = report["credential_discovery"]

        self.assertEqual(
            [item["source"] for item in discovery["candidates"]],
            ["current_process_env"],
        )
        self.assertEqual(
            discovery["bridge_plan"][0]["id"],
            "set_provider_env_in_hook_environment",
        )
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_credential_discovery_validation_distinguishes_valid_and_401_without_leaking_values(
        self,
    ) -> None:
        valid_fixture = fake_provider_doctor_value("VALID_DOTENV")
        stale_fixture = fake_provider_doctor_value("STALE")

        def fake_validator(candidate: dict[str, object], route: object) -> dict[str, object]:
            token_shape = candidate.get("secret_shape")
            if token_shape == f"len:{len(valid_fixture)}":
                return {"status": "valid", "method": "test_models_probe"}
            return {"status": "invalid_401", "method": "test_models_probe"}

        with tempfile.TemporaryDirectory() as tmp, provider_env():
            valid_dotenv = Path(tmp) / "valid.env"
            stale_dotenv = Path(tmp) / "stale.env"
            valid_dotenv.write_text(f"{DOTENV_PROVIDER_ENV_VAR}={valid_fixture}\n", encoding="utf-8")
            stale_dotenv.write_text(f"{DOTENV_PROVIDER_ENV_VAR}={stale_fixture}\n", encoding="utf-8")
            report = provider_doctor.build_provider_doctor_report(
                model_route="default",
                provider_env_var=DOTENV_PROVIDER_ENV_VAR,
                check_child_process=False,
                discover_credential_sources=True,
                credential_dotenv_paths=[stale_dotenv, valid_dotenv],
                validate_credentials=True,
                credential_validator=fake_validator,
            )
        encoded = json.dumps(report, ensure_ascii=False)
        dotenv_candidates = [
            item for item in report["credential_discovery"]["candidates"]
            if item["source"] == "explicit_dotenv"
        ]

        self.assertEqual(len(dotenv_candidates), 2)
        self.assertEqual(
            [item["validation_status"] for item in dotenv_candidates],
            ["invalid_401", "valid"],
        )
        self.assertEqual(dotenv_candidates[0]["validation_method"], "test_models_probe")
        self.assertNotIn(valid_fixture, encoded)
        self.assertNotIn(stale_fixture, encoded)

    def test_credential_validation_refuses_non_https_non_loopback_route_without_network_call(
        self,
    ) -> None:
        calls: list[object] = []

        def fake_urlopen(*args: object, **kwargs: object) -> object:
            calls.append((args, kwargs))
            raise AssertionError("unsafe route should not be probed")

        with tempfile.TemporaryDirectory() as tmp, provider_env(
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "unsafe",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "unsafe-test",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "unsafe-model",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://example.invalid/v1",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": LOCAL_ROUTE_PROVIDER_ENV_VAR,
            }
        ), patch("urllib.request.urlopen", fake_urlopen):
            dotenv = Path(tmp) / ".env"
            fixture_value = fake_provider_doctor_value("UNSAFE_ROUTE")
            dotenv.write_text(f"{LOCAL_ROUTE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")
            report = provider_doctor.build_provider_doctor_report(
                model_route="unsafe",
                provider_env_var=LOCAL_ROUTE_PROVIDER_ENV_VAR,
                check_child_process=False,
                discover_credential_sources=True,
                credential_dotenv_paths=[dotenv],
                validate_credentials=True,
            )
        encoded = json.dumps(report, ensure_ascii=False)
        dotenv_candidate = report["credential_discovery"]["candidates"][1]

        self.assertEqual(dotenv_candidate["validation_status"], "unsafe_transport_not_probed")
        self.assertEqual(calls, [])
        self.assertNotIn(fixture_value, encoded)

    def test_credential_validation_allows_https_probe_without_printing_url_or_secret(
        self,
    ) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        seen_urls: list[str] = []

        def fake_urlopen(request: object, **kwargs: object) -> FakeResponse:
            seen_urls.append(request.full_url)  # type: ignore[attr-defined]
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp, provider_env(
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "safe",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "safe-test",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "safe-model",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "https://provider.example/v1",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": LOCAL_ROUTE_PROVIDER_ENV_VAR,
            }
        ), patch("urllib.request.urlopen", fake_urlopen):
            dotenv = Path(tmp) / ".env"
            fixture_value = fake_provider_doctor_value("SAFE_ROUTE")
            dotenv.write_text(f"{LOCAL_ROUTE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")
            report = provider_doctor.build_provider_doctor_report(
                model_route="safe",
                provider_env_var=LOCAL_ROUTE_PROVIDER_ENV_VAR,
                check_child_process=False,
                discover_credential_sources=True,
                credential_dotenv_paths=[dotenv],
                validate_credentials=True,
            )
        encoded = json.dumps(report, ensure_ascii=False)
        dotenv_candidate = report["credential_discovery"]["candidates"][1]

        self.assertEqual(dotenv_candidate["validation_status"], "valid")
        self.assertEqual(seen_urls, ["https://provider.example/v1/models"])
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn("provider.example", encoded)

    def test_cli_provider_discovery_accepts_explicit_dotenv_path_without_leaking_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            fixture_value = fake_provider_doctor_value("CLI_DOTENV")
            dotenv.write_text(f"{DOTENV_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")
            env = dict(os.environ)
            for name in PROVIDER_ENV_NAMES:
                env.pop(name, None)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "doctor",
                    "provider",
                    "--provider-env-var",
                    DOTENV_PROVIDER_ENV_VAR,
                    "--discover-credential-sources",
                    "--credential-dotenv",
                    str(dotenv),
                    "--no-child-check",
                    "--json",
                ],
                cwd=SCRIPTS,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["credential_discovery"]["candidates"][1]["source"], "explicit_dotenv")
        self.assertNotIn(fixture_value, proc.stdout)
        self.assertNotIn(str(dotenv), proc.stdout)


if __name__ == "__main__":
    unittest.main()
