# Alpha/Beta/Stable Classifier Policy

last_checked: 2026-06-09

This page is the canonical readiness decision point for AIppocampus package
development-status classifiers. It governs `pyproject.toml`, public release
notes, README claims, public API docs, and the release checklist. It is not a
roadmap database; owner issues remain the execution queue.

## Machine-Checked Status

```text
current_classifier: Development Status :: 3 - Alpha
beta_readiness_decision: not_approved
earliest_beta_classifier_release: 0.3.0 or later
approved_classifier_release: none
decision_date: none
```

Do not change `pyproject.toml` from
`Development Status :: 3 - Alpha` until this block records an approved dated
Beta readiness decision for the exact release being packaged.

## Classifier Meanings

| Classifier | Meaning | Claim boundary |
| --- | --- | --- |
| `Development Status :: 3 - Alpha` | The source-backed continuity kernel, install path, docs, MCP surfaces, and selected evidence slices are useful and public, but major proof lines still have open readiness gates. | Current package state. Do not claim broad adoption, universal recall quality, hosted-service maturity, or all-client quality. |
| `Development Status :: 4 - Beta` | The Beta prerequisite table below has dated evidence, blockers are closed or explicitly waived, and README / public API / release notes agree on the same supported surface. | Eligible no earlier than `0.3.0 or later`; not approved as of 2026-06-09. |
| `Development Status :: 5 - Production/Stable` | Stable public API, release, support, adoption, and operational evidence exist beyond the Beta bar. | Out of scope for the current roadmap slice; requires a separate dated Stable decision. |

## Beta Prerequisites

| Track | Owner issues | Status on 2026-06-09 | Why it gates Beta |
| --- | --- | --- | --- |
| Source-backed kernel and authority rings | #978, #979 | #978 and #979 closed | Beta must preserve clean source as ground and prove the wheel/release surface can reopen source instead of shipping generated summaries as truth. |
| Memory Evidence Drawer foreground contract | #980 | Open | Foreground evidence needs a user-visible contract for what an agent may claim, reopen, or treat only as orientation. |
| Provider conformance kit | #981 | Open | Clean-source integrations need a reusable conformance path before Beta can claim provider-facing reliability. |
| Field Continuity Eval | #982 | Design/fixture/runner contract closed by `field-continuity-eval-design.md`; release evidence still needed | Long-term continuity quality needs a field-shaped eval, not only local deterministic smokes. A closed design issue does not by itself approve Beta. |
| Dream/Journey/subconscious graduation gates | #983, #1018, #1019 | #983 covered by `proof-slice-maturity.md`; #1018 and #1019 remain open mechanism substrates | Cognitive layers need graduation criteria so experimental surfaces do not inherit Beta authority by association, and proposed Awake SWR / reconsolidation mechanisms must not inherit Beta authority before their event substrates exist. |
| Docs IA and benchmark-evidence pressure | #965, #966, #967, #968 | Closed | The public reader path and evidence map are now cleaner, but they remain preconditions for honest Beta claims. |
| Benchmark remediation | #960, #961, #962, #963, #964 | #960 and #963 open; #961, #962, and #964 closed | Negative or partial benchmark lines must be remediated or explicitly bounded before Beta can imply stronger recall quality. |
| Narrative mesh and active-flow feedback | #949, #950, #951 | #950 open; #949 and #951 closed | Fresh-thread continuity should route narrative/domain pointers into action without depending on hook luck or ungrounded summary. |

## Decision Rules

- Alpha is the default until the machine-checked status block says otherwise.
- A Beta decision needs dated evidence, linked owner issues, and a release
  number. `0.3.0 or later` is an eligibility floor, not a promise.
- A closed design issue is not enough for Beta unless the release notes and
  public docs name the exact shipped behavior and its cannot-claim boundary.
- Release notes must distinguish shipped surfaces from roadmap work, and must
  link active limitations instead of implying they were solved.
- README claims, public API docs, release notes, and `pyproject.toml` package
  classifier must describe the same maturity level.

## Stable Deferral

Stable is intentionally not a near-term target. It should require a new dated
decision with public API stability, install/rollback evidence, support policy,
second-user or broader adoption evidence, and explicit limits for hosted,
provider, private-history, and high-risk recall claims.
