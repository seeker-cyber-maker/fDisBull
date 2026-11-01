# Delta rewind: experimental exposed-CPU and selected-RAM changes

This page describes native DOSBox. [Windows/Wine delta rewind](WINE_CPU_RAM_DELTAS.md)
uses the same history and recovery safeguards with selected-thread x86-64
registers, writable main-image RAM, and completed-instruction intervals.

This prototype records net changes to exposed real-mode registers and explicitly
selected project-mapped RAM between the same next-fetch boundaries used by
[MR !14 checkpoint history](DEBUGGER_REWIND.md). It stores changed register
before/after values and changed RAM runs, not a full native state at every step.
One full native **Anchor Stone** is retained for recovery when the history starts.
An Anchor Stone jumps directly to a saved native context; delta rewind follows
recorded changes. The name comes from TiGa's Blob to General game; see
[Anchor Stones and the compatibility names](ANCHOR_STONES.md). Existing receipt
keys such as `anchor` keep their wire format and refer to this Anchor Stone.

This is a narrower restoration contract than a native checkpoint. Unselected
RAM, hidden CPU/FPU state, device state, timers, pending events and external
files are not restored by a delta undo. Fetch observations still do not certify
general instruction retirement. The recorder compares selected state around
each boundary; it is not an in-emulator journal of every memory write.

## Public operations

Use the existing foreground debugger owner and live `run` identifier.

| JSON method | Python method | Purpose |
| --- | --- | --- |
| `debug-delta-start` | `cpu_delta_start` | Validate explicit RAM ranges and capture one native recovery anchor |
| `debug-delta-record` | `cpu_delta_record` | Advance and record net selected-state changes |
| `debug-delta-status` | `cpu_delta_status` | Inspect scope, cursor, budgets and partial-state guard |
| `debug-delta-rewind` | `cpu_delta_rewind` | Apply guarded reverse deltas; optionally preserve declared current state with an experimental policy |
| `debug-delta-recover` | `cpu_delta_recover` | Restore the complete native anchor; no automatic resume |

