# Topology Anchor Policy

Topology can protect a source-reopenable memory from time-only decay, but it is
navigation and lifecycle pressure only. It is not factual evidence, currentness,
or a reason to skip source reopen.

The deterministic policy lives in
`aippocampus_runtime.ops.topology_anchor_policy`. It reads source-joined graph
rows and emits `topology_anchor_weight`, classification, reason codes, and
metrics without mutating clean source or generated graph files.

## Protected Cases

| Case | Expected behavior |
| --- | --- |
| Old, low-frequency bridge between two durable clusters | Decay slower than an ordinary leaf and stay source-reopenable. |
| High-degree noisy hub | Do not protect merely because many edges point at it. Popularity is not bridge value. |
| Supersession or contradiction bridge | Preserve context for review before archive, but do not surface stale claims as current facts. |
| Model-only topology without source refs | Keep diagnostic-only; do not let generated graph structure become source support. |

## Metrics

The policy reports:

- `topology_protected_anchor_count`
- `bridge_reopen_helpful_count`
- `noisy_hub_suppression_count`
- `stale_bridge_reopen_required_count`

These counters describe lifecycle/navigation behavior. They do not prove memory
quality, user-visible recall lift, or the truth of an old bridge.

## Boundaries

Privacy blocks, explicit user correction, missing source, and stale/currentness
checks override topology. A protected topology anchor may influence retention,
activation, observatory visualization, or reopen priority only after it rejoins
stable source refs.
