# Continuity Domains Contract v1

Role: current contract.

Continuity domains are the source-trailed abstraction layer between clean
source and foreground action. They let a later agent find a durable working
interpretation, reopen the source trail, and revise the interpretation without
turning summaries into truth.

This contract covers issues #926 through #930 and folds in the pathlet /
narrative-mesh direction from discussion #700. The durable domain substrate is
`aippocampus_runtime.recall.continuity_domains`; the task-time route projection
for #700 narrative packets is `aippocampus_runtime.recall.narrative_packet`.

Contract v1 ships the runtime substrate, progressive recall exposure, and
opt-in runtime producer paths. Prompt hooks still do not write domain events
while the user is typing. Background jobs may write deterministic
source-ref-backed events after the user has enabled that producer feature, with
auditability, dedupe, repair/rebuild, and a kill switch replacing per-event
confirmation.

## Design Promise

AIppocampus must not stop at advanced grep. Long-term continuity needs
abstraction, but the abstraction must remain reopenable, revisable, and visibly
lower authority than clean source.

The memory shape is:

```text
clean source       -> source-backed original wording and event refs
pathlets           -> ordered source-ref routes across turns or threads
continuity domains -> source-trailed meso working conclusions
macro tendencies   -> derived pointers, not runtime-writable truth
situation glyphs   -> direction-only atmosphere over signals and path order
```

The important rule is:

```text
scale != authority
```

Micro, meso, and macro describe observation scale. `action_grammar` and the
existing trust contract decide what an agent may do.

## Layer Ownership

Clean source is the ground. It stores visible user messages, assistant final
answers, behavior events, source texture, and stable join keys such as
`message_id`, `turn_id`, and `event_id`.

Pathlets are ordered source-ref routes. They record that a continuity move
depends on sequence, not just a bag of fragments. A pathlet may say "source A
led to source B under this question", but it cannot claim that the resulting
interpretation is true.

Continuity domains are durable mesoscopic working conclusions. They are useful
for project direction, recurring questions, durable tensions, correction
boundaries, relationship continuity, and idea evolution. A domain can carry a
short working conclusion, but hook output must expose only a pointer.

Macro tendencies are derived action fields. They can help an agent notice a
long-range direction, but Contract v1 does not allow macro tendencies to be
runtime-writable factual memory.

Situation glyphs are atmosphere, not fact. Dream, Journey, hexagram,
cognitive-map, source-texture, navigation-potential, working-memory, and
continuity-domain signals may contribute to a glyph. The glyph must stay
`direction_only` unless a pinned boundary blocks or redirects it.

## Storage Contract

The append-only event log lives beside clean source:

```text
$AIPPOCAMPUS_REGISTRY_DIR/threads/<thread>/clean-source/continuity-domain-events.jsonl
```

Rebuildable snapshots live in the thread store:

```text
$AIPPOCAMPUS_REGISTRY_DIR/threads/<thread>/continuity-domain-snapshots/<snapshot_id>.json
$AIPPOCAMPUS_REGISTRY_DIR/threads/<thread>/continuity-domain-snapshots/latest.json
```

Project-local `.aippocampus/` paths may be used only as explicit
compatibility/debug output. The default memory surface is the global registry
thread store.

Event writes are append-only. Snapshot writes use the shared artifact lease and
atomic replace pattern. Snapshot data is rebuildable; it must not mutate clean
source and must not be treated as a source of exact wording.

The explicit operator/debug authoring path is:

```text
aippocampus continuity-domain produce --dry-run --json
aippocampus continuity-domain produce --dry-run --refresh-query-pattern-routes --json
aippocampus continuity-domain produce --append --publish --json
aippocampus continuity-domain append --event-json <json> --publish --json
aippocampus continuity-domain publish --json
aippocampus continuity-domain report --snapshot <path> --json
```

This CLI is a trusted local producer and append/publish surface. `produce`
scans registered clean-source history, plus reviewed signal sidecars only as
source-ref-resolving label producers, when explicitly invoked. `--append`
refreshes the existing query-pattern route sidecar first, so reviewed,
local-offline, or external-model generated alias rows that were materialized by
the registration/onboarding route can seed domain labels without becoming
evidence. `--dry-run` stays no-write unless `--refresh-query-pattern-routes` is
explicitly passed. Candidate events are written only with `--append`. Prompt
hooks and default MCP recall still do not mutate durable domain state.

The opt-in subconscious producer path is:

```text
python -m aippocampus_runtime.subconscious.jobs \
  --event-salience-gate \
  --continuity-domain-salience-mode report

python -m aippocampus_runtime.subconscious.jobs \
  --event-salience-gate \
  --continuity-domain-salience-mode write_when_enabled \
  --continuity-domain-events-output <clean-source/continuity-domain-events.jsonl> \
  --continuity-domain-snapshot-dir <continuity-domain-snapshots> \
  --continuity-domain-clean-source-dir <clean-source> \
  --continuity-domain-publish
```

