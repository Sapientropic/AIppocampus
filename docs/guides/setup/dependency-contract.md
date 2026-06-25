# Dependency Contract

This page is the dependency taxonomy for AIppocampus. Keep it aligned with
`pyproject.toml`, CI workflows, contributor docs, and release docs.

## Runtime

AIppocampus currently has no required third-party runtime dependencies:
`pyproject.toml` declares `dependencies = []`. The default local-first CLI, MCP,
clean-source, registry, search, sync, and benchmark-smoke paths are stdlib plus
package-local code unless a specific optional extra below is installed.

Do not add vector databases, embedding libraries, HTTP clients, or model SDKs as
runtime dependencies only because roadmap docs mention semantic search, RAG-lite,
or provider integrations. Add a runtime dependency only when a real import and a
public contract need it.

## Optional Integrations

`openai-agents` is the user-facing optional integration extra:

```sh
python -m pip install -e ".[openai-agents]"
```

It keeps a compatibility range so downstream apps can test against compatible
SDK releases. CI uses `openai-agents-smoke`, an exact-pinned smoke extra, so the
optional integration smoke does not drift silently.

## Benchmarks

`benchmark` is intentionally empty. Deterministic benchmark smoke uses stdlib
plus checked-in public fixtures. Add packages to this extra only when a committed
deterministic benchmark import requires them.

## Contributor Tooling

Use the exact-pinned `dev` extra for repo checks:

```sh
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The `dev` extra owns Ruff, mypy, coverage, and build versions used by CI. Update
the pins only in a PR that runs the normal docs-health, lint, type, build, and
fast-test gates.

`test-quality` is an opt-in pilot extra for expensive or experimental test
tools. It currently pins Hypothesis for the local lock owner-token property
tests:

```sh
python -m pip install -e ".[test-quality]"
```

Do not add this extra to default `dev`, quick, or PR lanes without a promotion
decision from the relevant guard-tooling issue.

## Release Tooling

Use the exact-pinned `release` extra for package and registry publication:

```sh
python -m pip install -e ".[release]"
```

The `release` extra owns build, twine, and check-jsonschema. It is for release
workflows and release operators, not for normal runtime use.

Package build isolation also uses an exact-pinned `setuptools` backend in
`pyproject.toml`. Bump the backend pin in the same PR as release-tool pin bumps,
after rebuilding the sdist and wheel.

## CI Caching

GitHub Actions uses `actions/setup-python` pip caching with `pyproject.toml` as
the dependency cache key. The cache may speed up downloads, but the exact-pinned
extras are the reproducibility contract. Do not treat a cache hit as evidence
that a dependency update was tested.
