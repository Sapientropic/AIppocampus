from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import prompt as hook  # noqa: E402


def _dream_off() -> dict[str, object]:
    return {
        "mode": "off",
        "event": None,
        "allow_dream": False,
        "dream_hypothesis_limit": 0,
        "reason": "off",
    }


def _runtime_for_skip_result() -> dict[str, Any]:
    result = {
        "decision": "skip",
        "score": 0.0,
        "confidence": "low",
        "query_terms": [],
        "reasons": ["no ambient recall cue"],
        "candidates": [],
        "evidence": [],
        "working_memory": [],
        "semantic_gate": None,
        "ambient_recall": {"cache_status": {"status": "disabled"}},
        "elapsed_ms": 1.0,
    }
    return {
        "assess_prompt": lambda *args, **kwargs: result,
        "apply_dream_delivery_boundary": lambda value, **kwargs: value,
        "public_hook_debug_payload": lambda value: {
            "decision": value["decision"],
            "elapsed_ms": value["elapsed_ms"],
        },
        "hook_stdout_payload": lambda value: None,
        "hook_input_from_stdin": lambda: {},
    }


class PromptHookHotPathTests(unittest.TestCase):
    def test_prompt_hook_cold_import_defers_debug_and_skip_telemetry_modules(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, sys; "
                    "import aippocampus_runtime.hooks.prompt; "
                    "names = ["
                    "'aippocampus_runtime.hooks.debug_log', "
                    "'aippocampus_runtime.hooks.skip_telemetry', "
                    "'aippocampus_runtime.ops.log_retention', "
                    "'aippocampus_runtime.core'"
                    "]; "
                    "print(json.dumps({name: name in sys.modules for name in names}, sort_keys=True))"
                ),
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.loads(proc.stdout),
            {
                "aippocampus_runtime.core": False,
                "aippocampus_runtime.hooks.debug_log": False,
                "aippocampus_runtime.hooks.skip_telemetry": False,
                "aippocampus_runtime.ops.log_retention": False,
            },
        )

    def test_default_fallback_classifies_missing_runtime_without_raw_error_text(self) -> None:
        stdout = io.StringIO()
        secret_path = r"C:\Users\private\secret-rollout.jsonl"
        with (
            patch.object(
                hook,
                "_load_runtime",
                side_effect=ModuleNotFoundError(f"missing runtime at {secret_path}"),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = hook.main(["--prompt", "继续这个方向", "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertEqual(payload["decision"], "skip")
        self.assertEqual(payload["fallback_reason"], "runtime_unavailable")
        self.assertEqual(payload["error_type"], "ModuleNotFoundError")
        self.assertNotIn(secret_path, encoded)

    def test_default_fallback_classifies_unexpected_runtime_failure_without_raw_error_text(self) -> None:
        stdout = io.StringIO()
        private_marker = "private-runtime-detail"
        with (
            patch.object(
                hook,
                "_load_runtime",
                side_effect=RuntimeError(f"unexpected failure: {private_marker}"),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = hook.main(["--prompt", "普通任务", "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertEqual(payload["decision"], "skip")
        self.assertEqual(payload["fallback_reason"], "unexpected_runtime_error")
        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertNotIn(private_marker, encoded)

    def test_strict_reraises_unexpected_runtime_failure(self) -> None:
        with (
            patch.object(hook, "_load_runtime", side_effect=RuntimeError("boom")),
            self.assertRaisesRegex(RuntimeError, "boom"),
        ):
            hook.main(["--prompt", "普通任务", "--json", "--strict"])

    def test_strict_reraises_skip_telemetry_failure(self) -> None:
        runtime = _runtime_for_skip_result()
        with (
            patch.object(hook, "_load_runtime", return_value=runtime),
            patch.object(hook, "_prepare_dream_delivery", return_value=_dream_off()),
            patch.object(
                hook,
                "write_skip_telemetry",
                side_effect=RuntimeError("telemetry write failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "telemetry write failed"),
        ):
            hook.main(["--prompt", "普通任务", "--json", "--strict"])

    def test_strict_reraises_audit_status_failure(self) -> None:
        runtime = _runtime_for_skip_result()
        with (
            patch.object(hook, "_load_runtime", return_value=runtime),
            patch.object(hook, "_prepare_dream_delivery", return_value=_dream_off()),
            patch.object(
                hook,
                "write_prompt_hook_audit_status",
                side_effect=RuntimeError("audit write failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "audit write failed"),
        ):
            hook.main(
                [
                    "--prompt",
                    "普通任务",
                    "--json",
                    "--no-skip-telemetry",
                    "--strict",
                ]
            )


if __name__ == "__main__":
    unittest.main()
