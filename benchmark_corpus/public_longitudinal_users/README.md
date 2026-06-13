# Public Longitudinal Users

This folder contains checked-in, public-safe pseudo-user timelines for the
AIppocampus coding implicit-knowledge benchmark.

The first fixture is
[`coding_implicit_v1.jsonl`](coding_implicit_v1.jsonl). It is synthetic and
released as `CC0-1.0` so fresh clones, CI, and outside projects can rerun the
same scoring contract without private chats, raw Codex rollouts, or gated data.

Important boundary: v1 is a contract smoke, not the final flagship benchmark.
It proves that public source events, gold claims, predictions, and sanitized
reports fit together. It does not prove recall over every future event that
should have been flagged.

## Why Synthetic Pseudo-Users

Public chat corpora are useful scale controls, but they do not provide a clean
same-user coding history with labeled rejected routes, tacit constraints,
workaround rationale, stale corrections, and reopen conditions. Using hashed
IP or header fields to stitch "users" would also be the wrong privacy posture
for AIppocampus.

This fixture therefore makes the benchmark truth explicit:

- each pseudo-user has chronological source events;
- each gold claim points back to source event ids;
- each probe declares the expected behavior and forbidden drift claims;
- anti-drift negatives make same-token future tasks stay suppressed.

Larger public corpora remain useful as secondary tracks, but not as the positive
coding decision-shadow source:

- LoCoMo: real public long-conversation evidence control. Treat each sample as
  one same-dialogue retrieval task and score evidence dialogue-id retrieval
  with `benchmark_locomo_public_users.py`; do not read it as cross-conversation
  user memory or coding tacit-constraint evidence.
- LongMemEval-V2: closest public memory benchmark for agent environment
  experience, workflow knowledge, environment gotchas, and premise awareness.
- SWE-Hero OpenHands trajectories: promising coding-agent trajectory corpus for
  future scale replay.
- LongMemEval V1: traditional longitudinal retrieval control.
- WildChat / ShareChat / ShareGPT-style corpora: broad distribution and
  false-activation controls, not same-user implicit coding knowledge truth.

The positive flagship track should use VCS-derived hard future events instead:

- pull requests accepted/rejected after earlier rejected routes or review
  rationale;
- Gerrit changeset/patchset supersession after review comments;
- SATD/workaround comments and later removal/revert events;
- issue reopen and commit revert events.

Those sources have a property chat logs lack: the future window can enumerate
all hard events that should have been flagged. That makes false negatives
measurable, so a system that never dreams cannot win merely by avoiding drift.

## Fixture Shape

Each JSONL row is one pseudo-user:

- `episodes[].source_events[]`: public source timeline.
- `gold_claims[]`: source-backed hidden engineering knowledge.
- `probes[]`: held-out future prompts with expected decision and required /
  forbidden claim ids.

Expected decisions:

- `surface`: the system should surface source-backed hidden context.
- `reopen`: the system should recognize a valid condition for reopening an old
  rejected path.
- `suppress`: the system should avoid drifting into unrelated future work.
- `unknown`: reserved for future abstention cases.

## Runner

Run the deterministic gold-contract smoke:

```powershell
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --json
```

Score an external system by writing JSON or JSONL predictions with this shape:

```json
{"case_id":"plu-cache-001","decision":"surface","claim_ids":["cache-redis-rejected-no-daemon"],"source_event_ids":["cache-e001"]}
```

Then run:

```powershell
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --predictions .tmp\public-longitudinal-predictions.jsonl --json
```

Default reports are sanitized: they include case ids, hashes, labels, and
source-event ids, but not source event text or raw probe text. Use
`--include-public-text` only for explicit local debugging.

## Boundary

This benchmark can support claims about a public pseudo-user fixture and a
deterministic scoring contract. It cannot claim private real-history quality,
live Dream worker quality, real same-user longitudinal identity, or recall over
a complete future window.

Do not report a single headline aggregate as wedge evidence. Interpret the
family slices separately, especially tacit constraints, workaround rationale,
reopen conditions, and anti-drift negatives. Future VCS-derived fixtures should
report both supported flags and missed hard events.

## VCS Future-Event Fixture

[`vcs_future_events_v1.jsonl`](vcs_future_events_v1.jsonl) is the first
recall-aware scaffold. It is still synthetic and `CC0-1.0`, but its shape is
VCS-native:

