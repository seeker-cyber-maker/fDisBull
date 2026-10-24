> Historical research and qualification record. For the current development integration and commands, see [PE64 Wine/QEMU debugger](WINE_DEBUGGER.md).

# Wine debugger feasibility on the M1 Max

**2026-10-23 execution update:** [Actual Linux/Wine qualification and receipts](../experimental/wine/README.md) now exist from the ARM64 Mac. Wine 9.0 starts Windows programs under Apple container/Rosetta, but that route aborts before the authored debugger breakpoint with `invalid gdt selector index 5`. Full x86-64 Linux CPU emulation under QEMU passes the authored PE64 breakpoint, memory edit, register and single-step oracle, including a replay of the exact controller that failed under Rosetta. DOSBox ran in both same-environment experiments; its required native tests were not fully green, as recorded separately. This is platform qualification, not a delivered fDisBull PE runtime adapter.

The research below was checked **2026-10-22** in the earlier Linux/x86-64 workspace. At that planning stage no Wine installation, executable, container or external infrastructure was started, and that environment had no `container`, `wine`, `winedbg`, `gdb`, QEMU system emulator or MinGW compiler. Its historical inventory is not the current Mac inventory.

## Feasibility decision

A small Wine-backed debugger is feasible as a separate execution backend for fDisBull. Start by qualifying **one self-authored x86-64 Windows console executable** in an isolated Linux guest. Keep static analysis usable independently. Add native Windows debug events and byte snapshots to the existing database model only after execution controls work.

Apple's current `container` documentation requires Apple silicon and documents macOS 26 support; Containerization's source build additionally requires Xcode 26. The M1 Max meets the CPU requirement, but its installed macOS version has not been checked. The tool runs Linux containers in separate lightweight VMs, and supports translated `linux/amd64` workloads. This supplies Linux isolation/translation, **not a Windows PE loader**: Wine remains necessary. [1–3]

Rosetta running an amd64 Linux program does not establish that Wine exception delivery, software breakpoints, register access or single-step work correctly under that translation stack. These are explicit qualification gates. Do not describe that combination as verified from a successful `uname` or application launch. [3; inference]

## Execution choices

| Route | Use | Qualification limit |
| --- | --- | --- |
| Apple `container` + amd64 Wine via Linux binary translation | First M1 prototype if its actual macOS supports the installed container release | Guest debugger behavior under translation remains untested. |
| Full x86-64 Linux guest under QEMU TCG on the Mac | Fallback when translation/debugger behavior fails | Slower software CPU emulation; no speed promise. |
| Existing actual x86-64 Linux machine/VM | Establish backend correctness independently of Apple translation | Does not qualify the M1 path. |
| ARM Windows VM with a Windows debug agent | Later option when real Windows behavior is required | Different backend, licensing and emulation behavior; not part of this MVP. |

The M1 fallback must not depend on Apple's nested virtualization flag: the documented feature requires M3 or newer. A full x86 system emulated with QEMU TCG avoids that requirement; hardware virtualization of an ARM guest alone does not turn it into an x86 guest. [4,10]

## Smallest architecture

The Mac-side coordinator owns the fDisBull database, renders images and launches one disposable guest session. A trusted guest controller owns Wine and the debugged child. Commands/events travel through bounded stdin/stdout messages; the guest receives no host filesystem mount, SSH agent, shared desktop or published network port.

Implement two bounded steps:

1. **Capability probe using WineDbg.** Existing commands can launch/attach, break, step instructions, inspect registers/mappings/modules/memory and write a minidump. Batch options are `--command` and `--file`. Its GDB proxy is optional. [7]
2. **Structured guest agent.** A small 64-bit Windows PE controller, built with MinGW or a suitable LLVM Windows cross-toolchain, uses Wine's implementation of Win32 debugging APIs and emits JSON directly. This avoids making a permanent database interface out of a human debugger's text. The same event adapter can later run on real Windows. [8; proposed design]

