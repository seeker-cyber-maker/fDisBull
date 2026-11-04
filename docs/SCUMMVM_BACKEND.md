# Experimental ScummVM AGI execution backend

The `scummvm-agi` backend runs a separately built ScummVM 2.8.1 AGI engine with
an owned, inherited-socket debugger. It uses the real AGI interpreter and a
headless framebuffer. The source patch and build recipe are under
`experimental/scummvm`; the executable is outside the Python distribution.
The November 1 experiment preserved its then-active shared 0.29.0 installation.
Its dated receipts qualify that frozen implementation, preserved in commit
`b028527`; later integration and handoff checks are reported separately.

## Launch

Create an evidence project from an original file in the private game directory.
For the tested KQ1 edition, its raw `AGI` interpreter file can be retained with
`Project.create(project_path, game_dir / 'AGI', arch='x86', bits=16)` without
running native analysis. This file owns the evidence version; ScummVM executes
the game resources through its replacement interpreter.

```text
fdisbull debug PRIVATE.fdb --backend scummvm-agi --game-id kq1 \
  --executable /private/patched-scummvm --game-dir /private/kq1
```

The foreground server accepts `debug-engine-state`, `debug-step`,
`debug-write-engine-state`, `debug-breakpoint`, `debug-watchpoint`,
`debug-resource`, and the supported shared input, frame, trace, save and scene
operations. Use `debug-contexts` and `debug-status` to inspect the selected
backend. The Python entry point is `project.debugger(...,
backend='scummvm-agi', game_id='kq1')`.

Saved debugger scripts may declare `"backend":"scummvm-agi"`. This binds
validation and execution to the engine's run/step signatures. Engine operations
are `engine-state`, `engine-set`, `engine-resource`, `engine-patch-resource`,
`engine-cycle`, `step`, `watchpoint` and `delete-watchpoint`, alongside supported
shared operations. A script for another execution backend is refused before
its first operation.

Each run records the backend executable hash, capability handshake, original
project file hash and complete game-input manifest. Changed original project
versions cannot launch implicitly. New runs bind their own resource inventory.
Original game files, native saves, private databases and derived text stay
outside Git.

## Engine state and locations

The selected context is `agi-vm`. A script location has a logic number and an
offset in ScummVM's decoded LOGIC buffer. For the tested AGI v2 inputs that
includes the two-byte code-length prefix, unlike `agi-logic`'s code-relative
offsets. Other profiles retain a VM location without a verified v2 disk mapping.
`debug-code`, `debug-read-resource` and `debug-resource` retain the corresponding original volume
offsets and hashes. A VM location is not a DOS segment or CPU address.

`debug-patch-resource` edits a loaded logic only after checking every expected
byte. The original files remain the source backing. The active edit digest is
part of frame/scene identity; reverting the bytes restores the unpatched
identity. Native game saves refuse active loaded-resource edits because those
edits are not represented by ScummVM's save format.

Byte guards validate the loaded encoding, not the behavior of an edited
script. An adversarial title-logic control-flow edit in this experiment caused
the native engine to exit with SIGSEGV. The controller detected EOF and did
not replay the request; the original game files remained unchanged. A
structured `layer_conflict` stop is therefore not guaranteed for every unsafe
script transformation.

`debug-engine-state` returns variables, flags, inventory locations, screen
objects, current room, script location and virtual time. A checked state edit
uses `kind`, `index`, `value` and an optional `expected` precondition. The
operation records the observed before and after values.

`debug-run` accepts a finite `max_instructions`, `timeout_ms`, and optional
`guest_ms`. Virtual time is supplied by the patched headless backend; host
timeouts remain a different stop. ScummVM timing is not qualified as original
DOS timing. Script steps and execution breakpoints occur at explicit AGI
opcode boundaries. An instrumented accessor watch or a traced fetch is described at
its observed stage; neither silently proves a whole game rule.

