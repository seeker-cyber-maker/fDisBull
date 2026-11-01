# Bounded checkpoint-backed debugger rewind

Rewind adds an owned history and a backward cursor to the existing native DOS
checkpoint mechanism. It captures a checkpoint before each requested forward
step, then restores the selected checkpoint when asked to go back. Restoring
does not become intrinsically faster because it is called rewind.

This first implementation records **next-fetch intervals** in a live native
DOSBox session. Each interval requests two fetch observations and stops at the
second. The backend does not certify general instruction retirement: REP,
interrupts and other exceptional control flow retain their existing unknown
completion semantics. This is not arbitrary reverse execution, deterministic
replay, or a log of every memory write.

## API

Use the foreground `serve`/`debug` owner's JSON interface, with the live `run`
identifier. Python callers use the corresponding methods on `DebugSession`.

| JSON method | Python method | Parameters beyond `run` |
| --- | --- | --- |
| `debug-rewind-start` | `rewind_start` | `max_steps=16`, `max_bytes=67108864` |
| `debug-rewind-record` | `rewind_record` | `count=1`, `timeout_ms=10000` |
| `debug-rewind-status` | `rewind_status` | None |
| `debug-rewind` | `rewind` | `count=1` |

The same route operations are `rewind-start`, `rewind-record`, `rewind-status`
and `rewind`. For example, inside an existing live debugger:

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"rewind-start","max_steps":8,"max_bytes":67108864},
  {"op":"rewind-record","count":4,"timeout_ms":20000},
  {"op":"rewind","count":2},
  {"op":"registers","as":"earlier_cpu"},
  {"op":"rewind-status","as":"history"}
]}
```

Recording advances the guest. Rewind restores without replaying intervening
instructions. Recording after rewinding begins a new branch of the live
index; earlier immutable checkpoint and trace artifacts remain in the project.

The cursor belongs to this live session. Saved project artifacts and events
survive closing it, but do not reconnect the emulator or automatically revive
a rewind cursor. Individual states can still be inspected or restored through
the existing checkpoint APIs in a separately compatible session.

## Bounds and failure behavior

- Native DOSBox and native save-state support are required. PE64, QEMU machine,
  DOSBox/QEMU transport and static Cortex-M analysis are outside this first scope.
- Maximum captures are 1–128 per history; checkpoint payload budget is
  1 byte–256 MiB. The default is 16 captures and 64 MiB. These cumulative limits
  include discarded branch captures. A new history does not delete old artifacts.
- Capacity is checked before recording starts. Checkpoint size is checked
  before storing the new state or advancing the guest. Trace and audit artifacts
  have their existing separate project limits.
- Read-only inspection preserves history. An unrecorded execution, input,
  control/layer change or external state load invalidates the live cursor.
  Start a new history; retained states remain available for explicit restoration.
- An incomplete trace, unexpected stop or failed operation never becomes a
  certified recorded interval. Failure retains evidence and invalidates the
  cursor; there is no automatic replay or rollback.

Native state restore retains the existing source/version/emulator/profile and
mounted-file identity checks, CPU readback, layer restoration, runtime-binding
invalidation and close-on-partial-deserialization behavior. It covers the devices
handled by the native serializer, not arbitrary host files. A changed mounted
file blocks restoration. Pending input must be drained before a checkpoint.
See [native checkpoints](DEBUGGER_SCRIPTS.md).

## Compare costs rather than names

`scripts/benchmark_rewind.py` uses an authored tiny DOS program on a selected
real native backend. Its output directory must be new and outside Git. It
measures forward execution with and without per-step recording, then compares
rewind with direct `load_state` of the **same** checkpoint artifact. It verifies
the expected PCs, CPU values and complete mapped RAM separately from timing.

The useful trade is automatic selection of a recent recorded boundary versus
capture time and retained state storage. Direct restoration remains preferable
when the desired checkpoint is already known. This implementation does not
provide undo-log or record/replay performance advantages; the benchmark reports
individual observations and bounded local results.

### Local macOS comparison

Three trials per pinned native profile used an authored 512-byte mapped DOS
module, twelve intervals and identical checkpoint artifacts for the two restore
routes. Medians below include API work and exclude the separate post-operation
CPU/RAM verification. Runs were serialized after the test suites completed.

| Operation | Stable | Layers |
| --- | ---: | ---: |
| Advance 12 intervals in one ordinary trace | 12.13 ms | 12.15 ms |
| Advance using 12 separate ordinary trace calls | 134.25 ms | 133.44 ms |
| Advance 12 intervals while recording checkpoints | 2,463.82 ms | 2,464.17 ms |
| Rewind to the point 4 intervals behind the end | 18.50 ms | 18.56 ms |
| Directly load that same checkpoint | 16.68 ms | 16.94 ms |
| Checkpoint payload retained for those 12 intervals | 974,267 bytes | 973,824 bytes |

All eighteen rewind/direct-load pairs across both profiles matched exposed CPU
register groups and every mapped RAM byte. Capture overhead was about 18 times
twelve separate trace calls, or 203 times one batched trace. Returning farther
back did not require replay: targets one, four and twelve intervals behind the
end used similarly sized full native states.

These are small local measurements, not real-game throughput estimates. Rewinds
were measured before the direct-load controls, so cache/order can favor the
controls. Full state capture and mounted-file hashing can cost more for larger
targets. An initial benchmark attempt exposed a wrong zero-stack assumption in
the harness; the corrected oracle preserves observed DOS startup RAM and applies
only independently declared writes. That failed attempt remains in the private
verification packet.

For a known checkpoint, direct load is simpler and was slightly faster here.
Checkpoint-backed rewind is useful when selecting earlier points during a short
recorded investigation. Long histories would need a different storage strategy,
such as an independently qualified delta log or checkpoint/replay mechanism.

For the broader terminology, GDB distinguishes
[reverse execution](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Reverse-Execution.html)
from its [process record/replay mechanisms](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Process-Record-and-Replay.html).
Our current mechanism is native checkpoint history, not GDB's recorded-memory
replay or branch tracing.
