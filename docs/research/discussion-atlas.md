# Discussion Atlas And Design Transit Map

Status: current research navigation map.
Last checked: 2026-06-16 through GitHub GraphQL; 32 discussions found.

This atlas maps GitHub Discussions onto current owner docs, runtime owners, and
execution tracks. It is a navigation layer only. Do not treat a discussion row as
public claim evidence or source truth without reopening the linked owner/evidence
artifact.

## Layer Taxonomy

| Layer | Use |
| --- | --- |
| `source_ground` | Clean source, evidence authority, sparse provenance, source reopen. |
| `route_attention` | Recall routes, action hints, Telepathy, search/reopen affordances. |
| `topology_sequence` | Journey shape, narrative mesh, derivation, local/global continuity. |
| `timing_macro` | Macro orientation, timing pressure, Yi-shaped or phase-shaped routing. |
| `package_profile` | Public package surfaces, profiles, avatars/facets, skill capability shape. |
| `learning_loop` | Self-improvement, feedback ledgers, second-user learning loops. |
| `product_philosophy` | Public philosophy, adoption posture, memory scope, open-source framing. |
| `field_validation` | Second-user reports, smoke reports, public validation signal. |

## Status Taxonomy

| Status | Meaning |
| --- | --- |
| `research_seed` | Valuable idea; not a runtime contract. |
| `active_design` | Design track with an owner doc or near-term implementation pressure. |
| `current_contract` | Stable rule or claim boundary already reflected in docs/runtime. |
| `implemented_slice` | A bounded implementation exists; wider ambition may remain open. |
| `evidence_signal` | Useful field/validation signal; not general proof by itself. |
| `historical_context` | Helps understand why choices were made; not current execution work. |
| `archived_or_superseded` | Kept for source reachability; current owner is elsewhere. |

## Transit Map

```text
source ground
  -> route/navigation
  -> working interpretation
  -> topology/timing pressure
  -> foreground packet
  -> source reopen
  -> claim/action
```

## Discussion Directory

