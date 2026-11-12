# Private Drive library synchronization

As of November 11, 2026, the updated local synchronization service is installed
and enabled. Its initial library transfer remains in progress and is not yet
qualified as complete; retained partial uploads are not completion evidence.
The current intake plan contains 7,350 files and 5,063 distinct objects; these
are scope counts, not verified upload progress. A newly added authored FDB was backed up automatically by the installed
watcher/worker and downloaded successfully with all three referenced objects,
verified hashes, SQLite integrity and an isolated Project reopen. A separate completed
FDB generation was downloaded from Drive and restored locally with all nine
referenced objects and a successful SQLite integrity check.

The service is one-way: the local intake library and private FDB repository are
the sources, and the [private fDisBull-Sync Drive folder](https://drive.google.com/drive/folders/14q0TFwF42EQ5ux5cQ007rr-Woc7C_mRG)
is the destination.

The current local setup uses:

- Configuration: `~/.local/state/fdisbull-drive-sync/config.json`.
- Local wake marker: `~/.local/state/fdisbull-drive-sync/wake`.
- Separate private mode-0600 rclone OAuth configuration:
  `~/.local/state/fdisbull-drive-sync/rclone.conf`.
- Active worker and watcher runtime: `~/.local/state/fdisbull-drive-sync/runtime/`.
- Inspectable versioned service payload:
  `/Volumes/CODEX/Codex_Projects/fDisBull-fdb-private/service/v1-20261111/`.
- Private state, snapshots, receipts and logs:
  `/Volumes/CODEX/Codex_Projects/fDisBull-fdb-private/sync-state/`.
- Agents: `org.fdisbull.drive-sync.watcher` and
  `org.fdisbull.drive-sync.worker`; the worker uses a 60-second interval and
  watches the marker. Confirm launchd state and the latest receipt before
  calling either process operational. An installed plist alone is not proof of
  a running watcher, an authorized remote or a successful backup.

The authorized Drive configuration is **separate** and uses `drive.file`
scope; it does not alter the existing encrypted rclone configuration. Keep
OAuth config private; do not print tokens or place them in
command arguments, logs, source control or status receipts. If authorization,
mount identity or verification fails, retain the existing copies and report a
failure. No password from the existing encrypted rclone configuration is needed
for this separate setup.

This setup currently uses rclone's shared Google Drive client ID. Rclone says
that ID will stop working during 2026; creating and authorizing a dedicated
Desktop OAuth client is a follow-up, not an indefinite guarantee for the present
grant. A new client's per-file access to the existing folder must be verified
before switching. See [rclone's own-client guidance](https://rclone.org/drive/#making-your-own-client-id).
One bounded diagnostic received Google Drive HTTP 403 `quotaExceeded`. A new
Google Cloud project could not be created because the account reached its
project limit; no existing project was changed. The choice between an existing
project, resolving the limit, or temporary shared-client use remains open.

## Scope and local wake-up

The configured intake selection covers targets, receipts, shared media, discs,
sources and the selected library-root metadata. It excludes analysis, CI and
runtime archives. Symlink targets are recorded as metadata only: external
installer or linked bytes are not followed or silently uploaded. The FDB
repository includes its projects and explicit registrations. Older analysis
FDBs outside that repository are not automatically imported; register them
explicitly if they are to be captured. The KQ1 seed's verified cloud restore is
bounded to that one FDB and its nine referenced objects.

The compiled Swift helper watches admitted roots using FSEvents. It writes a
local marker within a three-second coalescing window from the first event,
including on startup; it does not
read credentials or contact Drive. A nested-file wake was observed in the local
watcher test. FSEvents are hints, not an ordered transaction log: each worker
run reconciles the admitted selection, and the one-minute interval supplies a
fallback for missed notifications. Roots, aliases and mount identity must be
checked before copying. Google Drive webhooks signal **remote** changes and
require an HTTPS receiver and change-feed reconciliation; they are not needed
for this local one-way wake path. [Apple's FSEvents guide](https://developer.apple.com/library/archive/documentation/Darwin/Conceptual/FSEvents_ProgGuide/UsingtheFSEventsFramework/UsingtheFSEventsFramework.html)
describes coalesced and dropped events.

For a manual, read-only source plan or local status, use the versioned worker:

```sh
PY=/Users/tiga/miniconda/bin/python3
WORKER=/Users/tiga/.local/state/fdisbull-drive-sync/runtime/drive_library_sync.py
CONFIG=/Users/tiga/.local/state/fdisbull-drive-sync/config.json
"$PY" "$WORKER" plan --config "$CONFIG"
"$PY" "$WORKER" status --config "$CONFIG"
```

To include an older FDB outside the repository, register its exact path and
the private object-store root that contains its referenced objects:

```sh
"$PY" "$WORKER" register --config "$CONFIG" \
  --path /private/analysis.fdb --objects-root /private/target-objects
```

Registration records an input; it does not itself prove a backup. Supply
additional `--objects-root` options if the project's objects span stores, and
verify the subsequent generation receipt.

The installed worker invocation is `run --config` with the same paths. Multiple
wake-ups are serialized by the worker lock. Inspect its structured receipt and
errors; a wake, plan or launchd exit is not a transfer confirmation.

## Preservation and verification

The installed library layout stores new content under
`library/objects/<sha256>` and binds each entry in a completed namespace
manifest to its exact `content.remote_path`. Later edits create new content
objects, preserving those referenced by earlier manifests, so a completed
generation can identify its exact restorable payload set. Existing uploads under the earlier
`library/files` layout are retained read-only; older cached receipts may still
reference them. New payloads use the content-addressed layout. Source deletions
are not propagated as remote deletions.

A successful transfer requires Drive size and MD5 readback for every submitted
file; missing or mismatched hashes refuse completion. A transfer or manifest
failure must not advance local success state. The worker runs the FDB phase
before the library phase and records phase errors separately, so a library
failure does not prevent an independent FDB attempt. Inspect each run's receipt
for the actual outcome of both phases.

Each FDB is a separate fresh generation, rather than a copy of its live file.
The worker uses SQLite online backup to capture committed WAL state, then
collects and SHA-256 verifies the recursively referenced external objects. It
uploads and verifies the snapshot and objects first; `manifest.json` is the
last completion artifact. The manifest records hashes and sizes for
`project.fdb` and its `objects/` closure. The scope is the snapshot and
referenced objects; backend runtimes, source media and other external files are
not automatically included. Missing or corrupt referenced objects prevent a
complete generation. A completed local or host-test capture is not proof of a
completed Drive upload; the separate nine-object restore above is the current
bounded cloud evidence. See [SQLite's backup API](https://sqlite.org/backup.html)
and [rclone copy](https://rclone.org/commands/rclone_copy/).

The current snapshot bounds are 2 GiB for the database, 128 MiB per object and
1 GiB total referenced-object bytes. The worker defaults to a 120-second
snapshot deadline. An exceeded bound or deadline leaves that generation
incomplete; it does not authorize omitting its objects.

## Restore a verified generation

For the library, choose a complete `library/manifests/<run>/manifest.json`.
Its `source_root` identifies the captured namespace. Each ordinary entry's
`content.remote_path` identifies its payload; download that exact path and
check its recorded size and SHA-256 before placing it at the entry's relative
name under a new private restore directory. Reject absolute paths, parent
traversals and symlink ancestry when materializing a manifest. Link entries
are metadata only; recreating or following them requires a separate decision.
The Drive objects directory uses hashes as names; the manifest retains the
original filenames and directory structure.

For a verified Drive transfer, select its exact project ID and
complete generation. Copy the generation to a **new private directory** using
the authorized rclone profile, verify `manifest.json` and every recorded SHA-256
and size, then open `project.fdb` with `FDISBULL_TARGET_STORE` set to that
restored generation's `objects` directory. Use an isolated location so no
existing object is replaced. A clean local restore check does not prove that a
cloud copy is available; test the actual downloaded generation independently.
Preserve earlier generations and conflicting content; retention or deletion is
a separate explicit decision.


### Local launchd control-path correction

The initial external stdout/stderr paths caused launchd EX_CONFIG before either
program started. The installed agents now use a small runtime under
`~/.local/state/fdisbull-drive-sync/runtime`, a local WorkingDirectory and local
error logs; stdout is discarded. Bulk snapshots and durable receipts stay in
`/Volumes/CODEX/Codex_Projects/fDisBull-fdb-private/sync-state`. The existing
mirror service and encrypted default rclone configuration are preserved.
The subsequent Drive grant and private root were verified, and the updated
worker was installed atomically and enabled. A loaded agent alone is not
cloud-backup evidence.


## Verification and remaining work

The final focused host selection passed 31 tests, including active-WAL snapshot and
isolated Project restore, recursive object closure, failed transfer/manifest
retry, remote disappearance refusal, scope-change fencing and a source rescan
before publishing the namespace. The installed watcher writes its marker and
launchd ran the worker after a nested project-directory change.
The helper bounds coalescing from the first event, so sustained activity cannot
postpone a wake forever. Native updates are installed by atomic replacement;
in-place replacement caused an observed OS code-signing cache rejection during
setup. No security setting or volume ownership was changed.

The separate cloud FDB restore establishes that one captured generation and
its nine referenced objects can be downloaded and opened with SQLite integrity
intact. A bounded cloud test of the installed content-addressed layout verified
both downloaded versions by SHA-256, retained the older generation after a
deliberately refused new manifest, and verified the exact new manifest after
retry. The focused host suite passed 31 tests. These are bounded receipts; the
initial library transfer remains incomplete and requires its own final receipt.
