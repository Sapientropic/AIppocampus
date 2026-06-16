# Conversational Media-Ingest Fixture Report

Status: public-safe deterministic contract smoke for GitHub #532 and the #528
multimodal source-backed recall track.

This is the conversational counterpart to ATM-Bench-style staged corpus QA. It
models media the user sends or selects inside a conversation, where the user's
wording around the upload is itself source evidence.

It is intentionally separate from the
[`multimodal-corpus-fixture-report.md`](multimodal-corpus-fixture-report.md)
corpus-style fixture.

## Fixture Shape

The fixture lives at
[`../../../../../benchmark_corpus/conversational_media_ingest/fixture.json`](../../../../../benchmark_corpus/conversational_media_ingest/fixture.json).

It contains public-safe synthetic conversation traces with:

- conversation-turn sources for the user's wording around an upload or later
  correction;
- media sources attached to specific user turns;
- reopenable media/document anchors;
- a task-scoped consent boundary:
  `task_scoped_user_provided_media_only`.

The fixture records both source types because a later answer may need the
conversation label and the media anchor. Text around an upload can resolve a
personal reference, but it cannot count as visual proof when the claim depends
on what is visible in the media.

## Control Arms

| Arm | What it tests |
| --- | --- |
| Text-only conversational hint | User wording is available, but a visual claim must abstain unless media is reopened. |
| Media-only corpus retrieval | Media can be reopened, but user-provided personal labels are unavailable. |
| Combined source-backed recall | Conversation wording and reopened media together support the answer. |
| Stale label correction | A later user correction supersedes an earlier media label. |

## Commands

```powershell
python benchmarks\aippocampus\benchmark_conversational_media_ingest_recall.py --json
python benchmarks\aippocampus\benchmark_conversational_media_ingest_recall.py --source-open-replay --json
```

Latest local deterministic run on 2026-06-03:

- `status=fixture_contract_scored`
- `ok=true`
- `personal_reference_resolution_rate=1.0`
- `visual_source_reopen_rate=1.0`
- `text_hint_leakage_rate=0.0`
- `stale_label_correction_success_rate=1.0`
- `unsupported_visual_claim_rate=0.0`
- `hidden_durable_write_count=0`

This is a small-N contract smoke over six synthetic QA/control rows. Treat the
Wilson intervals in the JSON report as uncertainty metadata, not
population-quality evidence.

The optional `--source-open-replay` mode adds a seven-case public-safe replay
cohort for same-task upload/selection flows. It keeps the original deterministic
fixture rows as `fixture_boolean_only_case_count`, separately reports
source-open replay cases, and holds provider-blocked cases open instead of
claiming live product lift.

## Claim Boundary

Can claim:

- the public-safe fixture encodes the #532 conversational media-ingest recall
  contract;
- reports distinguish text-hint support, media reopen support, combined
  source-backed recall, and stale-label correction;
- the fixture enforces task-scoped user-provided media consent and zero hidden
  durable writes.

Cannot claim:

- ATM-Bench Hard support or score;
- ATM-style staged corpus retrieval;
- product privacy behavior;
- background photo-library or filesystem scanning;
- cross-domain media reuse;
- face-recognition identity graph behavior;
- live vision-model answer quality;
- media-only personal identity resolution;
- text hints as visual proof;
- durable memory write-policy quality.

## Privacy Boundary

Default reports emit sanitized ids, hashes, anchors, control-arm labels, and
metrics only. They do not emit raw transcript text, raw media text, raw media
bytes, absolute local paths, provider prompts, or hidden durable-write payloads.
