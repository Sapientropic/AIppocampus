# Fresh-Thread Real-History Smoke Evidence

Evidence date: 2026-06-02.

This report records a sanitized real-history boundary smoke for #302. It is not
a fresh-thread recall quality benchmark. It checks the two integration failures
that originally motivated #302 without publishing private prompts, source text,
thread ids, source refs, local paths, or registry exports.

## Source Map

- Issue: #302
- Runner:
  [`tools/aippocampus/smoke/smoke_fresh_thread_real_history.py`](../../../tools/aippocampus/smoke/smoke_fresh_thread_real_history.py)
- Fixture test:
  [`test_fresh_thread_real_history_smoke.py`](../../../tests/aippocampus/test_fresh_thread_real_history_smoke.py)
- Runtime boundaries:
  [`active_recall_lock.py`](../../../skills/aippocampus/scripts/aippocampus_runtime/recall/active_recall_lock.py),
  [`fresh_thread_action.py`](../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_action.py), and
  [`aippocampus_prompt_hook.py`](../../../skills/aippocampus/scripts/aippocampus_prompt_hook.py)

## Smoke Contract

The runner reads a registry and emits only aggregate/hash/count/status fields.
It checks:

- a ready lock with reopenable refs can reopen clean source;
- a thread-only route handle is not advertised as a usable ready lock;
- a current-repo factual prompt does not surface old-project evidence.

If the local registry does not contain enough clean-source rows to run the
reopenability checks, the smoke reports `insufficient_real_history` instead of
claiming success.

## Local Result

Command:

```powershell
python tools\aippocampus\smoke\smoke_fresh_thread_real_history.py --cwd . --json --strict
```

Sanitized result summary:

- `status=passed`
- `thread_count=1009`
- `clean_source_message_rows_seen=117`
- `selected_reopenable_thread_count=1`
- ready lock reopenability: passed, `match_count=1`
- thread-only lock boundary: passed, `lock_state=pending`
- current-repo fact negative control: passed, `decision=skip`,
  `evidence_count=0`, `current_checkout_required=true`

The output was aggregate/hash-only. No raw prompts, source snippets, thread ids,
source refs, registry paths, or local workspace paths were printed.

## Can Claim

- The fixed #302 runtime boundaries have a sanitized real-history smoke path.
- On the 2026-06-02 local registry slice, a ready lock with reopenable refs
  reopened source, thread-only refs did not become a usable ready lock, and the
  current-repo fact negative control did not inject old-project evidence.

## Cannot Claim

- No broad private real-history fresh-thread recall quality claim.
- No live semantic-model quality claim.
- No proof that all fresh-thread prompts or all private memory families are
  covered in production.
- The public fresh-thread demo remains synthetic; it should not be cited as
  real-history benchmark evidence.
