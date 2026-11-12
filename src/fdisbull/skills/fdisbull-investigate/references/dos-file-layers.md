# Native DOS workspace and file layers

The QEMU DOS workspace path is an optional, bounded checkpointed filesystem.
It combines a FreeDOS system on `C:` with a private FAT workspace on `D:`.
At launch it captures the chosen host directory into a private base, stages the
selected original COM/MZ in that view, selects its DOS parent directory, and
runs the existing source-bound process loader. Guest changes affect the private
image; they are not written back into the captured host files. The root is the
request's selected `dos_directory`, otherwise its `game_dir`. If both are
omitted, Python/CLI capture the caller's working directory at launch; a server
uses its recorded startup workspace. An explicit root is preferable for server
callers.

Bounded native cases have passed locally; broader qualification remains open. Existing DOSBox remains the default;
this is not general filesystem parity or qualification of the full migration
plan. Live mode is currently refused. An explicit controlled host refresh can
stage a new checkpointed generation for a later cold launch; it does not refresh
the running guest. Live visibility, automatic keep policies and broad DOS
application behavior remain open. A pre-existing checkpoint without workspace metadata does not gain
host-file restoration retroactively.

## Runtime selection

Prepare a component from the locked official FreeDOS 1.4 input image, kernel and
FreeCOM packages using external mtools and a new private output directory:

```sh
fdisbull freedos-runtime-prepare boot.img kernel.zip freecom.zip /private/new-runtime --mtools-dir /private/mtools/bin
fdisbull freedos-runtime-info --path /private/new-runtime
```

The output includes a manifest, minimal image, upstream source packages, notices,
recipe and portable archive. Verify the runtime's identity and boot evidence for
the intended host; the component's build receipt alone does not prove boot or
complete redistribution qualification. Set `FDISBULL_FREEDOS_RUNTIME` or provide
`freedos_runtime` explicitly. Continue to protect original binaries, saves and
session artifacts under the repository's private-input rules.

The locked FreeDOS package kernel and shell binaries match the official floppy
inputs, and their upstream source packages and license texts accompany the
component. A separately prepared component is used in native composite-disk tests, where
`C:` boots and the program reads and writes `D:`. The final delivery receipt pins
the image and bundle used in those tests. That external test
does not change its manifest's `boot_validation="pending"` or qualify another
build, platform, installed bundle or the entire redistribution chain.
The current rebuild recipe does not promise a byte-identical image: FAT volume
serials and file timestamps can differ. Verify each generated image's manifest
and boot it independently rather than transferring the earlier image's receipt.

For example, an agent using an already opened project can launch with:

```python
with project.debugger(qemu, game_dir, backend="qemu-dos",
        freedos_runtime="/private/new-runtime", dos_directory="/private/game-root",
        dos_file_mode="checkpointed", qemu_checkpoint_tool=qemu_img,
        qemu_firmware=firmware) as debug:
    status = debug.workspace_status()
    base = debug.workspace_files(view="base")
    checkpoint = debug.workspace_seal()
    changes = debug.workspace_files(view="diff")
```

The `debug` command accepts `--freedos-runtime`, `--dos-directory`,
`--dos-file-mode checkpointed` and `--dos-generation`. Server `debug-launch`
accepts the corresponding underscore names. To select a previously staged
child at a cold launch, pass its generation artifact as `dos_generation`; a
staged edit never modifies an already running VM. A generation-backed launch
requires omitting both `dos_directory` and `dos_file_mode`; the generation
supplies its recorded root/mode and is usable without the original host tree.

## Inspect, seal and stage changes

`workspace_status()` describes the admitted base and most recent sealed
workspace generation. `workspace_files(generation=None, view="base" |
"effective" | "diff")` and `workspace_read(path, generation=None)` inspect
sealed generations, not the live disk. `workspace_seal()` requests a full native
checkpoint and extracts a matching private FAT generation from its snapshot.
Full checkpoint restore must validate the corresponding workspace state before
resuming. Use `workspace_export(path, new_destination, generation=None)` for an
exclusive export after the caller has established the required guest close and
flush boundary. `workspace_keep` additionally requires an explicit authored
create in the staged generation; that does not prove the guest created the
file. A raw guest directory difference does not establish creation provenance.
Neither operation silently overwrites original or previously admitted paths.

