# First Recall Decision Card

Status: canonical first-recall front door for humans and agents.

Use this card when AIppocampus is installed or being evaluated and the next
goal is one useful source-backed recall moment, not a tour of every subsystem.

## Decide The First Move

1. If the user remembers exact wording, search clean source first:

   ```sh
   aippocampus search "distinctive old phrase"
   ```

2. If the user remembers a vague decision, handoff, correction, or project cue,
   ask the agent facade for a bounded foreground packet:

   ```sh
   aippocampus agent recall "old decision or handoff cue" --json
   aippocampus agent deepen --request 1 --last-recall --json
   ```

3. If no source is registered, or the first route is stale or blocked, use
   read-only recovery cards:

   ```sh
   aippocampus health
   aippocampus onboard --provider auto --status
   ```

4. If no local source is registered yet, preview before writing:

   ```sh
   aippocampus onboard --provider claude-code --dry-run --format json
   aippocampus import conversation --format generic-jsonl --input <path> --dry-run --json
   ```

   Register selected local history only after explicit consent.

## What Counts As Success

- A source-backed snippet, route, or source window appears.
- The output says what to do next without exposing local private paths.
- Exact, stale, sensitive, disputed, or high-risk claims still reopen source.

## What Not To Do First

- Do not start with benchmark suites, storage GC, sync repair, Telepathy,
  Observatory, hook install, or object storage unless the user asked for that
  operator task.
- Do not treat a scent, summary, AIppo clause, self-note, or route id as a fact.
- Do not import broad private history without a preview and explicit consent.
