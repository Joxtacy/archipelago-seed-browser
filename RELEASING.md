# Releasing

This is the operator's runbook for cutting a release. Most of the work is
done by `.github/workflows/release.yml`; this file documents what to do
around it.

## Versioning

We follow semver. Tag format is `vMAJOR.MINOR.PATCH`, optionally with a
pre-release suffix separated by a hyphen (e.g. `v1.0.0-rc1`, `v1.1.0-beta2`).

The release workflow inspects the tag:

- **Hyphen present** (e.g. `v1.0.0-rc1`, `v0.2.0-list`) → published as a
  GitHub **prerelease**.
- **No hyphen** (e.g. `v1.0.0`, `v1.1.0`) → published as a **stable
  release** and marked as the latest.

Keep `pyproject.toml`'s `version` field in sync with the tag you're about
to push. PEP 440 normalizes hyphens, so a tag like `v1.0.0-rc1` should map
to `version = "1.0.0rc1"`.

`seed_browser/archipelago.json` carries a separate `world_version` that AP
reads from inside the apworld. AP's parser is strict three-part semver
(`int(piece) for piece in version.split(".")`) — prerelease suffixes are
not allowed. Update `world_version` only on stable tags (e.g. `1.0.0`,
`1.1.0`); leave it untouched through rc cycles.

## Cutting a release

1. **Decide what's in it.** `main` should already contain everything you
   want shipped; if not, merge it in first.
2. **Bump `pyproject.toml`** to the version you're about to tag, e.g.
   `version = "1.0.0"`. Commit on `main`:
   ```sh
   jj describe -m "chore: bump version to 1.0.0"
   jj bookmark move main --to @
   jj git push --bookmark main
   ```
3. **Wait for CI to go green** on that commit. The release workflow re-runs
   tests, but a broken `main` is a faster signal.
4. **Tag the commit:**
   ```sh
   git tag v1.0.0 <commit-sha>
   git push origin v1.0.0
   ```
   (jj's bookmark/tag model differs from git's. Easiest path is to drop to
   `git tag` directly in the colocated repo — `jj` will pick it up.)
5. **Watch the workflow:**
   ```sh
   gh run watch --repo Joxtacy/archipelago-seed-browser --exit-status
   ```
6. **Verify the release page** at
   `github.com/Joxtacy/archipelago-seed-browser/releases/tag/v1.0.0`.
   Confirm `seed_browser.apworld` is attached and the auto-generated notes
   look reasonable. Edit notes via the GitHub UI if you want to polish.

## What the workflow does

`.github/workflows/release.yml`, on push of any `v*` tag:

1. Checks out the tagged commit with full history (`fetch-depth: 0`) so
   the release-notes generator can diff against the previous tag.
2. Installs Python 3.13 + project dev deps via uv.
3. Runs `ruff check` and `pytest`. **A failure here aborts the release**
   — no broken artifact gets published.
4. Runs `scripts/build_apworld.sh` to produce `dist/seed_browser.apworld`.
5. Invokes `gh release create <tag> --generate-notes [--prerelease]
   dist/seed_browser.apworld`. The `--generate-notes` flag asks GitHub to
   build release notes from commits and merged PRs since the previous
   release tag.

## Release notes

Auto-generated notes pull from:

- Commit titles between the previous release tag and this one.
- Merged PRs in that range (with author attribution).
- Contributors in that range.

If you want richer / curated notes for a particular release, edit the
release on the GitHub UI after the workflow finishes — the auto-generated
body is overwritable. There is currently no `CHANGELOG.md`; if that ever
becomes useful, drop one in and have the workflow include it instead of
(or alongside) `--generate-notes`.

## Recovering from a failed release

The workflow re-runs tests, so a release can fail mid-flight. If that
happens:

- **Lint/test failure** — fix on `main`, then **delete the bad tag** and
  re-tag at the new commit:
  ```sh
  git tag -d v1.0.0
  git push origin :refs/tags/v1.0.0
  # ... fix on main ...
  git tag v1.0.0 <new-sha>
  git push origin v1.0.0
  ```
  Deleting an already-published GitHub release also needs
  `gh release delete v1.0.0 --yes`.
- **Build failure** — same recovery; root-cause locally with
  `./scripts/build_apworld.sh` first.
- **Workflow succeeded but the release is wrong** (bad notes, wrong
  asset) — edit/delete via `gh release edit` or `gh release delete`
  without retagging, if the binary itself is still correct.

## Pre-release tags

Phase tags like `v0.1.0-foundation`, `v0.2.0-list`, `v0.3.0-actions`, and
`v1.0.0-rc1` were created during early development and pushed before the
release workflow existed, so they have no associated GitHub release.
Those tags are kept as historical markers; do not retroactively run the
workflow on them.

Future pre-release tags (`v1.1.0-rc1`, `v2.0.0-beta1`, etc.) will run the
workflow and publish a marked-as-prerelease GitHub release automatically.

## Discord announcement

Per `PLAN.md` §7 Phase 5, the user announces v1 in Archipelago's Discord
tools channel. Not part of this workflow.
