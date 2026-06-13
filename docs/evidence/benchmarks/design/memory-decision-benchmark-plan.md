# AIppocampus Memory Decision Benchmark Plan

Status: repeatable baseline suite, named profile ladder, threshold metadata,
and `public-fast` fresh-clone profile implemented; current source-evidence
recall has improved, live semantic-gate smoke is opt-in, semantic-sidecar
coverage remains a known gap, and deterministic synthetic Track D
compaction-continuity testing is implemented as a measurement surface.

This document defines the benchmark direction for AIppocampus memory decisions.
It complements the existing FTS5/source-evidence checks; it does not replace
them and does not turn AIppocampus into a generic vector-search benchmark.
For the shortest map of every benchmark runner, smoke surface, corpus note, and
dated evidence owner, start with `docs/evidence/benchmark-evidence-map.md`.

## Reader Path

This file is now the slim entrypoint and anchor-preserving map. Detailed
methodology lives under [`memory-decision/`](memory-decision/).

| Need | Open |
| --- | --- |
| Implemented slices, profile ladder, guardrails, attribution arms, optional semantic gates | [`memory-decision/implemented-slices.md`](memory-decision/implemented-slices.md) |
| Non-goals and benchmark-positioning boundary | [`memory-decision/positioning.md`](memory-decision/positioning.md) |
| Core labels and Track A/B/C/D definitions | [`memory-decision/tracks-a-d.md`](memory-decision/tracks-a-d.md) |
| Boundary tests, case generation, report shape, rollout plan, acceptance criteria | [`memory-decision/implementation-policy.md`](memory-decision/implementation-policy.md) |

## Goal

AIppocampus should be evaluated on the product behavior that matters most:

- when to stay silent
- when to emit quiet recall scent
- when to emit source-backed evidence
- whether surfaced payloads are faithful to clean source
- whether unrelated work prompts remain free of personal/private context
- whether work-task corrections and accepted decisions survive compaction
  without being promoted as automatic truth

The benchmark should prove that the system is useful without becoming noisy.
False positives, evidence over-escalation, and privacy leakage are worse than a
missed fuzzy recall.


## Existing Baseline

The existing lexical/source baseline lives in
`benchmarks/aippocampus/benchmark_fts5_recall.py`. It answers a narrower
question: given a source-backed recall case, can the FTS5 and production hybrid
paths navigate back to the expected clean-source message?

That baseline should remain because stale indexes, lexical misses, and ranking
regressions are real risks. The new benchmark layer should not re-score the
same thing under more complicated names.


## Current Implemented Slice