No new disassembler, GUI automation, browser or machine simulator is required. Keep the existing native decoders for captured bytes.

## Dependencies and example commands

These commands are a **reviewable future recipe**. The image, `/opt/fdisbull/wine-agent` and its image build are proposed deliverables; they do not exist in this package. Pin the actual container release, Linux image digest, Wine build and debugger/compiler versions when implementing. Image acquisition/build may need network access before a session; sample execution remains offline.

Read-only Mac capability inventory:

```bash
sw_vers
uname -m
container --version
container run --help
```

The trusted image needs amd64 Linux userland, Wine with WineDbg, a prebuilt empty/default 64-bit Wine prefix template, a supervisor/controller and the self-authored probe. Add GDB only for the proxy experiment. Add Xvfb and guest-local X11 libraries only if Wine's initialization or the chosen probe requires them; do not connect the Mac's X server. Install runtimes in the trusted image, never interactively during an offline sample run.

Proposed isolated session invocation, using documented container options: [5,6]

```bash
container run --rm -i --name fdisbull-probe \
  --arch amd64 --rosetta --network none \
  --read-only --cap-drop ALL --user 1000:1000 \
  --cpus 2 --memory 2G \
  --mount type=tmpfs,target=/work,size=1G,mode=1777 \
  --mount type=tmpfs,target=/tmp,size=128M,mode=1777 \
  --env WINEPREFIX=/work/prefix \
  --env HOME=/work/home \
  fdisbull-wine-probe:qualified \
  /opt/fdisbull/wine-agent --stdio
```

Inside the trusted image, the controller creates its private working directories and copies the prefix template. The deliberately set `HOME` is a guest application setting, not a repurposed shell variable. Transfer only an explicitly selected file as bounded bytes over the controller protocol. Return bounded result records/blobs before shutdown; tmpfs is ephemeral. Record resource limits and enforce a host wall-clock timeout. Do not add privileges until a specific failed capability test establishes what is needed; a same-user parent/child Win32 debug session is the intended starting point.

A Wine prefix is configuration/runtime state, **not a security boundary**. Keeping a separate prefix or removing its `Z:` link does not replace the guest boundary. The architectural boundary is the isolated VM with no host shares and no external networking. An ordinary host-only/internal network is also not equivalent to no host connectivity; use `--network none`. [4–6,13]

WineDbg batch probe, *inside the isolated guest and only with our probe executable*:

```bash
winedbg --file /opt/fdisbull/probe.winedbg /opt/fdisbull/probe64.exe
```

The command file can inspect `info regs`, `info share`, `info map`, `x /16b $pc`, perform `stepi`, then terminate its child. Handle architecture-specific PC names in the probe. Validate each returned value against the known fixture. `--auto` is a crash receipt, not an interactive control API. [7]

Optional proxy experiment, with both frontend and proxy inside the same offline guest:

```bash
winedbg --gdb --no-start --port 31337 /opt/fdisbull/probe64.exe
```

Connect an in-guest `gdb --interpreter=mi2` to its loopback endpoint. **`--no-start` means do not automatically launch GDB; it does not mean do not create the debuggee.** WineDbg's proxy forwards requests to Win32 APIs. Use GDB/MI for machine-oriented frontend records, not interactive text scraping. No port publishing is required. [7,9]

## Structured capabilities and lifecycle

The planned agent launches the child with `CreateProcessW` and `DEBUG_ONLY_THIS_PROCESS`, then owns a `WaitForDebugEvent`/`ContinueDebugEvent` loop. Track process/thread creation and exit, module load/unload, exception, breakpoint and single-step events. Preserve first-chance versus unhandled exception status; do not swallow every exception. Read/write thread context and memory through the appropriate Win32 APIs. [8]

Enumerate maps with `VirtualQueryEx`, retaining base, size, committed state, type and protection; use `ReadProcessMemory` only on readable committed ranges and retain short-read/errors. Maps are observations from this stopped guest process, not static PE section permissions. [11]

