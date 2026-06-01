from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools" / "aippocampus"
sys.path.insert(0, str(TOOLS))

import run_tests  # noqa: E402

SLOW_REVIEW_CUES = (
    "smoke",
    "real_history",
    "object_storage",
    "onboard",
    "plugin",
    "hook",
    "stage_0_5",
)

# These modules look operational but are intentionally cheap, deterministic unit
# guards. Future additions matching SLOW_REVIEW_CUES should not slide into fast
# by default; update this set only after checking that the module has no live
# service dependency, broad registry scan, plugin install, or long-running smoke.
FAST_REVIEWED_SENSITIVE_MODULES = {
    "tests.aippocampus.test_aippocampus_lifecycle_hook",
    "tests.aippocampus.test_codex_long_session_smoke",
    "tests.aippocampus.test_cross_agent_continuity_smoke",
    "tests.aippocampus.test_diagnose_hooks",
    "tests.aippocampus.test_install_lifecycle_hook",
    "tests.aippocampus.test_install_prompt_hook",
    "tests.aippocampus.test_macos_install_smoke_workflow",
    "tests.aippocampus.test_memory_pain_prompt_hook_smoke",
    "tests.aippocampus.test_multilingual_prompt_hook_smoke",
    "tests.aippocampus.test_question_confirmation_live_smoke",
    "tests.aippocampus.test_question_tracking_scale_smoke",
    "tests.aippocampus.test_semantic_paraphrase_reuse_smoke",
    "tests.aippocampus.test_semantic_scope_source_review",
    "tests.aippocampus.test_simulate_prompt_hook",
    "tests.aippocampus.test_synthetic_scale_capacity_smoke",
}


class RunTestsTierTests(unittest.TestCase):
    def test_main_preflights_tempdir_before_loading_tests(self) -> None:
        events: list[str] = []

        with (
            mock.patch.object(
                run_tests,
                "ensure_usable_tempdir",
                side_effect=lambda: events.append("tempdir"),
                create=True,
            ),
            mock.patch.object(run_tests, "modules_for_tier", return_value=["tests.fake"]),
            mock.patch.object(
                run_tests,
                "run_modules",
                side_effect=lambda modules, verbosity: events.append("run") or True,
            ),
        ):
            exit_code = run_tests.main(["--tier", "fast"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["tempdir", "run"])

    def test_tempdir_preflight_uses_fallback_when_default_temp_is_unusable(self) -> None:
        calls: list[Path | None] = []

        def fake_probe(path: Path | None) -> None:
            calls.append(path)
            if path is None:
                raise OSError("delete denied")

        with tempfile.TemporaryDirectory() as tmp:
            fallback = Path(tmp) / "runner-temp"
            fallback_identity = fallback.resolve()
            previous_tempdir = getattr(run_tests.tempfile, "tempdir", None)
            with (
                mock.patch.object(run_tests, "_probe_tempdir", side_effect=fake_probe),
                mock.patch.object(run_tests, "FALLBACK_TEST_TMPDIR", fallback),
                mock.patch.dict(os.environ, {}, clear=False),
            ):
                try:
                    selected = run_tests.ensure_usable_tempdir()
                    selected_env = {name: os.environ[name] for name in run_tests.TEMP_ENV_NAMES}
                finally:
                    run_tests.tempfile.tempdir = previous_tempdir

            self.assertEqual(selected, fallback_identity)
            self.assertEqual(calls, [None, fallback_identity])
            for name in run_tests.TEMP_ENV_NAMES:
                self.assertEqual(selected_env[name], str(fallback_identity))

    def test_slow_module_overrides_match_real_test_modules(self) -> None:
        discovered = set(run_tests.discover_modules())

        self.assertEqual(sorted(run_tests.SLOW_MODULES - discovered), [])

    def test_review_sensitive_modules_do_not_enter_fast_by_default(self) -> None:
        fast = set(run_tests.modules_for_tier("fast"))
        unexpected = sorted(
            module
            for module in fast
            if any(cue in module for cue in SLOW_REVIEW_CUES)
            and module not in FAST_REVIEWED_SENSITIVE_MODULES
        )

        self.assertEqual(unexpected, [])

    def test_tiers_partition_the_discovered_test_modules(self) -> None:
        discovered = set(run_tests.discover_modules())
        fast = set(run_tests.modules_for_tier("fast"))
        slow = set(run_tests.modules_for_tier("slow"))
        benchmark = set(run_tests.modules_for_tier("benchmark"))

        self.assertEqual(fast & slow, set())
        self.assertEqual(fast & benchmark, set())
        self.assertEqual(slow & benchmark, set())
        self.assertEqual(fast | slow | benchmark, discovered)


if __name__ == "__main__":
    unittest.main()
