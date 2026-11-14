# CI triggers and status coordination

The user selected original GitHub [`seeker-cyber-maker/fDisBull`](https://github.com/seeker-cyber-maker/fDisBull), repository ID `1431097789`, as the preferred source/review platform. The connected `TiGa-RCE` account now has Write access. `TiGa-RCE/fdisbull` is a distinct partial import, not the restoration target.

The guarded mirror service preserves original GitHub, local-hub and GitLab refs. GitHub and GitLab use separate durable histories and one outer lock. GitLab pushes retain `ci.skip`; GitHub/local pushes do not receive that option. Historical tag identities remain immutable. See [the restoration contract](GITHUB_RESTORATION.md).

**CI owner: n8n. The manual GitHub → OVH bootstrap passed on 2026-11-13.** [Run 43512305780](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/43512305780), attempt 1, completed successfully on runner `fdisbull-ovh-ca-gh1`; its artifact was independently verified and [handed back to PR #84](https://github.com/seeker-cyber-maker/fDisBull/pull/84#issuecomment-6865708771). Actions is enabled, `ovh-bootstrap.yml` is manual-only, and legacy workflow IDs `394106283` and `394474280` remain disabled. Its finite worker shares the OVH executor lock with GitLab and relinquishes the lock after owned-process cleanup. Pushes, PRs and tags do not automatically dispatch this workflow. Only n8n dispatches/observes jobs; other workers consume dated receipts.

This establishes infrastructure and artifact handoff, not application/native qualification. The real qualification checker rejected missing ordinary/native receipts and emitted `release_ready=false`. Existing exact-candidate GitLab/local receipts retain their own scope. QEMU qualification, the full offline consumer kit and release publication remain separate gates.

## Local-first workflow and provider routing

Routine pushes, all merge requests and tags do not admit GitLab pipelines.
Run ordinary and native qualification locally against the exact candidate SHA
using the finite local Linux runner, `scripts/ci/local-linux.py`. Inspect its
help and runtime preflight before starting; a missing prerequisite is incomplete,
not a passed gate. Use separate local execution identities and receipts. Local
results do not establish a GitLab pipeline or hosted CI success.

The retained GitLab workflow admits only explicit web/API pipelines. Every job
requires the `fdisbull-local-linux` runner tag, including the ordinary job; it
must never fall back to hosted instance runners. A dedicated runner would need
separate user authorization and setup before that route can run. No runner or
credentials are created by this policy. Native qualification remains behind a
blocking manual start and requires stable, layers, unified and summary jobs.
Source configuration does not prove runner registration or provider settings.

Use bounded external workspaces and finite commands. A local Linux run,
including any emulation, records its actual platform and must not be presented
as hosted CI.

The direct runner uses the guarded `container` command on this Mac. It snapshots
a clean candidate into separate shallow Git clones, pins the pulled amd64 image
by digest, and retains logs, stopped containers and failed attempts. It records
free-space and allocation estimates for the result filesystem and, when
separate, the CACHE container store. These figures are telemetry only. It
never mounts the original checkout's Git credentials or private game directory.
The snapshot mount is read-only. Source, build, temporary and package-install
work uses the Linux guest filesystem, whose backing disk is in that observed
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
# Continue the same run; retain exports before any explicitly approved worker cleanup.
# This reuses the completed preparation from this exact source and run.
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile unified
python scripts/ci/local-linux.py --output /Volumes/CACHE/AppleContainer/fdisbull-ci-CANDIDATE --profile qualify
```

`--profile all` explicitly starts the four qualification legs and their separate
unified preparation stage; heavy work is never automatic on a push or MR.
The default allocation telemetry is 12 GB for ordinary, 14 GB for stable,
18 GB for layers, 35 GB for unified preparation and 8 GB for unified acceptance.
`--expected-bytes` overrides the recorded estimate for each newly executed
stage. `--reserve-bytes` is retained for command compatibility and is recorded
only as telemetry. Each worker has a two-hour wall timeout. Completed
preparation does not repeat its estimate when resumed.
Inspect the retained log after failure; no automatic retry or cleanup occurs.
Do not overwrite a failed run or reuse it for a changed commit.

Local native legs require an explicit self-contained bare-Git archive through
`--dosbox-upstream-archive` and `--dosbox-upstream-sha256`. The host and guest
verify the archive, reject unsafe Git configuration, links and alternates, and
fetch only its pinned local commit. The local path refuses a network fallback.
Patched-source manifests and every declared source hash still have to match.

An explicit retained-component preparation route accepts
`--retained-base-manifest`, `--retained-base-sha256`, `--retained-base-root` and
`--retained-os-base`. It verifies the original QEMU/kernel/firmware and OS
component identities and build provenance, then removes earlier project
resources and creates fresh overlays from this candidate's installed wheel.
It does not reuse a foreign prepared-input manifest or its test outcome. Its
allocation estimate measures the compressed immutable stream, bounds current
resource growth and retained copies, and includes worker dependencies.

For the reviewed Windows lane, supply `--retained-windows-fixtures` and require
`wine64`, `dos`, `pe32` and `win16-guards` capabilities explicitly. The fixture
directory contains exactly the hash-bound authored selector program, declared
generated Snake program and INITIAL.BIN. Preparation retains a smaller Wine64
and DOS base, plus a separate Wine 11 image for the 8 GiB Windows tests. The
fresh acceptance worker verifies all three images and current resources. Its
combined PE report must include passing PE32, selector, Snake and three-case
campaign testcases; missing, duplicate, failed or skipped cases cannot qualify.
Original Windows and replacement-engine checks remain distinct.

The ordinary job separately requires all 22 typed-return cases and four
semantic-event contracts with zero skips, including actual Linux callers and
Unicorn-backed adapters. Optional backend skips in the broad ordinary suite do
not waive these required cases.

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
attempts are never overwritten or automatically retried. There is no cross-commit
unified-runtime reuse. No persistent runner is registered. Missing
kernel, namespace, Docker or Rosetta support leaves that leg incomplete; do not
substitute another platform and claim the declared gate passed.

The final `qualification/qualification.json` binds all four leg receipts and
their host process exits, run/job UUIDs, image digests, test captures and package
hashes. A zero process exit alone is not a completed leg; source checks and
artifact collection must also finish. A missing required capture never becomes
successful equality or qualification.

## Legacy local/GitLab helper

Use the installed guarded three-way service for normal propagation. Push an ordinary source branch to `origin` or `local-hub`; the service preserves the other endpoints. The legacy `scripts/sync_mirrors.py` helper is only for reviewed local/GitLab operations. Do not use the old `dual` command or pass `ci.skip` to GitHub/local-hub. Manual GitLab pushes require `-o ci.skip`.


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
`qualify-candidate` validates GitLab pipeline and job identities only when that
explicit runner route actually executes.

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

## Finite agent waits and controller handoffs

Reviewers must not remain active solely to wait for another CI chat. Read the
owner's existing receipt first. At most one bounded chat wait of up to 60 seconds
is appropriate for an imminent result; do not renew it merely because the owner
is active or its cursor changed. If the required result is unavailable, publish
the completed review, name the missing evidence and its owner, and end the turn
or continue independent authorized work. Resume review when concrete new evidence
is available. This rule does not stop an authorized finite worker or replace the
existing n8n service with a chat-based polling loop.

The CI owner maintains one durable current-state handoff in the existing control
records. Include the incident, run and attempt, exact application and workflow
commits, owner, current stage, last substantive progress time, stage deadline,
next action, blocker and paths to retained results. Repeated status reads and
additional passing test counts are not substantive progress by themselves.

Controller stages need finite deadlines and explicit success, failure or
attention outcomes. A timeout must retain the original action intent and evidence;
it must not authorize replay of an uncertain mutation. A completed job must not
leave an idle holder retaining the executor indefinitely. Before releasing or
transferring ownership, reconcile live workers and unresolved actions under the
existing executor protocol. Report controller attention through the existing
deduplicated notification route, including failures before job-evidence capture.

When a verifier rejects a completed export, preserve it and correct the verifier
against that real evidence without weakening failure detection. Reuse the export
where source identity and completeness remain valid; do not rebuild merely to
repair receipt interpretation. Record operator-assisted reconciliation separately
from automatic recovery. A fix, a successful rehearsal and a recovered production
incident are distinct outcomes. These are required behaviors, not a declaration
that the current deployment has passed them.
