# Native QEMU DOS migration

Use `dos-migration` to inspect the current slices, capability gaps and default
promotion gate. The ledger covers all current DOSBox RPC methods and public
debugger routes plus non-method surfaces. Test references are requirements,
not a claim those tests ran. DOSBox stays the default and remains selectable
after the migration; an uncertain operation never triggers an implicit fallback.

## Choose the backend explicitly

| Selector | Execution environment |
| --- | --- |
| `dosbox` | Retained patched DOSBox-X; existing COM/MZ project route |
| `dosbox-qemu` | DOSBox-X inside a prepared Linux/QEMU guest |
| `qemu-dos` | Native QEMU PC; original raw disk or original COM/MZ plus a separate DOS boot disk |
| `qemu-machine` | Existing generic raw machine and QEMM/DESQview contexts |

Native QEMU currently supplies machine controls, physical/virtual memory,
guarded edits, break/watchpoints, stopped-boundary trace artifacts, stored PNGs
when the QEMU build supports them, and stopped memory snapshot/search/edit/rule
operations. The process slice adds real DOS EXEC loading, verified PSP/source
entry and selected-process exit/TSR observations. Source-bound trace predicates
and persistent event searches cover the initial verified real-mode module.
Owned keyboard and relative PS/2 mouse input, explicit instruction-count
observation and stopped surface/CPU/clock captures are now available.
Frame-timed input, native checkpoints, fetch layers and scene parity remain later
slices. Periodic memory rules need the later
guest-clock slice; explicit stopped rule ticks are available.

## Check an installation without a game

```sh
fdisbull dos-migration
fdisbull dos-migration --surface debug-save-state
fdisbull doctor --backend qemu-dos --executable /path/to/qemu-system-x86_64 \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe \
  --output /private/qemu-core-check
```

Doctor executes authored boot code. Inspect its scope and individual checks:
it does not boot DOS or qualify drivers, checkpoints, games or timing parity.
QEMU 9.1+ is required. No custom QEMU patch is required. A minimal QEMU build
may lack stored-display capture; that capability is observed at startup.

`pipe` uses private POSIX process streams/FIFOs without a network listener.
The default `unix` transport remains available for existing environments.
Dispatched control failures are terminal when their outcome is uncertain.

## Launch a caller-owned DOS disk

Keep source disks, project databases and runtime artifacts outside Git. A
native DOS disk has complete 512-byte sectors, a boot signature and at most
64 MiB. Standard floppy sizes use A:; other sizes use the IDE disk. The basic
profile uses one 486, 32 MiB and no network. Configuration is not boot proof.

```sh
fdisbull dos-profile /private/DOS.img
fdisbull import /private/DOS.img /private/dos-native.fdb \
  --arch x86 --bits 32 --base 0 --entry 0
fdisbull debug /private/dos-native.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

The 32-bit raw file-address view allows a whole floppy in the project; actual
instruction width comes from observed CPU state. Raw disk offsets are not a
loaded program's source addresses. The machine starts paused at reset. In the
same retained JSON server, use the returned run ID with `debug-breakpoint` at
`0x7c00`, `debug-run`, `debug-registers`, and explicitly physical/virtual
`debug-memory`. `debug-step` is one instruction boundary, without the DOSBox
count option. A data watch uses `debug-breakpoint` with `access` and `length`.

Prepared `dos-profile --cpu max --memory-mib 64` output can be supplied as the
`guest_profile` object to JSON `debug-launch`. For installed QEMM or DESQview,
select its existing pinned profile with `--guest-profile qemm` or `desqview`;
report ingestion and actual kernel compatibility remain separate evidence.

Project identity, admitted profile and private runtime copy must agree. QEMU
runs with a disposable disk snapshot over that copy, preserving the source
disk. Closing discards runtime disk changes. An explicit firmware directory is
recorded by file hashes at admission; the default firmware path is unpinned.

Use scripts with `backend: "qemu-dos"` for the supported native operations.
Unknown or unsupported operations must refuse before execution. Stored trace
completion and display-surface capture do not acquire DOSBox fetch/frame
semantics just because their method names resemble each other.

## Keep the fallback testable

Launch an original COM/MZ project explicitly with `--backend dosbox` when a
migration gap or late regression requires comparison. Retain the old executable,
its preparation recipe and native regression tests. A raw disk project and a
COM/MZ project have different address mappings; never silently convert them or
restore one emulator's checkpoint into the other.

Transfer slices in dependency order: core; DOS process/drivers; traces/events;
clock/media/input; checkpoints; layers/hooks/block services; histories;
workflows; compatibility and fallback campaigns. QEMM, DESQview, Windows and
real games each require actual runtime evidence beyond the authored snippets.
Custom hostcalls, asynchronous providers and UDL/UIL joins remain a later slice;
the native launcher does not activate the earlier experiment's opcode hooks.

## Launch an original DOS process

For an original COM/MZ project, select `qemu-dos` with a separate
`dos_boot_image`, `dos_mcopy`, `dos_startup_batch` (default `FDAUTO.BAT`) and
`dos_arguments` (literal CP437 command tail, at most 126 bytes).

```sh
fdisbull import /private/game/TARGET.COM /private/target.fdb --image com
fdisbull debug /private/target.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private/game \
  --dos-boot-image /private/DOS.img --dos-mcopy /path/to/mcopy \
  --dos-startup-batch FDAUTO.BAT --dos-arguments ' ALPHA.TXT /Q' \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

