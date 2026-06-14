# Release Checklist

Use this checklist before creating a public AIppocampus tag, GitHub release,
plugin package, or broad public-readiness claim. The detailed evidence ledger
lives in `docs/evidence/readiness/public-readiness-verification.md`; this page is the
repeatable gate list.

Release tags, package metadata, registry metadata, release notes, and
public-readiness claims always use the strict PR lane in
[`CONTRIBUTING.md`](../../../CONTRIBUTING.md#maintainer-shipping-lanes). Do not
route them through a maintainer light lane only because the diff is small.

## Version And Scope

- Pick the tag name and release scope before running verification.
- Confirm the release notes distinguish shipped behavior from roadmap work.
- Confirm `pyproject.toml`, plugin metadata, README claims, and public API docs
  describe the same supported surface.
- Confirm the package classifier, README claims, public API docs, release
  notes, and dated readiness decision in
  [`classifier-policy.md`](../../evidence/readiness/classifier-policy.md) agree.
  Do not change the development-status classifier without an approved dated
  decision for the exact release.
- Link any known limitations to active issues rather than burying them in the
  release notes.

## Required Gates

Release verification has three owners. Do not flatten them into one local
marathon.

1. The release PR proves the merged source through CI.
2. The local tag preflight checks metadata, public-boundary hygiene, and any
   focused changed-surface tests that have not already passed in CI.
3. The publish workflow proves and publishes the built artifact.

Start with the planner:

```sh
python tools/aippocampus/test_plan.py --json
python tools/aippocampus/test_plan.py --release-preflight --json
```

Run the focused commands from the changed-surface plan. During development,
`quick` is useful as a cheap inner loop. For closeout, remember that `pr`
already includes `quick`; do not run both by reflex.

For a normal patch or minor release whose PR CI is green, the local tag
preflight is:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
python tools/aippocampus/release/check_agent_discovery_release.py --offline --json
git clean -ndX
git diff --check
```

Before publication, the online agent-discovery check may report `pending`
because PyPI and MCP Registry cannot contain the new version yet. Use the
offline local metadata check before tagging; use the strict online check only
after publication.

PR CI owns these routine release signals by default:

- Ruff and mypy.
- `python tools/aippocampus/run_tests.py --tier pr` under coverage.
- Sharded `broad-pr`.
- `benchmark-smoke --benchmark-suite-profile public-fast`.
- Python 3.13 `quick`.
- Focused macOS default `TMPDIR` path-identity smoke.
- Wheel contract against the CI-built artifact.

The publish workflow owns:

- `python -m pip install -e ".[release]"`.
- Docs health and `pr` tests at the tag commit.
- MCP Registry schema validation.
- `python -m build --sdist --wheel`.
- `python -m twine check dist/*`.
- `python tools/aippocampus/release/check_wheel_contract.py --wheel dist/*.whl --json`.
- PyPI and MCP Registry publication.

Escalate locally only when the changed surface owns the risk:

- Run `broad-pr` locally for tier-runner, manifest, or CI changes when waiting
  for CI would hide the failure source.
- Run `benchmark-smoke --benchmark-suite-profile public-fast` locally for
  benchmark runner, benchmark fixture, or public benchmark claim changes.
- Run `full` locally only for repository-health or public-readiness claims that
  explicitly need the slow, benchmark, and release-heavy surface.
- Run manual macOS install smoke for package/install/path-identity changes, or
  when the release itself claims fresh macOS install behavior.

The wheel contract builds the wheel into a fresh venv by default and verifies
the documented CLI, MCP, generic JSONL import/search/reopen, public module
imports, config doctor, and isolated hook rollback surfaces without provider
credentials or network dependency resolution. In CI, pass `--wheel dist/*.whl`
to reuse an already-built release artifact.

The Ruff hard gate is deliberately staged through `pyproject.toml`: `E9/F/I/B`
must pass in normal CI and release checks. Use the advisory all-rule report
below when choosing future lint hardening work; do not treat its full count as a
release blocker without a separate rule-selection issue:

```sh
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus --select ALL --statistics
```

Run the full tier before a repository-health or broad public-readiness claim
that actually needs full coverage. Do not use it as a routine patch-release
tax after green PR CI:

```sh
python tools/aippocampus/run_tests.py --tier full
```

For an agent-discoverability release, run the stricter public-state gate after
PyPI and MCP Registry publication:

```sh
python tools/aippocampus/release/check_agent_discovery_release.py --fail-on-not-ready
```

The non-strict check may report `pending` before publication. Do not translate
that pending state into a public claim.

Run the complete benchmark, slow, provider, integration, or smoke tiers when the
release touches their surface. Do not use `quick`, `pr`, or benchmark-smoke
coverage to claim that cloud providers, physical device sync, prompt hooks,
external-model routes, large public-corpus adapters, or private real-history
packs were exercised.

PR and push CI include a focused macOS default `TMPDIR` path-identity guard, but
that job is only a regression gate for the recurring `/var` and `/private/var`
class. It intentionally does not repeat the full `pr` tier. For package,
install, or path-identity changes, or when a release explicitly claims fresh
macOS install behavior, run the manual macOS install smoke:

```sh
gh workflow run macos-install-smoke.yml -f runner-label=macos-latest -f python-version=3.12
```

## Privacy And Secret Scan

- Scan for real local paths, API keys, bearer headers, cookies, connection
  strings, age private identities, SSH keys, and credential URLs.
- Confirm `.aippocampus/`, registry exports, raw rollouts, sync bundles,
  generated indexes, vault exports, `.coverage*`, `coverage.xml`, and `htmlcov/`
  are not committed.
- Inspect hits manually. Synthetic `FAKE_TEST_` values may be valid fixtures;
  real user memory or credentials are not.
- Recheck `docs/guides/community/privacy-security-checklist.md` before publishing demos or
  bundles.

## Release Artifact Review

- Confirm `SECURITY.md` is present and linked from README.
- Confirm install and Quick Start commands still match the current CLI facade.
- Confirm release notes include exact verification commands and dates.
- Confirm optional external-model and encrypted-sync claims name the tested
  provider, dataset, device, or smoke boundary.
- Confirm generated artifacts are either intentionally uploaded as CI artifacts
  or ignored locally.

## Tag And Publish

- Create the tag only after the verification evidence is recorded.
- For the agent-discoverability release, configure the PyPI trusted publisher
  for the `release` environment before pushing the tag or manually running
  `publish-agent-discovery.yml`.
- After the tag exists, either push the tag or run `Publish Python Package And
  MCP Registry` from GitHub Actions with `release_tag` set to the existing tag.
- Draft the GitHub release from the tag, linking the evidence ledger and known
  follow-up issues.
- If a plugin or package is produced, verify install, uninstall, and rollback
  instructions with a fresh target directory before linking it publicly.
