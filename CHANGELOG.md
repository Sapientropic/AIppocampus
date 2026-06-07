# Changelog

All notable public-facing changes to AIppocampus are summarized here. The
project is still alpha; release notes distinguish shipped behavior from
evidence, diagnostics, and claim boundaries.

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
- Before tagging, run the full release checklist in
  `docs/guides/release-checklist.md`, including build, release extra install,
  docs health, agent-discovery release check, Ruff, mypy, quick/pr/benchmark
  smoke, coverage, full tier, and privacy/secret scans.
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
