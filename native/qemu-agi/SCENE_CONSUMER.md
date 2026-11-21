# Stopped AGI actor-position consumer

The optional native observations now feed one shared actor-position consumer
and a thin adapter around a caller-owned QEMU instance. This host-side layer
adds no native helper, flag or ABI change.

## Shared behavior

`fdisbull_core.agi_scene.AGISceneConsumer` is a standard-library-only module. It
does not import either application, start QEMU, own a process, alter guest
controls, or make interpretation decisions for a full game engine. Both
products pin the independently built shared package at `0.1.0.dev3`.

It accepts the native `agi-2917-scalar-position-pilot-1` profile: 16 actors,
byte-valued coordinates, immutable raw code identity, and selected position
records. The view provides source identity, session identity, a stopped
checkpoint, guest stop/fault state, actors and their optional witnesses, and
coverage information.

### Two separate facts

The actors are current **as of the recorded stopped checkpoint**. History
completeness is a separate statement about the interval **since attachment**.
An attachment after earlier execution or buffer loss may have fully current
positions without claiming any earlier observed history. The cursor begins
after every eligible event, including already dropped records; retained records
are checked but not replayed into the initial snapshot.

For new scene records, the consumer validates source/session identity, schema,
sequence and retirement order, control generations, epoch and channel
accounting, and the full retained prefix. Position witnesses must obey the
profile's opcode, extent, actor and successor constraints. A literal-position
instruction's coordinates must agree with its immediate operands. Before/after
states must chain correctly and the resulting actors must match the next
snapshot. Accepted raw records are retained as witnesses, with detached inputs
and outputs.

The consumer requests resynchronization for gaps or unexplained discontinuity.
Examples include execution with SCENE disabled, newly dropped scene records,
epoch changes, uncheckpointed control changes across executed instructions, or
a mismatch between deltas and current actors. DISASM-only loss does not by
itself imply lost scene history.

Resynchronization adopts current positions promptly, clears witnesses that
would imply a continuous chain, increments the gap count, and preserves the
last gap's reason and checkpoint boundary. Completeness stays false for the
attachment after a gap, even if later deltas are complete. Callers needing the
entire gap history retain capture receipts; the current view holds the latest
gap and total count.

Malformed input, wrong source/session, stale counters and changed retained
history raise `SceneInputError`. Failed validation and a resync request leave
the old projection unchanged. A new source/session requires explicit attachment.
The consumer checks witness consistency; it does not independently decode the
program bytes or prove complete-game equivalence.

### Native adapter and ownership

`native/qemu-agi/scene_harness.py` supplies `AGISceneHarness` around an existing,
caller-owned `QemuAGI`. Each attachment has a fresh UUID. A capture reads state,
events, then state again and requires equality of the complete state objects.
A changing bracket raises without retrying or advancing the consumer.
Serialized access remains a caller obligation; the bracket is not a lock.

The adapter applies valid new deltas or immediately resynchronizes from the
same coherent stopped snapshot. Explicit mask, capacity, budget, clear and
restart operations capture pending changes first and then checkpoint the
result. Successful controls preserve the preliminary `pending_update`; a
budgeted run retains the full control result as `preparation`. A plain run
adds no hidden control setter or restart.

Independent review found that a rejected control could otherwise hide a
successfully captured pending delta from the caller. The fix introduces
`SceneOperationError` with an operation, stage, original chained cause and
detached successful receipts. Control failures retain `pending_capture`;
failure after successful budget preparation retains `preparation`. Initial
capture failure remains transactional and unwrapped. The error does not imply
native rollback or authorize replay of an uncertain operation.

## Actual authored demonstration

The standalone CLI uses a 21-byte, six-instruction program and an explicit
executable. It requires a new output file, finite bounded controls, and no more
than six resumes. The demonstrated budget was two instructions per resume,
therefore three captures per case. It contains no game resource.

| PC | Effect |
| --- | --- |
| 0 | Set actor 0 to (10, 20) |
| 4 | Set actor 1 to (30, 40) |
| 8 | Repeat actor 0 at (10, 20); no changed-position event |
| 12 | Set actor 0 to (50, 60) |
| 16 | Set actor 1 to (70, 80) |
| 20 | Return |

All five runs returned normally after six retired instructions. Every final
view agreed: actor 0 at (50, 60), actor 1 at (70, 80), and all other actors at
zero. The selected profile sets previous-coordinate fields to the new
coordinates; historical movement comes from the records, not those fields.

