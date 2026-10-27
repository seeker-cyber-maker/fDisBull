# UI completion and pre/post screenshot-hook boundaries

Status: proposed contract and investigation feedback, not a production fix.
Author: ChatGPT, DinoPark investigator, at TiGa's request. Date: 2026-10-27.
The user reports that the fDisBull agent already knows of a related issue. This
note is a separate, narrowly scoped companion for that agent, not a replacement
implementation. Keyboard delivery/polling feedback remains separate in PR #4.

## Observed motivation

The E41 original-DOS employment investigation observed a pending staff count
change before the roster redraw and FIRE-control enable update completed. An
early 400-guest-ms observation still displayed zero workers and a disabled FIRE
button; continued execution produced the one-worker display and enabled button.
The accepted route checked both the pending-count relation and control-enable
state, and rechecked readiness before the next input.

This is evidence of distinct application boundaries, not proof of a debugger
failure or a universal 400-ms delay. It was observed using Python source
416b64d / 0.18.0 and the genuine scene/keyboard Linux DOSBox backend. The E41
research receipt retains its scope; no new native run is claimed by this note.
No proprietary executable, resource, memory dump or native checkpoint is added.

## The same issue affects screenshot pre/post hooks

A successful input enqueue, a changed state field, an enabled control and a
frame showing that change are four different observations. A screenshot taken
in a hook immediately after a state-writing instruction can legitimately show
the previous application display, even if it is a completed video frame.
Neither a new frame ID nor a drained input queue establishes UI completion.

Use explicit capture meanings rather than one overloaded `after`:

| Boundary | Meaning | Does not establish |
| --- | --- | --- |
| Pre-input | Current scene/focus and baseline captured immediately before sending input | That the future action will be accepted |
| Post-dispatch | Requested input was sent or queued | Consumption, state change or redraw |
| Post-state | The declared state transition was observed | Control registration, enable update or rendered result |
| Post-interface | Declared readiness and visible-result conditions were observed on a current frame | Persistence or unrelated controls being ready |
| Post-persistence | Required durable output was written and independently reloaded where the claim requires it | Pixel-equivalent rendering |

These are proposed conceptual phases, not new public API names. Existing
breakpoints, watches, bounded waits and screenshots can produce them explicitly.
A route should request only the phases needed to substantiate its claim.

## Required properties for any eventual hook integration

1. Bind a pre-capture to the actual action, scene/object revision and observed
   context. If preparation resumes execution, rematches a scene or dismisses a
   popup, distinguish that earlier image from the final pre-input baseline.
2. Keep immediate post-state evidence even when the interface is not ready.
   Label it intermediate; do not replace it with a later image under the same
   identity. UI disagreement is evidence, not a reason to rewrite memory.
3. A passive screenshot hook must not secretly advance the guest. An explicit
   interface-settle policy may wait within shared guest/wall budgets, but must
   record that execution as part of the action and preserve all debugger stops.
4. Capture the frame identity, mode/state generation, action identifier and
   observed predicate values. Memory and pixels from different execution
   moments must not be presented as an atomic snapshot. Record their order and
   mark cross-phase captures when a coherent observation is unavailable.
5. Detect the declared application outcome, not universal visual stillness.
   Animated backgrounds and blinking cursors can continue after a control is
   ready. Conversely, a visually unchanged screen can conceal a new modal,
   disabled control or pending operation.
6. Failure to obtain a suitable post-interface frame means `capture incomplete`
   or `readiness unknown`, not necessarily `action failed`. Preserve the state
   result and last valid frame. Check effects before retrying a non-idempotent
   action. A timeout must not cause an automatic second purchase or submission.
7. Before the next action, re-evaluate visibility, focus/modal constraints,
   readiness and enabled state. Prior successful completion is not a reusable
   permission token after execution, restore or context change.
8. Preserve clean pixels separately from annotations. A reference screenshot
   is historical evidence; an overlay must not become its own recognition input.

The practical invariant is: an event receipt describes what happened, while the
capture receipt describes what could actually be observed at its declared phase.

## Synthetic acceptance cases for the implementation owner

These vectors are specifications, not executed new runtime tests:

- At logical step 0 a pending quantity is zero, FIRE is disabled and the frame
  shows zero. Input changes quantity at step 1; control enable updates at step 2;
  the new number appears in a completed frame at step 3. A post-state capture
  at step 1 is retained but cannot qualify as post-interface completion.
- The state is committed, then a diagnostic capture times out. Return the known
  state result plus incomplete capture; do not send the action again.
- A breakpoint or watchpoint interrupts the optional settle wait. Return the
  stop unchanged. Hook machinery must not resume through it to obtain a frame.
- A known popup is dismissed before the intended action. The pre-input capture
  must be from after that dismissal, or explicitly marked as a different phase.
- A completed frame still shows old application pixels. A new frame counter
  alone must not satisfy a predicate about the new displayed quantity.
- Background animation never stops, but the target's declared control and
  display predicates are satisfied. No global-stillness requirement is imposed.
- Restoring invalidates current framebuffer availability. Imported historical
  reference pixels cannot stand in for a fresh post-restore observation.

## Scope and coordination

This note proposes capture/observation semantics and reports a calibration
finding. It does not add hooks, change input defaults, patch the game's state,
or implement a UIL runtime. The fDisBull agent retains implementation ownership
and can map these phases to its existing pre/post hooks. The separate UIL
interface-description amendment addresses the exported semantic relationship,
not debugger callback implementation.
