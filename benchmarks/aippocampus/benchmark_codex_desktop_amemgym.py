#!/usr/bin/env python3
"""AMemGym-style Codex Desktop memory-arm benchmark.

This runner deliberately does not adapt AMemGym's official ``BaseAgent``. It
transposes AMemGym's useful evaluation shape into the Codex Desktop product
surface: multi-period state changes, later multiple-choice questions, a random
baseline, an oracle upper bound, and per-arm normalized memory scores.

Default output is a deterministic public-safe contract preview. A future live
Desktop run may attach measurements only when the clean-workspace and isolated
Codex-home preflight passes for every arm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
DEFAULT_MODEL_ID = "openai/gpt-4.1-mini"
OFFICIAL_NATIVE_TEMPERATURE = 0.0
KIND = "aippocampus_codex_desktop_amemgym_style_benchmark"

CODEX_NATIVE_ARM = "codex_native_no_aippocampus"
AIPPOCAMPUS_NO_SIDECAR_ARM = "aippocampus_clean_source_no_semantic_sidecar"
AIPPOCAMPUS_SEMANTIC_ARM = "aippocampus_semantic_sidecar"
ARM_ORDER = (
    CODEX_NATIVE_ARM,
    AIPPOCAMPUS_NO_SIDECAR_ARM,
    AIPPOCAMPUS_SEMANTIC_ARM,
)
REQUIRED_AIPPOCAMPUS_LIVE_HOOK_EVENTS = ("sessionStart", "userPromptSubmit", "stop")
REQUIRED_NO_SIDECAR_CACHE_SURFACES = (
    "clean_source",
    "source_index",
    "ambient_route_cache",
)
REQUIRED_SEMANTIC_CACHE_SURFACES = (
    *REQUIRED_NO_SIDECAR_CACHE_SURFACES,
    "semantic_sidecar",
)
PROMPT_HOOK_FOREGROUND_BUDGET_MS = 4300
REQUIRED_ANSWER_CHOICE_STYLE = "personalized_natural_language_recommendation"
REQUIRED_SETUP_EXPOSURE_STYLE = "implicit_natural_session"
REQUIRED_MEASUREMENT_TOPOLOGY = "cross_thread_cold_start"
ALLOWED_SCORING_STATE_POLICIES = frozenset(
    {"per_question_fork_rollback", "restart_from_post_compaction_checkpoint"}
)
TEMPERATURE_CONTROL_CONFIGURED_ZERO = "configured_0.0"
TEMPERATURE_CONTROL_VARIANCE_REPORTED = "unconfigurable_variance_reported"
MIN_TEMPERATURE_VARIANCE_RUNS = 3
ACCEPTED_TEMPERATURE_VERIFIERS = frozenset(
    {
        "codex_app_server_request_log",
        "provider_request_metadata",
        "openrouter_request_metadata",
    }
)

PRIVATE_TEXT_RE = re.compile(
    r"(?i)([a-z]:\\|\\\\|api[_-]?key|bearer\s+|cookie|token|sk-[a-z0-9_-]{12,})"
)


@dataclass(frozen=True)
class DesktopMemoryCase:
    case_id: str
    family: str
    question_kind: str
    answer_choice_style: str
    state_exposure_style: str
    measurement_topology: str
    choice_count: int
    correct_choice: int
    arm_choices: Mapping[str, int]
    expected_evidence_path: Mapping[str, str]
    requires_semantic_bridge: bool = False
    negative_control_kind: str | None = None

    def choice_for_arm(self, arm: str) -> int:
        try:
            return int(self.arm_choices[arm])
        except KeyError as exc:
            raise KeyError(f"case {self.case_id!r} has no choice for arm {arm!r}") from exc


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def fixture_cases() -> list[DesktopMemoryCase]:
    """Public-safe AMemGym-shaped Desktop memory cases.

    The cases encode expected arm behavior instead of raw prompts. Live Desktop
    measurements should use separate local-only fixture prompts and attach only
    hashed case ids plus selected-choice indices to this report shape.
    """

    return [
        DesktopMemoryCase(
            case_id="provider-choice-advice-after-correction",
            family="post_compaction_correction",
            question_kind="personalized_recommendation_after_correction",
            answer_choice_style=REQUIRED_ANSWER_CHOICE_STYLE,
            state_exposure_style=REQUIRED_SETUP_EXPOSURE_STYLE,
            measurement_topology=REQUIRED_MEASUREMENT_TOPOLOGY,
            choice_count=4,
            correct_choice=2,
            arm_choices={
                CODEX_NATIVE_ARM: 1,
                AIPPOCAMPUS_NO_SIDECAR_ARM: 2,
                AIPPOCAMPUS_SEMANTIC_ARM: 2,
            },
            expected_evidence_path={
                CODEX_NATIVE_ARM: "host_summary_lost_correction",
                AIPPOCAMPUS_NO_SIDECAR_ARM: "clean_source_exact_reopen",
                AIPPOCAMPUS_SEMANTIC_ARM: "semantic_route_then_clean_source_reopen",
            },
        ),
        DesktopMemoryCase(
            case_id="paraphrased-preference-advice",
            family="paraphrased_preference_update",
            question_kind="semantic_alias_recommendation",
            answer_choice_style=REQUIRED_ANSWER_CHOICE_STYLE,
            state_exposure_style=REQUIRED_SETUP_EXPOSURE_STYLE,
            measurement_topology=REQUIRED_MEASUREMENT_TOPOLOGY,
            choice_count=4,
            correct_choice=3,
            arm_choices={
                CODEX_NATIVE_ARM: 1,
                AIPPOCAMPUS_NO_SIDECAR_ARM: 2,
                AIPPOCAMPUS_SEMANTIC_ARM: 3,
            },
            expected_evidence_path={
                CODEX_NATIVE_ARM: "current_prompt_guess",
                AIPPOCAMPUS_NO_SIDECAR_ARM: "lexical_query_miss",
                AIPPOCAMPUS_SEMANTIC_ARM: "semantic_alias_to_source_ref",
            },
            requires_semantic_bridge=True,
        ),
        DesktopMemoryCase(
            case_id="workspace-scoped-advice-trap",
            family="same_entity_wrong_scope",
            question_kind="scope_aware_recommendation",
            answer_choice_style=REQUIRED_ANSWER_CHOICE_STYLE,
            state_exposure_style=REQUIRED_SETUP_EXPOSURE_STYLE,
            measurement_topology=REQUIRED_MEASUREMENT_TOPOLOGY,
            choice_count=4,
            correct_choice=4,
            arm_choices={
                CODEX_NATIVE_ARM: 2,
                AIPPOCAMPUS_NO_SIDECAR_ARM: 1,
                AIPPOCAMPUS_SEMANTIC_ARM: 4,
            },
            expected_evidence_path={
                CODEX_NATIVE_ARM: "host_has_no_cross_thread_scope",
                AIPPOCAMPUS_NO_SIDECAR_ARM: "lexical_same_name_trap",
                AIPPOCAMPUS_SEMANTIC_ARM: "workspace_scoped_semantic_route",
            },
            requires_semantic_bridge=True,
            negative_control_kind="same_name_cross_project_memory_should_not_win",
        ),
        DesktopMemoryCase(
            case_id="expired-concern-nonintervention",
            family="expired_memory_suppression",
            question_kind="avoid_stale_personalization_recommendation",
            answer_choice_style=REQUIRED_ANSWER_CHOICE_STYLE,
            state_exposure_style=REQUIRED_SETUP_EXPOSURE_STYLE,
            measurement_topology=REQUIRED_MEASUREMENT_TOPOLOGY,
            choice_count=4,
            correct_choice=1,
            arm_choices={
                CODEX_NATIVE_ARM: 1,
                AIPPOCAMPUS_NO_SIDECAR_ARM: 3,
                AIPPOCAMPUS_SEMANTIC_ARM: 1,
            },
            expected_evidence_path={
                CODEX_NATIVE_ARM: "no_memory_no_unneeded_intervention",
                AIPPOCAMPUS_NO_SIDECAR_ARM: "old_exact_hit_without_expiry_context",
                AIPPOCAMPUS_SEMANTIC_ARM: "semantic_expiry_suppression_then_abstain",
            },
            requires_semantic_bridge=True,
            negative_control_kind="expired_memory_should_not_intervene",
        ),
        DesktopMemoryCase(
            case_id="open-question-next-step-advice",
            family="recurring_question_continuity",
            question_kind="open_question_followup_recommendation",
            answer_choice_style=REQUIRED_ANSWER_CHOICE_STYLE,
            state_exposure_style=REQUIRED_SETUP_EXPOSURE_STYLE,
            measurement_topology=REQUIRED_MEASUREMENT_TOPOLOGY,
            choice_count=4,
            correct_choice=2,
            arm_choices={
                CODEX_NATIVE_ARM: 4,
                AIPPOCAMPUS_NO_SIDECAR_ARM: 2,
                AIPPOCAMPUS_SEMANTIC_ARM: 2,
            },
            expected_evidence_path={
                CODEX_NATIVE_ARM: "host_context_horizon_lost",
                AIPPOCAMPUS_NO_SIDECAR_ARM: "clean_source_question_terms_match",
                AIPPOCAMPUS_SEMANTIC_ARM: "question_sidecar_confirms_same_thread",
            },
        ),
        DesktopMemoryCase(
            case_id="visible-session-advice-positive-control",
            family="host_native_positive_control",
            question_kind="within_thread_recommendation_positive_control",
            answer_choice_style=REQUIRED_ANSWER_CHOICE_STYLE,
            state_exposure_style=REQUIRED_SETUP_EXPOSURE_STYLE,
            measurement_topology=REQUIRED_MEASUREMENT_TOPOLOGY,
            choice_count=4,
            correct_choice=3,
            arm_choices={
                CODEX_NATIVE_ARM: 3,
                AIPPOCAMPUS_NO_SIDECAR_ARM: 3,
                AIPPOCAMPUS_SEMANTIC_ARM: 3,
            },
            expected_evidence_path={
                CODEX_NATIVE_ARM: "host_compaction_summary_kept_state",
                AIPPOCAMPUS_NO_SIDECAR_ARM: "clean_source_exact_reopen",
                AIPPOCAMPUS_SEMANTIC_ARM: "semantic_route_then_clean_source_reopen",
            },
        ),
    ]


def evaluate_case(case: DesktopMemoryCase, arm: str) -> dict[str, Any]:
    selected = case.choice_for_arm(arm)
    return {
        "case_id_sha1": sha1_text(case.case_id)[:16],
        "case_family": case.family,
        "question_kind": case.question_kind,
        "answer_choice_style": case.answer_choice_style,
        "state_exposure_style": case.state_exposure_style,
        "measurement_topology": case.measurement_topology,
        "arm": arm,
        "selected_choice": selected,
        "choice_count": case.choice_count,
        "correct": selected == case.correct_choice,
        "answer_choice_sha1": sha1_text(f"{case.case_id}:{selected}")[:16],
        "evidence_path": case.expected_evidence_path.get(arm),
        "requires_semantic_bridge": bool(case.requires_semantic_bridge),
        "negative_control_kind": case.negative_control_kind,
    }


def mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def normalized_against_random(accuracy: float, random_accuracy: float) -> float | None:
    denominator = 1.0 - random_accuracy
    if abs(denominator) < 1e-12:
        return None
    return round((accuracy - random_accuracy) / denominator, 6)


def safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def summarize_rows(rows: list[dict[str, Any]], cases: Sequence[DesktopMemoryCase]) -> dict[str, Any]:
    random_accuracy = mean([1.0 / case.choice_count for case in cases])
    by_arm: dict[str, dict[str, Any]] = {}
    for arm in ARM_ORDER:
        arm_rows = [row for row in rows if row["arm"] == arm]
        correct = sum(1 for row in arm_rows if row["correct"])
        accuracy = mean([1.0 if row["correct"] else 0.0 for row in arm_rows])
        semantic_cases = [row for row in arm_rows if row["requires_semantic_bridge"]]
        negative_cases = [row for row in arm_rows if row["negative_control_kind"]]
        by_arm[arm] = {
            "case_count": len(arm_rows),
            "correct_count": correct,
            "accuracy": accuracy,
            "normalized_memory_score": normalized_against_random(accuracy, random_accuracy),
            "semantic_bridge_case_accuracy": mean(
                [1.0 if row["correct"] else 0.0 for row in semantic_cases]
            )
            if semantic_cases
            else None,
            "negative_control_accuracy": mean(
                [1.0 if row["correct"] else 0.0 for row in negative_cases]
            )
            if negative_cases
            else None,
        }
    return {
        "case_count": len(cases),
        "arm_count": len(ARM_ORDER),
        "random_choice_baseline_accuracy": random_accuracy,
        "oracle_upper_bound_accuracy": 1.0,
        "normalized_formula": "(arm_accuracy - random_choice_baseline) / (oracle_upper_bound - random_choice_baseline)",
        "by_arm": by_arm,
        "deltas": {
            "aippocampus_no_sidecar_lift_over_codex_native": round(
                by_arm[AIPPOCAMPUS_NO_SIDECAR_ARM]["accuracy"]
                - by_arm[CODEX_NATIVE_ARM]["accuracy"],
                6,
            ),
            "semantic_sidecar_lift_over_no_sidecar": round(
                by_arm[AIPPOCAMPUS_SEMANTIC_ARM]["accuracy"]
                - by_arm[AIPPOCAMPUS_NO_SIDECAR_ARM]["accuracy"],
                6,
            ),
            "semantic_sidecar_lift_over_codex_native": round(
                by_arm[AIPPOCAMPUS_SEMANTIC_ARM]["accuracy"]
                - by_arm[CODEX_NATIVE_ARM]["accuracy"],
                6,
            ),
        },
    }


def validate_desktop_environment(arm: str, environment: Mapping[str, Any] | None) -> dict[str, Any]:
    env = dict(environment or {})
    blockers: list[str] = []
    model_id = str(env.get("model_id") or "")
    if model_id != DEFAULT_MODEL_ID:
        blockers.append("model_id_mismatch")
    answer_choice_style = str(env.get("answer_choice_style") or "")
    if answer_choice_style != REQUIRED_ANSWER_CHOICE_STYLE:
        blockers.append("answer_choices_not_personalized_natural_language")
    if env.get("raw_state_answer_options_present") is not False:
        blockers.append("raw_state_answer_options_present")
    setup_exposure_style = str(env.get("setup_exposure_style") or "")
    if setup_exposure_style != REQUIRED_SETUP_EXPOSURE_STYLE:
        blockers.append("setup_not_implicit_natural_session")
    if env.get("explicit_state_bullets_present") is not False:
        blockers.append("explicit_state_update_bullets_present")
    if env.get("raw_state_labels_exposed") is not False:
        blockers.append("raw_state_labels_exposed")
    measurement_topology = str(env.get("measurement_topology") or "")
    if measurement_topology != REQUIRED_MEASUREMENT_TOPOLOGY:
        blockers.append("measurement_not_cross_thread_cold_start")
    setup_thread_id_sha1 = str(env.get("setup_thread_id_sha1") or "")
    scoring_thread_id_sha1 = str(env.get("scoring_thread_id_sha1") or "")
    if not setup_thread_id_sha1 or not scoring_thread_id_sha1:
        blockers.append("setup_or_scoring_thread_hash_missing")
    elif setup_thread_id_sha1 == scoring_thread_id_sha1:
        blockers.append("setup_and_scoring_thread_not_separate")
    if env.get("setup_context_visible_to_scoring_thread") is not False:
        blockers.append("setup_context_visible_to_scoring_thread")
    if env.get("native_context_window_contains_setup_history") is not False:
        blockers.append("native_context_window_contains_setup_history")
    scoring_state_policy = str(env.get("scoring_state_policy") or "")
    if scoring_state_policy not in ALLOWED_SCORING_STATE_POLICIES:
        blockers.append("scored_turn_state_isolation_missing")
    if env.get("scored_turn_writes_discarded") is not True:
        blockers.append("scored_turn_writes_not_discarded")
    if env.get("scoring_from_same_post_compaction_checkpoint") is not True:
        blockers.append("scoring_not_restarted_from_same_checkpoint")
    scoring_checkpoint_id_sha1 = str(env.get("scoring_checkpoint_id_sha1") or "")
    if not scoring_checkpoint_id_sha1:
        blockers.append("scoring_checkpoint_hash_missing")

    temperature_control = str(env.get("temperature_control") or "")
    temperature_value = safe_float(env.get("temperature"))
    temperature_verified_by = str(env.get("temperature_verified_by") or "")
    variance_run_count = safe_int(env.get("temperature_variance_run_count")) or 0
    if temperature_control == TEMPERATURE_CONTROL_CONFIGURED_ZERO:
        if temperature_value != OFFICIAL_NATIVE_TEMPERATURE:
            blockers.append("temperature_not_configured_zero")
        if temperature_verified_by not in ACCEPTED_TEMPERATURE_VERIFIERS:
            blockers.append("temperature_not_request_verified")
    elif temperature_control == TEMPERATURE_CONTROL_VARIANCE_REPORTED:
        if env.get("temperature_configurable") is not False:
            blockers.append("temperature_unconfigurable_not_verified")
        if variance_run_count < MIN_TEMPERATURE_VARIANCE_RUNS:
            blockers.append("temperature_variance_reruns_missing")
        if env.get("temperature_variance_reported") is not True:
            blockers.append("temperature_variance_report_missing")
    else:
        blockers.append("temperature_control_unverified")

    if env.get("workspace_dirty") is not False:
        blockers.append("workspace_not_confirmed_clean")
    if env.get("isolated_codex_home") is not True:
        blockers.append("codex_home_not_isolated")
    if env.get("project_rules_loaded") not in (False, None):
        blockers.append("project_rules_loaded")
    if env.get("loaded_plugin_names") not in ([], None):
        blockers.append("unexpected_plugins_loaded")
    if env.get("loaded_skill_names_verified_by") != "codex_app_server_skills_list":
        blockers.append("loaded_skill_names_not_host_verified")
    if env.get("skills_list_force_reloaded") is not True:
        blockers.append("skills_list_not_force_reloaded")
    skill_catalog_errors = list(env.get("skill_catalog_errors") or [])
    if skill_catalog_errors:
        blockers.append("skill_catalog_errors_present")

    loaded_skills = sorted(str(name) for name in env.get("loaded_skill_names") or [])
    observed_hook_events = sorted(str(name) for name in env.get("observed_hook_events") or [])
    trusted_hook_events = sorted(str(name) for name in env.get("trusted_hook_events") or [])
    hook_trust_status_by_event = {
        str(name): str(status)
        for name, status in (env.get("hook_trust_status_by_event") or {}).items()
    }
    trusted_event_set = set(trusted_hook_events)
    trusted_event_set.update(
        name for name, status in hook_trust_status_by_event.items() if status == "trusted"
    )
    observed_event_set = set(observed_hook_events)
    hook_duration_ms_by_event = {
        str(name): int(duration)
        for name, duration in (env.get("hook_duration_ms_by_event") or {}).items()
        if isinstance(duration, int) and not isinstance(duration, bool)
    }
    hook_completed_status_by_event = {
        str(name): str(status)
        for name, status in (env.get("hook_completed_status_by_event") or {}).items()
    }
    prepared_cache_surfaces = sorted(str(name) for name in env.get("prepared_cache_surfaces") or [])
    required_cache_surfaces: list[str] = []
    if arm == CODEX_NATIVE_ARM:
        allowed_skills: list[str] = []
        if loaded_skills:
            blockers.append("native_arm_loaded_skills")
        if env.get("aippocampus_enabled") not in (False, None):
            blockers.append("native_arm_aippocampus_enabled")
        if env.get("aippocampus_hooks_installed") not in (False, None):
            blockers.append("native_arm_aippocampus_hooks_installed")
        if observed_hook_events:
            blockers.append("native_arm_hook_notifications_observed")
        if trusted_event_set:
            blockers.append("native_arm_trusted_hooks_present")
    else:
        allowed_skills = ["aippocampus"]
        required_cache_surfaces = list(
            REQUIRED_SEMANTIC_CACHE_SURFACES
            if arm == AIPPOCAMPUS_SEMANTIC_ARM
            else REQUIRED_NO_SIDECAR_CACHE_SURFACES
        )
        if loaded_skills != allowed_skills:
            blockers.append("aippocampus_arm_loaded_unexpected_skills")
        if env.get("aippocampus_enabled") is not True:
            blockers.append("aippocampus_arm_disabled")
        if env.get("aippocampus_hooks_installed") is not True:
            blockers.append("aippocampus_hooks_not_installed")
        required_hook_events = set(REQUIRED_AIPPOCAMPUS_LIVE_HOOK_EVENTS)
        if env.get("aippocampus_hooks_trusted") is not True and not required_hook_events.issubset(
            trusted_event_set
        ):
            blockers.append("aippocampus_hooks_not_trusted")
        if not required_hook_events.issubset(observed_event_set):
            blockers.append("aippocampus_hook_notifications_missing")
        if env.get("cache_preparation_completed") is not True:
            blockers.append("cache_preparation_not_completed")
        if not set(required_cache_surfaces).issubset(set(prepared_cache_surfaces)):
            blockers.append("cache_preparation_missing_required_surfaces")
        if env.get("measured_after_cache_warmup") is not True:
            blockers.append("measured_before_cache_warmup")
        prompt_hook_status = hook_completed_status_by_event.get("userPromptSubmit")
        if prompt_hook_status and prompt_hook_status != "completed":
            blockers.append("user_prompt_submit_hook_not_completed")
        prompt_hook_duration = hook_duration_ms_by_event.get("userPromptSubmit")
        if prompt_hook_duration is None:
            blockers.append("user_prompt_submit_hook_latency_missing")
        elif prompt_hook_duration > PROMPT_HOOK_FOREGROUND_BUDGET_MS:
            blockers.append("user_prompt_submit_hook_exceeded_foreground_budget")
        if env.get("foreground_hook_timeout_observed") is True:
            blockers.append("foreground_hook_timeout_observed")

    semantic_enabled = bool(env.get("semantic_sidecar_enabled"))
    if arm == AIPPOCAMPUS_NO_SIDECAR_ARM and semantic_enabled:
        blockers.append("no_sidecar_arm_semantic_sidecar_enabled")
    if arm == AIPPOCAMPUS_SEMANTIC_ARM and not semantic_enabled:
        blockers.append("semantic_sidecar_arm_disabled")

    return {
        "arm": arm,
        "claimable": not blockers,
        "blockers": blockers,
        "expected_loaded_skill_names": allowed_skills,
        "observed_loaded_skill_names": loaded_skills,
        "loaded_skill_names_verified_by": env.get("loaded_skill_names_verified_by"),
        "skills_list_force_reloaded": env.get("skills_list_force_reloaded"),
        "skill_catalog_error_count": len(skill_catalog_errors),
        "model_id": model_id or None,
        "answer_choice_style": answer_choice_style or None,
        "raw_state_answer_options_present": env.get("raw_state_answer_options_present"),
        "setup_exposure_style": setup_exposure_style or None,
        "explicit_state_bullets_present": env.get("explicit_state_bullets_present"),
        "raw_state_labels_exposed": env.get("raw_state_labels_exposed"),
        "measurement_topology": measurement_topology or None,
        "setup_thread_id_sha1": setup_thread_id_sha1 or None,
        "scoring_thread_id_sha1": scoring_thread_id_sha1 or None,
        "setup_context_visible_to_scoring_thread": env.get("setup_context_visible_to_scoring_thread"),
        "native_context_window_contains_setup_history": env.get(
            "native_context_window_contains_setup_history"
        ),
        "scoring_state_policy": scoring_state_policy or None,
        "scored_turn_writes_discarded": env.get("scored_turn_writes_discarded"),
        "scoring_from_same_post_compaction_checkpoint": env.get(
            "scoring_from_same_post_compaction_checkpoint"
        ),
        "scoring_checkpoint_id_sha1": scoring_checkpoint_id_sha1 or None,
        "temperature_control": temperature_control or None,
        "temperature": temperature_value,
        "temperature_verified_by": temperature_verified_by or None,
        "temperature_configurable": env.get("temperature_configurable"),
        "temperature_variance_run_count": variance_run_count,
        "temperature_variance_reported": env.get("temperature_variance_reported"),
        "temperature_same_param_as_official_native": (
            temperature_control == TEMPERATURE_CONTROL_CONFIGURED_ZERO
            and temperature_value == OFFICIAL_NATIVE_TEMPERATURE
        ),
        "workspace_dirty": env.get("workspace_dirty"),
        "isolated_codex_home": env.get("isolated_codex_home"),
        "semantic_sidecar_enabled": env.get("semantic_sidecar_enabled"),
        "aippocampus_hooks_installed": env.get("aippocampus_hooks_installed"),
        "aippocampus_hooks_trusted": env.get("aippocampus_hooks_trusted"),
        "required_aippocampus_hook_events": list(REQUIRED_AIPPOCAMPUS_LIVE_HOOK_EVENTS)
        if arm != CODEX_NATIVE_ARM
        else [],
        "observed_hook_events": observed_hook_events,
        "trusted_hook_events": sorted(trusted_event_set),
        "cache_preparation_completed": env.get("cache_preparation_completed"),
        "measured_after_cache_warmup": env.get("measured_after_cache_warmup"),
        "required_cache_surfaces": required_cache_surfaces,
        "prepared_cache_surfaces": prepared_cache_surfaces,
        "hook_duration_ms_by_event": hook_duration_ms_by_event,
        "hook_completed_status_by_event": hook_completed_status_by_event,
        "prompt_hook_foreground_budget_ms": PROMPT_HOOK_FOREGROUND_BUDGET_MS
        if arm != CODEX_NATIVE_ARM
        else None,
        "foreground_hook_timeout_observed": env.get("foreground_hook_timeout_observed"),
    }


def validate_live_environments(
    live_environment_by_arm: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    if live_environment_by_arm is None:
        return {
            "status": "not_run",
            "all_arms_claimable": False,
            "temperature_comparability": "not_measured",
            "by_arm": {
                arm: {
                    "arm": arm,
                    "claimable": False,
                    "blockers": ["live_environment_missing"],
                    "expected_loaded_skill_names": []
                    if arm == CODEX_NATIVE_ARM
                    else ["aippocampus"],
                    "observed_loaded_skill_names": None,
                    "loaded_skill_names_verified_by": None,
                    "skills_list_force_reloaded": None,
                    "skill_catalog_error_count": None,
                    "model_id": None,
                    "answer_choice_style": None,
                    "raw_state_answer_options_present": None,
                    "setup_exposure_style": None,
                    "explicit_state_bullets_present": None,
                    "raw_state_labels_exposed": None,
                    "measurement_topology": None,
                    "setup_thread_id_sha1": None,
                    "scoring_thread_id_sha1": None,
                    "setup_context_visible_to_scoring_thread": None,
                    "native_context_window_contains_setup_history": None,
                    "scoring_state_policy": None,
                    "scored_turn_writes_discarded": None,
                    "scoring_from_same_post_compaction_checkpoint": None,
                    "scoring_checkpoint_id_sha1": None,
                    "temperature_control": None,
                    "temperature": None,
                    "temperature_verified_by": None,
                    "temperature_configurable": None,
                    "temperature_variance_run_count": None,
                    "temperature_variance_reported": None,
                    "temperature_same_param_as_official_native": None,
                    "workspace_dirty": None,
                    "isolated_codex_home": None,
                    "semantic_sidecar_enabled": None,
                    "aippocampus_hooks_installed": None,
                    "aippocampus_hooks_trusted": None,
                    "required_aippocampus_hook_events": []
                    if arm == CODEX_NATIVE_ARM
                    else list(REQUIRED_AIPPOCAMPUS_LIVE_HOOK_EVENTS),
                    "observed_hook_events": None,
                    "trusted_hook_events": None,
                    "cache_preparation_completed": None,
                    "measured_after_cache_warmup": None,
                    "required_cache_surfaces": []
                    if arm == CODEX_NATIVE_ARM
                    else list(
                        REQUIRED_SEMANTIC_CACHE_SURFACES
                        if arm == AIPPOCAMPUS_SEMANTIC_ARM
                        else REQUIRED_NO_SIDECAR_CACHE_SURFACES
                    ),
                    "prepared_cache_surfaces": None,
                    "hook_duration_ms_by_event": None,
                    "hook_completed_status_by_event": None,
                    "prompt_hook_foreground_budget_ms": None
                    if arm == CODEX_NATIVE_ARM
                    else PROMPT_HOOK_FOREGROUND_BUDGET_MS,
                    "foreground_hook_timeout_observed": None,
                }
                for arm in ARM_ORDER
            },
        }
    validations = [
        validate_desktop_environment(arm, (live_environment_by_arm or {}).get(arm))
        for arm in ARM_ORDER
    ]
    temperature_controls = {str(item.get("temperature_control") or "") for item in validations}
    if temperature_controls == {TEMPERATURE_CONTROL_CONFIGURED_ZERO}:
        temperature_comparability = "official_native_temperature_matched"
    elif temperature_controls <= {
        TEMPERATURE_CONTROL_CONFIGURED_ZERO,
        TEMPERATURE_CONTROL_VARIANCE_REPORTED,
    } and TEMPERATURE_CONTROL_VARIANCE_REPORTED in temperature_controls:
        temperature_comparability = "variance_bounded_not_official_same_param"
    else:
        temperature_comparability = "temperature_unverified"
    return {
        "status": "validated" if all(item["claimable"] for item in validations) else "not_claimable",
        "all_arms_claimable": all(item["claimable"] for item in validations),
        "temperature_comparability": temperature_comparability,
        "by_arm": {item["arm"]: item for item in validations},
    }


def desktop_live_protocol() -> dict[str, Any]:
    return {
        "host_surface": "codex_desktop_app_server_or_equivalent_desktop_thread_host",
        "model_id": DEFAULT_MODEL_ID,
        "target_temperature": OFFICIAL_NATIVE_TEMPERATURE,
        "amemgym_official_base_agent_adapter": False,
        "evaluation_shape": [
            "create synthetic public-safe multi-period memory state through natural implicit setup sessions, not explicit state bullets",
            "run non-scored cache preparation before measured questions",
            "run one non-scored warmup turn and require foreground hook completion inside budget",
            "start measured scoring from a separate cold Desktop thread with setup context hidden from the model context",
            "answer each scored question from a fork/rollback or the same post-compaction checkpoint so one answer cannot leak into later questions",
            "ask multiple-choice personalized natural-language recommendation questions, not raw route codes or state-key recall",
            "compare Codex native, AIppocampus clean-source-only, and AIppocampus semantic-sidecar arms",
        ],
        "clean_environment_requirements": {
            "workspace": "disposable clean workspace; no project AGENTS.md or user rules loaded",
            "codex_home": "isolated temporary Codex home or equivalent verified empty plugin/skill surface",
            "native_arm_loaded_skill_names": [],
            "aippocampus_arm_loaded_skill_names": ["aippocampus"],
            "loaded_skill_names_source": "Codex app-server skills/list with forceReload=true immediately before measured turns",
            "skill_catalog_errors": "must be empty; parse errors in unrelated global skills make the run not claimable",
            "aippocampus_arm_hooks": "installed, trusted by Codex hooks.state, and observed for sessionStart/userPromptSubmit/stop",
            "native_arm_hooks": "no AIppocampus hooks installed, trusted, or observed",
            "aippocampus_precache": "clean-source/index/route-cache preparation completes before scoring; semantic arm also materializes semantic sidecar",
            "aippocampus_warmup": f"non-scored userPromptSubmit warmup completes under {PROMPT_HOOK_FOREGROUND_BUDGET_MS} ms before measured questions",
            "no_other_plugins": True,
        },
        "measurement_boundary": {
            "answer_choice_style": REQUIRED_ANSWER_CHOICE_STYLE,
            "setup_exposure_style": REQUIRED_SETUP_EXPOSURE_STYLE,
            "measurement_topology": REQUIRED_MEASUREMENT_TOPOLOGY,
            "native_context_window_contains_setup_history": False,
            "allowed_scoring_state_policies": sorted(ALLOWED_SCORING_STATE_POLICIES),
            "scored_turn_writes_discarded": True,
            "scoring_from_same_post_compaction_checkpoint": True,
            "temperature_control": [
                {
                    "mode": TEMPERATURE_CONTROL_CONFIGURED_ZERO,
                    "claim": "matched to official Native temperature 0.0",
                },
                {
                    "mode": TEMPERATURE_CONTROL_VARIANCE_REPORTED,
                    "claim": (
                        "Codex Desktop temperature is not fully same-parameter; "
                        f"report at least {MIN_TEMPERATURE_VARIANCE_RUNS} reruns and variance"
                    ),
                },
            ],
            "pre_score_costs_recorded_separately": [
                "clean_source_rebuild",
                "source_index_refresh",
                "ambient_route_cache_refresh",
                "semantic_sidecar_materialization",
                "non_scored_hook_warmup_turn",
            ],
            "scored_turn_requirement": "consume prepared hot-path artifacts; do not cold-build indexes or run cold semantic sidecar inside the foreground hook",
            "foreground_hook_budget_ms": PROMPT_HOOK_FOREGROUND_BUDGET_MS,
        },
        "privacy_boundary": {
            "public_report_raw_prompts": False,
            "public_report_raw_model_outputs": False,
            "public_report_local_paths": False,
            "public_report_provider_auth_material": False,
        },
    }


def assert_public_text(encoded: str) -> None:
    if PRIVATE_TEXT_RE.search(encoded):
        raise ValueError("public report contains private-looking text")


def assert_public_safe(payload: Mapping[str, Any]) -> None:
    assert_public_text(json.dumps(payload, ensure_ascii=False))


def encode_public_json(payload: Mapping[str, Any], *, indent: int | None = None) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, indent=indent)
    assert_public_text(encoded)
    return encoded


def write_public_stdout(text: str) -> None:
    assert_public_text(text)
    # CLI benchmark output is intentionally public and is rejected above when it
    # contains private-looking material; CodeQL cannot infer this local sanitizer.
    # codeql[py/clear-text-logging-sensitive-data]
    sys.stdout.write(text)


def run_benchmark(
    *,
    live_environment_by_arm: Mapping[str, Mapping[str, Any]] | None = None,
    model_id: str = DEFAULT_MODEL_ID,
) -> dict[str, Any]:
    started = time.perf_counter()
    cases = fixture_cases()
    rows = [evaluate_case(case, arm) for case in cases for arm in ARM_ORDER]
    metrics = summarize_rows(rows, cases)
    live_environment = validate_live_environments(live_environment_by_arm)
    live_claimable = bool(live_environment_by_arm) and live_environment["all_arms_claimable"]
    payload: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc(),
        "status": "live_desktop_evidence_ready" if live_claimable else "contract_preview_live_desktop_not_run",
        "ok": True,
        "arms": list(ARM_ORDER),
        "config": {
            "model_id": model_id,
            "target_temperature": OFFICIAL_NATIVE_TEMPERATURE,
            "uses_official_amemgym_base_agent": False,
            "uses_live_desktop_host": bool(live_environment_by_arm),
            "uses_private_history": False,
            "public_safe_synthetic_cases": True,
            "default_suite_member": False,
            "answer_choice_style": REQUIRED_ANSWER_CHOICE_STYLE,
            "setup_exposure_style": REQUIRED_SETUP_EXPOSURE_STYLE,
            "measurement_topology": REQUIRED_MEASUREMENT_TOPOLOGY,
        },
        "metrics": metrics,
        "rows": rows,
        "desktop_live_protocol": desktop_live_protocol(),
        "desktop_live_environment": live_environment,
        "claim_boundary": {
            "score_layer": "live_desktop_evidence" if live_claimable else "contract_preview_only",
            "codex_native_baseline": "claimable" if live_claimable else "not_measured_live",
            "aippocampus_no_sidecar": "claimable" if live_claimable else "not_measured_live",
            "aippocampus_semantic_sidecar": "claimable" if live_claimable else "not_measured_live",
            "scored_turn_state_isolation": "claimable" if live_claimable else "not_verified_live",
            "natural_recommendation_choices": REQUIRED_ANSWER_CHOICE_STYLE,
            "implicit_state_exposure": REQUIRED_SETUP_EXPOSURE_STYLE,
            "cross_thread_cold_start": REQUIRED_MEASUREMENT_TOPOLOGY,
            "temperature_comparability": live_environment["temperature_comparability"],
        },
        "privacy_boundary": {
            "raw_case_prompts_in_report": False,
            "raw_model_outputs_in_report": False,
            "absolute_paths_in_report": False,
            "provider_auth_material_in_report": False,
            "case_ids_are_hashed": True,
            "output_shape": "public_safe_desktop_memory_arm_scores_and_environment_claim_gates",
        },
        "interpretation_notes": [
            "This is an AMemGym-style Codex Desktop benchmark, not an official AMemGym runner.",
            "Random and oracle controls are used only for normalization; the user-facing comparison is the three Desktop arms.",
            "Scored Desktop turns must discard answer writes through fork/rollback or checkpoint restart, matching AMemGym answer_question non-mutation.",
            "Questions must choose the best personalized natural-language recommendation from candidate answers, not repeat a raw state slot.",
            "Setup state must be exposed implicitly through natural sessions, not as explicit key-value bullets.",
            "Native Desktop baseline is tested from a cold scoring thread with setup context hidden; otherwise same-thread host context can dominate the result.",
            "Semantic sidecar output is navigation until clean source is reopened; it is not source truth.",
            "Live Desktop scores are not claimable unless every arm proves clean workspace, isolated Codex home, expected loaded skills, and the required AIppocampus hook trust/notification state.",
            "Loaded skills must be observed from Codex app-server skills/list with forceReload=true; manual declarations do not make a run claimable.",
            "AIppocampus live scores must be measured after non-scored cache preparation and warmup; cold-start timeout behavior is a separate readiness metric.",
            "If Codex Desktop temperature cannot be fixed to 0.0, report the run as variance-bounded rather than official same-parameter.",
        ],
        "cannot_claim": [
            "official AMemGym score or leaderboard compatibility",
            "AIppocampus beats Codex native Desktop behavior before isolated live Desktop run",
            "Desktop score from questions that write back into later scored turns",
            "Desktop score from raw state-key or memory-recitation questions",
            "Desktop score from explicit bullet-list state setup",
            "Desktop score from same-thread native context with setup history visible",
            "official Native temperature parity unless temperature 0.0 is request-verified",
            "semantic sidecar facts without clean-source reopen",
            "AIppocampus memory quality from a run where foreground hooks cold-built cache or timed out",
            "real private-history generality",
            "provider billing or latency from deterministic contract preview",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    assert_public_safe(payload)
    return payload


def print_human_summary(payload: Mapping[str, Any]) -> None:
    lines = ["AIppocampus Codex Desktop AMemGym-style benchmark"]
    lines.append(f"status: {payload['status']}")
    metrics = payload["metrics"]
    lines.append(f"cases: {metrics['case_count']} arms: {metrics['arm_count']}")
    for arm in ARM_ORDER:
        arm_metrics = metrics["by_arm"][arm]
        lines.append(
            f"- {arm}: accuracy={arm_metrics['accuracy']} "
            f"normalized={arm_metrics['normalized_memory_score']}"
        )
    lines.append(f"score layer: {payload['claim_boundary']['score_layer']}")
    write_public_stdout("\n".join(lines) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = run_benchmark(model_id=args.model)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            encode_public_json(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        write_public_stdout(encode_public_json(payload, indent=2) + "\n")
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
