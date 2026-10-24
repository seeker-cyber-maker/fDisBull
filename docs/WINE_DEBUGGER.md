# PE64 Wine/QEMU debugger (0.12.0)

fDisBull 0.12.0 can launch an original x86-64 PE executable under Wine inside a disposable x86-64 Linux QEMU guest. Static disassembly stays on the host. The published 0.11.0 packages predate this integration.

The backend provides disassembly-address execution breakpoints, register observations, guarded memory edits, bounded instruction traces, actual client-window screenshots, coordinate grids and mouse clicks. Runs, edits, screenshots and traces use the same persistent project timeline and artifact/export commands as DOS. Closing a project or its foreground server terminates and reaps its QEMU process.

## Runtime preparation

Supply QEMU, an x86-64 Linux kernel, and a trusted Linux initramfs containing Wine64, Python 3, Xvfb, `runuser`, and `x86_64-w64-mingw32-gcc`, with the `ubuntu` user and group (UID/GID 1000) used by the supplied guest launcher. The tested Ubuntu 24.04 runtime preparation and its provenance are described in [the platform experiment](../experimental/wine/README.md). That original image is a base: its old probe launcher is replaced in a **new** prepared image. No games, saved states or project databases enter the prepared runtime.

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

Alternatively use `debug-launch` in `fdisbull serve` with `executable`, `game_dir`, `backend`, `kernel`, `initramfs`, and optional `version`, `files`, `boot_timeout_ms`. The returned `run` owns the live session. Use `debug-breakpoint`, `debug-run`, `debug-registers`, `debug-memory`, **`debug-write-memory`** (`address`, `data_hex`, `expected_hex`), `debug-trace`, `debug-screenshot`, `debug-click`, `debug-click-frame`, `debug-delete-breakpoint`, and `debug-stop`. Screenshots and traces remain available through `debug-artifacts`, `debug-grid` and `debug-export` after process and project restart. Declarative scripts support this same PE operation subset, including `write-memory`; unsupported DOS steps are rejected before script execution.

## Address and execution semantics

Project addresses are preferred-image virtual addresses. Runtime addresses are calculated as `observed main-module image base + RVA`. Breakpoints require a stored instruction boundary and compare the complete instruction against runtime logical bytes, applying PE DIR64 base relocations to the expected view when rebased. The original file bytes and static versions remain unchanged. External DLL and private/JIT addresses in traces have no project address rather than being guessed into the main module.

Execution breakpoints use owned INT3 bytes. The agent restores the displaced byte and instruction pointer when hit, executes that instruction with peer threads held, flushes the instruction cache and rearms the breakpoint. Memory reads present the original bytes hidden beneath owned INT3s. Memory edits require explicit expected bytes, reject overlap with active breakpoints, restore page protection and verify readback. They are recorded as runtime events.

`run(timeout_ms=...)` continues until a breakpoint, exception, process exit or host-duration timeout. A timeout requests a Windows debug break and returns a stopped session; it is not successful completion. Other exceptions retain their first-chance/code information and are passed to the program on continuation. `registers()` returns `rip`, `rflags`, `general`, `thread` and `project_address`.

Traces single-step the selected stopped thread and record **completed instructions with pre-instruction registers and real observed bytes**. Peer threads are held during each step. A breakpoint, exception, exit or time limit can make a trace incomplete; inspect `metadata.complete`. If an individual step cannot complete before its deadline, the VM closes rather than claiming a resumable stop. This is instruction tracing, not a complete memory-access log or a scheduler-faithful recording.

Screenshots capture the visible target window's client rectangle in the guest's headless Xvfb desktop using Win32 GDI. Coordinates are native client pixels with the origin at top left. Grids are derived from saved clean PNGs. `click-frame` stores and labels the frame before queuing Win32 `SendInput` mouse motion/down/up. The target consumes input when resumed. The PE click currently queues down and up together; DOS `hold_ms` timing is not applied. A frame-bound click checks window identity and dimensions. There is one selected visible client window (the largest); DirectX/fullscreen rendering, occluded windows and multi-window selection have not been qualified.

## Verification and limits

Run the real acceptance gate with an authored executable compiled from `tests/wine_gui_fixture.c` (MinGW `-O0 -g -mwindows`, linking user32 and gdi32):

```bash
FDISBULL_PE_QEMU=/path/to/qemu-system-x86_64 \
FDISBULL_PE_KERNEL=/path/to/linux-amd64 \
FDISBULL_PE_INITRAMFS=/path/to/fdisbull-wine-runtime.cpio.gz \
FDISBULL_PE_FIXTURE=/path/to/oracle.exe \
FDISBULL_REQUIRE_PE=1 \
python -m pytest -q tests/test_wine_debugger.py
```

The explicit gate fails when inputs are missing. Ordinary tests skip the VM acceptance if no runtime is supplied. This fixture is authored source, not a shipped game. The native CI workflow builds a separate minimal Linux/Wine runtime from [the CI recipe](../experimental/wine/ci/README.md) and runs this gate against an installed wheel in two fresh QEMU sessions. See [PE64 verification and receipts](PE64_VERIFICATION.md) for the installed-wheel, restart, input, trace and offline-export results.

The initial scope is native **PE64 x86-64 EXEs and the main image**. DLL launch, child-process following, PE32/WoW64, managed/.NET source debugging, heap/JIT imports, data watchpoints, DOS guest-time/fast-forward, code layers and resumable state editing are unsupported. Wine minidumps are not emulator checkpoints. Wine compatibility with an arbitrary game is not established by the authored GUI fixture.

[Historical planning and source research](WINE_DEBUGGER_RESEARCH.md) and [the Rosetta versus QEMU probe](../experimental/wine/README.md) preserve the earlier feasibility work. The Win32 implementation follows Microsoft's [debug event loop](https://learn.microsoft.com/en-us/windows/win32/debug/writing-the-debugger-s-main-loop), [memory-write API](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-writeprocessmemory), and [input API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput); Wine support is established only by the recorded real runs.
