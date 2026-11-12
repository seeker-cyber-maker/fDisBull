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
