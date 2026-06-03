# Rust Deterministic Core

Status: planning contract for GitHub issue #463. No Rust slice is shipped by
this document.

AIppocampus may move stable deterministic infrastructure surfaces into a small
Rust core over time. This is not a rewrite plan. Python remains the
cognitive, semantic, benchmark-generation, issue-automation, and experimental
runtime layer until those contracts settle.

The first Rust boundary must be contract replay, not implementation ambition:
a Rust slice earns authority only by preserving an already frozen Python-owned
public contract.

## Authority Boundary

Rust may own deterministic substrate work when the contract is stable enough:

- source-ref resolution and source-pointer validation;
- registry manifest reading and query planning;
- file locks, atomic publish, and cache eviction manifests;
- sync/encrypted-sync manifest validation;
- segment fanout planning and low-latency cache routing after hook contracts
  settle.

Rust must not become the truth owner. Source truth remains exact raw or clean
source, source refs, registry manifests, and documented source-reopen paths.
Generated summaries, concept graphs, dream outputs, activation hints, and
semantic sidecars remain navigation or staging layers unless their owning flow
ties them back to source.

Do not port unsettled semantics just to make them feel more final. Semantic
recall gates, dream workers, prompt construction, benchmark fixture generation,
research prototypes, and GitHub/docs automation stay in Python unless a later
design proves a narrower stable contract.

## Contract-Replay Gate

Before the first Rust slice lands, freeze a contract corpus for that slice
under `tests/fixtures/` or an equivalent public-safe fixture owner. The corpus
must be runnable by the Python implementation and the Rust prototype.

Each Rust slice must prove:

- Python and Rust consume the same input fixtures.
- Public JSON output is byte-level deterministic where practical.
- Any allowed differences are explicit and narrow, such as timestamps, elapsed
  time, platform path spelling, or intentionally redacted private path text.
- Public CLI or MCP JSON shape changes update public API docs and
  compatibility tests in the same slice.
- Source-backed truth boundaries are unchanged: caches can disappear, but
  source refs, source reopen, and canonical manifests keep their meaning.
- Python fallback remains available until Rust reaches fixture parity and the
  source-truth boundary tests pass.

Prefer a CLI JSON seam first: read JSON from stdin or a file, write JSON to
stdout, and keep the payload schema stable. Avoid PyO3, maturin, or daemon
embedding until the boundary has proven useful through replay fixtures.

## First Candidate Slice

The first apply-capable candidate is the storage-governance bridge from #460.
It is deterministic, filesystem-heavy, safety-critical, and already has a
Python contract for rebuildable cache eviction.

The Rust/Python parity fixture for that slice should cover the full operator
contract:

1. Build a small registry/source/index surface with at least one rebuildable
   cache.
2. Run dry-run and compare the expected eviction-plan JSON.
3. Apply eviction for the rebuildable class only.
4. Verify health reports an intentional degraded/rebuildable state, not
   corruption.
5. Rebuild through the manifest command or documented rebuild path.
6. Verify recall/search/source-reopen behavior is restored.
7. Compare public JSON shape against the frozen fixture, with only the
   documented volatile fields ignored.

The current Python implementation already tests the core product semantics for
this flow in `tests/aippocampus/test_storage_governance.py`: evict a
rebuildable cache, report intentional degradation, rebuild, and restore search.
That is a foundation for a future Rust replay slice, not evidence that the Rust
slice exists.

## Candidate Order

After storage governance, prefer candidates whose contracts are already
source-backed and deterministic:

1. Source-ref resolver and source-pointer validation.
2. Registry manifest reader and segment query planner.
3. Sync/encrypted-sync manifest validation and conflict/revocation checks.
4. Low-latency cache/router probes only after hook/card contracts settle.

Do not introduce a local daemon before CLI JSON contracts and golden fixtures
have proved useful. A daemon boundary should be an operational packaging
decision over stable contracts, not the place where semantics are invented.

## Closeout Rule For #463

#463 should not be closed merely because this planning document exists. Closure
requires a first Rust prototype slice with fixture parity, Python fallback, and
source-truth boundary tests. Until then, this document is the architecture
contract that prevents both premature rewrites and indefinite avoidance of a
deterministic core.