Moved detail: [`memory-decision/implemented-slices.md#current-implemented-slice`](memory-decision/implemented-slices.md#current-implemented-slice).

### Knowledge Pollution And Privacy Partition Benchmark

Moved detail: [`memory-decision/implemented-slices.md#knowledge-pollution-and-privacy-partition-benchmark`](memory-decision/implemented-slices.md#knowledge-pollution-and-privacy-partition-benchmark).

### Field Continuity / Magic Moment Reproducibility Suite

Moved detail: [`memory-decision/implemented-slices.md#field-continuity-magic-moment-reproducibility-suite`](memory-decision/implemented-slices.md#field-continuity-magic-moment-reproducibility-suite).

### Benchmark Suite Profiles

Moved detail: [`memory-decision/implemented-slices.md#benchmark-suite-profiles`](memory-decision/implemented-slices.md#benchmark-suite-profiles).

### Run-History Diff Guardrails

Moved detail: [`memory-decision/implemented-slices.md#run-history-diff-guardrails`](memory-decision/implemented-slices.md#run-history-diff-guardrails).

### Continuous-Memory Attribution Arms

Moved detail: [`memory-decision/implemented-slices.md#continuous-memory-attribution-arms`](memory-decision/implemented-slices.md#continuous-memory-attribution-arms).

### Repeatable Baseline Command

Moved detail: [`memory-decision/implemented-slices.md#repeatable-baseline-command`](memory-decision/implemented-slices.md#repeatable-baseline-command).

### Uncertainty And Gate Semantics

Moved detail: [`memory-decision/implemented-slices.md#uncertainty-and-gate-semantics`](memory-decision/implemented-slices.md#uncertainty-and-gate-semantics).

### Coding Decision-Shadow A-E Benchmark

Moved detail: [`memory-decision/implemented-slices.md#coding-decision-shadow-a-e-benchmark`](memory-decision/implemented-slices.md#coding-decision-shadow-a-e-benchmark).

### Optional ShareGPT Public Track B

Moved detail: [`memory-decision/implemented-slices.md#optional-sharegpt-public-track-b`](memory-decision/implemented-slices.md#optional-sharegpt-public-track-b).

### Optional Public Semantic Sidecar Track B

Moved detail: [`memory-decision/implemented-slices.md#optional-public-semantic-sidecar-track-b`](memory-decision/implemented-slices.md#optional-public-semantic-sidecar-track-b).

### Optional Live Semantic Gate

Moved detail: [`memory-decision/implemented-slices.md#optional-live-semantic-gate`](memory-decision/implemented-slices.md#optional-live-semantic-gate).

## Non-Goals

Moved detail: [`memory-decision/positioning.md#non-goals`](memory-decision/positioning.md#non-goals).

## Benchmark Positioning: Retrieval Quality vs End-to-End QA

Moved detail: [`memory-decision/positioning.md#benchmark-positioning-retrieval-quality-vs-end-to-end-qa`](memory-decision/positioning.md#benchmark-positioning-retrieval-quality-vs-end-to-end-qa).

### What AIppocampus measures instead

Moved detail: [`memory-decision/positioning.md#what-aippocampus-measures-instead`](memory-decision/positioning.md#what-aippocampus-measures-instead).

### Track S: no-live-judge semantic robustness

Moved detail: [`memory-decision/positioning.md#track-s-no-live-judge-semantic-robustness`](memory-decision/positioning.md#track-s-no-live-judge-semantic-robustness).

### When end-to-end QA benchmarks are appropriate

Moved detail: [`memory-decision/positioning.md#when-end-to-end-qa-benchmarks-are-appropriate`](memory-decision/positioning.md#when-end-to-end-qa-benchmarks-are-appropriate).

### Summary

Moved detail: [`memory-decision/positioning.md#summary`](memory-decision/positioning.md#summary).

## Core Labels

Moved detail: [`memory-decision/tracks-a-d.md#core-labels`](memory-decision/tracks-a-d.md#core-labels).

## Track A: Gate Decision

Moved detail: [`memory-decision/tracks-a-d.md#track-a-gate-decision`](memory-decision/tracks-a-d.md#track-a-gate-decision).

### Case Families

Moved detail: [`memory-decision/tracks-a-d.md#case-families`](memory-decision/tracks-a-d.md#case-families).

### Metrics

Moved detail: [`memory-decision/tracks-a-d.md#metrics`](memory-decision/tracks-a-d.md#metrics).

## Track B: Source Evidence Retrieval

Moved detail: [`memory-decision/tracks-a-d.md#track-b-source-evidence-retrieval`](memory-decision/tracks-a-d.md#track-b-source-evidence-retrieval).

## Track C: End-to-End Payload Fidelity

Moved detail: [`memory-decision/tracks-a-d.md#track-c-end-to-end-payload-fidelity`](memory-decision/tracks-a-d.md#track-c-end-to-end-payload-fidelity).

## Track D: Compaction Continuity Benchmark

Moved detail: [`memory-decision/tracks-a-d.md#track-d-compaction-continuity-benchmark`](memory-decision/tracks-a-d.md#track-d-compaction-continuity-benchmark).

### Hook Stage Coverage

Moved detail: [`memory-decision/tracks-a-d.md#hook-stage-coverage`](memory-decision/tracks-a-d.md#hook-stage-coverage).

### Case Families

Moved detail: [`memory-decision/tracks-a-d.md#case-families`](memory-decision/tracks-a-d.md#case-families).

### Required Inputs

Moved detail: [`memory-decision/tracks-a-d.md#required-inputs`](memory-decision/tracks-a-d.md#required-inputs).

### Metrics

Moved detail: [`memory-decision/tracks-a-d.md#metrics`](memory-decision/tracks-a-d.md#metrics).

### Runner Shape

Moved detail: [`memory-decision/tracks-a-d.md#runner-shape`](memory-decision/tracks-a-d.md#runner-shape).

## Deterministic Boundary Tests

Moved detail: [`memory-decision/implementation-policy.md#deterministic-boundary-tests`](memory-decision/implementation-policy.md#deterministic-boundary-tests).

## Case Generation Policy

Moved detail: [`memory-decision/implementation-policy.md#case-generation-policy`](memory-decision/implementation-policy.md#case-generation-policy).

## Report Shape

Moved detail: [`memory-decision/implementation-policy.md#report-shape`](memory-decision/implementation-policy.md#report-shape).

## Implemented Files

Moved detail: [`memory-decision/implementation-policy.md#implemented-files`](memory-decision/implementation-policy.md#implemented-files).

## Rollout Plan

Moved detail: [`memory-decision/implementation-policy.md#rollout-plan`](memory-decision/implementation-policy.md#rollout-plan).

## Acceptance Criteria

Moved detail: [`memory-decision/implementation-policy.md#acceptance-criteria`](memory-decision/implementation-policy.md#acceptance-criteria).
