# Product Profiles

Role: current contract.

Status: product and architecture boundary for GitHub #680.

This note defines where AIppocampus should feel quiet and low-friction, and
where heavier governance belongs. It is not a billing plan, compliance claim,
permission framework, or replacement for source-truth contracts.

Core rule:

> Default personal AIppocampus should be low-friction and source-backed.
> High-risk governance should be opt-in or enterprise-profile behavior, not
> baseline ceremony.

## Privacy Posture Contract

Use this contract before adding sensitive/profile gates to recall, Dream,
working memory, subconscious workers, or host projections:

| Action class | Runtime action | Personal-default meaning | Examples |
| --- | --- | --- | --- |
| `allow_with_boundary` | `allow` or `private_route` | Ordinary same-user conversation source may shape local continuity as a bounded route. Reopen source before public, exact, stale, disputed, or strong profile-like claims. | user-directed preferences, relationship continuity, project/life context, recurring themes, Dream hypotheses marked as not source facts |
| `degrade_or_review` | `downgrade` or `private_route` | Keep useful navigation but lower authority to hypothesis/review/source-reopen route. Do not publish a profile fact. | possible implicit profile, sensitive-domain pattern, weak source coverage, stale/conflicting source |
| `purpose_check` | `purpose_check` | Use only when real cross-domain sensitive reuse, regulated/team use, or an explicit governed deployment needs purpose review before reuse. | reusing relationship context for medical/legal/therapy-like advice, team/governed access decisions |
| `block` | `hard_block` or `external_projection_block` | Suppress use/projection and keep the reason in detail/operator output. Hard blocks stay narrow. | secrets/credentials, raw private export, non-consensual broad scan, user-disabled scope, unsafe external projection, explicit high-risk answer support |

`personal_default` must not inherit `enterprise_governed` friction by default.
Same-user conversation source defaults to `allow_with_boundary` / `private_route`,
not `purpose_check`. `purpose_check` is for actual cross-domain sensitive reuse;
`hard_block` is for true secret-like, disabled-scope, raw-private, unsafe
external-projection, or high-risk answer-support cases.

Compact/default foreground output should translate this into the smallest useful
state or route. Detail/operator views may explain the privacy action, reason
codes, and reopen/review boundary. Do not solve privacy drift by adding a wall
of foreground caveats or silently parking useful personal continuity.

Public anchors:

