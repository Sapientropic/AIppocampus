# Instruction Surface Policy

Role: current contract.
Status: current contract.

This is the canonical policy for instruction-shaped text in first-party runtime
code.

AIppocampus needs some instruction-shaped text in code: prompts, compact
projection contracts, diagnostic wording, and tests all guide agents. The
boundary is that these instructions must have an owner and a surface. They must
not quietly become hidden product policy that future agents copy into compact
foreground output.

## Surfaces

Use the narrowest fitting surface:

| Surface | Belongs Here | Must Not Do |
| --- | --- | --- |
| Local invariant comment | Why a nearby fallback, ranking, gate, or compatibility edge exists. | Repeat broad product doctrine from `AGENTS.md`, `SKILL.md`, or architecture docs. |
| Runtime prompt owner | Model-facing prompt or worker contract that is named, reviewed, and tested as a product surface. | Scatter policy fragments across unrelated helpers. |
| Compact foreground projection | Small state/action/boundary that helps an agent continue. | Dump proof, provenance, matrices, selectors, or diagnostics to prove wiring. |
| Detail/operator/explain | Evidence trails, diagnostics, recovery commands, and follow-through proof. | Become the default user or foreground-agent packet. |
| Test contract text | User-visible invariant or explicit detail/operator invariant. | Freeze incidental wording, debug payload shape, or local comments. |
| Canonical docs | Durable project policy, rationale, and cross-file rules. | Mirror the same rule into many code comments. |

## Changed-Surface Gate

`tools/aippocampus/docs/debt_report.py` inventories instruction-like comments
and strings in runtime hot paths and tests. On a changed file, instruction-like
text is acceptance-bearing when it reaches the file threshold and has no owner
classification.

Resolve the warning by doing one of these:

- Replace compensatory noise with clearer code or delete it.
- Keep it as a local invariant comment near the behavior it protects.
- Point to this or another canonical doc instead of repeating broad doctrine.
- Move prompt text into a named runtime prompt owner with tests.
- Move proof or recovery diagnostics to detail/operator/explain.
- Keep test wording only when it asserts a real compact or detail/operator
  contract.

## Current Classified Owners

Representative high-pressure owners. The executable owner list lives in
`tools/aippocampus/docs/instruction_surface.py`; this table stays short so the
policy does not become another mirrored issue register.

| File | Classification | Reason |
| --- | --- | --- |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py` | `compact_projection_owner` | Owns compact recall card translation while keeping proof in detail/operator/tests. |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_route_projection.py` | `compact_route_receipt_owner` | Owns compact route labels/actions without carrying source proof or ranking diagnostics. |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_result_assembly.py` | `compact_projection_result_owner` | Owns final compact recall assembly and strips detail/operator/debug fields. |
| `skills/aippocampus/scripts/aippocampus_runtime/mcp/public_projection.py` | `mcp_public_projection_owner` | Owns MCP default-vs-full projection and redaction text. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity.py` | `runtime_prompt_and_route_owner` | Owns recall route/action selection text before projection. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_primitives.py` | `recall_route_primitive_owner` | Owns shared route-to-packet boundary wording without taking over source proof or compact projection. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli.py` | `recall_cli_dispatch_owner` | Owns CLI parser/help and compact-vs-full dispatch without taking over recovery projection logic. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_cache.py` | `last_recall_cache_navigation_owner` | Owns same-machine selector/cache recovery text; local handles stay private. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_context_render.py` | `prompt_hook_context_render_owner` | Owns prompt-hook compact context and operator debug projection separation. |
| `skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_ambient.py` | `prompt_hook_ambient_coordinator_owner` | Owns ambient cache coordination, active locks, and degraded-cache diagnostics. |
| `skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py` | `source_io_trust_boundary_owner` | Owns JSONL/source-ref loss-accounting boundary text. |
| `skills/aippocampus/scripts/aippocampus_runtime/update/agent_status_summary.py` | `update_status_compact_projection_owner` | Owns compact readiness projection without treating unverified tools as ready. |
| `tests/aippocampus/frontstage_assertions.py` | `test_contract_owner` | Owns reusable compact-vs-detail assertions. |
| `tests/aippocampus/test_architecture_boundaries.py` | `architecture_guard_test_owner` | Owns repository-level architecture boundary tests. |

New classifications should be added only when the file truly owns that surface;
otherwise split, delete, or move the text.
