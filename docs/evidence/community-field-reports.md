# Community Field Reports

This is the project-maintained boundary for public community evidence. It is a
submission and curation surface, not a shortcut for turning anecdotes into
official benchmark claims.

Use this page when someone wants to share a real AIppocampus run, demo,
benchmark attempt, screenshot, log excerpt, or reproduction note without
exposing private raw memory.

## Where To Submit

- Public site entrypoint: [`/evidence/`](https://www.aippocampus.com/evidence/).
- GitHub Discussions are enabled for the repository.
- The dedicated `Evidence & Field Reports` Discussion category still needs to
  be created by a maintainer. At implementation time on 2026-06-02, the
  repository had the default categories: Announcements, General, Ideas, Polls,
  Q&A, and Show and tell.
- Until the dedicated category exists, use
  [Show and tell](https://github.com/Sapientropic/AIppocampus/discussions/categories/show-and-tell)
  with the `[Field Report]` title prefix. The repository includes a structured
  Discussion form for that category.

## What Belongs Here

| Surface | Status | Claim boundary |
| --- | --- | --- |
| Official benchmark evidence | Project-maintained | Can support official claims only when linked from the benchmark map and dated verification ledgers. |
| Community field reports | Community-authored | Useful signals, reproduction notes, demos, and surprises; not official claims until reviewed and promoted. |
| Demo runs | Mixed | Good for product feel and workflow clarity; not broad evidence unless the fixture and controls are explicit. |
| Known gaps | Project-maintained or community-authored | Evidence that something did not work, was not reproducible, or still needs a controlled benchmark. |
| Not-yet-proven claims | Explicitly provisional | Ideas for future tests; do not cite as proof. |

## Report Template

```md
## What I tested

## Environment
- OS:
- AIppocampus version / commit:
- Host agent:
- Model:
- Dataset / thread type:

## Steps

## Result

## What surprised me

## Reproducibility
- Can others reproduce this? yes/no/partial
- Any private data removed? yes/no

## Claim boundary
This shows:
This does not show:
```

## Curation Rules

- Do not mirror every Discussion into docs. Promote only high-signal reports
  that are public-safe, reproducible enough to inspect, or important as a known
  gap.
- Keep raw conversations, local paths, private registry exports, tokens, and
  unredacted logs out of the repository.
- Link community reports from curated docs only with their status visible:
  `community report`, `demo run`, `known gap`, or `promoted evidence`.
- If a community report changes what the project can honestly claim, update
  the dated verification ledger or the current claim-boundary snapshot instead
  of adding a second status source here.

## Maintainer Setup

GitHub Discussion category forms only activate when the YAML filename matches
an existing category slug. See GitHub's
[discussion category form docs](https://docs.github.com/discussions/managing-discussions-for-your-community/syntax-for-discussion-category-forms).

1. Create a GitHub Discussions category named `Evidence & Field Reports`.
2. Use the slug `evidence-and-field-reports` if GitHub offers the default slug.
3. Copy the current `.github/DISCUSSION_TEMPLATE/show-and-tell.yml` form to
   `.github/DISCUSSION_TEMPLATE/evidence-and-field-reports.yml`.
4. Pin a starter post that links this page, the public `/evidence/` page, and
   the benchmark evidence map.
5. Keep the Show and tell route as a fallback until existing field reports have
   been moved or clearly labeled.

## Related Official Evidence Work

- [#425 Create Evidence & Field Reports surface for community test results](https://github.com/Sapientropic/AIppocampus/issues/425)
- [#216 Umbrella: harden benchmark methodology for public-quality memory claims](https://github.com/Sapientropic/AIppocampus/issues/216)
- [#252 Unify evidence snapshots and add supersession rules for benchmark claims](https://github.com/Sapientropic/AIppocampus/issues/252)
- [#301 Create benchmark design rationale hub and external-benchmark analysis folder](https://github.com/Sapientropic/AIppocampus/issues/301)
- [Benchmark And Evidence Map](benchmark-evidence-map.md)
