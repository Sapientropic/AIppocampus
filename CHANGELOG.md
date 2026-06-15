# Changelog

All notable public-facing changes to AIppocampus are summarized here. The
project is still alpha; release notes distinguish shipped behavior from
evidence, diagnostics, and claim boundaries.

## Unreleased

The next slice is about fewer sharp edges.

- Agent recall now opens with a tiny action card: the next route, the next
  deepen step, and the same old boundary: do not make claims before source is
  reopened.
- Learning is more useful without getting louder. Tool failures, good command
  order, environment workarounds, and context-reopen saves can become small
  source-backed hints; stale, local-only, or source-thin lessons stay quiet.
- Learned hints now keep their address. A lesson from one project or target no
  longer taps every unrelated `pytest` on the shoulder.
- Action-time hints have a real front door: cache refresh, install/status
  readiness, malformed-cache fail-open behavior, and public-safe JSON that says
  what is installed, what is fresh, and what still needs a refresh.
- AIppo, source-shape routes, macro posture, and subconscious intake now share
  the same discipline: navigation first, source truth later, no backstage
  material promoted just because it is interesting.
- Public and local handoff got less fussy. Public recall output no longer
  exposes local handles or fake-short MCP tokens; MCP errors are marked as
  errors; semantic MCP recall sees the provider-key bridge; route limits reject
  explicit bad values; macOS commands are copy-pasteable; and local install
  sync points ambiguous plugin caches toward the human-friendly reinstall path.
- Benchmark gates are less theatrical. JSON entrypoints separate report
  generation from benchmark quality, public companion reports now say when
  workflow guidance was not measured, and diagnostic wins no longer masquerade
  as public-quality proof or product failure.
- Semantic bridges learned some manners. They now carry source-shaped context,
  can widen search before FTS when there are refs, and keep a ledger of whether
  they actually helped; stale, private, source-free, or wrong-route bridges stay
  quiet. MemoryAgentBench, STATE-Bench, and LongMemEval-V2 reports now include
  AIppocampus runtime arms without pretending those arms are official scores.

Still alpha. Still source-backed. Quieter in the doorway.

## 0.3.3 - 2026-06-15

0.3.3 is a dogfood release for fewer sharp edges.

AIppocampus should feel easier to keep nearby: quieter status, clearer routes,
less release-theater, and fewer places where an agent has to guess whether a
diagnostic is evidence.

- Recall gets better handholds: source-backed aliases, safer candidate
  planning, outcome feedback, route labels that survive packet trimming, and an
  attention-router guard that will not promote a less relevant route just
  because it scored loudly.
- MCP and public outputs are more careful by default. Search is metadata-only
  unless snippets are requested, thread ids are bounded, storage dry-runs are
  public-safe, and sync status gives copyable `aippocampus` commands.
- Install/update is less fussy. `apply --all-local` can refresh the local Codex
  plugin cache when there is one clear target, and status can acknowledge when
  the foreground agent already sees the tools.
- The test and release path is calmer: focused tests first, `pr` at most once
  locally, and release preflight for the few checks that can drift after CI.
- Benchmark and doctor reports are smaller and more honest. A report existing
  is no longer confused with a public-quality claim.

Still alpha. Still source-backed. Fewer knobs in the doorway.

### Compare

- Source range: `v0.3.2..v0.3.3`
- Compare URL:
  https://github.com/Sapientropic/AIppocampus/compare/v0.3.2...v0.3.3

## 0.3.2 - 2026-06-15

0.3.2 is a cleanup release for trust at the edges.

The main change is not louder memory. It is calmer proof. Install, export,
maintenance, benchmark, and release paths now say more clearly what happened,
what is safe to share, and what still needs a human or operator look.

### What Feels Different

- Release checks are less ceremonial. The planner now points to the checks that
  matter for the changed surface, and local preflight no longer tries to be CI.
- Codex plugin install success is readable at a glance. `--json` now returns a
  compact success summary; `--operator-json` keeps the full deep-debug report.
  Rollback also has a dry-run preview.
- Public issue attachments have a real metadata-only `public-export` path.
  Clean-source text, session ids, anchors, graph labels, and searchable SQLite
  indexes stay out.
- Search, recall, MCP tool listing, health, and CLI help now have quieter
  public-safe modes for agents that need the next step, not the whole machine.