The startup batch must already exist and return. Staging preserves its original
bytes and CONFIG files, appends an authored loader invocation, and uses private
disk copies. Required drivers/assets must already be on the FAT12/FAT16 boot
image; no host directory is mounted. COM2 is reserved for the loader protocol.
Conflicting names, changed source/disk, patched project versions, secondary
executable formats and inconsistent observations are refused.

`debug-dos-process` returns the real PSP/parent, MCB allocation, entry registers,
initial source map, environment segment, tail/FCBs, driver-chain observations
and process lifecycle. Read `source_mapping.runtime_base` and `delta` before
placing native breakpoints: machine controls do not translate static addresses.
The entire file-backed module is verified after ordered MZ relocations and
the exact DOS startup stack writes recorded in `loader_writes`. Initial load
verification is not continuous proof after self-modification or overlay loads.

The internal parent-return breakpoint yields `guest_exit` or `guest_tsr` only
after a matching helper report and DOS return category. Nested child completion
does not complete the selected process. Resident results retain observed
allocations and vector changes, without inferring which TSR instruction ran or
claiming vector-change causation. Exit/residency changes the capture epoch;
machine close invalidates live ranges. A failed observation is not a DOS exit.
The machine remains stopped and owned after a verified return.

Entry requires observed real mode. QEMM, DESQview, DPMI and V86 combinations
remain separate qualification campaigns. A registered device header or the
authored SYS initialization test does not establish arbitrary device I/O.
Source tests require real QEMU/FreeDOS and independent authored COM/MZ/TSR
witnesses; production uses the packaged helper without requiring NASM.

## Capture register and execution events

On a live COM/MZ process, `debug-trace` preserves the existing bounded-count
artifact route. `debug-trace-until` accepts the shared register, PC-range,
mnemonic, region-change and nonsequential predicates. For example:

```json
{"method":"debug-trace-until","params":{"run":"RETURNED_RUN","until":{"kind":"register","register":"ax","equals":7},"max_steps":100,"timeout_ms":10000,"name":"ax-seven.json"}}
```

Budgets count stopped QEMU debugger intervals. A stop can follow a fault or
partial REP progress; it does not certify instruction retirement. Artifacts
retain actual IRQ/timer stepping policy, full register observations, linear
and segmented PCs, verified source sites and the initial capture epoch.
Source-site hashes account for DOS relocation separately from observed byte
hashes, so independent launches can be compared at the same project site.

Use the returned `trace_artifact` with `event-trace-query`, `event-search-start`
and `event-search-refine`. Ordered entry/artifact receipts and source bytes are
rechecked after session close or project reopening. Only a closed qualified
window can narrow candidates. Self-modification, source/module departure,
allocation/epoch or mode changes stop the source binding; unbound boundaries
never acquire a source site. Inspect `source_window_closed`, `outcome` and
`error`, even if an explicit runtime predicate matched the final boundary.

Queued `action` input inside `trace-until` is refused before mutation. Dispatch
physical input with a bounded natural run, then start a separate trace at an
explicit breakpoint; the prior run is an unobserved interval, not contiguous
source-trace evidence or proof of input causation.
Raw-disk machine tracing remains separate and supplies no process source map.

