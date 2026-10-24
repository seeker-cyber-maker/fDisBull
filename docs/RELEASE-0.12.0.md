# fDisBull 0.12.0

This release connects PE64 static disassembly to a real Wine debugger running inside an offline x86-64 Linux QEMU guest. Agents can launch the original executable, stop at analyzed disassembly addresses, inspect and edit memory with byte guards, capture bounded instruction traces, and drive a client window with screenshots and mouse clicks. Screenshots, traces and scripts remain project artifacts that can be exported after the emulator and project restart.

## PE64 debugger

- Map preferred-image project addresses through the observed runtime main-module base. Verify stored instruction bytes before installing execution breakpoints; apply DIR64 relocations to the comparison view without changing original static bytes.
- Preserve displaced instructions, rewind RIP when a breakpoint is hit, step with peer threads held, and rearm breakpoints. Logical memory reads hide the debugger's owned INT3 bytes.
- Require expected bytes for memory writes, reject overlap with active breakpoints, restore page protection and verify readback. Record runtime edits separately from static versions.
- Bound runs by breakpoint, exception, exit or timeout. A timeout returns a stopped session; it does not claim execution completed. Bounded traces record completed instructions with observed bytes, pre-instruction registers and project mappings.
- Capture actual GDI client pixels and queue Win32 mouse input using native client coordinates. Reuse the 8px grid and click-frame workflow and export stored images without operating a GUI.
- Expose the backend through the Python project API, foreground JSON interface and supported script operations. Reject unsupported DOS-only script steps before any guest edit.

## Runtime sources and qualification

The tool packages include the Win32 debugger agent C source, guest broker and launcher, runtime preparation code and authored GUI test fixture source. QEMU **9.1 or later**, Wine, the Linux kernel and the prepared runtime image are separate inputs. The QEMU minimum avoids an upstream user-mode IRET/SMAP emulation defect observed during Linux qualification; CI builds pinned QEMU 9.2.4. The guest has no network device or host directory share; explicit program files are copied into guest RAM through a private serial channel. This execution arrangement is not a security-isolation claim.

The [verification record](PE64_VERIFICATION.md) preserves the earlier Mac installed-wheel acceptance and its screenshots, trace, script and hash-bound receipts. Linux package CI and required native CI are separate promotion gates. Native CI builds both pinned DOSBox profiles and a separate Wine/QEMU runtime, then tests an installed 0.12.0 wheel with `FDISBULL_REQUIRE_PE=1`. That PE gate launches two fresh VMs, verifies actual clicks change the fixture counter, observes rearmed breakpoints, edits memory, traces instructions, and exports artifacts after project restart. CI artifacts retain logs, JUnit reports, input identities and authored screenshots/traces; game files, runtime images, saved states, compiled fixtures and local project databases are excluded.

## Scope and compatibility

The qualified PE scope is an original, unpatched, native x86-64 EXE and its main image, with an authored Win32 GDI window. Static child versions are not applied implicitly. PE32/WoW64, DLL launch, following child processes, managed source breakpoints, arbitrary game compatibility, DirectX/fullscreen capture and multi-window selection are unqualified. Data watchpoints, execution layers, fast-forward and resumable editable native states remain DOS-only. Instruction stepping is not a complete memory-access trace or scheduler-faithful replay.

The existing DOS backends and their hash-checked patches remain available. The full ordinary Linux suite is the platform gate; the full macOS suite retains pre-existing Linux ELF compiler/linker fixture failures. Native PE and DOS acceptance were also run on the actual Mac, as recorded in the local evidence. No game, saved state or project database is distributed.

See [PE64 usage](WINE_DEBUGGER.md), [runtime build recipe](../experimental/wine/ci/README.md), and [verification evidence](PE64_VERIFICATION.md).
