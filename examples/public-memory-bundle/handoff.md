# Public Example Memory Bundle

This bundle is synthetic. It demonstrates AIppocampus shape without private
rollouts, private registry rows, or local machine paths.

- Raw rollout included: no
- Clean source: `clean-source/messages.jsonl`
- Search index sample: `index/messages.jsonl`
- Registry sample: `registry/threads.json`
- Life-wide demo includes a synthetic casual-important metaphor/pivot turn and
  a semantic scope-label sidecar.

Try:

```powershell
aippocampus search "recurring question" --cwd . --clean-source-dir .\examples\public-memory-bundle\clean-source --json
aippocampus search "lighthouse metaphor pivot" --cwd . --clean-source-dir .\examples\public-memory-bundle\clean-source --scope-label personal_reflection --scope-label idea_seed --json
```
