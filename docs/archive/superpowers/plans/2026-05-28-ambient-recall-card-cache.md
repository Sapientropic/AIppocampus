# Ambient Recall Card Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Ambient Associative Recall slice: compact private recall cards plus a thread ambient cache, while leaving a clean warm-path boundary for later 10-scout work.

**Architecture:** Reuse the existing prompt recall decision pipeline as the signal source. Add focused card and cache modules, then expose a compact `ambient_recall` block from hook decisions without making foreground hooks wait for new DeepSeek work.

**Tech Stack:** Python stdlib, existing AIppocampus registry helpers, `unittest`.

---

### Task 1: Ambient Recall Card Schema

**Files:**
- Create: `skills/aippocampus/scripts/ambient_recall_cards.py`
- Test: `tests/aippocampus/test_ambient_recall_cards.py`

- [ ] **Step 1: Write failing tests**

```python
def test_cards_distinguish_scent_candidate_and_evidence():
    result = {
        "decision": "evidence",
        "confidence": "high",
        "candidates": [{"thread_key": "session:a", "title": "Old thread", "matched_terms": ["continuity"]}],
        "evidence": [{"thread_key": "session:a", "title": "Old thread", "line": 12, "snippet": "continuity survives change"}],
        "working_memory": [],
        "cognitive_map": [],
    }
    payload = cards.ambient_recall_from_decision(result)
    assert payload["mode"] == "source_backed_recall_card"
    assert payload["cards"][0]["support_level"] == "evidence"
    assert payload["cards"][0]["source_refs"][0]["line"] == 12
```

- [ ] **Step 2: Run test to verify RED**

Run: `python -m unittest tests.aippocampus.test_ambient_recall_cards`
Expected: FAIL because `ambient_recall_cards` does not exist.

- [ ] **Step 3: Implement minimal card builder**

Create card validation, visibility selection, source-ref normalization, candidate conversion, and a stable output shape:

```python
{
    "mode": "active_gentle_nudge",
    "confidence": "medium",
    "cards": [...],
    "avoid": [...],
    "latency_ms": ...,
    "cache_status": {"status": "not_used"},
    "late_update_policy": "warm_scouts_deferred",
}
```

- [ ] **Step 4: Run test to verify GREEN**

Run: `python -m unittest tests.aippocampus.test_ambient_recall_cards`
Expected: PASS.

### Task 2: Thread Ambient Cache

**Files:**
- Create: `skills/aippocampus/scripts/ambient_thread_cache.py`
- Test: `tests/aippocampus/test_ambient_thread_cache.py`

- [ ] **Step 1: Write failing tests**

```python
def test_thread_cache_reuses_cards_without_raw_prompt_text():
    cache_path = root / "ambient-thread-cache.json"
    card = {"card_id": "arc_1", "theme": "continuity", "source_refs": [{"thread_key": "session:a"}]}
    payload = cache.write_thread_cache(cache_path, thread_id="thread-a", workspace="workspace", topic_epoch="epoch-1", cards=[card])
    assert payload["status"] == "written"
    loaded = cache.read_thread_cache(cache_path, thread_id="thread-a", workspace="workspace", topic_epoch="epoch-1")
    assert loaded["cards"][0]["theme"] == "continuity"
    assert "prompt" not in json.dumps(loaded).casefold()
```

- [ ] **Step 2: Run test to verify RED**

Run: `python -m unittest tests.aippocampus.test_ambient_thread_cache`
Expected: FAIL because `ambient_thread_cache` does not exist.

- [ ] **Step 3: Implement minimal cache**

Store a bounded JSON object keyed by hashed `thread_id + workspace + topic_epoch`. Include expiry, small card list, negative contexts, and topic drift helper based on source-ref/card overlap.

- [ ] **Step 4: Run test to verify GREEN**

Run: `python -m unittest tests.aippocampus.test_ambient_thread_cache`
Expected: PASS.

### Task 3: Hook Decision Integration

**Files:**
- Modify: `skills/aippocampus/scripts/prompt_recall_decision.py`
- Modify: `skills/aippocampus/scripts/prompt_context_render.py`
- Modify: `skills/aippocampus/scripts/aippocampus_prompt_hook.py`
- Test: `tests/aippocampus/test_aippocampus_prompt_hook.py`
- Test: `tests/aippocampus/test_prompt_recall_decision_boundaries.py`

- [ ] **Step 1: Write failing integration tests**

Add tests asserting `assess_prompt()` returns `ambient_recall`, and hook context can render the private block without source ids for ordinary scent.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `python -m unittest tests.aippocampus.test_aippocampus_prompt_hook tests.aippocampus.test_prompt_recall_decision_boundaries`
Expected: FAIL because `ambient_recall` is missing.

- [ ] **Step 3: Integrate card builder**

Call `ambient_recall_from_decision()` after decision fields are assembled. Keep hook foreground behavior unchanged: no wait-all scouts, no raw prompt text logging.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `python -m unittest tests.aippocampus.test_aippocampus_prompt_hook tests.aippocampus.test_prompt_recall_decision_boundaries`
Expected: PASS.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/research/ambient-associative-recall.md`
- Modify if needed: `skills/aippocampus/references/ambient-hooks.md`

- [ ] **Step 1: Update memo status**

Mark Card/cache first as the active first slice and keep 10 scouts as the next warm-path evolution.

- [ ] **Step 2: Run verification**

Run:

```powershell
python tools\aippocampus\docs\check_docs_health.py --json
python -m unittest discover -s tests -t .
```

Expected: docs health `ok=true`; unit tests pass.
