# First Recall Decision Card

Status: canonical first-recall front door for humans and agents.

Use this card when AIppocampus is installed or being evaluated and the next
goal is one useful source-backed recall moment, not a tour of every subsystem.

## One Public-Safe Receipt

This is the shape a first run should make visible before benchmark, hook, sync,
or operator detail:

```text
cue: "without pretending it has innate memory"
source-backed hit: msg_public_001 from examples/public-memory-bundle/clean-source
snippet: "can an agent catch up without pretending it has innate memory?"
boundary: the snippet supports only the quoted source trail; summaries and route ids are navigation.
next: open/deepen the source turn before using exact wording or making a broader claim.
```

Copyable local demo command from a source checkout:

```sh
aippocampus search "without pretending it has innate memory" --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

If the user only has a vague cue, use the same shape with `agent recall` and
then deepen the selected route:

```sh
aippocampus agent recall "old decision or handoff cue" --json
aippocampus agent deepen --request 1 --last-recall --json
```

## Decide The First Move

1. Choose the setup branch before running recall commands:

   ```sh
   # Trusted Codex/local setup.
   aippocampus plugin install --codex --verify
   aippocampus update status --json

   # No-clone/read-only probe.
   uvx aippocampus --help
   uvx aippocampus onboard --provider auto --status
   ```

   If local source is already registered, skip setup/probe and start with the
   recall or exact-search branch below.

1. If the user remembers a vague decision, handoff, correction, or project cue,
   ask the agent facade for a bounded foreground packet:

   ```sh
   aippocampus agent recall "old decision or handoff cue" --json
   aippocampus agent deepen --request 1 --last-recall --json
   ```

2. If the user remembers exact wording, search clean source directly:

   ```sh
   aippocampus search "distinctive old phrase"
   ```

3. If no source is registered, or the first route is stale or blocked, use
   read-only recovery cards:

   ```sh
   aippocampus health
   aippocampus onboard --provider auto --status
   ```

4. If no local source is registered yet, preview before writing:

   ```sh
   aippocampus onboard --provider claude-code --dry-run --json
   aippocampus import conversation --format generic-jsonl --input <path> --dry-run --json
   ```

   Register selected local history only after explicit consent.

## What Counts As Success

- A source-backed snippet, route, or source window appears.
- The output says what to do next without exposing local private paths.
- Exact, stale, sensitive, disputed, or high-risk claims still reopen source.

## What Not To Do First

- Do not start with benchmark suites, storage GC, sync repair, Telepathy,
  Observatory, or object storage unless the user asked for that operator task.
- Do not silently install hooks. In trusted Codex setup, hook/action-hint setup
  is core continuity plumbing after plugin trust, status, and rollback are
  clear.
- Do not treat a scent, summary, AIppo clause, self-note, or route id as a fact.
- Do not import broad private history without a preview and explicit consent.
