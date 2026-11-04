# Original Win32 and Win16 debugging with shared Windows scenes

This development branch extends the existing Wine/QEMU debugger to original
I386/PE32 programs and Windows NE programs. The local Mac owns the controller
and an offline x86-64 Linux/Wine guest. The code is experimental and requires a
new runtime prepared from the same package. Source implementation, native
program qualification, hosted CI, release packaging and local activation are
separate gates. The MR handoff records the exact tested revision and results.

## Choose the actual program profile

| Input | Native context and addresses | Scope |
| --- | --- | --- |
| Win32 I386/PE32 | Actual WOW64 EIP, EFLAGS, eight 32-bit GPRs and segment registers; observed image base plus project RVA | Original main-image breakpoints, memory/register edits, completed steps/traces and bounded scalar data watches |
| Win64 AMD64/PE32+ | Native RIP, RFLAGS and sixteen 64-bit GPRs; observed image base plus project RVA | Existing PE64 debugger, with the shared Windows input/frame/scene interface |
| Win16 Windows NE | At a live 16-bit LDT stop, low 32-bit register values projected from the observed native context, checked against the WOW64 selector view; source-bound `ne:segment:offset` mappings | Original entry, observed code/data selectors, six checked non-stack register edits, breakpoints, completed steps/traces and restricted scalar watches |

The runtime detects the mapped process architecture. A PE32 session cannot
reinterpret a segmented LDT context as a flat address. Unknown or stale Win16
bindings refuse. Static analysis and generated Win16/Win32 UDC shells remain
independent capabilities; they do not establish original-program compatibility.

On a stopped live 16-bit LDT selector, the guest reads both native and WOW64
contexts, verifies their observed code selector and the live descriptor, and
reports a low 32-bit projection of the native registers. Ordinary 32-bit stops
continue to use the WOW64 view. Internal instruction-pointer and trap-flag
changes in observed LDT code selectors update the native and WOW64 control
views together before resuming, including a 32-bit LDT callback reached by a
Win16 far-call trace.
This is a Wine 11 specific control path; a matching stopped readback alone does
not prove that every native field survives continuation.

Win16 permits checked EAX/EBX/ECX/EDX/ESI/EDI edits at a live 16-bit LDT stop.
The caller supplies an expected old value; the guest submits integer-only
native and WOW64 updates, checks that the observed control, selectors, stack
and unedited registers are unchanged, and refuses continuation on a mismatch.
EBP, ESP, instruction pointer, flags and selectors are excluded from this
public edit path. The generated Snake Win16 trial changed and restored EAX,
observed both context views, then continued through physical input, ordinary
reset, named scene and spectator checks. This supports that tested Wine 11
path, not arbitrary NE programs or every register value. PE32/PE64 retain
their own edit paths. Win16 native checkpoints, layers and deltas remain
unavailable.

For PE64's existing advanced operations, see [Wine debugging](WINE_DEBUGGER.md).
The [read-only preflight](../scripts/windows_runtime_preflight.py) is still a
useful tool inventory, with independent `compilers --target pe32`, `qemu-host`,
`wine-guest` and `macos-native` modes. Its result is explicitly `preflight-only`.

## Prepare and launch

Supply QEMU 9.1 or newer, an x86-64 Linux kernel and a private trusted initramfs
with Wine, Xvfb, Python and the guest MinGW compiler. PE32 and NE require a
qualified Wine 11 new-WoW64 runtime; Win16 compiler tools are needed only to
build Win16 fixtures, not to analyze an existing original NE executable.
Existing prefix contents are never migrated. The guest creates its own prefix.

Prepare a new matching runtime without overwriting the base:

```sh
python -m fdisbull.wine_runtime \
  --base-initramfs /private/trusted-wine11.cpio.gz \
  --output /private/matching-fdisbull-wine11.cpio.gz
```

The protocol checks all packaged guest resource hashes, the compiled agent,
Wine version and kernel identity. A changed source or installed package needs
a new matching runtime. Keep the base, prepared runtime and receipts outside
Git. Run the repository storage admission check before a material build or
capture. The retained test image used here needs 8 GiB of guest RAM; smaller
prepared runtimes may use the 4 GiB default. Memory allocation is explicit and
recorded, and native state restoration must retain the saved configuration.

```sh
# Original Win32; PE64 uses the same backend with an actual PE64 input.
fdisbull debug /private/win32.fdb --backend wine-qemu \
  --executable /opt/homebrew/bin/qemu-system-x86_64 \
  --game-dir /private/program --version 1 \
  --kernel /private/linux-amd64 --initramfs /private/matching-fdisbull-wine11.cpio.gz \
  --memory-mib 8192 --boot-timeout-ms 600000 --dot-mode

# Original Windows NE; logical segment addresses are preserved.
fdisbull debug /private/win16.fdb --backend wine-ne \
  --executable /opt/homebrew/bin/qemu-system-x86_64 \
  --game-dir /private/program --version 1 \
  --kernel /private/linux-amd64 --initramfs /private/matching-fdisbull-wine11.cpio.gz \
  --memory-mib 8192 --boot-timeout-ms 600000 --dot-mode
```

