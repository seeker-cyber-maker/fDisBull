# Private Drive library synchronization

The local synchronization service is prepared and its LaunchAgents are registered,
but the worker configuration is **disabled** while Google Drive authorization
is pending. No successful cloud transfer or remote restore has been established.
The service is one-way: the local intake library and private FDB repository are
the sources, and a separately selected private Drive folder is the destination.

The current local setup uses:

- Configuration: `~/.local/state/fdisbull-drive-sync/config.json`.
- Local wake marker: `~/.local/state/fdisbull-drive-sync/wake`.
- Separate rclone OAuth configuration path, to be created privately with mode 0600:
  `~/.local/state/fdisbull-drive-sync/rclone.conf`.
- Versioned worker and watcher binaries:
  `/Volumes/CODEX/Codex_Projects/fDisBull-fdb-private/service/v1-20261111/`.
- Private state, snapshots, receipts and logs:
  `/Volumes/CODEX/Codex_Projects/fDisBull-fdb-private/sync-state/`.
- Agents: `org.fdisbull.drive-sync.watcher` and
  `org.fdisbull.drive-sync.worker`; the worker uses a 60-second interval and
  watches the marker. Confirm launchd state and the latest receipt before
  calling either process operational. An installed plist alone is not proof of
  a running watcher, an authorized remote or a successful backup.

The user-facing OAuth step uses a **separate** Drive configuration with
`drive.file` scope; it does not alter the existing encrypted rclone
configuration. Complete Google consent in the side browser, then verify the
selected account, private root folder and token-backed access before enabling
the worker. Keep OAuth config private; do not print tokens or place them in
command arguments, logs, source control or status receipts. If authorization,
mount identity or verification fails, retain the existing copies and report a
failure. No password from the existing encrypted rclone configuration is needed
for this separate setup.

## Scope and local wake-up

The configured intake selection covers targets, receipts, shared media, discs,
sources and the selected library-root metadata. It excludes analysis, CI and
runtime archives. Symlink targets are recorded as metadata only: external
installer or linked bytes are not followed or silently uploaded. The FDB
repository includes its projects and explicit registrations. The current local
seed contains an existing KQ1 analysis and nine referenced objects; that is a
local input, not a cloud receipt.

The compiled Swift helper watches admitted roots using FSEvents. It writes a
local marker after a three-second debounce, including on startup; it does not
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

The installed worker invocation is `run --config` with the same paths. `run`
returns disabled without uploading while configuration is disabled. Multiple
wake-ups are serialized by the worker lock. Inspect its structured receipt and
errors; a wake, plan or launchd exit is not a transfer confirmation.

## Preservation and verification

For library files, the worker copies the changed selected files with rclone
`copy --checksum` to the current library path. An overwritten remote version
is retained under `history/<run>/library/files`; source deletions are recorded
in namespace manifests but are not propagated as remote deletions. This latest
library path is therefore **not** an immutable destination. A successful
transfer requires Drive size and MD5 readback for every submitted file; missing
or mismatched hashes refuse completion. A transfer or manifest failure must
not advance local success state.

Each FDB is a separate fresh generation, rather than a copy of its live file.
The worker uses SQLite online backup to capture committed WAL state, then
collects and SHA-256 verifies the recursively referenced external objects. It
uploads and verifies the snapshot and objects first; `manifest.json` is the
last completion artifact. The manifest records hashes and sizes for
`project.fdb` and its `objects/` closure. The scope is the snapshot and
referenced objects; backend runtimes, source media and other external files are
not automatically included. Missing or corrupt referenced objects prevent a
complete generation. A completed local or host-test capture is not proof of a
completed Drive upload. See [SQLite's backup API](https://sqlite.org/backup.html)
and [rclone copy](https://rclone.org/commands/rclone_copy/).

## Restore a verified generation

After an actual Drive transfer is verified, select its exact project ID and
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
Cloud upload is disabled until the separate Drive OAuth grant and private root
identity are verified. A loaded agent alone is not cloud-backup evidence.


## Local verification before authorization

The local host selection passed 26 tests, including active-WAL snapshot and
isolated Project restore, recursive object closure, failed transfer/manifest
retry, remote disappearance refusal, scope-change fencing and a source rescan
before publishing the namespace. The installed watcher writes its marker and
launchd runs the disabled worker after a nested project-directory change.
The helper bounds coalescing from the first event, so sustained activity cannot
postpone a wake forever. Native updates are installed by atomic replacement;
in-place replacement caused an observed OS code-signing cache rejection during
setup. No security setting or volume ownership was changed.

This remains pre-authorization local evidence. There is no remote folder binding,
verified cloud upload, cloud history rehearsal or downloaded restore receipt yet.
The Google side browser is parked at its final limited-access consent screen.