`workspace_edit(generation, operation, ...)` creates an immutable, inactive
child for `create`, `import`, `write`, `write-range`, `resize`, `rename` or
`delete` or `refresh`. Replacement/range/resize edits require the expected original SHA-256;
Python byte payloads use `data`, while the JSON `debug-workspace-edit` route
uses `data_hex`. Paths are DOS-relative or `D:` paths. `refresh` takes no file
payload or path arguments. It captures the already admitted host root again
and stages an immutable child without touching the running disk. A
staged child is not a checkpoint or a change to the current guest. Changing
layer selection does not rewrite loaded guest RAM or authorize rebinding source.

For example, explicitly refresh from a sealed generation, inspect it, then
select its returned artifact as `dos_generation` in a separate cold launch:

```python
current = debug.workspace_status()["generation"]["artifact"]
staged = debug.workspace_edit(current, "refresh")
child = staged["generation"]["artifact"]
assert staged["active"] is False
changes = debug.workspace_files(child, view="diff")
```

Refresh refuses a replaced root, unsupported or unstable capture, or a branch
whose private contents or metadata differ from its last admitted host revision.
No automatic merge is attempted. Select an earlier generation explicitly if
that is the intended branch. The original executable must retain its original
host-relative path, DOS alias and SHA-256. A changed, removed or remapped source
refuses before a child is published. Newly admitted host paths become protected
from replacement by later create/keep/export operations. Deletions and edits
in the new generation leave every earlier generation readable.

The active guest keeps its existing disk, open handles, offsets, caches,
history cursor and source mapping. Refresh neither closes guest files nor
imports new bytes into that machine. Old full checkpoints still restore their
pinned file view even after the host changes. Only a cold launch selects the
staged host revision. A generation with multiple original executables sharing
the project basename and hash refuses cold launch because its source working
directory is ambiguous.

JSON counterparts are `debug-workspace-status`, `debug-workspace-files`,
`debug-workspace-read`, `debug-workspace-seal`, `debug-workspace-export`,
`debug-workspace-keep` and `debug-workspace-edit`; reads return `data_hex` in
JSON. Workspace snapshots and exports can contain private file bytes and belong
in the private external store, not a source or review upload.

## Capture a caller-attested output

`workspace_save_output(path, new_destination, closed_and_flushed=True)` combines
a full native checkpoint with an exclusive physical export. The destination
must be an absolute new host path. The selected guest pathname must be absent
from the protected host/DOS admission sets and present as a file in the freshly
sealed generation. The returned receipt binds the original source/process
epoch, runtime, checkpoint, file generation, exact payload hash and export.
JSON exposes the same operation as `debug-workspace-save-output`.

The caller must independently establish close/flush before supplying literal
`True`; omitted, false, integer and string attestations refuse. For example:

```python
# After the caller has observed the program close and flush this output:
saved = debug.workspace_save_output(
    "SAVE.DAT", "/private/kept/SAVE.DAT", closed_and_flushed=True)
assert saved["export"]["durable"] is True
assert saved["guest_create_provenance"] is False
```

The operation reads the qualified FreeDOS kernel's complete global SFT and
buffer lists using stopped physical conventional RAM, with equal repeated
observations and a stable CPU/process context. Every ordinary open SFT entry
and dirty DOS buffer must be absent before and after checkpoint capture.
There is no guest resume or implicit DOS close/flush. The counters are guards;
the observer still reports full paths, sharing, locks, flush boundary and
coherence as unknown. Provenance is **caller-attested**. A renamed original
cannot acquire `keep` rights from this operation, and strict `workspace_keep`
continues to require an explicitly authored create unless supplied with the separate native guest-create proof described below.

Initial admission is deliberately bounded to the tested minimal FreeDOS
component-04 image, SHA-256
`badc71221f90a0ae823b23ee45b9372d8f6e4b819fecd301fed0ee4b7d0dadf2`,
with matching locked package/runtime descriptors. `dos_output_capture` reports
that runtime capability. Rebuilt images require separate qualification. The
fingerprint qualifies the initial runtime/layout, not later kernel RAM
integrity. A verified real-mode, unpaged, single-CPU context is required;
active global/task-private layers, input ownership/schedules, clock budgets
and clock sync refuse this initial route. Other workspace/debugging operations
retain their existing contracts.

