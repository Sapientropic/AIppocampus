# Magic Moments, Claim-Bounded

AIppocampus should not make a new reader dig through benchmark caveats before
seeing why the project exists. This page collects a few real second-user
moments where source-backed continuity felt different from ordinary chat
memory, while keeping the claim boundary visible.

These examples come from external live-use notes in
[Discussion #98](https://github.com/Sapientropic/AIppocampus/discussions/98).
They are product-shaped evidence, not benchmark scores, release claims, or
proof that the base model remembered anything by itself.

## How To Read These

- A memory scent or hook result is navigation, not evidence.
- Specific claims should reopen clean source, registry state, automation state,
  or another durable source before they are trusted.
- Local paths, session ids, credentials, raw private snippets, and unnecessary
  personal detail are intentionally omitted.
- The examples show useful continuity moments; they do not prove universal
  recall quality, no-hook superiority, hosted-service readiness, or private
  real-history benchmark coverage.

## Examples

### Fresh Projectless Thread

Source:
[fresh-thread live-use note](https://github.com/Sapientropic/AIppocampus/discussions/98#discussioncomment-17141243).

- **User typed:** "do u know what i'm working on recently?"
- **AIppocampus helped recover:** several recent work streams, including a
  phonics app, a signal-scanner product, and AIppocampus/OpenClaw-adjacent
  automation work, with uncertainty marked instead of flattened away.
- **What made it source-backed:** the note says the workspace had no relevant
  project files and no project-local instructions containing those facts. A
  light ambient scent oriented the agent, then the agent reopened local
  memory/registry evidence and direct clean source before making specific
  claims.
- **What not to claim:** this was not a no-hook baseline and does not prove
  universal fresh-thread recall quality.
- **Why it matters:** a new, projectless thread did not start from bare ground,
  but it still treated scent as a cue rather than as proof.

### Correction Across Languages

Source:
[fresh-thread live-use note](https://github.com/Sapientropic/AIppocampus/discussions/98#discussioncomment-17141243).

- **User typed:** a Russian question about which words had been studied, then
  corrected the route: "нет я не про сайт. про школу".
- **AIppocampus helped recover:** the first answer routed to the phonics app
  context; after the correction, the assistant moved to the school/Oxford
  Phonics context and gave a narrower, uncertainty-marked answer.
- **What made it source-backed:** the useful behavior was not that the first
  route was perfect. It was the progressive route change after a small user
  correction, while preserving the difference between app/project context and
  school context.
- **What not to claim:** this does not prove the first route is always right or
  that multilingual recall is solved.
- **Why it matters:** long-running continuity needs recoverable correction, not
  only confident first guesses.

### Ambiguous LinkedIn Cue

Source:
[fresh-thread live-use note](https://github.com/Sapientropic/AIppocampus/discussions/98#discussioncomment-17141243).

- **User typed:** "что случилось с моим линкедин?"
- **AIppocampus helped recover:** a local automation/delivery failure around
  LinkedIn draft delivery, while refusing to claim live LinkedIn account state.
- **What made it source-backed:** the assistant separated external account
  state from local automation evidence, inspected local automation state, and
  framed the live-account part as unverified.
- **What not to claim:** this does not prove browser/live-account access or
  that anything was verified on LinkedIn itself.
- **Why it matters:** source-backed memory should prevent overclaiming as much
  as it helps recall.

### Long-Thread Fuzzy Self-Reference

Source:
[long-thread live-use note](https://github.com/Sapientropic/AIppocampus/discussions/98#discussioncomment-17141509).

- **User typed:** a fuzzy question asking what an earlier "xxx" completion
  question had referred to.
- **AIppocampus helped recover:** the target was Phonics Lab Books 3/4/5, with
  the important nuance that image assets were effectively complete while
  audio/content/product-course closure was not fully complete.
- **What made it source-backed:** the thread was roughly multi-day and 140+
  visible user-message events long. The hook gave general orientation, but it
  did not directly surface the decisive anchors. The agent still had to inspect
  rollout metadata, use clean/turn tooling, and search clean source/raw text.
- **What not to claim:** this does not prove that the foreground hook alone is
  strong enough, nor does it replace private real-history benchmark tracks.
- **Why it matters:** this is the lived product promise: fuzzy old references
  can be recovered when the agent is allowed to reopen source instead of
  pretending to remember.

## Try A Public-Safe Path

The current honest install probe uses the PyPI package:

```sh
uvx aippocampus --help
uvx aippocampus onboard --provider codex --status
```

After explicit consent to register local history, the first useful proof is a
source-backed search receipt:

```sh
uvx aippocampus onboard --provider codex --all
uvx aippocampus search "a distinctive old phrase"
```

If the user does not remember exact wording, use a project cue or time cue as
candidate navigation only. Do not present a vague-cue route as evidence until
AIppocampus returns a source-backed snippet.

PyPI and MCP Registry publication evidence is captured in
[#291](https://github.com/Sapientropic/AIppocampus/issues/291). Broader
all-client readiness claims still require the separate external install/UI
readiness track in
[#307](https://github.com/Sapientropic/AIppocampus/issues/307).

For no-private-data demos, start with
[`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md). For the
benchmark and smoke ledger behind broader claims, use
[`benchmark-evidence-map.md`](benchmark-evidence-map.md) and
[`readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md).

Related technical tracks: [#201](https://github.com/Sapientropic/AIppocampus/issues/201),
[#281](https://github.com/Sapientropic/AIppocampus/issues/281),
[#285](https://github.com/Sapientropic/AIppocampus/issues/285),
[#291](https://github.com/Sapientropic/AIppocampus/issues/291),
[#382](https://github.com/Sapientropic/AIppocampus/issues/382), and
[#397](https://github.com/Sapientropic/AIppocampus/issues/397).
