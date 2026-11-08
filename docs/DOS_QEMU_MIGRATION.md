# Native QEMU DOS migration

`qemu-dos` supplies an explicit, native QEMU PC backend. It boots a caller-owned
disk and can launch an original COM/MZ project through real DOS. `dosbox` remains the default
for DOS programs, and both DOSBox choices remain selectable after the migration.

The first slice supplies owned startup/shutdown, private disk isolation,
capability discovery, stopped CPU/RAM inspection and edits, break/watchpoints,
bounded execution, instruction traces and stored-display screenshots. Existing
memory snapshots, searches, guarded edits and explicit rule ticks use the
native machine context. The [capability inventory](DOSBOX_QEMU_CAPABILITY_INVENTORY.md)
tracks every existing DOSBox protocol method and public debugger route, plus
capabilities that a method count misses.

The second slice adds verified DOS process entry, PSP/source identity,
termination versus TSR residency and driver-chain observations. The maintained
[migration plan and handoff log](DOS_QEMU_HANDOFF.md) records decisions,
expected difficulties, findings and dated validation.

The third slice connects that verified process to stopped-boundary traces,
register/PC/region predicates and persistent execution-event searches. Its
source identity survives ordinary MZ relocation and later process closure.
Overlays, mode changes and queued-input timing remain explicit boundaries.

The fourth slice now supplies owned physical keyboard/PS/2 input, explicit
instruction and native virtual-clock profiles, and stopped display captures
with CPU/clock brackets. The optional virtual profile adds native timer budgets;
completed frames, audio and legacy timing parity remain open gates.

This is an alternative for testing now. Checkpoints and execution layers remain
later slices. The default-switch gate remains blocked until the outstanding slices
and compatibility campaigns are qualified. No command here changes the default.

## Select the execution environment

| Backend | What executes | Input and scope |
| --- | --- | --- |
| `dosbox` | The existing patched DOSBox-X | Existing DOS program project; retained default and fallback |
| `dosbox-qemu` | DOSBox-X inside a prepared Linux/QEMU guest | Existing DOS project plus Linux kernel/initramfs; retained fallback |
| `qemu-dos` | DOS or an authored boot program directly on QEMU's virtual PC | Original raw disk, or original COM/MZ plus a separate DOS boot disk; single TCG vCPU and explicit physical/virtual controls |
| `qemu-machine` | Generic existing QEMU machine context | Original raw disk; existing QEMM/DESQview profiles remain supported |

Selecting QEMU never silently launches DOSBox. After a failed or uncertain
operation, the caller inspects the result and explicitly starts a separate
fallback session. A DOSBox state cannot be loaded as a QEMU checkpoint.

## Prepare and check the core

Use a separately installed `qemu-system-x86_64` version 9.1 or later and its
matching PC firmware. No custom QEMU patch, DOS installation, Python media
renderer or game is required for the core self-test. QEMU's TCG backend is
selected explicitly; this lane does not use KVM or a host virtualization API.

```sh
fdisbull dos-migration
fdisbull dos-migration --slice layers-hooks --details
fdisbull doctor --backend qemu-dos --executable /path/to/qemu-system-x86_64 \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe \
  --output /private/native-qemu-check
```

The doctor runs disposable authored boot code and returns a receipt. Its core
result does not qualify DOS services, drivers, a game, checkpoint restore or
DOSBox parity. Inspect the individual checks and reported graphics capability;
minimal QEMU builds may omit `screendump`. Source tests separately exercise an
authored COM probe under an actual FreeDOS installation.

The default control transport remains private Unix sockets. `pipe` is an
explicit POSIX alternative using QMP over the owned process's standard streams
and GDB over private FIFOs. It needs no listening TCP port. Channel errors and
uncertain dispatched control operations close the owned machine; they are not
automatically replayed. QEMU's executable identity and an explicitly selected
firmware directory's top-level file identities are recorded. The default
firmware search path is labelled unpinned when no directory is supplied.

## Boot a private DOS disk

