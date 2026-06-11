# Public Longitudinal Memory Benchmark

This page records the first public, deterministic benchmark slice for the
coding implicit-knowledge scenario in
[`docs/research/agent-coding-context-analysis.md`](../../research/agent-coding-context-analysis.md).
It is the evidence companion for GitHub issue #172.

Related implementation surfaces:

- #167 / `aippocampus_runtime.coding.rejected_route_probes` covers
  source-backed rejected-route Dream retrospective fixtures; the top-level
  `skills/aippocampus/scripts/coding_rejected_route_probes.py` path remains a
  compatibility shim.
- #169 / `benchmarks/aippocampus/benchmark_coding_decision_shadow.py` covers
  deterministic coding decision-shadow Tracks A-E.
- #171 / `benchmarks/aippocampus/benchmark_suite.py --profile public-fast`
  remains the fresh-clone deterministic profile and keeps omitted surfaces in
  `cannot_claim`.
- #407 / `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` owns the
  pre-registered #378 primary endpoint, paired seed/repeat strategy, and
  no-advantage rule for continuous-memory superiority claims. Public
  longitudinal fixtures can feed that registered design later, but they do not
  override the decision rule after results are known.
- #406 / `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` keeps the
  public longitudinal slices from being compared only against a bare continuous
  context strawman: `host_native_continuous_no_aippocampus` is the first
  Codex-style host-native compaction contract arm, while live host telemetry
  remains a separate evidence requirement.
- #409 / `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` now uses
  this page's public VCS hard-event discipline as a provenance source for
  `public_log_or_vcs_derived` + `holdout_blind` continuous-memory scenarios.
  These scenarios remain sanitized contract controls: the local React VCS
  fixtures and raw PR metadata are not checked in as a redistributable corpus.

Latest dated measurement:
[`public-longitudinal-users-measurement-2026-05-31.md`](public-longitudinal-users-measurement-2026-05-31.md).

Latest real public VCS smoke:
[`react-real-vcs-smoke-2026-05-31.md`](react-real-vcs-smoke-2026-05-31.md).

Latest 100+ gold real public VCS measurement:
[`react-real-vcs-100-gold-2026-05-31.md`](react-real-vcs-100-gold-2026-05-31.md).

Latest adversarial React VCS measurement:
[`react-real-vcs-adversarial-v2-2026-05-31.md`](react-real-vcs-adversarial-v2-2026-05-31.md).

Latest non-oracle React VCS source-disambiguation follow-up:
[`react-real-vcs-production-like-disambiguation-2026-06-04.md`](react-real-vcs-production-like-disambiguation-2026-06-04.md).

## Purpose

AIppocampus should help agents remember hidden engineering context across
months, projects, and context compactions without pretending the base model has
innate memory. The hard case is not "find a string from yesterday." It is
whether the system preserves the currently valid, source-backed project intent:

- rejected routes;
- tacit constraints;
- workaround rationale;
- stale assumptions corrected by the user;
- conditions that justify reopening an old decision;
- anti-drift negatives where similar future wording should not activate memory.

## Data Decision

The v1 public fixture is
[`benchmark_corpus/public_longitudinal_users/coding_implicit_v1.jsonl`](../../../benchmark_corpus/public_longitudinal_users/coding_implicit_v1.jsonl).
It uses checked-in synthetic pseudo-users under `CC0-1.0`. Treat it as a
scoring-contract smoke, not the flagship Dream-recall benchmark.

This is deliberate but limited. The synthetic fixture proves the report shape:
given explicit source events, gold claims, probes, and external predictions,
the runner can score source attribution, forbidden drift, and anti-drift
negatives without private data. It cannot prove that a system will notice every
future event that should have been flagged.

LoCoMo is a real public long-conversation control, not a true cross-conversation
or cross-month user-memory proof. The official repository describes ten
very long-term conversations, chronological sessions, dialogue ids, and
annotated QA evidence ids, but the scorer asks for evidence from within the
same conversation sample. AIppocampus treats each LoCoMo sample as a
`long_conversation_public_control` and scores source-turn evidence retrieval
with:

