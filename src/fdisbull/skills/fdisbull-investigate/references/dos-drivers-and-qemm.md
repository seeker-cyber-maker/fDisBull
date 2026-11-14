# DOS device drivers and QEMM guests

Use three separate evidence paths: a DOS device's static entry points, a mixed
LE object's code view, and the state of a full machine. Recognition or a valid
configuration does not prove installation, residency, boot success or a game's
compatibility. Keep original binaries, boot images, FDBs and captured memory in
private paths outside the checkout.

## Static DOS device analysis

`file-identify`, `inspect`, and automatic import recognize structurally validated
DOS device headers in flat files and MZ load modules. `--image sys` selects that
view explicitly. A filename ending in `.SYS` is insufficient evidence.

```sh
fdisbull inspect /private/QEMM386.SYS
fdisbull import /private/QEMM386.SYS /private/qemm.fdb --image sys
fdisbull analyze /private/qemm.fdb --max-instructions 256
fdisbull analysis-status /private/qemm.fdb
```

The SYS loader records header chains, attributes, names or block-unit fields,
and independent Strategy and Interrupt entry roots. Each root has its own CS;
DS, ES, SS, SP and the request pointer remain unknown. No PSP is invented and
the Strategy root does not imply a control-flow edge to the Interrupt root.
An MZ process entry is not the driver's entry. DOS request command meanings,
installation/resident extents and handler ownership require further evidence.

Analysis persists through reopen, reset and supported child byte versions.
Changing header entry fields rebuilds the driver roots for that version. A
budget-limited pass remains partial. An explicit protected-mode transition
ends the bounded real-mode SYS traversal; it cannot preserve real-mode CS
semantics after that boundary. SYS imports do not enable direct DOSBox process
launch or generic driver UDC compilation.

## Mixed LE executable projects

Supported LE executables, including a validated MZ/BW/inner-MZ carrier, can use
normal `import --image le` and `analyze`. Each object's 16/32-bit mode persists
through reopen and mapped-memory child versions. New mode-bearing LE projects
use semantic schema10 so older readers reject them; ordinary legacy9 remains
supported. Unguarded9 mode prototypes require explicit reimport. Instructions report their
actual decoder width; the project context is a stable namespace. Preserve
object-local near targets and stop at unbacked/object boundaries. Do not infer
runtime selectors, segment memory targets or cross-mode near edges.

Internal offset32 fixups affect only the preferred static image. Offset16
records stay symbolic/unapplied because original loader conventions differ;
intersecting instructions and backing exports retain that unresolved status.
CFG closure is not complete operand interpretation. Native code-backings keep
per-block widths but remain incomplete for executable reconstruction where a
relocation is unresolved. Mixed projects and any LE image with symbolic operand fixups refuse the fixed-width advanced ABI
analysis. These are ordinary persisted static projects, not runtime selector
bindings or runnable reconstructed executables. The source guide
`docs/dos4gw-le.md` records the complete contract.

## LE objects and VxD ABI

Some drivers contain both an MZ/DOS loader and an LE module. Select an object
explicitly rather than forcing every object through one 32-bit decoder:

```sh
fdisbull le-driver-inspect /private/QEMM386.SYS
fdisbull le-driver-disasm /private/QEMM386.SYS 1 --max-instructions 32
fdisbull le-driver-disasm /private/QPI.VXD 1 --abi windows-vxd --max-instructions 32
```

Object numbers are one-based. Offsets are object-relative. The output retains
the source hash, object bitness, source-file fragments, and symbolic fixups.
Validated DOS headers at the start of a 16-bit object expose their own
object-relative Strategy/Interrupt roots. If the declared LE entry points into
such a header, it remains recorded but is classified as data. Follow an exposed
root explicitly; do not decode the header as an instruction stream. Unapplied
fixups affecting header fields prevent those static roots from being trusted.
No entry object means no entry point; offset zero in an arbitrary object must
not be promoted to a program entry. Page-map, unsupported page, relocation,
unbacked-byte and decode limits remain explicit. These are bounded code views,
not an installed VxD, a complete control-flow graph, or a linked executable.

The default ABI is `unknown`. Only the explicit `windows-vxd` selection permits
recognizing the 32-bit `INT 20h` plus inline service DWORD convention. Such a
service boundary is not a DOS process exit and the inline DWORD is not another
instruction. A 16-bit object alone does not establish that ABI.

## Prepare a QEMM guest

The supported route uses `qemu-machine` and a caller-prepared bootable DOS disk
containing the caller's QEMM installation. The DOSBox process-launch route does
not boot DOS `CONFIG.SYS` and cannot be made QEMM-enabled with this option.

```sh
fdisbull qemm-config --config-file /private/CONFIG.SYS
fdisbull qemm-profile /private/boot.img
```

`qemm-config` returns a text preview and hash. It does not write the source file
or install anything in the disk image. The profile reader examines the actual
FAT12/16 members in the disk; optional `--config-sys` and `--driver-path` compare
host copies byte-for-byte. It refuses conflicting memory managers, ambiguous
menu/include selection, divergent FAT copies and unsupported file layouts.
Keep DOS path drives consistent with the boot device: a floppy boots as A:;
the admitted hard-disk volume is C:. Root-relative paths use that boot volume.

Profile identity binds the disk, configuration, driver and machine policy.
Launch rechecks the identity, makes a private image copy and uses a temporary
QEMU disk snapshot. The profile selects one 486 CPU and 32 MiB RAM, with no
network. QEMU 9.1 or later is required by the underlying machine backend.
Configuration evidence starts with `memory_manager.observed = unknown`.

Import the disk as an explicit raw project solely for machine/source identity:

```sh
fdisbull import /private/boot.img /private/machine.fdb --arch x86 --bits 16 --base 0 --entry 0
fdisbull debug /private/machine.fdb --executable /path/to/qemu-system-x86_64 \
  --game-dir /private --backend qemu-machine --guest-profile qemm
```

The machine begins paused. Use the returned run ID in subsequent JSON-line
requests. Plan program launch in the private image's DOS startup files or use
the existing machine controls. Raw disk offsets are not a loaded game's memory
addresses. This route does not inherit the DOSBox game scenes/input machinery.

```json
{"method":"debug-run","params":{"run":"<run>","timeout_ms":1000}}
{"method":"debug-registers","params":{"run":"<run>"}}
{"method":"debug-memory-translation","params":{"run":"<run>","address":"0xa0000"}}
```

Register observations distinguish real, v86, protected and long mode, retain
observed segment-cache bases and widths, and do not turn a protected selector
into `selector * 16`. Tracing uses the observed width and refuses a conflicting
caller width. Translation reads the stopped machine's current CR3/PDE/PTE for
non-PAE 4 KiB maps; absent pages, unobserved A20, large pages and unsupported
paging formats stay unknown/unsupported. It does not establish allocation
ownership, lifetime, a permanent source binding or a complete access verdict.

## Record QEMM's own observations

Generate the authored helper before constructing/admitting the private image:

```sh
fdisbull qpi-probe /private/FDQPI.COM --mode breakpoint
```

Copy it into the DOS image and arrange to run it after QEMM loads. The helper
opens `QEMM386$`, obtains the far entry through DOS IOCTL, and calls GetVersion,
GetStatus, GetInfo and GetPTE. It requires a 386 and QEMM 6.00 or later. These
QPI calls are read-only; there are no page setters or interrupt/I/O hooks.

Breakpoint mode holds ES:DI and CX=1120 in a stable report-ready loop. The export
receipt gives `ready_com_offset`, `report.com_offset` and `release_com_offset`.
Pause after a bounded run or set a breakpoint at the helper's observed load
segment plus its ready offset. Confirm that CS:IP is in that helper loop. A
guest INT3 is deliberately not used because it may be handled inside the guest.

At a real/v86 stop, calculate the buffer's linear address from the observed
ES:DI, then retain it through the machine API:

```json
{"method":"debug-qemm-observe","params":{"run":"<run>","address":"<observed linear buffer address>"}}
```

The exact report bytes become a private run artifact, with report, boot-image,
profile and emulator hashes plus the captured CPU context. Results distinguish
guest-reported active/inactive/unknown, partial reports and complete page loops.
The observer does not execute QPI or independently establish report freshness.
To let the helper return to DOS, guard-write its release byte from 00 to 01 at
the observed helper segment plus `release_com_offset`, then resume.

For an offline report, export with `--mode file`; the helper creates/replaces
`FDQPI.BIN` in its DOS working directory and exits. Extract that file privately:

```sh
fdisbull qpi-report /private/FDQPI.BIN --include-pages
```

The parser retains BCD version registers, raw PTE values, aliases, ranges and
explicit failures. Its maximum is 272 CPU pages of 4 KiB (the first 1088 KiB),
not an EMS allocation inventory. The sequential QPI loop is not atomic and
leaf PTE attributes alone do not establish effective permissions. Do not treat
a parsed file, authored emulator fixture, successful API call or detected QEMU
binary as native QEMM/game qualification.

## Persist task/object relationships

Use `runtime-objects` to select a source-bound object, then
`runtime-task-start`, `runtime-map`, `runtime-unmap`, `runtime-map-checkpoint`
and `runtime-map-restore` to preserve attributed relationships and their event
history. `runtime-tasks`, `runtime-mappings`, `runtime-resolve` and `runtime-mapping-events`
remain available after project reopen. CLI writes take one bounded JSON object
through `--definition-file`; JSON-line calls accept the operation parameters.

These direct records are caller evidence, including when labeled `recorded`;
they do not authenticate a live mapping. `runtime-map-snapshot` additionally
checks a local retained snapshot's bounded object span and capture context.
Excluded relocation fields, task ownership and continuous mapping lifetime
remain separately qualified. A foreign artifact ID is not silently imported.
Register the task with its explicit capture epoch before taking the qualifying
snapshot; an older baseline may establish the epoch but cannot qualify a new
incarnation. Original MZ carriers can expose source-bound `le:1` objects without
pretending their LE preferred keys are MZ instruction addresses.

Preserve every alias instead of choosing one inverse physical address. Do not
project a protected selector through `selector * 16` or infer one global object
relocation delta. A direct map's `selector` is an explicit descriptor object
with integer `value`, `base`, `limit` and `bits` fields, not a numeric selector
alone. Selector queries take the numeric value and an offset, using the recorded
base and limit. This still describes attributed evidence, not a verified hidden
CPU cache. A registry restore creates fresh recorded binding lifetimes;
it does not restore the guest. The full public contract and examples are in
`docs/runtime-mappings.md` in the source documentation.

## Sources and useful follow-up work

The DOS header/entry contract follows Microsoft's *MS-DOS Encyclopedia*,
Section II, article 15. QPI acquisition and read-only functions follow the
supplied QEMM 97 `TECH_DOC/QPI.PDF`, printed pp. 262–266. Preserve raw PTE bit 2;
its CPU meaning is user-accessible when set, despite a contradictory sentence
in that manual's prose. The manual's own `000FF007` example agrees with the CPU
meaning.

Useful future work includes observed resident extents, interrupt/callback
ownership, EMS/VCPI/XMS service inventories and mapping-change histories.
Those are additional evidence adapters, not implied by this implementation.
Stealth ROM interception, QPI I/O trapping, Windows 3.x/9x execution, MagnaRAM
and arbitrary driver reconstruction remain separate projects.
