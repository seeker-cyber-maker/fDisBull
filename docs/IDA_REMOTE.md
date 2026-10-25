# Remote debugger endpoints (unreleased development)

The optional `ida-wine-qemu` backend uses a user-supplied IDA 9.4
`win64_remote.exe` as its Windows debugging engine. The Linux controller speaks
the server's binary debugger protocol directly. No IDA GUI, plugin, IDA analysis
database or IDC command wrapper is required for the implemented operations.
The vendor executable is uploaded only into the disposable guest at launch;
its SHA-256, interface version and observations are recorded, never its bytes.

This is new source work after the published 0.13.0 release. Existing tagged
packages, deliveries and the default `wine-qemu`/`dosbox` backends are unchanged.
It is an optional adapter, with a smaller qualified feature set than those
backends. See [verification](IDA_REMOTE_VERIFICATION.md).

## Reference and architecture

The protocol reference is the public Hex-Rays SDK, pinned at
[`f80b1283e9a40b4e0c734c22d6c5d2d07f379de0`](https://github.com/HexRaysSA/ida-sdk/tree/f80b1283e9a40b4e0c734c22d6c5d2d07f379de0).
`include/network.hpp`, `include/idd.hpp`, `dbg/rpc_debmod.cpp` and
`dbg/dbg_rpc_handler.cpp` define framing, messages, registers and the two sides
of the conversation. Interface 31 and 64-bit protocol address fields are
required. Unknown profiles fail before launching the target. Captured register
description vectors from the actual 9.4 server independently exercise decoding.
See [SDK attribution](THIRD_PARTY_IDA_SDK.md).

The controller handles version negotiation, asynchronous event acknowledgments,
thread tracking, software-independent execution stops, memory/register access,
bounded stepping and page-breakpoint displacement. Guest Windows APIs remain
the execution mechanism. The same client speaks to the DOS endpoint, where
the mechanism is the real DOSBox CPU's existing hooks.

The Linux controller and Windows server live inside the owned QEMU guest. The
host talks to the controller over the existing private serial transport, with
no guest network interface or host filesystem mount. The Windows server uses
guest-local loopback. A separate capture/input helper uses the target PID and
never attaches as a second debugger.

Execution breakpoints do not replace guest instructions with INT3. The PE
adapter requests IDA page breakpoints and filters the exact requested PC;
the DOS endpoint uses heavy-debug fetch hooks. Page protections, Windows debug
attachment, stepping, timing and debug registers are still observable. This
does not establish debugger invisibility or zero host overhead.

## PE64 launch

Prepare a separate runtime from the same trusted Linux/Wine base used by the
ordinary backend. The base must contain Wine64, Python, Xvfb and MinGW:

```bash
python -m fdisbull.ida_runtime \
  --base-initramfs /private/base.cpio.gz \
  --output /private/ida-runtime.cpio.gz

fdisbull debug /private/analysis.fdb \
  --backend ida-wine-qemu \
  --executable /path/to/qemu-system-x86_64 \
  --kernel /path/to/linux-amd64 \
  --initramfs /private/ida-runtime.cpio.gz \
  --remote-server '/path/to/IDA Professional 9.4/dbgsrv/win64_remote.exe' \
  --game-dir /private/program
```

Python uses `project.debugger(..., backend='ida-wine-qemu',
remote_server=SERVER, kernel=KERNEL, initramfs=RUNTIME)`. The foreground JSON
`debug-launch` method accepts the same arguments. Project addresses, original
code/version guards, scripts, 8px grids and offline artifact exports use the
existing fDisBull APIs. The executable and explicit asset allowlist are checked
before launch. The selected runtime must match all current controller sources.

## Bounded trace collection

`debug.trace(name, count=N, timeout_ms=T)` runs its stepping loop in the Linux
controller. One host request collects the bounded batch. The controller reuses
the post-step integer registers as the next instruction's pre-step snapshot,
reads code again on every fetch, and holds peer threads across the batch. A
thread created during the batch is held before its start event is continued.
No instruction cache is used, so a later visit can observe self-modified code.

The limits remain 1..10,000 instructions and 1..600,000 ms. Only confirmed
native single steps become completed trace events. Exceptions and other stops
end the batch. A deadline between instructions returns the completed prefix
and a stopped timeout; an unfinished native step closes the connection rather
than presenting an uncertain CPU as resumable. Cleanup and transport overhead
can extend elapsed host time beyond the requested execution budget.

An execution breakpoint at the next observed PC stops before that instruction.
When the stop comes from inspecting a native STEP, evidence records
`stop_origin: single-step-boundary` and preserves the actual native STEP event.
It does not invent a native breakpoint event. Resuming completes the displaced
instruction once and rearms the breakpoint. A host budget that expires before
the batch starts is reported in the returned trace; a later status query can
still show the preceding native stop.

Stored traces retain instruction bytes, pre-instruction integer registers,
RAM/execution bytes, active RAM-layer identity, project addresses and decoded
instructions. They export after the live session and project have closed.
The prepared runtime includes `remote/ida_trace.py` in its verified source set;
rebuild older development runtimes before using this collector.

The replayable performance probe is
[`examples/synthetic/benchmark_ida_trace.py`](../examples/synthetic/benchmark_ida_trace.py).
It uses the authored PE fixture and a guarded temporary NOP/NOP/JMP loop,
alternates collector order, verifies instruction/register results, and saves
traces and an 8px screenshot privately. `--backend wine-qemu` measures the
existing engine with its own matching runtime. Runtime tracing and static
disassembly are separate performance claims.

## DOS endpoint

Use the existing patched, heavy-debug DOSBox layers build:

```bash
python -m fdisbull.ida_dosbox /private/dos-project.fdb \
  --executable /path/to/dosbox-x --game-dir /private/game
```

The first stdout line is JSON with the loopback host, selected port, interface
31 and debugger ID 10. One connection owns one real-mode DOS CPU. The endpoint
starts only its selected original project, validates the executable hash and
reaps the emulator on disconnect or deadline. The default idle limit is 120s;
`--idle-timeout` sets 1..3600s. It never binds an external interface.

```python
import socket
from fdisbull.ida_dosbox import DOSRemoteDebugger

debug = DOSRemoteDebugger(socket.create_connection(("127.0.0.1", port)))
try:
    started = debug.start("GAME.EXE", bits=16)
    base = started["module"]["base"]
    bp = debug.breakpoint(base + 3)
    stopped = debug.run(timeout_ms=2000)
    print(stopped, debug.registers())
    debug.delete_breakpoint(bp)
    frame = debug.extension("screenshot", name="frame.png", grid=True, grid_step=8)
finally:
    debug.close()
```

Wire addresses are actual runtime linear addresses. Segment registers and EIP
retain their real-mode values. Do not add project relocation twice. The
endpoint converts an execution address to the canonical segment:offset pair
`segment = linear >> 4`, `offset = linear & 0xf`; the native heavy-debug hook
compares physical fetch addresses, including CS aliases. Instruction bytes are
unchanged even when a caller requests a software-breakpoint operation.

The common debugger messages cover initialization, launch, events, pause,
continue, step-into, integer/segment registers, memory, execution/data watches,
memory map and breakpoint deletion. DOS has one emulated CPU thread.

The explicitly namespaced fDisBull IOCTL (`0x01004644`) adds `run`, `trace`,
`screenshot`, `click`, `click-frame`, `layer-patch`, `layer-enable`, `layers`,
`save-state` and `load-state`. These use the existing project-bound APIs and
persist real evidence. Extensions update the controller's pending event after
CPU movement. Delete wire breakpoints before state capture/restore; there is
not yet a saved wire-client breakpoint registry. Native state bytes remain in
the private project. This extension is not a vendor IDA capability.

## Current boundary

DOS execution layers retain separate RAM/fetch views, including guest reads of
their own code. PE execution-only layers and native-state reconnection are not
yet qualified for the IDA endpoint; their methods reject explicitly. Continue
using `wine-qemu` for those PE features and PE data watchpoints. The IDA
adapter rejects data-watch requests until their native stop semantics are
qualified; a successful hardware-breakpoint installation was insufficient in
the actual Wine/QEMU test. RAM layers remain explicit paused edits.

The DOS endpoint has no IDC interpreter and advertises no IDC/conditional-
breakpoint support. IDA's Windows server has low-level IDC condition machinery;
this adapter has not exposed or qualified it. Full IDA GUI interoperability,
other IDA versions, PE32/WoW64, process-tree following, native Linux ELF debugging,
guest register-read filters and a QEMU CPU-hook endpoint are separate work.

No IDA executable, target program, game asset, database, emulator checkpoint,
license key or boot image belongs in the repository or tool distributions.
