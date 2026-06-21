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


BENCHMARK_FAST_LANE_PROFILES: dict[str, BenchmarkFastLaneProfile] = {}


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
