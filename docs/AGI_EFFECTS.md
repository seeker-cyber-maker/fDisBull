# AGI object and resource effect contract

The explicit `agi-2.917` effect profile turns the declared KQ1 logic-103 actions
into typed `effect` ports in compact `fdisbull-il-2`. It models one bounded
invocation against caller-supplied state. It does not run the original game,
advance an independent scheduler, paint a native screen, or generate UDC code.
The module descriptor is revision 4; instruction encoding facts remain revision
3. The default tree/scalar behavior remains available.

```text
fdisbull module-lift fdisbull.agi.2.917.subset /private/game/LOGDIR \
  --volume-dir /private/game --logic 103 --profile 2.917 \
  --control-flow compact --effect-profile agi-2.917 \
  --state-file /private/scalar-snapshot.json
```

The Python/JSON option is `effect_profile="agi-2.917"`. All reachable scalar
read/write values still need explicit typed bindings, including flag 15 and
variable 21 for print behavior. Callee entries and component boundaries retain
their existing meaning. Other unknown predicates/actions, dynamic calls,
recursion and cycles still refuse unless an explicitly permitted action is
retained as opaque. An opaque graph always refuses execution.

## Ports and source semantics

The built-in contract identity is `fdisbull.agi.object-resource.2.917.v1`.
A node records its source binding hash and a named action with typed argument
and output sockets. Object, view and message identifiers are literal bytes in
this bounded profile. Coordinates and step values can refer to scalar inputs.
Ports are top-level continuation operations; conditions transfer between named
continuations. An input cannot import a handler or executable plugin.

| Source actions | Modeled operation |
| --- | --- |
| load.view | Require captured geometry; mark the view loaded, idempotently |
| animate.obj | Preserve an already animated object; otherwise reset flags/motion/cycle/direction according to the profile |
| set.view | Require a loaded view; retain valid loop/cel or select zero, bind dimensions and apply screen/horizon clipping |
| position / position.v | Write current and previous positions; no guessed collision correction |
| get.posn | Return byte x then y; an aliased destination ends with y |
| distance | Drawn objects use horizontal cel centers and Manhattan distance, capped at 254; unavailable objects yield 255 |
| horizon/land/block/cycling controls | Update the corresponding object flags |
| stop/start/normal motion | Configure motion; ego stop/start also updates direction output/player control |
| step.size / follow.ego / wander | Configure the controller; follow resets its completion flag and records its binding |
| draw / erase | Suspend for explicit host work when the drawable state changes |
| print | Resolve a hash-bound message and suspend for shown/dismissed completion according to output mode and timer |

These are 22 source action encodings and 21 port names: position and position.v
share the same typed position operation. Motion configuration does not imply
arrival, a completed animation or a guest tick. Active overlapping motion/end
cycler state is refused because original union behavior and compatibility
workarounds require further qualification. Unloaded set.view is refused rather
than using an emulator's autoload workaround. Unsupported signed-center
narrowing is refused. Draw requires a loaded, bound cel geometry.

Nominal semantics were checked against pinned ScummVM
[command handlers](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_cmd.cpp),
[view binding/clipping](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/view.cpp),
[motion activation](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/motion.cpp)
and [message behavior](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/text.cpp).
Those implementations include compatibility workarounds. Source agreement is
not proof of exact original-interpreter behavior.
Native KQ1 testing subsequently qualified one correction: `set.view` only
checks the horizon inside its top-edge repair branch. An already valid top
edge does not cause an independent horizon clamp. The explicit
[DOS host adapter](AGI_DOS_HOST.md) now supplies original-handler observations
for selected invocations; it is separate from this nominal evaluator.

## Explicit private context

`agi_resources.capture_view(VIEWDIR, volume_dir, view, profile="2.917")` captures
bounded uncompressed DOS v2 resource structure and returns provenance plus
`metadata` containing its payload hash and loop/cel geometry. It checks header,
offset, dimension and RLE bounds. It is not a renderer. Empty/unsupported views,
compressed/v3/platform-specific encodings and oversized inputs are outside the
profile. `logic_messages(resource)` decodes the captured logic's message table,
returning texts keyed by the complete logic-resource hash. Texts remain private
input data, not instructions.

A context has these fields:

```python
from fdisbull.agi_effects import CONTRACT, object_state
from fdisbull.agi_resources import capture_view, logic_messages

# logic_resource is an immutable captured AGILogicResource.
view = capture_view(viewdir, volume_dir, 14, profile="2.917")
context = {
    "contract": CONTRACT, "horizon": 36, "player_control": True,
    "objects": {"0": captured_ego, "13": captured_actor},
    "views": {"14": view["metadata"]},
    "loaded_views": captured_loaded_views,
    "messages": logic_messages(logic_resource),
}
```

Object snapshots are complete typed records. `object_state(**overrides)` is a
factory for explicitly declared nominal fixtures; it is not a runtime reader.
Missing object snapshots, resources or message bindings refuse before model
execution, including references in inactive branches. The context is finite
JSON limited to 1 MiB and copied before evaluation. Original files are not
modified. Initial state, resource capture and live runtime correspondence are
separate evidence gates.

## Host suspension, save and resume

```python
from fdisbull.interaction_il import execute_il

pending = execute_il(projection["uil"], effect_context=context)
# Save pending["checkpoint"] privately if status is pending_host.
# Obtain a real host result, or explicitly label an authored test fixture.
result = execute_il(
    projection["uil"], checkpoint=pending["checkpoint"],
    host_result={
        "request_id": pending["host_request"]["request_id"],
        "status": "completed",
        "result": host_operation_result,
    },
)
```

A draw result contains x/y after the host's position/collision work; the model
checks geometric bounds and horizon but cannot certify collision safety. An
erase result is an empty object. A blocking print requires `dismissed: true`;
a nonblocking print requires `shown: true`. Blocking completion resets variable
21, and output mode is cleared. No later instruction runs while that request
is pending. Native dialogue timing and changes to other engine state are not
inferred. Independent ticks and time-variable changes are outside this frozen
invocation model and need separate host qualification.

Readback with the checkpoint alone returns the same request without replaying
its operation. The checkpoint binds the document, context, scalar state,
continuation, stack, pending operation and cumulative budgets. A changed program,
wrong request, invalid response or exhausted budget refuses. The JSON checkpoint
is limited to 4 MiB. Its unkeyed checksums detect ordinary corruption, not an
adversarial caller; neither checksums nor supplied acknowledgements authenticate
native execution. Real adapters need their own authoritative action/completion
records. This evaluator sends no native or GUI command.

During suspension, committed `state`/`effect_context` remain the model baseline;
proposed fields show progress. A host completion claim can outlive a later
failed model transaction. Such failures preserve `host_completions` and report
`recovery_required` with last modeled values. Reconcile the actual host before
retrying; uncommitted model state does not mean an external action rolled back.
A final `complete` result is still `native_execution: false`.

`il-run` accepts private `--effect-context`, `--checkpoint`, and `--host-result`
files. It can resume in a fresh Python process without a live emulator or site
packages. Pending/refused results return exit code 1; inspect structured status
and retrieve artifact-backed output before repeating an action. Keep contexts,
source-retaining projections, message texts and checkpoints outside Git and
select a private output-artifact directory.

See [verification](VERIFICATION-AGI-EFFECTS-2026-10-31.md) for authored controls
and the KQ1 corpus scope. Renderer/collision execution, independent movement
cycles, time progression, complete game recovery and UDC emission remain
separate work.