The physical copy survives rewind independently. Loading an earlier checkpoint
restores its historical guest membership; it neither deletes the export nor
silently imports later bytes. Explicit staged import followed by cold launch
makes an exported copy available to a new guest branch. New staged imports and
authored creates default to the valid DOS epoch date, 1980-01-01; existing
generation metadata is retained.

All workspace exports now stage bytes in a private same-directory file, fsync
and verify them, recheck case/DOS aliases, then publish the final name through
an exclusive hard link. Partial writes do not expose a final file. This requires
filesystem hard-link support; there is no in-place publication fallback.
Exact-name races cannot overwrite another file; case/alias checks retain a
filesystem-dependent concurrent-writer window. A failure after publication
retains the file and precise available effects on the exception. Do not replay
an uncertain export. This caller-attested route does not itself grant guest-create proof or enable keep policies; the separate opt-in native route below supplies bounded evidence.

Admission rejects symlinks and special entries rather than silently following
them. Current host capture is bounded to 512 entries, 16 MiB total file bytes,
and depth 16, subject also to FAT naming and capacity checks. The default D: FAT image is 32 MiB; the composite disk is bounded to 64 MiB. Unresolvable name mappings, unsupported paths, changes detected during
capture, and invalid generations are refused. Capture uses two stable no-follow
passes; it is not an atomic host snapshot and cannot exclude undetected ABA
changes by noncooperating writers. These bounds and the effective view do not imply live observation
of later host edits.

Host names receive deterministic ASCII 8.3 aliases (including case collisions);
inspection preserves the admission mapping. Capture assigns the archive bit to
files and the directory bit to directories. It converts UTC modification times
to DOS two-second timestamps within 1980–2107; host permission bits do not
become DOS read-only attributes. Guest FAT attributes/timestamps are retained
in sealed inventories. Long-filename DOS APIs and network filesystems are not
qualified. A sealed inventory describes committed FAT bytes. Open-handle and
dirty-buffer state is retained by the accompanying full VM checkpoint, rather
than materialized into that file inventory. A malformed/transient FAT inventory
is refused; this route does not promise capture at every internal DOS boundary.


## Witness a guest-created save

The optional N22 QEMU extension adds native DOS call/return evidence for one
new file. `workspace_provenance_start` arms it at the **verified original COM/MZ
entry**, where the loader has established the child PSP. Arming after an
unobserved guest interval refuses. The initial route uses the same qualified
component-04 image and real-mode/unpaged/single-CPU context as output capture;
active layers, task views, input owners and clock sync/budgets refuse admission.
Existing trials, histories, layers, hooks, checkpoints and IRQ operations retain
their existing contracts; their presence does not broaden this proof's scope.

```python
armed = debug.workspace_provenance_start("SAVE.DAT")
# Execute the original guest to a caller-selected stopped boundary after its
# close and flush, before termination or another unsupported DOS operation.
status = debug.workspace_provenance_status()
assert status["native"]["phase"] == "ready"
proof = debug.workspace_provenance_capture()
kept = debug.workspace_keep(
    "SAVE.DAT", "/private/kept/SAVE.DAT", proof["generation"],
    provenance={"artifact": proof["artifact"], "sha256": proof["sha256"]})
assert kept["guest_create_provenance"] is True
```

