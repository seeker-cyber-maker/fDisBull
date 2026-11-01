# Windows/Wine delta rewind

Wine/QEMU supports the same `debug-delta-start`, `debug-delta-record`,
`debug-delta-status`, `debug-delta-rewind` and `debug-delta-recover` operations
as the [DOS prototype](CPU_RAM_DELTAS.md), with a Windows-specific projection.
An **Anchor Stone** saves the complete native VM context; delta rewind restores
only declared RAM and exposed registers for the selected Windows thread.

This works with the prepared x86-64 Wine/QEMU runtime hosted on macOS/ARM64.
It does not add native Windows-host qualification or a native macOS/ARM64
target debugger. IDA/Wine/QEMU remains excluded.

## Admission and recorded state

Use an original x86-64 PE project in a live `wine-qemu` session. The target must
be stopped at an executable main-image address, with no active layers, relocated
instruction, user breakpoints or watchpoints. Complete or remove those controls
before starting the recorder. The selected thread is pinned across register,
stop and trace observations. Each interval is **one completed selected-thread
instruction**, unlike DOS's next-fetch intervals; neither unit is a video frame.

RAM ranges must fit writable, non-executable main-image regions. They use flat
project addresses, translated through the observed runtime image base. Up to
64 nonoverlapping ranges and 64 KiB combined are accepted. Heap, stack, other
modules, shared mappings and device memory are outside this first scope.
The CPU projection covers 16 general registers, RIP and full exposed RFLAGS;
the thread ID is identity evidence and is never edited. General registers and
RIP retain 64-bit values, while native RFLAGS fits 32 bits. Undo preflights the
reserved flags mask and executable target RIP before the first memory write.

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"delta-start","ranges":[{"address":"0x140003000","length":4}]},
  {"op":"delta-record","count":3},
  {"op":"delta-rewind","count":1},
  {"op":"registers","as":"earlier_cpu"},
  {"op":"delta-status","as":"scope"},
  {"op":"delta-recover"}
]}
```

The address is illustrative; select the actual writable range in your project.
The same operations are available through `cpu_delta_*` Python methods and the
foreground JSON debugger owner. Literal range structure/length budgets are
checked before any script step executes; dynamically resolved values and
project mapping are checked before recording.

New register/memory/status RPCs honor the remaining shared recording or script
deadline. Expiration invalidates an incomplete recording instead of reporting
success. An already dispatched native serialization retains its own RPC deadline.

## Refusal, failure and recovery

Before undo, the recorder validates the full selected CPU/RAM projection,
thread, project/run/backend identity, host input identities, retained artifact
hashes and parent chain. Native guarded writes and complete readback follow.
The operation and both debugger contexts share one lock; another caller cannot
interleave an edit between validation and readback. Partial native application
or uncertain readback closes the session rather than attempting an automatic
rollback or resume.

A successful undo is still **partial**. Hidden CPU/FPU/SIMD state, other threads,
unselected memory, guest services, devices, timers and files are not rewound.
By default, normal execution, input, new snapshots, screenshots and ordinary edits are
refused until full native recovery. A previously obtained outer-machine handle
cannot bypass the guard. Read-only selected-register/RAM/status inspection and
further guarded undo remain available. A clean refusal leaves recovery possible.
Runtime code snapshots (`capture-code`), including scripted captures, are also
refused before any observation or artifact creation; ordinary code inspection
remains available. Capture becomes available again after full native recovery.
The explicit experimental policy below can instead permit continuation and
captures from a deliberately mixed state; that permission does not certify a
complete historical machine context.

`delta-recover` or a successful compatible `load_anchor_stone` restores the full
native context and leaves the target stopped. Failed recovery retains the guard.
The native manifest and sidecar hashes, actual runtime files, staged input
identities and restored registers are checked; changing a runtime file on disk
cannot silently substitute a different VM during recovery. Histories belong to
one live session; project restart preserves artifacts, not a resumable delta cursor.

## Preserve selected current state during rewind

The shared [agent-specified policy](CPU_RAM_DELTAS.md#agent-specified-rewind-policies)
is also available for Wine through `cpu_delta_rewind(..., policy=...)`, the
`debug-delta-rewind` JSON method and the `delta-rewind` script operation. For
example, after recording a target's relevant RAM:

```json
{"op":"delta-rewind","count":2,"policy":{
  "name":"preserve-rng",
  "preserve_memory":[{"address":"0x140003010","length":8}],
  "preserve_registers":[],
  "allow_partial_resume":true
}}
```

Use actual project addresses for a target's identified RNG state. Wine ranges
must be flat, contained in the history's selected writable, non-executable
main-image RAM, and nonoverlapping. `preserve_registers` names exposed x86-64
registers; the pinned thread ID is identity evidence and is never a register
edit. This is no generic RNG adapter: incomplete or incorrectly identified RNG
state remains the caller's experiment assumption.

Undo checks the full current projection before writing and verifies the mixed
result, including preserved values, afterward. Any policy invalidates the old
delta chain while retaining its full recovery Anchor Stone. An explicit
`allow_partial_resume:true` permits later execution and capture, leaves the
target stopped on return, and reports `execution_allowed:true` alongside
`resume_safe:false` and `partial_restored:true`. The `experiment` receipt/status
object retains the policy, preserved register values, hashes of preserved memory
and full projection fingerprints; subsequent captures retain that provenance.
Without that flag, the mixed result remains frozen until full native recovery.
Starting another recording requires a new history and recovery Anchor Stone.

This enables agent-directed input experiments; it does not qualify full-machine
rewind, deterministic TAS replay or safe continuation for an arbitrary game.
Wine counts remain completed instructions rather than video frames.

## Budgets and comparison

Wine defaults to 16 captures and **2 GiB** cumulative anchor-plus-delta payload;
captures are limited to 1–128. The complete recovery Anchor Stone is charged:
its small manifest **plus its native migration sidecar**. Each forward interval
reserves a conservative delta budget before executing. Traces retain their
separate existing limits. The existing native limits remain: 2 GiB compressed
per state, 8 GiB expanded, and 6 GiB retained native sidecars per project.
Oversize captures are rejected before committing their sidecar or artifact.
DOS keeps its existing 64 MiB default and 256 MiB maximum.

`scripts/benchmark_wine_deltas.py` compares three instructions of the authored
PE self-test with an independent MOV/RET/JMP oracle. Each trial uses one saved
starting context for both recording modes, alternates mode order, and compares
delta undo with direct loading of the exact Anchor Stone at the same boundary.
It separately reports start/recovery-anchor cost, recording, undo, native load,
native recovery and manifest/sidecar/trace storage. It checks all exposed CPU
values, the pinned thread, selected RAM, frozen-state refusals and native recovery.

The experiment is a selected-state microbenchmark, not equivalent whole-machine
rewind or a general Windows-game throughput result. Raw states, databases,
authored inputs and reports belong in a new private directory outside Git.
See the merge request's local measurement receipt for the measured source and
host/runtime identities; earlier DOS timings do not measure Wine migration.
