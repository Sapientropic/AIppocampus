# Planning Index

This folder holds active handoffs and follow-up planning notes. It is not the
canonical roadmap, evidence ledger, or issue queue. Start from
[`docs/roadmap.md`](../roadmap.md) for product direction, GitHub Issues or the
Project for executable work, and this folder when a slice needs source-backed
handoff context.

## Current Planning Lanes

| File | Classification | Use |
| --- | --- | --- |
| [next-iteration-plan.md](next-iteration-plan.md) | source-backed handoff | Durable development-slice context plus historical issue-state review; use GitHub Issues/Project for the live queue. |
| [agent-discoverability-release.md](agent-discoverability-release.md) | active handoff | PyPI, MCP Registry, one-command install, and agent recommendation publication gates. |
| [standalone-binary-packaging.md](standalone-binary-packaging.md) | active handoff | Optional Python-free binary claim boundary and cross-platform smoke matrix. |
| [encrypted-sync-follow-up-rfc.md](encrypted-sync-follow-up-rfc.md) | implemented follow-up RFC | Historical-to-current bridge for device-key UX, plaintext migration, and sync follow-up owners. |
| [technical-differentiation-analysis.md](technical-differentiation-analysis.md) | exploratory research / strategy | Positioning hypotheses and research directions; verify external facts before public claims. |

## Audit Notes

| Category | Docs | Result |
| --- | --- | --- |
| Moved to archive | `quality-task-state.md` -> [`../archive/planning/2026-05-31-quality-task-state.md`](../archive/planning/2026-05-31-quality-task-state.md) | It was already marked archived and represented a one-time 2026-05-31 issue-refinement handoff. Current executable work lives in GitHub Issues / Project after checking the relevant source docs. |
| Kept active and relabeled | `next-iteration-plan.md`, `agent-discoverability-release.md`, `standalone-binary-packaging.md` | These remain active handoff docs, with explicit Role / Status lines added so they are not mistaken for evidence ledgers or broad current contracts. |
| Kept but demoted by label | `technical-differentiation-analysis.md` | It remains in place for stable source routes, but is labeled exploratory strategy rather than active implementation truth. |
| Kept as implemented bridge | `encrypted-sync-follow-up-rfc.md` | It already points current sync work to #104, #306, and #307 rather than acting as the live queue itself. |
| Later-review sweep resolved | `docs/evidence/benchmarks/reports/public-longitudinal/react-real-vcs-100-gold-2026-05-31.md`, [`../evidence/benchmarks/design/hippocampal-recall-plan.md`](../evidence/benchmarks/design/hippocampal-recall-plan.md), [`../architecture/host/browser-extension-design.md`](../architecture/host/browser-extension-design.md), [`../architecture/future/rust-deterministic-core.md`](../architecture/future/rust-deterministic-core.md), [`../research/frontiers/compact-activation-signals.md`](../research/frontiers/compact-activation-signals.md) | React VCS remains a dated report; Hippocampal recall plan moved to the benchmark design layer; browser design now keeps research/platform notes in a sibling background file; Rust core and compact activation remain correctly placed active/future notes with source-boundary labels. |

## Maintenance Rule

Keep planning short enough to be a handoff surface. If a note becomes a stable
runtime contract, move the contract to `skills/aippocampus/references/` or
`docs/architecture/` and leave a pointer here. If a note becomes only historical
task context, move it under `docs/archive/` with a current owner pointer.
