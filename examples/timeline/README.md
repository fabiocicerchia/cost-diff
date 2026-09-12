# Timeline Example

What it shows: the last 60 days of daily cost, the days it stepped, and the
deploy that landed just before each step.

## Run

```sh
export AWS_PROFILE=billing   # needs ce:GetCostAndUsage

# deploys from the tags in this checkout
cost-diff timeline --deploys-git . --tag-pattern 'v*'

# or from a file, so it runs anywhere — deploys.csv here is a sample
cost-diff timeline --deploys-file deploys.csv --end 2026-09-11
```

## What you get

```text
## Steps

- **+$41/day in Amazon EC2 starting 2026-09-03**, 6h after `v2.14` — one deploy in window, high confidence.
  - $107/day → $149/day (+39%), 13.9σ over the window's noise
  - `v2.14` — 2026-09-02T18:00Z (`9f3a1c2`, file, 6h before the step day)
```

Plus a chart of the series with `▲` under each deploy day. Add `--format json`
for the same numbers as data, or `--chart mermaid` for a diagram to paste into a
doc.

## Reading it honestly

`v2.14` is the deploy that *preceded* the step and was alone in the window. That
is a coincidence in time, not a proven cause — start there, don't stop there.

## Feeding it your own deploys

`deploys.csv` is the dullest possible format on purpose:

```csv
timestamp,label,revision
2026-09-02T18:00:00Z,v2.14,9f3a1c2
```

Anything that can write three columns can drive this: a CI job, a webhook log, a
`git log` one-liner. The other sources (`--deploys-github`, `--deploys-argocd`)
save you writing it when your deploys are already recorded somewhere.
