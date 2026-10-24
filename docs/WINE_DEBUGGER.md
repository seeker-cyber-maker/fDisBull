# PE64 Wine/QEMU debugger

fDisBull 0.12.0 can launch an original x86-64 PE executable under Wine inside a disposable x86-64 Linux QEMU guest. Static disassembly stays on the host. The published 0.11.0 packages predate this integration.

**Current source: 0.13.0.** The watches, layers, register editing and whole-VM state features below require the 0.13 package and a newly prepared matching guest runtime. Published 0.12.0 packages and their existing delivery remain unchanged. [Development acceptance and evidence](PE64_ADVANCED_VERIFICATION.md) is separate from [0.12.0 release verification](VERIFICATION-0.12.md).

The [published 0.13.0 delivery](DELIVERY-0.13.md) supplies the exact packages and a separately tested Mac ARM64 backend/runtime, with integrity checks and agent launch helpers. Its compatibility and copied-pair evidence are distinct from Linux tag CI.

The backend provides disassembly-address execution breakpoints, register observations, guarded memory edits, bounded instruction traces, actual client-window screenshots, coordinate grids and mouse clicks. Runs, edits, screenshots and traces use the same persistent project timeline and artifact/export commands as DOS. Closing a project or its foreground server terminates and reaps its QEMU process.

## Runtime preparation

