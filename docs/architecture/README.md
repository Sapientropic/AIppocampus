# Architecture Index

This folder is the role map for AIppocampus architecture documents. Keep files
at their stable paths so old issues, docs, and source-reopen routes remain
useful; make the document role visible in this index and in each document's
top-level `Role:` line instead of moving files whenever the taxonomy changes.

Roles:

- `current contract`: implementation owners may rely on this as current truth.
- `implementation map`: maintainer navigation, script map, or operating map.
- `inventory`: classified list that prevents drift or duplicated ownership.
- `active design`: planned or partially implemented design track.
- `research seed`: source-reopenable inspiration or analysis, not current
  architecture truth.
- `archive`: historical architecture material retained for provenance only.

## Current Contracts

| File | Role | Use |
| --- | --- | --- |
| [aar-v2-action-time-nudges.md](aar-v2-action-time-nudges.md) | current contract | AAR v2 action-time nudge authority and stale-topology boundaries. |
| [agent-skill-capability-contracts.md](agent-skill-capability-contracts.md) | current contract | Typed agent-skill capability boundaries. |
| [architecture-overview.md](architecture-overview.md) | current contract | High-level runtime layers, data flow, and metaphor discipline. |
| [clean-source-redaction-profiles.md](clean-source-redaction-profiles.md) | current contract | Optional redaction profiles without replacing raw-private clean source. |
| [cognitive-runtime-architecture.md](cognitive-runtime-architecture.md) | current contract | Job-circuit runtime discipline for deterministic gates and semantic workers. |
| [edge-capture-consolidation-boundary.md](edge-capture-consolidation-boundary.md) | current contract | Edge capture vs asynchronous consolidation lane ownership. |
| [encrypted-sync-v1.md](encrypted-sync-v1.md) | current contract | First encrypted sync design and compatibility boundary. |
| [high-risk-answer-gates.md](high-risk-answer-gates.md) | current contract | High-risk answer gating and source authority boundary. |
| [knowledge-source-lifecycle.md](knowledge-source-lifecycle.md) | current contract | Knowledge source lifecycle, eligibility, and claim promotion boundary. |
| [multimodal-answer-gate.md](multimodal-answer-gate.md) | current contract | Multimodal answer source and gate contract. |
| [multimodal-provider-routing.md](multimodal-provider-routing.md) | current contract | Provider capability-routing contract and public-safe fixture boundary. |
| [multimodal-source-manifests.md](multimodal-source-manifests.md) | current contract | Multimodal source manifest fields and provenance boundary. |
| [path-identity.md](path-identity.md) | current contract | Identity keys, display paths, and privacy-safe path handling. |
| [product-profiles.md](product-profiles.md) | current contract | Personal default, power-user optional, and enterprise-governed profiles. |
| [runtime-envelope-and-failure-taxonomy.md](runtime-envelope-and-failure-taxonomy.md) | current contract | Public runtime envelope, failure families, and config registry boundary. |
| [schema-field-profiles.md](schema-field-profiles.md) | current contract | Field-budget and projection discipline for runtime surfaces. |
| [topology-anchor-policy.md](topology-anchor-policy.md) | current contract | Topology anchor weighting as lifecycle pressure, not source truth. |

## Implementation Maps

| File | Role | Use |
| --- | --- | --- |
| [architecture-debt-register.md](architecture-debt-register.md) | implementation map | Architecture debt budgets for large scripts, tests, benchmarks, and tools. |
| [project-planning-automation.md](project-planning-automation.md) | implementation map | GitHub issue triage and roadmap drift audit boundary. |
| [runtime-script-map.md](runtime-script-map.md) | implementation map | High-risk runtime entrypoints, recall flow, callers, and tests. |

## Inventories

| File | Role | Use |
| --- | --- | --- |
| [compatibility-shim-inventory.md](compatibility-shim-inventory.md) | inventory | Compatibility shim ownership and sunset inventory. |
| [legacy-alias-inventory.md](legacy-alias-inventory.md) | inventory | Legacy env/path alias classification and removal stages. |
| [provider-entrypoint-inventory.md](provider-entrypoint-inventory.md) | inventory | Provider-aware and Codex-specific entrypoint ownership. |

## Active Designs

| File | Role | Use |
| --- | --- | --- |
| [browser-extension-design.md](browser-extension-design.md) | active design | Browser companion and local MCP bridge direction; confirm external platform details before relying on them. |
| [cognitive-load-sidecar.md](cognitive-load-sidecar.md) | active design | Deterministic cognitive-load sidecar and live-calibration boundary. |
| [encrypted-sync-v2.md](encrypted-sync-v2.md) | active design | Encrypted sync recovery, conflict, revocation, and migration design. |
| [episode-arc-read-models.md](episode-arc-read-models.md) | active design | Ordered Episode/Arc read-model schema, sequence packet projection, and source-window reopen boundary. |
| [gb-scale-roadmap.md](gb-scale-roadmap.md) | active design | Large-thread storage, retention, search, and sync scale roadmap. |
| [question-tracking-subconscious.md](question-tracking-subconscious.md) | active design | Question extraction, tracking, and theme-emergence design. |
| [rust-deterministic-core.md](rust-deterministic-core.md) | active design | Future Rust deterministic-core migration gate. |
| [source-backed-familiarity-map.md](source-backed-familiarity-map.md) | active design | Familiarity-map direction and source-backed boundary. |

## Research Seeds

| File | Role | Use |
| --- | --- | --- |
| [wukong-mining-notes.md](wukong-mining-notes.md) | research seed | Mining and score-fusion inspiration; use as research context, not current routing truth. |

## Archives

No archived architecture docs currently live in this folder. Put historical
architecture material under `docs/archive/architecture/` when it is superseded
and keep a short pointer here only if current readers still need the route.
