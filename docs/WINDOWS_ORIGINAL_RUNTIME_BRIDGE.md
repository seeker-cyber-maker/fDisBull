# PE32-first original Windows runtime bridge (macOS host, Win16 later)

**Status:** phase-zero **read-only preflight implemented**; subsequent native-runtime/debugger work is proposed. This MR does not claim a new Windows debugger, a built Wine 11 guest, or execution of an original program. Existing output/back-end qualification is not equivalent to original-image debugging.

## Why this is needed

fDisBull v0.30.0 already has:

| Windows era | Existing static and output capabilities | Original program debugging gap |
| --- | --- | --- |
| Win16 NE / x86-16 | NE loader and fixup-preserving static traversal; native Win16 UDC memory shell, tested in Wine 11 | No live selector/task-aware original NE debugger |
| Win32 PE32 / x86-32 | PE32 static loader; i686 MinGW Win32/GDI UDC shell with native tests | The Wine debugger only admits x86-64 PE; no original PE32 WoW64 debugger |
| Win64 PE32+ / x86-64 | PE64 static analysis, common UIL Win64 lowering, native desktop shell | Existing Wine/QEMU debugger, qualified only within its documented scope |

See [NE loading](NE_LOADING.md), [Win16 output](UDC_MEMORY_WIN16.md), [Win32/Win64 output](UDC_MEMORY_DESKTOP.md), [common UIL native](COMMON_UIL_NATIVE.md), [PE64 debugger](WINE_DEBUGGER.md), and [Snake cross-target qualification](evidence/snake-win16-win32/verification.json).

**Goal:** a shared, provenance-preserving observation interface for original PE32 first, and subsequently NE, without regressing the existing PE32+ debugger. Feed the original behavior into RE -> UDL -> UIL -> UDC and verify block-fusion optimizations. Preserve each original source identity, ABI, register width and runtime mapping. The **first original-program target is an authored PE32 fixture, then user-owned Win32 crackmes**. Original Win16 Colonization remains a separate later milestone; it must not gate PE32 progress.

## Binding execution priorities (updated November 3, 2026)

| Priority | Deliverable | Must pass before calling it implemented |
| --- | --- | --- |
| **P0: PE32** | Compile a genuine I386/PE32 fixture and run it in an isolated Wine 11 WoW64 guest | Actual 32-bit entry, input, state change and exit, not a PE64 process or successful compilation alone |
| **P1: PE32 debugging** | Extend guest and host protocol to x86-32 registers, breakpoints and guarded memory | Independent EIP/ESP/EFLAGS context proof, RVA rebasing, breakpoint rearm and failure/refusal tests |
| **P1 in parallel: local macOS** | Run the controlling fDisBull process and macOS-native investigation on the local Mac; host the PE32 guest through QEMU where required | Fresh Mac-specific toolchain, native Mach-O/LLDB observation and guest communication receipts; remote Linux not silently required |
| **P2: crackme/UDC qualification** | Original PE32 A->B vs optimized AB at matched stopped states | Explicit live flags, memory, branch, SEH/API and continuation comparisons; no proprietary crackmes in Git |
| **P3: Win16 original debugger** | Original NE selector/task/CS:IP observation and Colonization parity | Compatible Win16 runtime and source/selector/offset binding proof |
| **P4: general UIL targets** | Expand common indexed-UIL native implementations beyond current Win64 | Separately qualified generic PE32/NE backends, not just bounded-memory UDC shells |

This is **priority ordering, not a claim that these native implementation stages have landed**. The existing Win64 debugger must remain functional and receive non-regression testing. Win16 research can continue independently without blocking the PE32 gate.

## macOS is the local host, not an afterthought

**The primary workflow is local-first on the user's Mac Studio.** fDisBull's macOS-native Python process, Mach-O/ARM64 analysis, `macos-observe`, LLDB-based original-code observations and macOS ARM64 UDC build path should stay usable independently of Wine or a Linux VM. See [macOS ARM64 analysis](MACOS_ARM64_ANALYSIS.md), [macOS memory UDC](UDC_MEMORY_MACOS.md) and [macOS reversible capture](MACOS_REVERSIBLE_CAPTURE.md). Their existing bounded original/runtime scopes must not be silently enlarged into arbitrary native-process debugging.

For an **original PE32 process**, macOS itself cannot execute 32-bit Windows code. The local Mac therefore runs the fDisBull controller and an **isolated QEMU x86-64 Linux guest with Wine 11 WoW64**, using the same persistent project/evidence API. Neither Apple Silicon Rosetta nor an ARM64 native compiler is a substitute for a PE32 CPU/Win32 runtime. Retain the guest image and checksums outside Git, and reuse the current Wine/QEMU transport rather than adding a mandatory remote service.

