# Compatibility Shim Inventory

The authoritative inventory is executable:

```powershell
python tools\aippocampus\docs\compat_shim_inventory.py --json
```

Current snapshot after the #659 first flat-import migration slice, focused
`delete_now` cleanup, and the archived-doc blocker cleanup:

| Bucket | Count | Meaning |
|---|---:|---|
| `keep_cli` | 23 | Documented CLI, hook, MCP, install, sync, onboarding, or operator paths. Keep until docs/installers publish a migration note. |
| `temporary_compat` | 75 | Flat import shims still referenced by first-party imports, non-identity tests, documented direct invocation, hooks/installers/binaries, or documented local-logic exceptions. |
| `legacy_bridge` | 0 | No single-implementation legacy top-level script exceptions remain. |
| `delete_now` | 0 | Pure package-owner shims with no remaining first-party/import/docs blocker; delete only in a focused batch with any matching `py-modules` entries. |
| `reexport_blocks` | 0 | The prompt-cue compatibility re-export block was removed; cue policy now lives in `aippocampus_runtime.recall.prompt_cues`. |
| `manual_export_surfaces` | 0 | No long temporary shim currently publishes a hand-maintained export list as a second API surface. |

The current top-level script count is 98. This file is only a short human pointer. Do not mirror the full script list
here; use the tool output when planning a deletion batch.

Temporary compatibility shims must not grow a second API surface. Long manual
export lists are reported by the inventory tool and guarded in
`tests/aippocampus/test_compat_shim_inventory.py`; use a module-alias shim or a
tiny `globals().update(...)` mirror unless a documented installer/hook fallback
needs explicit local logic.

The inventory also reports `shim_style_counts` and an `unknown_shim_styles`
gate. Current style counts are:

| Style | Count | Meaning |
|---|---:|---|
| `module_alias_shim` | 52 | Uses `sys.modules[__name__]` when import identity compatibility matters. |
| `export_mirror_shim` | 43 | Mirrors package-owner exports through a tiny explicit list or generated mirror. |
| `facade_shim` | 2 | Public command-router or provider-aware facade. |
| `local_fallback_shim` | 1 | Documented half-installed fallback exception. |

`unknown_shim_styles` should stay empty. If it becomes non-empty, either
convert the shim to one of the documented styles in `runtime-script-map.md` or
add a specific policy reason before treating it as intentional compatibility.

The #305 kill-list phase left the immediate `delete_now` queue empty. The first
#659 cleanup batch deleted the next five `delete_now` candidates and matching
`py-modules` entries. Future #659 flat-import migration work should continue to
move concrete blockers into `delete_now`; delete those candidates only in
focused batches after rerunning the inventory and dropping any matching
`py-modules` entries.

The inventory treats the installable skill runtime entrypoint,
`skills/aippocampus/SKILL.md`, as a documentation source. A direct script path
there is a public/operator contract until the skill text is migrated. It also
counts literal `importlib.import_module("flat_module")` calls as imports, so
dynamic test and tool dependencies protect shims until callers move to package
owners.

Archived documents under `docs/archive/` preserve provenance for humans but do
not keep direct-script compatibility shims alive. If an archived plan is the
only remaining reference, migrate or delete the shim through the normal focused
batch and leave the archive text unchanged.
