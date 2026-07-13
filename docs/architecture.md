# Architecture

## Overview

`cost-diff` fetches grouped costs for two periods from AWS Cost Explorer,
diffs them per service, and renders a Markdown report sorted by absolute
impact.

## Components

- **Cost Explorer client** — injectable `boto3` client (`ce`), mocked in tests.
- **Diff** — pairs services across the two periods; flags new/removed ones.
- **Report** — Markdown table sorted by absolute delta, optional Slack post.

## Data flow

`args → fetch(period) + fetch(vs) → diff → render → stdout / Slack`

## Decisions

Record significant choices here (or in a `docs/adr/` folder if they pile up).