A Linux x86-64 runner may compile, reproduce, or run the *same* offline guest as an **optional CI/remote route**. Native Windows or compatible-Wine runs provide their own scoped OS evidence; no Mac-specific result is inferred from Linux CI, or vice versa. Mac-local build checks use the host toolchain where applicable. Avoid requiring Open Watcom or Win16 setup before PE32 work can begin.

**macOS acceptance is its own gate**: native `fdisbull` CLI and Mach-O/ARM64 observation, local compiler/probe, QEMU guest launch and data transfer when requested, and an exact backend/host identity receipt. Missing tools or privileges must yield a specific refusal, not silently route the whole workflow to Linux. The read-only `qemu-host` preflight can run on macOS but currently does not certify macOS LLDB access, Wine-guest functionality or Apple-native execution.

The planned common runtime is **Wine 11 new WoW64** in a contained x86-64 Linux environment (using QEMU full emulation on ARM64 hosts). Wine 11 supports 16-bit programs in new WoW64 but **does not thereby guarantee Win16 debugger events or selector contexts**. The default 64-bit prefix or an explicitly new WoW64-compatible prefix must be used; do not automatically migrate or replace a user's existing prefix. See [official Wine 11.0 announcement](https://list.winehq.org/hyperkitty/list/wine-releases%40list.winehq.org/message/UL6L2GJ55VYUJ5KUMBZ3TZSXRFJ52QG6/).

