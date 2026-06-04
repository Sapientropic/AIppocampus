# Dream Private Large-History Diagnostic Evidence - 2026-06-04

This evidence slice records the issue #158 / #164 private-history diagnostic run
from 2026-06-04. It is a sanitized aggregate record only. The local raw outputs
stayed under `.tmp/issue-158-164-private-large/` and are not checked in.

The important correction for this run is that two accidental operator settings
are invalid for the main Dream-quality conclusion:

- any run with explicit `--max-tokens 700`;
- any run with `--dream-model-thinking disabled`.

The valid Dream model-backed run used provider/default thinking and did not send
an explicit max-token cap.

## Commands

Selector boundary:

```powershell
python skills\aippocampus\scripts\dream_real_history_eval.py --json --max-packs 100 --min-packs 20 --output .tmp\issue-158-164-private-large\dream-real-history-deterministic-100.json
```

Valid model-backed all-selected Dream run:

```powershell
python skills\aippocampus\scripts\dream_real_history_eval.py --json --max-packs 18 --min-packs 18 --dream-worker-mode model-backed --max-samples 1 --dream-model-timeout 180 --dream-model-thinking provider --dream-model-reasoning-effort provider --output .tmp\issue-158-164-private-large\dream-real-history-model-backed-18-PROVIDER-THINKING-NO-MAX-TOKENS.json
```

Valid model-backed historical clean-source shadow replay:

```powershell
python skills\aippocampus\scripts\dream_live_shadow_ab.py --json --replay-clean-source --max-threads 50 --max-user-messages 100 --generate-dream-rows 18 --dream-worker-mode model-backed --dream-max-samples 1 --dream-model-timeout 180 --dream-model-thinking provider --dream-model-reasoning-effort provider --semantic-relevance-gate --semantic-relevance-max-candidates 5 --semantic-relevance-min-confidence 0.45 --output .tmp\issue-158-164-private-large\dream-live-shadow-model-backed-18-semantic-gate-PROVIDER-THINKING-NO-MAX-TOKENS.json
```

E2E50 candidate-seed scan:

```powershell
python tools\aippocampus\smoke\smoke_e2e50_seed_candidates.py --json --min-turns 30 --max-turns 120 --early-turns 15 --later-start-turn 30 --min-candidates 20 --max-candidates 100 --output .tmp\issue-158-164-private-large\e2e50-seed-candidates-wide-100.json
```

Live semantic gate diagnostic:

```powershell
python benchmarks\aippocampus\benchmark_live_semantic_gate.py --json --cases 20 --min-cases 10 --semantic-mode on --semantic-timeout 60 --semantic-workers default --case-workers 1 --output .tmp\issue-158-164-private-large\live-semantic-gate-20.json
```

Corrected worker smoke after root-cause isolation:

```powershell
python benchmarks\aippocampus\benchmark_live_semantic_gate.py --json --sharegpt-conversations 1 --cases 4 --min-cases 4 --semantic-mode on --semantic-timeout 60 --semantic-workers default --case-workers 1 --output .tmp\issue-158-164-private-large\live-semantic-gate-diagnostic-default-alias-after-fix.json
```

Agency host-timing deterministic replay:

```powershell
python tools\aippocampus\smoke\smoke_agency_host_timing.py --json
```

Coding decision-shadow deterministic benchmark:

```powershell
python benchmarks\aippocampus\benchmark_coding_decision_shadow.py --json
```

## Input Surface

- Subconscious job rows: 698
- Working-memory rows: 63
- Selected source-backed cross-thread ready packs: 18
- Source seed kinds: 6 frontier-marker, 8 question-candidate, 1 question-link,
  15 working-memory
- Coding decision-shadow packs selected: 0
- Private text emitted: no

## Results

Valid model-backed all-selected Dream run:

- Status: `lift_observed`
- Selected packs: 18
- Dream worker mode: model-backed
- Dream findings: 36
- Dream working-memory rows: 31
- Model calls: 36
- DeepSeek route: default flash route
- Total tokens: 89,422
- DeepSeek prefix-cache hit rate: 0.9608
- Prompt hit-rate delta: 0.0
- Source-thread coverage delta: 1.6111
- Structural reflection-ready delta: 616
- Bridge-claim coverage delta: 1.0
- User-visible recall hit delta: 0
- User-visible reflection-ready delta: 125
- Unsupported strong-claim suppression rate: 1.0
- Source-support correctness rate: 1.0
- Manual/source review rows: 0

Valid historical clean-source shadow replay:

- User turns replayed: 100
- Threads: 2
- Delivery mode: 100 shadow-only events
- Live delivered treatment events: 0
- Dry-run would-deliver events: 0
- Explicit recall-reminder prompts detected: 2
- Overall reminder rate: 0.02
- Eligible exposure rate: 0.01
- Dream eligible exposures: 1
- Dream attributed reminder outcomes: 1
- Control eligible exposures: 0
- Baseline match events: 95
- Dream match events: 1
- Semantic relevance calls: 5
- Semantic relevance match events: 1
- Dream-minus-control reminder-rate delta: 1.0, where lower is better

E2E50 candidate-seed scan:

- Status: `insufficient_candidate_seeds`
- Candidate count: 17 against a requested minimum of 20
- Registry threads scanned: 1,028
- Message rows scanned: 11,877
- Event rows scanned: 41,065
- Long threads in the configured range: 40
- Compaction-observed threads: 94
- Signal threads: 907

E2E50 local manual annotation:

