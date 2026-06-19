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

## Cold Start Versus Steady State

First recall has two different experiences:

- **steady state**: local clean source and route/index artifacts already exist;
  start with `aippocampus start --json`, then recall/deepen;
- **cold start/setup**: clean source is missing, stale, or not yet registered;
  preview or register source first, and expect the first useful recall to spend
  time preparing source/index artifacts.

Do not imply private memory is ready until source is available. A trusted
checkout can offer a read-only probe or the public demo fixture, but that is not
the same as private source readiness. After registration/build artifacts exist,
ordinary recall should be faster and should stay on the compact recall/deepen
route unless exact latest, sensitive, stale, disputed, or high-risk claims need
source reopen.

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

   `aippocampus start --json` reports `first_recall_readiness`. Treat
   `phase=steady_state_available` as the ordinary recall path. Treat
   `cold_start_setup_required`, `cold_start_probe_or_public_demo`, or
   `cold_start_maintenance_required` as honest setup/progress states, not
   proof that memory is already ready.

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
   aippocampus onboard --provider codex --dry-run --json
   aippocampus onboard --provider codex --cwd . --json
   aippocampus onboard --provider claude-code --dry-run --json
   aippocampus onboard --provider claude-code --cwd . --json
   aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json
   aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --json
   ```

   Replace `./conversation.jsonl` with the user-selected export. Register
   selected local history only after explicit consent. Status cards are
   read-only; the `--cwd .` provider commands and explicit import are the
   source-registration writes.

5. After a successful deepen, carry the reopened context only when the user is
   moving to another thread, device, or project:

   ```sh
   aippocampus export --json
   aippocampus sync --json
   ```

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
