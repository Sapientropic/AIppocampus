<p align="center">
  <img src="docs/guides/assets/aippocampus-readme-hero.jpg" alt="A shadow figure and a light figure clasp hands in a ruined circular hall, with light opening between them." width="100%" />
</p>

<h1 align="center">AIppocampus</h1>

<!-- mcp-name: io.github.Sapientropic/aippocampus -->

<p align="center">
  <em>A source-backed continuity layer for long-running relationships with AI agents.</em>
</p>

AIppocampus began with a human problem: every new agent session can be bright,
capable, and strangely newborn. Work may survive in commits and notes while the
path behind the work falls back into silence.

This project gives future agents a way to find that path again. It keeps source
reachable, preserves the conditions of return, and lets a new conversation begin
with honest continuity instead of pretending there was never a break.

> Source is the ground. Summaries are weather.

First useful continuity move after AIppocampus is visible to an agent:

```sh
aippocampus agent recall "old decision or handoff cue" --json
aippocampus agent deepen --request 1 --last-recall --json
```

That turns an old cue into a route the agent can deepen before making claims.
From a public source checkout, an exact-search demo can still show the source
substrate without touching private history:

```sh
aippocampus search "without pretending it has innate memory" --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

In ordinary use, AIppocampus should feel less like a control panel than a
remembered doorway. It helps an agent ask: where did this come from, what did
we actually say, and which source should be opened again?

The machinery behind that moment can be extensive, but it should stay
backstage. A long relationship with an AI agent should not have to start from
bare ground every time a thread, device, model, or project changes.

The origin essay is [未干的地图](docs/未干的地图.md). English readers can start with
[The Unfinished Map](docs/the-unfinished-map.md).
For role-based documentation paths, use
[Start Here](docs/start-here.md).

## Quick Start

First run should end in one useful decision card, then one source-backed recall
route. The fuller guided version is
[First Recall Decision Card](docs/guides/first-recall-decision-card.md); role
paths live in [Start Here](docs/start-here.md).

If `aippocampus` already exists from a source checkout or editable install,
start here:

```sh
aippocampus start --json
aippocampus agent recall "old decision or handoff cue" --json
aippocampus agent deepen --request 1 --last-recall --json
```

`start` is the foreground chooser. If it says source is missing or stale, stay
read-only until the user agrees to register local history:

```sh
aippocampus onboard --provider auto --status --json
aippocampus onboard --provider codex --dry-run --json
```

After consent, choose the provider path from
[Start Here](docs/start-here.md) rather than copying a setup matrix out of the
README. Codex, Claude Code, generic JSONL import, plugin install, hooks,
export, and sync each have different consent and host boundaries.

If the command does not exist yet, use the no-clone probe first:

```sh
uvx aippocampus --help
uvx aippocampus onboard --provider auto --status --json
```

That proves the package is reachable without registering private history. If a
public no-private-data demo is all you need, use the bundled clean source:

```sh
aippocampus search "without pretending it has innate memory" --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

Exact search is the proof lane when the user remembers wording; agent
recall/deepen is the continuity lane when the user has a cue. For the short
public walkthrough, use
[10-Minute Public Path](docs/guides/ten-minute-public-path.md). For the felt
product shape after the first route, read
[Magic Moments, Claim-Bounded](docs/evidence/magic-moments.md). For the current
proof map, use the [Can-Claim Ladder](docs/evidence/can-claim-ladder.md). For a
compact origin and current-value trail, use the
[Public Provenance And Current Value Ledger](docs/evidence/public-provenance-ledger.md).

After a useful deepen, `aippocampus export --json` and
`aippocampus sync --json` are the carry-forward checks for the next thread,
device, or project.

Good first queries are an exact phrase, a project cue, or a time cue such as
`recent` / `last month`. Exact hits are source-backed snippets. Project/time
cues are candidate navigation until AIppocampus shows a source-backed snippet.
Do not publish or commit raw rollouts, registry exports, `.aippocampus/` output,
API keys, cookies, or sync bundles while following the quick path.

