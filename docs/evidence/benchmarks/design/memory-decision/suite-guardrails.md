# Memory Decision Suite And Guardrails

Role: extracted implemented-slice detail page.
Status: current detail under [`implemented-slices.md`](implemented-slices.md).

### Benchmark Suite Profiles

`benchmark_suite.py` exposes named profiles so benchmark runs can be compared by
claim surface instead of by an opaque pile of flags. The CLI help links here,
and each JSON report includes `profile_metadata`, `threshold_metadata`, and
`claim_surface_warnings` so later run-history comparison can reject mismatched
surfaces before interpreting score deltas.

Profiles are presets plus safety boundaries. Maintainers may still use explicit
flags for narrow experiments, but those runs should be treated as mixed claim
surfaces unless the report metadata says otherwise.

| Profile | Intended use | Default included surface | Default exclusions / boundary pointer |
| --- | --- | --- | --- |
| `public-fast` | Fresh-clone public smoke and quick local confidence. | Track A gate decision, Track C payload fidelity, Track D compaction continuity. | Excludes private text, live semantic calls, Track B, and optional public-corpus adapters. |
| `ci-deterministic` | Deterministic CI-oriented baseline where Track B diagnostics are allowed. | Tracks A/C/D, Track B source-evidence retrieval, deterministic source-label diagnostic slice. | Excludes private text, live semantic calls, and optional public-corpus adapters. |
| `local-calibration` | Maintainer local calibration with deterministic Track B enabled. | Tracks A/C/D and deterministic Track B surfaces. | Excludes private text and live semantic calls by default; registry/data availability affects interpretation. |
| `live-semantic` | Explicit provider-backed semantic calibration. | Tracks A/C/D, Track B, and `live_semantic_gate`. | Live/provider-dependent surface; excludes private text by default. |
| `private-full` | Maintainer-only private-history regression. | Tracks A/C/D and Track B with private text allowed. | Private-history maintainer surface; public-release claims need sanitized dated evidence. |
| `release-evidence` | Public-safe release evidence with stable metadata. | Tracks A/C/D and deterministic Track B surfaces. | Excludes private text, live semantic calls, and optional public-corpus adapters unless explicitly opted in and documented. |
| `baseline` | Backward-compatible default baseline capture. | Current default suite surface. | Legacy continuity surface; prefer a named non-legacy profile for new evidence comparison. |

