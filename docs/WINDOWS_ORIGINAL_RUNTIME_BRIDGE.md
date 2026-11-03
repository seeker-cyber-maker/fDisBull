# Original Win16 / Win32 / Win64 runtime bridge

**Status:** phase-zero **read-only preflight implemented**; subsequent native-runtime/debugger work is proposed. This MR does not claim a new Windows debugger, a built Wine 11 guest, or execution of an original program. Existing output/back-end qualification is not equivalent to original-image debugging.

## Why this is needed

fDisBull v0.30.0 already has:

| Windows era | Existing static and output capabilities | Original program debugging gap |
| --- | --- | --- |
| Win16 NE / x86-16 | NE loader and fixup-preserving static traversal; native Win16 UDC memory shell, tested in Wine 11 | No live selector/task-aware original NE debugger |
| Win32 PE32 / x86-32 | PE32 static loader; i686 MinGW Win32/GDI UDC shell with native tests | The Wine debugger only admits x86-64 PE; no original PE32 WoW64 debugger |
| Win64 PE32+ / x86-64 | PE64 static analysis, common UIL Win64 lowering, native desktop shell | Existing Wine/QEMU debugger, qualified only within its documented scope |

See [NE loading](NE_LOADING.md), [Win16 output](UDC_MEMORY_WIN16.md), [Win32/Win64 output](UDC_MEMORY_DESKTOP.md), [common UIL native](COMMON_UIL_NATIVE.md), [PE64 debugger](WINE_DEBUGGER.md), and [Snake cross-target qualification](evidence/snake-win16-win32/verification.json).

**Goal:** a shared, provenance-preserving observation interface for original NE, PE32 and PE32+ executables, feeding the existing RE to UDL/UIL pipeline. Retain every original source identity, ABI and runtime mapping; never collapse source-specific behavior into a shared rule before independent equivalence evidence. The primary concrete target is original Win16 Colonization, not a new output compiler.

## It does not have to be built on the Mac Studio

A trusted x86-64 Linux build environment or CI/remote worker can compile authored NE/PE32/PE32+ fixtures, prepare an offline Wine/QEMU guest, build the guest agent and run the acceptance tests. The user's Mac is **one possible QEMU host**, not a prerequisite for writing or compiling this feature. Native original Win16 runtime debugging must eventually be qualified in an actual compatible guest. Replaying a model locally or compiling a source file does not certify that edge.

The planned common runtime is **Wine 11 new WoW64** in a contained x86-64 Linux environment (using QEMU full emulation on ARM64 hosts). Wine 11 supports 16-bit programs in new WoW64 but **does not thereby guarantee Win16 debugger events or selector contexts**. The default 64-bit prefix or an explicitly new WoW64-compatible prefix must be used; do not automatically migrate or replace a user's existing prefix. See [official Wine 11.0 announcement](https://list.winehq.org/hyperkitty/list/wine-releases%40list.winehq.org/message/UL6L2GJ55VYUJ5KUMBZ3TZSXRFJ52QG6/).

