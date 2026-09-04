# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2](https://github.com/fabiocicerchia/cost-diff/compare/v0.2.1...v0.2.2) (2026-09-04)


### Bug Fixes

* **ci:** pin the editorconfig-checker binary version ([#68](https://github.com/fabiocicerchia/cost-diff/issues/68)) ([653f2f0](https://github.com/fabiocicerchia/cost-diff/commit/653f2f0bdeba56d5e01abae1ed39ca9797a44b8f))

## [0.2.1](https://github.com/fabiocicerchia/cost-diff/compare/v0.2.0...v0.2.1) (2026-08-29)


### Bug Fixes

* unblock quality and clear the Scorecard pinned-dependencies finding ([#53](https://github.com/fabiocicerchia/cost-diff/issues/53)) ([a5de0a5](https://github.com/fabiocicerchia/cost-diff/commit/a5de0a5e1e54991b6b7659425a4b33796c2b66e7))

## [0.2.0](https://github.com/fabiocicerchia/cost-diff/compare/v0.1.2...v0.2.0) (2026-08-25)


### Features

* **docs:** build the docs site in Actions and drop Read the Docs ([#43](https://github.com/fabiocicerchia/cost-diff/issues/43)) ([62d9925](https://github.com/fabiocicerchia/cost-diff/commit/62d9925c46f0af79fdaaaa12587a68bc9cf5a350))


### Bug Fixes

* **ci:** compute the next release PR after the draft is published ([#40](https://github.com/fabiocicerchia/cost-diff/issues/40)) ([8c1a336](https://github.com/fabiocicerchia/cost-diff/commit/8c1a33649289b8bfb8b57b99dddfa7adcebbcb58))

## [0.1.2](https://github.com/fabiocicerchia/cost-diff/compare/v0.1.1...v0.1.2) (2026-08-13)


### Bug Fixes

* security and code-quality findings ([#34](https://github.com/fabiocicerchia/cost-diff/issues/34)) ([7411ec8](https://github.com/fabiocicerchia/cost-diff/commit/7411ec802fa4bcf10e1bd7cdf7f096db1948a343))

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