The accepted sequence is exclusive `INT 21h/AH=5Bh` creation of one absent,
unprotected root `D:\` non-device 8.3 path, zero or more complete positive
`AH=40h` writes, optional `AH=68h` commit, successful `AH=3Eh` close, then
returned `AH=0Dh` flush. The observer captures actual accepted write bytes and
DOS return flags. A proof also requires equal native records and clean stopped
global SFT/buffer observations around a full checkpoint, plus exact agreement
between captured bytes and the selected file in the sealed FAT generation.
An empty exclusive-created file is supported. Overwrite/truncate creation,
seeks, duplicate handles, rename/delete, process changes and unowned raw
storage/DMA/PCI operations invalidate evidence without changing guest execution.

The native ledger is bounded to 32 source ranges below `0xA0000`, 64 KiB of
accepted payload, 256 events and 16 nested hardware return frames. Pending DOS
calls, their input bytes and hardware frames survive full checkpoint restore;
restore compares the complete record and requires advanced epoch/generation
before rebinding. Ready and invalid records remain owned until explicit
`workspace_provenance_stop`. The witness does not stop execution on readiness:
the caller must select the stopped close/flush boundary. Later unsupported
activity invalidates the live witness. A previously persisted proof remains
bound to its immutable historical generation.

Ownership follows the loader-established process lifetime. The INT 21h vector
is pinned; observed PSP queries must agree, and process-changing calls invalidate.
There is no independent read of the kernel current-PSP global on every call and
no proof against arbitrary live kernel RAM changes, custom drivers, TSR activity
or another DOS runtime. Host RAM/register/layer/task mutations taint live
evidence. Full checkpoint restore can rebind the saved observer; selected CPU/RAM
undo does not manufacture a new filesystem proof. No commercial-game or general
DOSBox parity follows from these bounded COM/MZ witnesses.

## Opt in to versioned save keeps

`workspace_keep_policy(path, directory)` arms the same observer and explicitly
enables a host keep policy for that path. The destination must already exist
as an absolute directory; no-follow checks pin its device/inode identity.

```python
armed = debug.workspace_keep_policy("SAVE.DAT", "/private/kept/versions")
policy = armed["policy"]["artifact"]
# Execute to the stopped, witnessed close/flush boundary as above.
sealed = debug.workspace_seal()
assert sealed["keep_policy"]["outcome"] in ("kept", "already-kept")
debug.workspace_keep_policy_enabled(policy, False)
```

The service runs only when the caller explicitly invokes `workspace_seal`.
Internal trial/history/checkpoint captures do not publish files, and there is
no background watcher or guest-call callback that writes to the host. An
incomplete or tainted witness reports `not-ready`; a disabled policy reports
`disabled`. A ready proof is revalidated against the sealed source/path/bytes
before publication. Policy output names are `00000001.SAV`, `00000002.SAV`, etc.,
with exclusive durable publication through the existing export path. Existing
files are never overwritten. Directory swaps, aliases and changed kept bytes
refuse rather than silently redirecting or replacing output.

An immutable host journal reserves each payload SHA-256 before export and
records completion afterwards. Identical content is deduplicated within the
same policy, including after guest rewind or a reopened analysis session.
Different policies are independent. Up to 128 content versions and 1,024 journal
events per policy are supported. A failed or uncertain reservation returns
`needs-reconciliation` and is never replayed automatically. Available checkpoint,
reservation and physical-export effects remain on the failure receipt.
Disabling a policy survives guest rewind. This journal is outside the VM
checkpoint, not outside the project database: restoring an older whole FDB is
not covered by its deduplication guarantee. Native checkpoint migration across
different QEMU binaries is also unqualified.

Both native provenance and policy routes have Python and `debug-workspace-*`
JSON interfaces. Missing native extensions refuse these routes. Plain
`workspace_keep` retains the authored-create contract; supplying a validated
provenance reference grants the bounded guest-create route. All new surfaces
remain formally unqualified in the migration inventory. DOSBox-X stays default
and retained; no CI or backend-default change is required.


## Overwrite, seek and rename saves

N23 adds an explicit `mode="save"` for `workspace_provenance_start` and
`workspace_keep_policy`. The default remains `mode="exclusive"`, preserving
N22's append-only exclusive-create contract. The new mode has a separate native
arm command and versioned receipt; missing N23 support refuses before arming.
It retains the original-entry/runtime/context admission limits above.

```python
armed = debug.workspace_keep_policy(
    "SAVE.DAT", "/private/kept/versions", mode="save",
    temporary_path="SAVE.TMP")
