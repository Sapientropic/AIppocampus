"""Rule catalog for the repo-local agent slop guard.

Keep rule metadata separate from the scanner so adding a new red light does not
turn the CLI into another broad responsibility owner.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    owner_hint: str
    owner_issue: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "owner_hint": self.owner_hint,
            "owner_issue": self.owner_issue,
            "description": self.description,
        }


RULES: dict[str, Rule] = {
    "compact_projector_bypass": Rule(
        rule_id="compact_projector_bypass",
        severity="warning",
        owner_hint=(
            "Route MCP/CLI compact recovery through render_profiled_result or "
            "the compact projection owner; do not return text_result(public_payload(...))."
        ),
        owner_issue="#2696",
        description="MCP/CLI compact path appears to bypass compact/detail projection.",
    ),
    "hot_path_silent_fallback": Rule(
        rule_id="hot_path_silent_fallback",
        severity="warning",
        owner_hint=(
            "Use typed recovery with diagnostics/loss accounting, or baseline the "
            "historical debt to #2629/#2676 before touching this hot path."
        ),
        owner_issue="#2697",
        description="Hot-path broad exception hides failure by continuing or returning empty state.",
    ),
    "source_jsonl_owner_bypass": Rule(
        rule_id="source_jsonl_owner_bypass",
        severity="warning",
        owner_hint=(
            "Use aippocampus_runtime.source.io_kernel.load_jsonl_dict_rows, "
            "load_jsonl_dict_rows_with_line_field, or an approved source IO wrapper."
        ),
        owner_issue="#2698",
        description="Source-backed JSONL appears to be parsed line-by-line outside the IO kernel.",
    ),
    "atomic_write_owner_bypass": Rule(
        rule_id="atomic_write_owner_bypass",
        severity="warning",
        owner_hint=(
            "Use aippocampus_runtime.io_integrity.prepared_atomic_replace or "
            "atomic_write_* helpers instead of fixed .tmp files or ad hoc replace/rename."
        ),
        owner_issue="#2698",
        description="Runtime writer appears to bypass shared atomic write helpers.",
    ),
    "source_ref_helper_duplicate": Rule(
        rule_id="source_ref_helper_duplicate",
        severity="warning",
        owner_hint=(
            "Reuse source.io_kernel source-ref helpers or a documented owner wrapper; "
            "do not grow local source-ref key/normalization copies."
        ),
        owner_issue="#2698",
        description="Local source-ref key/normalization helper duplicates the source-ref owner.",
    ),
    "registry_writer_owner_bypass": Rule(
        rule_id="registry_writer_owner_bypass",
        severity="warning",
        owner_hint=(
            "Use aippocampus_runtime.registry.store.update_registry or "
            "registry_writer_lease around load/modify/save; do not copy registry "
            "writer helpers into sync/update/runtime callers."
        ),
        owner_issue="#2682",
        description="Registry mutation appears to bypass the registry writer owner.",
    ),
    "local_lock_owner_bypass": Rule(
        rule_id="local_lock_owner_bypass",
        severity="warning",
        owner_hint=(
            "Use artifact_lease, registry_writer_lease, active_recall_lock, or a "
            "documented local-lock owner helper instead of hand-rolled os.O_EXCL locks."
        ),
        owner_issue="#2681",
        description="Runtime code appears to copy a local lock implementation outside a lock owner.",
    ),
    "compat_field_metadata_missing": Rule(
        rule_id="compat_field_metadata_missing",
        severity="warning",
        owner_hint=(
            "Compatibility fields need nearby owner, removal condition, and default "
            "exposure boundary metadata; do not expose aliases in compact foreground by habit."
        ),
        owner_issue="#2699",
        description="Compatibility/legacy field is missing owner/removal/default exposure metadata.",
    ),
    "field_only_followthrough_test": Rule(
        rule_id="field_only_followthrough_test",
        severity="warning",
        owner_hint=(
            "Use product_probe_helpers recall/deepen/open assertions or another real "
            "follow-through probe before treating fields, route counts, or selectors as success."
        ),
        owner_issue="#2699",
        description="Recall/MCP/APW/source-open test appears to assert payload fields without follow-through.",
    ),
    "compact_debug_field_test": Rule(
        rule_id="compact_debug_field_test",
        severity="warning",
        owner_hint=(
            "Compact foreground tests should assert action-sized behavior; detail/operator "
            "debug fields belong behind full/detail profiles or frontstage assertions."
        ),
        owner_issue="#2699",
        description="Compact foreground test appears to require debug/operator fields.",
    ),
    "public_compact_field_unclassified": Rule(
        rule_id="public_compact_field_unclassified",
        severity="warning",
        owner_hint=(
            "Classify new top-level compact fields in guard_registry.py as compact "
            "contract, detail diagnostic, trace/operator-only, or internal-only before "
            "exposing them on CLI/MCP compact foreground surfaces."
        ),
        owner_issue="#2782",
        description="Compact foreground return payload exposes an unclassified top-level field.",
    ),
    "public_compact_field_misplaced": Rule(
        rule_id="public_compact_field_misplaced",
        severity="warning",
        owner_hint=(
            "Move detail/trace/internal fields behind full/detail/operator output or "
            "translate them into a compact state/action/source boundary."
        ),
        owner_issue="#2782",
        description="Compact foreground return payload exposes a field classified as non-compact.",
    ),
    "performance_hot_path_nested_loop": Rule(
        rule_id="performance_hot_path_nested_loop",
        severity="warning",
        owner_hint=(
            "Aggregate or index by unique entity before nested work; known owners include "
            "#2705 association mining, #2708 long-thread scans, and #2709 hub expansion."
        ),
        owner_issue="#2707",
        description="Hot path contains nested loops over unbounded product collections.",
    ),
    "performance_hot_path_loop_materialization": Rule(
        rule_id="performance_hot_path_loop_materialization",
        severity="warning",
        owner_hint=(
            "Move list/sorted materialization outside the hot loop, bound it explicitly, "
            "or baseline the known owner issue instead of hiding the cost."
        ),
        owner_issue="#2707",
        description="Hot path materializes an unbounded collection inside a loop.",
    ),
    "performance_hot_path_repeated_db_work": Rule(
        rule_id="performance_hot_path_repeated_db_work",
        severity="warning",
        owner_hint=(
            "Batch or cache DB work by unique concept/ref/entity; #2706 owns concept "
            "upsert amplification and #2709 owns live graph query budget."
        ),
        owner_issue="#2707",
        description="Hot path performs DB lookup/upsert work inside an unbounded loop.",
    ),
}


OWNER_LAYER_CONTRACTS: tuple[dict[str, object], ...] = (
    {
        "contract_id": "mcp_foreground_projection_owner",
        "rule_ids": ("compact_projector_bypass",),
        "owner": "aippocampus_runtime.mcp.result_profile / public_projection",
        "why": "Compact/default foreground output stays action-sized instead of becoming proof dumps.",
    },
    {
        "contract_id": "source_io_kernel_owner",
        "rule_ids": ("source_jsonl_owner_bypass", "source_ref_helper_duplicate"),
        "owner": "aippocampus_runtime.source.io_kernel",
        "why": "JSONL loss accounting and source-ref identity stay source-backed and consistent.",
    },
    {
        "contract_id": "registry_writer_owner",
        "rule_ids": ("registry_writer_owner_bypass",),
        "owner": "aippocampus_runtime.registry.store.update_registry / registry_writer_lease",
        "why": "Registry read-modify-write paths share one lease and do not clobber each other.",
    },
    {
        "contract_id": "local_lock_owner",
        "rule_ids": ("local_lock_owner_bypass", "atomic_write_owner_bypass"),
        "owner": "aippocampus_runtime.artifacts.publish / io_integrity / dedicated lock owners",
        "why": "Writers use portable interrupted-write boundaries instead of local lock copies.",
    },
    {
        "contract_id": "followthrough_test_owner",
        "rule_ids": (
            "field_only_followthrough_test",
            "compact_debug_field_test",
            "public_compact_field_unclassified",
            "public_compact_field_misplaced",
        ),
        "owner": "tests.aippocampus.product_probe_helpers / frontstage assertions",
        "why": "Recall/MCP/APW tests prove source follow-through and compact UX, not field presence.",
    },
)
