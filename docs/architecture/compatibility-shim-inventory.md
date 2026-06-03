# Compatibility Shim Inventory

The authoritative inventory is executable:

```powershell
python tools\aippocampus\docs\compat_shim_inventory.py --json
```

Current snapshot after the #305 final `delete_now` deletion batch:

| Bucket | Count | Meaning |
|---|---:|---|
| `keep_cli` | 23 | Documented CLI, hook, MCP, install, sync, onboarding, or operator paths. Keep until docs/installers publish a migration note. |
| `temporary_compat` | 81 | Flat import shims still referenced by first-party imports, non-identity tests, documented direct invocation, hooks/installers/binaries, or documented local-logic exceptions. |
| `legacy_bridge` | 0 | No single-implementation legacy top-level script exceptions remain. |
| `delete_now` | 0 | No pure package-owner shims are currently safe to delete without first moving a real dependency or documented direct invocation. |
| `reexport_blocks` | 0 | The prompt-cue compatibility re-export block was removed; cue policy now lives in `aippocampus_runtime.recall.prompt_cues`. |
| `manual_export_surfaces` | 0 | No long temporary shim currently publishes a hand-maintained export list as a second API surface. |

This file is only a short human pointer. Do not mirror the full 104-script list
here; use the tool output when planning a deletion batch.

Temporary compatibility shims must not grow a second API surface. Long manual
export lists are reported by the inventory tool and guarded in
`tests/aippocampus/test_compat_shim_inventory.py`; use a module-alias shim or a
tiny `globals().update(...)` mirror unless a documented installer/hook fallback
needs explicit local logic.

The inventory treats the installable skill runtime entrypoint,
`skills/aippocampus/SKILL.md`, as a documentation source. A direct script path
there is a public/operator contract until the skill text is migrated. It also
counts literal `importlib.import_module("flat_module")` calls as imports, so
dynamic test and tool dependencies protect shims until callers move to package
owners.