This table is a profile navigation map, not the active run claim boundary. It
names excluded surfaces so readers can choose the right profile, but it should
not mirror every profile's `default_cannot_claim` list. The selected profile in
the JSON report carries the active `cannot_claim` list, while inactive ladders
and docs maps should follow the count/pointer rule in
[`schema-field-profiles.md#cannot-claim`](../../../../architecture/runtime/schema-field-profiles.md#cannot-claim).

Run `public-fast` from a fresh clone when you need the deterministic public
benchmark surface without private registry data, live model calls, or external
dataset downloads:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --profile public-fast --json
```

`public-fast` runs the Track A gate-decision, Track C payload-fidelity, and
Track D compaction-continuity slices. It forcibly disables private text, live
semantic checks, Track B source-evidence retrieval, and optional public-corpus
adapters. Its report includes `cannot_claim` entries for those omitted surfaces
so the profile cannot be mistaken for Track B, private-history, or live-model
quality evidence.

Suite reports keep `cannot_claim` as a backward-compatible flat union of all
claim boundaries, but readers should use `cannot_claim_by_track` and
`suite_level_cannot_claim` to interpret source and scope. For example, Track A's
`payload_fidelity` boundary means the gate-decision track does not validate
Track C payload fidelity; it does not contradict
`track_statuses.payload_fidelity=sufficient`. Track C can pass its
synthetic/public-safe payload-fidelity slice while still carrying
`real_history_payload_fidelity` as a track-local boundary.

Threshold metadata intentionally explains the comparison boundary rather than
just repeating numbers:

| Metadata key | Meaning | Claim boundary |
| --- | --- | --- |
| `fts5_min_cases` | Minimum deterministic source-line cases for the Track B FTS5 baseline. | Sample-count floor only; not a quality pass by itself. |
| `source_min_cases` | Minimum selected source-evidence cases. | Avoids tiny selected slices, but does not repair selection bias. |
| `source_min_hit_rate` | Diagnostic selected source-evidence top-k hit-rate floor. | Bounded retrieval diagnostic; not broad private real-history quality. |
| `live_semantic_min_cases` | Minimum optional live semantic cases. | Live provider smoke only; model/provider dependent. |
| `live_semantic_min_surface_recall` | Optional live semantic surface-recall threshold. | Local live slice threshold, not a guarantee for future semantic prompts. |
| `standard_min_questions` | Minimum LoCoMo/LongMemEval public retrieval-QA questions. | Public-control retrieval only; no answer-generation claim. |
| `standard_min_session_hit_rate` | Expected answer-session retrieval floor for standard public QA. | Session retrieval only; not SOTA, not LongMemEval-V2, and not answer quality. |

Do not lower thresholds to make a profile pass. If a run captures a baseline
but misses a threshold, keep `quality_gate_ok=false`, preserve `known_gaps`, and
use the result as regression evidence rather than as a product-quality
certificate.


### Run-History Diff Guardrails

`benchmarks/aippocampus/benchmark_run_history_diff.py` compares two saved
`benchmark_suite.py` JSON reports and emits a diagnostic artifact with
`status=no_regression`, `warning`, or `regression`:

```powershell
python benchmarks\aippocampus\benchmark_run_history_diff.py --baseline .tmp\prior-suite.json --current .tmp\current-suite.json --json
```

The comparator only treats runs as comparable when the benchmark-suite schema,
selected profile, `profile_metadata.effective_surface`, and key config fields
match. Profile changes, Track B / Track D switches, optional public adapter
changes, seed/top-k/ranking/dataset changes, private-text boundaries, and live
semantic surface changes are warnings about incomparable surfaces, not metric
regressions.

The comparable identity also includes track statuses, public adapter
status/corpus fingerprints such as `corpus_path_sha1`, threshold metadata, and
per-metric gate thresholds for metrics present in both runs. It deliberately
excludes absolute local paths and raw text fields from the diff artifact. If a
rate metric disappears or appears inside an otherwise comparable surface, the
diff emits a warning (`metric_missing_in_current` or `metric_new_in_current`)
instead of silently comparing only the intersection.

Trend status is separate from `quality_gate_ok`. A current run can still clear
its point-in-time threshold while receiving `status=regression` because it
dropped materially from the previous comparable run. Conversely, a run with
`quality_gate_ok=false` can still be useful as a baseline snapshot if the diff
shows the same known gap and no additional trend regression.

The first diff policy is intentionally conservative:

- higher-is-better rate estimates warn on absolute drops of at least `0.03` and
  regress on drops of at least `0.05`, unless the sample size changed enough to
  make a sample-size warning more honest than a regression claim;
- lower-is-better rates such as false-positive, false-negative, over-escalation,
  error, miss, failure, and privacy-breach rates regress when they increase;
- Wilson lower-bound drops are warnings, not proof that sampling bias was
  solved;
- privacy boundary fields moving from safe to unsafe, such as
  `raw_text_emitted=false` to `true`, are direct regressions;
- sample-size shrinkage is a warning, not a healthy pass;
- live semantic metric drops are warning-only until the project defines a
  stable provider/model comparison policy;
- `elapsed_ms` increases are warnings only because local machine, cache, and
  provider conditions can dominate single-run timing.

Historical suite JSON and diff artifacts remain local/generated evidence under
`.tmp/` or `benchmark_corpus/reports/` unless a small public-safe summary is
deliberately promoted into docs. The comparator never rewrites old reports and
does not replace the dated public-readiness ledger.

Cannot-claim boundaries:

- a run-history diff is diagnostic trend evidence, not proof of overall product
  quality;
- different profiles, corpora, seeds, public adapters, private-text settings, or
  live providers are not directly ranked;
- confidence intervals make small-N uncertainty visible but do not repair sample
  construction bias;
- live semantic deltas are warning-only until a stable provider/model policy is
  explicitly defined.


### Repeatable Baseline Command

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_suite.py
```

For a machine-local JSON artifact, write into the gitignored private benchmark
area:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --json --output benchmark_corpus\reports\baseline-suite.json
```

Default suite semantics:

- `ok=true` means the current baseline was captured and the report stayed inside
  the default privacy boundary.
- `quality_gate_ok=false` is allowed for the current baseline and means at least
  one track is diagnostic or below target.
- `status=baseline_captured_with_known_gaps` is the expected current status.
- Raw prompts, context, source refs, snippets, absolute paths, and private
  registry details stay out of default reports.
- `--include-private-text` is a local-debug opt-in only and should not be used
  for public docs or committed artifacts.
- Private real-history case selection delegates obvious sensitive-content
  detection to `aippocampus_runtime.safety.benchmark_sensitive_text_policy`.
  That policy skips candidates with credential/path/recipient/database/private
  host signals; it is stricter than external-model prompt redaction because
  benchmark fixtures should avoid selecting publishable targets from sensitive
  text in the first place.


### Uncertainty And Gate Semantics

Empirical benchmark reports should expose `rate_estimates` for key binomial
rates. Each entry includes numerator, denominator, point estimate, and a
Wilson-score confidence interval. This makes small-N reports visibly wide
instead of letting a perfect point estimate read like a release-quality result.

Confidence intervals do not repair sampling bias. Selected real-history slices,
synthetic contract fixtures, public-corpus pilots, and opt-in semantic-sidecar
pilots must keep their `claim_level`, `sample_size_warning`, and `cannot_claim`
boundaries. A high point estimate with a wide lower bound is still diagnostic
unless the owning track's design says the sample is release/public-readiness
evidence.

Default deterministic contract gates keep their existing point/count
semantics. They answer "did this fixed contract fail today?" rather than
"would this pass with statistical confidence?" Broader empirical gates may opt
into lower-bound semantics when that is the product claim under review. The VCS
future-event recall benchmark exposes this explicitly with
`--gate-statistic lower_bound`; the default remains point-estimate gating so
small fixtures do not silently become release blockers.

MRR and rank-order metrics are still point estimates unless a runner exposes a
dedicated bootstrap interval. Do not average Track A gate decisions, Track B
retrieval, Track C payload fidelity, and Track D continuity into one headline
confidence number; their sample construction and product meanings differ.
