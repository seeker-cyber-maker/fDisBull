# Python package distribution (prepared, not published)

This is a maintainer runbook for `.github/workflows/publish-pypi.yml`.
Merging this workflow does not publish a package. There are no tag, release,
push, pull-request, or scheduled publication triggers. `validate` is the default
manual operation and never uploads. No API token is needed: the upload jobs use
[PyPA Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## What users will install after publication

```sh
python -m pip install fdisbull          # Python 3.12+
fdisbull --help
python -m pip install fdisbull-player   # Python 3.10+, standalone player
fdisbull-player --help
```

These are intended commands, not a claim that the projects are already on PyPI.
Each project gets a wheel and source distribution. The core package declares
iced-x86, Capstone, LIEF and Pillow; `fdisbull[managed]` and `fdisbull[proof]`
add the optional managed-code and proof dependencies. The player has no core
dependency and consumes authored projections or compatible endpoints.

The packages contain no game/story files, saved states, project databases,
DOSBox, QEMU, Wine, offline kit or backend source-companion archives. Native
backends and user inputs remain separately prepared. A `py3-none-any` wheel
describes this package's Python code; it does not establish dependency-wheel or
backend availability on every platform. macOS remains unverified.

## Blockers before any upload, including TestPyPI

The license is not settled in this preparation change. The requested direction
is PolyForm Noncommercial source-available licensing, not an OSI open-source
license. The legal licensor identity and approved license text still need to be
settled by the owner; this PR supplies neither. A separate reviewed license
change must add accurate metadata to both projects and include the approved
license/notice files in both wheels and source distributions. Update the package
content checks/allowlists as needed and inspect the actual artifacts. Do not
mark readiness solely because these instructions exist.

Until that is done, leave repository Actions variables `PYPI_LICENSE_READY` and
`PYPI_PUBLISH_ENABLED` unset (or `false`). An upload selection fails unless both
are exactly `true`, and both manifests have nonempty license metadata. This
metadata check is an additional guard, not legal validation. Setting the
variables, creating accounts/trust, configuring environments and uploading are
separate owner-authorized actions; this preparation does none of them.

## Account and publisher setup (separate step)

1. The owner signs in to or creates their own PyPI and TestPyPI accounts, verifies
   email and completes required account security. Never share passwords or
   recovery codes with an agent.
2. Configure two GitHub environments, `pypi` and `testpypi`, in this repository.
   Require a reviewer, prevent self-review, and restrict deployments to `main`.
   Confirm the repository/account plan supports these protections before enabling
   uploads; if approval protection is unavailable, leave publication disabled.
3. Register pending publishers for both projects on each index (four bindings),
   or normal publishers if the owner already controls an existing project:

   | Index | Project name | Repository owner | Repository name | Workflow filename | Environment |
   | --- | --- | --- | --- | --- | --- |
   | PyPI | `fdisbull` | `seeker-cyber-maker` | `fDisBull` | `publish-pypi.yml` | `pypi` |
   | PyPI | `fdisbull-player` | `seeker-cyber-maker` | `fDisBull` | `publish-pypi.yml` | `pypi` |
   | TestPyPI | `fdisbull` | `seeker-cyber-maker` | `fDisBull` | `publish-pypi.yml` | `testpypi` |
   | TestPyPI | `fdisbull-player` | `seeker-cyber-maker` | `fDisBull` | `publish-pypi.yml` | `testpypi` |

   The publisher form takes the filename, not `.github/workflows/` plus filename.
   PyPI and TestPyPI have independent accounts/projects/trust. A public project
   lookup returning 404 does not guarantee a name can be registered. Stop if a
   name is unavailable and review a consistent package/workflow change first.
4. After the approved license is packaged and protections/trust are verified,
   explicitly authorize enabling the two repository variables above. Do not add
   long-lived PyPI tokens or `skip-existing` to work around a failed setup.

## Release procedure

1. Integrate the approved changes through the normal review process. The two
   manifests and `src/fdisbull/__init__.py` must have the same stable version.
   A release commit requires ordinary and required-native Linux CI on its exact
   SHA before tagging, as specified in `AGENTS.md`. Version/tag/release creation
   remains a separately authorized operation; this workflow creates none.
2. Once an existing `vMAJOR.MINOR.PATCH` tag points to that exact tested main
   commit, dispatch **Prepare or publish Python packages** from `main`, with
   `tag`, the full lowercase 40-character `source_sha`, and `target: validate`.
   The dispatched main SHA must equal the requested SHA and tag. If main moves,
   prepare a new release commit; this workflow cannot publish historical refs or
   arbitrary input refs. It requires successful latest trusted `ci.yml` and
   `native-debugger.yml` runs on that SHA (push/manual runs, not PR merge runs).
   If a required run was skipped by path filters, run that CI workflow manually
   on the exact main commit before advancing main.
3. Review logs and the `tested-python-packages` artifact. The unprivileged build
   job runs tests, builds/checks both wheels and sdists, installs the exact wheels
   into clean environments, runs pip check, CLI and bundled-skill smoke checks,
   then hashes the four artifacts. No offline kit or tool ZIP is uploaded to an
   index. Ordinary CI also checks both source distributions on PRs.
4. With explicit upload authorization, dispatch `target: testpypi`, approve the
   `testpypi` environment, and inspect both projects. Only the upload jobs receive
   OIDC permission. They download artifacts from their own run, verify hashes,
   and publish without checking out or executing repository source. Each project
   has its own upload job/publisher; the two-project upload is not transactional.
5. After reviewing TestPyPI results, obtain production publication authorization,
   dispatch the same source/tag with `target: pypi`, and approve `pypi`. This run
   rebuilds and tests its own artifacts; it does not silently promote an artifact
   from a different run. Verify the printed hashes against the resulting files
   on PyPI and verify installation in a fresh environment after publication.

Package versions on an index cannot be overwritten. If a job partially uploads,
inspect the index before retrying; do not silently skip duplicates. Resolve the
partial state with the owner and usually a newly reviewed version. Leave
publication disabled if license, CI, approval protection or trust is uncertain.

Official references: [PyPA GitHub Actions publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/),
[PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