A **second, historical oracle** is Windows 3.1/3.11 under DOSBox-X, using user-supplied appropriately licensed Windows media and original target files. It must remain private and is only for original-game comparison. See [DOSBox-X Windows 3.1 installation guide](https://dosbox-x.com/wiki/Guide%3AInstalling-Windows-3.1x).

### What is implemented by this MR: read-only readiness inventory

A small Python script reports only tool presence and versions. Its three modes are independent. The `qemu-host` mode is host-neutral, including macOS. A distinct macOS-native LLDB/Clang runtime gate is **planned**, not implemented by this preflight:

~~~sh
python scripts/windows_runtime_preflight.py --mode compilers
python scripts/windows_runtime_preflight.py --mode qemu-host \
  --qemu /private/qemu-system-x86_64 --kernel /private/bzImage \
  --initramfs /private/wine11.cpio.gz --strict
# Run wine-guest INSIDE the prepared Linux guest, not on the Apple Silicon host:
WINEARCH=wow64 python scripts/windows_runtime_preflight.py --mode wine-guest --strict
~~~

The script invokes **only** Wine and QEMU version commands where available, checks tool/file presence, and produces machine-readable JSON with qualification explicitly equal to "preflight-only." It installs nothing, does not start QEMU/Wine on a target executable, does not initialize a Wine prefix, does not execute private game files, and does not build anything. A successful tool check is **readiness to attempt further tests**, not a native acceptance. Kernel/initramfs presence is not integrity/boot verification. The tool does not inspect or qualify a Wine prefix's on-disk architecture or a live X display. See tests/test_windows_runtime_preflight.py.

### Milestone 1 (P0): original PE32 executable probe before Win16

Reuse `src/fdisbull/wine_runtime.py`, `src/fdisbull/wine_rpc.py`, `src/fdisbull/wine_guest/agent.c`, `src/fdisbull/qemu_machine.py` and the existing authored Windows fixture mechanisms. First compile and admit a **genuine I386/PE32 x86-32 fixture** using i686 MinGW. Run it in an offline Wine 11 WoW64 guest under full x86 QEMU, driven by fDisBull on macOS or Linux. Verify format, entry, controlled state transition, process exit, resource cleanup, observed image base, and exact runtime/guest identities.

Do not substitute a Win64 PE32+ fixture for this test, and do not require a Win16 toolchain. Explicitly test new-prefix startup, process-bitness detection and refusal on mismatched PE32/PE64 context. Keep the existing PE64 native acceptance unchanged as a regression. Hosted heavy native jobs remain manual under CI anti-abuse rules.

### Milestone 2 (P1): original Win32 PE32 stopped-process debugging

Extend the guest/host protocol to **architecture-dependent x86-32 state**, not reinterpretation of 32-bit EIP/ESP/EFLAGS as x86-64 RIP/RSP. Validate the actual Wine 11 WoW64 debug events before choosing thread-context APIs. Require 32-bit breakpoint hit, restored displaced byte, single-step/rearm, guarded memory read/write, exception/SEH and thread reporting, close/restart isolation, and reliable RVA to observed module-base translation. Unrecognized context or stack/frame shape must refuse.

Win32 watchpoints, native code layers, machine snapshots/rewind, multiple windows, DLL/child-process following and broad anti-debug compatibility each require separately tested capability flags. No PE64 feature parity is inherited by metadata alone.

**Mac-host lane in parallel:** run exactly the same authenticated guest protocol under QEMU on macOS/Apple Silicon; compare relevant PE32 observations with the Linux host route and record host-specific timing/translation separately. Also smoke the already-existing native macOS ARM64 target analysis and generated UDC path *without launching Wine*. This confirms that adding Windows support does not break the local platform.

### Milestone 3 (P2): original PE32 crackme and UDC fusion acceptance

Use an **authored PE32 key-check fixture first**, then a privately supplied, unpacked user-owned crackme. Compare original connected blocks A->B and candidate fused AB under matching stopped original-program state, including live general registers/EFLAGS, touched memory, caller-visible exceptions, imports/last-error, ordered effects and continuation. Keep source hashes, compiler profile, solver/model proof and original runtime witness separate. Preserve original child blocks and offer qualified optimized backings as opt-in UIL/UDC realizations. See the separate [reversible feedback MR !63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63).

On the Mac, the authoring/solver/LLVM pure-model loop can run **natively**; only original PE32 execution needs the Windows-compatible guest. This removes an unnecessary dependency on a remote Linux development machine. A completed native guest experiment is still required before claiming original PE32 equivalence.

### Milestone 4 (P3): Win16 original NE selector/task debugging

After the PE32 path passes, test whether Wine's NE loader and native debug events actually expose stable **16-bit CS:IP, DS, tasks/modules and selectors**. Otherwise investigate bounded loader/selector tracing in the guest or use the independent original Windows 3.1/DOSBox-X observation route. **Do not fake Win16 runtime support** by reinterpreting NE segment identities as DOS paragraphs.

Only an observed binding may map static `ne:segment-index:offset` to runtime `selector:offset`. Record module/task identity, descriptor base/limit, live epoch and exact source hash; stale bindings or moved segments must refuse. Then qualify original COLONIZE.EXE with user-owned files using the existing DOS/Win16 food/shortage evidence. No whole-game equivalence claim is justified by isolated fragments.

### Milestone 5 (P4): generic UIL target completeness

Common indexed UIL's native code generator currently has macOS ARM64, Linux x64 and Win64 targets. A bounded-memory UDC shell already exists for NE and PE32; that is not proof of a general typed indexed UIL compiler for those platforms. Extend the **generic PE32** path before additional Win16 lowering, preserving exact 32-bit ABI, carrier widths and proof domains; keep native macOS ARM64 as a required regression target.

## Required proof and refusals

| Gate | Required evidence | Must not be inferred |
| --- | --- | --- |
| P0 tools and artifact identity | Toolchain, Wine/QEMU versions, exact I386 PE32 machine identity and original source hash | A functioning guest from version numbers |
| P0 PE32 native execution | Actual 32-bit entry/input/state/exit in Wine 11 WoW64 under QEMU | PE64 execution or compile-only success |
| P1 PE32 debugger | EIP/ESP/EFLAGS, breakpoint/rearm, original memory, context/exception and lifecycle evidence | PE64 layer/watch/state parity |
| P1 macOS-local host | Host-owned QEMU guest and CLI protocol, independently native Mach-O/ARM64 observation and compiler probe | macOS verified by Linux CI, or PE32 runs as macOS-native code |
| P2 original PE32 fusion | Original A->B vs F under same stopped state and complete declared observations | Algebraic model agreement alone or dropped flags/API effects |
| P3 NE original debugging | Runtime CS:IP with observed selector/task bindings and stale-context refusal | DOS segment arithmetic or guessed selector values |
| P4 target-wide semantics | Qualified Win32/Win16 generic indexed UIL backends with unchanged macOS ARM64 baseline | Passing bounded-memory shells proves arbitrary UIL conversion |

Do not store original games, Windows installation media, guest images, private FDB projects or resumable VM states in GitLab. Only authored fixtures, sanitized receipts, scripts and tests belong in the repository. Preserve unresolved/rejected paths explicitly.

## Build/ownership status

The phase-zero script and unit tests previously passed in an isolated Linux x86-64 Python 3.13.5 sandbox; this revision primarily changes roadmap and acceptance scope, not delivered debugging capability. The tested sandbox did not contain Wine, QEMU, Open Watcom or MinGW. The first real native build should be executed in a prepared guest, preferably driven **locally by macOS on the Mac Studio**, with Linux CI as a complementary route. Mac-local LLDB and original PE32 Wine debugging have **not** been freshly tested by this MR. The local-hub Git mirror remains pending in this tool environment.

Release alignment: v0.31.0 was tagged from a dedicated release line containing the earlier preflight, but MR !60 remains **open and not integrated into GitLab `main`** at this update. The release tag and the default branch are different histories; neither proves this revised priority matrix is shipped.
