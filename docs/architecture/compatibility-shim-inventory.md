# Compatibility Shim Inventory

The authoritative inventory is executable:

```powershell
python tools\aippocampus\docs\compat_shim_inventory.py --json
```

Current snapshot after the #144/#305 policy pass:

| Bucket | Count | Meaning |
|---|---:|---|
| `keep_cli` | 23 | Documented CLI, hook, MCP, install, sync, onboarding, or operator paths. Keep until docs/installers publish a migration note. |
| `temporary_compat` | 113 | Flat import shims for package owners. Remove once first-party imports, docs, hooks, and binary packaging no longer call the flat path. |
| `legacy_bridge` | 0 | No single-implementation legacy top-level script exceptions remain. |
| `delete_now` | 0 | No current top-level script qualifies for immediate deletion without a migration check. |
| `reexport_blocks` | 0 | The prompt-cue compatibility re-export block was removed; cue policy now lives in `aippocampus_runtime.recall.prompt_cues`. |
| `manual_export_surfaces` | 0 | No long temporary shim currently publishes a hand-maintained export list as a second API surface. |

This file is only a short human pointer. Do not mirror the full 136-script list
here; use the tool output when planning a deletion batch.

Temporary compatibility shims must not grow a second API surface. Long manual
export lists are reported by the inventory tool and guarded in
`tests/aippocampus/test_compat_shim_inventory.py`; use a module-alias shim or a
tiny `globals().update(...)` mirror unless a documented installer/hook fallback
needs explicit local logic.
