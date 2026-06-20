"""Benchmark suite profile ladder and release-evidence scope metadata."""

from __future__ import annotations

from typing import Any

BASELINE_PROFILE = "baseline"
PUBLIC_FAST_PROFILE = "public-fast"
CI_DETERMINISTIC_PROFILE = "ci-deterministic"
LOCAL_CALIBRATION_PROFILE = "local-calibration"
LIVE_SEMANTIC_PROFILE = "live-semantic"
PRIVATE_FULL_PROFILE = "private-full"
RELEASE_EVIDENCE_PROFILE = "release-evidence"
PROFILE_CHOICES = (
    BASELINE_PROFILE,
    PUBLIC_FAST_PROFILE,
    CI_DETERMINISTIC_PROFILE,
    LOCAL_CALIBRATION_PROFILE,
    LIVE_SEMANTIC_PROFILE,
    PRIVATE_FULL_PROFILE,
    RELEASE_EVIDENCE_PROFILE,
)
PROFILE_DOCS = (
    "docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md"
    "#benchmark-suite-profiles"
)
PROFILE_LADDER: tuple[dict[str, Any], ...] = (
    {
        "name": PUBLIC_FAST_PROFILE,
        "stage": "fresh_clone_public_smoke",
        "runtime_cost": "fast",
        "purpose": "deterministic public A/C/D smoke that should run from a fresh clone",
        "included_tracks": ["gate_decision", "payload_fidelity", "compaction_continuity"],
        "excluded_surfaces": [
            "private_text",
            "live_semantic",
            "track_b_source_evidence",
            "optional_public_corpus_track_b",
        ],
        "privacy_boundary": "public_safe_no_registry_no_live_models",
        "dependencies": ["repository fixtures only"],
        "default_cannot_claim": [
            "public_fast_profile_track_b_quality",
            "public_fast_profile_live_semantic_quality",
            "public_fast_profile_private_real_history_quality",
            "public_fast_profile_large_external_dataset_quality",
        ],
    },
    {
        "name": CI_DETERMINISTIC_PROFILE,
        "stage": "ci_deterministic_baseline",
        "runtime_cost": "medium",
        "purpose": "deterministic CI-oriented baseline with Track B diagnostics",
        "included_tracks": [
            "gate_decision",
            "payload_fidelity",
            "compaction_continuity",
            "source_evidence_retrieval",
            "source_evidence_deterministic_labels",
        ],
        "excluded_surfaces": [
            "private_text",
            "live_semantic",
            "optional_public_corpus_track_b",
        ],
        "privacy_boundary": "sanitized_no_private_text_no_live_models",
        "dependencies": ["local deterministic fixtures and sanitized registry metadata"],
        "default_cannot_claim": [
            "ci_profile_live_semantic_quality",
            "ci_profile_private_real_history_quality",
            "ci_profile_optional_public_corpus_quality",
        ],
    },
    {
        "name": LOCAL_CALIBRATION_PROFILE,
        "stage": "maintainer_local_calibration",
        "runtime_cost": "medium",
        "purpose": "maintainer calibration run with deterministic Track B surfaces enabled",
        "included_tracks": [
            "gate_decision",
            "payload_fidelity",
            "compaction_continuity",
            "source_evidence_retrieval",
            "source_evidence_deterministic_labels",
        ],
        "excluded_surfaces": ["private_text", "live_semantic"],
        "privacy_boundary": "sanitized_local_diagnostics",
        "dependencies": ["local registry or generated sanitized benchmark data"],
        "default_cannot_claim": [
            "local_calibration_profile_live_semantic_quality",
            "local_calibration_profile_private_text_quality",
        ],
    },
    {
        "name": LIVE_SEMANTIC_PROFILE,
        "stage": "optional_live_semantic_calibration",
        "runtime_cost": "slow_or_provider_dependent",
        "purpose": "explicit live semantic-model calibration beside deterministic tracks",
        "included_tracks": [
            "gate_decision",
            "payload_fidelity",
            "compaction_continuity",
            "source_evidence_retrieval",
            "live_semantic_gate",
        ],
        "excluded_surfaces": ["private_text"],
        "privacy_boundary": "sanitized_but_uses_live_model_calls",
        "dependencies": ["configured live semantic provider", "local benchmark corpus"],
        "default_cannot_claim": [
            "live_semantic_profile_private_real_history_quality",
            "all_future_semantic_prompts_correct",
        ],
    },
    {
        "name": PRIVATE_FULL_PROFILE,
        "stage": "maintainer_private_regression",
        "runtime_cost": "slow",
        "purpose": "explicit local private-history regression run for maintainers",
        "included_tracks": [
            "gate_decision",
            "payload_fidelity",
            "compaction_continuity",
            "source_evidence_retrieval",
            "source_evidence_deterministic_labels",
        ],
        "excluded_surfaces": ["public_release_claims_without_sanitization"],
        "privacy_boundary": "may_emit_private_text_when_runner_flags_allow_it",
        "dependencies": ["local private registry", "maintainer-only output handling"],
        "default_cannot_claim": [
            "public_release_evidence_without_sanitized_rerun",
            "model_independent_memory_superiority",
        ],
    },
    {
        "name": RELEASE_EVIDENCE_PROFILE,
        "stage": "public_release_evidence",
        "runtime_cost": "medium_to_slow",
        "purpose": "public-safe release evidence run with explicit claim boundaries",
        "included_tracks": [
            "gate_decision",
            "payload_fidelity",
            "compaction_continuity",
            "source_evidence_retrieval",
            "source_evidence_deterministic_labels",
        ],
        "excluded_surfaces": [
            "private_text",
            "live_semantic",
            "optional_public_corpus_track_b_by_default",
        ],
        "privacy_boundary": "public_safe_sanitized_release_report",
        "dependencies": ["sanitized benchmark inputs", "dated verification ledger"],
        "default_cannot_claim": [
            "release_profile_private_real_history_quality",
            "release_profile_live_semantic_quality_without_live_run",
            "release_profile_optional_public_corpus_quality_without_opt_in",
        ],
    },
    {
        "name": BASELINE_PROFILE,
        "stage": "legacy_default_baseline",
        "runtime_cost": "medium",
        "purpose": "backward-compatible default baseline capture",
        "included_tracks": [
            "gate_decision",
            "payload_fidelity",
            "compaction_continuity",
            "source_evidence_retrieval",
            "source_evidence_deterministic_labels",
        ],
        "excluded_surfaces": ["live_semantic", "private_text_by_default"],
        "privacy_boundary": "sanitized_unless_flags_explicitly_expand_surface",
        "dependencies": ["local deterministic fixtures and current default registry path"],
        "default_cannot_claim": [],
    },
)
PROFILE_METADATA_BY_NAME = {profile["name"]: profile for profile in PROFILE_LADDER}
