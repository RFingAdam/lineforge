# PyPI / TestPyPI Trusted Publisher Setup

Once-only browser config to enable OIDC-based publishing from this repo's
release workflow.

## Why trusted publishers

GitHub Actions signs each workflow run with a short-lived OIDC token.
PyPI / TestPyPI verifies the token's claims (`repository`, `workflow`,
`environment`) against a pre-registered list of trusted publishers and
accepts the upload if they match. No long-lived API tokens in GitHub
secrets, no rotation, much smaller blast radius if compromised.

The downside: a one-time browser configuration per index (TestPyPI + PyPI)
is required before the workflow can publish.

## TestPyPI setup

1. Go to https://test.pypi.org/manage/account/publishing/
2. Click **Add a new pending publisher**
3. Fill in:
   - **PyPI Project Name**: `lineforge`
   - **Owner**: `RFingAdam`
   - **Repository name**: `lineforge`  (or `atlc3` until the GitHub repo rename completes)
   - **Workflow filename**: `release.yml`
   - **Environment name**: `testpypi`
4. Submit.

The publisher is now "pending" until the first publish succeeds — after
that it auto-promotes to a real publisher.

## PyPI (production) setup

Same flow as TestPyPI, on the real index:

1. Go to https://pypi.org/manage/account/publishing/
2. Click **Add a new pending publisher**
3. Same fields as above, but:
   - **Environment name**: `pypi`  (matches the `environment.name` in `publish-pypi` job)

## Triggering a release

After both publishers are registered:

```bash
# TestPyPI happens automatically on tag push
git tag v2.0.1
git push origin v2.0.1

# Real PyPI is gated behind workflow_dispatch with target=pypi (manual approval)
gh workflow run release.yml -f target=pypi
```

## What if you don't want trusted publishers

The fallback is a long-lived API token. Steps:

1. Create token at https://pypi.org/manage/account/token/ (scoped to the
   `lineforge` project)
2. Add as a GitHub secret: `PYPI_API_TOKEN`
3. Edit `.github/workflows/release.yml` to use it:

   ```yaml
   - name: Publish to PyPI
     uses: pypa/gh-action-pypi-publish@release/v1
     with:
       password: ${{ secrets.PYPI_API_TOKEN }}
   ```

   And remove the `permissions: id-token: write` block and the
   `environment:` section.

We recommend trusted publishers — they're more secure and ergonomic.

## Troubleshooting

**Error: `invalid-publisher: valid token, but no corresponding publisher`**

The publisher isn't registered for this exact (repo, workflow, environment)
triple. Check that your registration on test.pypi.org / pypi.org matches:

- The repo owner exactly (`RFingAdam` not `rfingadam`)
- The repo name exactly (after the GitHub rename, this is `lineforge`)
- The workflow filename exactly (`release.yml`)
- The environment name exactly (`testpypi` or `pypi`)

If you're publishing during the GitHub repo rename transition:
- The OIDC claim uses the *current* repo name at the time of the workflow run
- Pre-register publishers under BOTH `RFingAdam/atlc3` AND `RFingAdam/lineforge`
  if you want a smooth handover (or just delete the atlc3 one once renamed)

**Error: `403 Forbidden — The user 'X' isn't allowed to upload to project Y`**

Usually means the project already exists on PyPI under a different owner,
or you need to claim the name first by uploading a stub package via API
token before trusted publishing works.

## Current state

As of v2.0.0 (2026-05-11):

- ✗ TestPyPI trusted publisher NOT yet registered
- ✗ PyPI trusted publisher NOT yet registered
- ✓ `release.yml` workflow correctly configured for both targets
- ✓ `publish-testpypi` job set to `continue-on-error: true` so the
  failure-to-publish doesn't fail the whole release
- ✓ Wheels build successfully on Linux x86_64/aarch64 + macOS + Windows
- ✓ sdist builds successfully

Once you register both publishers, no code changes needed — just re-run
the release workflow (or push a new tag).
