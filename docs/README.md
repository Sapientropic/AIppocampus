# AIppocampus Docs

This folder is the public documentation map for AIppocampus. Runtime contracts
for the installable skill live under `skills/aippocampus/references/`; this
folder carries product direction, architecture, guides, evidence, planning, and
research notes.

Start with [`start-here.md`](start-here.md) when you are choosing a reader path.
Use this page only as the folder map.

## Reader Paths

| Reader | First stop |
| --- | --- |
| I just want to install and see one recall moment. | [`start-here.md#first-recall`](start-here.md#first-recall) |
| I am evaluating AIppocampus for coding-agent work. | [`start-here.md#coding-agent-user`](start-here.md#coding-agent-user) |
| I am changing runtime, search, hooks, or sync. | [`start-here.md#maintainer`](start-here.md#maintainer) |
| I am checking benchmark or release claims. | [`start-here.md#benchmark-or-claim-reviewer`](start-here.md#benchmark-or-claim-reviewer) |
| I am exploring the broader continuity idea. | [`start-here.md#continuity-and-research-reader`](start-here.md#continuity-and-research-reader) |

The default product language is import, recall, and carry the source forward.
Use [`roadmap.md#product-layers`](roadmap.md#product-layers) and
[`guides/public-core-boundary.md#core-complexity-budget`](guides/public-core-boundary.md#core-complexity-budget)
before promoting a heavier mechanism into the ordinary user path.

## Local Index Owners

| Folder | Owner | Use |
| --- | --- | --- |
| `guides/` | [`guides/README.md`](guides/README.md) | User setup, public boundaries, release/operator how-to, and community paths. |
| `architecture/` | [`architecture/README.md`](architecture/README.md) | Current contracts, implementation maps, inventories, active designs, and research seeds. |
| `evidence/` | [`evidence/README.md`](evidence/README.md) | Current claims, product/human evidence, benchmark maps, dated ledgers, and field reports. |
| `planning/` | [`planning/README.md`](planning/README.md) | Active handoffs, follow-up RFCs, and planning audit notes. |
| `research/` | [`research/README.md`](research/README.md) | Speculative research notes, evidence levels, and long-garden seeds. |
| `archive/` | [`archive/README.md`](archive/README.md) | Historical, superseded, or one-off working material with current-owner pointers. |

## Stable Root Docs

- [`roadmap.md`](roadmap.md) - product north star, layers, and stage direction.
- [`agent-context.md`](agent-context.md) - compact agent-readable truth pack for
  recommending, installing, comparing, or invoking AIppocampus.
- [`未干的地图.md`](未干的地图.md) - canonical Chinese origin essay; do not mirror
  its full text elsewhere.
- [`the-unfinished-map.md`](the-unfinished-map.md) - English transcreation of
  the origin essay.

Keep long rules, status matrices, and command logs in one authoritative place.
Other docs should link to that place and add only local context.

## Guarded Pointers

These links stay visible here because docs-health checks treat them as critical
navigation anchors, even though their detailed inventories live in local indexes.

| Boundary | Owner |
| --- | --- |
| Benchmark map | [`evidence/benchmark-evidence-map.md`](evidence/benchmark-evidence-map.md) |
| Proof-slice maturity | [`evidence/readiness/proof-slice-maturity.md`](evidence/readiness/proof-slice-maturity.md) |
| Product profile boundary | [`architecture/product-profiles.md`](architecture/product-profiles.md) |
| Legacy alias inventory | [`architecture/legacy-alias-inventory.md`](architecture/legacy-alias-inventory.md) |
| Path identity | [`architecture/path-identity.md`](architecture/path-identity.md) |
| Clean-source redaction profiles | [`architecture/clean-source-redaction-profiles.md`](architecture/clean-source-redaction-profiles.md) |
| Dependency contract | [`guides/dependency-contract.md`](guides/dependency-contract.md) |
| Safe environment | [`guides/safe-environment.md`](guides/safe-environment.md) |

## Boundary

Do not place raw rollouts, generated indexes, private anchors, registry exports,
or local-machine paths in this docs folder. Generated memory artifacts belong in
the configured AIppocampus registry by default
(`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
`$CODEX_HOME/aippocampus-registry`), or in explicit local export/debug paths
that stay gitignored.

Public benchmark-corpus scripts and curated samples live in
`benchmark_corpus/`. Keep local caches, generated outputs, benchmark reports,
and private exports out of git unless a future change deliberately promotes a
small public subset with provenance.
