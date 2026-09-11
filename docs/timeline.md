# Timeline: attributing cost steps to deploys

`cost-diff timeline` pulls daily cost from Cost Explorer, finds the days a
service stepped to a new level, and names the deploy that landed just before
each step.

## The claim it makes

A step is a fact about the bill. The deploy next to it is **a coincidence in
time, and nothing more** — the tool has no idea what the deploy changed, and a
step can equally be a traffic spike, a retention policy, an expired credit, or a
Savings Plan that ran out. What the report gives you is a place to look first,
plus an honest account of how alone that deploy was in the window.

## Run it

```sh
export AWS_PROFILE=billing        # ce:GetCostAndUsage, nothing else

cost-diff timeline --deploys-git .
cost-diff timeline --deploys-file deploys.csv --days 90 --format json
cost-diff timeline --deploys-github acme/api --tag Environment --chart mermaid
```

`--days` (default 60) sets the range; `--end YYYY-MM-DD` pins the last day for a
reproducible run. Today is always excluded — it is a part day of cost and would
look like a step down.

## Grouping

Daily cost is grouped by `--group` (default `SERVICE`) and optionally by one
cost-allocation tag (`--tag Environment`). Cost Explorer allows two group-by
keys, which is exactly one dimension plus one tag; the group then reads
`Amazon EC2 / prod`. Steps are looked for in each group separately — a step in
one service is precisely what a total hides.

## Detection

| Flag | Default | What it does |
| --- | --- | --- |
| `--method` | `median-mad` | `median-mad` or `pelt` |
| `--window-days` | 7 | days either side of a candidate step |
| `--threshold-sigma` | 4 | how far past the window's noise a step must be |
| `--min-step` | 5 | ignore steps under $N/day |
| `--ramp-fraction` | 0.6 | share of the level change due inside the transition |
| `--transition-days` | 2 | days a step may take to complete |
| `--pelt-penalty` | 3 | PELT penalty, in σ²·ln n |

**`median-mad`** compares the median of the days before each day with the median
of the days after, and scores the difference against the window's own noise —
a median absolute deviation, scaled by 1.4826, so one spike cannot inflate it.
A flat series would score every cent as infinitely significant, so the noise
estimate is floored at 2% of the level.

**`pelt`** runs a minimal [PELT][pelt] search instead: the optimal segmentation
under an L2 segment cost with a `σ²·ln n` penalty, with the pruning step that
makes it PELT rather than plain optimal partitioning. It handles several steps
in one series better, and is harder to explain to the person paying the bill.

Both feed the same two filters, which is what keeps the output short:

- **the dollar floor** — under `--min-step` per day, nobody is going to act on it.
- **the ramp guard** — the change across the transition, measured against the
  change across a horizon several times longer. A step delivers all of its level
  change in a day or two; a line sloping through the horizon delivers only the
  days it is wide, whatever its slope. So a gradual ramp is never reported as a
  step, and neither is a one-day spike: both fail on the same ratio.

Levels either side are medians of three days rather than single readings, so one
odd day cannot make a ramp look like a step or the other way round.

Whichever method ran, the day reported is the first day cost actually moved: a
rolling median can flag a step a day early and PELT a day late, so the candidate
is walked back to the first day at least halfway to the new level.

## Attribution

A step first visible on day *D* is attributed to every deploy in the
`--deploy-window` (default 24h) before *D*, plus day *D* itself — a deploy at
lunchtime bills half a day, so it lands on the day it happened or the day after.
Confidence is how alone the deploy is in that window: one is `high`, two is
`medium`, three or more is `low`, none is unattributed. With more than one
candidate the report lists them all; nothing in a daily series can separate them.

The lag is measured from the deploy to the start of the step day, so `6h after
v2.14` means the tag was cut at 18:00 the evening before.

## Deploy sources

```sh
--deploys-git [PATH]           # tags in a checkout, by creation date
--deploys-github OWNER/REPO    # the GitHub Deployments API, via gh
--deploys-argocd APP           # argocd app history APP -o json
--deploys-file PATH            # a CSV or JSON list of timestamp + label
```

`--tag-pattern` filters git tags (`'v*'`); `--deploy-match` filters any source by
label (`'production/*'`), which is how you keep staging deploys out of a
production timeline.

The file source exists so nobody is locked out by their deploy tooling:

```csv
timestamp,label,revision
2026-09-02T18:00:00Z,v2.14,9f3a1c2
```

A CSV may also be headerless (`timestamp,label,revision,url` in that order), and
JSON may be a list of objects or of `[timestamp, label]` pairs.

## Output

`--format markdown` (default) or `--format json`. The JSON carries every number
the Markdown shows plus the daily series, so a dashboard never has to re-parse
prose. `--chart ascii|mermaid|none` draws the series with `▲` under each deploy
day; `--chart-group` picks which series (default: the total).

`--pr-comment` posts each confidently attributed step on the pull request its
deploy points at, via `gh` — only single-deploy steps, since with two candidates
there is no one PR to tell. `--dry-run` prints instead of posting, and `--repo`
names the repository when it cannot be inferred.

## Cost and state

One `GetCostAndUsage` call per timeline (plus a page or two on a large account),
at $0.01 each. `--cache-dir` stores the assembled answer on disk with a
`--cache-ttl` (default 24h) so tuning a threshold does not buy the same days
twice. That cache is the only state the tool keeps, and it is opt-in.

[pelt]: https://arxiv.org/abs/1101.1438
