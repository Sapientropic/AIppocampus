#!/usr/bin/env python3
"""Compatibility shim for the packaged dream one-sidedness gate."""

from __future__ import annotations

from aippocampus_runtime.dream.one_sidedness import (
    DREAM_FINDING_KIND,
    GATE_KIND,
    OPPOSITE_TRIGRAM,
    SCHEMA_VERSION,
    VOICE_ID,
    build_opposite_hexagram_probe,
    compute_opposite_arc,
    evaluate_one_sidedness_gate,
    main,
    merge_refs,
    normalize_arc,
    normalize_source_refs,
    stable_digest,
)

__all__ = [
    "DREAM_FINDING_KIND",
    "GATE_KIND",
    "OPPOSITE_TRIGRAM",
    "SCHEMA_VERSION",
    "VOICE_ID",
    "build_opposite_hexagram_probe",
    "compute_opposite_arc",
    "evaluate_one_sidedness_gate",
    "main",
    "merge_refs",
    "normalize_arc",
    "normalize_source_refs",
    "stable_digest",
]


if __name__ == "__main__":
    raise SystemExit(main())
