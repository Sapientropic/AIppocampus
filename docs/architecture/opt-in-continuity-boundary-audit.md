# Opt-In Continuity Boundary Audit

Role: current contract.

This audit classifies boundaries that can either protect AIppocampus or quietly
erase its core usefulness. The product promise is source-backed continuity, not
manual memory chores. Safety should live at the right layer: install/enable
policy, source refs, audit trails, dedupe, repair/rebuild, and kill switches.

## User-Facing Policy

After a user installs/enables an ordinary deterministic continuity producer,
source-ref-backed maintenance should be quiet by default, visible in logs or
reports, easy to disable, and rebuildable. It should not ask for repeated
per-event confirmation when the event family is deterministic and already
bounded by source refs.

Prompt hooks are still a tighter boundary: they may read and render existing
continuity material, but they should not scan history or write durable domain
events while the user is typing.

External LLM/provider routes remain a separate first-run choice. Ask once when
enabling LLM-backed semantic/background routes; if the user declines or has no
key, keep the no-key source-backed path useful instead of treating missing keys
as failure.

## Boundary Table

| Surface | Classification | Current action |
| --- | --- | --- |
| Source refs, exact wording, public claims, secrets, credentials, local paths | `must_keep` | Require source reopen for claims; keep public reports sanitized. |
| Prompt-hook durable writes while the user is typing | `must_keep` | Prompt hooks consume snapshots and scents only. |
| Missing refs, unresolved clean-source refs, currentness with no target domain | `must_keep` | Defer or reject rather than writing a confident continuity event. |
| Deterministic salience rows with resolving refs after the producer is enabled | `move_to_enable_policy` | `continuity_domain_salience_adapter.py` can run in `report` or `write_when_enabled`. |
| Per-event confirmation for deterministic correction/counter/boundary events | `replace_with_auditability` | Use stable event ids, duplicate suppression, append-only logs, and public count summaries. |
| `aippocampus continuity-domain produce --append` as the normal user workflow | `debug_only` | Keep it for operator backfill, repair, and tests; do not present it as the primary ADHD-facing path. |
| Registry producer emitting only `domain_created` before the salience adapter | `replace_with_auditability` | Treat as the pilot gap now addressed by #1432: enabled deterministic salience can write through the auditable event path instead of asking for manual append. |
| Split/merge/reinterpretation/pathlet lifecycle automation | `debug_only` | Keep as operator-authored or future automation until source-ref mapping and user-facing recovery semantics are stronger. |
| Help-first install probes before a continuity moment | `move_to_enable_policy` | Public docs should lead toward an agent-mediated plugin/setup path, then one source-backed recall moment, with probes as diagnostics. |
| Optional provider-key setup | `move_to_enable_policy` | Ask once for LLM-backed semantic/background routes; no-key fallback remains source-backed. |
| Magic-moment examples living only in evidence review paths | `move_to_enable_policy` | Link them from first-run/product paths as product feel, not benchmark proof. |

These are the only classifications used for this closeout: `must_keep`,
`move_to_enable_policy`, `replace_with_auditability`, `debug_only`, and
`remove_or_relax`. No first-pass boundary currently needs `remove_or_relax`
alone; the harmful cases above become safer by moving consent to enable policy
or replacing confirmation with auditability.

## Pilot Change

The current pilot is the subconscious salience to continuity-domain adapter:

- `report` mode gives a public-safe no-write dry run.
- `write_when_enabled` appends and publishes through the existing
  continuity-domain event path when writes are enabled and not suppressed by
  `--dry-run` or `--no-write`.
- Duplicate salience rows do not create duplicate durable domain events.
- Public job JSON exposes counts, statuses, event-kind buckets, and boundary
  text only. Source refs and raw source text stay local.

This pilot satisfies the first ADHD-friction check for this track: enabled
deterministic continuity maintenance does not require repeated per-event
confirmation, and report/write status is visible without a separate manual
append chore.

Implementation issue #1432 is closed with this pilot implemented, and #1433 is
closed with the continuity-domain producer capability / UX-tier docs updated.
The linked docs now frame explicit `aippocampus continuity-domain
produce --append` and manual append/publish commands as trusted local
debug/operator/backfill surfaces, not the ordinary user path.

## ADHD-Friction Acceptance Checks

- Enabled deterministic continuity production must not ask for per-event
  confirmation when refs resolve and the event family is already in the
  conservative adapter map.
- The ordinary path must not require a diagnostic/status detour before the
  first continuity moment. Diagnostics such as `--help`, `--dry-run`, status
  probes, and manual append remain useful repair/operator surfaces, not the
  headline workflow.
- The kill switch remains simple: set the producer policy to `off`, run with
  `--no-write` / `--dry-run`, or rebuild snapshots from the append-only event
  log after repair.

## Open Follow-Ups

- Root README, Start Here, Agent Context, Public API, and the install guide now
  point ordinary Codex setup toward agent-mediated plugin verify, hooks with
  rollback, one explicit provider-key choice, and a working no-key fallback.
  Website/demo copy should follow the same ordering when it is next edited.
- Continuity-domain lifecycle events now have a shared
  `runtime_recheck_event` bridge for macro/Dream/active-recall recheck
  pressure. Deeper macro arbitration, scheduling, and Dream quality claims still
  need their own evidence before promotion.
- Source-shape and factual-recall issues should reuse this boundary: local
  runtime artifacts may preserve navigation handles, while public reports stay
  aggregate and sanitized.

Related issues: #1432, #1433, #1434, #1435, #1421, #1417, #1185.

## Closeout Status

#1435 can close as a docs/audit slice if the linked public onboarding docs keep
the same ordering: agent-mediated Codex plugin path first, hooks after machine
trust, one explicit LLM-key choice, useful no-key fallback, and diagnostics or
manual CLI commands only as probes, repair, automation, or operator fallback.