- Expected operator failures return structured JSON and useful exit codes
  instead of tracebacks.
- Maintenance and storage reports are bounded by default, with full audits kept
  explicit.
- Warm ambient status now separates queued work from actual worker evidence.
- Benchmark reports are more honest about proxies, fixture gates, and public
  quality claims.

Still alpha. Still source-backed. Less smoke, clearer lantern.

### Compare

- Source range: `v0.3.1..v0.3.2`
- Compare URL:
  https://github.com/Sapientropic/AIppocampus/compare/v0.3.1...v0.3.2

## 0.3.1 - 2026-06-15

0.3.1 is a small release about foreground manners.

AIppocampus can now let architecture-native route work be felt without turning
the frontstage into a wiring diagram. When attention-router, macro, topology,
or local/global cues matter, agents get a tiny navigation hint and the same old
boundary: deepen before claims.

Human recall output also stops printing long opaque navigation handles by
default. The handle is still there for JSON and MCP callers; people get a short
next action instead.

Still alpha. Still source-backed. Less transport noise, more useful handhold.

### Compare

- Source range: `v0.3.0..v0.3.1`
- Compare URL:
  https://github.com/Sapientropic/AIppocampus/compare/v0.3.0...v0.3.1

## 0.3.0 - 2026-06-15

0.3.0 is the release where AIppocampus becomes easier to invite into an
agent's day.

The promise is the same: continuity should come from source trails, not from a
model pretending it remembers. What changed is the feel. The package now gives
agents clearer doors to knock on, clearer reasons to stay quiet, and a much
shorter path from "is this installed?" to "yes, here is the next source-backed
step."

### What Feels Different

- First run is calmer. The Codex plugin install path, update status, onboard
  status, sync status, and nested CLI help now speak in one public language.
- Agents get better handholds: recall, AIppo, deepen, and explain are exposed
  as agent-native affordances instead of hidden machinery.
- Prompt-hook recall is more polite. Small casual prompts stay cheap; explicit
  continuity prompts route toward the right next action.
- Successful plugin verification is now readable at a glance with
  `--compact-json`, without local paths or unrelated host noise.
- Benchmark and evidence work is better organized, with stronger gates against
  turning diagnostics into grand claims.

### Still Alpha

- 0.3.0 does not change the package classifier. AIppocampus remains
  `Development Status :: 3 - Alpha`.
- It does not claim universal recall quality, hosted-service maturity,
  all-client coverage, or a stable Python SDK.
- Live pilots, benchmark reports, Dream/macro/Telepathy work, and LongMemEval
  source-side evidence are useful signposts. They are not a victory lap.

### Compare

- Source range: `v0.2.0..v0.3.0`
- Compare URL:
  https://github.com/Sapientropic/AIppocampus/compare/v0.2.0...v0.3.0

## 0.2.0 - 2026-06-07

0.2.0 is the first broad continuity release after the 0.1.x metadata and
discovery repair tags. Before this release-prep change, the mainline range from
`v0.1.1` through PR #889 covered 392 commits touching 802 files, with 252
merged PRs after the v0.1.1 release PR.

### Highlights

