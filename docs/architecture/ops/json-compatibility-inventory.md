# JSON Compatibility Inventory

Role: inventory.

Last audited: 2026-06-21.

AIppocampus public JSON no longer keeps migration-only duplicates by default.
When a field is retired here, normal CLI/MCP foreground output must not emit it.
Use explicit operator/detail adapters only when a local diagnostic truly needs
to describe an older shape.

| Field | Former meaning | Canonical field | Status | Removal condition |
| --- | --- | --- | --- | --- |
| `agent_next_action` beside `foreground_action` | Byte-for-byte primary foreground action alias | `foreground_action` | Removed in `foreground-action-v2` | Normal public JSON must omit it. |
| `safe_next_actions[0] == foreground_action` | Repeated primary action in alternatives list | `foreground_action`; `safe_next_actions` for distinct alternatives | Removed in `foreground-action-v2` | Contract lint rejects repeated primary actions. |
| `next_safe_action` matching `foreground_action` | Older primary-action alias | `foreground_action` | Removed from compact foreground cards | Keep only non-duplicative domain follow-up fields. |

Keep-with-reason fields:

| Field | Reason |
| --- | --- |
| `choices` | Chooser cards expose all user-selectable options; it is not a primary-action alias. |
| `recommended_actions` | Health and maintenance diagnostics can carry a broader advisory list behind the compact foreground card. |
| Row-level `agent_next_action` in domain tables | Retired with `foreground-action-v2`; row/domain actions should use `foreground_action` for action objects or `foreground_guidance` for prose guidance. |

Guardrail: `foreground_action_contract_violations()` rejects top-level legacy
primary aliases for `foreground-action-v2`.