`AIPPOCAMPUS_CONTINUITY_DOMAIN_PRODUCTION=report|write_when_enabled` can set the
same policy for configured job runners when the salience gate is enabled.
`report` is no-write. `write_when_enabled` appends through the existing
continuity-domain event path only when writes are not otherwise disabled by
`--dry-run` or `--no-write`.

## Producer Capability Matrix

| Tier | Event families | Current owner | Boundary |
| --- | --- | --- | --- |
| `accepted_by_contract` | all domain and pathlet families listed below | `continuity_domains.py` normalizer/materializer | Accepted events still need resolving source refs and remain navigation until source reopen. |
| `auto_produced_now` | `domain_created`, support/source refs | `continuity_domain_producer.py` registry producer | Producer-backed labels are source-ref routes, not evidence owners. |
| `materialized_fallback` | representative refs synthesized from support/counter/correction/boundary refs | `continuity_domains.py` snapshot finalizer | Fallback representative refs are not a claim that a producer classified representative evidence. |
| `opt_in_runtime_production_now` | `correction_source_added`, `counter_source_added`, `boundary_pinned`, and cautious repeated-ref `domain_created` from salience | `continuity_domain_salience_adapter.py` via subconscious jobs | Enabled jobs may write quietly with dedupe/auditability; public summaries expose counts only. |
| `review_or_target_required` | `domain_superseded` from currentness salience | salience adapter | Written only when a target domain is supplied or resolved; otherwise deferred as reviewable currentness pressure. |
| `operator_debug_or_backfill` | any accepted event family when curated by an operator/agent | `aippocampus continuity-domain append/produce/publish/report` | Useful for repair, imports, exceptional curation, and tests; not the ordinary ADHD-facing path. |
| `operator_authored_or_future` | split, merge, reinterpretation, representative curation, pathlet lifecycle automation | future source-shaped producers | Do not imply these are automatically produced by the current registry or salience producer. |

Lifecycle snapshots may also project into shared
[`runtime_recheck_event`](runtime-recheck-events.md) diagnostics. That bridge is
not a continuity-domain producer and does not add source truth: it only lets
macro, Dream/subconscious, and active-recall consumers notice contested,
stale/superseded, pinned-boundary, blocked, or retired routes as direction-only
recheck pressure.

Supported domain event families:

- `domain_created`
- `support_source_added`
- `counter_source_added`
- `correction_source_added`
- `representative_source_added`
- `boundary_pinned`
- `domain_reinterpreted`
- `domain_split`
- `domain_merged`
- `domain_superseded`
- `domain_retired`

Supported pathlet event families:

- `pathlet_created`
- `pathlet_reinterpreted`
- `pathlet_superseded`
- `pathlet_retired`

Every accepted event must carry resolving source refs. Events without usable
source refs, unsupported event kinds, unresolved refs, local paths, raw source
text, or secret-shaped values are rejected or redacted before materialization.

## Domain Snapshot Shape

A continuity domain snapshot separates the axes that ordinary summaries often
mix together:

- `identity`: `domain_id`, `domain_type`, `title`, `scale`, scope labels.
- `evidence_trail`: support, counter, correction, boundary, and representative
  source refs.
- `claim_contract`: existing `trust_level`, `action_grammar`,
  `trust_contract`, allowed claim classes, and reopen requirements.
- `activation`: activation cues, negative cues, hook policy, foreground
  projection.
- `lifecycle`: active, contested, stale, blocked, superseded, or retired.
- `lineage`: event ids, version, parent domains, merge/split/supersession.

`working_conclusion_short` is allowed inside a domain brief after explicit
deepen. It is not allowed in default hook text.

## Pinned Boundaries

Pinned boundaries survive coarse-graining. A hard explicit correction, privacy
boundary, safety boundary, current-task fact, or do-not-use-here constraint has
higher priority than weak trends.

Boundary effects include:

- `block_hook`
- `require_source_reopen`
- `block_public_claim`
- `suppress_domain`
- `supersede_prior_conclusion`
- `redirect`

`block_hook` and `suppress_domain` force `ignore_or_blocked`.
`require_source_reopen`, `block_public_claim`, `supersede_prior_conclusion`,
and `redirect` keep the source-court path visible without letting a domain
answer as fact.

## Runtime Exposure

Prompt hooks may render a `continuity_domain_pointer` card. The card may carry:

- `domain_id`
- label/theme
- `action_grammar`
- source refs or reopen plan
- pinned boundary hints
- a compact reason it may matter now

Prompt hooks must not carry the domain working conclusion body. The hook should
say "there is a source-trailed continuity route here", not "this long-term
conclusion is true".

Agent-initiated recall may pull continuity domain pointers and matching pathlet
pointers through `active_recall --mode context`. This path is explicitly
different from passive hooks: it can show route material when the agent asks for
continuity, but it still keeps domain summaries and pathlet summaries out of
factual authority. When a domain or pathlet route matches, the context payload
may include a small `fresh_thread_route_packet` compiled from existing route
primitives. That packet is navigation only: exact, public, sensitive, disputed,
or stale claims still require source reopen.

