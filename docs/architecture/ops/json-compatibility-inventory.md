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

Compact MCP/foreground debug-field families are intentionally not mirrored in
this table. Their executable guard lives in
`skills/aippocampus/scripts/aippocampus_runtime/mcp/compact_profile.py`, with
cross-surface regression assertions in `tests/aippocampus/frontstage_assertions.py`
and the MCP compact tests. Add new compact fields there first so the renderer
can classify them as foreground, boundary, or detail/operator-only instead of
letting another diagnostic noun leak into default product output.

Executable local checks:

```powershell
python -m unittest tests.aippocampus.test_runtime_contracts_and_config_registry tests.aippocampus.test_aippocampus_mcp_server_catalog -v
python tools\aippocampus\docs\compat_shim_inventory.py --json
```

Use the first command for retired public JSON aliases and MCP compact
debug-field leaks. Use the second command for flat compatibility shims; it is
listed here because public JSON compatibility and import/path compatibility are
usually reviewed together during closeout, but their field lists stay in their
own canonical inventories.
