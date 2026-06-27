# AIppocampus Guard Lifecycle Registry

Role: current contract.
Status: active guard and verification ownership registry.

This is the canonical repo-owned registry for local red-light tooling,
verification ownership, and guard compact-output budgets. Contributor skills
may point here, but should not mirror this table.

## Verification Ownership

| Bucket | Owner | Default local use | Examples |
| --- | --- | --- | --- |
| local fail-fast | editing agent | Run early before PR | `git diff --check`, planner-named `ruff`/`mypy`, changed-surface debt/slop guards |
| local closeout | implementation owner | Run once near closeout when planner names it | focused changed-surface tests, `run_tests.py --tier pr` |
| CI required | GitHub Actions / release workflow | Do not rerun locally by default after green CI | clean install, wheel contract, docs health in clean env, PR tier in clean env, broad-pr shards, Python 3.13 quick, macOS smoke, benchmark smoke |
| manual/dogfood required | implementation owner + reviewer | Required for product claims, not every PR | real cue `agent recall -> deepen/open -> opened source anchor hits` for recall/MCP/APW/source-open claims |
| advisory | verification steward | Run or explain when changed surface names it | timing trends, broad slop/debt reports outside changed surface, structural metrics not promoted |

CI must not become the normal way to discover cheap local failures. Local
agents should also not turn CI-owned broad, benchmark, platform, coverage, or
release lanes into default local rituals after CI is green.

## Active Guard Set

| Guard id | Command / surface | Class | Owner | Blind spot prevented | Bad example | Accepted good example | Noise / allowlist | Lifecycle condition | Compact expectation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `git-diff-check` | `git diff --check` | hard | local fail-fast | Agents bury whitespace/conflict-marker errors behind long tests | Run PR tier first, then discover conflict markers in CI | Stop immediately and fix diff hygiene | None expected | Keep until Git stops catching this cheaply | first blocker + detail command |
| `static-ruff` / `static-mypy` | planner-named static gates | hard | local fail-fast, CI mirrored | Basic import/type drift discovered late in CI | Wait for CI to catch changed tooling import breakage | Run only when planner names Python/tooling surface | Python minor mismatch is a warning unless CI-equivalent runtime is absent | Downgrade only if planner proves a cheaper owner catches the same failures | command + class + owner |
| `changed-surface-debt` | `debt_report.py --changed-surface-only` | hard | local fail-fast | Cleanup PR adds duplicate helpers, broad fallbacks, compact debug literals, or giant owners | Add a report while leaving duplicated helper path active | Delete/migrate/centralize changed-surface debt and show before/after | Historical debt outside changed surface remains owner-tracked | Split or retire when each family has a closer owner guard | first acceptance-bearing warning + detail command |
| `agent-slop-guard` | `agent_slop_guard.py --fail-on-violations` | advisory red light, acceptance-bearing for changed surface | local fail-fast | Agent-authored patches prove fields instead of product behavior, copy owner helpers, or leak compact debug fields | Assert `route_count` without opening source | Use product probe helpers or compact/frontstage assertions | Baselined historical findings stay advisory unless touched | Keep as a small family registry; add rules only with fixtures and retirement note | blockers only, rule catalog only in full |
| `closeout-audit` | PR body / issue closeout audit | hard for closing keywords | closeout archivist | PR closes broad/debt/product issues from field presence, synthetic fixtures, or guard-only armor | “Added a red light. Closes cleanup issue.” | `before inventory -> debt removed/simplified -> after inventory -> focused tests` | Guard-only issues may pass only with explicit label plus promote/park/remove condition | Revisit when GitHub issue forms encode closeout class natively | compact findings + rerunnable command |
| `changed-surface-preflight` | `changed_surface_preflight.py` | hard | local fail-fast | Agents run too much too late or miss the one cheap blocker | Run broad-pr before `git diff --check` | Fail fast, then run closeout/pre-push proof explicitly | Slow focused proof is skipped in default preflight by design | Keep while agent workflows remain local-first | pass/fail, first blocker, verification cost, detail command |
| `benchmark-smoke-public-fast` | benchmark-smoke / public-fast | CI-owned | CI required | Benchmark or platform lanes become default local rituals | Run benchmark smoke for routine runtime edit after green CI | Leave to CI unless benchmark evidence itself changed | Local run is okay for benchmark runner/fixture changes | Keep CI-owned unless benchmark lane becomes fast enough for local closeout | labeled as CI-owned, not default local |
| `tier-report-diagnostic` | `run_tests.py --report-json` / timing artifacts | advisory | verification steward | Suite growth or stale timing becomes invisible until agents stop running local gates | Dump full timing rows into PR closeout | Compact summary names top slow modules and budget status; full JSON keeps rows | Timing drift is advisory unless changed planner/tier surface creates obvious waste | Promote to hard only for structural duplicate plans or reviewed budget violations | top slow summary + detail artifact |

## New Hard Guard Checklist

Before promoting or adding a hard guard, record:

- guard id, command or owning surface, owner doc, and verification owner;
- recurring agent blind spot it prevents;
- one bad example and one accepted good example or allowlist policy;
- false-positive/noise note;
- expected runtime cost and default local/CI ownership;
- compact output expectation;
- promotion, park, downgrade, or removal condition;
- focused fixture or changed-surface example proving the guard catches the bad
  pattern and stays quiet on the allowed pattern.

If a proposal cannot fill those fields, keep it advisory, park it in a
research seed, or delete the stale guard instead of adding more armor.

## Public Compact Field Classes

Top-level fields on compact CLI/MCP/guard surfaces must be classified in
`tools/aippocampus/guard_registry.py` as:

- `compact_contract`: action, state, source receipt, boundary, owner, or exact next command;
- `detail_diagnostic`: useful diagnostics that belong in `--detail full`;
- `trace_operator_only`: provenance, selectors, caches, policy matrices, or operator commands;
- `internal_only`: helper rows, raw data, or implementation scaffolding.

The compact field guard starts hard only when changed MCP/CLI compact
foreground surfaces are under review. Other surfaces begin as advisory so the
classification table can converge without blocking unrelated work.