| Discussion | Layer | Status | Owner | Execution / evidence | Next action | Cannot claim |
| --- | --- | --- | --- | --- | --- | --- |
| [#74 AIppocampus is open](https://github.com/Sapientropic/AIppocampus/discussions/74) | product_philosophy | historical_context | [roadmap](../roadmap.md) | none | Keep as launch context. | Current readiness from launch post alone. |
| [#75 Ask questions about installing, privacy, sync, or memory scope](https://github.com/Sapientropic/AIppocampus/discussions/75) | product_philosophy | current_contract | [install guide](../guides/install-guide.md) | Support/Q&A route | Keep questions routed to docs/issues. | Support answer equals verified runtime behavior. |
| [#76 What should source-backed agent memory remember?](https://github.com/Sapientropic/AIppocampus/discussions/76) | product_philosophy | research_seed | [roadmap](../roadmap.md) | none | Keep as scope seed. | Every suggested memory type is implemented. |
| [#98 Second-user technical validation after latest main updates](https://github.com/Sapientropic/AIppocampus/discussions/98) | field_validation | evidence_signal | [readiness verification](../evidence/readiness/public-readiness-verification.md) | Field report | Link dated evidence rows only when verified. | Broad public readiness by itself. |
| [#110 复归于婴儿：LLM、潜意识层与主意识的无知起点](https://github.com/Sapientropic/AIppocampus/discussions/110) | product_philosophy | historical_context | [pearl of presence](pearl-of-presence.md) | none | Preserve as philosophy context. | Runtime subconscious claims. |
| [#240 AIppocampus as a local hippocampal layer for search decisions](https://github.com/Sapientropic/AIppocampus/discussions/240) | source_ground | implemented_slice | [architecture overview](../architecture/architecture-overview.md) | Search/recall tests | Keep owner docs current. | Hosted/cloud memory or innate model memory. |
| [#249 AIppocampus as a source-backed familiarity layer](https://github.com/Sapientropic/AIppocampus/discussions/249) | source_ground | current_contract | [source-backed kernel](../architecture/architecture-overview.md#source-backed-kernel-contract) | Clean-source/readiness evidence | Keep claim ladder aligned. | Familiarity as source-open truth. |
| [#287 为什么我还是选择开源 AIppocampus](https://github.com/Sapientropic/AIppocampus/discussions/287) | product_philosophy | historical_context | [roadmap](../roadmap.md) | none | Keep as public posture. | Open-source post proves adoption. |
| [#380 Fresh context should be a baseline, not a fate](https://github.com/Sapientropic/AIppocampus/discussions/380) | product_philosophy | current_contract | [roadmap](../roadmap.md) | Benchmark framing | Keep baseline language honest. | Any benchmark superiority not evidenced elsewhere. |
| [#428 Second-user smoke: source-backed memory that actually felt like continuity](https://github.com/Sapientropic/AIppocampus/discussions/428) | field_validation | evidence_signal | [magic moments](../evidence/magic-moments.md) | Field report | Use as product-signal pointer. | General user success rate. |
| [#435 Attention Hint Before Action: mid-turn memory nudges for long agent loops](https://github.com/Sapientropic/AIppocampus/discussions/435) | route_attention | implemented_slice | [action-time hints](../architecture/coordination/action-time-hints.md) | #1670, #1671, #1799; successor #1945/#1970 | Keep hook/cache readiness explicit. | Ambient hints as always-on source truth. |
| [#519 From Skill Manuals to Internalized Capabilities](https://github.com/Sapientropic/AIppocampus/discussions/519) | package_profile | active_design | [agent-skill capability contracts](../architecture/host/agent-skill-capability-contracts.md) | Capability-contract tests | Route concrete work to capability fixtures. | Replacement of skill docs. |
| [#523 Telepathy for Agent Clusters](https://github.com/Sapientropic/AIppocampus/discussions/523) | route_attention | implemented_slice | [Telepathy packets](../architecture/coordination/telepathy-coordination-packets.md) | #1686, #1747, #1758; successor #1953 | Keep coordination enums behind presets/cards. | Autonomous multi-agent consensus. |
| [#587 When models learn to smell memory, they still need a way back to the source](https://github.com/Sapientropic/AIppocampus/discussions/587) | source_ground | current_contract | [agent-native recall facade](../architecture/recall/agent-native-recall-facade.md) | MCP/CLI recall tests | Keep deepen/reopen visible. | Scent/support as source evidence. |
| [#700 Tacit memory as a source-backed narrative mesh](https://github.com/Sapientropic/AIppocampus/discussions/700) | topology_sequence | active_design | [source-shape runtime spine](../architecture/source-shape-runtime-spine.md) | Episode/Arc, Dream, topology tests | Continue bounded read-model slices. | Narrative mesh as canonical truth. |
| [#768 The little hippocampus should light the way back](https://github.com/Sapientropic/AIppocampus/discussions/768) | route_attention | current_contract | [magic moments](../evidence/magic-moments.md) | First-recall demos | Keep first-use path product-first. | Every user will hit a magic moment. |
| [#835 Design review request: source-backed agent memory without turning summaries into facts](https://github.com/Sapientropic/AIppocampus/discussions/835) | source_ground | evidence_signal | [claim ladder](../evidence/can-claim-ladder.md) | Design review | Use as review context. | Review equals implementation. |
| [#836 Source-Backed Multi-Head Recall](https://github.com/Sapientropic/AIppocampus/discussions/836) | route_attention | implemented_slice | [agent-native recall facade](../architecture/recall/agent-native-recall-facade.md) | MCP/agent recall tests | Keep push/pull/ref lanes bounded. | Generic all-host push hooks. |
| [#890 From Tokens to Inner Signals](https://github.com/Sapientropic/AIppocampus/discussions/890) | product_philosophy | research_seed | [source as world](source-as-world.md) | none | Keep in research path. | Functional empathy implementation. |
| [#894 Source as World: how agents gain shape without innate memory](https://github.com/Sapientropic/AIppocampus/discussions/894) | product_philosophy | current_contract | [source as world](source-as-world.md) | Roadmap/architecture alignment | Keep as north-star essay. | Innate or model-native memory. |
| [#911 Claim authority ladder for ref-backed summaries vs source reopen](https://github.com/Sapientropic/AIppocampus/discussions/911) | source_ground | current_contract | [can-claim ladder](../evidence/can-claim-ladder.md) | Docs-health and evidence maps | Keep source authority terms aligned. | Exact claims from summaries alone. |
| [#1106 Source-backed attention router for AIppocampus navigation](https://github.com/Sapientropic/AIppocampus/discussions/1106) | route_attention | implemented_slice | [attention router](../architecture/recall/source-backed-attention-router.md) | Recall/router tests | Keep router output navigation-only. | Router as answer oracle. |
| [#1118 Lossless source codebook and sparse provenance router](https://github.com/Sapientropic/AIppocampus/discussions/1118) | source_ground | active_design | [sparse provenance codebook](../architecture/source/sparse-provenance-codebook.md) | [#1869](https://github.com/Sapientropic/AIppocampus/issues/1869), [#1876](https://github.com/Sapientropic/AIppocampus/issues/1876); successor #1895 | Expand only with compression/privacy evidence. | #1190 V0 as full scale-layer readiness. |
| [#1119 Ficus AIppo: source-backed impressions with fig-leaf privacy](https://github.com/Sapientropic/AIppocampus/discussions/1119) | package_profile | active_design | [public API](../guides/public-api.md) | AIppo/Ficus tests | Keep privacy and claim boundaries explicit. | Personality/profile as factual memory. |
| [#1210 Macro orientation memory: remembering where the agent stands](https://github.com/Sapientropic/AIppocampus/discussions/1210) | timing_macro | active_design | [source-shape runtime spine](../architecture/source-shape-runtime-spine.md) | Macro/router fixtures | Keep macro as orientation layer. | Macro signal as source-open evidence. |
| [#1252 Future experiment: an Agent Self-Improvement Harness](https://github.com/Sapientropic/AIppocampus/discussions/1252) | learning_loop | research_seed | [action-time hints](../architecture/coordination/action-time-hints.md) | #1653, #1751, #1799 | Route implemented slices through ledgers. | Autonomous self-improvement solved. |
| [#1262 Agent positional topology](https://github.com/Sapientropic/AIppocampus/discussions/1262) | topology_sequence | active_design | [source-shape runtime spine](../architecture/source-shape-runtime-spine.md) | Topology/Dream tests | Keep topology as navigation/read-model layer. | Topology as source truth. |
| [#1270 Sheaf memory: local sections, global continuity](https://github.com/Sapientropic/AIppocampus/discussions/1270) | topology_sequence | research_seed | [source-shape runtime spine](../architecture/source-shape-runtime-spine.md) | none | Use as language for future contracts. | Sheaf theory implemented broadly. |
| [#1316 Fixed tables, living routes: parallel derivation memory](https://github.com/Sapientropic/AIppocampus/discussions/1316) | topology_sequence | active_design | [source-shape runtime spine](../architecture/source-shape-runtime-spine.md) | Derivation/sequence fixtures | Keep fixed tables separate from living routes. | Derived routes as canonical facts. |
| [#1318 Source-backed avatars: facets, not personas](https://github.com/Sapientropic/AIppocampus/discussions/1318) | package_profile | active_design | [avatar reports](../archive/research/avatar-bounded-resonance/avatar-bounded-resonance-live-model-2026-06-13.md) | Avatar bounded-resonance pilots | Keep as facet/profile boundary. | Persistent persona simulation. |
| [#1577 Structure That Holds, Timing That Waits](https://github.com/Sapientropic/AIppocampus/discussions/1577) | timing_macro | active_design | [source-shape runtime spine](../architecture/source-shape-runtime-spine.md) | Macro/timing design track | Keep timing pressure source-bounded. | Timing/Yi layer as proven runtime quality. |
| [#1591 Source-backed self-learning](https://github.com/Sapientropic/AIppocampus/discussions/1591) | learning_loop | implemented_slice | [action-time hints](../architecture/coordination/action-time-hints.md) | #1653, #1671, #1751; successor #1960; #1978 closed measurement blocker | Continue ledger-backed learning slices. | Learning loop improves every future task. |

## Hygiene Rules

- Do not mirror long discussion text into this atlas.
- Use `owner_missing` in future rows instead of inventing canonical owners.
- A discussion can seed an issue, but only issues/tests/docs carry executable
  closeout work.
- Discussion links may orient attention; source-backed claims still require the
  owner doc, evidence row, test, or runtime source to be reopened.
