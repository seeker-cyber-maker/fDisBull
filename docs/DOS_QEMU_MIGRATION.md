# Native QEMU DOS migration

`qemu-dos` starts the DOSBox-X migration with an explicit, native QEMU PC
backend. It boots a caller-owned disk directly. `dosbox` remains the default
for DOS programs, and both DOSBox choices remain selectable after the migration.

The first slice supplies owned startup/shutdown, private disk isolation,
capability discovery, stopped CPU/RAM inspection and edits, break/watchpoints,
bounded execution, instruction traces and stored-display screenshots. Existing
memory snapshots, searches, guarded edits and explicit rule ticks use the
native machine context. The [capability inventory](DOSBOX_QEMU_CAPABILITY_INVENTORY.md)
tracks every existing DOSBox protocol method and public debugger route, plus
capabilities that a method count misses.

This is an alternative for testing now. It is not yet a replacement for the
DOSBox COM/MZ process launcher, frame/input machinery, checkpoints or execution
layers. The default-switch gate remains blocked until the outstanding slices
and compatibility campaigns are qualified. No command here changes the default.

## Select the execution environment

| Backend | What executes | Input and scope |
| --- | --- | --- |
| `dosbox` | The existing patched DOSBox-X | Existing DOS program project; retained default and fallback |
| `dosbox-qemu` | DOSBox-X inside a prepared Linux/QEMU guest | Existing DOS project plus Linux kernel/initramfs; retained fallback |
| `qemu-dos` | DOS or an authored boot program directly on QEMU's virtual PC | Original raw disk project; single TCG vCPU, explicit physical/virtual addresses |
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

The existing whole-program event-search adapter still requires its qualified
DOSBox/PE mappings. `qemu-dos` can retain completed-step machine traces, but it
does not claim `trace-until`, action causality, original-entry discovery or
source-bound event narrowing. Periodic memory rules also remain blocked until
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
