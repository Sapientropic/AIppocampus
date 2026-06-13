# Source-Shape Runtime Spine

Role: active design.

Status: reader-facing map for the source-shape integration owners. This is not
a runtime contract yet. Use it to find the current owner issue, source file, and
claim boundary before changing Macro, Dream, recall, avatar, or continuity-map
integration.

## Why This Exists

AIppocampus now has several strong but separately named architecture tracks:
Macro/Yi derivations, Dream jobs, local/global compatibility, familiarity
cards, avatar illumination, and active recall. The runtime gap is not that any
one track is missing; it is that a later agent can no longer quickly see how the
tracks compose.

The source-shape spine is the proposed composition layer:

```text
shared source snapshot
  -> parallel derivations and local sections
  -> compatibility / recheck diagnostics
  -> source-shape descriptor
  -> bounded projection into recall, Dream, avatar, or foreground packets
```

Every output remains navigation until source is reopened or already source-open
within scope.

## Agent Fast Path

If you are touching one of these areas, start here first:

| You are changing | First owner | Then read |
| --- | --- | --- |
| Macro/Yi derivation compatibility | #1399 | [yi-macro-runtime-interfaces.md](coordination/yi-macro-runtime-interfaces.md) |
| Local/global section glue | #1394 | [agent-native-recall-facade.md](recall/agent-native-recall-facade.md) |
| Runtime spine, guard order, recheck events, or projection | #1417 | this file, then the relevant child issue |
| Dream <-> Macro feedback | #1412 | [dream-task-design.md](../research/dream-task-design.md), then Dream runtime files |
| Familiarity cards, avatar invalidation, or decision shadows | #1407 | [source-backed-familiarity-map.md](recall/source-backed-familiarity-map.md) |
| Active recall consuming structural diagnostics | #1428 | [agent-native-recall-facade.md](recall/agent-native-recall-facade.md) and [source-backed-attention-router.md](recall/source-backed-attention-router.md) |

GitHub Issues are the executable queue. This page is the map, not a second
queue.

## Concept Status Map

| Concept | Status | Owner issue | Current code / doc anchor | Boundary |
| --- | --- | --- | --- | --- |
| Source-backed kernel | Current contract | none | [architecture-overview.md#source-backed-kernel-contract](architecture-overview.md#source-backed-kernel-contract) | Clean source and source reopen remain the authority for claims. |
| Source-shape runtime spine | Active design | #1417 | this file | No new memory store, global score, or fact authority. |
| `parallel_derivation_bundle` | Active design | #1399, #1400-#1405 | `aippocampus_runtime.macro.*`, `aippocampus_runtime.navigation.local_global_compatibility` | Shared derivations must declare snapshot/source-basis and compatibility before route flattening. |
| `source_shape_descriptor` | Active design | #1411 | pending runtime owner | One descriptor should translate module-specific signals into a bounded shape description. |
| Runtime recheck event | Active design | #1421 | pending runtime owner | Recheck events request review; they do not mutate source truth or Macro state. |
| Interlayer coupling surface | Active design | #1402 | `macro.three_powers`, `macro.line_topology`, `macro.momentum`, `macro.perturbation` | Cross-layer diagnostics run before flattening and stay navigation-only. |
| Local/global section compatibility | Partly implemented, hardening open | #1394 | `navigation.local_global_compatibility` | `glued_route`, `partial_glue`, and `obstruction` route attention; they are not facts. |
| Partial-glue narrowing | Active design | #1406 | `navigation.local_global_compatibility` | Narrowing may preserve local consistency without hiding the broader obstruction. |
| Dream/Yi recheck loop | Active design | #1412-#1416 | `dream.*`, `macro.*` | Dream can request recheck after adjudication; it must not directly rewrite Macro state. |
| Active recall source-shape consumer | Active design | #1428 | `recall.agent_continuity`, `recall.macro_live_recall`, `recall.active_recall` | Structural diagnostics may influence priority/reopen order, not claim authority. |
| Avatar illumination | Active design | #1407-#1410 | [source-backed-familiarity-map.md](recall/source-backed-familiarity-map.md) | Avatar posture emerges from valid source shape and degrades on invalidation. |

## Projection Rules

- Query text decides what the agent is asking about.
- Source-shape diagnostics may decide where to look first, what to reopen first,
  and which route needs currentness review.
- Hard masks, privacy, stale boundaries, and source authority run before
  symbolic or structural navigation.
- Compatibility diagnostics, Dream findings, avatar posture, Macro shape, and
  route scores must not become fact evidence.
- Ordinary foreground packets should use stable engineering vocabulary, not
  symbolic design vocabulary.

## Current Consolidation Boundary

Do not open a no-harm benchmark owner from this page yet. The current work is
still defining the runtime shape and projection contracts. No-harm evaluation
should wait until those slices converge enough to test real risks instead of
obvious boundaries.

## Maintenance

When a concept graduates:

1. Move the operational rule to the specific runtime contract or skill
   reference.
2. Leave a short pointer here.
3. Update the owner issue status.
4. Do not mirror long rules across multiple docs.
