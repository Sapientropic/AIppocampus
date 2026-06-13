# Architecture Index

Role: architecture entrypoint.
Status: stable reader map; detailed contracts live in topic folders.

Start here when changing runtime contracts, source authority, recall routing,
coordination packets, host/provider surfaces, or planning automation. Keep this
file as a map, not a mirror of every contract.

## Start Here

| Need | Start with |
| --- | --- |
| Source-backed kernel contract and metaphor discipline | [architecture-overview.md](architecture-overview.md) |
| Cross-layer source-shape integration track | [source-shape-runtime-spine.md](source-shape-runtime-spine.md) |
| Runtime entrypoints, callers, and tests | [runtime-script-map.md](runtime-script-map.md) |
| Large-file guard budgets and split queue | [architecture-debt-register.md](architecture-debt-register.md) |

## Topic Layers

| Layer | Use |
| --- | --- |
| [runtime/](runtime/) | Runtime envelope, job-circuit architecture, schema field profiles, and deterministic-core direction. |
| [source/](source/) | Clean-source, source reopen, redaction, provenance, source manifests, and source lifecycle contracts. |
| [recall/](recall/) | Agent recall facade, attention router, foreground budget, familiarity, continuity domains, cognitive load, and question tracking. |
| [coordination/](coordination/) | Telepathy, packet topology, cross-agent isolation, Episode/Arc, AAR, topology anchors, and Yi/Macro interfaces. |
| [host/](host/) | Host/provider/product-profile contracts, multimodal answer/provider gates, browser extension direction, and high-risk answer gates. |
| [ops/](ops/) | Sync, scale, compatibility, legacy aliases, and GitHub/project planning automation. |
| [future/](future/) | Future deterministic-core and research-seed architecture notes. |

## Roles

- `current contract`: implementation owners may rely on this as current truth.
- `implementation map`: maintainer navigation, script map, or operating map.
- `inventory`: classified list that prevents drift or duplicated ownership.
- `active design`: planned or partially implemented design track.
- `research seed`: source-reopenable inspiration or analysis, not current
  architecture truth.

Historical architecture material belongs under `docs/archive/architecture/`
when superseded. Keep only a short pointer here if current readers still need
the route.