A **second, historical oracle** is Windows 3.1/3.11 under DOSBox-X, using user-supplied appropriately licensed Windows media and original target files. It must remain private and is only for original-game comparison. See [DOSBox-X Windows 3.1 installation guide](https://dosbox-x.com/wiki/Guide%3AInstalling-Windows-3.1x).

### What is implemented by this MR: read-only readiness inventory

A small Python script reports only tool presence and versions. Its three modes are independent:

~~~sh
python scripts/windows_runtime_preflight.py --mode compilers
python scripts/windows_runtime_preflight.py --mode qemu-host \
  --qemu /private/qemu-system-x86_64 --kernel /private/bzImage \
  --initramfs /private/wine11.cpio.gz --strict
# Run INSIDE a prepared Linux guest, not on the Apple Silicon host:
WINEARCH=wow64 python scripts/windows_runtime_preflight.py --mode wine-guest --strict
~~~

The script invokes **only** Wine and QEMU version commands where available, checks tool/file presence, and produces machine-readable JSON with qualification explicitly equal to "preflight-only." It installs nothing, does not start QEMU/Wine on a target executable, does not initialize a Wine prefix, does not execute private game files, and does not build anything. A successful tool check is **readiness to attempt further tests**, not a native acceptance. Kernel/initramfs presence is not integrity/boot verification. The tool does not inspect or qualify a Wine prefix's on-disk architecture or a live X display. See tests/test_windows_runtime_preflight.py.

### Milestone 1: Wine 11 guest and three authored executable probes (pending)

Reuse src/fdisbull/wine_runtime.py, src/fdisbull/wine_rpc.py, src/fdisbull/wine_guest/agent.c, src/fdisbull/qemu_machine.py and experimental/wine/ci; do not replace the proven PE64 backend. Produce one pinned guest runtime and a real Win16 NE, Win32 PE32, and Win64 PE32+ test EXE from source authored for this experiment. Use Open Watcom for NE and the matching i686/x86_64 MinGW compilers for PE32/PE32+.

For each: verify real format/architecture with the existing loader; run it through the same offline Wine 11 guest, observe entry, controlled input/state changes, GUI surface if applicable, process exit, and resource cleanup. Repeat from a fresh prefix without inferring a debugger pass from the executable's exit code. Retain guest/kernel/toolchain/source SHA-256 identities. Release/CI heavy runs are manual under the repo's anti-abuse CI policy.

### Milestone 2: original Win32 PE32 debugger (pending)

Extend the existing guest/host stopped-process API with **architecture-dependent x86-32 context**, not reinterpretation of 32-bit EIP/ESP as x86-64 RIP/RSP. Test Wine 11 WoW64 debug-event behavior before selecting Wow64GetThreadContext/GetThreadContext operations. Add verified RVA to observed module-base mapping, x86-32 breakpoint hit, displaced-byte execution/rearm, register and guarded memory reads/writes, threads, exceptions and cleanup.

Win32 watchpoints, native layer substitution, VM checkpoint/restore, multi-window picking, DLL and child-process debugging need separate gates; do not inherit PE64 capability flags without executing 32-bit tests. Run current PE64 native acceptance unchanged as a regression.

### Milestone 3: original Win16 NE runtime and selector bindings (pending)

First test whether Wine's NE loader and native debug events actually expose stable **16-bit** CS:IP, DS, tasks/modules and selectors. If events do not expose that state, investigate bounded NE-loader/selector tracing in the guest or use the separate original Windows 3.1/DOSBox-X observation route; **do not fake NE runtime support**.

Only a qualified observer may bind static ne:segment-index:offset to runtime selector:offset. Every binding needs observed module/task identity, source SHA, descriptor base/limit, valid address range, session/epoch and replay evidence. Reject unresolved selectors, movable/reloaded segment changes and stale logical-to-physical mappings. Preserve far calls, imports, thunk boundaries and Win16 host effects.

Then test the exact original COLONIZE.EXE with user-owned files. Start with the known DOS/Win16 paired production input and shortage correction, capture original entry state and complete observable changes. Compare original NE versus original DOS and shared UIL separately, without claiming a full colony-turn/warehouse-commit reconstruction.

### Milestone 4: generic UIL target completeness (pending)

Common indexed UIL's native code generator currently has macOS-arm64, Linux-x64 and Win64 targets. A bounded-memory UDC shell already exists for NE and PE32; this is **not** proof that all generic typed indexed UIL operations compile to both. Add 16/32 ABI and carrier-width lowering only after matched semantics and real output/native tests justify each operation. Keep original and output code provenance distinct.

## Required proof and refusals

| Gate | Required evidence | Must not be inferred |
| --- | --- | --- |
| P0 prerequisites | Runtime/tool version and caller-owned artifact inventory | A functioning guest, Wine prefix, or debugger |
| P1 guest execution | Real authored NE/PE32/PE64 files and actual Wine 11 entry/input/state/exit | Original target compatibility or debugging |
| P2 PE32 debug | Native WoW64 x86-32 register context, breakpoint/rearm, guarded memory effects | PE64 watch/layer/snapshot parity |
| P3 NE debug | Runtime CS:IP and observed selector/task bindings, relocated call and negative stale-context cases | Real-mode paragraph arithmetic or guessed selector values |
| P4 fidelity | Original instruction trace, UIL reference, generated target, full private state/effect and RNG comparison | Complete game recovery from a screenshot or a passing scalar helper |

Do not store original games, Windows installation media, guest images, private FDB projects or resumable VM states in GitLab. Only authored fixtures, sanitized receipts, scripts and tests belong in the repository. Preserve unresolved/rejected paths explicitly.

## Build/ownership status

The phase-zero script and unit tests were authored and tested in an independent Linux x86-64 Python 3.13.5 sandbox. Wine, QEMU, Open Watcom and MinGW are **not installed in that sandbox**. It cannot truthfully claim runtime success. Once a pinned guest is available, the native build/launch and debugger work can run on a Linux runner or a local Mac QEMU host. The local-hub Git mirror and native host acceptance remain pending; this draft MR was published through the connected GitLab repository interface only.
