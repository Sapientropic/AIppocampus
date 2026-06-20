"""Docs-health guard for benchmark evidence map discoverability."""

from __future__ import annotations

from pathlib import Path

REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS = {
    "## Benchmark-To-Action": "benchmark evidence map missing benchmark-to-action card",
    "tools/aippocampus/benchmark_outcomes.py": (
        "benchmark evidence map missing benchmark outcome router command pointer"
    ),
    "docs/evidence/benchmarks/design/benchmark-priority-map.md": (
        "benchmark evidence map missing run-selection action pointer"
    ),
    "benchmarks/reports/recall-navigation/README.md": (
        "benchmark evidence map missing recall-navigation current-state pointer"
    ),
    "docs/evidence/current-claims.md": (
        "benchmark evidence map missing current claims snapshot pointer"
    ),
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "benchmark evidence map missing current claim-boundary pointer"
    ),
    "docs/evidence/readiness/public-readiness-verification.md": (
        "benchmark evidence map missing dated verification ledger pointer"
    ),
    "docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md": (
        "benchmark evidence map missing benchmark methodology pointer"
    ),
    "benchmark_corpus/README.md": "benchmark evidence map missing corpus README pointer",
    "benchmark_corpus/sharegpt_manifest.json": (
        "benchmark evidence map missing corpus manifest pointer"
    ),
    "docs/evidence/benchmarks/reports/field-journey/memory-pain-fixture-report.md": (
        "benchmark evidence map missing memory-pain fixture report pointer"
    ),
    "docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md": (
        "benchmark evidence map missing hippocampal private annotation protocol pointer"
    ),
}

REQUIRED_RECALL_NAVIGATION_README_TERMS = {
    "## Current State": "recall-navigation README missing current-state card",
    "Recommended default explicit path": (
        "recall-navigation README missing recommended explicit path"
    ),
    "Default hook full foreground": (
        "recall-navigation README missing default-hook non-adoption boundary"
    ),
    "Tiny hook-to-agent affordance": (
        "recall-navigation README missing tiny affordance boundary"
    ),
    "default-hook-recall-usefulness-2026-06-20.md": (
        "recall-navigation README missing current default-hook report pointer"
    ),
}

BENCHMARK_EVIDENCE_EXCLUDED_SCRIPT_NAMES = {"_paths.py"}


def benchmark_evidence_entrypoints(repo_root: Path) -> list[str]:
    """Return benchmark/smoke entrypoints that must stay discoverable from the docs map."""

    paths: list[Path] = []

    benchmark_dir = repo_root / "benchmarks" / "aippocampus"
    if benchmark_dir.exists():
        paths.extend(sorted(benchmark_dir.glob("benchmark_*.py")))
        warm_case_builder = benchmark_dir / "builders" / "build_warm_ambient_trace_cases.py"
        if warm_case_builder.exists():
            paths.append(warm_case_builder)

    smoke_dir = repo_root / "tools" / "aippocampus" / "smoke"
    if smoke_dir.exists():
        paths.extend(
            sorted(
                path
                for path in smoke_dir.glob("*.py")
                if path.name not in BENCHMARK_EVIDENCE_EXCLUDED_SCRIPT_NAMES
            )
        )

    plugin_dir = repo_root / "plugins" / "aippocampus"
    if plugin_dir.exists():
        paths.extend(sorted(plugin_dir.glob("smoke_*.py")))

    return sorted({path.relative_to(repo_root).as_posix() for path in paths})


def benchmark_evidence_map_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    rel_path = "docs/evidence/benchmark-evidence-map.md"
    evidence_map = repo_root / rel_path
    if not evidence_map.exists():
        return [f"missing benchmark evidence map: {rel_path}"]

    text = evidence_map.read_text(encoding="utf-8")
    for term, issue in REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS.items():
        if term not in text:
            issues.append(issue)

    docs_readme = repo_root / "docs" / "README.md"
    if docs_readme.exists() and "benchmark-evidence-map.md" not in docs_readme.read_text(
        encoding="utf-8"
    ):
        issues.append("docs README missing benchmark evidence map pointer")

    for entrypoint in benchmark_evidence_entrypoints(repo_root):
        if entrypoint not in text:
            issues.append(f"benchmark evidence map missing entrypoint: {entrypoint}")

    recall_readme = (
        repo_root
        / "docs"
        / "evidence"
        / "benchmarks"
        / "reports"
        / "recall-navigation"
        / "README.md"
    )
    if recall_readme.exists():
        recall_text = recall_readme.read_text(encoding="utf-8")
        for term, issue in REQUIRED_RECALL_NAVIGATION_README_TERMS.items():
            if term not in recall_text:
                issues.append(issue)
    return issues
