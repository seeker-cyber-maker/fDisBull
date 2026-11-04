# CI triggers and status coordination

fDisBull maintains **equal repository state** across local Git (`/Volumes/CODEX/Codex_Projects/fDisBull` and `local-hub` at `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git`) and GitLab (`gitlab` at `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project ID `88349936`) during the 30-day GitLab evaluation trial. **GitHub (`origin` / `seeker-cyber-maker/fDisBull`) is permanently retired and obsolete** (`remote.origin.pushurl` is locked to `RETIRED_GITHUB_DO_NOT_PUSH`, and `scripts/ci_status.py` blocks live refreshes against `seeker-cyber-maker/fDisBull`).

Agents are required to update **both** local Git and GitLab when landing or syncing branches and tags, while strictly preventing duplicate or unthrottled CI pipeline runs that could trigger provider abuse filters.

## Controlled execution and provider routing

Routine pushes, all merge requests and tags do not admit GitLab pipelines.
Use macOS for rapid prototyping and focused checks of affected behavior. Run
full Linux CI and release builds on explicitly started Boat workers against the
exact candidate SHA, using `scripts/ci/boat-linux.py`. See the
[Boat workflow](BOAT_CI.md). The retained Apple-container driver,
`scripts/ci/local-linux.py`, is a separately selected fallback. Inspect the
chosen driver's help and runtime preflight before starting; a missing prerequisite is incomplete,
not a passed gate. Use separate local execution identities and receipts. Local
results do not establish a GitLab pipeline or hosted CI success.

The retained GitLab workflow admits only explicit web/API pipelines. Every job
requires the `fdisbull-local-linux` runner tag, including the ordinary job; it
must never fall back to hosted instance runners. A dedicated runner would need
separate user authorization and setup before that route can run. No runner or
credentials are created by this policy. Native qualification remains behind a
blocking manual start. The provider summary is a legacy diagnostic for ordinary,
stable, layers and unified evidence; its status is `legacy-dos-only`, not full
qualification. The explicit Boat and Apple-container drivers run the complete chat consumer gate.
Source configuration does not prove runner registration or provider settings.

Apply the storage admission rules before image pulls, builds and each material
growth phase. Use bounded external workspaces and finite commands; a rejected
admission stops new bulk work. A local Linux run, including any emulation,
records its actual platform and must not be presented as hosted CI.

## Retained Apple-container fallback

The Apple-container driver uses the guarded `container` command on this Mac. It snapshots
a clean candidate into separate shallow Git clones, pins the pulled amd64 image
by digest, and retains logs, stopped containers and failed attempts. It admits
both the result filesystem and the CACHE container store before growth. It
never mounts the original checkout's Git credentials or private game directory.
The snapshot mount is read-only. Source, build, temporary and package-install
work uses the Linux guest filesystem, whose backing disk is in that admitted
external container store. Only selected regular evidence files cross back to
the writable host result directory; a guest postcheck must confirm the exact
commit and unchanged tracked source before a leg is completed. This avoids
depending on host-shared filesystem support for Linux links and sockets.

```sh
# Choose a new output directory beneath an existing authorized external parent.
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile ordinary
# Continue the same exact commit and run directory, deliberately, one leg at a time.
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile stable
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile layers
# Prepare the pinned QEMU/Wine/DOS inputs in the dedicated build worker.
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile unified-prepare
# Build and independently accept the complete offline chat archive.
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile chat-prepare
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile chat-consumer
# Recheck space; retain exports before any explicitly approved worker cleanup.
# This reuses the completed preparation from this exact source and run.
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile unified
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile qualify
```

`--profile all` starts seven stages in order: ordinary, stable, layers, unified
preparation, chat preparation, chat consumer, and unified acceptance. Heavy
work is never automatic on a push or MR. The default allocation estimates are
12 GB for ordinary, 14 GB for stable, 18 GB for layers, 35 GB for a fresh
unified preparation, 8 GB for each chat stage, and 16 GB for unified acceptance.
The destination reserve defaults to 40 GB and each worker has a two-hour wall
timeout. `--expected-bytes` explicitly overrides the estimate for each newly
executed stage. Choose a conservative estimate for the actual work; a bounded
local run may explicitly use the user-authorized 20 GB minimum. Completed
preparation does not reserve its compiler workspace again when resumed.
Storage is admission-only, not a running quota.
Inspect the retained log after failure; no automatic retry or cleanup occurs.
Do not overwrite a failed run or reuse it for a changed commit.

For a fixture/client-only correction, `--reuse-stable-backend` or
`--reuse-layers-backend` can explicitly select the matching profile's original
compiled leg's `guest-data/exported` directory. Each verifies the
binary hash and ELF architecture, original local build process/image, upstream,
patch, configure flags, and byte-identical current/source-commit manifests.
The original build identity/configuration records are retained unchanged and
`build_source_commit` stays distinct from the current qualification source.
Only C++ recompilation is reused: the complete current profile's test selection,
strict native checks, layers offline-kit checks and evidence export still run. A failed original test run
does not become a passing run through reuse. The pinned upstream fetch is
shallow; checked-out commit and patched-file hashes remain mandatory. Select the original compiled-leg export; an export from a previously reused leg is rejected so its later test commit cannot replace the original build provenance.

Synthetic checkpoint fixtures explicitly settle the video device before their
first target instruction and verify restored CPU, program/stack bytes and
keyboard state. This setup advances device time, not a whole-machine replay.
It is confined to authored test programs; production checkpoint calls still
refuse a pending video mode change and never silently execute the target.

Before native compiler work, establish the actual local Docker route with a
bounded daemon/build/create/start/copy/export preflight. On Apple Silicon,
unified preparation uses a native ARM64 guest VM for Docker and a pinned AMD64
child container for the actual compiler/preparation job. It records both image
digests and requires the child's Linux x86-64 runtime proof. The native daemon
avoids Docker re-execution failures observed under Rosetta; the AMD64 job and
Windows runtime remain translated or emulated as declared. The outer VM has
Linux capabilities for Docker, VFS storage and VM-local host networking for
dependency downloads. The child connects through a VM-local Unix socket; it
has no macOS Docker socket or credentials.

Acceptance then runs in a separate fresh AMD64 Linux worker with no Docker
daemon. It checks the preparation's successful stopped process, exact source/run,
distinct build job UUID, matching image, clean source/export, ordinary-tested
wheel, six runtime input hashes, packaged runtime resource hashes and the
pinned QEMU firmware inventory. It installs the verified firmware and wheel,
then executes the complete existing PE64 and DOS/boot selections. The final
qualification independently checks the preparation and acceptance evidence.
A successful build never substitutes for successful tests.

`--profile unified` performs missing preparation first or verifies and retains
completed preparation from this same source and run. The separate
`unified-prepare` command allows an explicit pause for storage review before
starting acceptance. Worker disks remain retained; inspect exported inputs,
logs and source receipts before requesting any irreversible cleanup. Failed
attempts are never overwritten or automatically retried. `--reuse-unified-base`
explicitly selects an original completed preparation export, checks its frozen
source, recipe, image and inputs, and retains the original compilation origin.
It regenerates runtimes with the current wheel and resources; all current native
and chat acceptance gates still run. Reuse does not make the original preparation
a qualified result. No persistent runner is registered. Missing
kernel, namespace, Docker or Rosetta support leaves that leg incomplete; do not
substitute another platform and claim the declared gate passed.

The final `qualification/qualification.json` binds the ordinary, stable, layers,
unified and chat receipts, preparation proofs, host process exits, run/job UUIDs,
image digests, test captures and package hashes. A zero process exit alone is not a completed leg; source checks and
artifact collection must also finish. A missing required capture never becomes
successful equality or qualification.

## Dual synchronization between local Git and GitLab

Sync only authorized refs with `scripts/sync_mirrors.py`; inspect its current
help and dry run before pushing. Its suppression options and workflow rules are
separate controls. The YAML prevents automatic pipelines for ordinary push and
MR events; GitLab push option `ci.skip` alone does not suppress an independent
MR pipeline. Existing refs with different source-branch configuration may have
different behavior. Never push an empty commit or resync every ref to request a
check. Tags and release actions require separate authorization.

## Candidate and package acceptance

The ordinary job derives a payload inventory from tracked runtime, player,
test and support files, then compares bytes in the wheel, player wheel, sdist
and tool ZIP. Newly added resources cannot disappear unnoticed because their
extension was absent from an older selector. Privacy/archive checks still run
separately. Built-wheel skills and isolated core/player/sdist/tool installations
are checked outside the source tree. Failure logs are retained. CI pins a
hash-verified Node 22.23.4 toolchain and checks real Web Crypto/WebAssembly
availability before the suite; a distro's older Node must not silently replace
the runtime used by the former workflow.

Cheap package and installed-skill checks run before the full suite, with a
final payload/privacy recheck afterward. The exact installed-package recipe
is `scripts/ci/package-smoke.sh`; local verification can reuse it with an
external `CI_BUILDS_DIR`, the real checkout in `CI_PROJECT_DIR`, and optional
`FDISBULL_CI_PYTHON`, `FDISBULL_CI_PACKAGES` and `FDISBULL_CI_RECEIPTS` paths.
It uses existing genuine dependencies and fresh environments, generates skill
receipts outside the checkout, and copies successful receipts into the selected
artifact directory. Local execution is a smoke check, not a hosted Linux result.

The required evidence covers ordinary, stable DOSBox, layers DOSBox and
installed-wheel PE64/DOS/QEMU/boot on the same exact source SHA. The layers leg
also verifies the offline kit. Missing, skipped, canceled, failed or wrong-source
required tests leave qualification incomplete. The local runner's receipts use
local execution identities, not fabricated GitLab IDs. The retained GitLab
`legacy-diagnostic` checks its pipeline and job identities only when that
explicit runner route actually executes; it cannot produce full qualification.

A local pass does not establish hosted CI and does not by itself authorize
merging, tagging, publication or installation. The exact-SHA Linux CI release
requirement in [AGENTS.md](../AGENTS.md) remains a separate release decision. Preserve exact artifact hashes and raw evidence.
See the [migration handoff](CI_MIGRATION_HANDOFF.md) for the historical baseline.

## One owner and a finite status command

Name one CI owner per repository before observing hosted checks. The owner
publishes the exact head, run IDs, observation time, terminal conclusions and
next permitted refresh time. Other agents consume that receipt and continue
independent work. They do not each refresh GitLab or GitHub.

From a source checkout, any agent can read the local receipt without network
access:

```sh
python scripts/ci_status.py --host gitlab.com --repo brewster-jennings-group/fdisbull --sha "$(git rev-parse HEAD)"
```

Only the named owner requests one refresh:

```sh
python scripts/ci_status.py --host gitlab.com --repo brewster-jennings-group/fdisbull --sha "$(git rev-parse HEAD)" --refresh --owner YOUR_CHAT_ID
```

The helper performs at most one bounded provider API request (`glab api` for GitLab or `gh api` for portable GitHub fallback) per invocation and has no watch, force or automatic retry mode. A repository-wide five-minute cooldown is reserved before network access, including failed requests. Cached results are separated by exact host, repository and full commit SHA. A different SHA does not bypass the repository cooldown. Receipts preserve their observation time; cached success is not a new live observation or a qualification verdict.

The resolved Git common directory shares the owner, lock, cooldown and cache across sibling local worktrees. `--state-dir` supports an explicitly selected shared directory or isolated verification.

## Failures and recovery

Missing runs, incomplete pages, mismatched SHAs, stale data and provider errors remain explicit. Inspect failed job logs once after a terminal failure; do not poll each matrix job while it runs. Do not combine this command with separate connector loops, `glab ci trace`, or `gh run watch`.

Authentication/access failures, rate limits, CI quota exhaustion and confirmed account restrictions stop refreshes through a persisted `provider_stop`. Do not repeatedly retry, change accounts/repositories, weaken checks or push empty commits to evade the condition. Resolve normal provider access first.

Do not start watchers, scheduled checks or monitoring services without a separate user request. Source fixes, CI qualification, review readiness, merging and releasing remain separate gates.

The local `all` route also requires `chat-prepare` and `chat-consumer` after
unified preparation and before unified acceptance. Each is a separate Linux AMD64 Python 3.13.5 container,
with an 8 GB default admission estimate. Preparation binds the same run's
ordinary packages, layers inputs, and verified unified preparation evidence;
the earlier unified preparation retains its own Python 3.12 image identity.
The consumer receives only the designated ZIP and small bootstrap control,
with no source checkout mount. It must run the verifier shipped in the archive
on a read-only kit in a network namespace with only loopback. Its source proof
is a host check of the frozen clone plus the archive identity, not a guest
checkout claim. Failed attempts and their partial evidence remain retained.
These local checks do not establish hosted CI, authorize a release, or install
anything. A single archive larger than 500 MB cannot qualify.