MCP progressive recall reuses existing tools:

- `recall_context` may return a `continuity_domain` route handle.
- `recall_context` may return a `pathlet` route as a short-lived source-ref
  handle when an ordered pathlet matches before broad manual search.
- `recall_deepen` opens the domain brief and attempts to reopen representative
  clean-source refs.
- `recall_deepen` opens pathlet handles through the carried clean-source refs;
  there is no separate pathlet fact layer.
- `recall_deepen` rejects blocked, stale, superseded, or retired domain handles
  even when the handle carries fresh snapshot fields.
- If a source ref carries `thread_key`, `recall_deepen` may use the machine
  registry to reopen that thread's clean-source store before falling back to
  source-not-found.
- `recall_deepen` validates and reopens the refs carried by the short-lived
  handle. Additional refs in the opened domain brief remain navigation material
  until a later handle or clean-source reopen selects them.
- `get_turn_context` or clean-source search remains the authority for exact
  wording and broader source context.
- If no continuity-domain snapshot is published or readable, active recall and
  MCP context should report the missing snapshot artifact instead of silently
  implying there is no memory.

Macro and Dream consumers may read continuity-domain lifecycle pressure through
the shared runtime recheck event bridge. Contested/counter/correction-heavy
domains map to conflict recheck, stale or superseded domains map to currentness
recheck, pinned boundaries map to restriction diagnostics, and blocked or
retired domains map to route-unavailable diagnostics. These events remain
`direction_only`; active recall must still reopen source before any factual use.

Post-packet relation diagnostics for narrative pathlets, missing-middle
cut-points, route cycles, and navigation-as-claim failures are defined in
[`packet-topology-diagnostics.md`](packet-topology-diagnostics.md). They may
explain a broken pathlet relation, but they do not create a separate pathlet
fact layer.

No new MCP tool is required for Contract v1. Domain handles are short-lived and
become stale when the caller clean source, referenced registry-thread clean
source, or the domain snapshot changes.

## Signal Producers

Signals may feed situation glyphs, not facts:

| Producer | Runtime boundary |
| --- | --- |
| Dream | hypothesis, invitation, draft, or bridge probe only |
| Journey | path/frontier navigation candidate only |
| Hexagram | atmosphere/state-transition direction only |
| Cognitive map | topology and route hint only |
| Source texture | texture signal, not source fact |
| Navigation potential | affordance diagnostic, not truth |
| Working memory | source-backed staging/candidate, not clean source |
| Continuity domain | pointer or brief, not source truth |

Situation glyphs are path-order-sensitive. If the same refs appear in a
different pathlet order, the glyph id changes.

## AGENTS.md And SKILL.md

`AGENTS.md` stays the repo or workspace contract: stable instructions, build
rules, public boundaries, and editing discipline.

`SKILL.md` stays the slim runtime entrypoint, but it should sound like an
agent's own operating posture. It should teach an agent to ask whether
source-backed continuity can change the next action, then actively use
ambient cards, active recall, MCP handles, continuity domain pointers, or clean
source as needed.

Continuity domains do not replace either file. They give agents a durable,
source-trailed place to recover long-running working conclusions without
forcing every prompt hook to inject those conclusions.

## Non-Goals

Contract v1 does not:

- store macro tendencies as writable factual truth
- create a new authority taxonomy
- replace clean source, AGENTS.md, SKILL.md, working memory, or cognitive map
- make hook output a long-term conclusion channel
- create a dashboard, scoring layer, or external model dependency
- treat Dream, hexagram, cognitive-map, or glyph output as evidence
- write raw prompts, raw source text, local paths, or secrets into public
  reports

## Acceptance Criteria

- The architecture doc defines the full Contract v1 shape, including pathlets,
  domains, macro derived pointers, situation glyphs, producers, and non-goals.
- Event materialization accepts only supported event families with usable
  source refs and rejects unresolved refs when clean source is available.
- Snapshots are rebuildable and public-safe.
- Hook rendering emits only pointer cards, not working conclusion bodies.
- Active recall can surface continuity domain handles in
  `working_continuity_brief`, pathlet pointers, and a navigation-only
  `fresh_thread_route_packet`.
- MCP `recall_context` can return domain and pathlet routes; `recall_deepen` can
  open the domain brief plus clean-source trail or the pathlet's clean-source
  refs.
- MCP deepen rejects blocked/stale/superseded/retired domain handles and can
  follow registry-backed `thread_key` refs for cross-thread source reopen.
- The explicit `aippocampus continuity-domain` CLI can produce source-ref-backed
  registry candidates, append events, publish snapshots, and emit public-safe
  reports.
- Pinned boundaries override weak trends.
- Macro tendencies are derived-only and `direction_only`.
- Situation glyphs are direction-only, path-order-sensitive, and blocked or
  redirected by pinned boundaries.
- Tests cover positive and negative cases for these contracts.
