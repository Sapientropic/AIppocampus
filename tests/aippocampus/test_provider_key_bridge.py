from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import provider_bridge as hook_provider_bridge  # noqa: E402
from aippocampus_runtime.ops import provider_key_bridge  # noqa: E402
from aippocampus_runtime.update import cli as update_cli  # noqa: E402

BRIDGE_PROVIDER_ENV_VAR = "PROVIDER_BRIDGE_TEST_VALUE"


def fake_provider_bridge_value(label: str) -> str:
    prefix = "".join(chr(code) for code in (115, 107, 45))
    return prefix + f"FAKE_TEST_PROVIDER_BRIDGE_{label}_1234567890"


class ProviderKeyBridgeTests(unittest.TestCase):
    def test_bridge_plan_selects_explicit_dotenv_candidate_without_secret_or_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            fixture_value = fake_provider_bridge_value("PLAN")
            dotenv.write_text(f"{BRIDGE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")

            report = provider_key_bridge.build_provider_key_bridge_plan(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
                credential_dotenv=dotenv,
            )
            encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["kind"], "aippocampus_provider_key_bridge")
        self.assertEqual(report["action"], "plan")
        self.assertFalse(report["applied"])
        self.assertEqual(report["candidate"]["status"], "candidate_present")
        self.assertEqual(report["candidate"]["secret_shape"], f"len:{len(fixture_value)}")
        self.assertFalse(report["candidate"]["value_printed"])
        self.assertFalse(report["candidate"]["path_included"])
        self.assertIn("bridge_manifest", {item["kind"] for item in report["writes"]})
        self.assertIn("codex_hooks_json", {item["kind"] for item in report["writes"]})
        self.assertFalse(report["privacy"]["secret_values_printed"])
        self.assertFalse(report["privacy"]["local_paths_included"])
        self.assertFalse(report["privacy"]["default_runtime_reads_credential_stores"])
        self.assertIn("future", report["claim_boundary"])
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_bridge_plan_missing_credential_source_has_recovery_actions(self) -> None:
        report = provider_key_bridge.build_provider_key_bridge_plan(
            target="codex-hooks",
            source="explicit-dotenv",
            provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
            credential_dotenv=None,
        )

        self.assertFalse(report["ok"])
        self.assertIn(
            "credential_candidate_missing",
            {item["code"] for item in report["issues"]},
        )
        self.assertIn("recommended_actions", report)
        self.assertEqual(
            report["recommended_actions"][0]["id"],
            "plan_with_private_credential_source",
        )
        self.assertIsInstance(report["agent_next_action"], dict)
        self.assertEqual(
            report["agent_next_action"]["command_template"],
            (
                "aippocampus onboard provider-key --plan --source explicit-dotenv "
                "--credential-dotenv {credential_dotenv_path} --json"
            ),
        )
        self.assertEqual(report["agent_next_action"]["requires"], ["credential_dotenv_path"])
        self.assertNotIn("<path>", json.dumps(report["recommended_actions"], ensure_ascii=False))
        self.assertIn("aippocampus search", report["recommended_actions"][1]["command"])

    def test_cli_plan_without_source_is_successful_chooser(self) -> None:
        old_default_key = os.environ.pop(provider_key_bridge.DEFAULT_PROVIDER_ENV_VAR, None)
        try:
            with patch("sys.stdout", new=StringIO()) as stdout:
                code = provider_key_bridge.main(["--plan", "--json"])
        finally:
            if old_default_key is not None:
                os.environ[provider_key_bridge.DEFAULT_PROVIDER_ENV_VAR] = old_default_key

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["action"], "plan")
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["candidate"]["status"], "source_choice_required")
        self.assertTrue(payload["chooser"]["no_write_happened"])
        commands = [item["command"] for item in payload["recommended_actions"] if item.get("command")]
        command_templates = [
            item["command_template"]
            for item in payload["recommended_actions"]
            if item.get("command_template")
        ]
        self.assertIn(
            (
                "aippocampus onboard provider-key --plan --source explicit-dotenv "
                "--credential-dotenv {credential_dotenv_path} --json"
            ),
            command_templates,
        )
        self.assertIn('aippocampus search "a distinctive old phrase"', commands)
        self.assertNotIn("<path>", json.dumps(payload["recommended_actions"], ensure_ascii=False))

    def test_cli_plan_without_source_prefers_visible_env_key_without_secret_leak(self) -> None:
        fixture_value = fake_provider_bridge_value("VISIBLE_ENV")
        with patch.dict(os.environ, {BRIDGE_PROVIDER_ENV_VAR: fixture_value}, clear=False):
            with patch("sys.stdout", new=StringIO()) as stdout:
                code = provider_key_bridge.main(
                    [
                        "--plan",
                        "--provider-env-var",
                        BRIDGE_PROVIDER_ENV_VAR,
                        "--json",
                    ]
                )
            payload = json.loads(stdout.getvalue())
            encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["source"]["kind"], "visible-env-key")
        self.assertEqual(payload["candidate"]["status"], "visible_env_key_present")
        self.assertTrue(payload["provider_env"]["visible_in_current_process"])
        self.assertTrue(payload["provider_env"]["visible_in_child_process"])
        self.assertEqual(
            payload["recommended_actions"][0]["id"],
            "confirm_visible_env_key",
        )
        self.assertIn("--source visible-env-key", payload["agent_next_action"])
        self.assertNotIn("--credential-dotenv <path>", payload["agent_next_action"])
        self.assertIn("explicit-dotenv", payload["alternate_paths"]["source_options"])
        self.assertFalse(payload["privacy"]["secret_values_printed"])
        self.assertNotIn(fixture_value, encoded)

    def test_help_leads_with_visible_env_key_before_private_dotenv_bridge(self) -> None:
        with self.assertRaises(SystemExit) as raised, patch("sys.stdout", new=StringIO()) as stdout:
            provider_key_bridge.main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = stdout.getvalue()
        visible_index = help_text.index("--source visible-env-key")
        explicit_index = help_text.index("--source explicit-dotenv")
        self.assertLess(visible_index, explicit_index)
        self.assertIn("Private dotenv fallback", help_text)

    def test_bridge_apply_installs_redacted_codex_hook_wrapper_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            dotenv = root / "provider.env"
            fixture_value = fake_provider_bridge_value("APPLY")
            dotenv.write_text(f"{BRIDGE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")

            report = provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
                credential_dotenv=dotenv,
                codex_home_path=codex_home,
            )
            encoded = json.dumps(report, ensure_ascii=False)
            hooks_json = codex_home / "hooks.json"
            hooks_data = hooks_json.read_text(encoding="utf-8")
            manifest = provider_key_bridge.bridge_manifest_path(codex_home)
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            hook_status = update_cli.status_hooks(codex_home)
            manifest_exists = manifest.exists()
            wrapper_exists = (
                provider_key_bridge.bridge_dir(codex_home) / "aippocampus_provider_bridge_hook.py"
            ).exists()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["applied"])
        self.assertEqual(report["action"], "apply")
        self.assertTrue(manifest_exists)
        self.assertTrue(wrapper_exists)
        self.assertIn("aippocampus_provider_bridge_hook.py", hooks_data)
        self.assertNotIn(fixture_value, hooks_data)
        self.assertNotIn(fixture_value, json.dumps(manifest_data, ensure_ascii=False))
        self.assertEqual(manifest_data["provider_env_var"], BRIDGE_PROVIDER_ENV_VAR)
        self.assertEqual(manifest_data["source"]["kind"], "explicit-dotenv")
        self.assertTrue(hook_status["prompt_installed"])
        self.assertTrue(hook_status["lifecycle_installed"])
        self.assertTrue(hook_status["provider_key_bridge_installed"])
        self.assertEqual(hook_status["status"], "current")
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_bridge_undo_restores_direct_hooks_and_removes_bridge_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            dotenv = root / "provider.env"
            fixture_value = fake_provider_bridge_value("UNDO")
            dotenv.write_text(f"{BRIDGE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")
            provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
                credential_dotenv=dotenv,
                codex_home_path=codex_home,
            )

            report = provider_key_bridge.undo_provider_key_bridge(
                target="codex-hooks",
                codex_home_path=codex_home,
            )
            encoded = json.dumps(report, ensure_ascii=False)
            hooks_data = (codex_home / "hooks.json").read_text(encoding="utf-8")
            manifest_exists = provider_key_bridge.bridge_manifest_path(codex_home).exists()
            wrapper_exists = (
                provider_key_bridge.bridge_dir(codex_home) / "aippocampus_provider_bridge_hook.py"
            ).exists()

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["undone"])
        self.assertIn("aippocampus_runtime.hooks.prompt", hooks_data)
        self.assertIn("aippocampus_runtime.hooks.lifecycle", hooks_data)
        self.assertNotIn("aippocampus_provider_bridge_hook.py", hooks_data)
        self.assertFalse(manifest_exists)
        self.assertFalse(wrapper_exists)
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_bridge_undo_without_bridge_is_noop_for_hooks_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            report = provider_key_bridge.undo_provider_key_bridge(
                target="codex-hooks",
                codex_home_path=codex_home,
            )
            hooks_exists = (codex_home / "hooks.json").exists()

        self.assertTrue(report["ok"], report)
        self.assertFalse(report["undone"])
        self.assertFalse(hooks_exists)
        self.assertFalse(report["hooks"]["updated"])
        self.assertFalse(report["manifest"]["removed"])
        self.assertFalse(report["hook_script"]["removed"])

    def test_hook_bridge_loads_explicit_dotenv_secret_without_public_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dotenv = root / "provider.env"
            fixture_value = fake_provider_bridge_value("RUNTIME")
            dotenv.write_text(f"{BRIDGE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")
            manifest = root / "bridge.json"
            provider_key_bridge.write_bridge_manifest(
                manifest,
                provider_key_bridge.build_bridge_manifest(
                        target="codex-hooks",
                        source="explicit-dotenv",
                        provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
                        credential_dotenv=dotenv,
                ),
            )

            update = hook_provider_bridge.environment_update_from_manifest(manifest)
            summary = provider_key_bridge.public_manifest_summary(manifest)

        self.assertEqual(update, {BRIDGE_PROVIDER_ENV_VAR: fixture_value})
        self.assertNotIn(fixture_value, json.dumps(summary, ensure_ascii=False))
        self.assertNotIn(str(dotenv), json.dumps(summary, ensure_ascii=False))

    def test_hook_bridge_windows_credential_source_fail_opens_off_windows(self) -> None:
        if sys.platform == "win32":
            self.skipTest("Windows Credential Manager lookup needs a host credential fixture.")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "bridge.json"
            manifest.write_text(
                json.dumps(
                    {
                        "provider_env_var": BRIDGE_PROVIDER_ENV_VAR,
                        "source": {
                            "kind": "windows-credential-manager",
                            "target_name": "AIppocampus/Test",
                        },
                    }
                ),
                encoding="utf-8",
            )

            update = hook_provider_bridge.environment_update_from_manifest(manifest)

        self.assertEqual(update, {})

    def test_hook_bridge_macos_keychain_source_uses_security_without_public_leak(self) -> None:
        fixture_value = fake_provider_bridge_value("KEYCHAIN")
        calls: list[list[str]] = []

        def fake_command_secret(argv: list[str]) -> str:
            calls.append(argv)
            return fixture_value

        old_command_secret = hook_provider_bridge._command_secret
        hook_provider_bridge._command_secret = fake_command_secret
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "bridge.json"
                provider_key_bridge.write_bridge_manifest(
                    manifest,
                    provider_key_bridge.build_bridge_manifest(
                        target="codex-hooks",
                        source="macos-keychain",
                        provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
                        keychain_service="AIppocampus/Test Service",
                        keychain_account="test-account",
                    ),
                )

                update = hook_provider_bridge.environment_update_from_manifest(manifest)
                summary = provider_key_bridge.public_manifest_summary(manifest)
        finally:
            hook_provider_bridge._command_secret = old_command_secret
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(update, {BRIDGE_PROVIDER_ENV_VAR: fixture_value})
        self.assertEqual(
            calls,
            [
                [
                    "security",
                    "find-generic-password",
                    "-w",
                    "-s",
                    "AIppocampus/Test Service",
                    "-a",
                    "test-account",
                ]
            ],
        )
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn("AIppocampus/Test Service", encoded)
        self.assertNotIn("test-account", encoded)

    def test_hook_bridge_linux_secret_service_source_uses_secret_tool_without_public_leak(self) -> None:
        fixture_value = fake_provider_bridge_value("SECRET_SERVICE")
        calls: list[list[str]] = []

        def fake_command_secret(argv: list[str]) -> str:
            calls.append(argv)
            return fixture_value

        old_command_secret = hook_provider_bridge._command_secret
        hook_provider_bridge._command_secret = fake_command_secret
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manifest = Path(tmp) / "bridge.json"
                provider_key_bridge.write_bridge_manifest(
                    manifest,
                    provider_key_bridge.build_bridge_manifest(
                        target="codex-hooks",
                        source="linux-secret-service",
                        provider_env_var=BRIDGE_PROVIDER_ENV_VAR,
                        selector_attributes={
                            "service": "aippocampus-test-service",
                            "account": "test-account",
                        },
                    ),
                )

                update = hook_provider_bridge.environment_update_from_manifest(manifest)
                summary = provider_key_bridge.public_manifest_summary(manifest)
        finally:
            hook_provider_bridge._command_secret = old_command_secret
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(update, {BRIDGE_PROVIDER_ENV_VAR: fixture_value})
        self.assertEqual(
            calls,
            [
                [
                    "secret-tool",
                    "lookup",
                    "account",
                    "test-account",
                    "service",
                    "aippocampus-test-service",
                ]
            ],
        )
        self.assertNotIn(fixture_value, encoded)
        self.assertNotIn("aippocampus-test-service", encoded)
        self.assertNotIn("test-account", encoded)

    def test_windows_credential_blob_decoder_prefers_utf8_unless_blob_looks_wide(self) -> None:
        ascii_secret = "plain-provider-token"
        wide_secret = "wide-provider-token"

        self.assertEqual(
            hook_provider_bridge._decode_windows_credential_blob(ascii_secret.encode("utf-8")),
            ascii_secret,
        )
        self.assertEqual(
            hook_provider_bridge._decode_windows_credential_blob(wide_secret.encode("utf-16-le")),
            wide_secret,
        )

    def test_hook_bridge_main_sets_env_before_delegating_without_public_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dotenv = root / "provider.env"
            provider_env_var = "PROVIDER_BRIDGE_TEST_VALUE"
            fixture_value = "provider-bridge-main-fixture-value"
            dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")
            manifest = root / "bridge.json"
            provider_key_bridge.write_bridge_manifest(
                manifest,
                provider_key_bridge.build_bridge_manifest(
                    target="codex-hooks",
                    source="explicit-dotenv",
                    provider_env_var=provider_env_var,
                    credential_dotenv=dotenv,
                ),
            )
            observed: dict[str, object] = {}

            def fake_delegate(event: str, args: list[str]) -> int:
                observed["event"] = event
                observed["args"] = list(args)
                observed["env_value"] = hook_provider_bridge.os.environ.get(provider_env_var)
                return 0

            old_stdin = sys.stdin
            old_delegate = hook_provider_bridge._delegate
            old_env = hook_provider_bridge.os.environ.get(provider_env_var)
            hook_provider_bridge._delegate = fake_delegate
            sys.stdin = StringIO('{"hook_event_name": "UserPromptSubmit"}')
            try:
                hook_provider_bridge.os.environ.pop(provider_env_var, None)
                exit_code = hook_provider_bridge.main(["--manifest", str(manifest), "--json"])
            finally:
                sys.stdin = old_stdin
                hook_provider_bridge._delegate = old_delegate
                if old_env is None:
                    hook_provider_bridge.os.environ.pop(provider_env_var, None)
                else:
                    hook_provider_bridge.os.environ[provider_env_var] = old_env
        encoded = json.dumps(observed, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(observed["event"], "UserPromptSubmit")
        self.assertEqual(observed["args"], ["--json"])
        self.assertEqual(observed["env_value"], fixture_value)
        self.assertNotIn(str(dotenv), encoded)

    def test_cli_onboard_provider_key_apply_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            dotenv = root / "provider.env"
            fixture_value = fake_provider_bridge_value("CLI")
            dotenv.write_text(f"{BRIDGE_PROVIDER_ENV_VAR}={fixture_value}\n", encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "onboard",
                    "provider-key",
                    "--apply",
                    "--target",
                    "codex-hooks",
                    "--source",
                    "explicit-dotenv",
                    "--provider-env-var",
                    BRIDGE_PROVIDER_ENV_VAR,
                    "--credential-dotenv",
                    str(dotenv),
                    "--codex-home",
                    str(codex_home),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            hooks_data = (codex_home / "hooks.json").read_text(encoding="utf-8")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["applied"])
        self.assertIn("aippocampus_provider_bridge_hook.py", hooks_data)
        self.assertNotIn(fixture_value, proc.stdout)
        self.assertNotIn(str(dotenv), proc.stdout)


if __name__ == "__main__":
    unittest.main()
