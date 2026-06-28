# Architecture Operations

Role: operational architecture and inventory index.
Status: implementation map layer.

Use this folder for sync, scale, compatibility, legacy alias, and planning
automation docs. It is a maintenance surface, not the product claim layer.

Start with the row whose `Reader route` matches the task. For product claims,
leave this folder and use
[`../../evidence/current-claims.md`](../../evidence/current-claims.md) or
[`../../evidence/readiness/stage-0-5-readiness.md`](../../evidence/readiness/stage-0-5-readiness.md).

| File | Kind | Status | Reader route |
| --- | --- | --- | --- |
| [agent-domain-hazards.md](agent-domain-hazards.md) | Verification aid | Current starter cards | Use before changing agent-prone surfaces where recurring failures come from missed domain hazards rather than ordinary syntax or unit-test gaps. |
| [compatibility-shim-inventory.md](compatibility-shim-inventory.md) | Inventory | Current maintenance owner | Use before changing fallback env/path names or deleting compatibility shims. |
| [encrypted-sync-v1.md](encrypted-sync-v1.md) | Contract/design | Current Stage 3 boundary | Use before enabling raw sync or claiming encrypted transfer readiness. |
| [encrypted-sync-v2.md](encrypted-sync-v2.md) | Design | Forward-looking | Use for recovery, conflict, revocation, and migration design; do not cite as shipped behavior. |
| [gb-scale-roadmap.md](gb-scale-roadmap.md) | Roadmap | Current scale planning | Use before changing retention, registry cache, large-thread search, or sync scale policy. |
| [json-compatibility-inventory.md](json-compatibility-inventory.md) | Inventory | Current JSON sunset map | Use before adding, removing, or reviving public JSON compatibility aliases. |
| [legacy-alias-inventory.md](legacy-alias-inventory.md) | Inventory | Current sunset map | Use before documenting or removing legacy `CODEX_MEMORY_*` / path aliases. |
| [project-planning-automation.md](project-planning-automation.md) | Implementation map | Current GitHub automation boundary | Use before changing issue triage, milestones, or roadmap drift audits. |
| [runtime-ops-owner-map.md](runtime-ops-owner-map.md) | Implementation map | Current runtime ops owner map | Use before adding or moving `aippocampus_runtime/ops/` modules; it is the guard-backed allowlist for remaining flat ops files. |
