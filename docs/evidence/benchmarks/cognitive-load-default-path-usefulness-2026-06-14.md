# Cognitive-Load Default-Path Usefulness Replay - 2026-06-14

This evidence slice validates #1375 with a public-safe default-path replay. The
result is intentionally diagnostic: the sidecar shows one useful hint, but also
one safe-yet-draggy regression, so #575 should be narrowed to diagnostic-only
behavior instead of default foreground weighting.

## Commands

```powershell
@'
import json
from pathlib import Path
from aippocampus_runtime.recall.cognitive_load_sidecar import (
    build_public_default_path_usefulness_report,
)
out = Path(
    "docs/evidence/benchmarks/cognitive-load-default-path-usefulness-2026-06-14.json"
)
out.write_text(
    json.dumps(
        build_public_default_path_usefulness_report(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
'@ | python -
python -m pytest tests\aippocampus\test_cognitive_load_sidecar.py -q
```

## Results

- Status: `validated_diagnostic_result`
- Recommended maturity: `dogfood_diagnostic_only`
- Public replay cases: 4
- Useful hint count: 1
- Wrong-route drag reduction count: 1
- Blind-deepen reduction count: 1
- No-hint/no-op pass count: 2
- Default-path regression count: 1
- Default-path usefulness rate: 0.25
- No-op behavior pass rate: 1.0
- Feedback false-positive rate: 0.5
- Feedback caution-hint useful rate: 0.5

## Decision

#1375 is satisfied because the replay reports default-path usefulness and no-op
behavior, then states the maturity outcome explicitly. The outcome is not strong
enough for default adoption: one generic caution route would still add memory
drag.

#575 should close as narrowed to diagnostic-only behavior. The sidecar remains
useful as a private-safe diagnostic and bounded ranking input for reviewed
cases, but it should not be claimed as default host-timing or foreground
weighting quality until a future issue produces stronger live/default evidence.

## Can Claim

- Public-safe replay shows one cognitive-load hint can reduce wrong-route drag
  and blind deepen.
- No-hint cases can stay quiet or refresh sources without emitting affect or
  personality claims.
- The current evidence recommends diagnostic-only maturity, not default
  foreground weighting.

## Cannot Claim

- Live hook capture quality.
- Default foreground weighting readiness while regressions exist.
- Broad private-history generality.
- Emotion, stress, identity, intent, or personality truth from load signals.
