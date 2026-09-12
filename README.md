# cost-diff

[![CI](https://github.com/fabiocicerchia/cost-diff/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiocicerchia/cost-diff/actions/workflows/ci.yml)
[![Security](https://github.com/fabiocicerchia/cost-diff/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/cost-diff/actions/workflows/security.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/cost-diff/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/cost-diff)
[![CI carbon](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/fabiocicerchia/cost-diff/gh-pages/badge.json)](.github/workflows/carbon-badge.yml)
[![Release](https://img.shields.io/github/v/release/fabiocicerchia/cost-diff)](https://github.com/fabiocicerchia/cost-diff/releases)

**Which deploy moved the AWS bill.**

`cost-diff timeline` pulls daily cost from **AWS Cost Explorer**, finds the days
it stepped to a new level, and names the deploy that landed just before each
step — from git tags, the GitHub Deployments API, Argo CD history, or a CSV
anyone can write. Markdown, a chart, or JSON; no server, no state, read-only
AWS access.

```console
$ cost-diff timeline --days 60 --deploys-git .
# AWS cost timeline: 2026-07-14 → 2026-09-11

Daily UnblendedCost from Cost Explorer, grouped by SERVICE.
Steps: rolling median with a MAD threshold (window 7d, threshold 4σ). Steps under $5/day, and level changes that take longer than 2d to complete, are not reported.
3 deploys from git, attributed within 24h. Attribution is temporal, not causal: the deploy preceded the step, which is not proof that it caused it.

## Steps

- **+$41/day in Amazon EC2 starting 2026-09-03**, 6h after `v2.14` — one deploy in window, high confidence.
  - $107/day → $149/day (+39%), 13.9σ over the window's noise
  - `v2.14` — 2026-09-02T18:00Z (`9f3a1c2`, git, 6h before the step day)
```

## Where this sits

[aws-cost-cli][aws-cost-cli] already does period-over-period AWS cost
reporting, with Slack output and a GitHub Action. If you want to know **what
you spent**, use that — it is the better reporting tool, and this one keeps its
own period diff as a subcommand rather than competing with it.

`cost-diff timeline` answers the question that comes after the report: the bill
went up **on a day**, and something shipped **around that day**. Nobody joins
those two up for you.

**Attribution here is temporal, not causal.** The tool reports that a deploy
preceded a step and how alone it was in that window. It does not know what the
deploy changed, and a step can just as easily be a traffic spike, a retention
policy, an expired credit or a Savings Plan running out. Treat a named deploy
as the first place to look, not as the answer.

## Features

- Finds the days daily cost **stepped to a new level** and names the deploy that
  landed just before each one, rather than leaving you to line up two tabs.
  Grouped by service, or by service and a **cost-allocation tag**.
- Reads deploys from **git tags, the GitHub Deployments API, Argo CD history, or
  a CSV** — whichever thing already records what shipped, and a file if nothing
  does.
- Grades each step by **how alone that deploy is** in the window, and lists every
  candidate rather than guessing when several landed together.
- Says **temporal, not causal** wherever it reports: the deploy preceded the
  step, which makes it the first place to look, not the answer.
- Two **explainable detectors** and no stats dependency — a rolling median with a
  MAD threshold, or a minimal PELT — and the report says which one ran.
- Never calls a **gradual ramp** a step, so growing traffic does not get blamed
  on a release.
- **Markdown, JSON, or a chart** (ASCII or Mermaid, deploy days marked), plus
  `--pr-comment` to post a step on the pull request its deploy points at.
- Still **diffs two periods** when that is the question: biggest mover first, new
  services flagged, any Cost Explorer dimension (`--group LINKED_ACCOUNT`), any
  two periods, and `--slack "$SLACK_WEBHOOK"` for a monthly cron.
- Needs one IAM permission, `ce:GetCostAndUsage`, and the API calls cost
  $0.01 each — a 60-day timeline is effectively free.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/cost-diff/main/install.sh | bash
```

Or with pipx directly:

```sh
pipx install git+https://github.com/fabiocicerchia/cost-diff
```

## Usage

```sh
export AWS_PROFILE=billing      # needs ce:GetCostAndUsage

cost-diff timeline --deploys-git .                     # tags in this checkout
cost-diff timeline --deploys-github acme/api --tag Environment
cost-diff timeline --deploys-argocd api --days 90 --method pelt
cost-diff timeline --deploys-file deploys.csv --format json
cost-diff timeline --deploys-git . --chart mermaid --chart-group "Amazon EC2"

cost-diff diff --last-month                            # the period diff
```

IAM: `ce:GetCostAndUsage` only — nothing here writes. Cost Explorer calls cost
$0.01 each; a 60-day timeline is one call (plus a page or two on a large
account).

### Deploy sources

Pick exactly one. Every source ends up as the same thing: a timestamp, a label,
and optionally a revision.

| Flag | Reads | Needs |
| --- | --- | --- |
| `--deploys-git [PATH]` | tags in a checkout, by creation date | `git` |
| `--deploys-github OWNER/REPO` | the GitHub Deployments API | `gh`, authenticated |
| `--deploys-argocd APP` | `argocd app history APP -o json` | `argocd`, logged in |
| `--deploys-file PATH` | a CSV or JSON list | nothing |

`--tag-pattern 'v*'` picks which git tags count; `--deploy-match 'production/*'`
filters any source by label. The file format is deliberately dull:

```csv
timestamp,label,revision
2026-09-02T18:00:00Z,v2.14,9f3a1c2
```

JSON works too — a list of objects (`timestamp`/`time`/`date` plus
`label`/`name`/`tag`) or a list of `[timestamp, label]` pairs. Timestamps are
ISO 8601 (a naive one is read as UTC), or an epoch in seconds or
milliseconds.

### What counts as a step

Two methods, both explainable, neither a dependency. The report always says
which one produced it.

- `--method median-mad` (default) — compare the median of the 7 days before each
  day with the median of the 7 days after. A step has to clear `4σ` of the
  window's own noise, measured as a median absolute deviation, so a service that
  bounces around by 30% a day needs a bigger move to qualify than a steady one.
  That noise estimate is floored at 2% of the level, because a bill that charges
  the same round number every day has none for a step to have to beat.
- `--method pelt` — a minimal [PELT][pelt] changepoint search (L2 segment cost,
  a `σ²·ln n` penalty, and the pruning that makes it PELT). Better when the
  series has several steps in it; slower to explain to a finance team.

`--threshold-sigma` applies to both. Both then have to pass the same two
filters:

- **a dollar floor** (`--min-step`, default `$5/day`) — a step nobody would act on
  is not worth a name.
- **a ramp guard** (`--ramp-fraction`, default `0.6`) — most of the level change
  has to land inside the transition itself rather than trickle in, measured
  against what the series does over a horizon several times longer. A straight
  line only ever delivers a couple of days' worth of its rise in two days,
  however steep it is, so **a gradual ramp is never reported as a step**.
  Growing traffic is not a deploy.

A one-day spike fails both: it is not a new level, so the medians either side
barely move. The day reported is the first one the new level holds, which is the
day a deploy has to precede.

### Attribution and confidence

A step first visible on day *D* is attributed to deploys in the `--deploy-window`
(default 24h) before *D* **plus day *D* itself** — a deploy at lunchtime only
bills half a day, so it shows up on the day it happened or the day after.

| Deploys in window | Confidence | Reported as |
| --- | --- | --- |
| 1 | high | named, with the lag: `6h after v2.14` |
| 2 | medium | both listed, newest first |
| 3+ | low | all listed |
| 0 | none | the step, unattributed |

With more than one deploy in the window there is nothing in a daily cost series
that can tell them apart, so the tool lists them instead of guessing.

### Output

- `--format markdown` (default) — the timeline above.
- `--format json` — the same numbers, plus the daily series, for a dashboard.
- `--chart ascii` (default) / `--chart mermaid` / `--chart none` — the series with
  `▲` under every deploy day. `--chart-group` picks which series to draw
  (default: the total).
- `--pr-comment` — post each confidently attributed step on the pull request its
  deploy tag points at, via `gh`. Pairs with `--dry-run` to see it first. Only
  single-deploy steps are posted: with two candidates there is no one PR to tell.
- `--cache-dir PATH` — cache Cost Explorer answers (`--cache-ttl`, default 24h)
  while tuning thresholds, so the same 60 days are not bought twice. It is the
  only state the tool keeps, and it is opt-in.

## The period diff

The original report — two Cost Explorer periods, biggest mover first, new
services flagged, postable to Slack — is now `cost-diff diff`:

```console
$ cost-diff diff --last-month --top 5
# AWS cost diff: 2026-05 → 2026-06

**Total: $12,340 → $14,890 (▲ $2,550)**

| change         | service          | before | after  |
| -------------- | ---------------- | ------ | ------ |
| +$1,900 (+38%) | Amazon EC2       | $5,000 | $6,900 |
| +$400 (new)    | Amazon SageMaker | $0     | $400   |
```

`cost-diff --last-month` (no subcommand) still works and still means the diff.

## Verifying the image

Every published image is signed with [cosign][cosign], keyless: the identity in
the signature is the workflow that published it, not a key anybody holds.

```sh
cosign verify ghcr.io/fabiocicerchia/cost-diff:latest \
  --certificate-identity-regexp \
    'https://github.com/fabiocicerchia/cost-diff/.github/workflows/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

`no signatures found` means the tag predates signing, not that verification was
set up wrongly — a wrong identity or issuer says so explicitly. Re-run the
publish workflow for that tag to sign it.

[aws-cost-cli]: https://github.com/nilbuild/aws-cost-cli
[cosign]: https://docs.sigstore.dev/
[pelt]: https://arxiv.org/abs/1101.1438

## Development

`make dev` then `make test` / `make lint`. Full docs live in [`docs/`](docs/);
runnable examples in [`examples/`](examples/).

## Documentation

Full docs live in [`docs/`](docs/). Runnable examples live in [`examples/`](examples/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a
public issue.

## Support

Need help implementing this? [Get in touch](https://fabiocicerchia.it/contact).

## License

Apache 2.0 — see [LICENSE](LICENSE).
