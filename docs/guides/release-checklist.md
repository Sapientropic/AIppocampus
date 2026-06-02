# Release Checklist

Use this checklist before creating a public AIppocampus tag, GitHub release,
plugin package, or broad public-readiness claim. The detailed evidence ledger
lives in `docs/evidence/readiness/public-readiness-verification.md`; this page is the
repeatable gate list.

Release tags, package metadata, registry metadata, release notes, and
public-readiness claims always use the strict PR lane in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#maintainer-shipping-lanes). Do not
route them through a maintainer light lane only because the diff is small.

## Version And Scope

- Pick the tag name and release scope before running verification.
- Confirm the release notes distinguish shipped behavior from roadmap work.
- Confirm `pyproject.toml`, plugin metadata, README claims, and public API docs
  describe the same supported surface.
- Link any known limitations to active issues rather than burying them in the
  release notes.

## Required Local Checks

Run from the repository root:

```sh
uv run --python 3.12 python -c 'import aippocampus_runtime; print("uv-run-ok")'
python -m pip install -e .
python -m build --sdist --wheel
python tools/aippocampus/docs/check_docs_health.py --json
python tools/aippocampus/release/check_agent_discovery_release.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast
python tools/aippocampus/run_coverage.py --tier fast
```

The Ruff hard gate is deliberately staged through `pyproject.toml`: `E9/F/I/B`
must pass in normal CI and release checks. Use the advisory all-rule report
below when choosing future lint hardening work; do not treat its full count as a
release blocker without a separate rule-selection issue:

```sh
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus --select ALL --statistics
```

Run the full tier before a repository-health, public-readiness, or release
claim:

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

Run the complete benchmark, slow, provider, or smoke tiers when the release
touches their surface. Do not use fast-tier or benchmark-smoke coverage to claim
that cloud providers, physical device sync, prompt hooks, external-model routes,
large public-corpus adapters, or private real-history packs were exercised.

PR and push CI include a macOS fast-tier path-identity guard on GitHub's
default `TMPDIR`, but that job is only a regression gate for the recurring
`/var` and `/private/var` class. For runtime/package-owner or path-identity
changes, also run the manual macOS install smoke before making a release or
public readiness claim:

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
- Recheck `docs/guides/privacy-security-checklist.md` before publishing demos or
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