Supply an explicit `files` allowlist for required assets, including the target
EXE. Only the selected files cross the private serial channel, within the
1,024-file/64 MiB limit. Symlinks, databases and state files are rejected. The
VM has no network adapter, host filesystem share, clipboard or host display.
Target writes stay in disposable guest RAM.

The Python factory accepts `window=True` or `dot_mode=True`; the foreground
JSON `debug-launch` accepts the same options and `memory_mib`. A retained
`serve` or `debug` session owns the live process. Saved history cannot reconnect
a closed emulator. Closing the session closes the spectator and reaps its VM.
No shared system installation is changed by launching a source worktree.

## Debugging the original NE rather than its carrier

Wine starts a 32-bit carrier before entering the original NE program. The
adapter first stops that carrier, reads the actual loaded module export table,
and breaks at Wine's register callback before the original entry executes.
The callback's prepared CS:IP and DS provide candidate selectors. The adapter
then checks live LDT descriptors and compares original code/data segments
against the retained source before stopping at the original NE entry.

Only declared NE fixup spans and the documented initial instance-data words
are masked. Recognized exported-entry prologs have exact, recorded Wine ABI
transforms rather than blanket ignored code. Unexpected unrelocated bytes
refuse the binding. Each binding retains source/segment hashes, selector,
descriptor base/limit/type, task thread and generation. Every memory/control
operation rechecks the descriptor; an unobserved segment is never computed
using DOS paragraph arithmetic. Current code selectors can be bound by unique
source matching; ambiguous matches refuse.

Use `ne:2:0xa568` style addresses obtained from the actual project, not selector
values copied from another run. Raw carrier context, selector/IP, linear
runtime address and logical project address are reported separately. A carrier
entry stop alone is never reported as an original NE entry.

## Shared Windows keyboard, frames and scene actions

The Windows adapter supplies the same public named scene operations used for
DOS: `scene-check`, `scene-assert`, `scene-act`, `scene-click` and `scene-wait`,
plus sparse `frame-probe`, screenshots, grids and stored exports. Scene memory
predicates use flat project addresses for PE and observed logical bindings for
NE. Frame signatures bind source, resources, runtime and display identity.
A click tied to an outdated frame/mode refuses before input. Fresh client frames use bounded lossless compression when it reduces
transfer size. Exact BGRA length, complete streams, dimensions and frame/context
identities are verified; both scene freshness captures remain independent.


Keyboard methods queue physical US scan codes in the guest. They include
`keyboard_press`, bounded ASCII `keyboard_type`, `keyboard_state` and explicit
key-down/key-up leases. Timed edges use execution-clock offsets: controller
think time while paused does not consume a key hold. Duplicate/conflicting,
consumed or stale leases refuse. Mouse holds also use the guest execution
clock. An acknowledgment proves queue admission/OS delivery; only subsequent
program memory/frame observations establish application consumption.

```python
with project.debugger(qemu, game_dir, backend="wine-qemu", kernel=kernel,
                      initramfs=runtime, version=1, dot_mode=True,
                      memory_mib=8192) as debug:
    print(debug.dot_mode())  # Includes the owned spectator URL.
    debug.keyboard_press("right", hold_ms=40, gap_ms=40)
    result = debug.scene(scene_id).wait(object="counter")
    print(result)  # Inspect matched/complete, observed memory/pixels and stops.
```

Use addresses, scene IDs and object names authored for the selected program.
For a large or slow client frame, pass an explicit outcome polling interval:
`debug.scene(scene_id).act("step", slice_ms=1000)`. Named actions default to
100 ms execution slices; `slice_ms` accepts 1–1000 ms and controls execution
between observations without repeating input or extending the host deadline.
A frame capture can take much longer than the execution slice. Queue/OS delivery,
application commit and painted output remain separate observations.

For a generic observation wait use `active_ms`, `slice_ms`, `timeout_ms` and
explicit memory/register predicates. Windows scene budgets use host execution
slices and report `time_basis: host`; a legacy scene `guest_ms` field is an
active host budget here. It does not become DOS guest time or frame accuracy.

Breakpoints, watches, exceptions, exit and incomplete observations interrupt a
scene. They are retained with any already-queued input. Do not replay a click
or key batch after such a stop. Inspect the first-chance exception and explicitly
continue the stopped program or use an input-free scene wait when appropriate.
The debugger forwards an unhandled first-chance exception on continuation;
it does not silently swallow application or Wine exceptions for a scene.

Declarative saved scripts may declare `backend: wine-qemu` or `backend: wine-ne`
with `format: fdisbull-script-1`. This selects the actual backend signatures
for offline validation, including `step` and host-time `wait`. Live execution
also checks the declaration against the owned session and rejects malformed
later operations before an earlier mutation. Omitting `backend` preserves the
legacy DOS storage grammar; live sessions still validate their own methods.

