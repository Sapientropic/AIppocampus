"""Shared claim-boundary references for benchmark and smoke reports.

This module intentionally does not own domain caveats. Runners keep active
run-level `cannot_claim` entries near the output they protect, while inherited
or inactive caveats point back to the canonical field-discipline rule or an
owning evidence page.
"""

from __future__ import annotations

CANONICAL_CANNOT_CLAIM_REF = "docs/architecture/runtime/schema-field-profiles.md#cannot-claim"
BENCHMARK_PRIORITY_REF = "docs/evidence/benchmarks/design/benchmark-priority-map.md"


def claim_boundary_ref(owner_ref: str | None = None) -> str:
    """Return the owner document for caveats that should not be mirrored."""

    return owner_ref or CANONICAL_CANNOT_CLAIM_REF
