"""Policy gate for APW recall fallback promotion.

This module owns the cheap hot-path decision about whether APW fallback should
run. The heavier fallback card module imports these functions so future APW
lanes can change policy without growing the source-open projection owner.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import associative_path_inputs as apw_inputs
from aippocampus_runtime.recall import recall_recovery_policy

SCHEMA_VERSION = 1
PROMOTION_MODE_ENV = "AIPPOCAMPUS_APW_PROMOTION_MODE"
MODE_SEMI_DEFAULT_RECOVERY = "semi_default_recovery"
MODE_OPT_IN = "opt_in"
MODE_OFF = "off"
VALID_PROMOTION_MODES = {MODE_SEMI_DEFAULT_RECOVERY, MODE_OPT_IN, MODE_OFF}


def _promotion_mode() -> str:
    raw = str(os.environ.get(PROMOTION_MODE_ENV) or MODE_SEMI_DEFAULT_RECOVERY)
    mode = raw.strip().casefold().replace("-", "_")
    aliases = {
        "semi_default": MODE_SEMI_DEFAULT_RECOVERY,
        "semidefault": MODE_SEMI_DEFAULT_RECOVERY,
        "recovery": MODE_SEMI_DEFAULT_RECOVERY,
        "on": MODE_SEMI_DEFAULT_RECOVERY,
        "true": MODE_SEMI_DEFAULT_RECOVERY,
        "1": MODE_SEMI_DEFAULT_RECOVERY,
        "optin": MODE_OPT_IN,
        "explicit": MODE_OPT_IN,
        "false": MODE_OPT_IN,
        "0": MODE_OPT_IN,
        "disabled": MODE_OFF,
    }
    mode = aliases.get(mode, mode)
    return mode if mode in VALID_PROMOTION_MODES else MODE_OPT_IN


def _ordinary_recall_needs_recovery(
    *,
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
) -> bool:
    return recall_recovery_policy.ordinary_recall_needs_recovery(
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        triage_metrics=triage_metrics,
    )


def _ordinary_recall_needs_semidefault_recovery(
    *,
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
) -> bool:
    """Gate default APW recovery to recall that is silent, non-reopenable, or weak.

    APW is still navigation-only and source-gated. The semi-default trigger is
    intentionally limited to the same weak-recall shape that would otherwise
    make compact recall fall back to manual source search, so APW does not
    perturb strong ordinary recall.
    """

    return _ordinary_recall_needs_recovery(
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        triage_metrics=triage_metrics,
    )


def _sidecar_root(cwd: str | Path | None, sidecar_dir: str | Path | None) -> Path:
    if sidecar_dir:
        return Path(sidecar_dir).expanduser().resolve()
    root = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    return root / apw_inputs.DEFAULT_SIDECAR_DIR_NAME


def _path_has_rows(path: str | Path | None) -> bool:
    if path is None:
        return False
    try:
        candidate = Path(path).expanduser().resolve()
    except OSError:
        return False
    if not candidate.is_file():
        return False
    try:
        return bool(candidate.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _root_has_rows(root: Path, filenames: tuple[str, ...]) -> bool:
    return any(_path_has_rows(root / filename) for filename in filenames)


def has_associative_path_candidate_input(
    *,
    query: str = "",
    cwd: str | Path | None = None,
    sidecar_dir: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
    include_registry_sources: bool = False,
) -> bool:
    """Return whether APW has candidate sidecars worth trying by default.

    Semantic bridges and feedback are calibration inputs; by themselves they do
    not create a source-reopenable route. The semi-default path therefore stays
    silent unless a navigation-potential or active-lock candidate source exists.
    Explicit ``--apw-fallback`` still reports an abstention so operators can see
    why no APW route surfaced.
    """

    if _path_has_rows(navigation_path) or _path_has_rows(active_lock_path):
        return True
    root = _sidecar_root(cwd, sidecar_dir)
    if _root_has_rows(root, apw_inputs.NAVIGATION_FILENAMES) or _root_has_rows(
        root,
        apw_inputs.ACTIVE_LOCK_FILENAMES,
    ):
        return True
    if str(query or "").strip():
        if apw_inputs.has_clean_source_candidate_input(
            query=query,
            cwd=cwd,
            clean_source_dir=clean_source_dir,
        ):
            return True
        if include_registry_sources and registry_dir is not None:
            return apw_inputs.has_registry_source_candidate_input(
                query=query,
                cwd=cwd,
                registry_dir=registry_dir,
            )
    return False


def recall_fallback_policy(
    *,
    include_associative_fallback: bool,
    query: str = "",
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
    cwd: str | Path | None = None,
    sidecar_dir: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return compact-safe APW fallback policy diagnostics for recall."""

    mode = _promotion_mode()
    recovery_needed = _ordinary_recall_needs_recovery(
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        triage_metrics=triage_metrics,
    )
    semidefault_recovery_needed = _ordinary_recall_needs_semidefault_recovery(
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        triage_metrics=triage_metrics,
    )
    candidate_input_available = has_associative_path_candidate_input(
        query=query,
        cwd=cwd,
        sidecar_dir=sidecar_dir,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        navigation_path=navigation_path,
        active_lock_path=active_lock_path,
        # Registry-wide exact search is useful for an explicit APW recovery ask,
        # but it is too expensive/noisy to run as a semi-default hot-path probe
        # on every ordinary recall. Keep it behind explicit opt-in.
        include_registry_sources=bool(include_associative_fallback),
    )
    explicit_requested = bool(include_associative_fallback)
    explicit_run = (
        explicit_requested
        and mode != MODE_OFF
        # An explicit APW request is a diagnostic/recovery ask from the
        # foreground agent. If current clean source has APW candidates, run the
        # source-shape gate even when ordinary recall produced a route-shaped
        # packet; the result still does not reorder default recall ranking.
        and (recovery_needed or candidate_input_available)
    )
    semi_default_run = (
        not explicit_requested
        and mode == MODE_SEMI_DEFAULT_RECOVERY
        and semidefault_recovery_needed
        and candidate_input_available
    )
    run_reason = ""
    if explicit_run:
        run_reason = "apw_opt_in_fallback"
    elif semi_default_run:
        run_reason = "apw_semi_default_recovery"
    elif mode == MODE_OFF:
        run_reason = "apw_fallback_policy_off"
    elif not recovery_needed:
        run_reason = "ordinary_recall_not_weak_enough_for_apw_recovery"
    elif not explicit_requested and mode == MODE_OPT_IN:
        run_reason = "apw_fallback_requires_explicit_opt_in"
    elif recovery_needed and not semidefault_recovery_needed:
        run_reason = "apw_recovery_not_semi_default_eligible"
    elif not candidate_input_available:
        run_reason = "apw_candidate_input_missing"
    else:
        run_reason = "apw_fallback_not_run"
    return {
        "kind": "aippocampus_associative_path_recall_policy",
        "schema_version": SCHEMA_VERSION,
        "current_build_posture": mode,
        "promotion_mode": mode,
        "promotion_surface": "secondary_recovery_action_for_no_route_or_weak_recall",
        "promotion_gate": "apw_source_shape_followthrough_gate",
        "explicit_requested": explicit_requested,
        "ordinary_recall_recovery_needed": recovery_needed,
        "semidefault_recovery_needed": semidefault_recovery_needed,
        "apw_candidate_input_available": candidate_input_available,
        "run_fallback": bool(explicit_run or semi_default_run),
        "run_reason": run_reason,
        "opt_in_required_for_this_run": not semi_default_run,
        "applied_to_default_ranking": False,
        "default_ranking_influence_allowed": False,
        "default_mode_allowed": False,
        "rollback_env": f"{PROMOTION_MODE_ENV}={MODE_OPT_IN}",
        "hard_off_env": f"{PROMOTION_MODE_ENV}={MODE_OFF}",
        "rollback_behavior": "opt_in restores pre-promotion recall behavior; off suppresses recall fallback.",
        "source_reopen_required_before_claim": True,
    }


__all__ = [
    "MODE_OFF",
    "MODE_OPT_IN",
    "MODE_SEMI_DEFAULT_RECOVERY",
    "PROMOTION_MODE_ENV",
    "has_associative_path_candidate_input",
    "recall_fallback_policy",
]