- `past_window[]`: earlier review/SATD/rationale source records.
- `future_window[]`: hard future events that are either flag-worthy or explicit
  anti-drift negatives.
- `flag_worthy=true`: must be predicted; missed events count as false
  negatives.
- `flag_worthy=false`: must not be predicted; predictions count as false
  positives.

Run it:

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --baseline empty --json
```

Score external predictions:

```json
{"prediction_id":"my-flag-1","event_id":"cache-pr-207-merged","decision":"flag","past_source_ids":["cache-pr-101-review"]}
```

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --predictions .tmp\vcs-future-event-predictions.jsonl --json
```

This is the shape that should later be backed by public MSR/Gerrit/SATD/revert
corpora. Its key invariant is that a silent system fails recall.

The same hard-event shape also applies inside agent rollouts. In
[`rollout_behavior_events_v1.jsonl`](rollout_behavior_events_v1.jsonl), a
rejected route is gold only when it has behavior traces such as a failed tool
call, failed test, reverted edit, or abandoned route. Assistant narration alone
is context, not support. That lets the benchmark follow decision shadows from
PR history into agent work traces while keeping the anchor on what actually
happened.

[`rollout_behavior_events_v2.json`](rollout_behavior_events_v2.json) is the
broader public-safe cohort for #1197. It keeps the same behavior-backed support
rule and expands the synthetic rollout shape to 17 projects and 34 future
events across temporal override, cross-scope drift, cross-project
contamination, post-compaction gaps, forget boundaries, Dream candidate
boundaries, route-topic specificity, and related actionability failures.

Public VCS outcomes can be pretrained into a model, especially crisp and famous
merge/revert/reopen outcomes. Every public report should therefore include a
closed-book ablation:

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --predictions .tmp\vcs-source-window.jsonl --closed-book-predictions .tmp\vcs-closed-book.jsonl --json
```

If closed-book recall is close to source-window recall, the fixture is not
proving source-backed recovery. The public VCS track also needs time-split
holdouts and counterfactual perturbations before it can support wild-corpus
claims.

## Public VCS Builder

Use the builder when a public MSR/Gerrit/SATD/agent-rollout source has already
been downloaded or curated into normalized event-link rows:

```powershell
python benchmarks\aippocampus\builders\build_vcs_future_event_fixture.py --input .tmp\public-vcs-links.jsonl --output .tmp\vcs-future-events-built.jsonl --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\vcs-future-events-built.jsonl --allow-non-cc0-dataset --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v2.json --production-like-retrieval --source-disambiguation-top-k 2 --json
```

The builder does not scrape datasets or infer labels. It only groups curated
rows into the benchmark schema. Default output must be `CC0-1.0`; use
`--allow-non-cc0-output` only for local reports whose raw rows stay out of the
checked-in public corpus.

For agent rollouts, first build clean source so tool/test behavior appears as
structured `events.jsonl`, then link selected past event ids to curated hard
future labels:

```powershell
python skills\aippocampus\scripts\build_clean_source.py --cwd . --output-dir .tmp\clean-source --json
python benchmarks\aippocampus\builders\build_vcs_future_event_fixture.py --clean-source-events .tmp\clean-source\events.jsonl --links .tmp\rollout-event-links.jsonl --output .tmp\rollout-future-events.jsonl --allow-non-cc0-output --json
```

The link file supplies the gold judgment. The builder reads behavior-backed
past sources from `events.jsonl`; it does not infer future labels from raw
rollout traces.

Minimal input row shape:

```json
{"project_id":"repo-a","past_source_id":"review-1","past_text":"Rejected route because tests failed.","event_id":"pr-9-merged","family":"reopen_condition","hard_event_kind":"pull_request_merged","flag_worthy":true,"event_text":"Route merged after condition changed.","required_past_source_ids":["review-1"]}
```

For rollout traces, add `behavior_backed:true` to tool/test/edit sources. A
source with `behavior_backed:false` may be kept as context, but the scorer will
reject it as required support for a flag-worthy hard event.

Candidate public sources and redistribution caveats live in
[`public_sources_manifest.json`](public_sources_manifest.json).

The real public same-conversation control runner and raw-data policy live one
level up in [`../locomo_manifest.json`](../locomo_manifest.json).
