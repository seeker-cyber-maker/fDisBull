# Native CI dependency reuse

CI reuses dependency builds, never acceptance results. Both DOSBox profiles still
verify the pinned upstream checkout and complete patch on every run. Native tests,
offline-kit/source-companion/skill gates, and installed-wheel PE64, DOS and boot
acceptance remain required. Ordinary tests and package/privacy checks are unchanged.
Existing acceptance job names and 45-minute timeouts remain unchanged.

## Events and concurrency

Both workflows accept every push, PR and manual dispatch. Removing the native
workflow's path filters ensures a required PR check exists for documentation-only
changes and tag/release checks cannot disappear because of a path filter.

A small event-policy job skips expensive feature-branch **push** jobs only when
GitHub reports an open, mergeable PR from that exact repository/branch with the
same head SHA. PR events always run, including forks. Branches without a PR run
immediately; conflicting PRs, unknown mergeability, stale PR heads, API failures
and rate limits keep the push checks. A PR opened after the push policy ran can
therefore still produce one duplicate initial run. The public read API uses no
credentials or additional repository permissions. Its anonymous rate limit is a
remaining deduplication limit; failure favors coverage.

Main, `integration/**` and `release/**` branch pushes always run. Workflow
concurrency cancels superseded runs only for the same PR number or feature push
branch, independently for each workflow and event kind. Other PRs never share a
group. Main/integration/release pushes, tag pushes and manual runs use unique run
IDs and cannot cancel one another or the current release. Repository settings and
permissions are unchanged (`contents: read`); no `pull_request_target` is used.

## Exact dependency identities

`.github/ci/native-build.sh` holds the source pins and configure flags. The key
includes its complete bytes and the cache helper's bytes; DOSBox additionally
includes the complete profile patch and source manifest (including upstream
commit and patched source hashes). The QEMU archive URL, SHA-256 and version
are in the build script. Application commit/version and test results are absent
from the key, so application-only edits can reuse unchanged dependencies.

The identity also records OS release, runner image version, architecture,
workspace/data path, Python version and relevant Python build packages, the full
installed dpkg package/version inventory, compiler/linker identities, build-tool
paths and hashes, and relevant build environment values. This deliberately
invalidates conservatively on runner/toolchain/package changes. The two DOSBox
profiles have different keys. Native configure flags remain the previous flags;
QEMU additionally points its data directory at the bundled firmware directory.

Only exact action cache hits are admitted. Partial-key matches are deleted, no
`restore-keys` are supplied, and the restored identity must match completely.
Receipts record every payload file's hash, size and mode, the executable's dynamic
runtime library hashes, and producer commit/ref/run metadata. Missing receipts,
files or QEMU firmware, extra files, changed bytes/modes, symlinks, malformed
receipts and runtime-library mismatches reject and remove the payload, then build
again. These checks detect corruption and mismatches; they are not signatures or
a substitute for GitHub's cache isolation. Existing cache entries are immutable:
a corrupt entry may cause repeated rebuilds until it expires or its key changes.

Only main push jobs write `trusted-main-*`. PR and feature/integration/release
branch pushes write separate `isolated-<ref>-*` namespaces. PRs may read main's
exact cache first, then their own isolated cache. Tags and manual runs read only
the trusted-main namespace and do not save native caches. GitHub additionally
scopes PR-created caches to the PR merge ref, so they cannot be promoted into
main/tag builds. These rules follow GitHub's
[cache isolation rules](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching#restrictions-for-accessing-a-cache).
Untrusted PR code has no new secrets or elevated permissions.

DOSBox caches only the binary. Each current source checkout is still patched and
verified for source-companion generation. QEMU caches its executable and firmware,
not its build tree. QEMU preparation runs alongside the two DOSBox matrix entries,
with one build per input set; the final installed-wheel job waits for all three.
A tarred current-run artifact preserves executable modes and contains the build
identity; its transfer digest and current source SHA are checked before the
consumer validates the payload again. If a runner-image rollout changes runtime
libraries between jobs, the consumer rejects the transfer and rebuilds locally
before acceptance. No cache result counts as a passed test.

## Remaining Wine cost

Wine is installed from Ubuntu packages inside a digest-pinned base image; it is
not compiled from source. The package repositories are moving inputs. This change
continues rebuilding that rootfs and records its resolved package inventory.
It does not claim that Containerfile-only hashing pins the rootfs. A future Wine
cache needs a reviewed immutable package snapshot or image digest and the same
producer/consumer trust boundaries. No registry writes or new credentials were
added here.

## Verification and bounded hosted qualification

Local commands:

```sh
python -m unittest discover -s .github/ci/tests -v
actionlint .github/workflows/ci.yml .github/workflows/native-debugger.yml
bash -n .github/ci/native-build.sh
```

The contract suite exercises unchanged-input reuse, application-only changes,
patch/manifest/profile/source-pin/toolchain/package/architecture/OS/build-flag
invalidation, missing/corrupt/incomplete payloads, runtime ABI changes, real ELF
library receipts, symlink rejection, cold mode, event fallbacks, actual workflow
concurrency expressions, cache trust namespaces and retained acceptance files.
These are local/static checks, not observed hosted native acceptance or timings.

Use the normal draft PR run for one cold population/acceptance. For bounded warm
qualification, use one manual dispatch on the same ref with `cold_cache: false`
after a matching **main** cache exists. Manual runs intentionally do not consume
PR-isolated caches; before integration, one application/documentation-only PR
update can exercise that PR's isolated warm cache. Do not repeat matrices just to
collect timing statistics. A manual native-workflow dispatch with
`cold_cache: true` discards local payloads and disables all native cache restores
and saves while running the same acceptance suite. Pip's download cache remains
independent; this option qualifies native source builds, not network emptiness.

Compare build/miss versus validated-hit logs, receipt inputs, and acceptance
artifacts at each exact head. A warm DOSBox hit should remove the previously
observed 5–8 minute compile stage, minus small restore/hash overhead; QEMU's
compile stage should also disappear. QEMU parallel preparation reduces the cold
critical path from a sum toward the maximum of DOSBox and QEMU preparation.
These are estimates. Queue time, image/package churn, cold caches, rootfs builds
and fresh tests remain; no hosted speedup is claimed before observation.

Integrate this focused CI PR only after the current release's checks and release
work complete. Do not merge it into PR #55 to obtain its earlier evidence: any
new integration SHA must earn its own ordinary and required-native checks before
a future tag. PR #55 at `90e748c8bc6a4f068f9136f4d4ec989672421a03` is untouched.
