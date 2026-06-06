# Edge Capture And Consolidation Boundary

AIppocampus has two lanes that should not be collapsed into one foreground
workflow.

The edge capture lane is local, cheap, and offline-safe. It records stable
source ids, hashes, timestamps, device/head metadata, and minimal source refs
without requiring a live external model. A captured item can be useful even
when downstream sidecars are stale or absent.

The consolidation lane is asynchronous. It refreshes clean source, segment
indexes, semantic labels, cognitive maps, Dream or working-memory candidates,
route-readiness reports, and cross-device merge material through explicit
maintenance, daemon, workstation, or private-server routes. It writes through
the existing generated-artifact and sidecar owners; it does not replace clean
source as authority.

## State Flow

The public-safe no-write diagnostic in
`aippocampus_runtime.ops.capture_consolidation_boundary` projects four states:

| State | Meaning | Claim boundary |
| --- | --- | --- |
| `captured` | The local edge lane has a source id or event shell. | Source is not lost, but downstream recall surfaces may not be ready. |
| `pending_consolidation` | Clean source or source metadata exists, but sidecars are not ready. | Stale consolidation is a freshness gap, not capture failure. |
| `consolidated_sidecars_ready` | Rebuildable indexes or sidecars are available. | Generated sidecars remain cache/navigation layers. |
| `source_reopenable` | Stable source refs can reopen clean source. | This is the first state that can support source-backed claims after reopen. |

The fixture command is intentionally no-write:

```sh
python -m aippocampus_runtime.ops.capture_consolidation_boundary --fixture --json
```

## Ownership

- Foreground hooks may capture or read tiny ready surfaces, but must not wait
  for semantic, Dream, graph, or cross-device consolidation.
- Sync moves clean source, manifests, registry rows, and approved sidecars. It
  should not move local lock state as if it were source truth.
- External-model work is optional and belongs behind explicit redaction and
  configuration.
- A local-only user who never enables a daemon or provider still has a valid
  product mode when source capture and source reopen remain available.

## Cannot Claim

This boundary does not claim a hosted cloud service is required, that
foreground hooks may run heavy consolidation, that generated sidecars replace
clean source, or that capture status proves recall quality.
