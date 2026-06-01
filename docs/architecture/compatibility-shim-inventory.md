# Compatibility Shim Inventory

The authoritative inventory is executable:

```powershell
python tools\aippocampus\docs\compat_shim_inventory.py --json
```

Current snapshot after the #144/#305 policy pass:

| Bucket | Count | Meaning |
|---|---:|---|
| `keep_cli` | 22 | Documented CLI, hook, MCP, install, sync, onboarding, or operator paths. Keep until docs/installers publish a migration note. |
| `temporary_compat` | 111 | Flat import shims for package owners. Remove once first-party imports, docs, hooks, and binary packaging no longer call the flat path. |
| `legacy_bridge` | 3 | Single-implementation legacy paths for credential-adjacent or model-output-heavy flows. Move only with scanner-aware output contracts. |
| `delete_now` | 0 | No current top-level script qualifies for immediate deletion without a migration check. |
| `reexport_blocks` | 0 | The prompt-cue compatibility re-export block was removed; cue policy now lives in `aippocampus_runtime.recall.prompt_cues`. |

This file is only a short human pointer. Do not mirror the full 136-script list
here; use the tool output when planning a deletion batch.
