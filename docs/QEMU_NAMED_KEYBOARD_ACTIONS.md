# Named QEMU keyboard actions

`scene_act` performs one named physical keyboard press after a fresh stopped RAM
readiness check, then observes its declared RAM postcondition. The explicit
`fdisbull-scene-3` profile is separate from passive scene-2 and frame-backed
scene-1. Saving a definition or reading a historical result does not authorize
input on a live machine.

## Define and call an action

The caller first binds actual live RAM with `bind_runtime_memory`, including an
expected-byte witness and provenance. Binding names in a stored definition are
references; they do not create or restore those live bindings.

This illustrative declaration expects a caller-provided `controls` binding. Its
two byte predicates are application-specific contracts, not discovered game
semantics:

```python
definition = {
    "format": "fdisbull-scene-3",
    "observation_profile": {"kind": "runtime-memory", "version": 1},
    "action_profile": {"kind": "qemu-virtual-keyboard", "version": 1},
    "context": {"state": "authored control state", "triggers": ["guest input"]},
    "match": {"constant": True},
    "objects": [{
        "name": "advance",
        "context": {"state": "one declared control", "triggers": ["key a"]},
        "visible": {"constant": True},
        "ready": {"runtime_memory": {
            "binding": "controls", "offset": 4, "length": 1, "hex": "01"
        }},
        "enabled": {"constant": True},
        "action": {
            "kind": "press", "key": "a", "modifiers": [],
            "hold_ms": 80, "gap_ms": 80
        },
        "outcome": {"runtime_memory": {
            "binding": "controls", "offset": 5, "length": 1, "hex": "01"
        }},
        "outcome_phase": "state",
        "guest_ms": 500,
        "timeout_ms": 5000
    }]
}
saved = project.debug_save_scene("controls", definition)
result = debug.scene_act(saved["id"], "advance", slice_ms=25)
```

The public signature preserves the existing scene action options and adds an
optional guest allowance:

```python
scene_act(scene, object, *, handle_popups=False, timeout_ms=None,
          slice_ms=100, compact=False, guest_ms=None)
```

JSON uses `debug-scene-act`; saved scripts use `scene-act`. A saved-script ID
selects immutable script content. The script preflight validates every known
literal and selected action definition before earlier script effects. A result
reference defers only its unknown value, which is validated again before the
script timeout clamp and actual action admission.

Only `handle_popups=False` is admitted. The profile contains no popup handler,
mouse action, text typing, macro, frame geometry or navigation authority. A
single action has one literal physical key and optional modifiers. The existing
native keyboard press validator supplies the physical key vocabulary and strict
integer `hold_ms`/`gap_ms` limits of 1..1000. For one chord, `gap_ms` is retained
metadata; it does not add a tail timer.

Stored object allowances default to 5000 ms: `guest_ms` is in 1..120000 and
`timeout_ms` in 1..60000. Explicit caller allowances can tighten these limits.
`slice_ms` is an integer in 1..1000; Boolean values are not integers for admission.
The fixed press span plus one polling tail must fit strictly inside the total
guest allowance before any input is armed.

`outcome_phase` is retained metadata (`state`, `interface`, `persistence` or
`unspecified`), defaulting to `state`. Its name does not supply additional proof:
the action establishes only the declared RAM postcondition it actually observes.

The scene has the same bounded RAM predicate grammar as scene-2. Every predicate
branch and action declaration is validated before storage. Definitions bind the
original source hash, selected byte version/hash and persistent object identities.
Revision chains cannot switch observation or action profiles. Existing scene-2
definitions continue to reject action fields. `scene_check` and `scene_assert`
may passively inspect scene-3; they neither arm nor execute it. `scene_wait`
retains its separate scene-2 contract.

## Fresh admission and one attempt

The operation requires one stopped, active owned DOS process, the explicit QEMU
virtual clock and the native keyboard extension. The physical input queue and
held-lease ledger must be empty and valid. Existing bound, partial or uncertain
input schedules and frame-key owners refuse admission. The action does not take
over or repair another input plan.

An internal invocation identity is consumed before the fresh readiness read.
The exact scene revision, manifest hash, object and action declaration remain
pinned. One stable ownership fence covers the original VM/process/project,
source and version, runtime/restore epoch, readiness read, native arm, execution
and result publication. A replacement machine sharing the original lock is still
a different owner. Timeline and selected-undo restrictions continue to apply.

