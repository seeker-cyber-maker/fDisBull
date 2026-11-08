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

This is an alternative for testing now. Frame/input machinery, checkpoints and
execution layers remain later slices. The default-switch gate remains blocked until the outstanding slices
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

Queued `action` input is refused before any execution, including saved-script
preflight, until the clock/media/input slice qualifies dispatch and consumption.
Raw-disk sessions retain machine traces and do not gain a COM/MZ source binding
or the process-specific `trace-until` method.

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
