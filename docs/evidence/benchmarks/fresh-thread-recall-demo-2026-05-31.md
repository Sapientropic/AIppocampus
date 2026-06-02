# Fresh-Thread Recall Demo Evidence

Evidence date: 2026-05-31.

This report records the deterministic public-safe demo runner added for #285.
It is a product-shape demonstration for fresh-thread progressive recall, not a
real-history benchmark or leaderboard claim.

## Source Map

- Parent design issue: #281
- Demo issue: #285
- Runner:
  [`benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py`](../../../benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py)
- Runtime fixture contract:
  [`fresh_thread_demo.py`](../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_demo.py)
- Existing contracts reused:
  [`fresh_thread_scent.py`](../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_scent.py),
  [`fresh_thread_action.py`](../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_action.py),
  and
  [`fresh_thread_activation.py`](../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_activation.py)
- Tests:
  [`test_fresh_thread_demo.py`](../../../tests/aippocampus/test_fresh_thread_demo.py)
  and
  [`test_benchmark_fresh_thread_recall_demo.py`](../../../tests/aippocampus/test_benchmark_fresh_thread_recall_demo.py)

## What Was Demonstrated

The runner covers four public-safe positive flows:

- stress cue
- website cue
- gift cue
- fresh coding cue

It also covers four negative controls:

- broad stress prompt with too little anchor
- website prompt where preferences are irrelevant
- gift prompt where sensitive detail is suppressed
- fresh coding prompt where old project facts must not bleed into the current
  repository

Each flow is rendered across three arms:

- `no_memory`: baseline with no recall route.
- `hook_only`: scent/action contract without source reopen or active lock use.
- `active_recall`: agent-owned active recall may use ready/pending route
  handles, while specific claims still require source reopen.

The fixture data is synthetic and public-safe. It uses structured upstream
decision packets as input, so semantic judgement remains upstream of the runner
instead of being hard-coded as prompt-word checks.

The demo's task-context flags are also synthetic upstream fixtures. They
exercise the action contract after a foreground, sidecar, activation, or
deterministic repo/source layer supplies flags; they do not evaluate live prompt
semantic classification quality.

## Issue #302 Boundary Hardening

The #302 follow-up keeps this demo labeled as synthetic, while runtime tests now
cover the two real-history failure shapes that motivated the issue:

- `test_active_recall_lock.py` checks that thread-only refs do not advertise a
  ready active-recall lock.
- `test_aippocampus_prompt_hook.py` checks that a current-repo factual
  source-backed prompt does not use old-project clean-source evidence.
- `test_fresh_thread_demo.py` checks that the synthetic project-fact negative
  control routes to `current_checkout_required_read_current_repo_first`.
- `smoke_fresh_thread_real_history.py` now provides the separate sanitized
  real-history boundary smoke required to close #302; see
  [`fresh-thread-real-history-smoke-2026-06-02.md`](fresh-thread-real-history-smoke-2026-06-02.md).

## Issue #359 Threshold Boundary

The prompt hook can now report a context-aware `scent_threshold_policy` with
`base_threshold`, `effective_threshold`, reason-code adjustments, and a
`risk_boundary`. This makes the #281 first-turn and continuation routes more
measurable, but it does not change this demo's evidence boundary: synthetic
fresh-thread packets remain navigation fixtures, and any specific memory-backed
claim still requires source reopen.

## Local Result

The local deterministic run reported:

- 8 flows total
- 4 positive flows
- 4 negative controls
- 3 arms
- `privacy_safe=true`
- `no_unsupported_evidence=true`
- `negative_controls_pass=true`

## Reproduce

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_fresh_thread_recall_demo.py --json --output .tmp\fresh-thread-recall-demo.json
python tests\aippocampus\test_fresh_thread_demo.py
python tests\aippocampus\test_benchmark_fresh_thread_recall_demo.py
```

The `.tmp` JSON output is a local evidence artifact. Do not commit it unless a
future public-release process deliberately promotes a small audited sample.

## Can Claim

- The fresh-thread packet, action, activation, and source-reopen contracts can
  be demonstrated together with public-safe synthetic fixtures.
- The demo distinguishes no-memory, hook-only, and active-recall behavior.
- Negative controls are first-class outcomes, not hidden skips.
- Specific memory-backed claims stay source-reopen-gated.

## Cannot Claim

- No real-history fresh-thread recall quality claim.
- No live semantic-model quality claim.
- No competitor superiority or leaderboard result.
- No proof that private emotional, family, design, or coding memories are
  already covered in production.
