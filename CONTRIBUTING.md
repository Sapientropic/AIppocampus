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

AIppocampus supports Python 3.10 and newer. Before claiming the repository is
healthy, run the fast deterministic path from the repository root:

```sh
python tools/aippocampus/docs/check_docs_health.py --json
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python tools/aippocampus/run_tests.py --tier fast
python -m compileall -q skills plugins tests tools benchmarks benchmark_corpus
```

Run `python tools/aippocampus/run_tests.py --tier full` before release,
public-readiness, or broad refactor claims. The `benchmark` and `slow` tiers are
explicit: use them when touching benchmark runners, prompt-hook integration,
onboarding, plugin packaging, smoke tools, or sync behavior.

For public-readiness changes, also run a secret/local-path scan and inspect any
hits. Test fixtures with `FAKE_TEST_` markers are acceptable; real credentials
or private paths are not.

## Test Debt Policy

- A test belongs in the fast tier only if it is deterministic, cheap, and blocks
  a real user-visible or runtime-contract regression.
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
