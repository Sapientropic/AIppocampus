#!/usr/bin/env python3
"""Lightweight guardrails for keeping AIppocampus docs maintainable."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import ia_pressure_guard
from architecture_index_guard import architecture_index_issues
from classifier_policy_guard import development_status_classifier_issues
from evidence_index_guard import evidence_index_issues
from legacy_alias_guard import legacy_alias_inventory_issues
from product_profile_guard import (
    product_profile_contract_issues,
    public_core_product_profile_issues,
)
from reader_path_guard import reader_path_issues
from source_kernel_guard import source_kernel_contract_issues

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

REQUIRED_SKILL_CONTINUITY_TERMS = {
    "source-backed continuity scaffold": "SKILL.md missing continuity scaffold promise",
    "not innate model memory": "SKILL.md missing no-innate-memory boundary",
    "when an agent knows it has AIppocampus": (
        "SKILL.md missing continuity permission framing"
    ),
    "relationship continuity": "SKILL.md missing relationship-continuity posture",
    "## Agent Stance": "SKILL.md missing agent stance section",
    "Could old source, old corrections, unfinished work": (
        "SKILL.md missing task-boundary continuity question"
    ),
    "Do not search every turn.": (
        "SKILL.md missing proactive-vs-overactive anti-nag boundary"
    ),
    "Do not run heavy recall every turn.": "SKILL.md missing heavy-recall boundary",
    "Source-backed evidence should be respected": (
        "SKILL.md missing bounded source-evidence respect"
    ),
    "## Memory Packet Action Grammar": (
        "SKILL.md missing packet action grammar section"
    ),
    "direction_only": "SKILL.md missing direction_only action grammar",
    "reopenable_route": "SKILL.md missing reopenable_route action grammar",
    "bounded_evidence": "SKILL.md missing bounded_evidence action grammar",
    "source_open": "SKILL.md missing source_open action grammar",
    "ignore_or_blocked": "SKILL.md missing ignore_or_blocked action grammar",
    "Active Path Packets": "SKILL.md missing route-first Active Path Packet framing",
    "before broad manual search": "SKILL.md missing route-first search boundary",
    "progressive MCP tools": "SKILL.md missing progressive MCP recall preference",
}

REQUIRED_PROJECT_DOCS = [
    "docs/README.md",
    "docs/roadmap.md",
    "docs/architecture/legacy-alias-inventory.md",
    "docs/evidence/README.md",
    "docs/evidence/benchmark-evidence-map.md",
    "docs/evidence/current-claims.md",
    "docs/evidence/readiness/stage-0-5-readiness.md",
    "docs/planning/next-iteration-plan.md",
    "docs/architecture/runtime-script-map.md",
    "docs/architecture/gb-scale-roadmap.md",
    "docs/architecture/wukong-mining-notes.md",
    "docs/planning/technical-differentiation-analysis.md",
]

DOCS_ROOT_ALLOWED_MARKDOWN = {
    "README.md", "agent-context.md", "roadmap.md", "start-here.md",
    "the-unfinished-map.md", "未干的地图.md",
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
    "aippocampus_runtime/hooks/prompt.py",
    "aippocampus_runtime/hooks/lifecycle.py",
    "aippocampus_runtime/mcp/server.py",
    "aippocampus_runtime/health.py",
    "aippocampus_runtime/source/clean_source.py",
    "aippocampus_runtime/recall/index_builder.py",
    "aippocampus_runtime/recall/segment_builder.py",
    "aippocampus_runtime/navigation/project_timeline.py",
    "aippocampus_runtime/registry/api.py",
    "aippocampus_runtime/registry/search.py",
    "aippocampus_runtime/recall/retrieval.py",
    "aippocampus_runtime/source/search.py",
    "aippocampus_runtime/recall/segment_search.py",
    "aippocampus_runtime/recall/score_fusion.py",
    "aippocampus_runtime/sync/bundle.py",
    "aippocampus_runtime/sync/object_storage/cli.py",
    "aippocampus_runtime/sync/encrypted/bundle.py",
    "aippocampus_runtime/vault/sync.py",
    "aippocampus_runtime/subconscious/jobs.py",
    "aippocampus_runtime/subconscious/scheduler.py",
    "aippocampus_runtime/subconscious/agent_fallback_executor.py",
    "aippocampus_runtime/subconscious/agent_fallback_materializer.py",
    "aippocampus_runtime/subconscious/worker.py",
    "aippocampus_runtime/subconscious/review.py",
    "aippocampus_runtime/dream/compensatory.py",
    "aippocampus_runtime/dream/precision_policy.py",
    "aippocampus_runtime/dream/one_sidedness.py",
    "aippocampus_runtime/dream/retrospective_lifecycle.py",
    "aippocampus_runtime/dream/sleep_cycle.py",
    "aippocampus_runtime/subconscious/theme_emergence.py",
    "aippocampus_runtime/journey/tracking.py",
    "aippocampus_runtime/reflection/space.py",
    "aippocampus_runtime/subconscious/candidate_router.py",
    "aippocampus_runtime/coding/agency_affordance.py",
    "aippocampus_runtime/coding/decision_events.py",
    "aippocampus_runtime/coding/host_contract.py",
    "aippocampus_runtime/coding/rejected_route_probes.py",
    "aippocampus_runtime/reflection/reconsolidation.py",
    "aippocampus_runtime/model/client.py",
    "aippocampus_runtime/model/routing.py",
    "aippocampus_runtime/recall/semantic_recall_gate.py",
    "aippocampus_runtime/warm_ambient/recall.py",
    "aippocampus_runtime/warm_ambient/scheduler.py",
    "aippocampus_runtime/warm_ambient/config.py",
    "aippocampus_runtime/warm_ambient/diagnostics.py",
    "aippocampus_runtime/question/confirmation_live.py",
    "aippocampus_runtime/question/index_sidecar.py",
    "aippocampus_runtime/question/health.py",
    "aippocampus_runtime/subconscious/question_resolution.py",
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
    "skills/aippocampus/scripts/aippocampus_runtime/dream/compensatory.py": (
        "dream task design missing compensatory_dream implementation pointer"
    ),
    'finding_kind="dream_synthesized"': (
        "dream task design missing dream_synthesized output contract"
    ),
    'foreground_eligible=false': "dream task design missing foreground eligibility boundary",
    "tests/aippocampus/test_aippocampus_runtime.dream.compensatory": (
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
    "docs/evidence/current-claims.md": (
        "benchmark evidence map missing current claims snapshot pointer"
    ),
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
    "docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md": (
        "benchmark evidence map missing hippocampal private annotation protocol pointer"
    ),
}

CURRENT_CLAIMS_SNAPSHOT_DOC = "docs/evidence/current-claims.md"

REQUIRED_CURRENT_CLAIMS_TERMS = {
    "## Current Claim Snapshot": "current claims snapshot missing current snapshot section",
    "metric_id": "current claims snapshot missing metric-id column",
    "run_date": "current claims snapshot missing run-date column",
    "source_report": "current claims snapshot missing source-report column",
    "claim_level": "current claims snapshot missing claim-level column",
    "cohort": "current claims snapshot missing cohort column",
    "supersedes": "current claims snapshot missing supersession column",
    "cannot_claim": "current claims snapshot missing cannot-claim column",
    "semantic_sidecar.aggregate_materialized_rows": (
        "current claims snapshot missing semantic sidecar aggregate metric"
    ),
    "semantic_sidecar.strict_survival_snapshot": (
        "current claims snapshot missing historical strict sidecar metric"
    ),
    "semantic_sidecar.source_review_green_gate": (
        "current claims snapshot missing semantic sidecar green-review metric"
    ),
    "semantic_sidecar.source_review_diagnostic": (
        "current claims snapshot missing semantic sidecar diagnostic-review metric"
    ),
    "track_b.private_semantic_sidecar_required": (
        "current claims snapshot missing private Track B semantic-sidecar metric"
    ),
    "fts5.real_history_recall_2026_05_29": (
        "current claims snapshot missing dated FTS5 real-history metric"
    ),
    "demo_scenarios.claim_boundaries": (
        "current claims snapshot missing demo scenario claim-boundary pointer"
    ),
}

CURRENT_CLAIMS_POINTER_DOCS = {
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "stage readiness missing current claims snapshot pointer"
    ),
    "docs/guides/demo-scenarios.md": "demo scenarios missing current claims snapshot pointer",
}

PROOF_SLICE_MATURITY_DOC = "docs/evidence/readiness/proof-slice-maturity.md"

REQUIRED_PROOF_SLICE_MATURITY_TERMS = {
    "`design_only`": "proof-slice maturity board missing design_only status",
    "`deterministic_smoke`": (
        "proof-slice maturity board missing deterministic_smoke status"
    ),
    "`public_safe_fixture`": (
        "proof-slice maturity board missing public_safe_fixture status"
    ),
    "`second_user`": "proof-slice maturity board missing second_user status",
    "`release_claimable`": (
        "proof-slice maturity board missing release_claimable status"
    ),
    "last_checked": "proof-slice maturity board missing last_checked field",
    "Cannot claim": "proof-slice maturity board missing cannot-claim column",
    "Owner / evidence": "proof-slice maturity board missing owner/evidence column",
}

PROOF_SLICE_MATURITY_POINTER_DOCS = {
    "docs/README.md": "docs README missing proof-slice maturity board pointer",
    "docs/evidence/readiness/stage-0-5-readiness.md": (
        "stage readiness missing proof-slice maturity board pointer"
    ),
}

# These phrase guards are intentionally narrow. They block specific stale
# evidence claims that have already misled issue triage while avoiding broad
# scans for ordinary identifiers such as current_thread or current_frontier.
STALE_CURRENT_EVIDENCE_PHRASES = {
    "docs/evidence/readiness/stage-0-5-readiness.md": {
        "current strict sidecars at 2 threads/5 rows": (
            "stage readiness has stale semantic sidecar current wording: "
            "current strict sidecars at 2 threads/5 rows"
        ),
        "current strict materialization keeps only": (
            "stage readiness has stale semantic sidecar current wording: "
            "current strict materialization keeps only"
        ),
    },
    "docs/evidence/readiness/public-readiness-verification.md": {
        "current strict re-materialized sidecars intentionally contain only 5 rows across 2": (
            "public readiness ledger has stale semantic sidecar current wording: "
            "current strict re-materialized sidecars intentionally contain only 5 rows "
            "across 2"
        ),
    },
}

HIPPOCAMPAL_PRIVATE_ANNOTATION_DOC = (
    "docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md"
)

REQUIRED_HIPPOCAMPAL_PRIVATE_ANNOTATION_TERMS = {
    "truth-source independence": (
        "hippocampal private annotation protocol missing truth-source independence"
    ),
    "## Reviewer And Adjudication Flow": (
        "hippocampal private annotation protocol missing reviewer/adjudication flow"
    ),
    "disagreement": "hippocampal private annotation protocol missing disagreement handling",
    "## Sanitized Dated Report Template": (
        "hippocampal private annotation protocol missing sanitized report template"
    ),
    "cannot_claim": "hippocampal private annotation protocol missing cannot-claim boundary",
    "raw private text": "hippocampal private annotation protocol missing privacy exclusions",
    "local paths": "hippocampal private annotation protocol missing privacy exclusions",
    "unsanitized snippets": "hippocampal private annotation protocol missing privacy exclusions",
    "20 scenes": "hippocampal private annotation protocol missing 20-scene sample plan",
    "15-30 minutes per scene": (
        "hippocampal private annotation protocol missing annotation time estimate"
    ),
    "synthetic fixture external validity": (
        "hippocampal private annotation protocol missing external-validity gate"
    ),
    "themes discussed at least three times": (
        "hippocampal private annotation protocol missing theme sampling rule"
    ),
    "cross-thread decision evolution": (
        "hippocampal private annotation protocol missing cross-thread sampling rule"
    ),
    "naturally degraded recall prompt": (
        "hippocampal private annotation protocol missing natural prompt sampling rule"
    ),
    "realistic distractor": (
        "hippocampal private annotation protocol missing distractor sampling rule"
    ),
}

REQUIRED_PUBLIC_API_CONTRACT_TERMS = {
    "### CLI JSON Error Contract": (
        "public API doc missing CLI JSON error contract"
    ),
    "`error.code`": "public API doc missing stable CLI error code field",
    "`error.class`": "public API doc missing stable CLI error class field",
    "`missing_prerequisite`": "public API doc missing stable CLI error classes",
    "`validation_error`": "public API doc missing validation error class",
    "`privacy_block`": "public API doc missing privacy error class",
    "`runtime_error`": "public API doc missing runtime error class",
    "Exit code `2`": "public API doc missing stable CLI exit class policy",
    "### MCP Control-Plane Boundary": (
        "public API doc missing MCP control-plane boundary"
    ),
    "Control-plane registration means": (
        "public API doc missing MCP control-plane definition"
    ),
    "memory-write API": "public API doc missing MCP memory-write non-goal",
    "Future MCP write additions must prove": (
        "public API doc missing future MCP write review bar"
    ),
    "privacy, provenance, idempotence": (
        "public API doc missing MCP write review criteria"
    ),
    "### Environment Configuration Matrix": (
        "public API doc missing environment configuration matrix"
    ),
    "| Variable / family | Group | Audience | Default / precedence | Sensitivity | Stability |": (
        "public API doc missing environment matrix columns"
    ),
    "`AIPPOCAMPUS_PROJECTS_TOKEN`": (
        "public API doc missing project automation token classification"
    ),
    "legacy-alias-inventory.md": "public API doc missing legacy alias inventory pointer",
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
    "`aippocampus import conversation --format generic-jsonl --input <path>`": (
        "public API doc missing provider-neutral conversation import command"
    ),
    "`python -m aippocampus_runtime.registry.api register-source --provider generic-jsonl --input <path>`": (
        "public API doc missing registry register-source command"
    ),
    "not a generic arbitrary-file ingest endpoint": (
        "public API doc missing MCP/register-source boundary"
    ),
}

REQUIRED_PUBLIC_CORE_SCHEMA_CONTRACT_TERMS = {
    "### Metadata Namespace And Extension Rules": (
        "public core schema doc missing metadata namespace rules"
    ),
    "`metadata.core`": "public core schema doc missing core metadata namespace",
    "`metadata.provider`": "public core schema doc missing provider metadata namespace",
    "`metadata.extensions`": "public core schema doc missing extension metadata namespace",
    "must not override or reinterpret top-level public fields": (
        "public core schema doc missing top-level field override guard"
    ),
    "Extension payloads should include": (
        "public core schema doc missing extension version guidance"
    ),
    "Private export mode": "public core schema doc missing metadata privacy boundary",
    "labels remain navigation": (
        "public core schema doc missing model-label truth boundary"
    ),
    "### Runtime Clean-Source Manifest": (
        "public core schema doc missing runtime clean-source manifest contract"
    ),
    "`source_artifact`": "public core schema doc missing provider-neutral source artifact",
    "`source_transcript_size`": (
        "public core schema doc missing provider-neutral transcript metadata"
    ),
    "`source_rollout`": "public core schema doc missing legacy rollout alias boundary",
    "`messages.jsonl`": "public core schema doc missing clean-source message mapping",
    "`turns.jsonl`": "public core schema doc missing clean-source turn mapping",
    "`kind` and `phase`": "public core schema doc missing provider-normalized metadata boundary",
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

# Python support is a public install and contributor claim. Keep the contract
# checked here so metadata, docs, and CI do not drift into false compatibility.
CANONICAL_PYTHON_FLOOR = "3.12"
CANONICAL_PYTHON_REQUIRES = ">=3.12"
SUPPORTED_PUBLIC_PYTHON_VERSIONS = ("3.12", "3.13")
UNSUPPORTED_PUBLIC_PYTHON_VERSION_CLAIMS = ("3.10", "3.11")

PYTHON_VERSION_DOC_TERMS = {
    "README.md": (
        "AIppocampus supports Python 3.12 and newer",
        "Homebrew Python 3.12",
    ),
    "CONTRIBUTING.md": (
        "public Python support floor is Python 3.12",
        "Python 3.10 and Python 3.11",
        "unsupported public targets",
    ),
    "docs/guides/install-guide.md": (
        "Install Python 3.12 or newer",
        "Homebrew Python 3.12",
    ),
}

PYTHON_VERSION_WORKFLOW_TERMS = {
    ".github/workflows/aippocampus-ci.yml": (
        'python-version: ["3.12", "3.13"]',
        'python-version: "3.12"',
    ),
    ".github/workflows/macos-install-smoke.yml": (
        'default: "3.12"',
        '- "3.12"',
        '- "3.13"',
    ),
}

DEPENDENCY_CONTRACT_REQUIRED_OPTIONAL_EXTRAS = {
    "dev": ["build==1.3.0", "coverage==7.14.1", "mypy==2.1.0", "ruff==0.15.12"],
    "release": ["build==1.3.0", "check-jsonschema==0.37.2", "twine==6.2.0"],
    "benchmark": [],
    "openai-agents": ["openai-agents>=0.17.4,<1"],
    "openai-agents-smoke": ["openai-agents==0.17.4"],
}

DEPENDENCY_CONTRACT_DOC_TERMS = {
    "dependencies = []": "dependency contract doc missing empty runtime dependency contract",
    "`openai-agents` is the user-facing optional integration extra": (
        "dependency contract doc missing user-facing optional integration boundary"
    ),
    "CI uses `openai-agents-smoke`, an exact-pinned smoke extra": (
        "dependency contract doc missing exact-pinned OpenAI Agents smoke boundary"
    ),
    "`benchmark` is intentionally empty": (
        "dependency contract doc missing deterministic benchmark dependency boundary"
    ),
    "Use the exact-pinned `dev` extra": (
        "dependency contract doc missing contributor tooling install path"
    ),
    "Use the exact-pinned `release` extra": (
        "dependency contract doc missing release tooling install path"
    ),
    "exact-pinned `setuptools` backend": (
        "dependency contract doc missing build backend reproducibility boundary"
    ),
    "setup-python` pip caching": "dependency contract doc missing CI caching boundary",
}

SAFE_ENV_REQUIRED_KEYS = {
    "AIPPOCAMPUS_HOME",
    "AIPPOCAMPUS_REGISTRY_DIR",
    "AIPPOCAMPUS_GENERIC_IMPORT_DIR",
    "CODEX_HOME",
    "AIPPOCAMPUS_VAULT",
    "AIPPOCAMPUS_STYLE_SOURCE",
    "AIPPOCAMPUS_SCRIPT_SOURCE",
    "AIPPOCAMPUS_SITE_MARK",
    "AIPPOCAMPUS_SITE_TITLE",
    "AIPPOCAMPUS_OBJECT_STORE_URL",
    "AIPPOCAMPUS_OBJECT_STORE_TOKEN",
    "AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID",
    "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY",
    "AIPPOCAMPUS_OBJECT_SESSION_TOKEN",
    "AIPPOCAMPUS_AGE_BIN",
    "AIPPOCAMPUS_AGE_KEYGEN_BIN",
    "AIPPOCAMPUS_SEMANTIC_GATE",
    "AIPPOCAMPUS_DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_KEY",
    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
    "LOCAL_OPENAI_COMPAT_API_KEY",
    "AIPPOCAMPUS_PROJECTS_TOKEN",
    "GH_TOKEN",
}

SAFE_ENV_ALLOWED_VALUES = {
    "AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS": "250",
    "AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS": "1000",
    "AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY": "1",
    "AIPPOCAMPUS_SEMANTIC_GATE": "off",
}

SAFE_ENV_DOC_TERMS = {
    ".env.example": "safe environment doc missing .env.example pointer",
    "public-api.md#environment-configuration-matrix": (
        "safe environment doc missing canonical environment matrix pointer"
    ),
    "`plugins/aippocampus/.mcp.json` intentionally has no `env` block": (
        "safe environment doc missing plugin MCP inherited-env boundary"
    ),
    "does not currently ship a Dockerfile": (
        "safe environment doc missing Docker/devcontainer deferral boundary"
    ),
    "smoke_alternate_runtime_sync.py": (
        "safe environment doc missing alternate-runtime smoke substitute"
    ),
    "not a release claim for a maintained container image": (
        "safe environment doc missing container-support overclaim boundary"
    ),
}

HOST_HOOK_BOUNDARY_DOC_TERMS = {
    "docs/architecture/provider-entrypoint-inventory.md": {
        "## Host Integration Matrix": "provider inventory missing host integration matrix",
        "configuration-mutating installers": (
            "provider inventory missing configuration-mutating installer classification"
        ),
        "Claude Code hook support: not yet claimable": (
            "provider inventory missing Claude Code hook not-claimable boundary"
        ),
    },
    "docs/architecture/runtime-script-map.md": {
        "Codex-only hook installer boundary": (
            "runtime script map missing Codex-only hook installer boundary"
        ),
    },
    "docs/guides/claude-code-mcp.md": {
        "AIppocampus does not ship a Claude Code hook installer": (
            "Claude Code MCP guide missing explicit no Claude Code hook installer claim"
        ),
        "official Claude Code hooks contract": (
            "Claude Code MCP guide missing official hook contract follow-up boundary"
        ),
    },
    ".claude/skills/aippocampus/SKILL.md": {
        "AIppocampus does not currently provide a Claude Code hook installer": (
            "Claude Code project skill missing no-hook-installation boundary"
        ),
    },
    "docs/guides/public-api.md": {
        "Provider support is not host hook support": (
            "public API doc missing provider-support-vs-hook-support boundary"
        ),
        "Codex-only hook installers": (
            "public API doc missing Codex-only hook installer boundary"
        ),
    },
}

HOST_HOOK_HELPER_FILES = (
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_prompt.py",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_lifecycle.py",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/diagnose.py",
)

HOST_HOOK_METADATA_TERMS = ("host_boundary", "add_host_integration")

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
    "reviews",
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
            issues.append(f"runtime script map missing high-risk runtime entry: {script}")
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


def current_claims_snapshot_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    snapshot = repo_root / CURRENT_CLAIMS_SNAPSHOT_DOC
    if not snapshot.exists():
        issues.append(f"missing current claims snapshot: {CURRENT_CLAIMS_SNAPSHOT_DOC}")
    else:
        text = snapshot.read_text(encoding="utf-8")
        for term, issue in REQUIRED_CURRENT_CLAIMS_TERMS.items():
            if term not in text:
                issues.append(issue)

    for rel_path, issue in CURRENT_CLAIMS_POINTER_DOCS.items():
        path = repo_root / rel_path
        if path.exists() and CURRENT_CLAIMS_SNAPSHOT_DOC not in path.read_text(encoding="utf-8"):
            issues.append(issue)

    for rel_path, phrases in STALE_CURRENT_EVIDENCE_PHRASES.items():
        path = repo_root / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        normalized_text = " ".join(text.split())
        for phrase, issue in phrases.items():
            if phrase in text or phrase in normalized_text:
                issues.append(issue)

    return issues


def proof_slice_maturity_board_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    board = repo_root / PROOF_SLICE_MATURITY_DOC
    if not board.exists():
        issues.append(f"missing proof-slice maturity board: {PROOF_SLICE_MATURITY_DOC}")
    else:
        text = board.read_text(encoding="utf-8")
        for term, issue in REQUIRED_PROOF_SLICE_MATURITY_TERMS.items():
            if term not in text:
                issues.append(issue)

    for rel_path, issue in PROOF_SLICE_MATURITY_POINTER_DOCS.items():
        path = repo_root / rel_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        docs_relative = PROOF_SLICE_MATURITY_DOC.removeprefix("docs/")
        if path.exists() and PROOF_SLICE_MATURITY_DOC not in text and docs_relative not in text:
            issues.append(issue)
    return issues


def hippocampal_private_annotation_protocol_issues(repo_root: Path) -> list[str]:
    path = repo_root / HIPPOCAMPAL_PRIVATE_ANNOTATION_DOC
    if not path.exists():
        return [
            "missing hippocampal private annotation protocol: "
            f"{HIPPOCAMPAL_PRIVATE_ANNOTATION_DOC}"
        ]

    text = path.read_text(encoding="utf-8")
    lower_text = text.lower()
    issues: list[str] = []
    for term, issue in REQUIRED_HIPPOCAMPAL_PRIVATE_ANNOTATION_TERMS.items():
        if term.lower() not in lower_text:
            issues.append(issue)
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


def public_core_schema_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []
    rel_path = "docs/guides/public-core-boundary.md"
    public_core = repo_root / rel_path
    if not public_core.exists():
        return [f"missing public core schema contract doc: {rel_path}"]

    text = public_core.read_text(encoding="utf-8")
    for term, issue in REQUIRED_PUBLIC_CORE_SCHEMA_CONTRACT_TERMS.items():
        if term not in text:
            issues.append(issue)
    return issues


def python_version_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []

    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        return ["missing pyproject.toml for Python version contract"]
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"cannot parse pyproject.toml for Python version contract: {exc}"]

    project = pyproject.get("project", {})
    requires_python = project.get("requires-python")
    if requires_python != CANONICAL_PYTHON_REQUIRES:
        issues.append(
            "pyproject.toml requires-python must stay "
            f"{CANONICAL_PYTHON_REQUIRES!r}; found {requires_python!r}"
        )

    classifiers = [str(item) for item in project.get("classifiers", [])]
    for version in SUPPORTED_PUBLIC_PYTHON_VERSIONS:
        classifier = f"Programming Language :: Python :: {version}"
        if classifier not in classifiers:
            issues.append(f"pyproject.toml missing Python classifier: {classifier}")
    for version in UNSUPPORTED_PUBLIC_PYTHON_VERSION_CLAIMS:
        classifier = f"Programming Language :: Python :: {version}"
        if classifier in classifiers:
            issues.append(
                "pyproject.toml must not advertise unsupported Python classifier: "
                f"{classifier}"
            )

    tool = pyproject.get("tool", {})
    ruff_target = tool.get("ruff", {}).get("target-version")
    if ruff_target != "py312":
        issues.append(f"ruff target-version must stay 'py312'; found {ruff_target!r}")
    mypy_python_version = tool.get("mypy", {}).get("python_version")
    if mypy_python_version != CANONICAL_PYTHON_FLOOR:
        issues.append(
            "mypy python_version must stay "
            f"{CANONICAL_PYTHON_FLOOR!r}; found {mypy_python_version!r}"
        )

    for rel_path, terms in PYTHON_VERSION_DOC_TERMS.items():
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing Python support contract doc: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for term in terms:
            if term not in text:
                issues.append(f"{rel_path} missing Python support contract term: {term}")
        if re.search(r"supports Python 3\.1[01]\b|Python 3\.1[01] and newer", text):
            issues.append(f"{rel_path} must not advertise Python 3.10/3.11 as supported")

    for rel_path, terms in PYTHON_VERSION_WORKFLOW_TERMS.items():
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing Python support workflow: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for term in terms:
            if term not in text:
                issues.append(f"{rel_path} missing Python support workflow term: {term}")
        for version in UNSUPPORTED_PUBLIC_PYTHON_VERSION_CLAIMS:
            if re.search(rf'["\']{re.escape(version)}["\']', text):
                issues.append(f"{rel_path} must not run unsupported Python {version}")

    return issues


def dependency_contract_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []

    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        return ["missing pyproject.toml for dependency contract"]
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"cannot parse pyproject.toml for dependency contract: {exc}"]

    project = pyproject.get("project", {})
    if project.get("dependencies") != []:
        issues.append("pyproject.toml must declare current runtime dependencies as []")

    optional = project.get("optional-dependencies", {})
    for extra, expected in DEPENDENCY_CONTRACT_REQUIRED_OPTIONAL_EXTRAS.items():
        actual = optional.get(extra)
        if actual != expected:
            issues.append(f"pyproject.toml optional dependency {extra!r} must be {expected!r}")

    build_requires = pyproject.get("build-system", {}).get("requires")
    if build_requires != ["setuptools==82.0.1"]:
        issues.append("pyproject.toml build-system requires must pin setuptools==82.0.1")

    contract = repo_root / "docs" / "guides" / "dependency-contract.md"
    if not contract.exists():
        issues.append("missing dependency contract doc: docs/guides/dependency-contract.md")
    else:
        text = contract.read_text(encoding="utf-8")
        for term, issue in DEPENDENCY_CONTRACT_DOC_TERMS.items():
            if term not in text:
                issues.append(issue)

    docs_readme = repo_root / "docs" / "README.md"
    if docs_readme.exists() and "guides/dependency-contract.md" not in docs_readme.read_text(
        encoding="utf-8"
    ):
        issues.append("docs README missing dependency contract pointer")

    readme = repo_root / "README.md"
    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        if "docs/guides/dependency-contract.md" not in readme_text:
            issues.append("README missing dependency contract pointer")
        if 'python -m pip install -e ".[dev]"' not in readme_text:
            issues.append("README missing dev extra contributor install path")
        if re.search(r"pip install --upgrade pip\s+ruff", readme_text):
            issues.append("README must not use floating Ruff/mypy/coverage install")

    install_guide = repo_root / "docs" / "guides" / "install-guide.md"
    if install_guide.exists():
        install_text = install_guide.read_text(encoding="utf-8")
        if "dependency-contract.md" not in install_text:
            issues.append("install guide missing dependency contract pointer")
        if 'python -m pip install -e ".[dev]"' not in install_text:
            issues.append("install guide missing dev extra contributor install path")
        if re.search(r"pip install --upgrade pip\s+ruff", install_text):
            issues.append("install guide must not use floating Ruff/mypy install")

    release_checklist = repo_root / "docs" / "guides" / "release-checklist.md"
    if release_checklist.exists() and 'python -m pip install -e ".[release]"' not in (
        release_checklist.read_text(encoding="utf-8")
    ):
        issues.append("release checklist missing release extra install path")

    ci_workflow = repo_root / ".github" / "workflows" / "aippocampus-ci.yml"
    if ci_workflow.exists():
        ci_text = ci_workflow.read_text(encoding="utf-8")
        for term in [
            'python -m pip install -e ".[dev]"',
            'python -m pip install -e ".[benchmark]"',
            'python -m pip install -e ".[openai-agents-smoke]"',
            "cache: pip",
            "cache-dependency-path: pyproject.toml",
        ]:
            if term not in ci_text:
                issues.append(f"aippocampus CI missing dependency reproducibility term: {term}")
        if re.search(r"python -m pip install ruff mypy coverage build", ci_text):
            issues.append("aippocampus CI must not use floating dev tool install")

    publish_workflow = repo_root / ".github" / "workflows" / "publish-agent-discovery.yml"
    if publish_workflow.exists():
        publish_text = publish_workflow.read_text(encoding="utf-8")
        for term in [
            'python -m pip install -e ".[release]"',
            "cache: pip",
            "cache-dependency-path: pyproject.toml",
        ]:
            if term not in publish_text:
                issues.append(f"publish workflow missing dependency reproducibility term: {term}")
        if "python -m pip install --upgrade build twine check-jsonschema" in publish_text:
            issues.append("publish workflow must not use floating release tool install")

    coverage_script = repo_root / "tools" / "aippocampus" / "run_coverage.py"
    if coverage_script.exists() and 'python -m pip install -e ".[dev]"' not in (
        coverage_script.read_text(encoding="utf-8")
    ):
        issues.append("run_coverage.py should point missing coverage users to the dev extra")

    return issues


def safe_environment_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []

    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        ignored = {
            line.strip()
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        if ".env" not in ignored or ".env.*" not in ignored or "!.env.example" not in ignored:
            issues.append(".gitignore must ignore private .env files while allowing .env.example")
    else:
        issues.append("missing .gitignore for private .env files")

    env_path = repo_root / ".env.example"
    if not env_path.exists():
        issues.append("missing safe environment template: .env.example")
    else:
        env_text = env_path.read_text(encoding="utf-8")
        if "docs/guides/public-api.md#environment-configuration-matrix" not in env_text:
            issues.append(".env.example missing canonical public API env matrix pointer")
        seen_keys: set[str] = set()
        for line_no, raw_line in enumerate(env_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                issues.append(f".env.example:{line_no} must use KEY=VALUE syntax")
                continue
            key, value = line.split("=", maxsplit=1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            seen_keys.add(key)
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                issues.append(f".env.example:{line_no} has invalid env var name: {key}")
            if value and SAFE_ENV_ALLOWED_VALUES.get(key) != value:
                issues.append(
                    f".env.example:{line_no} must keep {key} blank or use an approved safe value"
                )
            if value and (SECRET_OR_LOCAL_PATH_RE.search(value) or re.search(r"/(?:Users|home)/", value)):
                issues.append(f".env.example:{line_no} contains secret-like or local-path value")
        for key in sorted(SAFE_ENV_REQUIRED_KEYS - seen_keys):
            issues.append(f".env.example missing supported environment variable: {key}")

    safe_doc = repo_root / "docs" / "guides" / "safe-environment.md"
    if not safe_doc.exists():
        issues.append("missing safe environment guide: docs/guides/safe-environment.md")
    else:
        safe_text = safe_doc.read_text(encoding="utf-8")
        for term, issue in SAFE_ENV_DOC_TERMS.items():
            if term not in safe_text:
                issues.append(issue)

    for rel_path, required in {
        "README.md": ["docs/guides/safe-environment.md", ".env.example"],
        "docs/README.md": ["guides/safe-environment.md"],
        "docs/guides/install-guide.md": ["safe-environment.md", ".env.example"],
        "docs/guides/public-api.md": [".env.example"],
        "docs/guides/privacy-security-checklist.md": [".env.example", ".env"],
    }.items():
        path = repo_root / rel_path
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for term in required:
            if term not in text:
                issues.append(f"{rel_path} missing safe environment pointer: {term}")

    mcp_path = repo_root / "plugins" / "aippocampus" / ".mcp.json"
    if mcp_path.exists():
        try:
            mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(f"invalid plugin MCP manifest: {type(exc).__name__}")
            mcp = {}
        for name, server in (mcp.get("mcpServers") or {}).items():
            if isinstance(server, dict) and "env" in server:
                issues.append(
                    "plugin MCP manifest must not include public env block; "
                    f"configure {name} env privately"
                )

    return issues


def host_hook_boundary_issues(repo_root: Path) -> list[str]:
    issues: list[str] = []

    for rel_path, terms in HOST_HOOK_BOUNDARY_DOC_TERMS.items():
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing host hook boundary doc: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for term, issue in terms.items():
            if term not in text:
                issues.append(issue)

    host_boundary = (
        repo_root
        / "skills"
        / "aippocampus"
        / "scripts"
        / "aippocampus_runtime"
        / "hooks"
        / "host_boundary.py"
    )
    if not host_boundary.exists():
        issues.append("missing hook host boundary helper: aippocampus_runtime/hooks/host_boundary.py")
    else:
        text = host_boundary.read_text(encoding="utf-8")
        for term in ('HOOK_HOST = "codex"', 'HOOK_CONFIG_SURFACE = "codex_hooks_json"'):
            if term not in text:
                issues.append(f"hook host boundary helper missing metadata term: {term}")

    for rel_path in HOST_HOOK_HELPER_FILES:
        path = repo_root / rel_path
        if not path.exists():
            issues.append(f"missing hook helper for host metadata: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if any(term not in text for term in HOST_HOOK_METADATA_TERMS):
            issues.append(f"hook helper missing host integration metadata: {rel_path}")

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

    ia_issues, ia_metrics = ia_pressure_guard.docs_health_ia_payload(
        repo_root,
        allowed_root_markdown=DOCS_ROOT_ALLOWED_MARKDOWN,
        allowed_root_directories=DOCS_ROOT_ALLOWED_DIRECTORIES,
    )
    issues.extend(ia_issues)
    metrics.update(ia_metrics)

    origin_stub = repo_root / "docs" / "origin.md"
    if origin_stub.exists():
        issues.append("docs/origin.md duplicates the origin essay; link docs/未干的地图.md instead")

    issues.extend(reader_path_issues(repo_root))
    issues.extend(runtime_script_map_issues(repo_root))
    issues.extend(dream_phase1_contract_issues(repo_root))
    issues.extend(llm_call_contract_issues(repo_root))
    issues.extend(evidence_index_issues(repo_root))
    issues.extend(benchmark_evidence_map_issues(repo_root))
    issues.extend(current_claims_snapshot_issues(repo_root))
    issues.extend(proof_slice_maturity_board_issues(repo_root))
    issues.extend(source_kernel_contract_issues(repo_root))
    issues.extend(hippocampal_private_annotation_protocol_issues(repo_root))
    issues.extend(legacy_alias_inventory_issues(repo_root))
    issues.extend(public_api_contract_issues(repo_root))
    issues.extend(product_profile_contract_issues(repo_root))
    issues.extend(public_core_schema_contract_issues(repo_root))
    issues.extend(public_core_product_profile_issues(repo_root))
    issues.extend(python_version_contract_issues(repo_root))
    issues.extend(development_status_classifier_issues(repo_root))
    issues.extend(dependency_contract_issues(repo_root))
    issues.extend(safe_environment_issues(repo_root))
    issues.extend(host_hook_boundary_issues(repo_root))
    issues.extend(architecture_index_issues(repo_root))

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
    warnings: list[str] = []
    diagnostics: dict[str, Any] = {}

    if not skill_path.exists():
        return {
            "ok": False,
            "issues": [f"missing {skill_path}"],
            "warnings": warnings,
            "diagnostics": diagnostics,
            "metrics": {},
        }

    text = skill_path.read_text(encoding="utf-8")
    flat_text = " ".join(text.split())
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

    metrics["required_skill_continuity_terms"] = len(REQUIRED_SKILL_CONTINUITY_TERMS)
    for phrase, message in REQUIRED_SKILL_CONTINUITY_TERMS.items():
        if phrase not in text and phrase not in flat_text:
            issues.append(message)

    references_dir = root / "references"
    for filename in REQUIRED_REFERENCES:
        ref_path = references_dir / filename
        if not ref_path.exists():
            issues.append(f"missing reference: references/{filename}")
        if filename not in text:
            issues.append(f"SKILL.md does not link references/{filename}")

    if "changelog" in text.lower() and "Do not append changelog-style notes" not in flat_text:
        issues.append("SKILL.md mentions changelog without the stable-entrypoint guardrail")

    repo_root = find_repo_root(root)
    if repo_root:
        for rel_path in REQUIRED_PROJECT_DOCS:
            if not (repo_root / rel_path).exists():
                issues.append(f"missing project doc: {rel_path}")
        repo_issues, repo_metrics = check_repo_docs(repo_root)
        issues.extend(repo_issues)
        warnings.extend(repo_metrics.pop("_warnings", []))
        diagnostics.update(repo_metrics.pop("_diagnostics", {}))
        metrics.update(repo_metrics)
    else:
        metrics["repo_docs_checked"] = False

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "diagnostics": diagnostics,
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
        for warning in result.get("warnings", []):
            print(f"! {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
