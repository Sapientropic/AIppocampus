# Proof-Slice Maturity Board

last_checked: 2026-06-09

This board is the public truth-navigation layer for fast-moving AIppocampus
proof lines. It is not a roadmap database and not a release checklist. Use it
to distinguish a claimable product slice from design notes, deterministic
smokes, public-safe fixtures, and second-user evidence.

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| `design_only` | Architecture, issue discussion, or planning contract exists; no deterministic proof is shipped for the line yet. |
| `deterministic_smoke` | Code, schema, or local smoke proves a narrow deterministic contract, usually with synthetic or no-write inputs. |
| `public_safe_fixture` | A public fixture or benchmark can run without private data; this still does not imply live quality. |
| `second_user` | At least one non-maintainer or fresh-machine/user path has passed with public-safe evidence. |
| `release_claimable` | Docs, install path, diagnostics, and evidence support the exact public claim in the row's `Can claim` cell. |

Rows name the maturity of the strongest current proof slice, not the ambition of
the whole line. A row can be useful and still have a strict `Cannot claim`
boundary.

## Cognitive Layer Graduation Ladder

Higher-level cognitive layers use a stricter public-claim ladder because they
can sound more stable than they are. These rungs govern README/public wording
for Dream, Journey, subconscious, observatory, semantic, and route-learning
surfaces:

| Rung | Meaning | Public wording boundary |
| --- | --- | --- |
| `metaphor` | Research language or product intuition only. | May appear in origin/research docs, not as implemented behavior. |
| `prototype` | Deterministic code or design slice exists, but quality is local or narrow. | Describe as experimental/internal and name cannot-claim boundaries. |
| `fixture_tested` | Public-safe deterministic fixture or smoke covers the slice. | May claim the fixture contract, not live quality. |
| `benchmark_supported` | Redistributable benchmark, public shadow cohort, or external public fixture supports the same failure taxonomy. | May cite benchmark support within scope. |
| `dogfooded` | Sanitized private/local aggregate runs show useful behavior. | private dogfood evidence may support operator confidence but needs explicit cannot-claim wording. |
| `public_contract` | Public reproducible evidence, docs, diagnostics, and release boundary support the default behavior claim. | May be advertised as stable public behavior only within the exact contract. |

private dogfood evidence is valuable for realism, but public-facing proof should
prefer public reproducible evidence whenever the claim asks outside readers to
trust the mechanism. Below `public_contract`, cognitive layers can appear in
architecture, research, and evidence docs; the main README must keep them framed
as opt-in, experimental, fixture-scoped, or not-yet-default.

## Cognitive Layer Board

| Layer | Current rung | Evidence owner | Can claim | Cannot claim |
| --- | --- | --- | --- | --- |
| Dream / sleep-cycle synthesis | `dogfooded` | #163, [`dream-task-design.md`](../../research/dream-task-design.md), [`dream-private-large-history-diagnostic-2026-06-04.md`](../dream/dream-private-large-history-diagnostic-2026-06-04.md) | Source-backed Dream substrates, bounded workers, precision gates, and sanitized private structural diagnostics exist. | Live provider Dream quality, predictive validity, active-imagination usefulness, or user-visible recall/reflection lift. |
| Journey / frontier routing | `prototype` | #310, [`journey-tracking.md`](../../research/journey-tracking.md) | Source-backed waypoint/Journey structures and conservative foreground hint timing fixtures exist. | Live default Journey quality, weekly/monthly journey review value, or future-state prediction. |
| Subconscious question/theme surfaces | `fixture_tested` | #248, [`question-tracking-subconscious.md`](../../architecture/question-tracking-subconscious.md) | Deterministic extraction, sidecar, parity, and review-gated candidate flows exist. | Default live answer-quality lift, fully calibrated dynamic thresholds, or private-history generality. |
| Semantic recall / source review | `fixture_tested` | #309, [`recall-navigation-comparison-2026-06-03.md`](../benchmarks/recall-navigation-comparison-2026-06-03.md), [`semantic-robustness-track-s.md`](../benchmarks/semantic-robustness-track-s.md) | Source-joined semantic/vector/graph signals can act as ranking hints after source gates. | Adaptive score fusion, universal semantic quality, or generated sidecars as evidence without reopen. |
| Cognitive Observatory | `prototype` | #576, [`public-api.md#cognitive-observatory`](../../guides/public-api.md#cognitive-observatory), [`cognitive-runtime-architecture.md`](../../architecture/cognitive-runtime-architecture.md) | Read-only public-safe diagnostic projections can be emitted. | Control-plane authority, mutation, live quality certification, or private source disclosure. |
| Cognitive-load sidecar | `dogfooded` | #575, [`cognitive-load-sidecar.md`](../../architecture/cognitive-load-sidecar.md) | Behavior-cost sidecars and caps/decay exist as recall weighting inputs. | Emotion/personality inference, live false-positive quality, or default hook usefulness. |
| Episode / Arc sequence model | `dogfooded` | #663, [`episode-arc-read-models.md`](../../architecture/episode-arc-read-models.md) | Source-backed sequence read models and private aggregate adjudication exist. | Broad live host adapters, public reproducible corpus coverage, or causality without source reopen. |
| Active-flow route feedback | `prototype` | #937, #950, `aippocampus_runtime.recall.feedback_events` | Public-safe route feedback rows and reducers can provide calibration/ranking metadata. | Online learning over private content, automatic score-weight changes, or activation metadata supporting factual claims. |

