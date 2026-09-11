# Architecture

## Overview

One module, `cost_diff.py`, and two subcommands over the same Cost Explorer
client:

- `timeline` — daily cost, the steps in it, and the deploy each step followed.
- `diff` — two periods, biggest mover first (the original report).

## Components

- **Cost Explorer client** — injectable `boto3` client (`ce`), mocked in tests.
  Monthly for the diff, daily for the timeline.
- **Diff** — pairs services across two periods; flags new/removed ones.
- **Step detection** — rolling median with a MAD threshold, or a minimal PELT
  changepoint search. Pure stdlib (`statistics`, `math`): a step detector is not
  worth a numerical dependency, and neither is explainable if it is a black box.
- **Deploy sources** — git tags, the GitHub Deployments API (via `gh`), Argo CD
  history (via `argocd`), or a CSV/JSON file. Each returns the same `Deploy`
  record, so everything downstream is source-agnostic.
- **Attribution** — pairs each step with every deploy in its window and grades
  the confidence by how alone that deploy is.
- **Report** — Markdown, a chart (ASCII or Mermaid), or JSON; optional PR
  comment via `gh`, optional Slack post for the diff.

## Data flow

```text
timeline: args → fetch_daily_costs → densify → detect_steps → attribute → render
diff:     args → fetch_costs(period) + fetch_costs(vs) → build_diff → render
```

## Decisions

- **Single module.** The tool is one CLI with two entry points into the same
  client and the same money formatting; splitting it would buy import graphs and
  cost the ability to read it end to end.
- **No stats dependency.** Both detectors are a few dozen lines of `statistics`
  and `math`. A finance conversation about a $41/day step should not have to
  start with "well, the library says".
- **Temporal attribution only.** The tool reports that a deploy preceded a step.
  Claiming cause would need to know what the deploy changed, which Cost Explorer
  cannot tell it — so the wording, the confidence grades, and the JSON all say
  so instead of implying otherwise.
- **No state.** No server, no database; an opt-in on-disk cache of Cost Explorer
  answers is the only thing written, because the API bills per call.

Record further significant choices here (or in a `docs/adr/` folder if they pile
up).
