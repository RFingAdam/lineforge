# Publishing to PyPI

`.github/workflows/release.yml` publishes lineforge from a `v*` tag on `main`. PyPI accepts the
upload through a trusted publisher, so the repository holds no API token.

## One-time setup

1. Sign in at <https://pypi.org/manage/account/publishing/>.
2. Under **Add a new pending publisher**, choose GitHub and enter:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `lineforge` |
   | Owner | `RFingAdam` |
   | Repository name | `lineforge` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

A pending publisher does not reserve the name. It becomes a normal publisher on the first upload,
and it stops working if someone else takes `lineforge` first.

The repository side is already in place: the `pypi` environment accepts only `v*` tags, and the
"Release tags" ruleset limits who can create, move, or delete them.

## Releasing

1. Set the version in `Cargo.toml` and `src/lineforge/version.py`, refresh `Cargo.lock`, and move
   the changelog entry out of `[Unreleased]`.
2. Merge to `main`.
3. Tag that commit:

   ```bash
   gh api repos/RFingAdam/lineforge/git/refs -f ref=refs/tags/vX.Y.Z \
     -f sha="$(gh api repos/RFingAdam/lineforge/commits/main --jq .sha)"
   ```

The tag builds the sdist and a wheel for each target, installs each wheel on its own platform,
checks that the kernel loads and solves a line, publishes, and creates the GitHub release. A pull
request that touches the release path runs everything except the last two steps.

A PyPI version can never be reused. If a release is wrong, fix it and tag the next version.

## Troubleshooting

**`invalid-publisher: valid token, but no corresponding publisher`**: the registration does not
match this run. Compare the owner, repository, workflow file name, and environment with the table
above; the match is exact.

**`403 Forbidden`, the user isn't allowed to upload**: the project exists on PyPI under another
owner, so the pending publisher no longer applies.
