# Dream Atlas Live Pilot, 2026-06-12

Status: public-safe live provider pilot for #1286.

Source report:
[`dream-atlas-live-pilot-2026-06-12.json`](dream-atlas-live-pilot-2026-06-12.json).

Command:

```powershell
python -m aippocampus_runtime.dream.atlas_pack --fixture --live-pilot --json --max-samples 2 --max-tokens 1800 --dream-model-thinking disabled --dream-model-reasoning-effort auto
```

## Result

The live DeepSeek V4 Flash route completed over the public-safe atlas fixture.
The fixture used 4 selected source-card packs, 8 source refs, and no raw source
text. The bounded single-pack baseline produced 0 candidates, the deterministic
atlas produced 2 bridge/cycle candidates, and the live atlas worker produced 2
model candidates.

Background adjudication outcome:

- accepted: 1
- parked: 1
- rejected: 0
- live source-ref validity rate: 1.0

Provider usage and cache telemetry came from response fields:

- prompt tokens: 3395
- completion tokens: 1303
- total tokens: 4698
- `prompt_cache_hit_tokens`: 3328
- `prompt_cache_miss_tokens`: 67
- cache hit rate: 0.9803
- latency: 13417.244 ms
- cost mode: `provider_pricing_not_configured`

No provider price was embedded in the report. Cost remains unavailable unless a
future run supplies explicit token prices or an audited pricing ledger.

## Boundary

This is a small public fixture pilot, not broad Dream quality evidence. It shows
that the live atlas command can call the provider, preserve real usage/cache
fields, feed candidates through the existing background adjudicator, and compare
bounded-pack, deterministic-atlas, and live-atlas surfaces.

It does not support private-history atlas quality, foreground Dream delivery,
source truth without reopen, broad long-context candidate quality, or broad live
DeepSeek quality.

The checked-in JSON report omits API key values and API key environment names.
It contains no private source text, local paths, raw private source refs, or
foreground hook model calls.
