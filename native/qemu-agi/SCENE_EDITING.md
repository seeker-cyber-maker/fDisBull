# Source-linked literal placement edits

The bounded AGI prototype can turn a captured actor position into a reviewable
edit of the instruction that produced its last observed change. A separate
candidate execution establishes what the edited program actually does. This is
the first scene-design action built on the [scene consumer](SCENE_CONSUMER.md).

## Pure shared API

```python
from fdisbull_core.agi_scene import plan_literal_position_edit

plan = plan_literal_position_edit(
    original_code, captured_result["view"], actor=0, x=30, y=40,
)
```

The caller supplies immutable raw code bytes and a coherent stopped view already
returned by the consumer/adapter. The planner captures nothing, writes nothing,
changes neither argument, and has no process or application dependency. Invalid
input raises `SceneInputError`.

The first contract supports only four-byte literal `position` instructions
(opcode 37) in profile `agi-2917-scalar-position-pilot-1`. Actor IDs are 0–15 and
coordinates are byte values 0–255; booleans are refused. It does not infer screen
geometry or clamp coordinates. `position.v` (opcode 38) is explicitly refused
because its operands identify variables rather than literal coordinates.

Admission requires exact source hash, length, profile and logic identity; complete
history since attachment with no recorded gap; a selected actor witness strictly
after attachment and within the captured checkpoint; and agreement between the
witness, current actor, instruction span and all four source bytes. Witnessed
execution requires a later invocation and a stopped state after execution.
Checkpoint counters and epochs must be consistent. A harmless stopped control
change may leave an older witness generation or the SCENE flag currently disabled.

The result uses schema `fdisbull-agi-literal-position-edit-1`:

| Field | Meaning |
| --- | --- |
| `session_id`, `checkpoint`, `source` | Exact recorded attachment and original program identity |
| `actor`, `witness` | Selected actor and copied observation |
| `offset`, `length` | Code-relative PC and four-byte instruction span |
| `expected_bytes` | Exact original instruction preimage |
| `replacement_bytes` | Same opcode/actor with requested x/y operands |
| `requested_position` | Requested coordinate operands, not an observed scene |
| `candidate_source` | Same profile, logic ID and size, with candidate SHA-256 |
| `changed` | False for a same-coordinate no-op |
| `write_performed` | Always false |
| `scope` | `static_instruction`: every execution of that PC changes |

Returned nested values are detached. The consumer and its captured view remain
unchanged. A caller can construct a separate candidate after checking the preimage:

```python
offset = plan["offset"]
assert original_code[offset:offset + 4] == bytes(plan["expected_bytes"])
candidate = (
    original_code[:offset]
    + bytes(plan["replacement_bytes"])
    + original_code[offset + 4:]
)
assert len(candidate) == len(original_code)
assert hashlib.sha256(candidate).hexdigest() == plan["candidate_source"]["sha256"]
```

The example assumes `hashlib` is imported. A production caller should handle a
failed preimage or identity check as an explicit refusal before execution. The
demonstration uses ordinary runtime checks rather than assertions for this seam.

## Why fresh replay matters

A SCENE witness records the last **effective position change**, not necessarily
the last assignment. An assignment that leaves the actor unchanged emits no
position-change record. Consider this authored input:

```text
PC 0: position(0, 10, 20)
PC 4: position(0, 10, 20)
PC 8: return
```

Its only original position witness points to PC 0. Replacing that instruction's
operands with `(30, 40)` is an exact source edit. On fresh execution, PC 4 still
restores `(10, 20)`. The plan is valid, but the requested final placement was not
achieved. The replay receipt reports `placement_matched: false`.

An edit also affects every future visit to the selected PC, and coordinates can
flow through `get.posn` into later variables or control flow. The planner does
not infer a final scene or certify whole-program equivalence. Hashes establish
byte identity; consistency checks do not authenticate caller-supplied JSON or
prove that a historical snapshot is current in a later live process.

## Bounded native demonstration

Install the matching shared package and use an explicitly selected qualified
`qemu-system-agi` binary:

```sh
python native/qemu-agi/scene_edit_harness.py \
  --binary /absolute/path/to/qemu-system-agi \
  --output /private/new-scene-edit-receipt.json
```

The output must be new. The CLI reserves it before starting a child and retains
partial receipts on failure. Optional `--evidence-dir` names an existing private
directory for failed native-run evidence; `--timeout` is bounded to 0.1–30 seconds
per harness operation. There are no retries and at most four owned children,
each with one resume and a four-instruction budget.

Each original child returns and closes before its separate candidate starts.
Original and candidate bytes, source hashes, attachment identities, observations
and complete final guest states are retained in the JSON receipt. Candidate
preimage, size and hash are checked before replay. The CLI uses SCENE alone:
mask 2, capacity 8, no DISASM observations.

The authored acceptance cases are:

| Case | Original position assignments | Requested edit | Observed candidate final position |
| --- | --- | --- | --- |
| Direct placement | `(10, 20)` | PC 0 → `(30, 40)` | `(30, 40)`; placement matched |
| Later assignment | `(10, 20)`, then `(10, 20)` | PC 0 → `(30, 40)` | `(10, 20)`; placement did not match |

These four original/candidate runs retire ten instructions in total. The second
original emits one SCENE record; its candidate emits two because the later
assignment now changes the position. An experiment status of `completed` means
both cases finished, while `all_requested_placements_matched` is false. Success
and mismatch remain separately visible.

Run the contract and real-native workflow checks with:

```sh
PYTHONPATH=packages/fdisbull-core/src \
FDISBULL_QEMU_AGI=/absolute/path/to/qemu-system-agi \
python -m pytest -q packages/fdisbull-core/tests/test_agi_scene_edit.py \
  tests/test_qemu_agi_scene_edit.py
```

## Product and native boundaries

The shared package advances to `0.1.0.dev4`, pinned separately by fDisBull and
DotBox. DotBox can use a small edit/replay action while building its harness;
fDisBull can retain the exact source proposal and observed outcome for later
recovery work. Neither policy treats a requested placement as a proven effect.

This host-side addition uses the existing CPU, observation controls and binary.
It adds no native compile requirement, default backend change, live patching,
resource archive writer, renderer or complete scene editor. It does not qualify
original-DOS QEMU parity, full-game compatibility, UDC export, macOS execution or
an end-to-end latency improvement. The legacy DOSBox-in-QEMU Python image still
needs regenerated shared-package resources before that deployment is reused.
