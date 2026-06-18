# Benchmark Report Layer

Role: dated benchmark report router.
Status: report-layer index; not the current claim snapshot.

This folder holds dated markdown reports and small promoted JSON artifacts by
benchmark family. Start from [`../README.md`](../README.md),
[`../../benchmark-evidence-map.md`](../../benchmark-evidence-map.md), or
[`../../current-claims.md`](../../current-claims.md) before treating any report
as current evidence.

## Report Router Task Card

current_claim_owner: `docs/evidence/current-claims.md`.

latest_promoted_report: `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.md`.

claim_safe_next_action: open `docs/evidence/current-claims.md` and the family
README before treating any dated report as current evidence.

safe_next_action: open the family README first, then run
`python tools\aippocampus\docs\check_docs_health.py --json` before promoting a
dated report into a current claim row.

historical_boundary: reports are provenance and bounded evidence; they do not
become present-tense claims until Current Claims or a verified issue route owns
the promotion.

## Families

| Family | Use |
| --- | --- |
| [`amemgym/`](amemgym/) | AMemGym live-provider and adapter blocker reports. |
| [`benchmark-family/`](benchmark-family/) | Cross-family promotion candidate reports. |
| [`cognitive-runtime/`](cognitive-runtime/) | Cognitive Observatory and runtime-readout completeness reports. |
| [`coordination/`](coordination/) | Natural handoff and Episode/Arc route-sequence usefulness reports. |
| [`e2e50/`](e2e50/) | Public-pack boundary plus private/local seed, annotation-readiness, and field-validation artifacts. |
| [`field-journey/`](field-journey/) | Field continuity, Journey replay, map-rot, and demo fixture reports. |
| [`fresh-thread/`](fresh-thread/) | Fresh-thread recall, host-surface, segmented merge, and preactivation reports. |
| [`hippocampal/`](hippocampal/) | Hippocampal recall, hard-negative, and comparison reports. |
| [`longmemeval/`](longmemeval/) | LongMemEval retrieval, rerank, source-worker, and fixed-reader reports. |
| [`multimodal/`](multimodal/) | Multimodal corpus, ingest, NIAH, pollution, and provider reports. |
| [`public-longitudinal/`](public-longitudinal/) | Public longitudinal user, React VCS, rollout, and sparse-provenance reports. |
| [`public-reliability/`](public-reliability/) | Public reliability gauntlet JSON artifacts. |
| [`recall-navigation/`](recall-navigation/) | Recall router, attention, continuity-loop, and degradation reports. |
| [`state-bench/`](state-bench/) | STATE-Bench preflight and defer-decision artifacts. |

## Boundary

Reports are provenance, not the source of current claims. If a report supersedes
or narrows a claim, update [`../../current-claims.md`](../../current-claims.md)
or [`../../benchmark-evidence-map.md`](../../benchmark-evidence-map.md) and keep
only a short pointer here.
