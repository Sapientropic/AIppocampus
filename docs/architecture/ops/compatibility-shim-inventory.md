# Compatibility Shim Inventory

Role: inventory.

The authoritative inventory is executable:

```powershell
python tools\aippocampus\docs\compat_shim_inventory.py --json
```

Current contract:

| Bucket | Count | Meaning |
|---|---:|---|
| `keep_cli` | 0 | No flat public CLI shim remains. The public operator surface is the packaged `aippocampus` facade. |
| `temporary_compat` | 0 | No temporary flat import shim remains. |
| `legacy_bridge` | 0 | No single-implementation legacy top-level script exception remains. |
| `delete_now` | 0 | No flat script is waiting for a deletion batch. |
| `reexport_blocks` | 0 | No package-level mechanical compatibility export block remains. |
| `manual_export_surfaces` | 0 | No temporary shim publishes a hand-maintained export list as a second API surface. |

The current top-level script count is 0. `skills/aippocampus/scripts/*.py`
should stay empty; implementation belongs under `aippocampus_runtime/` or
`conversation_sources/`.

Archived documents under `docs/archive/` preserve provenance for humans but do
not keep runtime compatibility alive. If a future migration deliberately
reopens a flat entrypoint, document the reason, owner, removal condition, and
tests before adding it.
