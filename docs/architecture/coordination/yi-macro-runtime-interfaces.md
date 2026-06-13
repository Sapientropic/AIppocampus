# Yi Macro Runtime Interfaces

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
| 世 / 应 role positioning | `telepathy_handoff_compatibility`, `deepen_explain_only` | `macro.state.relation_position`, `macro.line_topology` | No agent personality truth or user-intent inference. |
| 消息卦 momentum | `recheck_timing`, `compact_foreground_packet` | `macro.momentum`, agent macro packet | No energy score, metaphysical project-state claim, or evidence score. |
| 纳甲-like active-axis timing | `recheck_timing`, `research_only` | `macro.timing`, `ops.macro_timing_recheck_experiment` | No currentness replacement, fact assignment, foreground prose, or default ranking change. |
| 卦气-like source-epoch cadence | `recheck_timing`, `research_only` | `macro.timing`, `ops.macro_timing_recheck_experiment` | No literal calendar/solar-term timing, temporal-head replacement, scheduled background cost, or foreground prose. |
| 乘 / 承 / 比 / 应 internal line topology | `telepathy_handoff_compatibility`, `deepen_explain_only` | `macro.line_topology`, `macro.three_powers` | No ranking-weight change, source support, or mathematical topology claim. |
| 当位 / 不当位 | `research_only` | none | No foreground signal, route control, or claim support until usefulness is proven. |

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
- topology/sheaf-style consumption can read Yi-derived layer/movement signals
  without raising authority or bypassing source reopen.

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
