# Getting Started

## Prerequisites

- Python 3.10+
- An AWS profile with the `ce:GetCostAndUsage` permission.

## Setup

```sh
pipx install .            # or: pip install .
export AWS_PROFILE=billing
```

## Run

```sh
cost-diff --last-month
cost-diff --period 2026-06 --vs 2026-03 --group LINKED_ACCOUNT
cost-diff --last-month --slack "$SLACK_WEBHOOK"   # e.g. a monthly cron
```

Each Cost Explorer call costs $0.01, so a monthly run is effectively free.
