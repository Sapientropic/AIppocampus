# Warm Ambient Recall Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calibrate warm ambient recall with source validation, current-thread echo suppression, LLM-directed topic epoch rotation, and 50 structured scout lanes.

**Architecture:** Keep `warm_ambient_recall.py` as a standalone warm path. Expand the 10 scout families across 5 lane variants, then let deterministic parent code validate source refs, penalize current-thread echoes, merge topic-epoch votes, and write through the existing ambient thread cache/residue writer.

**Tech Stack:** Python stdlib threads/queues, existing AIppocampus clean-source registry, `ambient_thread_cache.py`, `search_clean_source.py`, `unittest`.

---

### Task 1: Add Failing Calibration Tests

**Files:**
- Modify: `tests/aippocampus/test_warm_ambient_recall.py`

- [x] Add tests that prove the default lane set is `10 families × 5 variants = 50`.
- [x] Add a clean-source fixture test where unsupported source refs downgrade evidence to candidate.
- [x] Add a clean-source fixture test where supported source refs remain evidence.
- [x] Add a current-thread-only source-ref test that suppresses echo cards by default.
- [x] Add a topic-epoch test where `topic_epoch_action=rotate` uses the scout-provided label, not deterministic prompt terms.
- [x] Add a prompt-trace sanitization test so local paths never enter scout payloads.
- [x] Run `python -m unittest tests.aippocampus.test_warm_ambient_recall` and confirm the new tests fail against current behavior.

### Task 2: Implement 50 Structured Lanes

**Files:**
- Modify: `skills/aippocampus/scripts/warm_ambient_recall.py`

- [x] Split the current scout list into `SCOUT_FAMILIES` and `SCOUT_VARIANTS`.
- [x] Make `DEFAULT_SCOUTS` expand to all family/variant lane ids.
- [x] Preserve family-only shorthand such as `("evidence_judge",)` by expanding it to the direct lane.
- [x] Include family and variant instructions in `scout_prompt`.
- [x] Keep quorum-first behavior: launch lanes concurrently, but return once the quorum is met unless `--wait-all` is requested.

### Task 3: Implement Source Validation And Echo Penalty

**Files:**
- Modify: `skills/aippocampus/scripts/warm_ambient_recall.py`

- [x] Load clean-source messages from registry entries when a registry path/object is available.
- [x] Validate evidence cards against `message_id` or `line/source_line`.
- [x] Require the clean-source text to support the card through `key_line` or matched terms before preserving `support_level=evidence`.
- [x] Downgrade unsupported evidence to `candidate` and attach compact validation metadata.
- [x] Suppress cards whose source refs all point to the current thread unless the caller explicitly allows current-thread echo.

### Task 4: Implement LLM Topic Epoch Rotation

**Files:**
- Modify: `skills/aippocampus/scripts/warm_ambient_recall.py`

- [x] Parse `topic_epoch_action`, `topic_epoch_label`, and `topic_epoch_reason` from scout output.
- [x] Merge epoch votes deterministically: `suppress` blocks writes, `rotate` hashes the scout label, and `reuse` preserves the caller-provided epoch when available.
- [x] Keep the fallback path only for missing scout epoch output; do not hard-code topic drift rules from prompt text.
- [x] Return `topic_epoch_decision` in the JSON result.

### Task 5: Document And Verify

**Files:**
- Modify: `docs/research/ambient-associative-recall.md`
- Modify: `skills/aippocampus/references/ambient-hooks.md`

- [x] Update the research note to state that 50 lanes are structured as 10 scout families across 5 variants.
- [x] Document source-ref validation, current-thread echo suppression, and LLM-directed topic epoch rotation.
- [x] Run focused tests, docs health, full unittest, and a touched-file static scan for local paths/secrets.
