# macOS prototype loop and Boat Linux CI

Use macOS to integrate and try a change. Run focused checks for the behavior
being changed, adjust the implementation, and inspect the combined diff. Do not
run the complete suite after each local edit. When the candidate is ready,
commit one clean SHA and qualify it on Boat. Full Linux CI and release builds
belong there; release publication remains a separate authorized action.

## First qualify the host

Use the existing Boat CLI login without copying credentials into the checkout,
worker receipt, Docker environment or reports. Start only the explicitly chosen
worker size and plan. The trial allows Default workers, has a two-hour maximum
auto-stop window, and cannot create Large workers. Ending the trial or changing
billing needs the user's decision.

Before a full run, check actual Linux x86-64 identity, Python versions, Docker,
free disk space and the read-only/network-isolated consumer controls. Then run
bounded authored DOSBox and Wine/QEMU probes covering input, capture and native
restore. Keep observations separate from platform marketing and from full CI.
A failed probe is retained and diagnosed before retrying a changed fixture.

Our QEMU launch currently selects TCG. Availability of `/dev/kvm` does not switch
the debugger to KVM, establish its compatibility or prove a speed improvement.
Measure performance only after compatibility is established.

## Exact-source execution

`scripts/ci/boat-linux.py` runs on the already provisioned Boat Linux host using
Docker. It does not create a worker, log in, register a GitLab runner, change
billing, automatically delete data or publish a release. The Mac remains the
interactive development and orchestration surface.

The controller supplies a small `fdisbull-boat-worker-v1` JSON receipt with
`execution_origin: boat-linux`, the actual `boat_sandbox_id`, `type`,
`architecture: x86_64`, current kernel `host_boot_id` and timezone-qualified
`observed_at`. Read the worker's actual Boat metadata and host boot identity;
do not infer them from a name. The executor binds that file by hash into its
run and phase records. It refuses resuming on a different worker boot, source
or receipt. It records image-index and actual Linux AMD64 platform digests
separately. Local and Boat execution never acquire invented GitLab job IDs.

### Automatic stop for the whole CI session

For a complete run, use `scripts/ci/boat-session.py` from the authenticated Mac.
This is the outer lifecycle controller; `boat-linux.py` remains the low-level
phase executor. The session controller always selects `all`, including the final
qualification check, and stops once after the whole command finishes or fails.
Do not put a VM-stop hook around each individual phase.
The low-level `all` command requires the session context supplied by this
controller, to catch accidental unattended launches without automatic shutdown.

The worker must already be running by an explicitly authorized action. The
controller never starts/resumes a VM, extends its running window, changes its
size or billing, deletes data, or forces a stop. The worker is currently held
stopped; adding this launcher does not authorize another run.

```sh
# On the Mac, only when another CI run is authorized and the worker is ready:
python3 scripts/ci/boat-session.py \
  --worker bx_EXPLICIT_WORKER \
  --source /home/user/fdisbull-ci/source-COMMIT \
  --output /home/user/fdisbull-ci/runs/COMMIT-01 \
  --worker-receipt /home/user/fdisbull-ci/controls/worker-COMMIT.json \
  --commit FULL_40_CHARACTER_COMMIT \
  --receipt /Volumes/CODEX/Codex_Projects/fDisBull-targets-private/CI-SESSION.json \
  -- --dosbox-upstream-archive /home/user/fdisbull-ci/inputs/dosbox-x-upstream.tar \
     --dosbox-upstream-sha256 VERIFIED_SHA256
```

Pass the retained OS/QEMU inputs and capability requirements after `--` as for
the low-level executor. The session controller does not relax storage admission
or create missing source/worker/input receipts. Run it as one finite background
controller with a durable log when leaving the interactive chat; no model or
agent needs to poll its progress. The Mac must remain online. Its interruption
handler tries to finalize the owned run before stopping; a killed controller
or loss of connectivity is not a proven shutdown. Boat's existing provider
auto-stop window remains the independent backstop, and is never extended here.

Before execution, the controller verifies snapshots are enabled and
delete-on-stop is disabled. It refuses excluded/cache result paths, symlink
escapes, unreviewed snapshot ignore files (including old ignore filenames),
and other running Docker workloads. Logs, packages, native exports and partial
results stay under the persistent `/home/user` run directory. On termination,
the finalizer waits for the recorded CI process to exit, confirms Docker jobs
are stopped and flushes evidence to disk. It retains every file and container.

After finalization it requests a normal `boat stop`, then reads back the
stopped state, snapshot availability and fresh completed/verified snapshot
timestamps. The local lifecycle receipt records the CI outcome, preservation,
and shutdown separately. A successful stop does not turn failed CI into a pass.
The existing notifier reports whole-CI failure; an unconfirmed shutdown also
attempts a signed `ci-shutdown` alert to Dot. If results cannot be finalized or
retention becomes unsafe, the controller refuses a destructive stop and reports
the failure instead of sacrificing evidence. It never retries CI automatically.

