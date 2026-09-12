# Getting Started

## Prerequisites

- Python 3.10+
- An AWS profile with the `ce:GetCostAndUsage` permission.
- For deploy sources other than a file: `git`, `gh`, or `argocd` on PATH.

## Setup

```sh
pipx install .            # or: pip install .
export AWS_PROFILE=billing
```

## Which deploy moved the bill

```sh
cost-diff timeline --deploys-git .                    # tags in this checkout
cost-diff timeline --deploys-file deploys.csv --days 90
cost-diff timeline --deploys-github acme/api --format json
```

The report names the deploy that preceded each step in daily cost, and says how
alone it was in the window. Attribution is temporal, not causal — see
[Timeline](timeline.md) for what that does and does not mean, and for every knob.

## What changed between two periods

```sh
cost-diff diff --last-month
cost-diff diff --period 2026-06 --vs 2026-03 --group LINKED_ACCOUNT
cost-diff diff --last-month --slack "$SLACK_WEBHOOK"   # e.g. a monthly cron
```

`cost-diff --last-month` without a subcommand still means the diff.

Each Cost Explorer call costs $0.01, so either report is effectively free to
run on a schedule.