The proposed control surface is deliberately small:

| Operation | Evidence returned |
| --- | --- |
| launch / stop / continue / terminate | Session/process identity and stop reason; bounded timeout status. |
| break.add / break.remove | Address, original byte, breakpoint kind and success/error. |
| step.instruction | Before/after PC, selected thread and actual stop event. |
| registers | Architecture, thread ID, complete validity-tagged register set. |
| maps / modules | Captured mappings; module base/path/hash when recoverable. |
| memory.read | Requested/actual byte count, bytes or content hash, read errors. |
| snapshot | Event sequence, maps/registers and selected byte blobs from one stop. |

Software-breakpoint bookkeeping must restore original instructions, adjust PC as required, single-step correctly and clean up on termination. Keep an exact event sequence and raw backend transcript for debugging the adapter. Hardware watchpoints, child-process following and native Wine internals are later capabilities, never silently promised by the first implementation.

## Feeding fDisBull

Use a separate runtime session/process address space. Record source executable SHA-256, guest image/Wine/translation versions, module load base, event/thread IDs, architecture, timestamps and stop cause. Store immutable observed byte snapshots with provenance such as `wine-runtime-read`; compare changed pages without overwriting original file bytes or previous manual patches.

A snapshot importer must distinguish image-backed bytes, relocated addresses, private/JIT allocations and unreadable gaps. New module mappings require an explicit importer/schema extension; today's byte `patch` command is not a general process-memory importer. Rebase references using the observed module mapping, then use existing decoding/annotation/render seams. A rendering should identify its runtime session and stopped snapshot, keeping runtime observation separate from static inference.

The concrete first acceptance fixture should call one DLL function, hit one breakpoint, modify a small buffer, execute one step and exit. Acceptance requires exact register/memory values, observed module base, map protections, snapshot import, image export and a clean second run from a fresh prefix. Also verify isolation with harmless probes: no external route, no host files/mounts, no inherited credentials and no published listener. A reproducible failure under Rosetta triggers the fallback; it is not a reason to rebuild the whole debugger.

## x86, .NET and LLVM limits

Wine 11.0's release notes describe completed new WoW64 support and deprecate pure `WINEARCH=win32` prefixes in that mode. Start with the default 64-bit prefix. Test a native PE32 executable separately from PE32+; amd64 Linux translation does not alone prove 32-bit Windows debugging, WoW64 contexts or compatibility across every Wine build. [12]

Wine Mono targets .NET Framework 4.8.1 and earlier under Wine; it is not a universal substitute for every Windows CLR/runtime. Managed source/IL breakpoints, object inspection and JIT-to-method mapping require a runtime-specific debugging adapter such as the applicable `ICorDebug`/managed callback interface, not merely native WineDbg support. Keep modern .NET, older Framework and mixed-mode cases as separate qualification tracks. [14,15]

LLVM may supply a Windows-targeting compiler or a future remote frontend. It is not needed to implement the Win32 debug-event loop, and a Mac LLDB installation cannot automatically inspect a Linux guest's translated Wine process. Prefer the existing WineDbg/GDB remote seam or the structured guest agent before introducing another backend.

## Full x86 Linux fallback

Create a disposable qcow2 overlay from an already prepared, trusted x86-64 Linux guest containing Wine and the agent. An illustrative host-side launch is:

```bash
qemu-system-x86_64 \
  -accel tcg -machine q35 -cpu max -smp 2 -m 4096 \
  -drive file=wine-session.qcow2,format=qcow2,if=virtio \
  -nic none -display none -serial stdio -monitor none
```

The guest image must already boot headlessly and start the session controller over its serial channel. Use no shared folders, clipboard, USB passthrough or host network. QEMU system emulation/TCG and its machine/serial options are documented, but this exact guest configuration has not been tested here. Deleting the disposable session disk after evidence extraction restores the prepared baseline. [10,16]

## Sources

