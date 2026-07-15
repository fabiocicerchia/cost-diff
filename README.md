# cost-diff

[![CI](https://github.com/fabiocicerchia/cost-diff/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiocicerchia/cost-diff/actions/workflows/ci.yml)
[![Security](https://github.com/fabiocicerchia/cost-diff/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/cost-diff/actions/workflows/security.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/cost-diff/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/cost-diff)
[![FOSSA Status](https://app.fossa.com/api/projects/git%2Bgithub.com%2Ffabiocicerchia%2Fcost-diff.svg?type=shield)](https://app.fossa.com/projects/git%2Bgithub.com%2Ffabiocicerchia%2Fcost-diff?ref=badge_shield)
[![Release](https://img.shields.io/github/v/release/fabiocicerchia/cost-diff)](https://github.com/fabiocicerchia/cost-diff/releases)

Diffs two **AWS Cost Explorer** periods into a human-readable
**"what changed and why"** report — sorted by absolute impact, new services
flagged, postable to Slack. The monthly bill autopsy, automated.

```console
$ cost-diff --last-month --top 5
# AWS cost diff: 2026-05 → 2026-06

**Total: $12,340 → $14,890 (▲ $2,550)**

| change | service | before | after |
|---|---|---|---|
| +$1,900 (+38%) | Amazon EC2 | $5,000 | $6,900 |
| +$400 (new)    | Amazon SageMaker | $0 | $400 |
...
```

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

cost-diff --last-month
cost-diff --period 2026-06 --vs 2026-03 --group LINKED_ACCOUNT
cost-diff --last-month --slack "$SLACK_WEBHOOK"     # monthly cron
```

IAM: `ce:GetCostAndUsage` only. Cost Explorer calls cost $0.01 each — a
monthly run is effectively free.

## Status & roadmap

Core diffing/reporting is implemented and unit-tested (Cost Explorer client
injectable/mocked). The deep end is edge cases:

- [ ] Credits/refunds/RI-amortization handling (`--metric` selection)
- [ ] "Why" drill-down: auto-split biggest mover by USAGE_TYPE
- [ ] Anomaly hints (weekday-normalized comparisons)
- [ ] Slack Block Kit formatting

## Development

`make dev` then `make test` / `make lint`. Full docs live in [`docs/`](docs/);
runnable examples in [`examples/`](examples/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please don't open a
public issue.

## License

Apache 2.0 — see [LICENSE](LICENSE).
