# Contributing

Thanks for taking the time to contribute to cost-diff!

## Getting started

1. Fork and clone the repo (needs Python 3.10+ and `make`).
1. Install tooling and git hooks: `make setup` (git hooks) and `make dev`
   (editable install with pytest, ruff, build).
1. Create a branch: `git checkout -b feat/short-description`.

## Making changes

- Keep changes focused; one logical change per PR.
- Add or update tests; keep the existing style.
- Update `docs/` and `examples/` when behavior changes.
- Don't edit `CHANGELOG.md` by hand — it's generated from commit messages by
  release-please.
- Make sure it passes locally:

  ```sh
  make lint    # ruff check .
  make test    # pytest
  ```

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
`fix:`, `docs:`, `chore:`, etc. This drives the version bump: `fix:` → patch,
`feat:` → minor, `feat!:` or a `BREAKING CHANGE:` footer → major.

## Releases

Releases are automated by
[release-please](.github/workflows/release.yml) — you don't tag or edit the
changelog manually.

1. Merge `feat:`/`fix:` PRs into `main` as normal — **no tag is created**.
1. release-please keeps an open **release PR** ("chore: release X.Y.Z") that
   bumps `pyproject.toml`'s version and updates `CHANGELOG.md`, recalculating on
   every merge.
1. When you're ready to ship, **merge the release PR** — that (and only that)
   creates the `vX.Y.Z` tag and GitHub Release, builds the sdist + wheel,
   attaches them, and (if `PUBLISH_TO_PYPI` is set) publishes to PyPI via
   trusted publishing.

## Pull requests

Fill out the PR template, link related issues, and request review. By
participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Contributions are licensed under the [Apache 2.0](LICENSE) license.