Boat's automatic stopped snapshot keeps the disk, not process memory. Its
documented retention is at least 14 days; it is not an indefinite archive.
Longer-lived saved snapshots and external result archives are separate actions.
See [stop semantics](https://docs.boat.dev/snapshots/stop) and
[snapshot contents](https://docs.boat.dev/snapshots/whats-saved).

```sh
# Low-level phase commands are for deliberate diagnostics, not unattended runs:
python3 scripts/ci/boat-linux.py --help
python3 scripts/ci/boat-linux.py \
  --source /home/user/fdisbull/source \
  --output /home/user/fdisbull/runs/CANDIDATE \
  --worker-receipt /home/user/fdisbull/controls/worker.json \
  --profile ordinary
```

Continue the same SHA/run with `stable`, `layers`, `unified-prepare`,
`chat-prepare`, `chat-consumer`, `unified` and finally `qualify`. `all` performs
those phases in order. The ordinary job tests and checks the actual packages;
required native phases have zero allowed skips. Original compiled input reuse
retains its original build identity and does not replace current acceptance.
Boat-built DOSBox inputs also retain the original worker/run/process and clean
source-export proofs; a new shallow checkout cannot stand in for that build.
The kit QEMU wrapper passes its firmware path explicitly because the private
ELF loader changes executable-relative directory discovery.

The driver admits each material phase against actual output/Docker filesystems,
without adding figures from the same device. Estimates are conservative;
`--expected-bytes` is an explicit estimate, not a way to evade admission. Retain
logs and selected exports before any separately approved cleanup. A failed run
cannot be reused for a changed commit. GitLab and local-hub must both receive
the source refs with automatic provider CI suppressed.

## Offline kit and persistence

The complete chat kit is a single bounded archive, independent of repository
access. Its fresh consumer receives the archive and bootstrap only; source and
extra runtime mounts are absent. The kit must actually supply its Python,
dependencies, DOSBox, Wine/QEMU, firmware, kernel and player and pass with network
access disabled. A prepared build image is not proof of a complete delivery.

Keep working evidence and reusable inputs in explicit persistent directories.
Boat stop/resume preserves selected disk state, not running processes or memory;
`/tmp`, default tool caches and Docker build cache are not persistent snapshots.
Keep screenshot/trace exports outside a mounted DOS input folder: a new file
there correctly invalidates a checkpoint's input-file identity.
Save a debugger checkpoint explicitly before ending an interactive investigation,
and verify the checkpoint receipt. Keep games, saved states and project databases
in private workspaces, outside Git and exported tool packages.

Official references: [machines](https://docs.boat.dev/machines),
[trial](https://docs.boat.dev/free-trial), [CI](https://docs.boat.dev/ci),
[snapshot contents](https://docs.boat.dev/snapshots/whats-saved).

## Current candidate preservation

Boat uses `boat_support.py` to extend the local runner with explicit Boat and
chat producer/consumer identities. The local pinned DOSBox archive and retained
OS/QEMU provenance gates remain in force. Do not replace newer source, native
selectors or Windows capability checks with an older donor script. Reused
components keep their original identities; every candidate acceptance is fresh.

The full Wine runtime is required for the chat kit. A kit can be up to 2 GB,
with a 4 GiB extracted archive limit and a separately hash-bound 6 GiB expanded
guest base limit. Each chat phase admits a conservative 32 GB allocation by
default, including intermediate images and evidence. Actual growth and input
sizes must still be inspected before choosing an explicit override. A failed
admission preserves the attempt and never lowers the reserve automatically.

For attachment limits, `scripts/chat_offline_parts.py split` creates an ordered
set (250 MB per part by default) and a checksum manifest. Deliver the helper and
all listed parts together. `reassemble` verifies every part and the whole archive
before the ordinary kit verifier runs. A missing part is an incomplete delivery.
No repository access or dependency downloads are part of that consumer route.

Run the installed notification wrapper on Boat around the finite CI driver to
report failures to the user's subscribed Dot. Do not wrap only a detached Boat
launcher, which exits before the work completes. Keep private signing settings
outside the checkout and package. Routine progress stays quiet; a notification
receipt is not CI qualification. No automatic retry, cleanup or release follows
an alert.

The compact DOS/PE64 base and the full Windows base are included separately in
the chat kit. `bin/prepare-runtimes --cache PATH` reconstructs compact images;
`bin/prepare-runtimes --windows --cache ANOTHER_PATH` reconstructs the larger
Windows image. Use its explicit 8 GiB guest configuration and retain host memory
headroom. The isolated kit consumer verifies both reconstructions and exercises
DOS and PE64; full Windows native results remain a separate required CI receipt.
Optional separately built engines retain their own platform and qualification
boundaries; a macOS engine executable is not a Linux backend.
