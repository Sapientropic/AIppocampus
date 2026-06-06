# Next Iteration Plan

This is the short handoff for the next development slice after the current
technical-debt baseline. It points to canonical docs instead of duplicating
their full contracts.

Keep this file as a task queue and preservation checklist. Detailed Stage 0-5
evidence belongs in `stage-0-5-readiness.md`; dated command evidence belongs in
`public-readiness-verification.md`.

Active planning view: the public GitHub Project
[`AIppocampus Roadmap`](https://github.com/users/Sapientropic/projects/1)
tracks the issue slices extracted from this file and related roadmap/readiness
docs. Use the Project for status/filtering; keep this file as the source-backed
handoff context.

## Current Product Focus

The next public-facing slice should keep the default lane narrow: import or
register source, search/recall, reopen source, and carry the source-backed
context forward. Use `docs/roadmap.md#product-layers` for the layer map and
`docs/guides/public-core-boundary.md#core-complexity-budget` before promoting a
heavier mechanism into Core.

Open issues are for executable slices. If a topic cannot plausibly become a
fixture, doc, CLI, runtime slice, or verified cleanup within 1-2 weeks, park it
as a Discussion or a seed under `docs/research/seeds/` until it can be cut
smaller.

### Open Issue Cleanup Review

As of the 2026-06-06 issue-cleanup implementation pass, every open issue body
and comment should be treated as a hypothesis until checked against code,
docs, and evidence. Recent owner comments explicitly reopened several broad
parents for sliced execution; those comments override older cleanup rows that
called the same issues complete or moved out of the foreground.

Open issues remain an execution queue, not an idea vault. Close an issue only
when the branch supplies the evidence its latest comments require, or when the
work is deliberately moved to a canonical roadmap/research surface with a clear
reason that it should no longer be an open executable item.

| Layer | Current issues | Current disposition |
|---|---|---|
| Public entry and docs IA | #801, #803 | Close together when the public site leads with the fastest useful setup path, magic moments are first-class, `docs/architecture/` has a role index, docs health guards that index, and responsive site QA passes. |
| Architecture lifecycle policy | #810, #811 | Close with small current-contract docs plus deterministic no-write readouts: edge capture vs async consolidation state flow, and topology anchor weights as lifecycle/navigation pressure rather than source truth. |
| Core route actionability | #201, #786, #791 | Keep open until high-confidence local/semantic routes become actionable reopen routes or bounded evidence without forcing the foreground agent into broad manual grep. #791 should not close while #786 still lacks live route-quality proof. |
| Fresh-thread and question continuity | #248, #281 | Keep open as product-quality owners. Existing fixtures are substrate; closing needs source-ref rejoin, fallback, answer-quality, and fresh-thread usefulness evidence. |
| Cognitive runtime evidence | #163, #310, #311, #575, #576, #663, #752 | Keep open, but cut tightly. Existing substrate/report slices do not prove live/private or user-visible lift. Focus next PRs on Dream behavior evidence, Journey hint timing, live correction capture, load calibration, Observatory coverage, Episode/Arc source reopen, and no-key host-agent fallback. |
| Benchmark and retrieval proof | #309, #378, #742 | Keep open as falsifiable evidence owners. Do not close with architecture prose; #742 needs official AMemGym outputs, #378 needs continuous-memory comparison evidence, and #309 needs measured source-joined retrieval/rerank/vector/filter behavior. |
| Provider credential onboarding | #784 | Keep open for real cross-platform credential-store smoke and quality evidence. The plan/apply/undo bridge exists but does not prove OS credential-store readiness. |

Current open queue at this pass: #163, #201, #248, #281, #309, #310, #311,
#313, #378, #574, #575, #576, #663, #742, #752, #784, #786, #791, #801, #803,
#810, and #811.

## Current Baseline To Preserve

- Public repo boundary: no raw rollouts, registry exports, private anchors,
  generated indexes, or local paths in Git.
- Public-core licensing and adapter boundaries live in
  `docs/guides/public-core-boundary.md`; do not mirror that contract into release
  notes, package metadata, or roadmap prose beyond a short pointer.
- Default generated artifacts live under
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/...`.
- `.aippocampus/` remains explicit compatibility/export/debug output only.
- The local MCP server exists at
  `skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py` and currently exposes
  read-mostly clean-source/registry tools plus explicit `register_thread`.
  Common tool failures return stable JSON error codes/details for client use.
- The plugin source package exists under `plugins/aippocampus/`; build output
  is generated under `dist/` by default and must not be committed.
- The real Codex app-server smoke exists at
  `plugins/aippocampus/smoke_real_codex_host.py`; it verifies Codex
  marketplace/plugin install, MCP host discovery, `sync_status` tool calls, and
  cleanup through real app-server methods.
- The package-level plugin install smoke also records an alternate client
  surface: a standalone MCP stdio JSON-RPC client launched from the installed
  plugin `.mcp.json`, not the headless Codex app-server.
- The single-machine dual-device sync smoke exists at
  `tools/aippocampus/smoke/smoke_cross_device_sync.py`; it verifies
  portable locators, target-registry path repair, bidirectional conflict
  preservation, cross-OS-shaped source locator cleanup, and raw rollout
  opt-in boundaries without claiming a real second machine or cloud backend.
- Plugin install must not silently enable prompt or lifecycle hooks. Hook
  installers remain explicit consent/action surfaces.
- External-model paths must pass through shared redaction before leaving the
  process.
- DeepSeek-backed subconscious jobs preserve the KV-cache contract: stable
  job/schema/tool prefixes come before source turns, variable objectives stay
  last, and same-prefix diversity samples run in warm-up waves rather than all
  launching cold at once.
- DeepSeek model routing preserves the latency boundary: flash is the default
  fast/background route, while Pro is reserved for slow adjudication,
  suppressed-label recovery, and agentic source-review. Pro must stay out of
  foreground hooks.
- Ruff now runs syntax-level `E9` plus full Pyflakes `F`; keep that baseline
  green before considering noisier style/import-order rules. The import-coupling
  test guards against same-directory script cycles, `registry.py` pulling
  `retrieval.py` at module load time, and `prompt_recall_core.py` becoming a
  broad foreground import hub again.
- The real-history FTS5 recall benchmark exists at
  `benchmarks/aippocampus/benchmark_fts5_recall.py`. Preserve the distinction
  between lexical/ranking misses and stale-index consistency misses; detailed
  dated metrics belong in the readiness snapshot or verification ledger.
- Segment rebuilds must preserve the last-known-good manifest and segment dirs
  when a rebuild fails.

## Recommended Next Slices

1. Stage 0-5 completion matrix
   - Source: `roadmap.md` and `stage-0-5-readiness.md`.
   - Keep the matrix current while closing blockers. Do not claim Stage 0-5
     completion until every explicit requirement has evidence, not just tests.

2. Public readiness hardening
   - Source: `roadmap.md`, Stage 1 and Stage 7.
   - Public install/demo docs, privacy checklist, contribution notes, and a
     synthetic public example bundle now exist.
   - Next keep the dated verification fresh after every release slice and
     validate install paths outside this single working copy.

3. GB/TB-scale storage, search, and sync track
   - Source: `gb-scale-roadmap.md` and issue #4.
   - This is now an active near-term track, not a distant optimization. The
     first foundation exists in `storage_capacity_report.py`, and the default
     sync policy no longer treats generated SQLite indexes as mandatory portable
     source.
   - Current executable evidence now covers content-addressed clean-source
     chunk delta sync (#11), registry-metadata query planning with fanout
     budgets (#12), synthetic multi-GB capacity smoke (#13), and Windows
     writer / rebuild reliability (#14).
   - Treat #13 and #14 as closed historical slices. Any new GB/TB-scale work
     should come from current open issues / Project evidence gaps instead of
     reopening these handoff bullets as remaining work.

4. Life-wide memory scope labels
   - Source: `roadmap.md`, Stage 2.
   - Clean-source messages and turns now carry deterministic `scope_labels`
     for personal reflection, relationship continuity, reading notes, idea
     seeds, preferences, life context, technical work, and open questions.
   - Fuzzy casual-important labels now have a DeepSeek/subconscious-compatible
     path: `semantic_scope_labeling` findings are materialized by
     `build_semantic_scope_labels.py` into `semantic-scope-labels.jsonl`, then
     search and timelines merge that sidecar as navigation metadata.
   - `project_timeline.json` now also carries a `life_wide` section that groups
     bounded recent labeled clean-source turns across registered
     threads/projects with `source_refs`.
   - Current real-history coverage numbers, strict source-review results, and
     Pro-agent recovery evidence live in `stage-0-5-readiness.md`. Do not mirror
     those metrics here unless this file becomes a release changelog.
   - Next broaden high-confidence recovery for suppressed soft labels
     (`relationship_continuity`, `open_question`, `idea_seed`,
     `technical_work`, `life_context`, `preference`) through better model
     evidence and selected source-review, not lexical expansion, and keep
     over-personalization boundaries tight for ordinary work prompts.

5. Cross-device sync bundle and commands
   - Source: `roadmap.md`, Stage 3.
   - The local-folder `sync status`, `sync push`, `sync pull`, and
     `sync repair` flows now live in `aippocampus_runtime.sync.bundle`, with
     `aippocampus_runtime.sync.bundle` kept as the package owner; pushed registry rows use
     portable bundle-relative locators, and pull repairs generated-artifact
     paths to the target registry. The local cross-device smoke now models two
     device registries, cross-OS-shaped source paths, bidirectional conflicts,
     and raw opt-in. `aippocampus_runtime.sync.object_storage.cli` now exercises
     the same contract over HTTP object `PUT`/`GET`, with
     `aippocampus_runtime.sync.object_storage.cli` kept as the package owner.
   - Current P0 evidence now includes a physical Windows-to-MacBook sync smoke
     and a managed Cloudflare R2 encrypted object-storage smoke. Release-oriented
     repair boundaries are documented in `encrypted-sync-v1.md`. Next harden
     them with broader provider/client soak only where a release claim needs it.

6. MCP access layer hardening
   - Source: `roadmap.md`, Stage 4.
   - The first MCP server is present and has both a stdio JSON-RPC process
     smoke and a real Codex app-server MCP host smoke through the plugin path.
   - Error contracts now cover common client failures. Next run an interactive
     Desktop UI flow or another named Codex client only if a release claim needs
     that wrapper.

7. Plugin distribution hardening
   - Source: `roadmap.md`, Stage 5.
   - The built plugin has been validated in a real Codex app-server
     marketplace/plugin install path with reversible cleanup.
   - Public distribution, uninstall, and rollback docs now cover the skill
     package, MCP config, plugin package, hook installers, and optional
     external-model routes. Next pursue marketplace submission or independent
     third-party install review only if those claims are needed.

8. Question tracking Phase 2
   - Source: `question-tracking-subconscious.md`.
   - First deterministic slice is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/question/tracking.py`, with
     `question_tracking.py` kept as the package owner: it groups existing
     `question_candidate` findings, writes `question_link` rows to
     `subconscious_jobs.jsonl`, records auditable ordering edges, skips stale
     refs when registry clean-source resolution is available, and requires
     explicit confirmation artifacts for borderline pairs.
   - First offline #134 slice is implemented:
     `aippocampus_runtime.question.tracking` can export compact pending
     confirmation requests for borderline pairs, and
     `benchmark_question_tracking_calibration.py` checks selected fixtures for
     obvious recurring retention, generic merge rejection, and pending request
     formation. The report now compares the static strong-threshold baseline
     with the current adaptive-threshold path and exposes missed-positive /
     merged-negative deltas.
   - First optional live/model adapter slice is implemented:
     `question_confirmation_live.py` converts pending requests into confirmation
     artifacts for the tracking `--borderline-confirmations` path, but defaults
     to dry-run unless `--call-model` and an API key route are supplied.
   - First #134 live smoke is implemented:
     `tools/aippocampus/smoke/smoke_question_confirmation_live.py` exercises the
     pending-request -> optional live artifact -> tracking round trip in a temp
     no-write path. A 2026-05-31 local DeepSeek run produced one accepted
     no-write round-trip link from one pending request, without emitting source
     refs or raw question text.
   - Next hardening: tune thresholds on broader private clean-source examples
     and add user-calibrated acceptance/rejection evidence before claiming live
     semantic quality or recall improvement.

9. Vector index protocol
   - Source: `gb-scale-roadmap.md` and `wukong-mining-notes.md`.
   - First slice is implemented in
     `aippocampus_runtime.question.vector_index`; it is package-owner only.
   - Keep vectors optional and join every result back to stable source ids.
   - `question_tracking` now has a deterministic local hash-vector baseline;
     TurboVec or sqlite vector evaluation remains deferred until the current
     source-backed baseline shows a scale bottleneck.

10. Retrieval score fusion contract
   - Source: `docs/architecture/wukong-mining-notes.md`, `docs/architecture/gb-scale-roadmap.md`,
     `docs/architecture/question-tracking-subconscious.md`, and `docs/guides/public-api.md`.
   - First internal policy is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`: it preserves the
     existing text score formula, blends optional vector and graph scores with
     context-dependent weights, and skips candidates that cannot join back to
     stable source ids, message/turn ids, or source refs.
   - Next hardening: connect real vector/graph consumers only after measuring
     recall behavior against source-evidence benchmarks; do not promote the
     policy output to a public schema.

11. Correction reconsolidation events
   - Source: `docs/research/correction-reconsolidation.md` and
     `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`.
   - First runtime helper is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/reflection/reconsolidation.py`: it builds and
     appends source-backed `correction_activation_event` /
     `correction_outcome_event` rows, privacy-scans correction/evidence
     surfaces, emits detached `correction_adjudication_candidate` hypotheses,
     and renders active anchors only after compaction or horizon loss.
   - Next hardening: wire live hook capture in a fail-open way, then add private
     real-history correction packs before making compaction-survival claims.

12. Coding decision events
   - Source: `docs/research/agent-coding-context-analysis.md` and
     `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`.
   - First deterministic extractor is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/coding/decision_events.py`: it reads clean
     source messages, emits staging `decision_event` candidates with source
     refs, flags accepted decisions / rejected routes / scope narrowing /
     do-not-repeat notes / user corrections, and renders at most one compact
     `coding_continuity_ticket` after the shared anti-nag gate.
   - Next hardening: review private real-history decision packs and measure
     whether host agents use tickets correctly before claiming intervention
     timing quality.

13. Agency affordance map and ticket selector
   - Source: `docs/research/agency-from-cognitive-map.md`,
     `docs/research/agent-coding-context-analysis.md`, and
     `docs/research/correction-reconsolidation.md`.
   - First deterministic selector is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/coding/agency_affordance.py`: it builds conservative
     source-backed affordances from cognitive-map-like inputs, correction
     windows, ambient recall cards, dream outputs, coding tickets, unfinished
     tasks, and scheduled revisits; emits at most one foreground ticket per
     topic epoch plus bounded backstage tickets; and records append-only ticket
     feedback outcomes.
   - Next hardening: wire host integration only through explicit executive
     policy, then measure real dismissal/acceptance patterns before claiming
     timing quality or annoyance-risk calibration.

14. Question salience and adaptive separation/completion thresholds
   - Source: `docs/planning/technical-differentiation-analysis.md`,
     `docs/architecture/question-tracking-subconscious.md`, and
     `docs/architecture/cognitive-runtime-architecture.md`.
   - First deterministic slice is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/question/tracking.py`: parsed
     `question_candidate` rows receive salience profiles, low-information
     candidates are skipped as link inputs, and pair thresholds adapt from
     compatible or conflicting six-axis evidence.
   - First #137 feedback-pressure slice is implemented:
     `aippocampus_runtime.question.feedback_policy` lets `question_tracking.py`
     treat source-id-backed ambient dismiss/reopen events as conservative
     separation pressure for the same source-backed `question_link` pair;
     it is package-owner only;
     theme/frontier dismissals stay ambient-surface policy only.
   - First #137 theme/cap hardening is implemented: `theme_candidate` scent uses
     the same frequency cap and dismiss/reopen overlay as question scent, and
     oversized ambient policy overlays fail open instead of blocking foreground
     prompt recall.
   - Next hardening: calibrate salience and threshold weights against more real
     clean-source samples and broader explicit user feedback before treating
     them as live timing or quality claims.

15. Cognitive portrait structured-text benchmark
   - Source: `docs/research/compact-activation-signals.md`,
     `docs/research/README.md`, and
     `docs/architecture/question-tracking-subconscious.md`.
   - First deterministic benchmark is implemented in
     `benchmarks/aippocampus/benchmark_cognitive_portrait.py`: it builds a
     compact structured-text portrait from source-backed
     `question_candidate`, `frontier_marker`, and `question_link` shapes,
     compares it with fuller clean-source injection on selected fixture prompts,
     and reports token savings, source-fidelity back-pointers,
     over-personalization risk, and expected quote-fidelity loss.
   - First #139 structural real-history proxy is implemented in
     `benchmarks/aippocampus/benchmark_question_aware_real_history.py`: it
     selects private question/frontier/link/theme rows when present, emits
     sanitized packs with hashed source refs only, and records pack-selection
     strategy, source-fidelity, term-coverage delta, token-ratio,
     quote-required count, known failure modes, and cannot-claim boundaries.
     The 2026-05-30 current-registry run selected 2 packs from 42 eligible rows
     and kept source-ref fidelity at 1.0 with no private text emitted, but it
     also reported `structural_proxy_ready_but_scaffold_regressed`,
     `portrait_token_ratio=3.7005`, `term_coverage_delta=-0.4412`, and missing
     selected `question_link` / `theme_candidate` context. This supports
     source-backed scaffold formation only, not helpfulness or token-savings
     claims.
   - First #313 no-leakage thread-story packet diagnostic is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/reflection/thread_story.py`:
     it builds a source-backed activation packet with freshness, sensitivity,
     source back-pointers, suppression boundaries, negative controls for
     contradictory symbolic arcs / persona-like claims / multi-channel
     interference, and an opt-in deterministic answer-boundary probe.
   - Next hardening: add opt-in answer comparison / live model probes before
     claiming behavioral equivalence or user-visible recall improvement. Keep
     numerical activation codes and white-box steering out of this slice.

16. Journey Tracking P1-P3 core
   - Source: `docs/research/journey-tracking.md`,
     `docs/architecture/question-tracking-subconscious.md`, and the hexagram validation
     study pack.
   - First deterministic core is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/journey/tracking.py`: it defines source-backed
     `Waypoint` / `Journey` / `JourneyFeedback` structures, append-only waypoint
     history, `traveling` / `camped` / `arrived` / `abandoned` transitions,
     expiry/TTL refresh, conservative multi-thread instantiation gates,
     deterministic `current_frontier`, and explicit feedback actions.
   - The fixture smoke compares Journey frontier/state against a plain summary
     baseline for later-continuation terms. `journey/live.py` adds the first
     no-write, time-sliced fixture that converts source-backed
     `theme_candidate`, `question_candidate`, and `frontier_marker` rows into a
     Journey candidate and exercises foreground hint timing with positive and
     negative controls.
   - This is still not proof of user-calibrated `theme_emergence`, production
     AAR foreground hook quality, predictive replay, or private real-history
     Journey quality. Next hardening should connect only source-backed live
     outputs when the job circuit exists, then evaluate on time-sliced private
     history before surfacing Journey hints by default.

17. Dream runtime substrate plus bounded sleep-cycle path
   - Source: `docs/research/dream-task-design.md`,
     `docs/research/source-as-world.md`, and
     `docs/architecture/cognitive-runtime-architecture.md`.
   - First deterministic helper is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/dream/compensatory.py`: it consumes
     source-backed single-thread extraction rows, discards unsourced or prior
     dream rows, suppresses refs from other threads, emits
     `dream_synthesized` compensatory candidates whose bridge claims carry
     thread-scoped source refs, preserves source-derived scope labels from live
     `question_extraction`, and keeps trigger defaults lower than extraction
     and out of foreground hooks.
   - The helper covers empty/no-pattern, technical unresolved-edge, life-wide
     silently-recurring, unsourced-row, cross-thread-ref, ordinary-no-pattern,
     self-reingestion, and background-adjudicated working-memory projection
     fixtures.
   - The P2 substrate is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py` and
     `skills/aippocampus/scripts/aippocampus_runtime/dream/working_memory.py`: it builds
     `aippocampus_dream_input_pack` rows from source-backed question links and
     Journey rows, allows ambient residue only as weak source-ref fingerprints,
     requires at least two clean source threads for a ready pack, and parks
     dream hypotheses whose bridge claims lack source refs. It is still a
     holding-queue plus background-adjudication substrate, not proof of live
     dream quality or user-visible lift.
   - The P3 structural eval is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/dream/real_history_eval.py`: it selects
     source-backed real-history packs from materialized question/frontier/link
     and working-memory rows, runs a deterministic compensatory/amplification
     worker, adjudicates dream hypotheses, and compares dream-augmented
     substrate against plain rows. A 2026-05-30 local smoke over the current
     registry selected 4 packs and observed structural lift
     (`source_thread_coverage_delta=2.5`, `reflection_ready_delta=64`,
     `bridge_claim_coverage_delta=1.0`) with sanitized aggregate output only.
   - The bounded worker and sleep-cycle path now exist as contract-level runtime
     slices: `aippocampus_runtime.dream.worker` covers model-backed
     compensatory/amplification/prospective candidates plus the
     active-imagination sandbox with source-ref, no-write, and adjudication
     gates; `aippocampus_runtime.dream.sleep_cycle` runs ready queue items as
     detached background work and can write staging rows without projecting
     dream hypotheses into working memory.
   - Next hardening: run #163's real-history quality and user-visible-lift eval
     with reviewed samples, no-dream baselines, negative controls, and sanitized
     aggregate output before claiming private Dream quality, predictive value,
     active-imagination usefulness, or foreground recall/reflection improvement.

18. Reflection-space topology and feedback MVP
   - Source: `docs/research/reflection-space.md`,
     `docs/research/journey-tracking.md`,
     `docs/research/dream-task-design.md`, and
     `docs/research/affect-side-channel.md`.
   - First deterministic helper is implemented in
     `skills/aippocampus/scripts/aippocampus_runtime/reflection/space.py`: it builds a small
     inspectable Journey/Waypoint/current-frontier topology, exposes
     `expand`/`merge`/`revive`/`abandon` actions, and converts recall effects,
     turning points, user corrections, and map feedback into source-ref-carried
     ranking/confidence/visibility adjustments.
   - The helper can feed AAR/reflection strategy surfaces only. It explicitly
     does not mutate clean source, rewrite Journey history, enforce scheduler
     behavior, prove live user behavior change, or provide a polished visual
     interface.
   - The #332/#484 AAR v2 hardening now connects source-backed reviewed
     correction/postmortem rows to
     `skills/aippocampus/scripts/aippocampus_runtime/reflection/aar_v2.py` as
     advisory action-time nudges. Stale, unsupported, and rejected review rows
     are ignored before they become strategy records; the scripted closeout
     lives in
     `docs/evidence/reflection-aar-v2-hardening-2026-06-05.md`.
   - Next hardening: run live/human review for usefulness, annoyance,
     calibrated timing, and reflection-mode UI behavior before claiming
     star-map, constellation, or foreground behavior lift.

## Do Not Start With

- A generic vector database rewrite.
- A cloud service dependency.
- New default-user concepts before the Core complexity budget says they reduce
  friction or source-claim risk.
- Standalone open issues whose main purpose is remembering a beautiful idea.
  Put those in Discussion or `docs/research/seeds/` first.
- Predictive replay or richer Phase 3 behavior beyond the deterministic
  `theme_emergence` first slice before Phase 2/3 source-backed signals are
  stable on real history.
- Prospective or active-imagination dream work before selected pack-backed
  amplification has source-review evidence. Amplification may proceed only as a
  pack-backed background worker with structural adjudication and measured
  recall/reflection impact.
- Any change that treats summaries, findings, or vector neighbors as truth
  without clean-source refs.
