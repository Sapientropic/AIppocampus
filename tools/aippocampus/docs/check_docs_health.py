#!/usr/bin/env python3
"""Lightweight guardrails for keeping AIppocampus docs maintainable."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER, infer_scope_labels

MAX_SKILL_LINES = 220
MAX_SKILL_WORDS = 2600
MAX_SKILL_CODE_FENCES = 2

REQUIRED_REFERENCES = [
    "ambient-hooks.md",
    "retrieval-and-storage.md",
    "maintenance-and-operations.md",
    "subconscious-jobs.md",
]

REQUIRED_PROJECT_DOCS = [
    "docs/README.md",
    "docs/roadmap.md",
    "docs/evidence/benchmark-evidence-map.md",
    "docs/evidence/readiness/stage-0-5-readiness.md",
    "docs/planning/next-iteration-plan.md",
    "docs/architecture/runtime-script-map.md",
    "docs/architecture/gb-scale-roadmap.md",
    "docs/architecture/wukong-mining-notes.md",
    "docs/planning/technical-differentiation-analysis.md",
]

DOCS_ROOT_ALLOWED_MARKDOWN = {
    "README.md",
    "agent-context.md",
    "roadmap.md",
    "the-unfinished-map.md",
    "未干的地图.md",
}

DOCS_ROOT_ALLOWED_DIRECTORIES = {
    "archive",
    "architecture",
    "evidence",
    "guides",
    "planning",
    "research",
}

REQUIRED_RUNTIME_MAP_SCRIPTS = [
    "aippocampus_prompt_hook.py",
    "aippocampus_lifecycle_hook.py",
    "aippocampus_mcp_server.py",
    "aippocampus_health.py",
    "build_clean_source.py",
    "build_index.py",
    "build_segments.py",
    "build_project_timeline.py",
    "registry.py",
    "registry_search.py",
    "retrieval.py",
    "search_clean_source.py",
    "search_segments.py",
    "retrieval_score_fusion.py",
    "sync_bundle.py",
    "sync_object_storage.py",
    "encrypted_sync_bundle.py",
    "encrypted_sync_object_storage.py",
    "vault_sync_utils.py",
    "sync_vault.py",
    "subconscious_jobs.py",
    "subconscious_scheduler.py",
    "subconscious_worker.py",
    "subconscious_review.py",
    "compensatory_dream.py",
    "dream_precision_policy.py",
    "dream_one_sidedness.py",
    "dream_retrospective_lifecycle.py",
    "dream_sleep_cycle.py",
    "theme_emergence.py",
    "journey_tracking.py",
    "reflection_space.py",
    "memory_candidate_router.py",
    "agency_affordance.py",
    "coding_decision_events.py",
    "coding_ticket_host_contract.py",
    "coding_rejected_route_probes.py",
    "correction_reconsolidation.py",
    "model_client.py",
    "deepseek_model_routing.py",
    "semantic_recall_gate.py",
    "semantic_cue_cache.py",
    "warm_ambient_recall.py",
    "ambient_warm_scheduler.py",
    "ambient_recall_policy.py",
    "ambient_thread_cache.py",
    "question_confirmation.py",
    "question_confirmation_live.py",
    "question_feedback_policy.py",
    "question_index_sidecar.py",
    "question_vector_index.py",
    "question_health.py",
    "question_resolution.py",
]

REQUIRED_RUNTIME_MAP_TERMS = {
    "## High-Level Runtime Flow": "runtime script map missing high-level runtime flow",
    "Core recall is the": "runtime script map missing core recall path boundary",
    "outside the core recall path": "runtime script map missing maintenance/core-recall boundary",
    "## Recall Decision Test Map": "runtime script map missing recall decision test map",
    "test_prompt_recall_decision_boundaries.py": (
        "runtime script map missing prompt recall decision test pointer"
    ),
    "test_retrieval_query_policy.py": "runtime script map missing retrieval query test pointer",
    "test_warm_ambient_recall.py": "runtime script map missing warm ambient test pointer",
}

REQUIRED_DREAM_PHASE1_CONTRACT_TERMS = {
    "### Implemented Phase 1 Contract": "dream task design missing implemented Phase 1 contract",
    "skills/aippocampus/scripts/compensatory_dream.py": (
        "dream task design missing compensatory_dream implementation pointer"
    ),
    'finding_kind="dream_synthesized"': (
        "dream task design missing dream_synthesized output contract"
    ),
    'foreground_eligible=false': "dream task design missing foreground eligibility boundary",
    "tests/aippocampus/test_compensatory_dream.py": (
        "dream task design missing executable contract test pointer"
    ),
    "### Live Dream Worker DeepSeek KV Cache Contract": (
        "dream task design missing live DeepSeek KV cache contract"
    ),
    "deepseek_prefix_v1": "dream task design missing explicit DeepSeek cache contract id",
    "prompt_cache_hit_tokens": "dream task design missing DeepSeek cache hit telemetry field",
    "prompt_cache_miss_tokens": "dream task design missing DeepSeek cache miss telemetry field",
}

REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS = {
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "benchmark evidence map missing current claim-boundary pointer"
    ),
    "docs/evidence/readiness/public-readiness-verification.md": (
        "benchmark evidence map missing dated verification ledger pointer"
    ),
    "docs/evidence/benchmarks/memory-decision-benchmark-plan.md": (
        "benchmark evidence map missing benchmark methodology pointer"
    ),
    "benchmark_corpus/README.md": "benchmark evidence map missing corpus README pointer",
    "benchmark_corpus/sharegpt_manifest.json": (
        "benchmark evidence map missing corpus manifest pointer"
    ),
    "docs/evidence/benchmarks/memory-pain-fixture-report.md": (
        "benchmark evidence map missing memory-pain fixture report pointer"
    ),
}

REQUIRED_PUBLIC_API_CONTRACT_TERMS = {
    "### Environment Configuration Matrix": (
        "public API doc missing environment configuration matrix"
    ),
    "| Variable / family | Group | Audience | Default / precedence | Sensitivity | Stability |": (
        "public API doc missing environment matrix columns"
    ),
    "`AIPPOCAMPUS_PROJECTS_TOKEN`": (
        "public API doc missing project automation token classification"
    ),
    "### Python Import Stability Layers": (
        "public API doc missing Python import stability layers"
    ),
    "Stable automation surfaces": (
        "public API doc missing stable automation surface import guidance"
    ),
    "Trusted-process runtime helpers": (
        "public API doc missing trusted-process runtime helper boundary"
    ),
    "Internal helper imports": "public API doc missing internal helper import boundary",
    "`aippocampus_runtime.public` is deferred": (
        "public API doc missing deferred public facade decision"
    ),
}

BENCHMARK_EVIDENCE_EXCLUDED_SCRIPT_NAMES = {"_paths.py"}
LLM_CALL_CONTRACT_EXCLUDED_SCRIPT_NAMES = {"model_client.py"}

REQUIRED_PUBLIC_READINESS_DOCS = [
    "CONTRIBUTING.md",
    "docs/architecture/architecture-overview.md",
    "docs/guides/public-core-boundary.md",
    "docs/guides/install-guide.md",
    "docs/guides/demo-scenarios.md",
    "docs/guides/privacy-security-checklist.md",
    "docs/evidence/readiness/public-readiness-verification.md",
]

PUBLIC_DOC_COMMAND_LINT_FILES = {
    "README.md",
    "docs/guides/install-guide.md",
    "docs/guides/demo-scenarios.md",
    "skills/aippocampus/SKILL.md",
}

PUBLIC_EXAMPLE_BUNDLE_FILES = [
    "bundle_manifest.json",
    "handoff.md",
    "clean-source/manifest.json",
    "clean-source/messages.jsonl",
    "clean-source/turns.jsonl",
    "clean-source/semantic-scope-labels.jsonl",
    "index/manifest.json",
    "index/messages.jsonl",
    "index/graph.json",
    "registry/threads.json",
    "registry/subconscious_jobs.jsonl",
]
PUBLIC_EXAMPLE_BUNDLE_ALLOWED_FILES = set(PUBLIC_EXAMPLE_BUNDLE_FILES)

REQUIRED_PRIVATE_GITIGNORE_PATTERNS = [
    ".aippocampus/",
    "aippocampus-registry/",
    "thread-anchors.md",
]

REPO_MARKDOWN_EXCLUDED_PARTS = {
    ".git",
    ".tmp",
    "__pycache__",
}

ORIGIN_PHRASES = [
    "生命还能变成什么，而我能不能在变化后仍然是我。",
]

SECRET_OR_LOCAL_PATH_RE = re.compile(
    r"([A-Za-z]:\\|sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{20,}|"
    r"\b(api[_-]?key|secret|token|password|cookie|authorization)\b\s*[:=])",
    re.IGNORECASE,
)

WINDOWS_COMMAND_MARKERS = (
    "$env:",
    ".\\",
    "tools\\",
    "skills\\",
    "\\scripts\\",
    "Copy-Item",
)


def markdown_link_targets(text: str) -> set[str]:
    targets: set[str] = set()
    for raw_target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = raw_target.strip().strip("<>")
        if "://" in target or target.startswith("#"):
            continue
        target = target.split("#", maxsplit=1)[0].strip()
        if target:
            targets.add(target)
    return targets


def research_index_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    research_dir = repo_root / "docs" / "research"
    if not research_dir.exists():
        return issues

    root_readme = research_dir / "README.md"
    if not root_readme.exists():
        issues.append("research index missing: docs/research/README.md")
        return issues
    root_targets = markdown_link_targets(root_readme.read_text(encoding="utf-8"))

    for note in sorted(research_dir.glob("*.md")):
        if note.name == "README.md":
            continue
        rel = note.relative_to(research_dir).as_posix()
        if rel not in root_targets:
            issues.append(f"research index does not link docs/research/{rel}")

    for child in sorted(path for path in research_dir.iterdir() if path.is_dir()):
        markdown_files = sorted(path for path in child.glob("*.md") if path.name != "README.md")
        if not markdown_files:
            continue
        child_rel = child.relative_to(research_dir).as_posix()
        if f"{child_rel}/README.md" not in root_targets and f"{child_rel}/" not in root_targets:
            issues.append(f"research index does not link docs/research/{child_rel}/README.md")
        child_readme = child / "README.md"
        if not child_readme.exists():
            issues.append(
                f"research index subdirectory docs/research/{child_rel} must include README.md"
            )
            continue
        child_targets = markdown_link_targets(child_readme.read_text(encoding="utf-8"))
        for note in markdown_files:
            rel = note.relative_to(child).as_posix()
            if rel not in child_targets:
                issues.append(
                    f"research index docs/research/{child_rel}/README.md does not link {rel}"
                )
    return issues


def runtime_script_map_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    runtime_map = repo_root / "docs" / "architecture" / "runtime-script-map.md"
    if not runtime_map.exists():
        return ["missing runtime script map: docs/architecture/runtime-script-map.md"]
    text = runtime_map.read_text(encoding="utf-8")
    for script in REQUIRED_RUNTIME_MAP_SCRIPTS:
        if script not in text:
            issues.append(f"runtime script map missing high-risk script: {script}")
    for term, issue in REQUIRED_RUNTIME_MAP_TERMS.items():
        if term not in text:
            issues.append(issue)
    return issues


def dream_phase1_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    dream_doc = repo_root / "docs" / "research" / "dream-task-design.md"
    if not dream_doc.exists():
        return ["missing dream task design doc: docs/research/dream-task-design.md"]
    text = dream_doc.read_text(encoding="utf-8")
    for term, issue in REQUIRED_DREAM_PHASE1_CONTRACT_TERMS.items():
        if term not in text:
            issues.append(issue)
    return issues


def llm_call_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    scripts_dir = repo_root / "skills" / "aippocampus" / "scripts"
    if not scripts_dir.exists():
        return issues
    for path in sorted(scripts_dir.rglob("*.py")):
        if path.name in LLM_CALL_CONTRACT_EXCLUDED_SCRIPT_NAMES:
            continue
        rel = path.relative_to(repo_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            issues.append(f"cannot parse Python script for LLM contract scan: {rel}:{exc.lineno}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_chat_config = (
                isinstance(func, ast.Name)
                and func.id == "ChatClientConfig"
                or isinstance(func, ast.Attribute)
                and func.attr == "ChatClientConfig"
            )
            if not is_chat_config:
                continue
            keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg}
            if "cache_contract" not in keyword_names:
                issues.append(f"LLM ChatClientConfig missing explicit cache_contract: {rel}:{node.lineno}")
    return issues


def benchmark_evidence_entrypoints(repo_root: Path) -> list[str]:
    """Return benchmark/smoke entrypoints that must stay discoverable from the docs map."""

    paths: list[Path] = []

    benchmark_dir = repo_root / "benchmarks" / "aippocampus"
    if benchmark_dir.exists():
        paths.extend(sorted(benchmark_dir.glob("benchmark_*.py")))
        warm_case_builder = benchmark_dir / "build_warm_ambient_trace_cases.py"
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
    return issues


def public_api_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    rel_path = "docs/guides/public-api.md"
    public_api = repo_root / rel_path
    if not public_api.exists():
        return [f"missing public API contract doc: {rel_path}"]

    text = public_api.read_text(encoding="utf-8")
    for term, issue in REQUIRED_PUBLIC_API_CONTRACT_TERMS.items():
        if term not in text:
            issues.append(issue)
    return issues


def windows_context_from_recent_lines(lines: list[str], fence_start_line: int) -> bool:
    recent = "\n".join(lines[max(0, fence_start_line - 5) : fence_start_line - 1]).casefold()
    return "windows" in recent or "powershell" in recent


def public_doc_command_issues(rel_path: str, text: str) -> list[str]:
    issues: list[str] = []
    lines = text.splitlines()
    in_fence = False
    fence_lang = ""
    fence_start = 0
    fence_lines: list[str] = []
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = stripped.removeprefix("```").strip().casefold()
                fence_start = index
                fence_lines = []
                continue
            block = "\n".join(fence_lines)
            windows_context = windows_context_from_recent_lines(lines, fence_start)
            if fence_lang in {"powershell", "ps1"} and not windows_context:
                issues.append(
                    f"{rel_path}:{fence_start} has a Windows-only command block outside a Windows section"
                )
            if any(marker in block for marker in WINDOWS_COMMAND_MARKERS) and not windows_context:
                issues.append(
                    f"{rel_path}:{fence_start} has Windows path/env command syntax outside a Windows section"
                )
            in_fence = False
            fence_lang = ""
            fence_lines = []
            continue
        if in_fence:
            fence_lines.append(line)
    return issues


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def find_repo_root(skill_root: Path) -> Path | None:
    for candidate in [skill_root.parent.parent, *skill_root.parents]:
        if (candidate / "README.md").exists() and (candidate / "skills" / skill_root.name).exists():
            return candidate
    return None


def check_repo_docs(repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    metrics: dict[str, Any] = {"repo_docs_checked": True}

    docs_dir = repo_root / "docs"
    if docs_dir.exists():
        for path in sorted(docs_dir.glob("*.md")):
            if path.name not in DOCS_ROOT_ALLOWED_MARKDOWN:
                issues.append(
                    f"docs root has unclassified markdown file: docs/{path.name}; "
                    "move it under docs/architecture, docs/guides, docs/evidence, "
                    "docs/planning, or docs/research"
                )
        for path in sorted(item for item in docs_dir.iterdir() if item.is_dir()):
            if path.name not in DOCS_ROOT_ALLOWED_DIRECTORIES:
                issues.append(
                    f"docs root has unclassified directory: docs/{path.name}; "
                    "use docs/architecture, docs/guides, docs/evidence, "
                    "docs/planning, docs/research, or docs/archive"
                )

    origin_stub = repo_root / "docs" / "origin.md"
    if origin_stub.exists():
        issues.append("docs/origin.md duplicates the origin essay; link docs/未干的地图.md instead")

    issues.extend(runtime_script_map_issues(repo_root))
    issues.extend(dream_phase1_contract_issues(repo_root))
    issues.extend(llm_call_contract_issues(repo_root))
    issues.extend(benchmark_evidence_map_issues(repo_root))
    issues.extend(public_api_contract_issues(repo_root))

    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        issues.append("missing .gitignore for private generated memory artifacts")
    else:
        ignored = {
            line.strip().strip("/")
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for pattern in REQUIRED_PRIVATE_GITIGNORE_PATTERNS:
            if pattern.strip("/") not in ignored:
                issues.append(f"private generated artifact is not gitignored: {pattern}")

    essay = repo_root / "docs" / "未干的地图.md"
    english_essay = repo_root / "docs" / "the-unfinished-map.md"
    if not essay.exists():
        issues.append("missing canonical Chinese origin essay: docs/未干的地图.md")
        return issues, metrics
    if not english_essay.exists():
        issues.append("missing English origin essay transcreation: docs/the-unfinished-map.md")
        return issues, metrics

    for rel_path in REQUIRED_PUBLIC_READINESS_DOCS:
        if not (repo_root / rel_path).exists():
            issues.append(f"missing public-readiness doc: {rel_path}")

    for rel_path in sorted(PUBLIC_DOC_COMMAND_LINT_FILES):
        doc_path = repo_root / rel_path
        if doc_path.exists():
            issues.extend(public_doc_command_issues(rel_path, doc_path.read_text(encoding="utf-8")))

    issues.extend(research_index_issues(repo_root))

    example_bundle = repo_root / "examples" / "public-memory-bundle"
    if not example_bundle.exists():
        issues.append("missing public example memory bundle")
    else:
        for path in example_bundle.rglob("*"):
            if path.is_file():
                rel = path.relative_to(example_bundle).as_posix()
                if rel not in PUBLIC_EXAMPLE_BUNDLE_ALLOWED_FILES:
                    issues.append(
                        f"unexpected public example bundle file: examples/public-memory-bundle/{rel}"
                    )
        for rel_path in PUBLIC_EXAMPLE_BUNDLE_FILES:
            if not (example_bundle / rel_path).exists():
                issues.append(
                    f"missing public example bundle file: examples/public-memory-bundle/{rel_path}"
                )
        manifest = {}
        manifest_path = example_bundle / "bundle_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                issues.append(f"invalid public example bundle manifest: {type(exc).__name__}")
        if manifest.get("raw_rollout_included"):
            issues.append("public example memory bundle must not include raw rollout")
        if (example_bundle / "rollout.jsonl").exists():
            issues.append("public example memory bundle must not contain rollout.jsonl")
        clean_manifest_path = example_bundle / "clean-source" / "manifest.json"
        if clean_manifest_path.exists():
            try:
                clean_manifest = json.loads(clean_manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                issues.append(f"invalid public example clean-source manifest: {type(exc).__name__}")
                clean_manifest = {}
            if not clean_manifest.get("scope_label_policy"):
                issues.append(
                    "public example clean-source manifest must document scope_label_policy"
                )
        public_messages_by_id: dict[str, dict[str, Any]] = {}
        for rel_path in ["clean-source/messages.jsonl", "clean-source/turns.jsonl"]:
            jsonl_path = example_bundle / rel_path
            if not jsonl_path.exists():
                continue
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    try:
                        item = json.loads(line)
                    except Exception as exc:
                        issues.append(
                            f"invalid public example JSONL {rel_path}:{line_no}: {type(exc).__name__}"
                        )
                        continue
                    if not isinstance(item.get("scope_labels"), list):
                        issues.append(
                            f"public example JSONL missing scope_labels: examples/public-memory-bundle/{rel_path}:{line_no}"
                        )
                        continue
                    scope_labels = [
                        label for label in item.get("scope_labels", []) if isinstance(label, str)
                    ]
                    if scope_labels != [
                        label for label in SCOPE_LABEL_ORDER if label in set(scope_labels)
                    ]:
                        issues.append(
                            f"public example JSONL has non-canonical scope_labels order: examples/public-memory-bundle/{rel_path}:{line_no}"
                        )
                    if rel_path == "clean-source/messages.jsonl":
                        expected = infer_scope_labels(str(item.get("text") or ""))
                        if scope_labels != expected:
                            issues.append(
                                f"public example message scope_labels do not match current generator: "
                                f"examples/public-memory-bundle/{rel_path}:{line_no}"
                            )
                        public_messages_by_id[
                            str(item.get("message_id") or item.get("id") or "")
                        ] = item
                    elif rel_path == "clean-source/turns.jsonl":
                        expected_set = {
                            label
                            for message_id in item.get("message_ids", [])
                            for label in public_messages_by_id.get(str(message_id), {}).get(
                                "scope_labels", []
                            )
                            if isinstance(label, str)
                        }
                        expected = [label for label in SCOPE_LABEL_ORDER if label in expected_set]
                        if scope_labels != expected:
                            issues.append(
                                f"public example turn scope_labels do not match message union: "
                                f"examples/public-memory-bundle/{rel_path}:{line_no}"
                            )
        for path in example_bundle.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
                text = path.read_text(encoding="utf-8")
                if SECRET_OR_LOCAL_PATH_RE.search(text):
                    rel = path.relative_to(repo_root).as_posix()
                    issues.append(
                        f"public example bundle contains secret-like or local-path text: {rel}"
                    )

    markdown_files = [
        path
        for path in repo_root.rglob("*.md")
        if not any(part in REPO_MARKDOWN_EXCLUDED_PARTS for part in path.parts)
    ]
    metrics["repo_markdown_files"] = len(markdown_files)
    for phrase in ORIGIN_PHRASES:
        owners = [
            path.relative_to(repo_root).as_posix()
            for path in markdown_files
            if phrase in path.read_text(encoding="utf-8")
        ]
        if owners != ["docs/未干的地图.md"]:
            issues.append(
                f"origin phrase should live only in docs/未干的地图.md; found in {owners}"
            )
    return issues, metrics


def check_docs(root: Path) -> dict[str, Any]:
    root = root.resolve()
    skill_path = root / "SKILL.md"
    issues: list[str] = []

    if not skill_path.exists():
        return {
            "ok": False,
            "issues": [f"missing {skill_path}"],
            "metrics": {},
        }

    text = skill_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    word_count = count_words(text)
    code_fence_count = text.count("```")
    metrics = {
        "skill_lines": len(lines),
        "skill_words": word_count,
        "skill_code_fences": code_fence_count,
        "required_references": len(REQUIRED_REFERENCES),
    }

    if len(lines) > MAX_SKILL_LINES:
        issues.append(f"SKILL.md has {len(lines)} lines; keep it <= {MAX_SKILL_LINES}")
    if word_count > MAX_SKILL_WORDS:
        issues.append(f"SKILL.md has {word_count} words; keep it <= {MAX_SKILL_WORDS}")
    if code_fence_count > MAX_SKILL_CODE_FENCES:
        issues.append(
            f"SKILL.md has {code_fence_count} code-fence markers; move command dumps to references"
        )

    references_dir = root / "references"
    for filename in REQUIRED_REFERENCES:
        ref_path = references_dir / filename
        if not ref_path.exists():
            issues.append(f"missing reference: references/{filename}")
        if filename not in text:
            issues.append(f"SKILL.md does not link references/{filename}")

    if "changelog" in text.lower() and "Do not append changelog-style notes" not in text:
        issues.append("SKILL.md mentions changelog without the stable-entrypoint guardrail")

    repo_root = find_repo_root(root)
    if repo_root:
        for rel_path in REQUIRED_PROJECT_DOCS:
            if not (repo_root / rel_path).exists():
                issues.append(f"missing project doc: {rel_path}")
        repo_issues, repo_metrics = check_repo_docs(repo_root)
        issues.extend(repo_issues)
        metrics.update(repo_metrics)
    else:
        metrics["repo_docs_checked"] = False

    return {
        "ok": not issues,
        "issues": issues,
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=_paths.SKILL_ROOT,
        help="AIppocampus skill root. Defaults to this script's parent skill directory.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    args = parser.parse_args(argv)

    result = check_docs(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "OK" if result["ok"] else "FAILED"
        print(f"docs health: {status}")
        for key, value in result["metrics"].items():
            print(f"{key}: {value}")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
