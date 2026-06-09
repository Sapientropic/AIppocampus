# AMemGym Official Live-Provider Blocker - 2026-06-09

Role: dated blocker note for #958.
Status: closes the ownerless deferred slice by recording why a live/provider
official AMemGym `v1.base` fixed-arm score is not yet safe or reproducible.

This note does not add an AMemGym score. It preserves the current claim
boundary and names the next unblock condition.

## Source Check

- Official repository: <https://github.com/AGI-Eval-Official/amemgym>
- Dataset: <https://huggingface.co/datasets/AGI-Eval/AMemGym>
- Local upstream HEAD check on 2026-06-09:
  `git ls-remote https://github.com/AGI-Eval-Official/amemgym.git HEAD`
  returned `ffcd18857a3e2b2c61f00730ebdec676e27d3e87`.
- The official AMemGym dataset card points usage details to the same GitHub
  repository. The older `AGI-Eval/AMemGym` GitHub path is not the live
  repository path.

## Evidence State

| Layer | Current state | Claim boundary |
| --- | --- | --- |
| Protocol compatibility | Complete `local-scripted` official run exists for `overall`, `upperbound`, and `random` on full public `v1.base`; normalized `Memory=1.0` is a protocol artifact. | Not a live LLM/provider score, Native baseline, or AIppocampus product-quality result. |
| Live model/provider quality | The 2026-06-06 OpenRouter Native attempt was partial: `overall` had 6/20 items, `upperbound` had 38/882 choice evaluations and no utilization metrics, `random` completed. #1052 adds bounded subset, resume-skip, phase-state, and checkpoint reporting for the next attempt. | Not an AMemGym score; only execution/progress evidence. |
| Source-backed overlay fidelity | Local fixture overlay and official `BaseAgent` adapter arms can report source-backed boundaries, and semantic-sidecar arms require prepared worker metadata. | Overlay fidelity is separate from official accuracy, diagnosis, utilization, and leaderboard claims. |
| Cost/latency | The bridge records subprocess elapsed time and redacts credentials; #1052 checkpoints explicitly report provider cost as unavailable when no stable usage field is present. | Provider billing/token cost is not claimable until raw official outputs or provider metadata expose a stable sanitized extraction path. |

## Blocker

A full live/provider official `v1.base` fixed-arm score is still blocked even
after the #1052 bridge update. The bridge can now make a debugging run bounded,
resumable, and publicly auditable, but no complete live/provider fixed arm has
been produced and reviewed yet:

- The previous live OpenRouter Native attempt ran for roughly two hours and was
  stopped while `upperbound` was still running.
- `--max-cases` can bound a debugging slice, but subset output is explicitly
  `progressive_subset_debug_only` and cannot retire the full public `v1.base`
  score boundary.
- `--resume` skips complete official summary artifacts and `--checkpoint`
  records sanitized phase state; partial upstream surfaces still require a later
  operator continuation/review rather than an automatic score claim.
- Provider/model identity can be pinned, but the public report cannot yet
  extract stable token/billing cost from official outputs without either raw
  local artifacts or provider-specific metadata.
- `overall`, `upperbound`, and `random` must be complete before normalized
  `Memory` can be interpreted for a live/provider fixed arm.
- Native/RAG/AWI/AWE parity arms should remain deferred until at least one
  bounded live fixed arm is complete and reviewed; otherwise parity would
  multiply cost and artifact-risk without improving claim quality.
- The AIppocampus semantic-sidecar official arm remains blocked for claimable
  semantic-worker evidence until a pre-score materializer writes reviewed
  working-memory / semantic sidecar artifacts and `adapter_metadata.json` proves
  those surfaces were present.

## Next Unblock Condition

Before any Current Claim Snapshot row can cite AMemGym live/provider quality,
produce a later dated note with all of these:

- official upstream commit and dataset/config identifiers;
- pinned provider, model id, and official command shape;
- complete `overall`, `upperbound`, and `random` outputs for the fixed arm;
- sanitized score summary that separates `Overall`, `UB`, `Random`, normalized
  `Memory`, source-backed overlay fields, and cost/latency;
- no committed raw official rows, model transcripts, provider credentials,
  local absolute paths, or raw provider billing payloads;
- explicit decision on Native/RAG/AWI/AWE parity arms after the bounded fixed arm
  has passed review.

Until then, AMemGym remains a staged external benchmark adapter with protocol
evidence and explicit live-score blockers, not a public AIppocampus score.
