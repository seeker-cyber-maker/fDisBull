# Local hub and GitLab mirror service

The optional user LaunchAgent reconciles the local bare hub and GitLab on a
one-minute schedule. A local push to the hub also writes a wake signal so the
service can start sooner. The hook only drains its input and touches that
signal; it does not run Git, wait for the network, or block a successful push
when the signal cannot be written. The worker runs separately, under a single
local lock. This is a Git service, not a scheduled model or Codex automation.

The worker synchronizes eligible refs only when the destination can advance
without losing history. It holds divergent refs, deletions and other conflicts
for explicit review. It does not update a checked-out worktree, replace history,
resolve a conflict, or trigger CI; GitLab updates use the configured CI-skip
option. The first setup establishes a baseline, so pre-existing unequal or
missing refs are not implicitly interpreted as a new deletion. The service can
catch up after an offline period on a later scheduled run; the one-minute
schedule is not a delivery guarantee.

Each push uses an exact expected-destination lease, including an empty expected
value for a new ref. The ancestry check still requires an existing branch to
advance without losing history; the lease rejects an absent or different
destination value at push time. It cannot detect deletion and recreation at
the identical object ID between observations. Before either creation or update, the
worker durably records the intended and observed values. A lost reply or
interruption cannot become a blind recreation or repeated update: an absent,
changed or unconfirmed outcome is held for explicit review. A branch-specific
push failure leaves other eligible refs free to progress. Ordinary conflicts
can resume after their histories are reconciled; deletion and uncertain-create
holds require deliberate review of the retained per-ref state.

GitHub is inactive following the user's reported account flag. The service
contacts only the configured local bare hub and GitLab. It never fetches,
pushes or polls `origin`, and it does not update active working checkouts.

The service uses the existing local hub and a separate independent bare
transport cache. The cache lives on CODEX under
`/Volumes/CODEX/Codex_Projects/active/fDisBull-mirror-sync/transport.git`,
with its own identity marker. It is not a shared-object checkout or an
alternate-object reference to the hub. It preserves objects needed for
reconciliation without making the hub depend on it. Neither service operation
nor disable deletes the cache or rewrites active worktrees.

## Storage behavior

Reserve-based admission was removed by user direction on 2026-11-14.
Free-space values and legacy storage helper failures do not stop mirroring.
Legacy storage options remain accepted for upgrade compatibility and have no
admission effect. New configurations explicitly record `storage.mode: none`.

Mounted-volume UUIDs, repository identities, global and per-peer locks,
fast-forward ancestry checks, tag preservation and bounded command deadlines
remain enforced. Missing or substituted volumes still stop the worker before
Git operations. Fetch-time automatic maintenance remains disabled. The service
never deletes caches or user files to recover space; actual I/O failures are
reported as errors while preserving reconciliation state for recovery.

## Preview and install

The installer is read-only unless `--apply` or `--disable` is specified:

```sh
python3 scripts/install_mirror_sync.py
python3 scripts/install_mirror_sync.py --apply
```

The preview validates the expected mounted volume identities, bare hub, hook,
local Git configuration and destination files, then prints the proposed paths
and worker configuration. It refuses an unrelated existing post-receive hook
or custom `core.hooksPath` rather than replacing it. Use the full `--help` for
explicit path, executable and volume arguments in a different installation.
The installer preserves the previous local `receive.denyCurrentBranch` value
in its manifest and sets it to `refuse`; it leaves
`receive.denyNonFastForwards` unchanged.
Apply and disable acquire the worker's same nonblocking lock before changing
managed files. A busy worker or changed installation manifest refuses the
update. The installed checker and configuration are hash-bound in that manifest.

`--apply` copies the standalone worker and writes its configuration and
rollback manifest to `~/.local/state/fdisbull-mirror`, installs the wake-only
hub hook, and writes the user plist under `~/Library/LaunchAgents`. That
internal plist location is intentional: launchd must be able to read it on
this Mac. The installer neither starts launchd nor initializes the cache, fetches
refs, pushes, or changes credentials. Once the apply result is reviewed,
initialize the worker, then explicitly load and trigger the service:

