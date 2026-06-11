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
| Nuclear / opposite / reverse transforms | `deepen_explain_only` | `macro.hexagram.public_hexagram_projection` | No foreground symbolic prose or route-weight change until a usefulness fixture proves lift. |
| King Wen sequence movement | `recheck_timing`, `deepen_explain_only` | `macro.stage_tracker` | The sequence is not project law and must not auto-mutate state or claims. |
| Three Powers route facets | `recall_fanout`, `telepathy_handoff_compatibility` | `macro.three_powers` | No source evidence, hard assignment, identity truth, or role truth. |
| 世 / 应 role positioning | `telepathy_handoff_compatibility`, `deepen_explain_only` | `macro.state.relation_position`, `macro.line_topology` | No agent personality truth or user-intent inference. |
| 消息卦 momentum | `recheck_timing`, `compact_foreground_packet` | `macro.momentum`, agent macro packet | No energy score, metaphysical project-state claim, or evidence score. |
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

## Boundary

Macro Orientation can steer where an agent looks, when it rechecks, and how it
explains a navigation packet. It cannot decide what happened, replace reopened
source, infer personality or fate, or add decorative foreground prose merely
because a classical concept exists.
