from __future__ import annotations

import sys
import unittest
from pathlib import Path

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
    "tests.aippocampus.test_question_confirmation_live_smoke",
    "tests.aippocampus.test_question_tracking_scale_smoke",
    "tests.aippocampus.test_semantic_paraphrase_reuse_smoke",
    "tests.aippocampus.test_semantic_scope_source_review",
    "tests.aippocampus.test_simulate_prompt_hook",
    "tests.aippocampus.test_synthetic_scale_capacity_smoke",
}


class RunTestsTierTests(unittest.TestCase):
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