## Dot-mode is a read-only spectator

`--dot-mode` / `dot_mode=True` starts an owned loopback HTTP viewer and returns
its capability URL through launch/status metadata and `debug-spectator`.
Open that URL in Dot's little computer or an ordinary browser able to reach the
controller's loopback listener. `debug-spectator` can enable/disable or inspect
it later. `debug-spectator-frame` captures one paused frame explicitly.

The viewer serves only retained in-memory PNGs and metadata. Browser refreshes
do not issue debugger commands. There is no keyboard/mouse forwarding,
pointer lock, global input hook or host capture; control POST requests refuse.
The underlying QEMU runs with `-display none`. The browser remains an ordinary
browser window and does not own the host keyboard or mouse.

Frames refresh at debugger stops and completed scene slices. For watching a
long gameplay, drive bounded scene slices rather than one uninterrupted long
`run`; the viewer does not promise continuous video during that call. Capturing
before a client window exists returns recoverable `WindowsCaptureUnavailable`
and clears a stale spectator image while preserving the live debugger. Raw
captures remain private; explicit screenshots are stored for offline export.

## Verification and limits

Real native checks use the supplied authored `wine_guest/selftest32.c` Win32
program, an original generated NE Snake program and a private original
Colonization executable. Their binaries, FDBs, assets, raw logs, images and
states stay outside Git and packages. Only authored source/tests and sanitized
handoff reports are published. Consult the MR's exact-head receipts for actual
passes, interrupted attempts and claim boundaries.

The reusable PE32 native test is `tests/test_windows_native.py`; set
`FDISBULL_PE_QEMU`, `FDISBULL_PE_KERNEL`, `FDISBULL_PE_INITRAMFS`,
`FDISBULL_PE32_FIXTURE` and `FDISBULL_REQUIRE_WINDOWS=1`. The opt-in original NE
entry test in `tests/test_win16_debugger.py` uses `FDISBULL_NE_QEMU`,
`FDISBULL_NE_KERNEL`, `FDISBULL_NE_INITRAMFS`, `FDISBULL_NE_FIXTURE` and
`FDISBULL_REQUIRE_NE=1`. The original generated Snake GUI, reset, named-scene
and spectator test is `tests/test_win16_native.py`. It uses the same QEMU,
kernel and initramfs variables plus `FDISBULL_NE_SNAKE_EXE`,
`FDISBULL_NE_SNAKE_INITIAL` and `FDISBULL_REQUIRE_NE_GUI=1` for a required run.
`FDISBULL_NE_GUI_GPR_PROBE=1` changes and restores EAX, refuses an ESP edit
and a stale expected value, and requires later gameplay to continue. The `FDISBULL_NE_GUI_NO_PROBES=1`
and `FDISBULL_NE_GUI_NO_FARCALL_TRACE=1` switches isolate narrower execution
sequences. Missing explicit inputs skip ordinary unit runs and fail required
native runs. An entry-only pass or a GUI run without optional debugger probes
does not qualify the full Win16 debugger route.

`tests/test_windows_sequence_campaign.py` can run at most three fresh Win16
operation cases when the same native inputs and a fresh external
`FDISBULL_NE_CAMPAIGN_OUTPUT` directory are provided. It reuses the GUI harness,
retains stage and fault-family feedback, records declared versus completed
operations, and stops after uncertain guest cleanup. It is a bounded diagnostic
campaign, not a coverage-guided whole-program fuzzer.

PE32 advanced layers, CPU/RAM deltas and whole-VM state code use the actual
32-bit context; each positive native feature still needs its own qualification.
Snapshots refuse queued or held input, and a restore invalidates host key
leases. Win16 whole-VM checkpoints, execution layers and CPU/RAM deltas are
explicitly unavailable pending selector recovery qualification. Ambiguous
scalar watches and changed selectors refuse; an unsafe guard classification
closes the owned session before any continuation.

Multiple-window selection, child-process following, arbitrary DLL/JIT code,
managed source debugging, DirectX/fullscreen capture, exact Windows hardware
behavior, DOS frame timelines and general Win16 compatibility remain outside
this qualified scope. Runs are finite synchronous operations; a slice is a
bounded yield, not an asynchronous interrupt API. The Mac-hosted Wine route
does not qualify native Microsoft Windows, whole-game recovery, DOSBox parity,
or the separate original-to-UIL and UIL-to-generated-code edges.

No original-versus-optimized crackme/UDC equivalence or generic Win16/Win32 UIL
compiler is added by this debugger contribution. Mac-native LLDB/ARM64 routes
remain separate and are not enlarged by Windows results. Hosted heavy CI is
manual; Draft MR updates use `ci.skip` on GitLab and keep local-hub in sync.
