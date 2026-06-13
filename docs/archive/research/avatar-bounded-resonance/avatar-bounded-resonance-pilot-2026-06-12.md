# Avatar Bounded Resonance Pilot, 2026-06-12

Role: exploratory public-safe proxy report for #1319.

Current owner: `docs/evidence/current-claims.md` carries the present claim
boundary; `docs/architecture/source-shape-runtime-spine.md` and #1407 carry the
current avatar/source-shape design route.

This report covers a deterministic pilot harness for bounded resonance avatar
posture prompts. It is not a live model result, not a default runtime adoption
decision, and not evidence that archetype terms improve production agent
behavior.

## Setup

- Runner: `benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py`
- Fixture: `benchmark_corpus/avatar_bounded_resonance/fixture.json`
- Execution mode: `deterministic_scripted_proxy_v0`
- Live model calls: 0
- Public-safe cases: 12
- Scenario families: closeout / broad issue risk, debug dead-end / repeated
  route, structural break / old frame
- Arms: A explicit engineering instruction, B neutral posture, C archetype
  alias only, D bounded resonance, E random symbolic control

## Result

| Arm | Average proxy score | Completion success | Manual search count | Off-topic archetype expansion |
| --- | ---: | ---: | ---: | ---: |
| A explicit instruction | 4.5 | 1.0 | 8 | 0 |
| B neutral posture | 1.083333 | 0.0 | 12 | 0 |
| C archetype alias only | -1.833333 | 0.0 | 24 | 12 |
| D bounded resonance | 5.666667 | 1.0 | 0 | 0 |
| E random symbolic control | 0.75 | 0.0 | 12 | 0 |

The deterministic proxy marks D as the best arm. The useful reading is narrow:
bounded resonance is worth a public-safe model-backed repeat before any
foreground runtime proposal. Standalone archetype aliases should not be
foregrounded; in this proxy they drift more than bounded resonance.

## Red Lines

- `bounded_resonance_off_topic_archetype_expansion_count = 0`
- `bounded_resonance_archetype_used_as_authority_count = 0`
- `factual_claim_from_resonance_count = 0`
- `private_or_sensitive_context_used_count = 0`

## Recommendation

Do not ship avatar posture packets by default. Continue only to a
model-backed, public-safe repeat using the same A-E arms, same fixture families,
and an explicit reviewer/scorer rubric. If bounded resonance fails to beat
explicit instruction or neutral posture in a real model run, keep resonance in
research/Campus/explain surfaces only.

## Boundaries

Can claim:

- the public-safe fixture exists;
- the deterministic runner applies arms A-E to all cases;
- the bounded resonance arm has zero candidate red lines in the proxy;
- standalone alias drift is visible.

Cannot claim:

- bounded resonance improves production agent behavior;
- live LLM or host behavior lift;
- default foreground avatar runtime readiness;
- private-history avatar quality;
- archetype or resonance as authority;
- source truth from posture or resonance;
- broad avatar/persona quality.
