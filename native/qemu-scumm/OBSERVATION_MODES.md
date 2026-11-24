# SCUMM DISASM and SCENE modes

The SCUMM CPU uses the same observation bit assignments and stopped-control
contract as the AGI raw CPU. The comparison source is AGI subtree
`aa35a891a27bd90ff53f63a32be2d45ae11f6d92`, last changed by
`5c59c9a03e8992149fcc2643dcf15298faa14816`. No AGI files are changed here.
Mode parity describes observation behavior; it does not imply equal engine,
renderer, resource-decoder or gameplay coverage.

| Mask | Selected records |
| ---: | --- |
| 0 | Observation off |
| 1 | DISASM: successfully retired instructions |
| 2 | SCENE: committed changes to the supported scene model |
| 3 | Both, with retirement before its associated scene change |

## Execution and capture

`scumm_execute_runtime` owns semantics. `scumm_observe` commits optional
records after successful retirement. Generated TCG passes a constant capture
mask to the semantic helper and emits the observer only for selected variants.
Mask zero passes no capture buffer and generates no observer call. A
SCENE-only instruction outside the potentially scene-changing operation classes
also needs neither. Canonical decode and instruction-byte registration remain
mandatory in every mode.

Return, yield and budget stops happen after the selected observations have
been committed. Faults and blocked effects stop before retirement and never
reach the observer. Dropping records, clearing the journal, reading snapshots
or changing masks must not acknowledge or skip a blocked effect.

The mode is part of the translation-block key. A stopped mask change selects
the correct translated variant, including when switching back to a previously
used mode. No blanket translation flush is needed.

## Stopped controls and identity

All QOM queries and control writes require one stopped TCG CPU.

| Property | Range or effect |
| --- | --- |
| `scumm-observation-mask` | 0..3 |
| `scumm-observation-capacity` | 0..4096, at least the current retained count |
| `scumm-step-budget` | 1..1,000,000,000 |
| `scumm-observation-clear` | Accepts only true; clears observations, advances epoch |
| `scumm-restart` | Accepts only true; resets guest/run state, clears observations, advances epoch |
| `scumm-decode-pc` | 0..code size, independent of guest PC |
| `scumm-decode-limit` | 1..64 static records |

Every accepted mask, capacity or budget write increments control generation,
including a write of the existing value. These writes retain journal contents
and epoch. Clear and restart each increment control generation once. Reads
and static listing selectors change neither generation nor epoch. Invalid
controls fail before mutation; exhausted control/epoch counters cannot wrap
through an accepted QOM write.

Clear preserves guest state, last-run retirement, immutable source, controls
and listing selectors. Restart and QMP system reset preserve source, controls
and selectors while resetting architectural/runtime state and the journal.
The epoch distinguishes reused sequence and retirement numbers after resets.
It is local to a CPU process; callers must separately identify their process or
attachment session when collecting records across executions.

## Bounded storage and loss

Both channels share one fixed maximum journal. Every eligible event advances
the logical sequence and its channel's eligibility counter, even when dropped.
When full, storage drops new events. Increasing capacity can resume storage,
so retained sequence numbers may contain gaps after a drop-and-grow interval.
Reads are repeatable and do not consume records.

Per-channel `eligible = stored + dropped`; `count` is the sum of stored
counts, and `sequence` is the sum of eligible counts within the current epoch.
Capacity zero is valid and counts all selected events as dropped.
`helper_calls` counts reached optional observer calls, including calls that
discover a no-op scene assignment; it does not count the mandatory semantic
helper or unsuccessful instructions. Clear resets all these counters.

## DISASM and static decoding

Live records identify the source instruction, exact bytes, retirement number,
actual successor and historical resolved inputs. The decoded object preserves
encoded operand tuples `[kind, value, width]`: immediate 0, variable 1,
destination 2. `resolved` contains historical values obtained while resolving
the encoded operands, not values reconstructed from a later state or a claim
that every value is an arithmetic input. Destination facts identify the
actual write index and its before/after value. For range writes this describes
the first destination; the encoded payload describes the remaining writes.

SCUMM v1/v2 variable reads at indices 14..16 can redirect through another
variable. INC/DEC perform that read even though their encoded operand is a
destination; indirect assignment has a separately resolved destination.
These facts must not be collapsed into a single ambiguous address/value field.

`next` in the event is the actual successor. `decoded.next` is the encoded
fall-through. Conditional branches take their relative target when the
condition is false; `branch_taken` records that outcome. Nonbranch rows use
null for this field.

Static decoding remains independent of retirement and observation mode. Its
bounded page includes source identity, exact successful instruction bytes,
start/next PC, limit and an explicit stop reason. The existing decode-fault row
is retained for compatibility; it has no successful extent or invented bytes.
A linear listing can include unreachable instructions after return. It is not
an execution trace.

## SCENE scope

SCENE emits typed committed changes:

- `actor`: full placement and metadata before/after, including room, palette
  entries and known membership, and exact immutable-code name spans/bytes.
- `default_talk_color`: before/after global value.
- `resource`: immutable resource identity and before/after availability,
  residency and locking. Loading bytes and logical residency remain distinct.
- `control`: cursor, user/interface, saved cutscene and override state, UI
  invalidation revision, and the exact relevant variable values at the operation.

An unchanged actor, default-color or resource assignment produces no SCENE
row. An accepted cursor operation increments the model's UI invalidation
revision even when its flags repeat, so it produces a control row. This
revision does not count rendered frames or draw calls.

The control snapshot's variable keys are 21, 26, 27, 28, 29 and 38. General
scalar instructions may write those variables without being a scene operation;
their presence in a control record does not establish a complete variable
history. The current coherent scene snapshot is authoritative for the model's
endpoint. Missing, cleared, disabled or dropped history is not reconstructed.

Actor placement binding does not prove visibility. Room IDs do not prove a
rendered room or a completed room transition. Costume IDs and indexed palette
metadata do not establish decoded pixels or RGB colors. Script scheduling,
room/object rendering, walking, verbs, audio and cutscene exit remain outside
this implementation's completed execution subset.