# Run to a caller-selected stopped boundary after the guest closes and flushes.
sealed = debug.workspace_seal()
assert sealed["keep_policy"]["outcome"] in ("kept", "already-kept")
```

The final path may be absent or contain an eligible save. An existing file must
come from an immutable authored workspace create (`origin=new`), or match the
exact bytes and path of a validated stored provenance receipt supplied as
`predecessor={"artifact": prior_id, "sha256": prior_hash}`. The predecessor must
bind the same source version and original workspace base. Its sealed bytes and
all v2 preimage dependencies are revalidated before admission and publication;
chains are bounded to 32 receipts. Mere FAT presence, a matching filename or an
unproven import does not grant overwrite eligibility. Initial original host
paths and their aliases remain protected even after deletion or replacement.

The native transcript supports create/truncate (`AH=3Ch`), exclusive create
(`AH=5Bh`), reopen for writing/readwrite (`AH=3Dh`, AL=1/2), full writes
(`AH=40h`), BOF/current/EOF-relative signed seeks (`AH=42h`, AL=0/1/2),
zero-count writes that truncate at the cursor, optional commit, close and
returned DOS flush. Each event retains its entry path and inputs, returned
flags/count/seek result and cursor/size transition. The host independently
replays those operations from the immutable preimage and captured write stream,
then compares the reconstructed final bytes with the sealed FAT file. In v2,
native `payload-hex` is the chronological write stream; the proof's
`payload_sha256` and `payload_size` describe the reconstructed final file.

A configured temporary path must start absent, be distinct from the final path
and pass the same protection checks. One tracked file identity and one open
handle are supported. A successful closed-file rename (`AH=56h`) can move it
between those two paths. Temporary replacement may retain an eligible old final
file while writing the temporary file, then observe deletion of that old final
(`AH=41h`) and rename the closed temporary file into place. The host also checks
that the temporary name has disappeared from the sealed generation. Unknown
paths, rename collisions, duplicate handles, unmodeled reads and unsuccessful or
short operations invalidate evidence. A policy remains bound to its explicitly
named final path; it does not silently follow a rename away.

Repeated create/open/write/close/flush cycles can produce new content versions
within the same observer. Explicit workspace seals keep each distinct content
hash once per policy; repeated content after rewind is verified and deduplicated.
The journal and policy disabling still survive guest rewind and reopened FDBs.
Pending seeks and renames, their captured path/offset inputs, stream bytes and
IRQ frames are included in full checkpoints before host rebind.

Logical file size and cursor are bounded to 64 KiB, as is the **cumulative**
accepted write stream over the observer lifetime. The initial preimage is also
bounded to 64 KiB. Up to 256 events, 32 source ranges below `0xA0000` and 16
hardware interrupt frames are retained. The source code mapping itself may
exceed 64 KiB. A seek may pass EOF within the cursor bound, but a subsequent
write or zero-count extension that would introduce undefined gap bytes refuses.
The witness never invents zero-filled DOS file contents. General filesystem
semantics, multiple simultaneous save handles, arbitrary drivers/TSRs, automatic
safe-stop selection and broader runtime/context parity remain unqualified.
DOSBox-X remains default and retained, with no CI requirement for this local slice.


## Automatic safe stops and keeps

N24 adds `safe_stop=True` to a `mode="save"` keep policy. The default remains
false. With this opt-in, an explicit outer public `run()` selects the native
return from a completed DOS flush, pauses before the next guest instruction,
then seals and validates the file and services the keep policy under the same
outer host deadline. The caller no longer supplies a post-flush breakpoint.

```python
armed = debug.workspace_keep_policy(
    "SAVE.DAT", "/private/kept/versions", mode="save", safe_stop=True,
    temporary_path="SAVE.TMP")
