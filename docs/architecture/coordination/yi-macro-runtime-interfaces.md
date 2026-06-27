# Yi Macro Runtime Interfaces

Audience: Macro/Yi runtime maintainer / reviewer.
Read this when: deciding what each Yi, hexagram, topology, or macro primitive may do in runtime packets.
Skip to: `README.md` for the coordination index; `../recall/agent-native-recall-facade.md` for agent-facing recall/deepen contracts; `../../research/` for speculative framing.

Role: current contract

Status: canonical #1272 audit table for Yi / macro-orientation primitives as
runtime interfaces, not symbolic decoration. Keep detailed runtime behavior in
the Python modules; keep this table as the single reader-facing role map.

Design rule:

> Yi says how the situation moves; topology says whether relations hold; sheaf
> style local/global gluing says whether local views can compose.

Discussion #1210 owns the dynamics framing, #1262 owns positional topology, and
#1270 owns the sheaf/local-global framing. None of those layers can upgrade a
macro packet into source evidence.

## Primitive Roles

| Primitive | Runtime role | Runtime owner | Non-goal |
| --- | --- | --- | --- |
| Hexagram state / six-bit bottom-to-top convention | `deepen_explain_only` | `macro.hexagram`, `macro.state` | No line-text reading, project truth, personality, fate, or user-intent claim. |
| Changing lines | `recall_fanout`, `deepen_explain_only` | `macro.hexagram.change_lines`, `macro.perturbation` | No symbolic advice and no evidence without source reopen. |
| Hamming distance / perturbation width | `recall_fanout`, `compact_foreground_packet` | `macro.perturbation`, agent macro packet | No quality score, source truth, or unbounded candidate expansion. |
| Nuclear / opposite / reverse transforms | `deepen_explain_only` | `macro.hexagram.public_hexagram_projection`, `macro.transform_orbit` | No foreground symbolic prose, route merge, source support, or route-weight change until a usefulness fixture proves lift. |
| King Wen sequence movement | `recheck_timing`, `deepen_explain_only` | `macro.stage_tracker` | The sequence is not project law and must not auto-mutate state or claims. |
| Three Powers route facets | `recall_fanout`, `telepathy_handoff_compatibility` | `macro.three_powers` | No source evidence, hard assignment, identity truth, or role truth. |
| 世 / 应 (Shi/Ying; host/response role positioning) | `telepathy_handoff_compatibility`, `deepen_explain_only` | `macro.state.relation_position`, `macro.line_topology` | No agent personality truth or user-intent inference. |
| 消息卦 momentum (growth/decline phase) | `recheck_timing`, `compact_foreground_packet` | `macro.momentum`, agent macro packet | No energy score, metaphysical project-state claim, or evidence score. |
| Total hexagram encoder | `compact_foreground_packet`, `recall_fanout` when complete/reviewed | `macro.total_encoder`, `recall.macro_live_recall` | No defaulting missing lines to 乾/人, no private/local-source projection, no symbolic advice. |
| 纳甲-like active-axis timing (Najia-style timing) | `recheck_timing`, `research_only` | `macro.timing`, `ops.macro_timing_recheck_experiment` | No currentness replacement, fact assignment, foreground prose, or default ranking change. |
| 卦气-like source-epoch cadence (hexagram-qi style cadence) | `recheck_timing`, `research_only` | `macro.timing`, `ops.macro_timing_recheck_experiment` | No literal calendar/solar-term timing, temporal-head replacement, scheduled background cost, or foreground prose. |
| 乘 / 承 / 比 / 应 internal line topology | `telepathy_handoff_compatibility`, `deepen_explain_only` | `macro.line_topology`, `macro.three_powers` | Cheng/Cheng/Bi/Ying relation checks; no ranking-weight change, source support, or mathematical topology claim. |
| 当位 / 不当位 (proper/improper line position) | `research_only` | none | No foreground signal, route control, or claim support until usefulness is proven. |

## Shi/Ying Restriction Edge Decision

Local/global compatibility keeps Shi/Ying restriction edges as V0
project-scoped navigation hints. The runtime may record
`shi_ying_v0_project_role_hint` when a Macro or Telepathy section carries
project relation-position metadata, but it does not load classical bagua
position tables or infer exact classical Shi/Ying line semantics.

This decision keeps the current product surface grounded: Shi/Ying can help
explain why two local sections need handoff/restriction review, but it cannot
alter source truth, rank routes, assign agent identity, infer user intent, or
grant foreground claim permission. Classical position infrastructure should be
a future issue only if a concrete usefulness fixture needs it.

## Cross-Grain Projection Contract

Cross-grain projection is owned by `aippocampus_runtime.macro.cross_grain`.
It is an explain/deepen contract over existing deterministic primitives, not a
new ranking, evidence, or foreground prose layer.

| Grain | Runtime source | Projection rule | Boundary |
| --- | --- | --- | --- |
| Three Powers / 3 layers | `macro.three_powers` | Earth, human, and heaven remain separate route facets; mixed queries expose `candidate_layers`, `score_margin`, and `ambiguity_status` instead of hiding ties. | Layer labels are navigation posture only, never user intent, role truth, or source support. |
| Six lines | `macro.line_topology` | Broken couplings such as `broken_coupling_earth_heaven` project upward as reason codes and review pressure for the relevant Three Powers layers. | Topology cannot change ranking weights or prove a claim without reopened source. |
| Trigram shape | `macro.hexagram` | Upper/lower trigrams may appear as compact shape hints in explain/deepen packets. | A trigram hint is not a full hexagram state and must not be foreground symbolic prose. |
| 64-state / orbit | `macro.transform_orbit` | `same_reversible_orbit` and `adjacent_flip` may explain structural relation; nuclear basins remain non-invertible projection diagnostics. | Orbit or basin membership is not source support, route merge permission, or ranking weight. |

