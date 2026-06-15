"""Deterministic 64x64 hexagram transition taxonomy.

This module labels transitions with existing structural reducers only. It does
not import Yi Lin poems, line texts, classical judgments, source/user data, or
route advice.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.macro import hexagram, transform_orbit
from aippocampus_runtime.macro.perturbation import (
    AUTHORITY_LEVEL,
    CLAIM_PERMISSION,
    changed_line_layer_diagnostics,
)


def _append(labels: list[str], label: str) -> None:
    if label and label not in labels:
        labels.append(label)


def transition_taxonomy(
    source: hexagram.HexagramRef,
    target: hexagram.HexagramRef,
) -> dict[str, Any]:
    left = hexagram.resolve_hexagram(source)
    right = hexagram.resolve_hexagram(target)
    changed = hexagram.changed_lines(left, right)
    distance = len(changed)
    band = hexagram.perturbation_band(distance)
    pair = hexagram.king_wen_pair_relation(left)
    raw_mate = pair.get("pair_mate")
    mate: Mapping[str, Any] = raw_mate if isinstance(raw_mate, Mapping) else {}
    orbit_relation = transform_orbit.relation_label(left, right)
    layer_diagnostics = changed_line_layer_diagnostics(changed)
    raw_layer_counts = layer_diagnostics.get("changed_layer_counts")
    changed_layer_counts: Mapping[str, Any] = (
        raw_layer_counts if isinstance(raw_layer_counts, Mapping) else {}
    )

    labels: list[str] = []
    _append(labels, "same_state" if distance == 0 else f"hamming_{distance}")
    _append(labels, f"perturbation_{band}")
    if distance == 1:
        _append(labels, "single_line_flip")
    for item in changed_layer_counts.items():
        layer, count = item
        if count:
            _append(labels, f"changed_layer_{layer}")
    if left.wen_next and right.number == left.wen_next.number:
        _append(labels, "king_wen_next")
    if left.wen_prev and right.number == left.wen_prev.number:
        _append(labels, "king_wen_prev")
    if distance > 0 and right.number == mate.get("number"):
        _append(labels, "king_wen_pair_internal")
        _append(labels, f"king_wen_pair_{pair['relation']}")
    elif distance > 0:
        _append(labels, "king_wen_cross_pair")
    reverse_match = right.lines == left.reverse.lines
    opposite_match = right.lines == left.opposite.lines
    if reverse_match:
        _append(labels, "reverse")
    if opposite_match:
        _append(labels, "opposite")
    if reverse_match and opposite_match:
        _append(labels, "reverse_and_opposite")
    if orbit_relation in {"same_state", "same_reversible_orbit"}:
        _append(labels, "same_cr_orbit")
    if right.lines == left.nuclear.lines:
        _append(labels, "nuclear_projection_target")

    return {
        "kind": "macro_hexagram_transition_taxonomy",
        "source": {"name": left.name, "number": left.number},
        "target": {"name": right.name, "number": right.number},
        "hamming_distance": distance,
        "changed_lines": list(changed),
        "changed_line_layers": layer_diagnostics["changed_line_layers"],
        "changed_layer_counts": dict(changed_layer_counts),
        "dominant_changed_layer": layer_diagnostics["dominant_changed_layer"],
        "king_wen_pair": pair,
        "transform_orbit_relation": orbit_relation,
        "structural_labels": labels,
        "reason_codes": [f"transition_label_{label}" for label in labels],
        "label_provenance": "reducer_backed",
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "foreground_action_allowed": False,
        "source_reopen_required_before_claim": True,
    }


def transition_inventory(*, include_rows: bool = False) -> dict[str, Any]:
    rows = [
        transition_taxonomy(source, target)
        for source in hexagram.HEXAGRAMS
        for target in hexagram.HEXAGRAMS
    ]
    counts: Counter[str] = Counter(
        label for row in rows for label in row["structural_labels"]
    )
    payload: dict[str, Any] = {
        "kind": "macro_hexagram_transition_taxonomy_inventory",
        "state_count": len(hexagram.HEXAGRAMS),
        "transition_count": len(rows),
        "label_counts": dict(sorted(counts.items())),
        "labels_are_reducer_backed": True,
        "raw_source_or_user_data_included": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "foreground_action_allowed": False,
        "non_goals": [
            "poem_text",
            "line_text",
            "classical_judgment",
            "source_truth",
            "foreground_advice",
        ],
    }
    if include_rows:
        payload["transitions"] = rows
    return payload


__all__ = [
    "transition_inventory",
    "transition_taxonomy",
]