- [#679](https://github.com/Sapientropic/AIppocampus/issues/679) is the
  purpose-bound memory-access anchor for governed/explicit opt-in paths, not
  baseline personal recall.
- [#703](https://github.com/Sapientropic/AIppocampus/issues/703) anchors the
  worker-first situation/glyph boundary: ordinary conversation source is usable
  for same-user recall; deterministic rails keep worker outputs private,
  source-reopenable, and non-factual until source is reopened.

## Profile Tags

Use these tags when planning issues, docs, feature flags, CLI output, MCP tools,
and future UI surfaces:

| Tag | Meaning | Default friction budget |
| --- | --- | --- |
| `personal_default` | Ordinary local continuity for individual users, browser companion users, and coding-agent memory. | First recall before ceremony: local source, source-backed search, simple controls, and privacy-safe diagnostics. |
| `power_user_optional` | Advanced controls for users who want more inspection, tuning, and review without enterprise governance. | Explicitly selected tools, richer diagnostics, optional review surfaces, and configurable partitions. |
| `enterprise_governed` | High-risk, regulated, team, compliance, legal, medical-like, therapy-like, or sensitive cross-domain deployments. | Purpose scope, review queues, audit reports, policy gates, and human review where uncertainty is costly. |

Unknown features should not silently default to `enterprise_governed` friction.
If a feature is safe and useful for ordinary recall, design it as
`personal_default`; if it adds review, diagnostics, or policy overhead, make the
profile explicit.

## Personal Default

The `personal_default` path is for getting to the first useful recall moment:

- local-first clean source and source-backed recall;
- read-only provider status before writes;
- explicit onboarding only when the user is ready to register local history;
- cheap proactive orientation and progressive recall;
- portable import/export or AIppo Pack style flows;
- privacy by default: no background hard-drive scan, no raw snippets in
  diagnostics, no hidden durable writes, and no external-model route unless
  configured.

The simple control language for this profile is:
pause / forget / do-not-use-here / export / why-not.

Today, `export`, `why-not`, and `do-not-use-here` have concrete public command
surfaces. Pause and forget are safe foreground control cards first: they explain
how to inspect or quiet the relevant surface without claiming global pause or
destructive deletion. Do not claim a control is implemented everywhere until the
specific surface exists and is tested.

## Power User Optional

The `power_user_optional` profile is for local users who ask for more visibility
or tuning:

- why-recall / why-not-recall diagnostics;
- optional review inboxes for suggested routes, memories, or entities;
- domain or lightweight partition configuration;
- explicit hook, semantic, Dream, or background-job tuning;
- local observability such as the future Cognitive Observatory.

These tools may be prominent for operators, but they are not prerequisites for
the first recall path. They should explain what changed and why without making
ordinary recall feel broken when the user has not opted in.

## Enterprise Governed

The `enterprise_governed` profile owns high-friction safety machinery:

- purpose-bound memory access tokens
  ([#679](https://github.com/Sapientropic/AIppocampus/issues/679));
- high-risk answer gates and source-thickness/applicability checks;
- human review queues and policy reports;
- audit logs, retention/deletion/access governance, and privacy partitions;
- typed capability contracts for regulated or team deployments;
- red-team/doctor checks for governed rollouts.

These controls protect legal, medical-like, therapy-like, safety-critical,
team, regulated, or sensitive multimodal workflows. They must not become the
baseline ceremony for `personal_default` recall. A user should not need to fill
purpose tokens or approve every ordinary source-backed recall before seeing
value.
In short: governed controls are not baseline ceremony.

## Feature Placement

| Feature or surface | Profile tag | Boundary |
| --- | --- | --- |
| First recall path, clean-source search, read-only provider status | `personal_default` | The shortest path to source-backed recall. |
| Import/export and AIppo Pack portability | `personal_default` | Explicit user action; no hidden durable writes. |
| Prompt/lifecycle hooks and semantic/model routes | `personal_default` when already opted in; `power_user_optional` for tuning | Missing hooks or LLM routes should degrade magic, not make core recall look broken. |
| why-recall / why-not-recall diagnostics | `power_user_optional` | Available for explanation; not mandatory ceremony. |
| Review inboxes for suggested memories/routes/entities | `power_user_optional` | Useful for disputed or sensitive candidates; not default for every recall. |
| Purpose-bound memory access tokens (#679) | `enterprise_governed` or explicit opt-in | Activation/context eligibility only; never source truth and never baseline ceremony. |
| High-risk answer gates | `enterprise_governed` | Required for high-impact answer support, not ordinary memory search. |
| Team admin, compliance reports, policy gates, and audit dashboards | `enterprise_governed` | Do not imply these exist in the public local-first product unless implemented. |

## Routing Rules

- Start documentation, onboarding, and demo flows with `personal_default`.
- Keep advanced diagnostics discoverable, but label them as optional/operator
  surfaces when they are not needed for first recall.
- Mark governance features as `enterprise_governed` unless they are explicitly
  designed for ordinary personal use.
- Purpose tokens, review queues, and high-risk gates decide access or answer
  eligibility; they do not rewrite clean source, promote model summaries to
  truth, or delete history.
- If a command reports readiness, distinguish core personal readiness from
  magic-quality degradation, optional surfaces, and operator surfaces.

## Cannot Claim

This profile vocabulary does not prove:

- enterprise compliance readiness;
- hosted service behavior;
- complete pause/forget/do-not-use-here coverage across every surface;
- high-risk answer correctness;
- live recall quality or Dream usefulness.

Use the evidence docs for those claims. This note only keeps the friction budget
and product boundary from drifting.