| Mode | Capacity | Stored records | Dropped records | Complete scene history since attach | Final handling |
| --- | ---: | ---: | ---: | --- | --- |
| OFF | 64 | 0 | 0 | No | Three snapshot refreshes; `observation_disabled` |
| DISASM | 64 | 6 | 0 | No | Three snapshot refreshes; `observation_disabled` |
| SCENE | 64 | 4 | 0 | Yes | Apply batches of 2, 1, 1 scene changes |
| BOTH | 64 | 10 | 0 | Yes | Same scene batches, plus six retirements |
| SCENE with overflow | 1 | 1 | 3 | No | Three snapshot refreshes; `scene_records_lost` |

The complete SCENE/BOTH views preserve actor 0's final witness at PC12 and actor
1's at PC16. OFF and overflow retain useful current positions without inventing
the missing path. This demonstrates the intended harness behavior; it is not
a new timing benchmark or a whole-game performance result.

## Shared Python API

Install the matching fdisbull-core==0.1.0.dev3 package. The caller supplies a
coherent stopped state/events pair and an opaque identity for that attachment.

    from fdisbull_core.agi_scene import AGISceneConsumer

    consumer = AGISceneConsumer.from_snapshot(state, session_id=attachment_id)
    update = consumer.consume(events, state, session_id=attachment_id)
    if update["needs_resync"]:
        update = consumer.resync(
            state, reason=update["reason"], session_id=attachment_id,
        )
    view = consumer.view()

Updates contain status, needs_resync, reason and changes. Status is applied,
unchanged, resync_required or resynced. Changes are the complete raw accepted
position records. A refresh invents no changes. The view has source/session
identity, checkpoint, guest, actors and coverage fields; all outputs are
detached copies. Completeness starts at attachment, not program start.

## Owned adapter API

From the native experiment directory, with shared core installed:

    from harness import QemuAGI
    from scene_harness import AGISceneHarness, DEMO_CODE

    with QemuAGI(explicit_binary_path, DEMO_CODE) as vm:
        scene = AGISceneHarness(vm)
        scene.configure(mask=2, capacity=64, step_budget=2)
        first = scene.run()
        second = scene.run()
        third = scene.run()

The attachment field holds the initial receipt with status attached. capture()
returns an update and detached view. view() is the last successful checkpoint.
configure(), clear_events(), and restart() preserve pending_update.
run(step_budget=...) preserves the full configuration receipt as preparation;
run() has no hidden setter or restart.

SceneOperationError.operation identifies configure, restart, clear_events or
run. Its stage is control, run or capture. The original failure is __cause__.
Control failures retain receipts["pending_capture"]; failures after successful
budget preparation retain receipts["preparation"]. Direct capture and
unbudgeted-run failures keep their original exception types because no
preparatory receipt was consumed.

The caller must serialize VM access. State/events/state comparison is not a
lock. After a failed control or run, inspect the actual stopped state before
continuing; multiple setters are not an atomic rollback group.

## Demonstration and verification

From the repository root, after installing shared core:

    python native/qemu-agi/scene_harness.py \
      --binary /absolute/path/to/qemu-system-agi \
      --output /new/private/path/scene-demo.json \
      --mask 2 --capacity 64 --step-budget 2

The CLI accepts masks 0..3, capacity 0..65,536, budgets 1..4,096 and finite
timeouts of 0.1..30 seconds. It refuses existing output paths and retains
failed-attempt receipts. Only the embedded authored program runs.

    python -m pytest packages/fdisbull-core/tests/test_agi_scene.py
    FDISBULL_QEMU_AGI=/absolute/path/to/qemu-system-agi \
      python -m pytest tests/test_qemu_agi_observation.py tests/test_qemu_agi_scene.py

An unset binary produces visible native skips. An invalid explicit binary
fails. Independent raw-byte oracle checks remain the native semantic gate.

## Scope and cost

This is the bounded 16-actor scalar/position profile. A renderer, editor UI,
resource loader/writer, animation, collision, room transitions and complete
AGI execution remain separate. Product backend defaults and original-DOS QEMU
parity qualification retain their existing ownership and requirements.

Each capture validates and copies the complete retained journal, including
fingerprints of its prefix. Host work grows with the bounded native capacity.
Large-journal latency and complete-game performance remain unqualified.
See the [native overview](README.md) for build and interpretation constraints.
