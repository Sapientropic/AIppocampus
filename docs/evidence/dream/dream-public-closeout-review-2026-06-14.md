# Dream Public Closeout Review - 2026-06-14

This evidence slice extends the public Dream-vs-baseline shadow report with a
sanitized candidate-quality review table. It is the public-safe closeout path
for #1364 and #1365, not a live/private Dream-quality claim.

## Commands

```powershell
@'
import json
from pathlib import Path
from aippocampus_runtime.dream.public_shadow_report import (
    build_public_dream_vs_baseline_shadow_report,
)
out = Path("docs/evidence/dream/dream-public-closeout-review-2026-06-14.json")
out.write_text(
    json.dumps(
        build_public_dream_vs_baseline_shadow_report(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
'@ | python -
python -m pytest tests\aippocampus\test_dream_live_shadow_ab.py -q
```

## Results

- Status: `ok=true`
- Claim level: `public_synthetic_dream_vs_baseline_shadow`
- Public shadow cases: 4
- Dream wins: 2
- Dream no-help quiet cases: 1
- Visible Dream regressions: 0
- Suppressed regression-risk controls: 1
- Dream route-lift count: 2
- Useful action-delta count: 2
- Visible wrong-hint count/rate: 0 / 0.0
- Total verification-cost delta: -3
- Candidate-review rows: 6
- Useful candidates: 2
- Quiet/no-help candidates: 1
- Rejected or blocked candidates: 3
- False-positive categories: `stale_route`, `noisy_generic_vocab`,
  `privacy_or_safety_boundary`
- Foreground leak count: 0
- Source-reopenable candidate rate: 0.666667

## Decision

#1364 is satisfied by a public-safe equivalent cohort: the report defines the
cohort and baseline arms before scoring, compares no-Dream baseline versus
bounded Dream hint behavior, records wins/no-help/regression-risk controls, and
marks the claim level as public-safe shadow rather than live default.

#1365 is satisfied by the sanitized candidate-quality review table: it includes
useful, quiet/no-help, stale, noisy, and privacy/safety-blocked Dream candidate
classes while keeping raw private text and raw source refs out of public
artifacts.

#163 can close only as a bounded public-safe owner closeout. It still cannot
claim live delivered Dream quality, broad private-history reviewed quality,
general Dream quality, active-imagination usefulness, or source truth from
Dream-only material.

## Can Claim

- Public Dream shadow cases include route-lift, useful action-delta, no-help,
  suppressed regression-risk, wrong-hint, and verification-cost axes.
- A sanitized candidate-quality table records useful and rejected/blocked Dream
  nominations with false-positive categories.
- Dream candidates remain navigation/candidate material until source support and
  source reopen justify foreground use.

## Cannot Claim

- Live/default Dream delivery quality.
- Broad private-history Dream quality.
- Causal real-user lift.
- General Dream behavior quality.
- Source truth from Dream summaries or Dream-only candidates.
