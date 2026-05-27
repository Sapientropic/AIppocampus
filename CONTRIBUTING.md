# Contributing To AIppocampus

AIppocampus is a source-backed continuity layer for long-running relationships
with AI agents. Contributions should preserve that purpose: clean source and
source references are truth; summaries, graphs, and model findings are
navigation layers.

## Public Boundary

Do not commit private memory artifacts:

- raw Codex rollouts or archived sessions
- `.aippocampus/` output
- `$CODEX_HOME/aippocampus-registry/` exports
- thread anchors from personal workspaces
- private vault exports
- API keys, cookies, bearer headers, credentials, or local machine paths

Use the fake fixtures under `skills/aippocampus/tests/` when testing redaction
or local-path handling.

## Development Checks

Before claiming the repository is healthy, run from `skills/aippocampus/`:

```powershell
python scripts\check_docs_health.py --json
python -m unittest discover -s tests
python -m compileall -q .
python -m ruff check . --config ..\..\pyproject.toml
```

For public-readiness changes, also run a secret/local-path scan and inspect any
hits. Test fixtures with `FAKE_TEST_` markers are acceptable; real credentials
or private paths are not.

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
