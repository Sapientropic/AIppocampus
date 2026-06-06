# Correction Reconsolidation

Status: first deterministic runtime prototype implemented; live hook capture and
private real-history adjudication remain future work.
Origin: user/product discussion, 2026-05-28.
Related: [Ambient Associative Recall](ambient-associative-recall.md),
[Dream Task Design](dream-task-design.md),
[Technical Differentiation Analysis](../planning/technical-differentiation-analysis.md),
[Memory Decision Benchmark Plan](../evidence/benchmarks/memory-decision-benchmark-plan.md).

## Problem

Work-task memory has a sharper reliability requirement than broad ambient
recall.

In a long coding or research thread, the user may correct the agent's claim,
scope, route, or assumption. That correction often matters later, especially
after compaction or after many turns of tool work. If it stays only in the
visible conversation, the next activation can drift back to the old mistaken
route. If it is promoted as memory too eagerly, the system may preserve a user
correction that was itself wrong or only locally true.

So the unit to capture is not "the user said X, therefore X is true." The unit
is a source-backed correction event that needs later reconsolidation.

## Design Goal

AIppocampus should preserve high-value user corrections, failed-route lessons,
accepted decisions, and task invariants across compaction without treating them
as automatic truth.

The foreground hook should capture and route events. Detached semantic dream
work should adjudicate whether a correction was valid, adopted, refuted, or
still uncertain. Deterministic routing should then decide whether the result
belongs in active task anchors, soft working memory, promotion candidates, or a
negative "do not promote" note.

## Two-Hook Loop

Correction reconsolidation starts from two semantic moments, then maps those
moments onto Codex hook events.

```text
UserPromptSubmit
  -> detect possible correction / failed-route signal
  -> write correction_activation_event with source refs
  -> optionally warm the thread cache for the current topic epoch

Stop / finish / post-work checkpoint
  -> capture model outcome, changed files, test evidence, and final claim
  -> write correction_outcome_event linked to the activation

Detached dream worker
  -> compare correction, outcome, clean source, and verification evidence
  -> emit a source-backed adjudication candidate

Router
  -> active_task_anchor | working_memory | promotion_candidate
     | refuted_correction | confirm_when_relevant
```

The first hook opens the reconsolidation window. The second hook supplies
evidence about whether the correction actually held after work was done.

## Hook Timing Matrix

The matrix below is the planning contract for Codex hook timing. It keeps the
semantic boundary clear: hooks capture moments and source refs; detached dream
work performs judgment.

| Codex event | AIppocampus role | Default behavior | Do not use it for |
|---|---|---|---|
| `SessionStart` | Rehydrate the working surface at thread start, resume, clear, or compact-start. | Load hot task anchors, registry readiness, and stale-cache signals; return only compact context. | Whole-history scans, semantic adjudication, or multi-minute onboarding. |
| `UserPromptSubmit` | Open a correction or recall window before the model sees the user turn. | Detect explicit correction, failed-route, recall, or continuation cues; write `correction_activation_event`; inject a few hot anchors or source-backed recall cards. | Treating the prompt as truth, running heavy semantic work, or relying on matchers. |
| `PreToolUse` | Preview the next action against active continuity anchors. | When active anchors exist, add lightweight model-visible context such as scope reminders, definition-of-done reminders, or evidence-capture expectations for the upcoming tool call. Prefer narrow matchers for `Bash`, `apply_patch`, and relevant MCP tools. | Security policy, permission enforcement, secret scanning ownership, or broad command rewriting. Those belong to Codex and agent-framework guardrails. |
| `PermissionRequest` | Usually out of scope for AIppocampus memory. | Leave approval decisions to Codex, user policy, enterprise policy, or the host agent framework. At most, record that an approval boundary occurred if a later source-backed audit needs it. | Memory-driven allow/deny decisions, bypassing approvals, or encoding project memory as security policy. |
| `PostToolUse` | Capture fresh evidence after tools run. | Record `tool_input`, sanitized `tool_response`, exit status, changed-file hints, test/build/search evidence, and link them to open correction windows. This is the main evidence hook for `correction_outcome_event`. | Undoing side effects, making final semantic judgments, or storing raw tool payloads as memory. |
| `SubagentStart` | Propagate the parent continuity contract into delegated work. | Inject active task anchors, write boundaries, and correction windows that the subagent needs; keep it compact and source-backed. | Giving subagents broader memory than the parent task requires. |
| `SubagentStop` | Reconcile delegated findings back into the parent thread. | Capture final subagent claim, transcript ref, changed paths, unresolved risks, and whether it adopted or contradicted active anchors. | Promoting subagent claims without parent-side or source-backed review. |
| `Stop` | Close the turn and enqueue consolidation. | Capture final assistant claim, adoption/ignored signal, unresolved test state, and enqueue detached dream review. Continue the turn only for narrow deterministic blockers. | Long-running maintenance, global association rebuilds, or turning every correction into formal memory. |
| `PreCompact` | Preserve continuity before context is rewritten. | Write a bounded private emergency snapshot of visible user/final tail turns not fully represented in clean source, then flush open correction windows, active task anchors, source refs, and recent outcome evidence so compaction cannot erase them. | Late semantic judgment, raw rollout copying, or large rebuilds under compaction pressure. |
| `PostCompact` | Rehydrate continuity after context loss. | Report the latest emergency snapshot as sanitized recovery diagnostics, re-inject high-value anchors only when visibility changed, and mark horizon loss for Track D style checks. | Repeating still-visible context, treating the compacted summary as authoritative source, or promoting emergency snapshots above clean source. |

