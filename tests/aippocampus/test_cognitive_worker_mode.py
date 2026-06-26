from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from typing import Iterator

from aippocampus_runtime import cognitive_worker_mode

MODE_ENV_NAMES = [
    "AIPPOCAMPUS_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "AIPPOCAMPUS_COGNITIVE_WORKER_MODE",
    "AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE",
]

@contextmanager
def mode_env(extra: dict[str, str] | None = None) -> Iterator[None]:
    old = {name: os.environ.get(name) for name in MODE_ENV_NAMES}
    try:
        for name in MODE_ENV_NAMES:
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

class CognitiveWorkerModeTests(unittest.TestCase):
    def test_auto_prefers_external_model_when_provider_key_visible(self) -> None:
        with mode_env({"AIPPOCAMPUS_DEEPSEEK_API_KEY": "secret-value"}):
            report = cognitive_worker_mode.resolve_cognitive_worker_mode()

        self.assertEqual(report["resolved_mode"], "external_model")
        self.assertEqual(report["status"], "external_model_active")
        self.assertTrue(report["provider_key_visible"])
        self.assertNotIn("provider_key_env", report)
        self.assertFalse(report["privacy"]["provider_key_value_printed"])

    def test_auto_uses_agent_fallback_when_no_key_but_host_capability_present(self) -> None:
        with mode_env({"AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE": "1"}):
            report = cognitive_worker_mode.resolve_cognitive_worker_mode()

        self.assertEqual(report["resolved_mode"], "agent_fallback")
        self.assertEqual(report["status"], "agent_fallback_scaffold_only")
        self.assertEqual(report["ambient_state"], "callable")
        self.assertFalse(report["provider_key_visible"])
        self.assertTrue(report["agent_fallback_available"])
        self.assertTrue(report["contracts"]["agent_fallback_manual_only"])
        self.assertFalse(report["contracts"]["queued_task_is_readiness_evidence"])
        self.assertFalse(report["contracts"]["queued_task_is_usefulness_evidence"])
        self.assertFalse(report["contracts"]["foreground_hook_waits_for_agent_fallback"])

    def test_auto_degrades_to_deterministic_only_without_key_or_agent(self) -> None:
        with mode_env():
            report = cognitive_worker_mode.resolve_cognitive_worker_mode()

        self.assertEqual(report["resolved_mode"], "deterministic_only")
        self.assertEqual(report["status"], "deterministic_only_missing_provider_and_agent")
        self.assertFalse(report["agent_fallback_available"])

    def test_explicit_off_is_public_disable_not_missing_auth(self) -> None:
        with mode_env({"AIPPOCAMPUS_COGNITIVE_WORKER_MODE": "off"}):
            report = cognitive_worker_mode.resolve_cognitive_worker_mode()

        self.assertEqual(report["resolved_mode"], "off")
        self.assertEqual(report["status"], "disabled_by_env")

    def test_retired_deepseek_key_does_not_activate_external_model(self) -> None:
        with mode_env({"DEEPSEEK_API_KEY": "legacy-secret"}):
            legacy = cognitive_worker_mode.resolve_cognitive_worker_mode()
        with mode_env(
            {
                "AIPPOCAMPUS_DEEPSEEK_API_KEY": "canonical-secret",
                "DEEPSEEK_API_KEY": "legacy-secret",
            }
        ):
            canonical = cognitive_worker_mode.resolve_cognitive_worker_mode()

        self.assertEqual(legacy["resolved_mode"], "deterministic_only")
        self.assertFalse(legacy["provider_key_visible"])
        self.assertEqual(canonical["resolved_mode"], "external_model")
        self.assertTrue(canonical["provider_key_visible"])

if __name__ == "__main__":
    unittest.main()