- Reframed AIppocampus around source-backed continuity, not generic task
  memory. The installable skill, root agent guidance, and public-facing docs now
  lead with clean source, source refs, packet trust, and the difference between
  navigation scent and evidence (#805, #806, #807, #808, #812, #816).
- Added recall packet trust/action grammar: `direction_only`,
  `reopenable_route`, `bounded_evidence`, `source_open`, and
  `ignore_or_blocked`. Foreground packets can now stay precise about what an
  agent may do next without pretending every cue is proof (#761, #770, #788,
  #798, #839).
- Advanced fresh-thread and ambient recall from demo fixtures toward a more
  usable runtime path. This includes fresh-thread action contracts, living cue
  cache selection, prompt-hook consumption, hot-path recall intent guards,
  active path packets, magic-preserving warm activation, and the #281 field
  continuity readout (#497, #508, #606, #632, #654, #731, #770, #814, #889).
- Expanded the source-backed evidence surface with new or hardened benchmark
  families: multimodal corpus/media/NIAH fixtures, Field Continuity,
  hippocampal recall and hard negatives, segmented merge policy, E2E50 silent
  constraints, semantic robustness Track S, AMemGym, MemoryAgentBench, and
  benchmark priority/claim-boundary maps (#494, #504, #529, #537, #538, #539,
  #553, #562, #565, #572, #730, #737, #738, #748, #774, #885).
- Added stronger recall navigation, route diagnostics, and repo familiarity
  paths. The runtime now has source-joined routing diagnostics, navigation
  potentials, source texture sidecars, repo familiarity affordances, issue-route
  quality smoke, and live semantic route actionability readouts (#551, #552,
  #628, #655, #767, #813, #845, #855, #875, #876, #878).
- Added coding-continuity read models and integrity guards, including
  SequencePacket/Episode/Arc evidence, code-state anchors, correction
  host-event capture, weak-covered operation validation, conflicting operation
  diagnostics, and an operation claim integrity gate (#766, #779, #857, #861,
  #862, #874, #886, #887).
- Deepened Dream/Journey and subconscious work from planning notes into
  bounded runtime and evidence slices: Dream manual review ingestion,
  user-visible eval axes, trust horizon gates, Journey resonance, working-memory
  compaction, delivery prefiltering, source-body stance/atmosphere arcs,
  constructive invitations, bridge hypotheses, and coding Dream probe selection
  (#613, #618, #619, #629, #645, #648, #717, #844, #871, #880, #881, #888).
- Hardened storage, sync, and maintenance internals. This includes storage GC,
  generation pointer publishing, reader pins, encrypted sync v2 boundaries,
  migration recovery diagnostics, key-provider contracts, encrypted sync head
  graph conflicts, provider metadata evidence, local update status/apply, and
  preemptive lifecycle health/snapshot paths (#524, #636, #686, #705, #708,
  #719, #720, #721, #722, #723, #724, #728, #729, #740, #741, #778, #841,
  #842).
- Improved public package, CI, and release hygiene. Python support is now
  explicitly 3.12/3.13, deterministic benchmark smoke and optional OpenAI
  Agents SDK smoke run in CI, maintainer shipping lanes and release checklist
  are documented, dependency and safe-environment contracts are clearer, MCP
  registry readiness checks were repaired, public client matrix evidence was
  refreshed, and CodeQL alert surfaces were cleared (#474, #495, #496, #499,
  #509, #510, #511, #687, #692, #702, #883).
- Removed resolved package-only and flat compatibility shims after the package
  entrypoints and public CLI facade were made clearer. Use the packaged
  `aippocampus` CLI and module-owner entrypoints rather than old flat helper
  scripts (#479, #480, #547, #548, #549, #550, #596, #677, #685).

### Compatibility Notes

- Public package metadata now declares version `0.2.0`.
- Python 3.12 remains the support floor; CI/package metadata cover Python 3.12
  and 3.13. Python 3.10 and 3.11 are not public support targets.
- The runtime still has no mandatory third-party runtime dependencies. Release,
  development, benchmark, and optional OpenAI Agents extras remain opt-in.
- Legacy helper shims have continued to shrink. Scripts and docs should prefer
  `aippocampus ...` or package-owned modules over old flat helper paths.

### Known Boundaries

- This changelog prepares the 0.2.0 release notes; it does not create the tag,
  publish PyPI, update MCP Registry metadata, or create a GitHub release.
- At the time of the 0.2.0 preparation notes, the release checklist still
  expected a broad local evidence sweep. Current releases should use
  `python tools/aippocampus/test_plan.py --release-preflight --json` and
  `docs/guides/setup/release-checklist.md` instead of replaying the historical
  quick/pr/benchmark/coverage/full stack by reflex.
- Current evidence does not claim interactive Codex Desktop marketplace
  click-through, third-party install review, macOS/Linux signed binaries, broad
  provider/client coverage, or production-quality private-history recall.
- Many benchmark and smoke surfaces are intentionally contract smokes or
  diagnostic proxies. They should not be summarized as live model quality,
  private-history quality, or broad superiority claims unless a dedicated
  dated evidence owner says so.

### Compare

- Source range: `v0.1.1..HEAD`
- Compare URL:
  https://github.com/Sapientropic/AIppocampus/compare/v0.1.1...main

## 0.1.1 - 2026-06-02

- Metadata repair release tag for the package and discovery surface.

## 0.1.0 - 2026-06-02

- Initial public package/discovery tag.