```sh
python3 ~/.local/state/fdisbull-mirror/runtime/mirror_sync_service.py \
  --config ~/.local/state/fdisbull-mirror/config.json --initialize
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/org.fdisbull.mirror-sync.plist
launchctl kickstart "gui/$(id -u)/org.fdisbull.mirror-sync"
```

Use the configured absolute Python executable from the installation preview
if `python3` above is not the intended runtime. Initialization requires the
external volumes to be present with their configured UUIDs. The worker owns its
external cache marker, baseline and status; the installer does not manufacture
a successful initialization receipt. Review expected disk use before
initializing or growing a substantial new cache.

## Observe and disable

Inspect `~/.local/state/fdisbull-mirror/status.json` for the worker's latest
receipt, including held refs or errors, and use `launchctl print
"gui/$(id -u)/org.fdisbull.mirror-sync"` for launchd state. Check actual refs on
both sides before treating a sync as complete. A successful wake or an elapsed
minute alone is not proof that a remote update landed.
The latest run ID and timestamp are retained in `refs.json`. Expected external
volume UUIDs are checked on each run; missing or changed mounts stop external
writes and update only the already-existing internal status location. The
transport cache's immutable archive refs retain fetched tips on both sides.

To stop and remove the managed activation, first unload the user job, then
run the installer disable operation using the same path arguments as install:

```sh
launchctl bootout "gui/$(id -u)/org.fdisbull.mirror-sync"
python3 scripts/install_mirror_sync.py --disable
```

Disable checks that the hook and plist still match the installation manifest
and that `receive.denyCurrentBranch` still has the managed value. It removes only matching managed files created by the installer, retains any
identical files that were already present, and restores the saved value. It
refuses for manual review if ownership or configuration changed. Runtime files, status,
manifest, and the external cache are retained. If an earlier apply did not
finish, inspect the manifest and the local hub configuration before manually
recovering; do not delete object storage as a repair step.

## Local activation evidence, 2026-11-11

The user-authorized Mac installation uses a stable worker copy, system Git,
the configured Python interpreter, and the 60-second user LaunchAgent. Initial
cache setup was read-only. The first live sync copied six GitLab-only branches
to the hub and one hub-only branch to GitLab, with no holds or errors.
Commit `9de519c497fd550c7273aab52a71ccb85d82f26d` was then pushed only to the
hub; the service propagated it to GitLab and both endpoints reported 681
matching refs. The hub receive hook changed the wake file without network work
in the push path. Local source checks passed 52 tests plus the separate
concurrent-readback archive witness. No CI was run. These are bounded local
checks; later operation must still be read back from the current status and
actual repository refs.

## Concurrency and storage correction, 2026-11-11

Three isolated regressions first reproduced stale pushes overwriting a
destination deletion, rewind or competing creation. Exact destination leases
and durable update intent now preserve those concurrent results across a fresh
worker run. Additional witnesses cover lost acknowledgments on existing refs,
storage denial before initialization/transfer/publication, invalid capacity
receipts, and locked installation updates.

The final focused source command covered `test_mirror_sync_races.py`,
`test_mirror_sync_storage.py`, `test_mirror_storage_admit.py`,
`test_mirror_sync_service.py`, `test_install_mirror_sync.py` and
`test_sync_mirrors.py`: **72 passed**, with no skips. The real host admission
check refused growth because internal storage was below 20 GB and the separate
hub container was below its destination reserve. That is a storage hold, not
a passing propagation result. Restore capacity before normal synchronization;
the installer can replace the small control payload without reinitializing
the retained reconciliation baseline. No hosted CI was run for this correction.

The historical storage-denial witnesses below describe the former policy;
current tests verify mirroring without capacity admission.