Keep the disk and project outside Git. The initial native DOS profile admits
512-byte sectors, a boot signature and a maximum image size of 64 MiB. Standard
floppy sizes select the floppy device; other sizes select IDE. The basic
profile defaults to a 486 and 32 MiB, with one vCPU and no network.

```sh
fdisbull dos-profile /private/DOS.img
fdisbull import /private/DOS.img /private/dos-native.fdb \
  --arch x86 --bits 32 --base 0 --entry 0
fdisbull debug /private/dos-native.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

The raw disk uses a 32-bit **file-address view** so a complete floppy fits in
the project. This does not make DOS execute in 32-bit mode. Native traces use
the observed CPU mode and code-segment width at each instruction. Disk offsets
do not establish a loaded COM/MZ program's source-to-memory mapping.

The machine starts paused at reset. Use the returned run ID in the same
retained `debug` server, for example:

```json
{"method":"debug-breakpoint","params":{"run":"RETURNED_RUN","address":"0x7c00"}}
{"method":"debug-run","params":{"run":"RETURNED_RUN","timeout_ms":10000}}
{"method":"debug-registers","params":{"run":"RETURNED_RUN"}}
{"method":"debug-memory","params":{"run":"RETURNED_RUN","address":"0x7c00","length":16,"space":"physical"}}
{"method":"debug-stop","params":{"run":"RETURNED_RUN"}}
```

Boot-image identity must match the original project throughout profile admission
and the private runtime copy. QEMU writes to a disposable snapshot over that
copy; the selected source disk stays unchanged. Closing the session discards
runtime disk changes. Firmware identity is an admission observation, not a
promise that the caller will never modify that external directory.

`dos-profile --cpu max --memory-mib 64` can prepare another explicit machine
configuration. Pass the returned profile object as `guest_profile` in a JSON
`debug-launch` request. The ordinary CLI `--guest-profile dos` uses the defaults.
Do not use the Windows-only launch `--memory-mib` flag for this profile.

For an installed QEMM or DESQview configuration, use its existing profile:

```sh
fdisbull debug /private/dos-native.fdb --backend qemu-dos \
  --guest-profile qemm --executable /path/to/qemu-system-x86_64 \
  --game-dir /private --qemu-transport pipe
```

The QEMM/DESQview readers still inspect the selected disk and bind its files;
their live observation rules are unchanged. Profile admission does not prove
that the manager loaded or that scheduling works. See
[DOS drivers and QEMM](DOS_DRIVERS_AND_QEMM.md) and
[DESQview and memory search](DESQVIEW_AND_MEMORY_SEARCH.md).

## Launch an original COM or MZ through DOS

The executable and boot disk are separate inputs. The project binds the
original executable; `--dos-boot-image` selects the DOS installation. Supply
`mcopy` from mtools and a FAT12/FAT16 image with a returning startup batch.
`FDAUTO.BAT` is the default; select `AUTOEXEC.BAT` explicitly for a disk that
uses that name. A partitioned FAT12/FAT16 disk is also admitted within the
64 MiB profile limit.

```sh
fdisbull import /private/game/TARGET.COM /private/target.fdb --image com
fdisbull debug /private/target.fdb --backend qemu-dos \
  --executable /path/to/qemu-system-x86_64 --game-dir /private/game \
  --dos-boot-image /private/DOS.img --dos-mcopy /path/to/mcopy \
  --dos-startup-batch FDAUTO.BAT --dos-arguments ' ALPHA.TXT /Q' \
  --qemu-firmware /path/to/qemu/share/qemu --qemu-transport pipe
