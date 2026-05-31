#!/usr/bin/env python3
"""Compatibility shim for the packaged coding ticket host contract."""

from __future__ import annotations

from aippocampus_runtime.coding.host_contract import (
    CONTRACT_KIND,
    CORE_AI_FIELDS,
    DECISION_KIND,
    FEEDBACK_OUTCOMES,
    HOST_DECISION_FIELDS,
    HOST_RUNTIME_INPUTS,
    REQUIRED_AI_FIELDS,
    SAFE_THIN_SOURCE_USES,
    SCHEMA_VERSION,
    TICKET_KIND,
    TUNING_KIND,
    VISIBILITIES,
    describe_host_contract,
    host_decision_for_ticket,
    main,
    normalize_ticket,
    simulate_host_consumption,
    tune_activation_from_feedback,
    validate_ticket_contract,
)

__all__ = [
    "CONTRACT_KIND",
    "CORE_AI_FIELDS",
    "DECISION_KIND",
    "FEEDBACK_OUTCOMES",
    "HOST_DECISION_FIELDS",
    "HOST_RUNTIME_INPUTS",
    "REQUIRED_AI_FIELDS",
    "SAFE_THIN_SOURCE_USES",
    "SCHEMA_VERSION",
    "TICKET_KIND",
    "TUNING_KIND",
    "VISIBILITIES",
    "describe_host_contract",
    "host_decision_for_ticket",
    "main",
    "normalize_ticket",
    "simulate_host_consumption",
    "tune_activation_from_feedback",
    "validate_ticket_contract",
]


if __name__ == "__main__":
    raise SystemExit(main())