All links below were consulted or retrieval attempted on **2026-10-22**. Apple `main` documentation is moving: use the tag matching the installed release when implementing, rather than assuming future `main` flags match it.

1. [Apple container README](https://github.com/apple/container/blob/main/README.md) — Apple silicon/macOS 26 requirements, signed installer, Linux VM scope.
2. [Apple Containerization README](https://github.com/apple/containerization/blob/main/README.md) — per-container VM design, process I/O over guest-agent transport, macOS/Xcode 26 build requirements.
3. [Apple multiplatform images](https://github.com/apple/container/blob/main/docs/multiplatform-images.md) — amd64 Linux userland via Rosetta. [Apple Linux Intel binary translation API](https://developer.apple.com/documentation/virtualization/running-intel-binaries-in-linux-vms) was also checked; detailed body retrieval was unavailable, so no unsupported debugger promise is inferred.
4. [Apple runtime configuration](https://github.com/apple/container/blob/main/docs/runtime-configuration.md) — capability controls and M3+ nested virtualization requirement.
5. [Apple CLI command reference](https://github.com/apple/container/blob/main/docs/command-reference.md) and [0.6.0 release](https://github.com/apple/container/releases/tag/0.6.0) — process/resource/read-only/network flags; release notes explicitly introduce no-network mode.
6. [Apple mounts/volumes](https://github.com/apple/container/blob/main/docs/volumes.md) — tmpfs size/mode syntax and ephemeral behavior. [Networking](https://github.com/apple/container/blob/main/docs/networking.md) distinguishes ordinary isolated networks from a no-network policy.
7. [Wine Developers Manual: WineDbg, distributed by Debian](https://manpages.debian.org/trixie/wine/winedbg.1.en.html) — Wine 10.0 manual, source updated 2025-08-16; batch modes, GDB proxy, `--no-start` semantics and commands. WineHQ GitLab source retrieval was blocked by its anti-bot service; verify the installed Wine build's `winedbg --help` before automation.
8. [Microsoft debugger main loop](https://learn.microsoft.com/en-us/windows/win32/debug/writing-the-debugger-s-main-loop) — updated 2025-07-14; debug events, continuation, contexts and process memory APIs. It specifies Windows behavior, not a guarantee of Wine/Rosetta compatibility.
9. [GNU GDB/MI](https://sourceware.org/gdb/current/onlinedocs/gdb.html/GDB_002fMI.html) — machine-oriented frontend interface.
10. [QEMU system introduction](https://www.qemu.org/docs/master/system/introduction.html) — full-system emulation, TCG, virtual devices and management interfaces.
11. [Microsoft VirtualQueryEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualqueryex) — updated 2022-05-24; mapping states/types/protection and region extents.
12. [Wine 11.0 upstream release announcement](https://list.winehq.org/hyperkitty/list/wine-releases@list.winehq.org/thread/UL6L2GJ55VYUJ5KUMBZ3TZSXRFJ52QG6/) — 2026-01-13; new WoW64 behavior, prefix restrictions and single loader.
13. [WineHQ user-list security explanation](https://www.winehq.org/pipermail/wine-users/2012-January/101444.html) — 2012-01; indexed primary explanation that Wine is not an isolated VM/sandbox. Full page retrieval was unavailable; the no-prefix-boundary conclusion also follows from treating the guest's OS permissions as the boundary.
14. [Wine Mono official repository](https://github.com/wine-mono/wine-mono) — supported Framework scope and relation to Wine's mscoree.
15. [Microsoft ICorDebug](https://learn.microsoft.com/en-us/dotnet/core/unmanaged-api/debugging/icordebug/icordebug-interface) — updated 2025-08-30; CLR debugging/event interfaces. Validate the specific runtime/version rather than generalizing mixed-mode support.
16. [QEMU invocation reference](https://www.qemu.org/docs/master/system/invocation.html) — accelerator, disk, serial, display and network options; current development documentation, pin the actual QEMU release for execution.