## Queue input and observe clocks/surfaces

While stopped, queue `keyboard_key_down(key)` and use its returned `lease` with
`keyboard_key_up(lease)`. The shared `keyboard.key_down/key_up` namespace works
too. `mouse_move_relative(dx,dy)` queues relative controller deltas;
`mouse_button_down(button)` and `mouse_button_up(lease)` own the matching
physical button. These are machine devices, including after a DOS child exits.
Relative motion does not identify pixels or supply a DOS INT33 mouse driver.

`run(timeout_ms=...)` sends one GDB continue and at most one QMP input batch,
then reads the same native stop. Inspect `input_delivery.delivery`: either
`qmp_accepted` or `not_dispatched`. An early breakpoint can retain pending
input or follow acceptance before any guest consumption. `guest_consumed`
stays `None`; establish consumption with independent guest RAM/register/driver
evidence. Unknown delivery closes the VM without replay. Pending input blocks
step/trace/unbounded resume before execution.

`input_state()` reports the owned queue and leases. `input_cancel_pending()`
discards only unsent transitions; accepted holds still require explicit
release. Closing invalidates leases without pretending release code ran.
Limits: 256 pending edges, 64 leases and relative deltas -32767..32767.
Timed press/type, pixel clicks and frame-edge timing remain unsupported.
Make and break in one batch specify order, not a hold duration.

JSON routes are `debug-keyboard-down/up/state`, `debug-mouse-move-relative`,
`debug-mouse-button-down/up`, `debug-input-state`, `debug-input-cancel-pending`,
`debug-clock-observe` and `debug-capture-surface`. Script operations are
`keyboard.key-down/up/state`, `mouse.move-relative`, `mouse.button-down/up`,
`input-state`, `input-cancel-pending`, `clock-observe` and `capture-surface`.
Alias a down result and use `$alias.lease` for its release. Failed scripts
that touched physical input close the owned VM. Native input/capture/clock
operations refuse caller-owned database transactions during full preflight.
Their native I/O inherits the saved script's one host-time deadline; prior
channel bounds are restored afterward. Windows whole-machine snapshots refuse
pending or held machine input because their current sidecar cannot restore
these physical leases. Release/cancel explicitly before requesting a snapshot.

Select `qemu_clock='instruction'` in Python/JSON launch or
`--qemu-clock instruction` on the CLI for one TCG CPU with
`-icount shift=7,align=off,sleep=off`. `Project.machine` uses
`clock_profile='instruction'`. Default `standard` leaves the launch unchanged.
`clock_observe()` records `query-replay.icount` only for the explicit profile,
with a machine epoch, sequence and a separately labelled host timestamp.
Without that profile the counter is explicitly unsupported. `guest_ms` and
`virtual_ns` are always `None`: idle timer warps mean `count * 128` is not all
elapsed guest time. This is neither cycle accuracy nor exact live count/time
stopping. The instruction profile changes timing and must be chosen explicitly.

Host startup budgets also differ from guest boot delays. The I/O witnesses
explicitly use FreeDOS `SWITCHES=/F` to omit its F5/F8 delay for both profiles;
the ordinary baseline exceeded 15 host seconds while still inside that guest
wait. Production preserves caller CONFIG files and never skips prompts or
extends a deadline automatically. This is post-boot I/O evidence on a declared
test configuration, not arbitrary boot-time qualification.

`capture_surface(name)` stores PNG bytes, unique capture ID, run/dimensions/hash,
selected CPU state and a stopped before/after clock bracket. `screenshot()`
uses the same path. Metadata is `source='qemu_display_surface'` with
`completed_guest_frame=None` and `guest_frame_id=None`. It can contain a
half-drawn screen; a capture ID proves no new frame or UI readiness. Standard
clock stability remains `not_observable`; instruction-profile stability is only
the observed counter. A changed stopped bracket closes the VM and refuses it.

The independent native witness checks BIOS AX, IRQ1 make/break bytes, IRQ12
mouse packets, separate consumption/draw points and PNG pixels under QEMU
10.0.13/FreeDOS1.4. This does not qualify real games, QEMM/DESQview, Windows,
audio, a completed-frame fence or generic guest-time scheduling. Keep those
gates open before building checkpoints, frame histories or Python media joins.
