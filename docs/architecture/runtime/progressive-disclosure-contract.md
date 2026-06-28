# Progressive Disclosure Contract

Role: current contract.
Status: foreground product contract.

Default compact output is a frontstage card, not an operator dashboard. It must
help the next agent or human move toward usable continuity before asking them
to inspect readiness ledgers, proof fields, or subsystem diagnostics.

## Compact Budget

Default compact surfaces must project these tiers in this order:

1. Outcome tier: one short state such as `ready`, `usable_now`,
   `needs_source_registration`, `recall_route_found`,
   `low_confidence_reopen_candidate`, or `blocked`.
2. Primary next step: exactly one `foreground_action`.
3. Boundary tier: the smallest source/privacy/mutation boundary needed to act.
4. Detail tier: `--detail full`, `--operator-json`, diagnostics, trace,
   inventories, and proof payloads.

Budget rules:

- `foreground_action` is the primary action; do not duplicate it as
  `agent_next_action` or `safe_next_actions[0]`.
- Compact `safe_next_actions` should be empty or one real alternative by
  default. Chooser cards may allow more only when the surface is explicitly a
  chooser and each action is distinct.
- Compact output may expose at most one top-level detail affordance such as
  `operator_detail_command`, unless the surface has a named allowlist in
  `tests/aippocampus/frontstage_assertions.py`.
- Compact output must not expose runtime provenance, policy matrices, gate
  objects, feedback controls, cache inventories, field inventories, or
  suppressed-hit diagnostic lists.
- Full/detail/operator output may carry diagnostics, but cannot be the only
  place where the user can find the next useful action.

## Surface Matrix

| Surface | Outcome tier | Primary next step |
| --- | --- | --- |
| setup/start | `decision` plus `status` | `foreground_action`; trusted-personal first-run uses one consent bundle and an after-setup recall receipt path. |
| update status | `setup_card.state` / `summary` | one foreground status action; slow components remain detail/operator. |
| plugin status/install | callability or install state | verify MCP/tool callability or install/rollback action, not a menu of internals. |
| MCP compact tools | structured content card | one tool-call action with arguments; detail remains behind explicit MCP/detail paths. |
| hooks/action hints | installed/callable/active/useful | probe/deepen/open or refresh action; proof stays in full output. |
| recall/deepen/APW | route found/opened/blocked | deepen/open selected source before claims. |
| search/registry search | source match, near-hit, or miss | open selected source, inspect low-confidence near-hit, or refine exact phrase. |

## Tests

Code-facing assertions live in:

- `tests/aippocampus/frontstage_assertions.py`
- `tests/aippocampus/test_agent_deepen_compact_projection.py`
- `tests/aippocampus/test_aippocampus_mcp_server_recall.py`
- `tests/aippocampus/test_aippocampus_mcp_server_ops.py`
- `tests/aippocampus/test_action_hint_hook.py`
- `tests/aippocampus/test_cli_start.py`
- `tests/aippocampus/test_registry_search.py`
- `tests/aippocampus/test_update_agent_status.py`

When a compact/default payload needs more fields to prove something, put that
proof in full/detail, a test, PR notes, or an issue comment. Do not move the
proof burden into the foreground product surface.
