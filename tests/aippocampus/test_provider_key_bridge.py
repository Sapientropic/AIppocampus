from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import provider_bridge as hook_provider_bridge  # noqa: E402
from aippocampus_runtime.ops import provider_key_bridge  # noqa: E402
from aippocampus_runtime.update import cli as update_cli  # noqa: E402


class ProviderKeyBridgeTests(unittest.TestCase):
    def test_bridge_plan_selects_explicit_dotenv_candidate_without_secret_or_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            secret = "sk-provider-key-bridge-secret"
            dotenv.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")

            report = provider_key_bridge.build_provider_key_bridge_plan(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var="DEEPSEEK_API_KEY",
                credential_dotenv=dotenv,
            )
            encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["kind"], "aippocampus_provider_key_bridge")
        self.assertEqual(report["action"], "plan")
        self.assertFalse(report["applied"])
        self.assertEqual(report["candidate"]["status"], "candidate_present")
        self.assertEqual(report["candidate"]["secret_shape"], f"len:{len(secret)}")
        self.assertFalse(report["candidate"]["value_printed"])
        self.assertFalse(report["candidate"]["path_included"])
        self.assertIn("bridge_manifest", {item["kind"] for item in report["writes"]})
        self.assertIn("codex_hooks_json", {item["kind"] for item in report["writes"]})
        self.assertFalse(report["privacy"]["secret_values_printed"])
        self.assertFalse(report["privacy"]["local_paths_included"])
        self.assertFalse(report["privacy"]["default_runtime_reads_credential_stores"])
        self.assertIn("future", report["claim_boundary"])
        self.assertNotIn(secret, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_bridge_apply_installs_redacted_codex_hook_wrapper_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            dotenv = root / "provider.env"
            secret = "sk-provider-key-bridge-apply-secret"
            dotenv.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")

            report = provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var="DEEPSEEK_API_KEY",
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
        self.assertNotIn(secret, hooks_data)
        self.assertNotIn(secret, json.dumps(manifest_data, ensure_ascii=False))
        self.assertEqual(manifest_data["provider_env_var"], "DEEPSEEK_API_KEY")
        self.assertEqual(manifest_data["source"]["kind"], "explicit-dotenv")
        self.assertTrue(hook_status["prompt_installed"])
        self.assertTrue(hook_status["lifecycle_installed"])
        self.assertTrue(hook_status["provider_key_bridge_installed"])
        self.assertEqual(hook_status["status"], "current")
        self.assertNotIn(secret, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_bridge_undo_restores_direct_hooks_and_removes_bridge_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            dotenv = root / "provider.env"
            secret = "sk-provider-key-bridge-undo-secret"
            dotenv.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
            provider_key_bridge.apply_provider_key_bridge(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var="DEEPSEEK_API_KEY",
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
        self.assertNotIn(secret, encoded)
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
            secret = "sk-provider-key-bridge-runtime-secret"
            dotenv.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
            manifest = root / "bridge.json"
            provider_key_bridge.write_bridge_manifest(
                manifest,
                provider_key_bridge.build_bridge_manifest(
                    target="codex-hooks",
                    source="explicit-dotenv",
                    provider_env_var="DEEPSEEK_API_KEY",
                    credential_dotenv=dotenv,
                ),
            )

            update = hook_provider_bridge.environment_update_from_manifest(manifest)
            summary = provider_key_bridge.public_manifest_summary(manifest)

        self.assertEqual(update, {"DEEPSEEK_API_KEY": secret})
        self.assertNotIn(secret, json.dumps(summary, ensure_ascii=False))
        self.assertNotIn(str(dotenv), json.dumps(summary, ensure_ascii=False))

    def test_hook_bridge_windows_credential_source_fail_opens_off_windows(self) -> None:
        if sys.platform == "win32":
            self.skipTest("Windows Credential Manager lookup needs a host credential fixture.")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "bridge.json"
            manifest.write_text(
                json.dumps(
                    {
                        "provider_env_var": "DEEPSEEK_API_KEY",
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
        secret = "sk-provider-key-bridge-keychain-secret"
        calls: list[list[str]] = []

        def fake_command_secret(argv: list[str]) -> str:
            calls.append(argv)
            return secret

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
                        provider_env_var="DEEPSEEK_API_KEY",
                        keychain_service="AIppocampus/Test Service",
                        keychain_account="test-account",
                    ),
                )

                update = hook_provider_bridge.environment_update_from_manifest(manifest)
                summary = provider_key_bridge.public_manifest_summary(manifest)
        finally:
            hook_provider_bridge._command_secret = old_command_secret
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(update, {"DEEPSEEK_API_KEY": secret})
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
        self.assertNotIn(secret, encoded)
        self.assertNotIn("AIppocampus/Test Service", encoded)
        self.assertNotIn("test-account", encoded)

    def test_hook_bridge_linux_secret_service_source_uses_secret_tool_without_public_leak(self) -> None:
        secret = "sk-provider-key-bridge-secret-service"
        calls: list[list[str]] = []

        def fake_command_secret(argv: list[str]) -> str:
            calls.append(argv)
            return secret

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
                        provider_env_var="DEEPSEEK_API_KEY",
                        secret_attributes={
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

        self.assertEqual(update, {"DEEPSEEK_API_KEY": secret})
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
        self.assertNotIn(secret, encoded)
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
            secret = "sk-provider-key-bridge-cli-secret"
            dotenv.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
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
                    "DEEPSEEK_API_KEY",
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
        self.assertNotIn(secret, proc.stdout)
        self.assertNotIn(str(dotenv), proc.stdout)


if __name__ == "__main__":
    unittest.main()