result = debug.run(timeout_ms=30000)
assert result["outcome"] == "save_boundary"
assert result["save_keep"]["policy"]["outcome"] in ("kept", "already-kept")
# A later explicit run may reach another save boundary or normal guest exit.
```

The return includes the original native machine stop, a separate save-stop
receipt, full checkpoint/workspace references and the policy result. Publication
never continues the guest implicitly. `needs-reconciliation` retains the
reservation/effect evidence and is never replayed automatically. A failure after
checkpoint or physical export carries the known effects and closes an unverified
owner; a close-persistence failure does not erase the earlier export receipt.

The native controller attempts a stop only after a matched `INT 21h/AH=0Dh`
return has completed and the v2 file is closed, final-named, valid and free of
pending DOS calls or hardware frames. A preexisting ready ledger, query, IRQ
return or restore cannot synthesize a new attempt. Each actual completed flush
may produce one new sequence; identical content is still deduplicated by the
host journal. The auxiliary stop packet binds observer token, epoch/generation,
sequence, event count and returned PC/CS/SS/SP. The host also checks the actual
GDB stop and the last DOS return, so a matching PC alone cannot claim ownership.

A user breakpoint, hook, step or another stop owner keeps its actual receipt.
The keep is withheld on a conflicting/preempted attempt. A configured control
at the returned PC is reported separately if it has not actually fired; the
host never manufactures breakpoint IDs from the PC. Hook hits and pending
step-over state are retained instead of silently continuing past the boundary.
Active clock budgets and renderer fences cannot share automatic stop selection.
The existing runtime/context and proven-preimage admission rules still apply.

Automatic selection/publication is limited to an outer public `run()`. Scripts,
comparative trials, internal history/CPU-undo execution and renderer/timing
execution disable this controller and retain their established contracts. No
background watcher or loop is added. Policy disable decisions remain in the
host journal, including after rewind or reopened FDBs. Host state mutations
still invalidate the underlying save evidence under its existing rules.

The native attempt outcome distinguishes `consumed` and `preempted`. A settled
receipt is durably recorded before a token/epoch/generation/sequence-bound ACK;
control is disabled on leaving the public run. An unacknowledged repeated flush
invalidates the auxiliary automatic-stop control, separately from the core
filesystem ledger. A pending native/main-loop handoff cannot be checkpointed.
A settled receipt can: full restore validates its logical state and advanced
owner counters, and explicit resume acknowledges an old consumed/preempted
attempt without republishing or retrying it. A later fresh flush may create the
next stop. Physical copies and journal decisions remain outside guest rewind;
whole-FDB rollback remains outside that guarantee.

N24 uses native VMState schema3/minimum3 and same-binary restore. Existing v1/v2
save-witness packets remain unchanged; N22 and N23 and their matching runtimes
stay available for their own checkpoints. Broad runtime/driver and cross-binary
migration qualification remain open. DOSBox-X remains default and retained.

## Disk-full save failures

Two bounded native N24/FreeDOS cases now exercise an actual full workspace,
rather than injected DOS replies. The authored test uses the real FAT builder
with a 4,595,712-byte D: volume and an independently counted allocation table;
the production workspace remains 32 MiB. The executable is allocated before
the filler and the complete test disk ends on a 16-head, 63-sector cylinder
boundary. This is a fixture layout, not a change to the production launcher or
a claim about the BIOS-reported geometry.

| Initially free clusters | Requested `AH=40h` bytes | Observed DOS return | Sealed file |
| --- | ---: | --- | ---: |
| One 512-byte cluster | 1,024 | Carry clear, AX=512 | 512 authored bytes |
| Zero | 1,024 | Carry clear, AX=0 | Empty |

Carry clear does not prove the whole write succeeded: the accepted count must
also match the request. Both runs invalidate the native save witness with
`DOS write failed or was short`; no write payload is admitted into that proof.
The guest still reaches its real user breakpoint after close/flush. Neither an
automatic boundary nor a keep reservation/completion is produced. An explicit
seal reports the policy as `not-ready`, retains the actual partial/empty file
as ordinary workspace state, and does not grant it save provenance. Full
checkpoint restore in a fresh QEMU process retains that invalid state and the
empty keep journal. The original host executable and filler remain unchanged.

An earlier nearly full 4 MiB fixture timed out before source entry when the
executable was allocated after the filler. Boot-only controls reached entry
when either file placement or image size/alignment changed. The pinned QEMU
geometry heuristic also disagrees with the BPB geometry; causality has not been
established. The failed run and controls are retained as diagnostics. Arbitrary
near-full layouts, BIOS geometry, other DOS runtimes, carry-set errors, and
short writes across the broader overwrite/seek/rename combinations remain
unqualified. The two save-refusal witnesses do not close a formal migration
surface or authorize removing DOSBox-X.
