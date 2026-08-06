# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1](https://github.com/fabiocicerchia/cost-diff/compare/v0.1.0...v0.1.1) (2026-08-06)


### Bug Fixes

* **pre-commit:** stop check-yaml failing on Helm templates and multi-doc manifests ([0d3a567](https://github.com/fabiocicerchia/cost-diff/commit/0d3a567d6be41a307972c9af78856007decbb372))
* **security:** skip the SARIF upload on private repos ([8ed81ea](https://github.com/fabiocicerchia/cost-diff/commit/8ed81ea132a21ccde8e6bdafaacedc2378a96651))

## [Unreleased]

## [0.1.0]

### Added

- AWS Cost Explorer period-over-period diff (`--last-month`, `--period`/`--vs`).
- Human-readable "what changed and why" report, sorted by absolute impact.
- New-service detection and `--group` breakdown (e.g. `LINKED_ACCOUNT`).
- Slack-postable output via `--slack`.

[Unreleased]: https://github.com/fabiocicerchia/cost-diff/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/fabiocicerchia/cost-diff/releases/tag/v0.1.0