```

For a classic MZ EXE, import it normally and use the same debugger options.
JSON `debug-launch` accepts `dos_boot_image`, `dos_mcopy`, `dos_startup_batch`
and `dos_arguments`. The source filename in `game_dir` must still match the
project's original SHA-256. Patched project versions and secondary-format
executable stubs are refused by this initial process path.

Staging copies the selected disk, preserves its configuration and existing
startup bytes, adds the source and an authored loader, and appends the loader
invocation. Existing shell setup executes first. Assets and drivers must
already be present on the image; this route does not import the rest of
`game_dir`. A nonreturning batch, name conflict, changed source, full disk or
loader error fails the launch. Source disk and executable remain unchanged.
COM2 is reserved for the loader's observation protocol.

The launcher uses DOS EXEC load-only, validates the stopped helper report,
PSP, parent, command tail, MCB ownership and full loaded module, then stops at
the child's first instruction. MZ mapping derives from the actual returned
entry, including high-load placement; declared relocations are applied in
order. DOS's exact initial-AX and COM return-zero writes are recorded in
`source_mapping.loader_writes` wherever they overlap file-backed bytes.
Overlay bytes and uninitialized allocation are not misrepresented as loaded
source bytes. Entry DS/ES, SS:SP and initial AX are retained.

Use the returned run ID in that retained debugger server:

```json
{"method":"debug-dos-process","params":{"run":"RETURNED_RUN"}}
{"method":"debug-run","params":{"run":"RETURNED_RUN","timeout_ms":5000}}
{"method":"debug-dos-process","params":{"run":"RETURNED_RUN"}}
```

`debug-dos-process` reports the selected PSP, source map, allocation,
environment segment, FCBs, entry registers, device-header chain and lifecycle.
All register/memory/breakpoint controls still address the native machine.
Use the map's runtime addresses explicitly; a static project address is not
automatically a runtime breakpoint. The map verifies the initial load, not
continuous byte equality after self-modification or subsequent overlay loads.

The reserved parent-return breakpoint separates selected-process completion
from a nested child's exit. A verified DOS return becomes `guest_exit` or
`guest_tsr`; the machine remains owned and stopped. DOS's termination category
does not identify which exit instruction ran. TSR results include observed
retained allocations and before/after interrupt vectors; live source ranges
are clipped to retained allocations. Exit, residency and machine close advance
the capture epoch so old memory-edit plans cannot silently cross lifetimes.
An invalid return report closes the machine and invalidates the binding without
inventing a successful termination. The protocol corroborates guest state;
it is not authentication against a guest that controls its own memory.

Process entry currently requires observed real mode. QEMM, DESQview, DPMI and
V86 process combinations need separate qualification. Existing raw-machine
profiles and report readers remain available. A validated device-chain header
or an authored SYS initialization marker establishes only that observation,
not successful arbitrary driver I/O.

Startup uses one host-time budget across staging and control setup. Execution
timeout recovery may use the existing five-second GDB interrupt allowance;
parent-return observation has a five-second bounded budget, capped by an
enclosing source-trace deadline when present. These are
host control budgets, not DOS cycle or guest-time guarantees.

## Trace the verified DOS process

After original COM/MZ launch stops at its real DOS entry, the existing public
routes can inspect register values and code transitions:

```json
{"method":"debug-trace","params":{"run":"RETURNED_RUN","name":"entry.json","count":8,"timeout_ms":10000}}
{"method":"debug-trace-until","params":{"run":"RETURNED_RUN","until":{"kind":"register","register":"ax","equals":7},"max_steps":100,"timeout_ms":10000,"name":"ax-seven.json"}}
```

The operations are sequential examples: the first advances the process before
the second starts. Use a fresh launch for independent trials. `trace(count=N)`
preserves N attempted stop intervals and N preceding snapshots when successful;
`trace-until(max_steps=N)` records the initial boundary and up to N endpoints.
Budgets count debugger stop intervals, not retired instructions. Predicates
reuse the existing unsigned register comparisons, masked register values,
`pc-range` in project/linear/segmented coordinates, decoded mnemonic,
`region-change`, `nonsequential`, and bounded `all`/`any` combinations.

Every source observation includes actual instruction bytes, full registers,
observed real-mode addressing, selected PSP and the original capture epoch.
Its linear `address` remains available; `segmented_address` records CS:IP and
`identity.project_address` supplies the verified static coordinate. The
runtime instruction hash remains distinct from the canonical source-site hash.
The latter uses the original project's relocation base and exact DOS startup
writes, allowing a normal relocated MZ operand to identify the same site in
independent launches. A changed opcode/decode, relocation crossing an
instruction boundary, unsupported wrapping or an unverified byte sequence
cannot acquire a source-site identity.

QEMU's actual `qqemu.sstepbits` and `qqemu.sstep` replies are retained without
changing the policy. A successful debugger stop does not certify completion:
a fault can stop in its handler and REP can stop after a partial iteration.
`instruction_completed` therefore remains unknown after an attempt. IRQ/timer
masking is reported from the observed mask; this tracing mode does not certify
natural DOS timing or a scheduled task's identity.

The collector checks the selected allocation through the MCB chain and the PSP
parent at each boundary. It checks each decoded instruction against the
verified load, allowing ordinary data writes elsewhere. Leaving the module,
self-modification, a changed allocation, process epoch, hidden segment mapping
or CPU mode stops source capture. It does not silently adopt a new overlay.
User break/watchpoints remain owned by their caller and stop the capture;
the internal parent-return breakpoint retains its lifecycle role.

Saved artifacts work with `event-trace-query`, `event-search-start`,
`event-search-refine` and `event-search-results`, including after exit, session
close and project reopening. Storage rederives original/runtime/canonical bytes
and checks the ordered original entry receipt, artifact receipt, epoch and
instruction identity. A current closed-process state cannot invalidate an
authentic historical capture, and a current live state cannot invent one.
Only closed, qualified observation windows can narrow an event search. A final
unbound boundary may satisfy an explicit runtime predicate, but its open source
window cannot prove absence of a source event or contribute a false site.

Queued `action` input inside `trace-until` remains refused before execution,
including saved-script preflight. Use a bounded natural run to dispatch physical
input, stop at an explicit machine breakpoint, and start a separate source
trace. That earlier run is an unobserved interval, not a contiguous trace or
proof that the input caused a particular instruction.
Raw-disk sessions retain machine traces and do not gain a COM/MZ source binding
or the process-specific `trace-until` method.

## Physical input, clocks and display observations

### Queue explicit controller edges

The native API queues input in Python while the VM is stopped. `run()` sends
one GDB continue, checks QEMU's run state, sends at most one QMP input batch,
and consumes that same GDB stop packet. This preserves breakpoints/watchpoints
and their reasons. It does not start another run when an early stop wins.

```python
# debug is a live qemu-dos session stopped at a known waiting loop.
lease = debug.keyboard.key_down('a')['lease']
debug.keyboard.key_up(lease)
point = debug.breakpoint(known_runtime_consumption_address)
result = debug.run(timeout_ms=5000)
print(result['input_delivery'])
debug.delete_breakpoint(point['breakpoint_id'])
```

The delivery receipt is `qmp_accepted` or `not_dispatched`; `guest_consumed`
remains `None`. An early breakpoint may leave the batch pending, or QEMU may
accept it before the guest consumes anything. Inspect guest RAM/registers or
driver state to establish consumption. A failed/uncertain QMP acknowledgment
closes the owned VM and invalidates its input without replay.

`keyboard_key_down/up` and the `keyboard` namespace use machine-owned leases.
Aliases such as `esc` and `escape` share ownership. The corresponding mouse
methods are `mouse_move_relative(dx, dy)`, `mouse_button_down(button)` and
`mouse_button_up(lease)`. Motion is relative controller movement, not a pixel
coordinate. Buttons are `left`, `middle` and `right`. The authored native
mouse witness handles IRQ12 directly; a real game still needs its own
admitted mouse driver or hardware consumer. This does not emulate DOSBox's
built-in INT33 driver.

`input_state()` reports the owned queue, leases and last delivery. It does not
read the guest's key state or mouse cursor. `input_cancel_pending()` discards
only unsent transitions; an already accepted hold remains owned and needs an
explicit release. Closing the VM invalidates its leases without claiming that
guest release code ran. Ownership is machine-scoped, including after a DOS
child returns to its parent. Limits are 256 pending edges, 64 active leases,
and relative axis deltas within -32767..32767.

Pending input blocks `step()`, traces and unbounded `resume()` before execution;
use a bounded `run()` or cancel it. Timed presses/text, pixel clicks and
frame-edge input are refused until their clock/driver/frame contracts exist.
Queueing make and break together specifies ordering, not a held duration.

The retained JSON server exposes `debug-keyboard-down/up/state`,
`debug-mouse-move-relative`, `debug-mouse-button-down/up`, `debug-input-state`
and `debug-input-cancel-pending`. Native saved scripts use
`keyboard.key-down/up/state`, `mouse.move-relative`, `mouse.button-down/up`,
`input-state` and `input-cancel-pending`; aliases can pass returned leases to
later steps. Failed scripts that touched physical input close the owned VM.
All static input/transaction checks precede earlier script mutations.
The new I/O operations share the script's one host-time deadline, including
lock admission and nested QMP/GDB reads. Existing Windows native snapshots
refuse pending or held machine input before migration because their current
sidecar does not restore these leases; the refusal preserves the live owner.

### Observe a declared clock

The default `qemu_clock='standard'` preserves the ordinary TCG launch. Its
`clock_observe()` explicitly reports the instruction counter as unsupported.
Select `qemu_clock='instruction'` in `Project.debugger` or `debug-launch`,
`--qemu-clock instruction` on the CLI, or `clock_profile='instruction'` in
`Project.machine` to enable the single-vCPU fixed-shift profile:

```text
-accel tcg,thread=single -icount shift=7,align=off,sleep=off
```

`clock_observe()` / `debug-clock-observe` / script `clock-observe` then records
the actual `query-replay.icount` value, a machine epoch, an observation sequence
and a separately labelled host monotonic timestamp. No record/replay mode is
enabled. Malformed or regressing counters invalidate the owned machine.

The counter covers firmware, DOS, interrupts and application execution. It is
not a process clock, a retirement proof or cycle-accurate emulation. In this
profile QEMU can jump its virtual clock to a timer deadline while the CPU is
halted. Consequently `icount * 128` does **not** measure all elapsed guest
nanoseconds. Both `virtual_ns` and `guest_ms` remain `None`. `run(timeout_ms=...)`
retains a host-time budget and a bounded interrupt-recovery allowance; it does
not acquire exact instruction-count or guest-time stopping. The instruction
profile changes timing and must be explicitly chosen for comparisons.

Guest boot delays can also outlast a host startup budget under instruction
counting. The I/O witnesses use an explicit FreeDOS configuration containing
`SWITCHES=/F` to skip its F5/F8 boot-key delay, for both clock profiles. This
choice is confined to those tests. Production preserves the caller's CONFIG
and startup batch; it never inserts that switch, increases the deadline or
changes profile automatically. The [handoff](DOS_QEMU_HANDOFF.md) retains the
original timeout, stopped-state diagnosis and controlled comparison. See the
FreeDOS [SWITCHES reference](https://help.fdos.org/en/hhstndrd/cnfigsys/switches.htm)
when deliberately preparing a separate test image.

### Continue with a native virtual timer

Select `qemu_clock='virtual'` in Python/JSON, `--qemu-clock virtual` on the CLI,
or `clock_profile='virtual'` in `Project.machine`. This profile requires the
explicit [QEMU 10.0.13 clock extension](../native/qemu-clock/README.md), with
one TCG CPU and the same fixed `shift=7,align=off,sleep=off` settings. A stock
executable is rejected while the new machine is still paused. The `standard`
and `instruction` profiles continue to work with stock QEMU.

The extension reads `qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)` directly.
`clock_observe()['virtual_ns']` therefore includes QEMU's idle-time advances.
The instruction counter remains a separate value, and `guest_ms` remains
`None`: this is a declared QEMU clock domain, not the legacy DOSBox scheduler.
The native epoch, executable identity and admission receipt remain attached
to the owned machine. A reset, unsupported restore/runstate, changed epoch
or regressing clock invalidates the observation.

```python
with project.debugger(qemu_with_clock_extension, game_dir,
        backend='qemu-dos', dos_boot_image=dos_image, dos_mcopy=mcopy,
        qemu_clock='virtual') as debug:
    before = debug.clock_observe()
    result = debug.clock_advance(20_000_000, timeout_ms=3000)
    budget = result['clock_budget']
    # Inspect both the actual native stop and the timer receipt.
    print(result['outcome'], budget['deadline_reached'], budget['elapsed_ns'])
