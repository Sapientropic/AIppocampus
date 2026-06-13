# Avatar Bounded Resonance Live-Model Pilot, 2026-06-13

This is the public-safe live-model follow-up for the deterministic bounded
resonance pilot. It uses only
`benchmark_corpus/avatar_bounded_resonance/fixture.json`; no private history,
raw local paths, credentials, or raw provider payloads are stored.

Command:

```powershell
$env:PYTHONPATH='skills/aippocampus/scripts'
python benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py --mode live-model --output docs/research/avatar-bounded-resonance-live-model-2026-06-13.json --json
```

Result:

- Status: `live_model_pilot_complete`
- Contract gate: passed
- Quality gate: not passed / not attempted
- Provider/model: DeepSeek `deepseek-v4-flash`
- Settings: temperature not sent (`temperature_requested=null`, `temperature_sent=false`), thinking `enabled`, reasoning effort `high`, no explicit max-token cap
- Calls: 60/60 case-arms
- Token usage: 41,308 prompt, 47,760 completion, 89,068 total
- Estimated cost: `$0.018717`, using DeepSeek's 2026-06-13 official V4-Flash prices for cache-hit input, cache-miss input, and output tokens
- Red lines: 0 off-topic bounded-resonance archetype expansion, 0 resonance-as-authority, 0 factual claims from resonance, 0 private/sensitive context use

Arm averages from scripted scoring:

| Arm | Avg Score | Manual Search | Over-Caution |
| --- | ---: | ---: | ---: |
| A explicit instruction | 2.5625 | 13 | 1 |
| B neutral posture | 2.833333 | 12 | 0 |
| C archetype alias only | 2.979167 | 9 | 0 |
| D bounded resonance | 2.375 | 14 | 1 |
| E random symbolic control | 1.875 | 14 | 3 |

Interpretation:

This is useful mixed/negative evidence, not a promotion result. The live model
did not show the deterministic proxy's bounded-resonance advantage; the bounded
arm scored below neutral posture and alias-only on this scripted rubric. The
good news is that the bounded arm did not trip the source-authority or private
context red lines. Temperature was not sent for this DeepSeek thinking-mode run;
do not interpret it as a temperature-0 normal-agent behavior run.

Do not claim default foreground avatar readiness, production behavior lift,
private-history avatar quality, or resonance as source authority from this run.
The next useful step is a blinded/human review or independent judge over the
sanitized outputs, plus a scoring rubric that does not let model self-labeled
metrics dominate the conclusion.