When you are choosing an integration surface, see the
[Ecosystem Integration Matrix](docs/guides/ecosystem-integration-matrix.md).
When you are deciding whether a feature belongs in the low-friction personal
path or in governed/high-risk opt-in behavior, use
[Product Profiles](docs/architecture/host/product-profiles.md).
Repository checks for maintainers live in
[Operator And Maintainer Paths](#operator-and-maintainer-paths).

## AIppocampus For Coding Agents

The narrow usable product lane today is local, source-backed continuity for
Codex/Claude-style long-running work: register local conversation source after
consent, search or reopen old snippets, and treat recall scents or repo
familiarity as navigation until source is reopened.

Start with the
[Coding-Agent Memory Lane](docs/guides/coding-agent-memory.md) when deciding
whether to recommend AIppocampus as an agent-memory tool. It includes the
3-5 minute demo path, evidence drawer, and "recommend / do not recommend"
boundary without duplicating the public API or readiness docs.

## Agent One-Command Probe

When an AI agent needs to verify the public CLI without cloning or writing local
memory artifacts, use the PyPI package, then prefer a first recall route over a
diagnostic tour:

```sh
uvx aippocampus --help
uvx aippocampus agent recall "old decision or handoff cue" --json
uvx aippocampus agent deepen --request 1 --last-recall --json
uvx aippocampus search "a distinctive old phrase"
```

Use exact search as a fallback when the user remembers wording or the recall
route is blocked.

For a read-only local onboarding/status check:

```sh
uvx aippocampus onboard --provider auto --status --json
```

This is a read-only provider matrix, not consent to ingest every detected
provider. Only after the user explicitly agrees to register local history,
route to [Start Here](docs/start-here.md) or the
[First Recall Decision Card](docs/guides/first-recall-decision-card.md) for the
right provider-specific write path.

For human-facing demos, omit `--format json` so onboarding and search show the
first-recall next steps. Agents should read [docs/agent-context.md](docs/agent-context.md) and
[llms.txt](llms.txt) before recommending or comparing AIppocampus. Use the
[first recall decision card](docs/guides/first-recall-decision-card.md) when the
goal is one useful source-backed moment before broader setup. Use the
GitHub `uvx --from git+...` form only when intentionally testing an unreleased
main-branch snapshot.

## What It Is

AIppocampus is the canonical public home for an external hippocampus for agents:
a local-first memory and continuity system that keeps original conversation
source available across projects, devices, and casual life-wide conversations.
The hippocampus language is a design metaphor, not a biological claim; the
[architecture overview](docs/architecture/architecture-overview.md#metaphor-discipline)
maps each major metaphor to its runtime mechanism, current claim, and boundary.

Project work is one surface. The deeper aim is continuity across work, reading,
reflection, unfinished questions, and the small phrases that make a relationship
recognizable again.

## What It Carries

At the center, AIppocampus keeps source close enough that continuity can be
honest instead of theatrical:

- Builds clean source from supported local conversation providers: Codex
  rollouts, Claude Code transcripts, or explicit generic JSONL visible-message
  exports, with summaries kept as navigation layers.
- Searches old conversation memory across the current thread and registered
  threads, then treats exact hits as source-backed snippets.
- Reopens or cites source when the agent needs evidence instead of memory-like
  impressions.
- Stores generated recall artifacts in the configured AIppocampus registry
  (`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
  `$CODEX_HOME/aippocampus-registry`) so memory remains useful when a new
  project opens. Project-local `.aippocampus/` output is explicit compatibility
  or export mode.

Ambient hooks are close to the front door because they keep continuity from
collapsing back into manual search. There are still deeper doors for people who
want them: MCP wiring, sync, plugin packaging, diagnostics, review surfaces,
semantic workers, and research experiments. They matter, but they should not
stand in front of the first handshake: source found, source reopened,
continuity resumed.

## First Stops

- Philosophy and origin: [未干的地图](docs/未干的地图.md) and
  [The Unfinished Map](docs/the-unfinished-map.md).
- Real user-visible continuity examples:
  [Magic Moments, Claim-Bounded](docs/evidence/magic-moments.md).
- Narrow coding-agent product lane:
  [Coding-Agent Memory Lane](docs/guides/coding-agent-memory.md).
- Evidence and field reports:
  [public evidence surface](https://www.aippocampus.com/evidence/) and
  [community field-report boundary](docs/evidence/community-field-reports.md).
- Website source:
  [`Sapientropic/aippocampus.com`](https://github.com/Sapientropic/aippocampus.com).
- Agent-readable context: [docs/agent-context.md](docs/agent-context.md) and
  [llms.txt](llms.txt).
- Runtime shape and metaphor boundaries:
  [Architecture Overview](docs/architecture/architecture-overview.md) and
  [Cognitive Runtime Architecture](docs/architecture/runtime/cognitive-runtime-architecture.md).
- Current claim boundary:
  [Stage 0-5 readiness](docs/evidence/readiness/stage-0-5-readiness.md).
- Default product lane and layer map:
  [Roadmap](docs/roadmap.md).
- Benchmark and smoke evidence:
  [Benchmark And Evidence Map](docs/evidence/benchmark-evidence-map.md).
- Supported public surface:
  [10-minute public path](docs/guides/ten-minute-public-path.md),
  [Public API](docs/guides/public-api.md), and
  [Public Core Boundary](docs/guides/public-core-boundary.md).
- Ecosystem support status:
  [Ecosystem Integration Matrix](docs/guides/ecosystem-integration-matrix.md).
- Security and release hygiene:
  [SECURITY.md](SECURITY.md),
  [Release Checklist](docs/guides/setup/release-checklist.md), and
  [maintainer shipping lanes](CONTRIBUTING.md#maintainer-shipping-lanes).
- Full documentation map: [docs/README.md](docs/README.md).

## Reading For The Soul

The research notes carry the human shape of the project. They are speculative
frames, not runtime contracts, but they explain the taste behind the machinery:

- [The Pearl of Presence](docs/research/pearl-of-presence.md) asks why retrieval
  without accumulated acquaintance can still feel absent.
- [Source as World, Interpretation as Weather](docs/research/source-as-world.md)
  gives AIppocampus its grounding rule: many meanings can grow from one shared
  world, and the world must have happened.
- [Journey Tracking](docs/research/journey-tracking.md) follows continuity as a
  first-person plural journey, with source-backed waypoints instead of a flat
  user profile.
- [Dream Task Design](docs/research/dream-task-design.md) sketches the
  subconscious layer: quiet work that integrates what the foreground could not
  finish.
- [Ambient Associative Recall](docs/research/ambient-associative-recall.md)
  describes how old memory can return as a scent before it becomes an
  interruption.
- [Long Garden](docs/research/seeds/README.md) keeps far-future seeds without
  turning them into default product promises or open-issue clutter.

## Operator And Maintainer Paths

The README stays close to the product path. Operator commands, source-checkout
setup, plugin packaging, sync, release checks, and benchmark notes live in the
guides that own those contracts:

AIppocampus supports Python 3.12 and newer. On macOS, Homebrew Python 3.12 is
the documented baseline before running source-checkout verification.

- Install paths and hook setup: [Install Guide](docs/guides/install-guide.md).
- Supported CLI, MCP, JSON, environment variables, and import policy:
  [Public API](docs/guides/public-api.md).
- Safe configuration: [.env.example](.env.example) and
  [Safe Environment](docs/guides/setup/safe-environment.md).
- Dependency ownership:
  [Dependency Contract](docs/guides/setup/dependency-contract.md).
- MCP, plugin, sync, and object-storage details:
  [docs/README.md](docs/README.md). For sync, start with the
  [Sync Decision Card](docs/guides/install-guide.md#sync-decision-card)
  before local-folder or object-storage command matrices.

For repository contributors, the dev extra install path is:

```sh
python3 -m pip install -e ".[dev]"
```

Public claims still need the maintainer lanes in
[CONTRIBUTING.md](CONTRIBUTING.md#maintainer-shipping-lanes). The default CI
keeps one canonical Ubuntu Python 3.12 `pr` lane with coverage, a Python 3.13
`quick` compatibility lane, and a focused macOS default TMPDIR path-identity
gate; Ubuntu green alone is not a broad cross-platform path-identity claim. The
broader boundary lives in
[docs/architecture/source/path-identity.md](docs/architecture/source/path-identity.md).

## Privacy Boundary

AIppocampus is local-first.

- Clean source may still contain private conversation text.
- Raw rollouts, bundles, registry rows, vault notes, and generated archives
  should be treated as private history.
- External-model routes are optional and should use redaction safeguards.
- Raw rollout sync should stay explicit and must be encrypted before use with
  untrusted multi-device sync. Start with the read-only
  [Sync Decision Card](docs/guides/install-guide.md#sync-decision-card) before
  choosing push, pull, repair, or object storage.
- Do not commit personal rollouts, `.aippocampus/` outputs, registry data, API
  keys, cookies, tokens, or private vault exports.

Common non-secret configuration:

- `AIPPOCAMPUS_REGISTRY_DIR` / `AIPPOCAMPUS_HOME`
- `AIPPOCAMPUS_VAULT`
- `AIPPOCAMPUS_STYLE_SOURCE`
- `AIPPOCAMPUS_SCRIPT_SOURCE`
- `AIPPOCAMPUS_SITE_MARK`
- `AIPPOCAMPUS_SITE_TITLE`
- `AIPPOCAMPUS_SEMANTIC_GATE`

Optional provider secrets are separate. Basic source search, MCP/plugin setup,
and local hooks do not require them. Set `AIPPOCAMPUS_DEEPSEEK_API_KEY` or an
`AIPPOCAMPUS_OPENAI_COMPAT_*` route only when you explicitly want semantic or
background model work. Provider-native env names are custom-route choices, not
built-in defaults. Values must never be committed or printed.

## Roadmap

The root roadmap pointer is [ROADMAP.md](ROADMAP.md). The canonical detailed
roadmap lives at [docs/roadmap.md](docs/roadmap.md). The documentation map is
[docs/README.md](docs/README.md).

## Repository Layout

```text
AIppocampus/
|- skills/aippocampus/        # installable skill package
|- skills/aippocampus-ux/     # agent-facing UX review skill
|- plugins/aippocampus/       # Codex plugin source package
|- docs/                      # origin essay, design notes, guides, evidence
|- docs/guides/assets/        # public README and documentation artwork
|- sources/                   # lightweight provenance catalog
|- tests/                     # repository-level unit and integration tests
|- tools/                     # smoke, docs-health, and maintenance tools
|- README.md
|- ROADMAP.md
|- AGENTS.md
`- LICENSE
```

## License

The public AIppocampus repository is licensed under Apache-2.0.

The Apache-2.0 public core covers the code, docs, local tools, schemas, MCP
surface, plugin packaging, public examples, and bundled project artwork shipped
in this repository unless a bundled third-party asset says otherwise. Hosted
services, enterprise governance, managed graph/semantic layers, support, and
other operated product surfaces can be offered under separate commercial or
product-specific terms.

Private user memory data is not project code. Raw rollouts, clean-source
exports, registry rows, sync bundles, vault exports, generated indexes, and
thread anchors remain private user artifacts unless their owner explicitly
publishes them.

See [docs/guides/public-core-boundary.md](docs/guides/public-core-boundary.md)
for the canonical licensing, adapter, schema, third-party asset, and relicensing
boundary. See [docs/guides/public-api.md](docs/guides/public-api.md) for
supported CLI, MCP, environment-variable, JSON, and import-stability
expectations.