## Flagship Cognitive Mechanism Gate

| Mechanism | Current gate | Owning issue | Cannot claim until |
| --- | --- | --- | --- |
| Awake SWR / online consolidation tagging | `fixture_tested` | #1018, `aippocampus_runtime.reflection.consolidation_priority` | Benchmark or private/public evidence shows these priority rows improve later review selection or user-visible continuity without promoting source truth. |
| Dynamic separation/completion threshold | `prototype` | #248 | Broader public/private calibration shows improved question quality without over-merging or noisy default activation. |
| Retrieval-induced reconsolidation | `substrate_prototype` | #1019, `aippocampus_runtime.reflection.retrieval_lifecycle` | Later consumers use confirmation/correction/conflict evidence without rewriting clean source; retrieval lifecycle counts alone are not memory correctness. |
| Preplay / state-dependent routing | `metaphor` | #163, #310, #940 | Public-safe predictive/preparation fixtures show value without pushing speculative content into foreground. |

## Board

| Line | Current maturity | last_checked | Can claim | Cannot claim | Owner / evidence |
| --- | --- | --- | --- | --- | --- |
| Local source-backed conversation memory | `release_claimable` | 2026-06-03 | AIppocampus provides a local, source-backed continuity path for agent work: clean source, search, MCP access, install docs, and source-reopen boundaries exist. | Broad adoption, all-client quality, hosted service readiness, innate model memory, universal recall quality, or generated sidecars as replacement truth. | [`agent-context.md`](../../agent-context.md), [`install-guide.md`](../../guides/install-guide.md), [`architecture-overview.md#source-backed-kernel-contract`](../../architecture/architecture-overview.md#source-backed-kernel-contract), [`magic-moments.md`](../magic-moments.md), [`stage-0-5-readiness.md`](stage-0-5-readiness.md), #470, #307 |
| Knowledge-as-source and high-risk gates | `public_safe_fixture` | 2026-06-03 | Governed source/claim manifests, lifecycle checks, high-risk answer gates, and synthetic public-safe pollution/privacy fixtures exist. | Medical, legal, therapy, compliance, or real high-risk answer quality certification. | [`knowledge-source-lifecycle.md`](../../architecture/knowledge-source-lifecycle.md), [`high-risk-answer-gates.md`](../../architecture/high-risk-answer-gates.md), [`knowledge-pollution-privacy-fixture-report.md`](../benchmarks/knowledge-pollution-privacy-fixture-report.md), #512, #514-#517 |
| Typed capability contracts | `deterministic_smoke` | 2026-06-03 | The repo has an architecture contract and public-safe internal manifest/validator prototype for source, permission, privacy, and cannot-claim boundaries. | Public SDK stability, replacement of `SKILL.md`, broad capability taxonomy completeness, or answer quality. | [`agent-skill-capability-contracts.md`](../../architecture/agent-skill-capability-contracts.md), [`knowledge-pollution-privacy-fixture-report.md`](../benchmarks/knowledge-pollution-privacy-fixture-report.md), #518 |
| Multimodal source recall | `public_safe_fixture` | 2026-06-03 | Source/route/gate contracts exist for public-safe corpus, conversational media-ingest, and NIAH-style evidence-pool fixtures. | ATM-Bench score, live vision-model quality, private media runtime, face identity graph behavior, or background photo/file scanning consent. | [`multimodal-source-manifests.md`](../../architecture/multimodal-source-manifests.md), [`multimodal-provider-routing.md`](../../architecture/multimodal-provider-routing.md), [`multimodal-answer-gate.md`](../../architecture/multimodal-answer-gate.md), [`multimodal-corpus-fixture-report.md`](../benchmarks/multimodal-corpus-fixture-report.md), #528, #531-#533, #541-#543 |
| Continuous-memory benchmark | `public_safe_fixture` | 2026-06-03 | Diagnostic public-safe benchmark arms exist for memory/no-memory/sham/stale/oracle/host-native-style comparisons with claim boundaries. | Superiority over fresh-context loops, live host-native telemetry, large-sample significance, or product-quality memory lift. | [`memory-decision-benchmark-plan.md`](../benchmarks/memory-decision-benchmark-plan.md), [`benchmark-evidence-map.md`](../benchmark-evidence-map.md), #378, #406-#410, #453 |
| Rust deterministic core | `design_only` | 2026-06-03 | A conservative contract-replay boundary and candidate order exist for future Rust infrastructure slices. | Any authoritative Rust runtime slice, Python/Rust fixture parity, Python fallback readiness, or shipped Rust storage/index/sync core. | [`rust-deterministic-core.md`](../../architecture/rust-deterministic-core.md), #463 |
| Field Continuity / magic moments | `public_safe_fixture` | 2026-06-03 | Second-user field-report shapes have been converted into public-safe reproducible scenario-family fixtures with negative controls. | Real-history recall quality, universal fresh-thread recall, hook-only sufficiency, live semantic-model quality, hosted-service readiness. | [`magic-moments.md`](../magic-moments.md), [`field-continuity-fixture-report.md`](../benchmarks/field-continuity-fixture-report.md), #454 |
| Progressive recall navigation | `public_safe_fixture` | 2026-06-03 | Public-safe demos and comparison smokes exercise `recall_context -> recall_deepen`, vague cues, multilingual cues, stale-handle rejection, and source-reopen boundaries. | Live user quality improvement, live token/tool-call reduction, production selector superiority, or broad private real-history fresh-thread quality. | [`fresh-thread-recall-demo-2026-05-31.md`](../benchmarks/fresh-thread-recall-demo-2026-05-31.md), [`fresh-thread-expanded-coverage-2026-06-03.md`](../benchmarks/fresh-thread-expanded-coverage-2026-06-03.md), [`recall-navigation-comparison-2026-06-03.md`](../benchmarks/recall-navigation-comparison-2026-06-03.md), #201, #281, #465, #490 |
| Source-backed repo familiarity | `public_safe_fixture` | 2026-06-04 | A source-backed repo familiarity card contract and opt-in no-write foreground experiment report exist for comparing no-card, selected-card, and stale/irrelevant-card fixture plus public current-checkout arms. | Live agent helpfulness, live cost reduction, default foreground-hook lift, multi-agent familiarity sharing, broad cognitive-map quality, or current-code claims without reopening source. | [`source-backed-familiarity-map.md`](../../architecture/source-backed-familiarity-map.md), [`benchmark-evidence-map.md`](../benchmark-evidence-map.md), #250 |
| Schema/profile field discipline | `deterministic_smoke` | 2026-06-03 | Minimal/runtime/governance/diagnostic/high-risk projection discipline exists with a small helper and tests. | Product quality, high-risk correctness, source truth without source reopen, or one universal mega-schema. | [`schema-field-profiles.md`](../../architecture/schema-field-profiles.md), #573 |

## Reading Rules

- Closed design or fixture issues are not production adoption evidence.
- `public_safe_fixture` means a contributor can inspect or run a clean proof
  slice; it does not mean live behavior is solved.
- `second_user` evidence is user-visible signal, not a statistical benchmark.
- `release_claimable` applies only to the exact `Can claim` text in that row.
- Dated metrics and supersession rules still live in
  [`current-claims.md`](../current-claims.md).