Every projection carries `authority_level=navigation_only`,
`claim_permission=no_claim_before_reopen`, and `fact_claim_allowed=false`.
Runtime consumers such as the attention route producer (#1188) and semantic
warming bridge (#1386) may use these reason codes as reopen/deepen hints only;
they must not duplicate this contract or treat the projection as evidence.

## Total Encoder Contract

`aippocampus_runtime.macro.total_encoder.build_total_hexagram_encoding(...)`
derives all six bottom-to-top lines only when source-backed line evidence is
complete, or when an explicit reviewed state is provided. Partial, ambiguous,
insufficient-source, and blocked/private-local inputs degrade to diagnostic
status and cannot feed `macro_live_recall` as a compact state hint.

Each derived line carries source refs and a derivation reason. The public
projection omits raw source text, local paths, and symbolic instruction. This
keeps the macro state usable for route fanout without letting a missing line
quietly become a full hexagram.

## Change-Line Transition Records

`cross_grain.macro_transition_record` names the existing computation
本卦 -> changing lines -> 之卦 (original hexagram -> changed hexagram) as a lifecycle record. The record carries source
hexagram, changed lines, target hexagram, perturbation band, optional source
refs, and review policy.

The record is for audit and explain/deepen readability. It does not create
divination-style advice, does not write macro state, and does not authorize
foreground action. Inversion transitions require conflict review/source reopen
before action; local and medium transitions remain navigation-only fanout
pressure over source-backed project events.

## Nuclear Basin Decision

Nuclear/互卦 basins (nuclear hexagram basins) are locked to `explain_only` for V0. The candidate
usefulness path is perspective-change explanation during deepen/debug, but no
current fixture proves route merging, ranking, or source-support lift. Until a
future issue supplies wins, no-help cases, and no authority upgrade evidence,
`nuclear_basin_explain_policy` enforces:

- no route merge from basin membership;
- no ranking-weight change;
- no source support from basin membership;
- no foreground symbolic prose.

## Runtime Audit

The executable audit lives in `aippocampus_runtime.macro.audit`:

```powershell
python -m pytest tests\aippocampus\test_yi_macro_runtime_interfaces.py -q
```

The fixture asserts:

- foreground-emitted macro primitives keep `action_grammar=direction_only`,
  `authority_level=navigation_only`, `claim_permission=no_claim_before_reopen`,
  and `fact_claim_allowed=false`;
- nuclear/opposite/reverse transforms remain `deepen_explain_only`;
- 当位 / 不当位 remains `research_only`;
- Hamming distance changes fanout width, and momentum changes recheck timing;
- mixed active-layer queries expose ambiguity instead of hiding ties;
- cross-grain projections and change-line transition records stay
  navigation-only;
- nuclear basins are locked to explain-only with no route merge or ranking
  effect;
- topology/sheaf-style consumption can read Yi-derived layer/movement signals
  without raising authority or bypassing source reopen.
- total-encoder states can change macro route hints only when complete or
  explicitly reviewed; degraded states produce diagnostics instead.

## Load-Bearing Topology Boundary

Topology primitives become action-time only through
`aippocampus_runtime.topology.packet_preflight` and the promotion metadata in
`aippocampus_runtime.topology.primitive_registry`.

Reducer-backed failures such as authority overreach, Borromean
source/user/agent breaks, and route cycles may repair, downgrade, suppress, or
request source reopen. Missing-middle and weak-bridge findings are review-only
annotations. Knot/unlinking language remains research vocabulary until a
future fixture proves reliable action selection. The
`macro.loadbearing_fixture` report keeps useful route/action changes separate
from authority upgrades and raw leak checks.

## Transform-Orbit Diagnostics

The reversible transform-orbit helper lives in
`aippocampus_runtime.macro.transform_orbit`. It currently defines one
operation set, `cr_reversible`, made only from opposite and reverse
transforms. The public fixture asserts 20 C/R orbits across 64 hexagrams, with
the size distribution `{2: 8, 4: 12}`.

Line flips are adjacency edges, not reversible-orbit generators. Nuclear
transforms are modeled as a non-invertible projection/dynamics layer with four
16-source basins, not as C/R orbit membership. These diagnostics can explain
why two macro states look structurally related, but they remain
`navigation_only`, `candidate_only`, and `no_claim_before_reopen`.

## Timing Experiment

The public-safe #1314 timing experiment lives in
`aippocampus_runtime.macro.timing` and
`aippocampus_runtime.ops.macro_timing_recheck_experiment`. It maps source-backed
deltas onto the existing 1-6 line axes and emits a source-epoch cadence check.
This answers "which axis deserves a recheck" and "has a quiet source epoch
crossed a fixture threshold"; it does not decide freshness, supersession,
truth, or a literal calendar phase.

## Boundary

Macro Orientation can steer where an agent looks, when it rechecks, and how it
explains a navigation packet. It cannot decide what happened, replace reopened
source, infer personality or fate, or add decorative foreground prose merely
because a classical concept exists.
