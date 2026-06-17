# Host-Agnostic Continuity Conformance Contract

Role: current contract.
Status: current host-readiness contract.

This contract gives every host the same minimum continuity checklist. It does
not claim all hosts are equally supported. It answers a narrower question: what
can this host actually do for source-backed continuity right now?

## Labels

Use the strongest label whose requirements are all true.

| Label | Meaning | Minimum requirements |
| --- | --- | --- |
| `unavailable` | AIppocampus is not discoverable or callable from the host. | No CLI/MCP/plugin route is available. |
| `cli_only` | A local agent or user can run AIppocampus manually. | CLI or module entrypoint works; host tools may be absent or stale. |
| `recall_only` | The host can call a foreground recall path. | AIppocampus is discoverable and `agent_recall` or equivalent is callable. |
| `recall_deepen` | The host can recall and reopen/deepen selected routes. | Recall plus deepen/source-reopen callability, with redacted foreground output. |
| `ambient_recall_deepen` | The host can provide ambient hints plus recall/deepen. | Recall/deepen plus explicit hook or hint lane installed. |
| `full_continuity_path` | The host supports the first-magic-moment path. | Ambient lane, recall, deepen, current-thread visibility, and fresh live schema. |

## Required Dimensions

Every host status or support row should answer these dimensions:

| Dimension | Required answer |
| --- | --- |
| Discoverability | Can the agent find that AIppocampus exists without broad search? |
| Recall callability | Can it call recall from the foreground thread? |
| Deepen/source reopen | Can it follow a selected route before making source-backed claims? |
| Ambient hints | Can it receive hook/cache/sidebar hints without manual recall? |
| Current-thread registration | Can the current conversation be registered or imported with consent? |
| Live-schema freshness | Can stale or mixed MCP/plugin schemas be detected separately from installed files? |
| Foreground privacy | Are local paths, handles, raw text, and secrets redacted by default? |
| CLI/manual fallback | Is there a safe manual command when host tools are missing? |
| First magic moment | Can a fresh agent get one useful recall, then deepen it? |

## Runtime Status Surface

`aippocampus update status --json` exposes the current label under
`summary.host_conformance_label` and the full readout under
`surfaces.host_conformance`.

`aippocampus update status --agent-json` remains a compatibility alias for the
same compact projection. Treat `tools_visible=true` and
`key_tools_callable=false` as a stale or mixed live-host state: reload the
host/plugin/MCP process before asking the user to debug recall quality.

## Contract Boundaries

- A label is a host affordance claim, not a memory-quality score.
- A listed MCP tool is not enough; key recall tools must also be callable when
  the host probe checks them.
- Source-backed factual claims still require source reopen within scope.
- Host-specific docs should point here for the shared label contract, then state
  their own setup and evidence.
- CLI-only is a valid fallback, not a failed install, when the host cannot expose
  MCP/plugin tools.

## Verification

Focused local checks:

```powershell
python -m unittest tests.aippocampus.test_update_sync -v
python tools\aippocampus\docs\check_docs_health.py --json
```

Broader host claims still need the host-specific smoke named in the ecosystem
matrix or benchmark evidence map.