```

The matching JSON method is `debug-clock-advance` with `run`, `delta_ns` and
optional `timeout_ms`. Saved scripts use `clock-advance` and may assert
`$advance.clock_budget.deadline_reached` explicitly. Each call accepts an
integer duration from 1 ns to 60 seconds, arms one native virtual timer and
issues exactly one ordinary GDB continue. Earlier breakpoints, watchpoints,
DOS exit/TSR and physical-input receipts remain visible. There is no automatic
continuation to consume the rest of the duration. A successful input dispatch
still does not certify consumption by a guest driver.

The receipt separates `start_ns`, `deadline_ns`, `fired_ns`, `stopped_ns`,
`elapsed_ns` and `overshoot_ns`. `deadline_reached` means the native timer
fired; it does not establish that the timer was the only concurrent stop
cause. An earlier stop has no firing time or overshoot. QEMU rounds busy
execution to instruction quanta, and other due callbacks can share a
boundary, so this API does not promise an exact arbitrary-nanosecond cutoff
or cycle accuracy. The extension's own pause produces GDB SIGINT; genuine
debugger traps retain SIGTRAP, preventing a timer stop at a matching PC from
being relabelled as a breakpoint or DOS return.

The host deadline starts before machine-lock admission and covers startup of
the debugger channel, observation, arm, continue, register/process readback,
token-bound cleanup and evidence persistence. It also respects any shorter
script or channel deadline. GDB retains its existing bounded interrupt
recovery, but that allowance cannot authorize another run or fresh clock
cleanup. An uncertain arm, unconfirmed disarm, expired post-execution budget
or failed execution evidence closes the owned VM. The timer and its deferred
stop request must both be absent before another operation is admitted.

This first extension blocks migration after budget use. Native checkpoints,
completed-frame/audio fences, timed input helpers, periodic memory rules and
scene scheduling still need their own integration and qualification.

### Capture a stopped display surface

`capture_surface(name)` / `debug-capture-surface` / script `capture-surface`
stores PNG bytes with a unique capture ID, run identity, dimensions, SHA-256,
selected-CPU registers and before/after clock observations. The entire bracket
holds the owned machine lock with QEMU stopped. `screenshot()` uses the same
capture path and retains optional grid annotation.

The metadata source is `qemu_display_surface`; `completed_guest_frame` and
`guest_frame_id` are `None`. A capture can show a half-drawn guest scene. A new
capture ID does not establish a new guest frame or input consumption. Standard
clock capture reports `clock_stability='not_observable'`; the instruction
profile can establish only an unchanged observed instruction counter. The
virtual profile checks both the direct virtual clock and instruction counter.
A changed stopped CPU/clock bracket closes the VM and refuses the capture.
Existing DOSBox frame-coherence consumers cannot accept this surface as a
`last_completed_guest_frame`.

Native evidence for this path uses QEMU 10.0.13 and FreeDOS 1.4, with independent
authored BIOS/IRQ programs. It separates queued input, QMP acceptance, BIOS or
IRQ consumption, and the program's later VGA drawing boundary. It does not
qualify arbitrary DOS drivers, QEMM/DESQview, Windows, audio or a real game.

Primary implementation references are QEMU's
[instruction-counting design](https://www.qemu.org/docs/master/devel/tcg-icount.html),
[icount invocation options](https://www.qemu.org/docs/master/system/invocation.html),
and [QMP input, screendump and replay commands](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html).
Those moving upstream manuals describe a newer development version; the
handoff records the actual installed version used for native acceptance.

## What the first slice does and does not qualify

The native tests use independent authored boot and DOS-service fixtures. They
check nonzero `CS:IP` versus linear-PC identity, execution and data controls,
physical/virtual reads, guarded edits, memory searches, stored traces and PNGs,
bounded-run interruption followed by usable control, reopened artifacts, a
fresh machine, source isolation and process cleanup. The real DOS case calls
DOS interrupts and checks the probe's nonce, reported CPU state and VGA output.
It does not stand in for QEMM, DESQview, a game or Windows.

Native machine stops affect the machine's vCPUs. A vCPU is not a DOS task or
Windows thread. Runs are bounded by host time; instruction stepping follows
QEMU's debugger semantics and does not establish original-machine cycle timing.
Stored-surface PNG capture is distinct from the DOSBox completed-frame contract.

Native event searches cover the verified initial real-mode DOS module, not a
whole-program execution history, arbitrary driver mapping or unpacked original
entry discovery. Periodic memory rules also remain blocked until
the guest-clock slice is implemented; explicit stopped `memory-rule-tick` is
available.

Hostcalls and UDL/UIL block services remain a later slice. The earlier lab's
custom opcodes and plugins are not enabled by this launcher, and experimental
`FDB_HOSTCALL_*`/`FDB_LAYER_*` environment selectors are removed from the child.
The layer slice must preserve separate fetch/data views, selection precedence,
translation invalidation and declared host-effect ownership before it can
replace the existing DOSBox machinery.

## Run the migration gates

The source coverage gate derives the current DOSBox API from the code and
compares it with the packaged ledger. New methods must acquire a slice and
disposition. Test names in the ledger describe required witnesses; they are
not automatically reported as passed.

```sh
python -m pytest -q tests/test_dos_migration.py tests/test_qemu_dos.py tests/test_qemu_pipe.py

