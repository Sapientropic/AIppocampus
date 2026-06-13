# Reflection AAR V2 Hardening Review

Date: 2026-06-05.

This is the scripted review/protocol closeout for #332. It records the boundary
between the reflection-space topology/feedback MVP and the first AAR strategy
reader that can consume reviewed adjustment rows.

## Scope

The implemented reader is
`skills/aippocampus/scripts/aippocampus_runtime/reflection/aar_v2.py`.

It consumes public-safe, source-backed correction or postmortem rows and
produces advisory AAR v2 records for one action class:
`specific_memory_source_claim`. At action time, it can nudge the agent to reopen
clean source before making a specific memory/source claim from weak support such
as `scent`, `candidate`, or `dream`.

This is a strategy-reader hardening slice, not a visual reflection-space
product and not a live hook installation.

## Scripted Review Protocol

The deterministic review protocol is:

1. Build candidate rows only from accepted source-backed corrections or
   postmortems with compact source refs.
2. Reject stale, unsupported, or rejected review rows before they become AAR
   records.
3. Match nudges only when the foreground action is a specific memory/source
   claim from weak support and clean source is not already visible.
4. Preserve counterfactual hypotheses as advisory policy support. Even a
   supported counterfactual does not become causal truth.
5. Summarize feedback rows as pruning/demotion inputs only; never mutate clean
   source or Journey history.

The fixture tests cover:

- one positive adjustment becoming an advisory nudge;
- suppression when visible source is already present or the action is low risk;
- provisional versus supported counterfactual status;
- stale, unsupported, and rejected review rows being ignored;
- feedback metrics for useful, ignored, false-positive, stale, and prevented
  failure signals.

## Current Claim

Can claim:

- reflection-space feedback has a first deterministic AAR strategy reader;
- the reader is source-backed, no-write, and advisory-only;
- stale, unsupported, and rejected reviewed rows do not become AAR v2 nudges;
- source-truth, clean-source mutation, and Journey-history mutation boundaries
  are preserved in the report and tests.

Cannot claim:

- polished reflection-space or constellation/star-map UI;
- human UI helpfulness or annoyance calibration;
- live hook behavior change;
- scheduler-wide AAR enforcement;
- real user behavior change;
- causal proof that a nudge would have prevented a failure;
- any factual memory claim from an AAR nudge without clean-source reopen.

## Verification

Focused verification:

```powershell
python -m unittest tests.aippocampus.test_aar_v2_action_time_nudges
```

Before claiming broader repository health for this slice, also run:

```powershell
python tools\aippocampus\docs\check_docs_health.py --json
python tools\aippocampus\run_tests.py --tier pr
```