```powershell
New-Item -ItemType Directory -Force benchmark_corpus\locomo | Out-Null
Invoke-WebRequest https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json -OutFile benchmark_corpus\locomo\locomo10.json
python benchmarks\aippocampus\benchmark_locomo_public_users.py --json
python benchmarks\aippocampus\benchmark_locomo_public_users.py --predictions .tmp\locomo-evidence-predictions.jsonl --json
```

The default no-predictions run is a gold oracle scorer self-check: it supplies
LoCoMo gold evidence ids as predictions to prove report/scorer semantics. Do
not read the perfect default score as AIppocampus system retrieval performance;
use the case pack and `--predictions` path below for that.

For public replication, generate the model-facing local inputs first:

```powershell
python benchmarks\aippocampus\benchmark_locomo_public_users.py --case-pack-output .tmp\locomo-case-pack.json --prediction-template-output .tmp\locomo-predictions.jsonl --json
```

`locomo-case-pack.json` includes source dialogue and question text, but does
not include answers or gold evidence ids. `locomo-predictions.jsonl` contains
one row per case with empty `evidence_ids`. A system under test should read the
case pack, fill the prediction template with retrieved dialogue ids, and then
call the scorer with `--predictions`.

The raw `locomo10.json` file stays local/ignored under the upstream CC BY-NC
4.0 license. Default reports are sanitized: they include case ids, evidence
ids, and question/answer hashes, but no dialogue text, question text, or answer
text. The current local snapshot has 10 users, 272 sessions, 5,882 dialogue
turns, 1,986 QA cases, and 1,973 evidence-linked cases.

When the local LoCoMo file is absent, the LoCoMo retrieval, text-QA, and
answer-usefulness runners return `status=skipped_missing_dataset` with
`ok=true`; retrieval/answer-usefulness also use
`quality_gate_status=not_scored` where they own a gate. That skip payload means
the diagnostic/report contract was generated successfully; it is not a
retrieval or answer-quality score.

#1158 adds a separate LoCoMo text-QA harness that registers the same public
conversation sessions through the standard source-backed retrieval adapter,
then optionally asks a fixed reader to answer from bounded candidate source
lines:

```powershell
python benchmarks\aippocampus\benchmark_locomo_qa.py --questions 25 --reader-mode dry-run --json --output benchmark_corpus\reports\locomo-text-qa-dry-run.json
$env:AIPPOCAMPUS_LOCOMO_READER_API_KEY="<provider key>"
python benchmarks\aippocampus\benchmark_locomo_qa.py --questions 100 --reader-mode provider --reader-model <fixed-reader-model> --reader-base-url <openai-compatible-url> --partial-output benchmark_corpus\reports\locomo-text-qa-provider.partial.json --provider-budget-checkpoint benchmark_corpus\reports\locomo-text-qa-provider.budget.json --max-provider-calls 100 --max-provider-total-tokens <token-cap> --max-provider-estimated-cost-usd <usd-cap> --json --output benchmark_corpus\reports\locomo-text-qa-provider.json
```

CLI stdout is static by design; use `--output` for the sanitized JSON report.
Provider mode now reuses the shared provider execution budget helper and stops
before the first reader call when max calls plus a token/cost budget and
checkpoint paths are missing. Dry-run remains cheap and does not require budget
flags.
The report keeps retrieval, answer quality, source citation, latency,
token/cache, cost, and failure taxonomy in separate fields. It preserves the
dataset-provided LoCoMo `category` values as `locomo_category_*` question-type
slices, but does not remap them to semantic labels. The fixed reader sees the
question and bounded source lines only; the serialized report omits raw
dialogue, question, answer, source text, provider response text, local paths,
and credentials. A dry-run proves schema and report boundaries; a dated
provider run is still required before adding any current answer-quality claim.

#400 adds a separate LoCoMo answer-usefulness prototype on top of that
retrieval layer:

```powershell
python benchmarks\aippocampus\benchmark_locomo_answer_usefulness.py --json
python benchmarks\aippocampus\benchmark_locomo_answer_usefulness.py --predictions .tmp\locomo-answer-predictions.jsonl --answer-model <fixed-answer-model-name> --json
```

This second-stage runner scores `source_evidence_retrieval`,
`context_gathering`, `answer_generation`, `source_citation`, and
`unsupported_inference_refusal` as separate report layers. The answer model
input should come from the local LoCoMo case pack and must not receive gold
answers or gold evidence ids. The deterministic judge can see gold labels for
scoring, but its output is benchmark telemetry, not source truth. Keep this as
a prototype for product-layer usefulness under fixed answer-model/evaluator
settings; do not fold it into Track B retrieval-only metrics or use it for
SOTA, LongMemEval-V2, or external-system superiority claims.

The answer-usefulness runner deliberately keeps report/artifact generation
separate from the quality gate. A run can write a sanitized answer template and
report while still returning exit code `1` when `quality_gate_ok=false`. Read
`report_generation_ok`, `artifact_generation_ok`, and `quality_gate_ok`
together: successful setup artifacts are not evidence that the fixed answer
model/evaluator path met the usefulness contract.

Public conversation corpora remain valuable, but they should not be the
positive coding source:

- [LongMemEval-V2](https://huggingface.co/datasets/xiaowu0162/longmemeval-v2)
  is the closest public long-term agent-memory control: its dataset card says
  it covers web and enterprise agents, 451 curated questions, and 1,870 task
  trajectories, with abilities including workflow knowledge, environment
  gotchas, and premise awareness. It is a near-neighbor, not a coding project
  decision-shadow source.
- [SWE-Hero OpenHands trajectories](https://huggingface.co/datasets/nvidia/SWE-Hero-openhands-trajectories)
  are a useful coding-agent replay source: the dataset card describes 34k
  OpenHands trajectories for SWE-style tasks. They are task trajectories, not
  months-long decision histories.
- [LoCoMo](https://github.com/snap-research/locomo) is useful for same-dialogue
  long-conversation evidence retrieval; its repository describes ten long-term
  conversations with annotated QA and event summaries. Do not use it as proof
  that AIppocampus handles cross-thread or cross-project longitudinal memory.
- [WildChat](https://huggingface.co/datasets/allenai/WildChat-4.8M) is useful
  for broad chat-distribution replay and false-activation checks, but its card
  describes per-conversation metadata such as hashed IP and headers. AIppocampus
  should not use that to construct public "same-user" identities.

The flagship positive track should move to VCS-derived future-event gold:

- [MSR 2020 pull-request dataset](https://2020.msrconf.org/details/msr-2020-Data-showcase/6/A-New-Dataset-for-Pull-Request-Acceptance):
  the official MSR page describes 96 features over 11,230 projects and
  3,347,937 pull requests. PR acceptance/rejection is a hard future event.
- [Pull Request Decisions Explained](https://research.tudelft.nl/en/publications/pull-request-decisions-explained-an-empirical-overview):
  the later empirical overview reports 95 factors over the same 3,347,937 PR
  corpus. Use it for feature/decision-factor taxonomy, not as a semantic judge.
- [Code review as decision-making](https://link.springer.com/article/10.1007/s10664-025-10791-2):
  use the Gerrit changeset/patchset reasoning model as a labeling pattern for
  patch supersession and review-rationale arcs.
- [CppSATD](https://zenodo.org/records/15284981):
  the Zenodo record describes 531,367 comments with 13,069 SATD comments
  identified and manually classified into SATD types. These comments are a
  direct source for workaround-rationale gold.
- Repository-native events such as issue reopen, commit revert, patchset
  supersession, and removal of a SATD/workaround comment should become the
  future-window labels.

The future-event track must score recall. The holdout window must enumerate all
flag-worthy hard events, so a system that stays silent can receive clean
false-negative penalties. For `reopen_condition` and other forward-looking
families, only brittle events count: literal merge/reject/reopen/revert/
supersede/removal. Soft "seems related" cases should be discarded rather than
sent to an LLM judge.

Fixture construction must also report candidate-discovery bias. A perfect
source-window score over a narrow candidate universe can still overstate
natural engineering-history coverage. VCS fixture builders should carry
license-safe discovery metadata such as source surface (`title`, `body`,
`comment`, `label`, `commit-message`), query-term family (`revert`,
`workaround`, `reland`, `again`, plus synonym expansions such as `undo`,
`rollback`, `backout`, and `patch`), manual inclusion/exclusion reason codes,
family balance, and sampled miss rate. These are audit telemetry, not source
truth: do not emit raw PR bodies, review text, search payloads, local paths, or
non-redistributable snippets.

Precision reporting must keep the source-backed contract separate from
diagnostic precision. `future_event_flag_precision` requires both a flag-worthy
event id and the required source support. A diagnostic event-identity precision
may help debug predictions that found the right public event id while missing
source support, but it must not become the headline quality gate.

Negative anti-drift controls should be labeled when they contrast event
families. Use `anti_drift_family_under_test` for the memory family that should
stay quiet and `anti_drift_contrast_family` for the tempting but wrong family.
The benchmark runner reports `negative_cross_family_count` and
`negative_cross_family_violation_count` so cross-family false activations do not
hide inside a generic false-positive total.

Source degradation should be explicit instead of hidden inside generic false
negatives. Datasets may include `truncated_source`, `redacted_source`,
`missing_source_id`, and `partial_support` controls. Redacted or truncated
sources can still be source ids when the benchmark contract says enough support
remains; `missing_source_id` and `partial_support` cannot satisfy full
source-backed support by themselves.

Hard public outcomes also create a contamination risk: a pretrained model may
already know a famous PR was later reverted or merged. The benchmark should
measure that risk instead of pretending it is absent. Every public VCS report
should include a closed-book arm that gets the question/event setup without the
past source window. If closed-book performance is close to source-window
performance, the score is not evidence that source-backed recovery did the
work.

Contamination controls, in descending reliability:

- Time split: prefer holdout events created after the evaluated model's
  training cutoff. This must be refreshed over time.
- Private real history: valid for private behavior lift, but report separately
  from public reproducible scores.
- Counterfactual perturbation: flip the public trajectory's decision/constraint
  so memorized public outcomes become confident wrong answers.

The same hard-event discipline should move inside agent rollouts. When agents
write code, PR text, review notes, and issues, the decision shadow no longer
lives only in human VCS commentary. It often appears first as behavior:

- a tool call failed;
- a test failed;
- an edit was reverted;
- a route was abandoned after an observation;
- a later run repeated the same failed route.

For benchmark purposes, distinguish behavior-trace rejection from narrative
rejection. A behavior-trace rejection has deterministic evidence in the rollout.
A narrative rejection is only an assistant message claiming that something was
bad. Only the first kind can support `rejected_route`, `tacit_constraint`, or
`workaround_rationale` gold. The second is weather unless it is linked to a
behavior-backed source event.

This is also now reflected in clean source: `build_clean_source.py` writes a
structured `events.jsonl` lane for Codex rollouts. Public-safe rollout source
records carry bounded fields such as `tool_name`, `command_class`, exit status,
timestamp, source refs, and input/observation hashes. Raw stdout, full diffs,
screenshots, local paths, full shell commands, and secrets remain audit/source
material, not default recall payload.

The behavior lane also carries bounded breadcrumbs for benchmark substrate:
`tool_intent`, `command_family`, `test_target_class`, `failure_family`,
`path_categories`, safe `path_fingerprints`, and generated-file flags. These
fields let fixture builders preserve the difference between "a test/check
actually failed against this category of target" and "the assistant later
narrated that a route was bad," without exposing private commands or paths.

Continuous-agent benchmark tracks should read the critical-operation integrity
diagnostic over clean-source `events.jsonl` and count uncovered operation
families as explicit coverage gaps. They should not reopen raw rollout payloads
or treat assistant narration as operation fact support unless a row joins back
to a behavior-backed event or curated event sidecar.

## Flagship Longitudinal Tracks

The real public longitudinal benchmark should target the places where ordinary
R@K and gate-decision tests are weakest. These tracks should be reported
separately; a single aggregate score would hide the hard failures.

1. Temporal override: a user changes a preference over time, sometimes
   implicitly and sometimes only within a project scope. Score
   `current_preference_accuracy`, `override_latency`, and
   `scope_specificity`. The runner must distinguish the latest effective
   source from older contradictory sources, not merely retrieve both.
2. Implicit constraint drift: a repeated behavior pattern implies a constraint,
   then the behavior shifts. Score `implicit_constraint_precision`,
   `drift_sensitivity`, and `over_generalization_rate`. Behavior must be
   source-backed: tool choice, edits, tests, or repeated user corrections count;
   a model-inferred habit without source support does not.
3. Cross-project contamination: two similar repositories or subprojects use
   different conventions. Score `cross_project_leak_rate`,
   `context_switch_latency`, and `same_library_version_precision`. Same-library
   version differences such as React 18 vs 19 must remain scoped.
4. Intentional forget compliance: the user asks the system to forget content,
   a full turn, or one part of a mixed source. Score `forget_compliance_rate`,
   `selective_preservation`, and `forget_depth` across clean source, semantic
   labels, dream candidates, and derived indexes. Mentioning that something was
   forgotten can itself violate the request.
5. Post-compaction gap: a long discussion is compacted after only the final
   decision survives in the summary. Score `post_compaction_detail_recall`,
   `compaction_summary_fidelity`, and `audit_trail_preservation`, especially
   for rejected alternatives and decision rationales.
6. Dream semantic quality: measure the content of generated dream hypotheses,
   not only activation frequency. Score `dream_amplification_precision`,
   `dream_fabrication_rate`, and `dream_relevance_ranking`. The key failure is
   inventing associations or merging unrelated decisions while still looking
   confident.

The VCS future-event runner is the right scaffold for the public hard-event
half of these tracks, but the next data slice should be real public repository
history, not synthetic rows. Curated Linux kernel, React, or similarly active
repositories should contribute merge/revert/reopen/supersede/removal events
with source URLs, timestamps, repository scope, and closed-book predictions.
Keep raw code and large raw review text out of the public fixture unless the
license and redistribution boundary are explicit; use local ignored reports for
large curated rows.

The first real public VCS smoke is now
[`react-real-vcs-smoke-2026-05-31.md`](react-real-vcs-smoke-2026-05-31.md).
It runs this scaffold on three curated `facebook/react` event clusters and
separate source-window, empty, source-stripped closed-book, and counterfactual
perturbation arms.

The first 100+ gold real public VCS measurement is now
[`react-real-vcs-100-gold-2026-05-31.md`](react-real-vcs-100-gold-2026-05-31.md).
It runs the builder on 105 curated `facebook/react` gold events plus 105
anti-drift negatives, keeps source-window / empty / closed-book arms separate,
adds a 105-event counterfactual perturbation control, and reports
`rejected_route`, `reopen_condition`, and `workaround_rationale` separately.

The sharper adversarial follow-up is
[`react-real-vcs-adversarial-v2-2026-05-31.md`](react-real-vcs-adversarial-v2-2026-05-31.md).
It adds dual-source counterfactuals, temporal override chains, family
cross-contamination, behavior-only rollout gold, adversarial paraphrase,
lexical near-miss anti-drift, narrative-only negatives, and abstention cases.
The bad-control arms deliberately fail: stale/decoy sources fall to 30% recall,
keyword-surface matching produces 57 false positives, and overactive all-flags
gets 0% anti-drift pass.

The first non-oracle production-like source-disambiguation follow-up is
[`react-real-vcs-production-like-disambiguation-2026-06-04.md`](react-real-vcs-production-like-disambiguation-2026-06-04.md).
It reuses the adversarial V2 fixture, builds a local past-window source index,
and ranks candidates without using `required_past_source_ids` as prediction
input. The run picks the current/effective source on the dual-source and
temporal-override tracks and, in the 2026-06-09 rerun, suppresses all 30
explicit-cue lexical near-miss hard negatives. It remains source-disambiguation
evidence,
not live model quality or wild VCS corpus quality.

## Runner

Entrypoint:

```powershell
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --json
```

Score an external system by providing predictions:

```powershell
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --predictions .tmp\public-longitudinal-predictions.jsonl --json
```

Prediction rows can be JSON or JSONL:

```json
{"case_id":"plu-cache-001","decision":"surface","claim_ids":["cache-redis-rejected-no-daemon"],"source_event_ids":["cache-e001"]}
```

LoCoMo evidence predictions use source dialogue ids:

```json
{"case_id":"locomo:conv-26:qa:0001","evidence_ids":["D1:3"]}
```

## Metrics

- `overall_score`: contract-smoke score only. Do not use it as a headline
  wedge metric.
- `decision_accuracy`: exact expected decision match.
- `required_claim_full_recall_rate`: whether required hidden context was
  recovered for surface/reopen cases.
- `source_event_full_recall_rate`: whether required claims were backed by the
  right source event ids.
- `forbidden_claim_violation_count`: unsupported or forbidden drift.
- `source_event_false_positive_count`: source ids attached to the wrong case.
- `anti_drift_pass_rate`: suppression behavior for unrelated same-token future
  tasks.
- `reopen_decision_accuracy`: whether valid reopen-condition probes are
  recognized without turning old rejections into permanent bans.

LoCoMo control metrics:

- `full_evidence_recall_rate`: whether every required QA evidence dialogue id
  was recovered.
- `exact_evidence_match_rate`: whether the retrieved evidence ids match the
  gold ids without extras.
- `mean_evidence_recall` / `mean_evidence_precision`: partial evidence quality.
- `false_positive_evidence_id_count`: extra source ids attached to cases.
- `by_category`: LoCoMo QA category slices. Keep these separate from coding
  implicit-knowledge families.

LoCoMo is a same-conversation control. It does not measure cross-conversation
preference override, cross-project contamination, intentional forgetting, or
post-compaction detail recovery.

Interpret family metrics separately. Do not average easy explicit-correction
cases with tacit/workaround/reopen cases and report the aggregate as the
AIppocampus moat. A public report should foreground at least:

- rejected-route recall / precision;
- tacit-constraint recall / precision;
- workaround-rationale recall / precision;
- reopen-condition recall / precision;
- anti-drift negative pass rate;
- false-positive source-event rate.

The future-event track additionally needs:

- `future_event_gold_count`;
- `future_event_flag_recall_rate`;
- `missed_reopen_event_count`;
- `missed_constraint_violation_count`;
- `hard_event_false_activation_count`;
- `closed_book_recall_rate`;
- `source_over_closed_book_recall_lift`;
- structural-disagreement-vs-self-rated-uncertainty predictive comparison.

The last metric is the core Dream wager: compare a deterministic structural
disagreement arm against a model self-reported `uncertainty_reduction` arm, and
measure which better predicts hard holdout support. If disagreement predicts
future support better than self-assessment, the Dream scoring philosophy has a
public, falsifiable foundation.

## Claim Shape

Supports:

- public, reproducible pseudo-user scoring for coding implicit knowledge;
- public LoCoMo same-conversation long-dialogue evidence retrieval;
- deterministic source-event attribution checks;
- a public contract other memory systems can implement against;
- a smoke-tested report shape for later VCS-derived future-event recall.

Important limits:

- private real-history coding continuity quality;
- real same-user longitudinal identity;
- live Dream worker quality;
- answer generation quality;
- external baseline superiority;
- recall over a complete future window;
- tacit/workaround/reopen performance on wild VCS histories;
- LoCoMo performance as evidence for cross-conversation user memory or coding
  tacit-constraint recall;
- AIppocampus superiority over realistic host-native continuous workflows or
  live host-native compaction behavior;
- a single headline score that validates the AIppocampus wedge.

## Current Implementation Slice

The current benchmark slice adds `vcs_future_event_*` and rollout-behavior
fixtures with this contract:

- Past window: rejected PR/review rationale, SATD/workaround comments, or
  earlier patchset reasoning.
- Dream candidate: predicted future risk, reopen condition, or constraint
  violation, emitted before the future event.
- Future window: hard events only, such as PR accepted/rejected, issue reopened,
  commit reverted, patchset superseded, or SATD/workaround comment removed.
- Scoring: count both supported flags and missed hard events. No soft semantic
  judge for forward-looking labels.
- Production-like retrieval: source-disambiguation reports whether a multi-source
  support chain entered the candidate pool separately from whether the route is
  actionably foreground-visible. Successful current events may keep old failed
  routes as diagnostic candidates, but the actionability gate must suppress them
  unless a separate currentness rule proves they still apply.
- Reporting: no single aggregate headline; family tables are the public result.

The next version should replace the synthetic rows with curated public
MSR/Gerrit/SATD/agent-rollout rows while keeping this same scoring boundary.

The first scaffold for this contract is now:

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --baseline empty --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --predictions .tmp\vcs-source-window.jsonl --closed-book-predictions .tmp\vcs-closed-book.jsonl --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --event-metadata .tmp\react-real-vcs-adversarial-v2\event-meta.json --production-like-retrieval --allow-non-cc0-dataset --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --production-like-retrieval --source-disambiguation-top-k 2 --json
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --input .tmp\public-vcs-links.jsonl --output .tmp\vcs-future-events-built.jsonl --json
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --clean-source-events .tmp\clean-source\events.jsonl --links .tmp\rollout-event-links.jsonl --output .tmp\rollout-future-events.jsonl --allow-non-cc0-output --json
```

Fixture:
[`benchmark_corpus/public_longitudinal_users/vcs_future_events_v1.jsonl`](../../../benchmark_corpus/public_longitudinal_users/vcs_future_events_v1.jsonl).
It is still synthetic and only proves recall-aware scoring semantics, but it
already has the critical property missing from the pseudo-user contract smoke:
the future window enumerates all flag-worthy hard events, so silence produces
false negatives.

Rollout behavior fixture:
[`benchmark_corpus/public_longitudinal_users/rollout_behavior_events_v1.jsonl`](../../../benchmark_corpus/public_longitudinal_users/rollout_behavior_events_v1.jsonl).
It is also synthetic, but it encodes the new boundary: assistant narrative
sources can appear in the past window, yet they cannot be required gold support
for a flag-worthy future event unless the row also has behavior evidence.

Builder:
[`benchmarks/aippocampus/build_vcs_future_event_fixture.py`](../../../benchmarks/aippocampus/build_vcs_future_event_fixture.py).
It converts already-curated public VCS or rollout event-link rows into the
scoring schema. It can also join clean-source `events.jsonl` behavior rows with
a curated link file. It deliberately does not scrape public datasets or infer
soft labels.

The runner now exposes `contamination_control.closed_book` when
`--closed-book-predictions` is provided. Public claims should report the
source-over-closed-book lift; without that lift, public VCS scores are
contamination diagnostics rather than source-backed memory evidence.

The same runner also exposes `--production-like-retrieval` for source
disambiguation. That arm builds a local candidate index from each case's
`past_window` and uses `required_past_source_ids` only for grading, not ranking.
Report it separately from `source_window_oracle_contract` and do not call it
live model quality unless a live provider/model is actually used.

Raw outputs, external predictions, and large follow-up reports belong in
`.tmp/` or `benchmark_corpus/reports/` unless a future change deliberately
promotes a curated public report.
