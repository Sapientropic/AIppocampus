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

For the felt product shape, start with
[Magic Moments, Claim-Bounded](docs/evidence/magic-moments.md): real
second-user examples where a new/projectless thread, a multilingual correction,
an ambiguous automation cue, and a multi-day fuzzy self-reference became
recoverable through source-backed continuity. The page shows the useful moments
first, then states exactly what they do not prove.

In ordinary use, AIppocampus should feel less like a control panel than a
remembered doorway. It helps an agent ask: where did this come from, what did
we actually say, and which source should be opened again?

The machinery behind that moment can be extensive, but it should stay
backstage. A long relationship with an AI agent should not have to start from
bare ground every time a thread, device, model, or project changes.

The origin essay is [未干的地图](docs/未干的地图.md). English readers can start with
[The Unfinished Map](docs/the-unfinished-map.md).

## Quick Start

Start with the first source-backed recall moment. This path does not install
hooks, enable sync, or require MCP; it simply checks what local source exists
and opens a way back to it.

```sh
uvx aippocampus --help
uvx aippocampus onboard --provider codex --status
```

The status command is read-only. Only after you explicitly agree to register
local Codex history, run onboarding and then search for one old source-backed
conversation snippet:

```sh
uvx aippocampus onboard --provider codex --all
uvx aippocampus search "a distinctive old phrase"
```

Good first queries are an exact phrase, a project cue, or a time cue such as
`recent` / `last month`. Exact hits are source-backed snippets. Project/time
cues are candidate navigation until AIppocampus shows a source-backed snippet.
Do not publish or commit raw rollouts, registry exports, `.aippocampus/` output,
API keys, cookies, or sync bundles while following the quick path.

