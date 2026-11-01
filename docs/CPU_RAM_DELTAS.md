# Delta rewind: experimental exposed-CPU and selected-RAM changes

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
| `debug-delta-rewind` | `cpu_delta_rewind` | Apply guarded reverse deltas without guest execution |
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
are required. Other execution backends and static Cortex-M analysis are outside
this prototype.

## A partial undo cannot silently become a machine rewind

Before applying any change, undo verifies the complete selected current CPU/RAM
projection, history identity, artifact hashes/chain and mounted-file identity.
It composes the requested earlier projection, performs guarded memory writes
and register edits, and verifies all selected bytes and registers afterward.
The native writes are multiple RPCs, not an atomic native transaction. A partial
apply or failed readback closes the session; it is never automatically resumed
or rolled back.

After undo, the response explicitly reports partial selected-state restoration,
with `full_machine_restored:false`. Normal execution, new recording, input,
screenshots and new native snapshots are blocked. Further delta undo and
read-only register/RAM/status inspection remain available. Starting a new
history cannot bypass this guard.

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
history. It cannot continue from that historical partial state: recovery jumps
back to the full anchor, or an explicitly loaded full checkpoint supplies a
different complete boundary. General resumable rewind still needs qualified
device/hidden-state handling or deterministic reconstruction from a full anchor.

The small three-trial, 512-byte RAM fixture does not establish throughput for
larger windows or real games. Selected-memory scanning and mounted-file hashing
can grow with the target. Native checkpoint methods also restore more state, so
the ratios are not claims of equivalent whole-machine functionality.