The matching route operations are `delta-start`, `delta-record`, `delta-status`,
`delta-rewind` and `delta-recover`. For example:

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"delta-start","ranges":[{"address":"1000:0000","length":512}],
   "max_steps":16,"max_bytes":67108864},
  {"op":"delta-record","count":4},
  {"op":"delta-rewind","count":2},
  {"op":"registers","as":"earlier_selected_cpu"},
  {"op":"delta-status","as":"scope"},
  {"op":"delta-recover"}
]}
```

The range is illustrative: use the selected project's actual mapped addresses.
All ranges are explicit, nonoverlapping, ordinary mapped DOS RAM, at most
64 ranges and 64 KiB total. Video/ROM mappings are excluded. The supported CPU
projection is eight 32-bit GPRs, six 16-bit segments, 16-bit EIP and FLAGS, plus
real-mode admission. Native save-state and structured register-edit support
are required. Wine/QEMU has a separate adapter and contract linked above;
DOSBox-in-QEMU, IDA and static Cortex-M analysis are outside this DOS prototype.

## A partial undo cannot silently become a machine rewind

Before applying any change, undo verifies the complete selected current CPU/RAM
projection, history identity, artifact hashes/chain and mounted-file identity.
It composes the requested earlier projection, performs guarded memory writes
and register edits, and verifies all selected bytes and registers afterward.
The native writes are multiple RPCs, not an atomic native transaction. A partial
apply or failed readback closes the session; it is never automatically resumed
or rolled back.

By default, undo explicitly reports partial selected-state restoration,
with `full_machine_restored:false`. Normal execution, new recording, input,
screenshots and new native snapshots are blocked. Further delta undo and
read-only register/RAM/status inspection remain available. Starting a new
history cannot bypass this default guard. An explicit
[experimental policy](#agent-specified-rewind-policies) can permit continuation
from an intentionally mixed state; it does not make that state a complete
historical machine context.

`delta-recover` restores the original full native anchor and leaves the target
stopped. A successful explicit compatible native `load_state` also clears the
guard. Failed native recovery does not clear it. The existing file-manifest and
close-on-partial-native-restore checks remain in force. Recovery can be attempted
after a recording failure even when the current mode is outside delta admission.

Defaults are 16 captures and a 64 MiB cumulative payload budget, including the
anchor. Capture limits are 1–128, and payload budgets are at most 256 MiB. A
conservative encoded-size reservation is checked before each forward interval;
only actual retained payload bytes are charged. Trace and audit artifacts retain
their separate existing limits. Histories are live-session owned, and immutable
artifacts remain retained when a history ends.

## Agent-specified rewind policies

`cpu_delta_rewind(count=1, policy=None)` accepts an optional policy for input
experiments. The agent can rewind the recorded CPU/RAM projection while keeping
declared registers or memory at their values immediately before undo. For
example, an agent that has identified a game's complete RNG state can preserve
that state while returning the selected gameplay state to an earlier boundary.
There is no automatic RNG discovery or frame detection: counts remain DOS
next-fetch intervals or Wine completed-instruction intervals.

```json
{"op":"delta-rewind","count":2,"policy":{
  "name":"preserve-rng",
  "preserve_memory":[{"address":"1000:0100","length":4}],
  "allow_partial_resume":true
}}
```

The address is illustrative and must lie within the RAM ranges selected when
the history started. Calling a memory range `rng` does not establish its role;
the caller supplies target-specific evidence. A generator can have several
state words, cached values and an index, including values held in registers.

| Policy key | Meaning |
| --- | --- |
| `name` | A 1–128 character experiment name; defaults to `experiment` |
| `preserve_registers` | Unique exposed register names whose current values are retained; defaults to `[]` |
| `preserve_memory` | Nonoverlapping address/length ranges contained in recorded RAM ranges; defaults to `[]` |
| `allow_partial_resume` | Explicit boolean enabling experimental continuation; defaults to `false` |

Policy validation finishes before the first native write. Preserved memory
uses the selected backend's address rules and the existing range/size limits.
The encoded policy is limited to 32 KiB.
An unknown register, range outside the recorded projection, overlap, malformed
policy or identity/hash mismatch is refused. The complete current projection is
still checked, and the complete resulting projection is read back, including
the values deliberately preserved. Uncertain native application still closes
the session.

Supplying a policy ends the current delta chain: its earlier fingerprints do
not describe the deliberately mixed result. The original full Anchor Stone
remains available through `delta-recover`. A policy with
`allow_partial_resume:false` leaves the partial-state guard active. With
`allow_partial_resume:true`, the operation returns stopped but permits subsequent
execution, input and captures for the experiment. The receipt and status retain
`partial_restored:true`, `full_machine_restored:false` and `resume_safe:false`;
`execution_allowed:true` records the explicit permission rather than a safety
or whole-machine equivalence claim. Policy details, preserved register values
and hashes of preserved memory are retained in the `experiment` receipt/status
object and subsequent capture provenance. The experiment also records the
history/cursors, recovery anchor and full observed/resulting projection hashes.
Continuation is permitted only after complete readback and the experiment
receipt have succeeded.

After experimental continuation is enabled, start a new history to record the
next branch; it captures a new full Anchor Stone from that current context.
Recover the previous Anchor Stone before starting a new history if that earlier
recovery point must remain the active recovery target. Preserved historical
artifacts remain retained. An input trial's success does not qualify the policy
for another target or establish deterministic TAS replay.

## Comparison procedure

`scripts/benchmark_cpu_deltas.py` compares this mode with unchanged MR !14
checkpoint history and direct native loading on the same selected backend,
same authored fixture and same saved starting state. It separately reports
anchor/start cost, recording cost, total start-plus-recording cost, reverse
application, direct restore and retained bytes. Both modes are checked against
the same native checkpoint targets and independent authored CPU/RAM oracles.

CPU/RAM equality is the common measured projection, not evidence that delta undo
restored devices or can safely continue execution. Direct restore and MR !14
perform more restoration work. Speed ratios must retain that difference in scope.
The benchmark tests the execution guard and full native recovery rather than
resuming from a partially restored projection. All states, databases and raw
outputs remain in a new private directory outside Git.

### Measured local macOS result

Three trials per pinned native stable/layers profile used the same authored DOS
fixture and saved start, alternating recording-mode order. All eighteen target
comparisons across profiles matched all exposed CPU groups and all 512 selected
RAM bytes for delta undo, MR !14 rewind and the same native checkpoint load.
Every attempted ordinary trace after delta undo was refused without state change;
native anchor recovery restored the starting projection and left it stopped.

| Median operation or logical payload | Stable | Layers |
| --- | ---: | ---: |
| MR !14 start plus 12 recorded intervals | 2,458.51 ms | 2,512.63 ms |
| Delta start, including one full recovery anchor | 197.06 ms | 200.84 ms |
| Record 12 delta intervals, excluding start | 252.03 ms | 258.83 ms |
| Delta start plus 12 recorded intervals | 452.36 ms | 459.87 ms |
| MR !14 state payload for the 12 points | 974,339 bytes | 974,020 bytes |
| Delta payload alone | 17,290 bytes | 17,290 bytes |
| Delta payload including recovery anchor | 98,476 bytes | 98,449 bytes |
| All new MR !14 artifact payloads, including traces | 1,049,065 bytes | 1,056,456 bytes |
| All new delta-mode artifact payloads, including traces | 173,205 bytes | 180,886 bytes |

The start-plus-record comparison is about **5.4 times faster**. State/delta
payload including the anchor is about **10 times smaller**; counting supporting
trace artifacts gives about **6 times less logical payload**. These counts are
artifact payload bytes, not filesystem allocation or a deduplication guarantee.
Individual start/record medians need not sum to the median of measured totals.

| Cumulative target depth | Stable delta / MR !14 / direct | Layers delta / MR !14 / direct |
| --- | ---: | ---: |
| 1 interval behind the end | 15.95 / 17.45 / 17.13 ms | 15.46 / 17.42 / 17.30 ms |
| 4 intervals behind the end | 17.59 / 18.05 / 16.29 ms | 17.55 / 17.99 / 16.95 ms |
| 12 intervals behind the end | 20.22 / 17.05 / 17.05 ms | 19.32 / 18.80 / 17.05 ms |

Delta undo is not a consistent restore-latency improvement. It performs less
restoration work, but pays for guarded multi-RPC writes and chain/readback
validation. Its benefit here is collecting and retaining a short selected-state
history. The measured runs use the default frozen mode: recovery jumps back to
the full anchor, or an explicitly loaded full checkpoint supplies a different
complete boundary. The explicit policy mode permits intentional partial-state
experiments; these timings do not measure it or establish coherent whole-machine
continuation. General resumable rewind still needs qualified device/hidden-state
handling or deterministic reconstruction from a full anchor.

The small three-trial, 512-byte RAM fixture does not establish throughput for
larger windows or real games. Selected-memory scanning and mounted-file hashing
can grow with the target. Native checkpoint methods also restore more state, so
the ratios are not claims of equivalent whole-machine functionality.
