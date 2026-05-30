# Release Checklist

Use this checklist before creating a public AIppocampus tag, GitHub release,
plugin package, or broad public-readiness claim. The detailed evidence ledger
lives in `docs/evidence/public-readiness-verification.md`; this page is the
repeatable gate list.

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
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
python tools/aippocampus/run_coverage.py --tier fast
```

Run the full tier before a repository-health, public-readiness, or release
claim:

```sh
python tools/aippocampus/run_tests.py --tier full
```

Run slow, benchmark, provider, or smoke tiers when the release touches their
surface. Do not use fast-tier coverage to claim that cloud providers, physical
device sync, prompt hooks, external-model routes, or private real-history packs
were exercised.

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
- Draft the GitHub release from the tag, linking the evidence ledger and known
  follow-up issues.
- If a plugin or package is produced, verify install, uninstall, and rollback
  instructions with a fresh target directory before linking it publicly.