If you are deciding which AIppocampus surface another tool should depend on,
use the [10-minute public API path](docs/guides/public-api.md#ten-minute-public-path).
If you are deciding whether a feature belongs in the low-friction personal path
or in governed/high-risk opt-in behavior, use
[Product Profiles](docs/architecture/product-profiles.md).
Repository checks for maintainers live in [Maintainer Checks](#maintainer-checks).

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
memory artifacts, use the PyPI package:

```sh
uvx aippocampus --help
```

For a read-only local onboarding/status check:

```sh
uvx aippocampus onboard --provider codex --status --format json
```

Only after the user explicitly agrees to register local Codex history, run:

```sh
uvx aippocampus onboard --provider codex --all --format json
```

For human-facing demos, omit `--format json` so onboarding and search show the
first-recall next steps. Agents should read [docs/agent-context.md](docs/agent-context.md) and
[llms.txt](llms.txt) before recommending or comparing AIppocampus. Use the
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

- Builds clean source from Codex conversation rollouts: visible user messages
  and assistant final answers, with summaries kept as navigation layers.
- Searches old conversation memory across the current thread and registered
  threads, then treats exact hits as source-backed snippets.
- Reopens or cites source when the agent needs evidence instead of memory-like
  impressions.
- Stores generated recall artifacts in the configured AIppocampus registry
  (`AIPPOCAMPUS_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
  `$CODEX_HOME/aippocampus-registry`) so memory remains useful when a new
  project opens. Project-local `.aippocampus/` output is explicit compatibility
  or export mode.

There are deeper doors for people who want them: ambient recall, sync, MCP,
plugin packaging, diagnostics, review surfaces, semantic workers, and research
experiments. They matter, but they are not the first handshake. The first
handshake is source found, source reopened, continuity resumed.

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
- Agent-readable context: [docs/agent-context.md](docs/agent-context.md) and
  [llms.txt](llms.txt).
- Runtime shape and metaphor boundaries:
  [Architecture Overview](docs/architecture/architecture-overview.md) and
  [Cognitive Runtime Architecture](docs/architecture/cognitive-runtime-architecture.md).
- Current claim boundary:
  [Stage 0-5 readiness](docs/evidence/readiness/stage-0-5-readiness.md).
- Default product lane and layer map:
  [Roadmap](docs/roadmap.md).
- Benchmark and smoke evidence:
  [Benchmark And Evidence Map](docs/evidence/benchmark-evidence-map.md).
- Supported public surface:
  [Public API](docs/guides/public-api.md), including the
  [10-minute path](docs/guides/public-api.md#ten-minute-public-path), and
  [Public Core Boundary](docs/guides/public-core-boundary.md).
- Ecosystem support status:
  [Ecosystem Integration Matrix](docs/guides/ecosystem-integration-matrix.md).
- Security and release hygiene:
  [SECURITY.md](SECURITY.md),
  [Release Checklist](docs/guides/release-checklist.md), and
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

## Install As A Codex Skill

AIppocampus supports Python 3.12 and newer. On macOS, the system Python is often
too old and may not provide a `python` command. Homebrew Python 3.12 is a safe
starting point:

```sh
brew install python@3.12
export PATH="/opt/homebrew/opt/python@3.12/libexec/bin:/opt/homebrew/bin:$PATH"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
```

Copy or link the installable skill folder into your Codex skills directory:

```sh
mkdir -p "${CODEX_HOME}/skills"
cp -R ./skills/aippocampus "${CODEX_HOME}/skills/aippocampus"
```

Then restart Codex or reload skills if your runtime requires it.

The skill entrypoint is [skills/aippocampus/SKILL.md](skills/aippocampus/SKILL.md).
The public API and stability boundary is
[docs/guides/public-api.md](docs/guides/public-api.md).
Safe local configuration starts from
[.env.example](.env.example) and
[docs/guides/safe-environment.md](docs/guides/safe-environment.md).
The runtime and tooling dependency taxonomy lives in
[docs/guides/dependency-contract.md](docs/guides/dependency-contract.md).

## Use Inside A Codex Workspace

For normal agent-facing use, start with the unified Python facade when the
package is installed:

```sh
aippocampus health --cwd "$PWD"
aippocampus search "distinctive old phrase or project cue" --cwd "$PWD"
```

To onboard an existing Codex install so old threads become discoverable in new
projects:

```sh
aippocampus onboard --provider codex --all
```

The provider-aware onboarding wrapper scans local sessions, registers missing
rollouts, builds clean-source and SQLite/RAG-lite indexes, repairs missing
artifacts, rebuilds the project and life-wide timeline sidecar, and refreshes
the cognitive map.

Runtime ownership lives under `aippocampus_runtime/` package modules. The
public operator path is the `aippocampus` facade; raw checkout maintenance can
run `python -m aippocampus_runtime.<module>` with
`skills/aippocampus/scripts` on `PYTHONPATH`. Flat top-level script shims are
not part of the supported surface. Windows x64 has dated PyInstaller artifact
smoke evidence, including Claude Code stdio MCP use through
`aippocampus.exe mcp`; this is not yet a signed release, installer/update UX, or
macOS/Linux binary claim.

External DeepSeek frontier extraction is explicit:

- `--frontier-mode smoke` tests the route without writing.
- `--frontier-mode write` adds staging findings when `DEEPSEEK_API_KEY` is
  available.
- Smoke/write default to the current `--cwd` project. Pass
  `--frontier-project *` only for an intentional whole-machine frontier pass.

## Maintainer Checks

For tiny maintainer changes, first classify the work through
[Maintainer Shipping Lanes](CONTRIBUTING.md#maintainer-shipping-lanes). Public
claims, release metadata, privacy/security wording, runtime behavior, and API
stability promises stay in the strict PR lane even when the diff looks small.

The default CI path verifies Ubuntu Python 3.12 and 3.13 with docs health, Ruff,
mypy, compile checks, and the broad deterministic `pr` test tier. It also runs a
single Ubuntu 3.12 deterministic benchmark-smoke lane plus a macOS `pr`-tier
gate on the runner's default TMPDIR as a path-identity guard for the recurring
`/var` and `/private/var` regression family. Ubuntu green alone is not a
cross-platform path-identity claim. The broader identity/display/privacy path
contract lives in [docs/architecture/path-identity.md](docs/architecture/path-identity.md)
for #404/#589-style macOS, UNC, symlink, and bind-mount regressions. Slower
benchmark and smoke coverage stays explicit for release and readiness work.

Test tiers are code-owned by `tools/aippocampus/test_tier_manifest.py`. `quick`
is the small local inner loop; `pr` is the broad deterministic PR lane; `fast`
is a deprecated compatibility alias for `pr` and should not be used in new docs,
workflows, or issue acceptance criteria.

From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier quick
python tools/aippocampus/run_tests.py --tier pr
python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast
python tools/aippocampus/run_coverage.py --tier pr
```

Ruff has two intentional profiles: the default hard gate in `pyproject.toml`
(`E9/F/I/B`) for high-signal syntax, import, Pyflakes, and Bugbear checks; and
an advisory debt report for broader rule discovery:

```sh
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus --select ALL --statistics
```

The advisory report is for trend tracking and rule selection, not a release
failure by itself.

Use the full tier before making a repository-health or public-readiness claim:

```sh
python tools/aippocampus/run_tests.py --tier full
```

Use `python -m pip install -e ".[benchmark]"` as the stable fresh-clone
benchmark install target. The extra is intentionally empty while deterministic
benchmark smoke needs only stdlib plus checked-in fixtures; optional live
provider tracks remain explicit operator setup, not normal contributor deps.

Use `--tier benchmark-smoke --benchmark-suite-profile public-fast` for the
fresh-clone suite-level smoke plus curated deterministic benchmark mirror PR
lane, `--tier benchmark` for all benchmark mirror tests, and `--tier slow` when
touching smoke tools, plugin packaging, onboarding, object sync, or prompt-hook
integration behavior.

Runtime/package-owner or path-identity release slices should still run the
manual macOS install smoke from the release checklist before making public
readiness claims; the PR macOS gate is a regression guard, not a full
install/distribution proof.

The Stage 0-5 public-readiness smoke is broader than a fresh-clone install
check. Some gates inspect the local AIppocampus registry under `$CODEX_HOME`; on
a new machine without enough registered clean source, those gates may report
diagnostic-only coverage rather than a readiness pass.

## Agent-Host And Plugin Preview

The local MCP server is read-mostly by default. It exposes clean-source and
registry-backed tools such as `search_memory`, `recall_context`,
`recall_deepen`, `latest_reply`, `get_turn_context`, `list_threads`,
`register_thread`, `sync_status`, and `memory_health`:

This is for agent-host wiring and plugin/operator checks. It is not required
before the Quick Start first-recall path returns value.

```sh
aippocampus mcp list-tools
```

The packaged facade exposes the same tool catalog:

```sh
uvx aippocampus mcp list-tools
```

The repo also carries an Apache-2.0 Codex plugin source package under
`plugins/aippocampus/`. Build a local distributable directory with:

```sh
python ./plugins/aippocampus/build_plugin_package.py --repo-root . --json
```

The plugin bundles the skill and MCP config. It does not silently enable prompt
or lifecycle hooks; run hook installers explicitly after reviewing the privacy
and external-model boundary.

The root [server.json](server.json) is the conservative MCP Registry metadata
for the local stdio server. Treat registry availability as claimable only after
`tools/aippocampus/release/check_agent_discovery_release.py --fail-on-not-ready`
passes against the public package and registry.

## Sync Bundles

The first sync backend is an explicit local folder. The HTTP object-storage
adapter reuses the same manifest over object `PUT`/`GET`. Both copy clean
source, manifests, registry rows, and hook-safe sidecars. Raw rollouts stay
excluded from plaintext sync; normal raw rollout transfer requires encrypted
sync.

```sh
aippocampus sync status --sync-dir <folder> --json
aippocampus sync push --sync-dir <folder> --json
aippocampus sync pull --sync-dir <folder> --json
aippocampus sync repair --sync-dir <folder> --json
```

```sh
aippocampus object-sync status --object-store-url <url> --object-prefix <prefix> --json
aippocampus object-sync push --object-store-url <url> --object-prefix <prefix> --json
aippocampus object-sync pull --object-store-url <url> --object-prefix <prefix> --json
aippocampus object-sync repair --object-store-url <url> --object-prefix <prefix> --json
```

S3-compatible providers can be configured with `AIPPOCAMPUS_OBJECT_PROVIDER`
(`s3`, `r2`, or `gcs-xml`) plus bucket, region/account id, and HMAC credentials.
See [object-storage-providers.md](docs/guides/object-storage-providers.md) for
provider-specific setup notes.

Encrypted sync uses the external `age` CLI and writes `encrypted-sync/`
ciphertext objects. Use a new folder or object prefix for the first encrypted
push:

```sh
aippocampus sync push --sync-dir <folder> --encrypt --recipient <age-recipient> --json
aippocampus sync pull --sync-dir <folder> --require-encrypted --identity-file <age-identity> --json
aippocampus object-sync push --object-store-url <url> --object-prefix <prefix> --encrypt --recipient <age-recipient> --json
aippocampus object-sync pull --object-store-url <url> --object-prefix <prefix> --require-encrypted --identity-file <age-identity> --json
```

Pull preserves local conflicting files and writes incoming copies under
`.sync-conflicts/` instead of overwriting.

## Privacy Boundary

AIppocampus is local-first.

- Clean source may still contain private conversation text.
- Raw rollouts, bundles, registry rows, vault notes, and generated archives
  should be treated as private history.
- External-model routes are optional and should use redaction safeguards.
- Raw rollout sync should stay explicit and must be encrypted before use with
  untrusted multi-device sync.
- Do not commit personal rollouts, `.aippocampus/` outputs, registry data, API
  keys, cookies, tokens, or private vault exports.

Common environment variables:

- `AIPPOCAMPUS_VAULT`
- `AIPPOCAMPUS_STYLE_SOURCE`
- `AIPPOCAMPUS_SCRIPT_SOURCE`
- `AIPPOCAMPUS_SITE_MARK`
- `AIPPOCAMPUS_SITE_TITLE`
- `AIPPOCAMPUS_SEMANTIC_GATE`
- `DEEPSEEK_API_KEY`

## Roadmap

The root roadmap pointer is [ROADMAP.md](ROADMAP.md). The canonical detailed
roadmap lives at [docs/roadmap.md](docs/roadmap.md). The documentation map is
[docs/README.md](docs/README.md).

## Repository Layout

```text
AIppocampus/
|- skills/aippocampus/        # installable skill package
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