### Reminder Budget

AIppocampus should be useful because it is selective. A hook reminder must earn
its prompt space by changing likely next behavior, preventing a known drift, or
recovering context that is no longer visible. If the model can already see the
source, just processed the same correction, or the reminder would not change
the next action, the hook should stay silent.

Apply this anti-nag gate before injecting any foreground cue:

- `visibility`: suppress when the source turn or equivalent anchor is still in
  the visible context; re-enable only after compaction or horizon loss.
- `recency`: suppress when the same cue was shown in the current topic epoch
  and no contradictory action is pending.
- `actionability`: suppress cues that do not affect the next model or tool
  decision.
- `risk`: allow repetition only for high-cost mistakes, such as reverting to a
  rejected route, violating a narrowed scope, or losing a verified correction
  after compaction.
- `size`: prefer one compact anchor over many reminders; include source refs,
  not long restatements.

This keeps AIppocampus in the hippocampal/prospective-memory role: it supplies
timely cues to the agent's executive controller, but it does not become a
chatty controller itself.

### PreToolUse Boundary

`PreToolUse` is useful, but only in a narrow memory sense. Its best job is not
to decide whether a command is safe. Its job is to notice that the next action
is about to cross an active memory boundary and give the model a compact
reminder before it acts.

Good `PreToolUse` cases:

- an active correction says "do not touch generated files," and the pending
  patch targets one
- the user narrowed the scope, and the pending command searches or edits
  outside that scope
- a benchmark/debug command should produce evidence for an open correction
  window
- a subagent or tool call is about to proceed without the active definition of
  done

Bad `PreToolUse` cases:

- blocking dangerous shell commands as a memory feature
- approving privileged commands
- replacing Codex permission policy with project memories
- running semantic adjudication before the tool result exists

If `PreToolUse` is implemented, it should be conditional: install it only with
specific matchers and make it produce no output unless an active anchor is
actually relevant to the pending tool call.

### Installation Tiers

The hook set should grow in tiers.

| Tier | Events | Purpose |
|---|---|---|
| Existing foreground | `UserPromptSubmit` | Recall and correction activation. |
| Existing lifecycle | `SessionStart`, `Stop`, `PreCompact`, `PostCompact` | Cheap maintenance, compaction survival, detached scheduler enqueue. |
| Proposed evidence tier | `PostToolUse` for `Bash`, `apply_patch`, selected MCP tools | Source-backed tool evidence and correction outcome capture. |
| Proposed delegation tier | `SubagentStart`, `SubagentStop` | Propagate and reconcile anchors across delegated work. |
| Conditional preview tier | `PreToolUse` with narrow matchers | Context reminders before actions that intersect active anchors. |
| Out-of-scope by default | `PermissionRequest` | Leave allow/deny policy to Codex and host frameworks. |

## Event Records

The deterministic layer should record compact append-only events, not final
truth.

