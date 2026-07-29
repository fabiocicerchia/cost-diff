# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0 (2026-07-29)


### Features

* add --metric selection for credits/refunds/RI-amortization handling ([e515435](https://github.com/fabiocicerchia/cost-diff/commit/e515435b866de09e5abb58ef7fd5f0e7844a8efd))
* add --why drill-down of the biggest mover by USAGE_TYPE ([a47be4a](https://github.com/fabiocicerchia/cost-diff/commit/a47be4a91a79f278cdec9f0418428e05dba49892))
* add install.sh one-liner installer ([d751291](https://github.com/fabiocicerchia/cost-diff/commit/d751291a21b7afeafbfc43f499b8e32ce15e4621))
* add weekday-normalized anomaly hints to the report ([b92e755](https://github.com/fabiocicerchia/cost-diff/commit/b92e755d7fa3bc8eecdd46747619a79b3b65174f))
* post Slack reports as Block Kit instead of raw GFM text ([3a244d1](https://github.com/fabiocicerchia/cost-diff/commit/3a244d15e9712b514120d74b9bbea8985ca19076))


### Bug Fixes

* restore executable bit, fix broken trivy-action pin, align codeql-action label ([#11](https://github.com/fabiocicerchia/cost-diff/issues/11)) ([5bcf6e0](https://github.com/fabiocicerchia/cost-diff/commit/5bcf6e040f13e5750ccf1ff9cd8c2bb6b71ae500))


### Documentation

* add GitHub Pages site, trim completed roadmap items from README ([aa33393](https://github.com/fabiocicerchia/cost-diff/commit/aa3339331aef42d4fb9686b85e2b725ca5124fe3))
* add missing README badges ([1d4b00d](https://github.com/fabiocicerchia/cost-diff/commit/1d4b00d0860af651b5f0e647631a1faa6209dced))
* remove the broken FOSSA badge ([264d5da](https://github.com/fabiocicerchia/cost-diff/commit/264d5da37ef93c290a3abbda6caef958795a12d8))

## [Unreleased]

## [0.1.0]

### Added

- AWS Cost Explorer period-over-period diff (`--last-month`, `--period`/`--vs`).
- Human-readable "what changed and why" report, sorted by absolute impact.
- New-service detection and `--group` breakdown (e.g. `LINKED_ACCOUNT`).
- Slack-postable output via `--slack`.

[Unreleased]: https://github.com/fabiocicerchia/cost-diff/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fabiocicerchia/cost-diff/releases/tag/v0.1.0
