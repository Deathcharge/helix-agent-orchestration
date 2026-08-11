# Release operations

Samsarix Orchestration releases use one controlled path: publish a GitHub release whose
tag exactly matches the package version, approve the protected `pypi` deployment, and let
GitHub Actions exchange an OIDC identity for a short-lived PyPI credential. No long-lived
package-index token belongs in GitHub secrets.

## One-time publisher setup

Before the first release, register a pending PyPI Trusted Publisher with these exact values:

| Field | Value |
| --- | --- |
| PyPI project | `samsarix-orchestration` |
| GitHub owner | `Deathcharge` |
| Repository | `samsarix-agent-orchestration` |
| Workflow | `release.yml` |
| Environment | `pypi` |

The public PyPI JSON endpoint returned `404` for this normalized project name on
2026-08-10. That is availability evidence, not a reservation; only a successful first
Trusted Publishing upload creates and claims the project.

The GitHub `pypi` environment must require a reviewer and allow only version tags matching
`v*`. Keep self-review disabled when a second authorized maintainer is available. Protect
changes to `.github/workflows/release.yml` like publishing credentials because PyPI trusts
the repository, workflow filename, and environment identity together.

## Prepare a release

1. Start from a clean, current `main` and confirm its post-merge CI matrix is green.
2. Choose the version and update `project.version`, `CHANGELOG.md`, and any status text in
   the same pull request. Versions are immutable after publication.
3. Run Ruff, strict MyPy, Bandit, the full branch-aware test suite, `python -m build`, and
   `python -m twine check dist/*` in a clean supported Python environment.
4. Merge the green release pull request. Create a draft GitHub release targeting `main`
   with tag `v<project.version>` and release notes derived from the changelog.
5. Publish the GitHub release. The workflow checks out the immutable tag, rejects a
   tag/version mismatch, rebuilds and validates the wheel and source archive, verifies the
   wheel boundary, generates SHA-256 checksums and a Sigstore/GitHub provenance attestation,
   and attaches those immutable files to the GitHub release. Only then does publication wait
   for approval on the `pypi` environment.
6. Review the workflow run and approve the deployment only when the tag, commit, changelog,
   artifact names, and checksums are expected. The final job publishes the already-attached
   distributions via PyPI OIDC.

The release trigger deliberately has no `workflow_dispatch` or ordinary tag-push path.
Publishing the GitHub release is the explicit release action, and the protected environment
is the final registry gate.

## Verify publication

Use a new environment with no source checkout on `PYTHONPATH`:

```bash
python -m venv verify-release
verify-release/bin/python -m pip install --no-cache-dir samsarix-orchestration==0.1.0
verify-release/bin/samsarix-orchestration --version
verify-release/bin/python -c "import samsarix_orchestration as s; print(s.__version__)"
```

On Windows, use `verify-release\Scripts\python.exe` and the matching console-script path.
Verify the downloaded distribution against GitHub's attestation:

```bash
gh attestation verify samsarix_orchestration-0.1.0-py3-none-any.whl \
  --repo Deathcharge/samsarix-agent-orchestration
```

Record the release URL, immutable tag and commit, workflow run, PyPI URL, artifact hashes,
attestation verification, clean-install output, and rollback disposition in the release
notes and `docs/PRODUCTIZATION.md`.

## Failure and rollback

- If build, metadata, boundary, attestation, or publishing checks fail, do not approve or
  retry blindly. Correct the source on a new commit and release a new version.
- If only PyPI authentication fails, correct the Trusted Publisher configuration and rerun
  the failed publish job; the successful build and immutable GitHub assets remain unchanged.
- PyPI files and released versions cannot be replaced. Yank a bad version on PyPI, mark the
  GitHub release as affected, and publish a fixed version; do not move or recreate its tag.
- A yank discourages new installs but does not erase existing copies. Document any security
  impact through the private reporting path in `SECURITY.md` before public disclosure.
- Never add an API token as a shortcut around a Trusted Publisher mismatch. Verify the exact
  owner, repository, workflow filename, environment, and tag policy instead.