The Python API supports a concurrent `pause()` during a bounded run and reports
whether the pause was acknowledged and the run was confirmed stopped.
`resume()` requires the same finite run budgets. Foreground server clients use
`debug-run-async` to start one finite owned operation, `debug-pause` to interrupt
it and `debug-run-result` with the returned operation ID to collect its result.
Other mutations refuse while that operation is outstanding. Ordinary
`debug-run` remains synchronous. Closing the foreground server closes and
reaps its engine and joins its owned operation threads.

## Frames and scenes

Frames come from the last display committed by the actual engine. The adapter
stores clean PNG artifacts and exposes sparse RGB probes. Offline overlays use
these stored artifacts after the process and project have closed.

Scene video identity includes the execution backend, complete input-manifest
digest and active resource-layer digest. A same-sized screenshot from DOSBox,
another resource set or another layer state cannot silently qualify a ScummVM
scene. Frame IDs include state revisions so an identical image after restore
does not authorize stale input.

Scene scalar comparisons can read engine values directly:

```json
{"compare":{"left":{"engine_state":{"path":["vars",0]}},"op":"eq","right":16}}
```

Paths select integer or boolean fields; booleans compare as 0/1. One stopped
observation shares one engine-state snapshot. Missing or nonscalar fields remain
unavailable. An action outcome may use
`{"before":{"engine_state":{"path":["vars",3]}}}` to refer to its retained
pre-action score. Existing pixel checks and named scene actions use the shared
scene framework.

## Saves and qualification

ScummVM native save slots are game saves at cycle boundaries. Their artifacts
are labeled `scummvm-agi-native-slot-v1` and `exact_vm_checkpoint: false`.
They are not DOSBox machine snapshots or arbitrary mid-opcode checkpoints.
Backend and resource identities must match before restore. Original-runtime
and ScummVM observations retain distinct provenance.

Both save and load require an empty input queue with no held keys or leases.
This prevents input queued before a restore from reaching the restored game.
An incomplete engine step or cycle wait stops a saved debugger script before
its next mutation. A known blocking popup prevents an action from completing
merely because its state predicate already changed; authored AGI outcomes
should also include the actual modal-open/modal-closed witness when required.

The same-source scene experiment is described in
[the comparison report](SCUMMVM_DOS_SCENE_COMPARISON.md). Its matched state
fields, attempted runs, timing boundaries and unresolved behavior determine
the claim ceiling. Successful parsing, execution, matching text or matching
room IDs cannot establish whole-engine equivalence.

## Verification and remaining scope

The figures and receipt immediately below describe the earlier AGI-only stage.
The later [combined-source verification](evidence/scummvm-gob-2026-11-01/verification.json)
pins the current packaged provider files, including the explicit hook capability
and stable control-ownership fixes. Its 100-test focused native gate repeats the
AGI KQ1/PQ1 cases alongside DOS and Gob. The separately pinned 2.8.1 AGI native
runtime remains unchanged.

The final focused gate passed 79 tests, including actual KQ1/PQ1 execution,
foreground asynchronous run/pause/result, project restart, real PNG export,
native save restoration in another process and checked resource edit isolation.
The wheel passed a separate real-engine step, stored PNG and project reopen.
The [verification receipt](evidence/scummvm-2026-11-01/verification.json) pins
provider, patch, binary and log identities.

The complete macOS suite reported 2,638 passed, 134 skipped, five failed and
23 errors. The five failures and 23 errors were reproduced using the unchanged
installed 0.29.0 baseline: Linux ELF/GCC fixtures, case-insensitive media and
LLDB wall-time gates. This is not a green release gate or hosted Linux CI.

This prototype enables AGI. Instrumented accessor watches omit direct raw field
accesses, modifier chords are refused, and native saves retain cycle-level game
state. Original DOS CPU registers, native code caves/hooks, the DOS baseline
layer-experiment workflow and exact mid-opcode machine snapshots retain their
separate backend contracts. The ScummVM bridge does not supply them. These
limits remain part of the capability and comparison claims.