- Local clean-source candidates reviewed: 17
- Gold seed candidates retained: 4
- Calibration / weak seed candidates retained: 2
- Rejected, duplicate, or negative-control candidates: 11
- Private text exported or checked in: no
- Representative E2E50 sample ready: no

Agency host-timing replay:

- Status: deterministic replay passed
- Cases: 5
- Decisions: 1 show, 1 hold, 3 suppress
- Reasons: 1 actionable host moment, 1 duplicate across host, 1 recent negative
  feedback, 1 source visible, 1 task phase not actionable
- Live host timing measured: no
- Privacy boundary: no raw source text, paths, private thread ids, or credentials
  serialized

Coding decision-shadow deterministic benchmark:

- Status: `quality_gate_passed`
- Tracks A-E: all sufficient
- Negative controls passed: wrong-source evidence, visible-source suppression,
  stale-authority suppression
- Privacy boundary: no raw text, raw source refs, or absolute paths emitted
- Still cannot claim live host timing, private-history behavior lift, or full
  code-index navigation quality

Live semantic gate diagnostic with `--semantic-workers default`:

- Report status before fix: `sufficient`
- Quality gate before fix: true
- Semantic gate spy call count: 15
- Semantic available count: 0
- Semantic usage: 0 tokens
- Root cause: `default` was not a valid runtime worker name and was filtered to
  zero workers; the benchmark status gate did not require any live semantic
  availability.

Corrected worker smoke with the fixed `default` worker alias:

- Cases: 4
- Reported semantic workers: `gate`, `alias`, `scope`
- Semantic gate spy call count: 2
- Semantic available count: 2
- Worker count per live case: 3
- Semantic usage: 11,513 total tokens
- This only proves the worker route can run. It is not a quality benchmark.

## Interpretation

The main Dream result is a real offline substrate signal, not a live product
lift. The model-backed Dream worker produced source-backed structural lift over
selected private ready packs, but plain recall was already saturated at 1.0, so
there was no recall-hit lift. The useful movement is source-thread coverage,
reflection surface, and bridge-claim coverage.

The 18-pack ceiling is not a max-packs bug. The selector currently builds packs
by shared cross-thread resonance terms, requires at least two source-backed
threads, and prevents seed reuse across selected packs. With the current job and
working-memory inputs, that yields 18 non-overlapping selected packs.

The coding decision-shadow probe did not run because none of the selected packs
contained `coding_ticket`, `coding_decision_event`, `decision_event`, or
`rejected_route` seed kinds. Issue #163/#158 therefore still need a falsifiable
coding Dream retrospective workload; this run only reports the deferment.

The shadow replay is not positive behavior evidence. It was historical
shadow-only replay, with no delivered treatment/control events and only one
eligible dream exposure in 100 turns. That one exposure was followed by a
reminder, so the direction is an annoyance/noise risk flag, not a lift signal.

The E2E50 scanner did find candidate seeds, but it did not reach the requested
20-case minimum. The output is candidate discovery only; it still needs manual
annotation and source reopening before it becomes a behavior benchmark.

The local E2E50 annotation step reviewed all 17 scanner candidates against
private clean source. That removed most automatic hits: several were subagent or
goal-context noise, repeated constraints, duplicate conceptual threads, or
source-visible/browser-report cases. Four candidates are strong enough to carry
forward as gold-seed candidates, and two more are useful calibration cases. This
is real annotation progress, but it is still not a 20-case or 50-case benchmark.

The host-timing and coding decision-shadow checks are the part that can be done
offline today. Agency host timing now has deterministic replay evidence for
show/hold/suppress decisions and duplicate/negative-feedback/source-visible
suppression. Coding decision-shadow Tracks A-E pass as a public-safe
deterministic benchmark. Neither result is live delivery evidence because no
real host accepted, delayed, suppressed, or measured user-facing tickets.

The live semantic gate result exposed a benchmark bug. Passing
`--semantic-workers default` selected zero runtime workers, and the old quality
gate could still pass because it only checked surface recall and false-positive
counts. The fix is to normalize `default` / `all` to `gate,alias,scope`, reject
unknown workers, include availability diagnostics in the report, and fail the
quality gate when live semantic calls are made but none are available.

## Can Claim

- The selected private real-history Dream eval can run model-backed with
  provider/default thinking, no explicit max-token cap, and no private-text
  emission.
- On this selected slice, model-backed Dream rows produced structural lift:
  source-thread coverage delta 1.6111, reflection-ready delta 616, and
  bridge-claim coverage delta 1.0.
- The historical shadow replay measured reminder frequency and sparse eligible
  exposures without delivered treatment.
- The E2E50 scanner can produce sanitized candidate seeds from private history.
- Local manual annotation narrowed the 17 E2E50 candidate seeds to 4 strong
  gold-seed candidates plus 2 calibration seeds without checking in private
  text.
- Agency host-timing replay exercises show/hold/suppress boundaries,
  duplicate suppression, and recent negative-feedback suppression in a
  deterministic fixture.
- Coding decision-shadow Tracks A-E pass with wrong-source, visible-source, and
  stale-authority negative controls.
- The live semantic gate provider route works when valid workers are selected;
  the invalid `default` worker path was a benchmark/operator bug, not a provider
  outage.

## Cannot Claim

- Causal real-user behavior lift.
- General Dream quality or user-visible reflection value.
- Full private-history coverage.
- Coding decision-shadow Dream value.
- Safe delivered Dream treatment outcomes.
- E2E50 benchmark quality or representative sample quality.
- A completed 20-case or 50-case annotated E2E50 sample.
- Live host timing or annoyance lift.
- Private-history coding decision-shadow behavior lift.
- Live semantic-model quality from the invalid-worker 20-case run.