Readiness requires a matched scene and content, visible/ready/enabled object,
unambiguous observations, and an initial outcome that is exactly false. A true
initial outcome refuses without input; it does not count as a successful action.
Unknown readiness or outcome also refuses. The final ownership and declaration
checks occur before the sole press arm while the guest remains stopped.

After acceptance, the first virtual interval accommodates the fixed input plan
and one polling tail. Later ordinary stopped boundaries evaluate only the
declared destination predicate. The old scene or readiness may legitimately
become false after input. Its disappearance alone does not invalidate a measured
destination effect.

## Read the evidence by phase

The canonical result uses `fdisbull-scene-action-1` and is stored in
`debug_scene_observations`. Its `observation` ID retrieves the complete result.

| Member | Meaning |
| --- | --- |
| `plan` | Immutable scene, object and action identities, fixed press and effective budgets. |
| `intention` | One consumed invocation identity; historical evidence with `replay: false`. |
| `before` | The fresh stopped readiness observation that preceded input. |
| `input.attempted` | An arm call may have been submitted. This is not proof of acceptance. |
| `input.accepted` | A validated native receipt accepted this owned finite press. |
| `input.completed` | The whole declared native callback prefix was delivered. |
| `effect` | The independently observed declared RAM postcondition, or an explicit unknown. |
| `action_wait` | Original polls/runs, first stop, measured clock progress, budgets and evidence size. |

Input acceptance and completed native callbacks do not establish device FIFO
acceptance, guest consumption or application completion. The low-level
`device_queue_accepted` and `guest_consumed` fields remain unknown. A fixture may
provide separate RAM evidence of consumed bytes, but this does not rewrite the
lower-level receipt. A matched postcondition records an observed result; causal
attribution remains a separate claim.

Success requires accepted input, complete callback delivery and a fresh true
postcondition within the declared bounds, with no earlier nonordinary stop.
An incomplete action raises `SceneError` with its result. Transport and callback
failures preserve their primary exception/native evidence alongside a separate
`scene_act_result` prefix. JSON and scripts preserve those distinctions.

## Stops, deadlines and recovery

The first breakpoint, watchpoint, hook, guest exit/TSR, host stop or interrupted
input takes precedence over an effect poll. No hidden continuation, rearm,
cancel or release follows it. A known partial press retains its actual held
leases and unsent suffix for explicit caller recovery. The effect stays unknown
if the action never observed it after delivery. A later caller inspection is
separate evidence and does not retroactively change that result.

A possibly submitted arm with an unknown outcome cannot be replayed. An
uncertain transport, observation or publication failure after input was touched
quarantines/closes the captured owner while preserving the original error and
cleanup diagnostics. Closing does not synthesize a guest key release. A new
session needs new live admission; a stored intention or result is not a token
that can be reused for execution.

One absolute host deadline intersects the declared/caller, session, VM and
control-channel bounds. Lock admission, RAM reads, arming, all native intervals
and persistence share that end. Each incoming limit is restored independently
afterward. The guest allowance is cumulative measured `QEMU_CLOCK_VIRTUAL`
progress, not host elapsed time or a sum of requested slices. Overshoot remains
visible and cannot turn a late match into success.

The operation preserves the existing per-observation predicate/capture limits
and bounds its complete canonical journal to 8 MiB and at most 1000 polls.
Retrieve or export a bounded-output artifact to inspect a large receipt; do not
rerun the action to recover its response. A committed receipt that becomes late
at a later publication boundary remains retained evidence, not a rolled-back
input or a successful timely response.

## Verification scope

The [native acceptance gate](QEMU_SCENE_ACT_GATE.md) passed both cases on
2026-11-20 at `3cb9628178577689c22b8a8e12b21fd2d8dc9fa2`, using two fresh authored
DOS owners: a successful single press with independent key-byte and position
evidence, and false-readiness refusal followed by an exact partial-input stop.
Its dated receipt records exact inputs, cleanup, the earlier failed controller
attempt and the limited acceptance scope. The final affected host selection
passed 1,090 cases, including 62 focused action cases, with ten explicit optional
native skips. Host checks cover malformed declarations, changed owners/epochs,
input ownership, deadlines and public error/persistence behavior.

This is a keyboard/RAM action profile. Frame-based actions, absolute clicks,
typing, popup handling, navigation, general game readiness and combined restore
campaigns require their own acceptance evidence. The
[DotBox transfer review](QEMU_DOTBOX_TRANSFER_REVIEW_20261120.md) explains the
immutable-plan, consumed-intention and separate-effect design input. DotBox's
tests do not qualify QEMU. This slice does not promote the default backend or
authorize retiring DOSBox.
