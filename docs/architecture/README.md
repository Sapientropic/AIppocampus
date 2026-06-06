# Architecture Index

This folder is the role map for current and historical AIppocampus architecture
documents. Start here before opening individual files: the same topic may have
a current contract, an implementation map, an active design track, and an older
research note.

Roles:

- `current contract`: implementation owners may rely on this as current truth.
- `implementation map`: inventory, script map, or maintainer operating map.
- `active design`: planned or partially implemented design track.
- `inventory`: classified list that prevents drift or duplicated ownership.
- `research/historical`: source-reopenable context, not current contract.

| File | Role | Use |
| --- | --- | --- |
| [aar-v2-action-time-nudges.md](aar-v2-action-time-nudges.md) | current contract | AAR v2 action-time nudge authority and stale-topology boundaries. |
| [agent-skill-capability-contracts.md](agent-skill-capability-contracts.md) | current contract | Typed agent-skill capability boundaries. |
| [architecture-debt-register.md](architecture-debt-register.md) | implementation map | Architecture debt budgets for large scripts, tests, benchmarks, and tools. |
| [architecture-overview.md](architecture-overview.md) | current contract | High-level runtime layers, data flow, and metaphor discipline. |
| [browser-extension-design.md](browser-extension-design.md) | active design | Browser companion and local MCP bridge direction. |
| [clean-source-redaction-profiles.md](clean-source-redaction-profiles.md) | current contract | Optional redaction profiles without replacing raw-private clean source. |
| [cognitive-load-sidecar.md](cognitive-load-sidecar.md) | active design | Deterministic cognitive-load sidecar and live-calibration boundary. |
| [cognitive-runtime-architecture.md](cognitive-runtime-architecture.md) | current contract | Job-circuit runtime discipline for deterministic gates and semantic workers. |
| [compatibility-shim-inventory.md](compatibility-shim-inventory.md) | inventory | Compatibility shim ownership and sunset inventory. |
| [edge-capture-consolidation-boundary.md](edge-capture-consolidation-boundary.md) | current contract | Edge capture vs asynchronous consolidation lane ownership. |
| [encrypted-sync-v1.md](encrypted-sync-v1.md) | active design | Encrypted sync v1 design contract. |
| [encrypted-sync-v2.md](encrypted-sync-v2.md) | active design | Encrypted sync recovery, conflict, revocation, and migration design. |
| [gb-scale-roadmap.md](gb-scale-roadmap.md) | active design | Large-thread storage, retention, search, and sync scale roadmap. |
| [high-risk-answer-gates.md](high-risk-answer-gates.md) | current contract | High-risk answer gating and source authority boundary. |
| [knowledge-source-lifecycle.md](knowledge-source-lifecycle.md) | current contract | Knowledge source lifecycle, eligibility, and claim promotion boundary. |
| [legacy-alias-inventory.md](legacy-alias-inventory.md) | inventory | Legacy env/path alias classification and removal stages. |
| [multimodal-answer-gate.md](multimodal-answer-gate.md) | current contract | Multimodal answer source and gate contract. |
| [multimodal-provider-routing.md](multimodal-provider-routing.md) | active design | Provider routing for multimodal source surfaces. |
| [multimodal-source-manifests.md](multimodal-source-manifests.md) | current contract | Multimodal source manifest fields and provenance boundary. |
| [path-identity.md](path-identity.md) | current contract | Identity keys, display paths, and privacy-safe path handling. |
| [product-profiles.md](product-profiles.md) | current contract | Personal default, power-user optional, and enterprise-governed profiles. |
| [project-planning-automation.md](project-planning-automation.md) | implementation map | GitHub issue triage and roadmap drift audit boundary. |
| [provider-entrypoint-inventory.md](provider-entrypoint-inventory.md) | inventory | Provider-aware and Codex-specific entrypoint ownership. |
| [question-tracking-subconscious.md](question-tracking-subconscious.md) | active design | Question extraction, tracking, and theme-emergence design. |
| [runtime-envelope-and-failure-taxonomy.md](runtime-envelope-and-failure-taxonomy.md) | current contract | Public runtime envelope, failure families, and config registry boundary. |
| [runtime-script-map.md](runtime-script-map.md) | implementation map | High-risk runtime entrypoints, recall flow, callers, and tests. |
| [rust-deterministic-core.md](rust-deterministic-core.md) | active design | Future Rust deterministic-core migration gate. |
| [schema-field-profiles.md](schema-field-profiles.md) | current contract | Field-budget and projection discipline for runtime surfaces. |
| [source-backed-familiarity-map.md](source-backed-familiarity-map.md) | active design | Familiarity-map direction and source-backed boundary. |
| [topology-anchor-policy.md](topology-anchor-policy.md) | current contract | Topology anchor weighting as lifecycle pressure, not source truth. |
| [wukong-mining-notes.md](wukong-mining-notes.md) | research/historical | Mining and score-fusion research notes. |