The first runtime prototype lives in
`skills/aippocampus/scripts/aippocampus_runtime/reflection/reconsolidation.py`. It can build and
append source-backed `correction_activation_event` and
`correction_outcome_event` JSONL rows, sanitize correction surfaces, changed-file
hints, and verification/tool evidence, and emit detached
`correction_adjudication_candidate` rows. These rows remain staging evidence and
candidate hypotheses; they are not formal memory.

`correction_activation_event` should include:

- `event_id`, `thread_id`, `workspace`, `topic_epoch`, and timestamp
- source refs for the user turn and any nearby assistant claim being corrected
- a compact correction surface, redacted for secrets
- detected target type: `claim`, `scope`, `route`, `default`, `test`,
  `doc_contract`, `tool_result`, or `handoff`
- provisional importance: `local`, `active_task`, `project`, or `unknown`

`correction_outcome_event` should include:

- linked `activation_event_id`
- model final claim or closeout source ref
- changed-file/test/doc/tool evidence when available
- sanitized `texture_evidence` for source-texture rows such as tool failure or
  rejected-route/process-route signals
- whether the agent appears to have adopted, ignored, or contradicted the
  correction
- any explicit user confirmation or follow-up correction

These rows are raw continuity evidence. They should not be inserted directly
into formal memory.

Texture evidence is an outcome reconstruction hint. It may add safe source/event
refs, signal kinds, and counts to an adjudication candidate, but it must not
store raw command output or upgrade an `uncertain` correction into `valid_*`
without explicit adjudication hints or reopened source-backed evidence.

## Semantic Adjudication

The dream worker performs the semantic step scripts cannot safely do alone.

It should classify each correction as:

| Status | Meaning | Default route |
|---|---|---|
| `valid_adopted` | The user correction was supported and the agent used it. | active task anchor; working memory if reusable |
| `valid_ignored` | The correction appears supported, but the agent did not use it. | active task anchor; foreground warning when relevant |
| `refuted` | Source, code, tests, or later user turns show the correction was wrong. | refuted correction note; do not promote |
| `superseded` | A later correction replaced this one. | link successor; suppress stale anchor |
| `local_only` | The correction was useful only for the current task or branch. | expires with task/handoff |
| `uncertain` | The evidence is insufficient or conflicting. | confirm when relevant |

The model may propose this adjudication, but source refs, tests, and tool output
remain the evidence layer. A dream finding is a hypothesis over source, not a
rewrite of clean source.

## Cache Path

Correction continuity needs hot, warm, and cold surfaces.

- Hot: current thread cache carries active correction anchors while the task is
  in progress.
- Warm: after compaction or topic continuation, the prompt hook can inject a
  compact "work continuity anchor" before ordinary ambient scent.
- Cold: detached dream work promotes durable, source-backed lessons into
  working memory or promotion candidates only after adjudication.

Current-thread echo suppression should be visibility-aware. If the corrected
source is still in the model's visible context, repeating it is noise. If
compaction or horizon loss removed it, the same source-backed correction may be
the highest-value anchor to re-inject.

## Foreground Contract

Foreground hooks should stay cheap and fail open.

They may:

- record a compact activation event
- read already-adjudicated active anchors
- inject at most a few source-backed continuity anchors
- enqueue detached semantic adjudication

They must not:

- run heavy dream adjudication synchronously
- treat user correction text as truth by itself
- expose raw prompts, local paths, secrets, or large source snippets
- promote formal memory without source-backed review

## First Slice

The first implemented slice is deliberately narrow:

1. Add append-only activation/outcome event builders for correction-like turns and
   post-work closeouts.
2. Add a small deterministic fixture set for accepted, ignored, refuted,
   superseded, and uncertain corrections.
3. Add a detached adjudication prototype that can read clean source and
   verification evidence, then emit sanitized candidates.
4. Add an active task anchor renderer that only surfaces adjudicated or
   high-confidence pending corrections after compaction/horizon loss.
5. Add Track D in the benchmark plan so regressions are visible before this is
   treated as a product-quality path.

The shipped helper covers append-only rows, source refs, privacy scanning,
deterministic six-status adjudication candidates, and active-task anchor
rendering after compaction or horizon loss. Foreground hooks are intentionally
unchanged in this slice, so this does not yet prove live Codex hook capture or
private real-history compaction survival.

Success is not "every correction becomes memory." Success is that the system has
a source-backed event and candidate layer that can preserve important task
corrections across compression while still being able to say "that correction
was later refuted."
