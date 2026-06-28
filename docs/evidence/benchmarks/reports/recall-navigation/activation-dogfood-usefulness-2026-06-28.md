# Activation Dogfood Usefulness - 2026-06-28

This report closes the bounded #2857 probe for activation usefulness. It asks a
narrow question: when replay signal is available, does activation reduce manual
search, wrong-route drag, or noisy surfacing on a small dogfood/replay slice
without claiming live default quality?

The answer is yes for this bounded replay. It is not a Dream/default-foreground
promotion.

## Command

```powershell
python benchmarks\aippocampus\benchmark_activation_dogfood_usefulness.py --json
```

Focused regression coverage:

```powershell
python -m unittest tests.aippocampus.test_benchmark_activation_dogfood_usefulness -v
```

## Result

| Metric | Cold no activation | Warm replay signal | Delta |
| --- | ---: | ---: | ---: |
| Generated candidates | 2 | 5 | +3 |
| Foreground exposed candidates | 2 | 2 | 0 |
| Verifier-seen candidates | 2 | 5 | +3 |
| Useful source-open hits | 1 | 2 | +1 |
| Source-open follow-through | 1 | 2 | +1 |
| Manual-search fallback | 2 | 1 | -1 |
| Wrong-route drag | 1 | 0 | -1 |
| Noisy surfacing | 1 | 0 | -1 |

Warm replay roles: `process_supervision=1`, `hard_negative=1`,
`replay_sample=1`, and `positive_demo=1`.

One case consumes a replayable live-agent trajectory packet with complete
ordered source reopen. The other cases cover route-feedback replay, parked
candidate lifecycle, and source-openable route preservation.

## Decision

`activation_probe_useful_on_bounded_replay=true`.

The probe supports keeping activation signals in the bounded replay/dogfood
pipeline because they reduce manual search and route drag while preserving
source-open follow-through. It does not promote live default foreground
activation, Dream default delivery, source truth from activation, or private
history quality.

## Boundary

This is a deterministic dogfood/replay usefulness probe. It does not claim
causal real-user lift, live default foreground quality, private-history quality,
default Dream delivery quality, or factual support from activation signals.
