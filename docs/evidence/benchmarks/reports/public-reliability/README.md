# Public Reliability Reports

Role: dated public reliability report router.
Status: report layer; current claim posture lives in
[`../../../../current-claims.md`](../../../../current-claims.md).

## Report Router Task Card

current_claim_owner: `docs/evidence/current-claims.md#current-claim-snapshot`.

latest_promoted_report: `public-reliability-gauntlet-2026-06-10.json`.

safe_next_action: open the JSON artifact, then use
`python tools\aippocampus\docs\check_docs_health.py --json` before promoting any
gauntlet axis into a current claim row.

historical_boundary: the gauntlet is a public-safe axis report with boundaries;
it is not a single reliability score, a live-agent quality claim, or a current
readiness upgrade by itself.

## Reports

| Report | Boundary |
| --- | --- |
| [`public-reliability-gauntlet-2026-06-10.json`](public-reliability-gauntlet-2026-06-10.json) | Public-safe runtime, mis-recall, and pollution-hygiene axis report; use Current Claims before citing it as present-tense evidence. |
