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
| `qemu-dos` | Native QEMU PC boot from an original raw disk project |
| `qemu-machine` | Existing generic raw machine and QEMM/DESQview contexts |

Native QEMU currently supplies machine controls, physical/virtual memory,
guarded edits, break/watchpoints, completed-step trace artifacts, stored PNGs
when the QEMU build supports them, and stopped memory snapshot/search/edit/rule
operations. It does not yet supply source-bound COM/MZ launch, selected-PSP
exit/TSR tracking, frame-timed input, native checkpoints, fetch layers, event
predicate tracing or DOSBox scene parity. Periodic memory rules need the later
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