Supply **QEMU 9.1 or later**, an x86-64 Linux kernel, and a trusted Linux initramfs containing Wine64, Python 3, Xvfb, `runuser`, and `x86_64-w64-mingw32-gcc`, with the `ubuntu` user and group (UID/GID 1000) used by the supplied guest launcher. Older QEMU TCG versions mishandle user-mode IRET with guest SMAP, which caused a real guest-kernel fault during Wine initialization in the first Linux PE CI run; the launcher rejects them before boot. See the [upstream fix](https://lists.gnu.org/archive/html/qemu-devel/2024-07/msg02430.html) and [CI recipe](../experimental/wine/ci/README.md). The tested Ubuntu 24.04 runtime preparation and its provenance are described in [the platform experiment](../experimental/wine/README.md). That original image is a base: its old probe launcher is replaced in a **new** prepared image. No games, saved states or project databases enter the prepared runtime.

```bash
python -m fdisbull.wine_runtime \
  --base-initramfs /path/to/trusted-linux-wine-base.cpio.gz \
  --output /path/to/fdisbull-wine-runtime.cpio.gz
```

Preparation reads a gzip/newc archive with expanded hard links, preserves the base file, refuses to overwrite an existing output, adds packaged guest sources, and writes an input/output SHA-256 receipt. It streams a compact image, removing the old experiment’s Python environment, tests, probes, DOSBox build and package-manager documentation/cache. Those initramfs files consume guest RAM even when unused. The guest compiles the Windows debug agent and waits for its headless X server before accepting a target. The launcher uses `rootfstype=ramfs` for the runtime root, avoiding Linux’s default tmpfs root quota during unpacking; game writes remain in bounded tmpfs mounts. [Linux rootfs documentation](https://www.kernel.org/doc/Documentation/filesystems/ramfs-rootfs-initramfs.txt). The host checks the protocol and all three guest source hashes against its installed package, and records the compiled agent hash, Wine version and guest kernel. Rebuild the runtime when that source changes; a mismatch is rejected.

A session uses 2 virtual CPUs and 4 GiB of memory with QEMU TCG. Booting and initializing a new Wine prefix is substantially slower than DOSBox. Allow up to 240 seconds for boot and up to 300 seconds for the initial launch. Calls have finite deadlines; an uncertain transport or native operation closes the VM rather than replaying a mutation.

The guest has no network device, host directory shares, clipboard, host display or published port. Target files are copied through the private serial channel into guest RAM. By default only the project executable is copied. For a program requiring assets, supply an explicit `files` list of relative paths including the EXE (maximum 1,024 files and 64 MiB total). Symbolic links, project databases and state extensions are rejected. Writes made by the target stay in the disposable guest and are lost on close.

## Python and foreground JSON interface

```python
from fdisbull.project import Project

with Project("sample.fdb") as project:
    project.analyze(start="0x140001530", max_instructions=100)
    with project.debugger(
        "/opt/homebrew/bin/qemu-system-x86_64", "/path/to/program",
        backend="wine-qemu", kernel="/path/to/linux-amd64",
        initramfs="/path/to/fdisbull-wine-runtime.cpio.gz", version=1,
    ) as debug:
        bp = debug.breakpoint("0x140001530")
        stopped = debug.run(timeout_ms=30000)
        print(stopped, debug.registers())
        before = debug.memory("0x140003010", length=4)
        debug.write_memory("0x140003010", "29000000", expected_hex=before["hex"])
        debug.trace("path.json", count=32, timeout_ms=20000)
        debug.screenshot("window.png", grid=True, grid_step=8)
        debug.click_frame(80, 80, name="click.png", grid_step=8)
        debug.run(timeout_ms=30000)
```

The example addresses must be replaced with analyzed addresses from the selected project. The original EXE must match the imported source SHA-256. Select `version=1` explicitly if a static patch version is current: static child patches are never applied implicitly.

For agents using JSON lines:

```bash
fdisbull debug sample.fdb --backend wine-qemu \
  --executable /path/to/qemu-system-x86_64 --game-dir /path/to/program \
  --kernel /path/to/linux-amd64 --initramfs /path/to/fdisbull-wine-runtime.cpio.gz \
  --version 1
```

Alternatively use `debug-launch` in `fdisbull serve` with `executable`, `game_dir`, `backend`, `kernel`, `initramfs`, and optional `version`, `files`, `boot_timeout_ms`, `state`. The returned `run` owns the live session. Use `debug-breakpoint`, `debug-run`, `debug-registers`, `debug-memory`, **`debug-write-memory`** (`address`, `data_hex`, `expected_hex`), `debug-trace`, `debug-screenshot`, `debug-click`, `debug-click-frame`, `debug-delete-breakpoint`, and `debug-stop`. Screenshots and traces remain available through `debug-artifacts`, `debug-grid` and `debug-export` after process and project restart. Declarative scripts support the PE operations described here; unsupported DOS steps are rejected before script execution.

## Address and execution semantics

Project addresses are preferred-image virtual addresses. Runtime addresses are calculated as `observed main-module image base + RVA`. Breakpoints require a stored instruction boundary and compare the complete instruction against runtime logical bytes, applying PE DIR64 base relocations to the expected view when rebased. The original file bytes and static versions remain unchanged. External DLL and private/JIT addresses in traces have no project address rather than being guessed into the main module.

Execution breakpoints use owned INT3 bytes. The agent restores the displaced byte and instruction pointer when hit, executes that instruction with peer threads held, flushes the instruction cache and rearms the breakpoint. Memory reads present the original bytes hidden beneath owned INT3s. Memory edits require explicit expected bytes, reject overlap with active breakpoints, restore page protection and verify readback. They are recorded as runtime events.

`run(timeout_ms=...)` continues until a breakpoint, exception, process exit or host-duration timeout. A timeout requests a Windows debug break and returns a stopped session; it is not successful completion. Other exceptions retain their first-chance/code information and are passed to the program on continuation. `registers()` returns `rip`, `rflags`, `general`, `thread` and `project_address`.

Traces single-step the selected stopped thread and record **completed instructions with pre-instruction registers and real observed bytes**. Peer threads are held during each step. A breakpoint, exception, exit or time limit can make a trace incomplete; inspect `metadata.complete`. If an individual step cannot complete before its deadline, the VM closes rather than claiming a resumable stop. This is instruction tracing, not a complete memory-access log or a scheduler-faithful recording.

Screenshots capture the visible target window's client rectangle in the guest's headless Xvfb desktop using Win32 GDI. Coordinates are native client pixels with the origin at top left. Grids are derived from saved clean PNGs. `click-frame` stores and labels the frame before queuing Win32 `SendInput` mouse motion/down/up. The target consumes input when resumed. The PE click currently queues down and up together; DOS `hold_ms` timing is not applied. A frame-bound click checks window identity and dimensions. There is one selected visible client window (the largest); DirectX/fullscreen rendering, occluded windows and multi-window selection have not been qualified.

<a id="pe64-watches-layers-and-native-states-013-development"></a>

## PE64 watches, layers and native states (0.13.0)

### Read/write watchpoints

```python
watch = debug.breakpoint("0x140004000", access="rw", length=4)
result = debug.run(timeout_ms=30000)
if result["outcome"] == "watchpoint":
    print(result["session"]["stop_reason"]["access_facts"], debug.registers())
debug.delete_breakpoint(watch["breakpoint_id"])
```

`access` accepts `x`, `r`, `w`, or `rw`. Data watches use flat project addresses and 1..65,536 bytes; at most 64 native watch ranges are active, with a shared budget of 512 distinct guard pages across watches and execution layers. They do not need an analyzed instruction at the watched data address. `bytes_verified:false` distinguishes them from code breakpoints. The host translates the address using the observed main-image relocation.

The native agent uses Windows `PAGE_GUARD`, and the host's iced decoder resolves the faulting scalar operand's address, width and access. A one-byte watch inside a four-byte store catches the overlapping store. A read-only watch ignores a pure store; a read-modify-write instruction reports both accesses when the native write fault identifies it. Stops are **before access**: the old memory value is still available. Continuing completes that instruction with peer threads held, then rearms the guards. Debugger memory reads and edits do not trigger their own watches.

This is a qualified scalar-access mechanism, not complete memory-access tracing. Repeated/string, multiple-memory-operand, VSIB, FS/GS-relative and unresolved-width/address cases are rejected if encountered on a guarded access. Fetching can clear a guard on a page containing both code and watched data; an instruction accessing that same page is rejected. These classification failures close the owned VM rather than allowing continuation with a silently cleared watch. Page protections are observable and guest protection changes can invalidate guards. The implementation follows the [Windows one-shot guard-page mechanism](https://learn.microsoft.com/en-us/windows/win32/memory/creating-guard-pages).

### Toggleable code layers and branch theories

```python
ram = debug.layer_patch("RAM theory", "0x140003001",
    expected_hex="01000000", data_hex="02000000", kind="ram")
debug.layer_enable(ram["layer"], enabled=False)
alternate = debug.layer_patch("execution theory", "0x140003001",
    expected_hex="01000000", data_hex="03000000", kind="execute")
debug.code("0x140003000", length=6, view="ram")
debug.code("0x140003000", length=6, view="execute")
debug.layer_enable(alternate["layer"], enabled=False)
```

These addresses illustrate the authored fixture; inspect your program's live bytes first. Definitions are immutable, version-bound records shared with the [layer API](CODE_LAYERS.md). `debug.layers([ID_A, ID_B])` switches an ordered stack, `layer_enable` toggles it, and `capture_code` persists an observed view without changing static analysis or xrefs. Layer switches preflight expected bytes and hold the target paused. Disable overlapping layers or delete owned execution breakpoints before directly editing their bytes. A breakpoint overlapping a layer transition refuses that transition.

`ram` layers change guest-visible memory and restore the guarded baseline on disable. A software self-CRC sees the changed RAM. `execute` layers preserve original source RAM, including data reads by the alternate instruction itself. The host intercepts a guarded fetch, uses iced's x64 block encoder to relocate one alternate instruction into a **private 4 KiB guest allocation**, executes it with peer threads held, and maps fallthrough back to the original address. Traces retain original RAM bytes, alternate execution bytes and the native scratch address/bytes. Guards and relocation add substantial host overhead and alter timing. This is not a zero-footprint or undetectability guarantee; owned INT3s and guard protections are separately observable.

The qualified subset is single-instruction relocations of ordinary instructions and Jcc/JMP. Calls, returns, interrupts and relocations requiring multiple physical instructions are rejected. Exotic instructions exposing native execution addresses, exceptions within relocated instructions, and arbitrary SIMD/FPU/system-instruction behavior have not been qualified. A watch inside an alternate instruction preserves a pending operation; finish it before switching layers, editing registers or saving a state.

`debug.branch(name, address, mode="invert"|"taken"|"fallthrough")` supports unprefixed x64 short/near Jcc. DOS virtual caves, breakpoint action hooks and live-view execution breakpoints are not implemented for PE; execution breakpoints still require analyzed original instructions.

### Whole-VM states and editable forks

```python
parent = debug.save_state("parent.sav")
debug.write_memory("0x140004000", "29000000", expected_hex="11000000")
debug.load_state(parent["artifact"])
```

`save_state` uses QMP native migration to capture the complete emulated machine: CPU/RAM/devices, Linux, Wine, the target, Xvfb and guest RAM-backed files. It is an actual resumable machine state, not a Wine minidump. The target stays in its Windows debug stop; Linux/broker services run around capture. The QMP migration stream is stopped, gzip-compressed and hashed. A new QEMU process can restore it with `project.debugger(..., state=ARTIFACT_ID)`, or the CLI's `debug ... --state ARTIFACT_ID`. `load_state` replaces the current owned VM and restores the saved watches, layer stack and original register values.

For a new session restored from a state, supply the same explicit `files` list as the original launch if it included assets beside the EXE. State forking reconstructs that saved allowlist automatically and verifies every original host input hash.

The project stores a small immutable manifest. The native image is a read-only, SHA-256-named file under **`PROJECT.fdisbull-states/`** beside the database. Preserve both together. `debug_state_info` verifies the sidecar offline, and `debug_export` writes a ZIP containing `state.json` and `machine.mig.gz`. The export's checksum differs from the manifest artifact checksum; both are returned. No standalone state-import operation is provided. Limits are 2 GiB compressed and 8 GiB expanded per checkpoint, 6 GiB per project's native sidecar, and at least 2 GiB free before capture. The tested fixture uses roughly 950 MB per state.

Exact QEMU, kernel, prepared runtime, uploaded program files, original static version and saved layer hashes must match. Restoring reattests the broker and guest source identities. This does not promise cross-QEMU, cross-runtime or cross-platform compatibility. It restores guest RAM-backed files; it cannot undo host files. Native states and databases can contain all program bytes and data and are local artifacts excluded from Git and packages.

Fork memory and 64-bit GPR state while keeping the parent immutable:

```python
child = project.debug_fork_state(
    parent["artifact"], "/path/to/qemu-system-x86_64", "/path/to/program",
    kernel="/path/to/linux-amd64", initramfs="/path/to/matching-runtime.cpio.gz",
    memory=[{"address":"0x140004000", "expected_hex":"11000000", "data_hex":"33000000"}],
    registers={"rax":{"expected":"0x0", "value":"0x123456789abcdef0"}},
)
```

Use actual saved expected values. All memory/register preconditions are checked before any edit. A fresh VM restores the parent, reuses its explicit program/asset upload allowlist and verifies the original host file hashes, applies and verifies the edits with **no target EXE instructions executed during editing**, captures the derived native machine, then closes. Linux/broker services run during the operation. Edits cover mapped main-image memory (up to 64 nonoverlapping ranges totaling 64 KiB), the sixteen 64-bit GPRs, RIP, and arithmetic/direction RFLAGS bits. TF and other debugger/control bits are reserved. Overlapping active layers/software breakpoints must be disabled first. Device structures are not directly edited. A mutation or readback failure closes the VM.

`debug.write_registers({"rax":{"expected":"0x0","value":"0x123456789abcdef0"}})` applies the same checked register edits to a live paused PE session. The JSON method is `debug-write-registers`; declarative scripts use `write-registers`. Scripts also accept `write-memory`, `save-state`, `load-state`, `layer-stack`, `layer-enable`, `layer-patch`, `code`, `capture-code`, and `branch`. A script can restore an edited state, navigate with `click-frame` and an 8px grid, run to a breakpoint, and retain screenshots/traces in one bounded request.

Register values, including RIP, are actual runtime values; memory/layer addresses are project addresses. RIP preflight maps the supplied runtime value through the observed ASLR delta before checking that it is executable main-image code. The rebased-address validation has a static mapping regression check; the real state test edits memory and RAX rather than forcing a rebased RIP redirect.

For the one-shot fork CLI use `debug-fork-state PROJECT ARTIFACT --backend wine-qemu --executable QEMU --game-dir DIRECTORY --kernel KERNEL --initramfs RUNTIME`, with `--memory` and `--registers` JSON values. These same extra backend arguments are accepted by the foreground JSON interface.

## Verification and limits

Run the real acceptance gate with an authored executable compiled from `tests/wine_gui_fixture.c` (MinGW `-O0 -g -mwindows`, linking user32 and gdi32):

```bash
FDISBULL_PE_QEMU=/path/to/qemu-system-x86_64 \
FDISBULL_PE_KERNEL=/path/to/linux-amd64 \
FDISBULL_PE_INITRAMFS=/path/to/fdisbull-wine-runtime.cpio.gz \
FDISBULL_PE_FIXTURE=/path/to/oracle.exe \
FDISBULL_REQUIRE_PE=1 \
python -m pytest -q tests/test_wine_debugger.py tests/test_wine_advanced.py
```

The explicit gate fails when inputs are missing. Ordinary tests skip the VM acceptance if no runtime is supplied. This fixture is authored source, not a shipped game. The native CI workflow builds a separate minimal Linux/Wine runtime from [the CI recipe](../experimental/wine/ci/README.md) and runs this gate against an installed wheel. Native state tests add fresh restored VMs after closing the original owner. See [published PE64 verification](PE64_VERIFICATION.md) and [development acceptance](PE64_ADVANCED_VERIFICATION.md) for their separate results.

The scope is native **PE64 x86-64 EXEs and the main image**. DLL launch, child-process following, PE32/WoW64, managed/.NET source debugging, heap/JIT imports, DOS guest-time/fast-forward and DOS virtual caves/hooks are unsupported. Watches, layers and native editing are 0.13 additions with the limits above. Wine compatibility with an arbitrary game is not established by the authored GUI fixture.

[Historical planning and source research](WINE_DEBUGGER_RESEARCH.md) and [the Rosetta versus QEMU probe](../experimental/wine/README.md) preserve the earlier feasibility work. The Win32 implementation follows Microsoft's [debug event loop](https://learn.microsoft.com/en-us/windows/win32/debug/writing-the-debugger-s-main-loop), [memory-write API](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-writeprocessmemory), and [input API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput); Wine support is established only by the recorded real runs.
