# Write-Like Memory Decision Card

Role: foreground agent decision card.
Status: current public guide.

AIppocampus has several write-like paths. They are not the same kind of
"memory." Before writing, choose the smallest durable thing that matches the
intent.

| Intent | Use | Writes | Durability | Authority | Next Action |
| --- | --- | --- | --- | --- | --- |
| Mark whether a route helped or was wrong | `aippocampus agent feedback <route_id> --outcome helped --feedback-jsonl <local-feedback.jsonl> --json` | yes, to the chosen local JSONL | durable only with an explicit path | low-authority navigation metadata | keep working; reopen source before claims |
| Quiet a route or ticket here | `aippocampus do-not-use-here <route-or-ticket-id> --feedback-jsonl <local-feedback.jsonl> --json` | yes, to the chosen local feedback lane | scoped activation pressure, not deletion | low-authority suppression hint | use why-not/why-recall for explanation; reopen source before claims |
| Leave a margin note for a later agent | `aippocampus self-note append --current-thread "short note"` | yes | local low-authority note | `direction_only` scent | use as posture; reopen source for facts |
| Prepare action-time hints | `aippocampus hooks action refresh-cache --write --json` | cache only | prepared default local navigation cache | navigation only | install/status the action hook if desired |
| Inspect continuity-domain candidates | `aippocampus continuity-domain report --json` | no | read/report first; append/publish is operator work | route planning, not fact text | use scoped preview before any append/publish |
| Sync or register the local tool surface | `aippocampus update status` / `aippocampus plugin install --codex --verify` | control-plane artifacts | explicit local setup | not memory truth | verify foreground tool visibility |

When not to write:

- If you need factual continuity, use `agent recall`, `agent deepen`, or
  `search` first.
- If the input is raw tool output, logs, or source text, do not store it as a
  self-note. Summarize the decision breadcrumb or attach source refs through the
  proper route.
- If the write would ingest broad private history, preview first and ask for
  consent before registration.

The rule of thumb: feedback tunes routes, self-notes carry posture, caches help
tool-time nudges, continuity domains preserve routes, and source remains the
ground.
