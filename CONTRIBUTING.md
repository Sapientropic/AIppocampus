# Contributing To AIppocampus

![Hands holding a crystal heart](.github/assets/community/contributing-crystal-heart.jpg)

AIppocampus is a source-backed continuity layer for long-running relationships
with AI agents. Contributions should preserve that purpose: clean source and
source references are truth; summaries, graphs, and model findings are
navigation layers.

The best contribution usually has a small surface and a clean receipt: what it
changes, what proves it, and what it still cannot claim.

## Public Boundary

Do not commit private memory artifacts:

- raw Codex rollouts or archived sessions
- `.aippocampus/` output
- `$CODEX_HOME/aippocampus-registry/` exports
- thread anchors from personal workspaces
- private vault exports
- API keys, cookies, bearer headers, credentials, or local machine paths

Use the fake fixtures under `tests/aippocampus/` when testing redaction
or local-path handling.

## Licensing Boundary

Contributions intentionally submitted to this public repository are expected to
be Apache-2.0 contributions unless explicitly marked otherwise. Do not submit
third-party code, corpora, generated memory data, or private conversation
exports unless you have the right to publish them.

The canonical split between Apache-2.0 public core, private user data, and
commercial/separate-license product surfaces is
`docs/guides/public-core-boundary.md`.

## Development Checks

AIppocampus's public Python support floor is Python 3.12. CI and package
metadata currently prove Python 3.12 and 3.13; Python 3.10 and Python 3.11 are
unsupported public targets unless package metadata, docs, and workflows are
widened in the same change. Before claiming the repository is healthy, run the
deterministic PR path from the repository root:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier quick
python tools/aippocampus/run_tests.py --tier pr
python -m compileall -q skills plugins tests tools benchmarks benchmark_corpus
```

Test tiers are explicitly classified in `tools/aippocampus/test_tier_manifest.py`.
`quick` is the small local inner loop; `pr` is the broad deterministic PR lane;
`fast` remains only as a deprecated compatibility alias for `pr`. New test
modules must be classified in the manifest before they can enter any tier.

Run `python tools/aippocampus/run_tests.py --tier full` before release,
public-readiness, or broad refactor claims. The `benchmark`, `slow`, `smoke`,
and `integration` tiers are explicit: use them when touching benchmark runners,
prompt-hook integration, onboarding, plugin packaging, smoke tools, provider
contracts, browser/MCP surfaces, or sync behavior.

For public-readiness changes, also run a secret/local-path scan and inspect any
hits. Test fixtures with `FAKE_TEST_` markers are acceptable; real credentials
or private paths are not.

## Maintainer Shipping Lanes

Use this section as the canonical lane policy for tiny maintainer changes.
README, release, and public-API docs should link here instead of repeating the
rules.

Start every lane decision with this claim-impact checklist. If the change
affects any item below, keep it in the strict PR lane unless a maintainer
explicitly records why existing evidence already covers the impact:

- install, support, adoption, or fresh-user success claims
- benchmark, smoke, readiness, or evidence interpretation
- privacy, security, source-backed guarantees, or private-data handling
- public API stability promises, CLI/MCP schema meaning, or documented return
  code behavior
- third-party ecosystem support status
- `can claim` / `cannot claim` boundaries
- release tags, package metadata, registry metadata, or release notes consumed
  by users or agents

**Strict PR lane**: use the normal branch, PR, CI, review/watch, and merge path
for runtime behavior, hooks, sync, registry, search ranking, benchmark scoring,
release tags, published package metadata, public evidence claims, privacy or
security wording, external-model behavior, and any claim-impact checklist hit.
Release/public-readiness changes also use the release checklist.

**Maintainer light lane**: allowed only for tiny, reversible edits with no
claim-impact hit, such as typo fixes, docs formatting, small site copy/layout
cleanup that does not change claims, issue/project metadata cleanup, or wording
that restates already-verified evidence without widening it. Run at least:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
git diff --check
```

Also inspect the diff for private paths and secret-like strings when the edit
touches public docs or assets. The preferred ruleset stance is narrow owner or
maintainer bypass for this lane only when GitHub branch protection permits it;
if no bypass is available, use a tiny PR instead. Do not use the light lane for
runtime code, release metadata, public-claim wording, or anything that needs CI
to prove behavior.

**Small-code auto-PR lane**: use a PR, but keep it lightweight and let CI do the
review gate. This fits tiny tooling fixes, test-only guards, local maintenance
scripts outside the shipped runtime path, or checker/parser compatibility fixes
that do not alter public behavior. A minimal `gh` flow is:

```sh
git switch -c sapientropic/<short-topic>
git add <files>
git commit -m "<clear change>"
git push -u origin HEAD
gh pr create --base main --fill
gh pr merge --auto --merge --delete-branch
```

Run focused local tests before opening the PR, and do not skip CI for code. If a
small-code change later touches public contracts, release evidence, runtime
behavior, or privacy/security boundaries, move it back to the strict PR lane.

## Test Debt Policy

- A test belongs in the `quick` tier only if it is deterministic, cheap, and a
  useful local inner-loop guard. Broader deterministic coverage belongs in
  `pr`; expensive, integration-like, provider, install, prompt-hook, smoke, or
  benchmark tests must live in an explicit manifest tier or smoke lane.
- Agent guard tests are part of the product process here. Keep cheap
  architecture and docs-health guards when they prevent recurring agent mistakes:
  missing public docs, leaked private artifacts, runtime packages absorbing repo
  tools, import cycles, unchecked high-risk scripts, or hook/orchestrator
  boundaries that have broken before.
- Do not add tests that only mirror strings from CI, pyproject, docs, or a
  preferred file layout. Let the real command or focused helper test own that
  signal.
- Benchmark quality, public-readiness smokes, plugin install checks, and
  end-to-end prompt-hook flows stay in explicit tiers unless a small unit slice
  can catch the same failure.
- New tests should name the failure they would catch. If the failure is "someone
  moved code to a different file", prefer an import-cycle, public API, or runtime
  behavior check over source-text assertions.

## Design Rules

- Keep `skills/aippocampus/SKILL.md` as a slim runtime entrypoint.
- Put runtime contracts under `skills/aippocampus/references/`.
- Put product direction, research, and release notes under `docs/`.
- Keep generated artifacts out of the repo by default.
- Make external-model routes optional, redacted, and explicit.
- Do not narrow the project into repo-task memory only; life-wide continuity is
  part of the product.

## Pull Request Shape

A useful PR should state:

- what Stage 0-5 requirement it advances
- what source-backed evidence or tests prove the change
- what cannot be claimed yet
- what private-data boundary was checked

Use the repository PR template as the minimum receipt. For broader ideas,
start with a GitHub Discussion or a focused issue before opening a large patch.