FDISBULL_QEMU_DOS=/path/to/qemu-system-x86_64 \
FDISBULL_QEMU_DOS_FIRMWARE=/path/to/qemu/share/qemu \
FDISBULL_REQUIRE_QEMU_DOS=1 \
python -m pytest -q tests/test_qemu_dos_native.py tests/test_qemu_doctor.py
```

The independent FreeDOS case additionally accepts
`FDISBULL_QEMU_DOS_BOOT_IMAGE` and `FDISBULL_QEMU_DOS_MCOPY`. Set
`FDISBULL_REQUIRE_QEMU_DOS_OS=1` to require those inputs and refuse an OS-test
skip. The test edits a private copy to install its authored probe; no vendor
image or runtime state belongs in Git or the wheel. A build without stored
display support cannot pass the complete graphics/native acceptance lane.

For the process slice, run `tests/test_qemu_dos_process_native.py` and
`tests/test_qemu_dos_process_lifecycle.py` with those same required inputs and
`NASM=/path/to/nasm`. NASM assembles independent test programs; production uses
the packaged authored helper and needs no assembler. The helper's readable
source/template equality is checked by `tests/test_dos_process_helper.py`
with `FDISBULL_NASM=/path/to/nasm` and
`FDISBULL_REQUIRE_DOS_HELPER_ASSEMBLY=1`.

The trace slice adds `tests/test_qemu_dos_trace_native.py` and
`tests/test_qemu_trace_semantics_native.py` with the same required native
inputs. Source/persistence and protocol checks are separate from these actual
guest witnesses. Consult the handoff log for the exact run results and scope.

The clock/input slice adds `tests/test_qemu_io_native.py` using the same required
QEMU/FreeDOS/mcopy/NASM inputs. It covers physical consumption and release,
pre/post-draw pixels, early-stop races, clock domains, stale leases, public
JSON/scripts and terminal failure cleanup. `tests/test_qemu_clock.py`,
`tests/test_qemu_input.py`, `tests/test_qemu_surface.py` and
`tests/test_qemu_io_public.py` cover malformed receipts and public preflight.

Rehearse the retained path with a separate original DOS program project:

```sh
fdisbull debug /private/game.fdb --backend dosbox \
  --executable /path/to/patched/dosbox-x --game-dir /private/game
```

After migration, keep this explicit selector, its backend preparation route,
and regression tests. Default promotion requires each remaining surface's
native evidence, real compatibility campaigns, cold restore and a fallback
rehearsal. Retaining DOSBox is part of the migration contract even after those
gates pass.
