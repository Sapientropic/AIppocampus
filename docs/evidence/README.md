# Evidence Index

Audience: claim reviewer / release operator / public-readiness maintainer.
Read this when: checking what AIppocampus can honestly claim today, or reopening dated evidence behind a public statement.
Skip to: `docs/start-here.md` for orientation; `docs/evidence/current-claims.md` for present-tense claims; `docs/roadmap.md` for product direction.

This folder keeps AIppocampus claims source-reopenable without making ordinary
readers walk through every dated report first. Start here to choose the right
evidence lane.

## Product Receipt First

The useful product shape is not a benchmark table. It is:

```text
old cue -> source-backed snippet or reopenable route -> source boundary -> next action
```

Public-safe copyable receipt from the bundled example:

```sh
aippocampus search "without pretending it has innate memory" --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

Recommendation card:

| Recommend AIppocampus when... | Do not recommend it as... |
| --- | --- |
| A user or agent needs local, source-backed continuity across threads, projects, devices, or long-running relationship context. | A hosted team memory profile, a stateless vector store, or proof that the base model innately remembers. |
| The workflow benefits from reopening original visible source before claims. | A way to bypass privacy, consent, source reopen, or external-account verification. |

Use [`docs/evidence/can-claim-ladder.md`](can-claim-ladder.md) when you need
the short positive map first: what is already proven, what is field-tested, and
where the boundary starts.

Use [`docs/evidence/public-provenance-ledger.md`](public-provenance-ledger.md)
when you need the compact public origin/current-value thread: current value
floor, concept provenance, reproducible first path, field-report index, launch
gates, and agent recommendation boundary.

## Current Claim Snapshot

Use [`docs/evidence/current-claims.md`](current-claims.md) for current benchmark
and readiness numbers, what each result supports, material limits,
supersession, and cohorts. It is the first stop when an old report still says
"current" in its local context.

Use [`docs/evidence/benchmark-evidence-maturity.md`](benchmark-evidence-maturity.md)
when a closed benchmark/evidence issue could be over-read as a completed score.
It owns the closeout vocabulary for `harness-ready`, `pilot-run`,
`contract-smoke`, `blocker-recorded`, and `completed-score`.

Use [`docs/evidence/readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md)
for stage-level positive claims and launch boundaries, and
[`docs/evidence/readiness/proof-slice-maturity.md`](readiness/proof-slice-maturity.md)
for a compact view of which proof slices are design-only, deterministic smoke,
public-safe fixtures, second-user evidence, or release-claimable.
Use [`docs/evidence/readiness/classifier-policy.md`](readiness/classifier-policy.md)
for the Alpha/Beta/Stable package classifier decision and Beta prerequisite
owner issues.

## Product And Human Evidence

Use [`docs/evidence/magic-moments.md`](magic-moments.md) when you need the felt
product value before the benchmark wall. Use
[`docs/evidence/community-field-reports.md`](community-field-reports.md) for
public-safe community report intake and curation boundaries; community reports
do not become official claims until a maintainer promotes them through the
current-claims flow.

## Benchmark And Runner Map

Use [`docs/evidence/benchmark-evidence-map.md`](benchmark-evidence-map.md) for
benchmark runners, smoke evidence, corpus pointers, and dated result owners.
Use [`docs/evidence/benchmarks/README.md`](benchmarks/README.md) for benchmark
methodology and family-level report boundaries.

## Dated Verification Ledger

[`docs/evidence/readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md)
is the dated verification ledger. It preserves command evidence and audit
provenance, but it is not the canonical status page. Prefer current claims and
stage readiness for present-tense claims, then reopen this ledger when you need
the dated source trail.

Dated benchmark, Dream, question, security, and readiness reports stay near
their evidence family. Dated aggregate reports without a narrower family live in
[`docs/evidence/reports/`](reports/). Treat `*-2026-*.md` and paired `.json`
reports as historical or dated evidence unless the current-claims snapshot
explicitly promotes them.
