from __future__ import annotations

from dataclasses import dataclass

BENCHMARK_FAST_LANE_CATEGORIES = frozenset(
    {
        "benchmark_guard",
        "benchmark_entrypoint_smoke",
    }
)


@dataclass(frozen=True)
class BenchmarkFastLaneProfile:
    module: str
    category: str
    rationale: str

    def as_dict(self) -> dict[str, str]:
        return {
            "module": self.module,
            "category": self.category,
            "rationale": self.rationale,
        }


BENCHMARK_FAST_LANE_PROFILES: dict[str, BenchmarkFastLaneProfile] = {
    "tests.aippocampus.test_benchmark_capability_provenance": BenchmarkFastLaneProfile(
        module="tests.aippocampus.test_benchmark_capability_provenance",
        category="benchmark_guard",
        rationale=(
            "Fast-lane provenance guard for benchmark capability records; "
            "benchmark tiers own quality evidence."
        ),
    ),
    "tests.aippocampus.test_benchmark_default_hook_recall_usefulness": BenchmarkFastLaneProfile(
        module="tests.aippocampus.test_benchmark_default_hook_recall_usefulness",
        category="benchmark_guard",
        rationale=(
            "PR-critical contract guard for default-hook recall fixtures; "
            "passing PR does not claim benchmark quality."
        ),
    ),
    "tests.aippocampus.test_benchmark_dream_delivery_quality": BenchmarkFastLaneProfile(
        module="tests.aippocampus.test_benchmark_dream_delivery_quality",
        category="benchmark_guard",
        rationale=(
            "PR-critical guard for dream-delivery benchmark wiring and public "
            "fixture boundaries, not a fresh benchmark evidence run."
        ),
    ),
    "tests.aippocampus.test_benchmark_entrypoints": BenchmarkFastLaneProfile(
        module="tests.aippocampus.test_benchmark_entrypoints",
        category="benchmark_entrypoint_smoke",
        rationale=(
            "Smoke-tests benchmark entrypoints and subprocess frontdoors only; "
            "it is not a quality evidence lane."
        ),
    ),
    "tests.aippocampus.test_benchmark_episode_arc_sequence_usefulness": BenchmarkFastLaneProfile(
        module="tests.aippocampus.test_benchmark_episode_arc_sequence_usefulness",
        category="benchmark_guard",
        rationale=(
            "PR-critical guard for episode-arc benchmark wiring; benchmark "
            "smoke/full benchmark tiers own evidence claims."
        ),
    ),
    "tests.aippocampus.test_benchmark_graph_extraction_boundary": BenchmarkFastLaneProfile(
        module="tests.aippocampus.test_benchmark_graph_extraction_boundary",
        category="benchmark_guard",
        rationale=(
            "Architecture boundary guard for graph extraction benchmark shape; "
            "it is not benchmark-result evidence."
        ),
    ),
}


def is_benchmark_shaped_module(module: str) -> bool:
    return module.rsplit(".", 1)[-1].startswith("test_benchmark_")


def benchmark_fast_lane_profile_for(module: str) -> BenchmarkFastLaneProfile | None:
    return BENCHMARK_FAST_LANE_PROFILES.get(module)


def require_benchmark_fast_lane_profile(module: str) -> BenchmarkFastLaneProfile:
    profile = benchmark_fast_lane_profile_for(module)
    if profile is None:
        raise ValueError(
            "benchmark-shaped fast-lane module needs explicit category/rationale: "
            f"{module}"
        )
    if profile.category not in BENCHMARK_FAST_LANE_CATEGORIES:
        raise ValueError(
            "benchmark-shaped fast-lane module has unsupported category "
            f"{profile.category!r}: {module}"
        )
    if not profile.rationale.strip():
        raise ValueError(
            "benchmark-shaped fast-lane module needs non-empty rationale: "
            f"{module}"
        )
    return profile
