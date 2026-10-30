# Scene-family recognition is not content readiness

Evidence note, 27 October 2026. Requested by TiGa after the E43 original-DOS
investigation. This document supplements the pre/post screenshot discussion in
PR #5 and the interface-description RFC in PR #7. It does not change production
APIs, input timings, UIL semantics or the other agent's implementation.

## Observed friction

The E43 research packet records two different scene-authoring failures:

1. Sparse samples included an animated title decoration. A later genuine frame
   matched only six of eight samples, below the configured seven-sample limit.
   The scene framework correctly refused that observation.
2. Moving generic recognition to a stable footer avoided that false negative,
   but the footer remained unchanged while content pages switched. A selected-item
   field changed before the new interface was adequately qualified. The Next
   outcome was accepted, then the following Previous request failed to produce
   its expected result and exhausted its bounded wait.

The accepted definition paired the selected-item identity with a fingerprint of
its displayed title. It passed the complete fresh route and the later measured
return-boundary run. Its supported pages remained explicitly restricted.

This is an authored-predicate correction. The exact low-level cause of the missed
Previous input was not isolated. It is not evidence of a mouse backend defect,
a universal title-is-ready flag or a need for blanket longer input durations.
The failed receipt remains a failure; no automatic action retry was introduced.

Source: private authored reports `DinoPark-E43-Report.md`, sections 5 and 6, and
`fDisBull-E43-Friction.md`. Observed runtime: Python source 416b64d / 0.18.0 with
the qualified scene-capable DOSBox ELF c04b1c189530af93cf054505ee92f2336c83b86e819bae8d8370350d23259fc6.
The reports and actual screenshots remain separate research evidence; no game
assets, native states, private database or reconstructed game source are added.

## Separate the evidence questions

| Question | Suitable evidence | Not sufficient by itself |
| --- | --- | --- |
| Which screen family is visible? | Stable chrome, layout, context and dimensions | The currently selected item |
| Which content variant is displayed? | Variant-specific title, icon or other calibrated content | A shared footer or unchanged navigation controls |
| Which content is requested internally? | Independently identified selection/request state | A claim that the requested content has rendered |
| Can this action be invoked now? | Separate readiness, enabled state, focus and modal conditions | A new frame, changed selector or visible button |
| Did the action complete? | Its declared state/interface/persistence boundary | Input acceptance or a condition already true before input |

Where the application legitimately separates requested, rendered and active
content, retain all three meanings. Do not force them to be equal until the
specific action's completion contract requires it.

## Authoring pattern

Use a stable predicate for the screen family and a discriminating predicate for
the content variant. Keep readiness and enabled state separately justified.
Conceptual pseudocode, not an added API:

```
family_matches = stable_chrome && expected_context
content_matches = selected_variant == expected_variant
                  && displayed_variant == expected_variant
may_act = family_matches && content_matches
          && readiness_matches && enabled && focus_matches && !known_blocker
```

When no reliable displayed-variant observation exists, report that boundary as
unknown or incomplete. A backend-only check can still establish a backend state
transition; it cannot silently certify the corresponding rendered interface.
Rendered identity is one useful qualification, not a universal input-readiness
proof. Titles can finish before controls in another program.

Choose recognition points from actual clean observations. Avoid cursors, blinking
labels, moving actors and changing counters unless that variation is explicitly
part of the recognizer. Calibrate on more than one animation phase and include
near-miss negative examples. Do not fix a false negative merely by lowering the
match threshold until unrelated pages also pass. Do not require whole-frame
stability in a continuously animated interface.

## Pre/post screenshots and object presence

A passive post-state screenshot may correctly contain the old content. Retain its
capture phase and observation/frame identity. A post-interface hook must either
observe its declared content/readiness conditions or return an incomplete result;
it must not relabel the old frame as the completed new page.

Waiting for presentation is explicit guest execution with a shared bounded
budget. Preserve breakpoint, watchpoint, hook and guest-error stops. If a wait
expires, inspect effects before retrying state-changing input. A timeout is not
proof that the earlier input had no effect.

The same rule applies to pixel-based object detection: distinguish object
identity, visual presence, occlusion/unknown, action availability and state.
A stable navigation object may remain visible while the content it operates on
changes. An unknown variant is not proof that the object's content is absent.

## Proposed conformance scenarios

These are implementation-owner acceptance specifications, not tests executed by
this documentation change. Use redistributable synthetic graphics/guest code.

1. **Animated decoration:** two legitimate animation phases retain family identity
   while a negative page with similar chrome does not acquire the content identity.
2. **Selector-first transition:** at A, request B. Let the selector become B while
   A's content and shared footer remain visible. Record post-state, but do not
   authorize a B-specific action or claim post-interface completion yet.
3. **Content before controls:** render B while its control remains disabled or not
   ready. Recognize B's content, still refuse the dependent action.
4. **Coherent completion:** B's content and authored readiness/enabled conditions
   become true. Accept once, retaining the pre/post observation identities.
5. **Wrong content:** selector B with displayed C stays a mismatch; missing/occluded
   evidence stays unknown. Neither is converted into absent or success.
6. **Interrupted transition:** a debugger stop, missing frame or exhausted budget
   returns the corresponding incomplete/stopped result without resending input.
7. **Restore and revision:** re-evaluate after restore or a new scene revision;
   historical matches are not reused as current availability.

## Scope

No new runtime feature is required to express the narrower E43 matcher with the
existing scene framework. This note gives future object detection and screenshot
hooks a reusable distinction to preserve. Production changes and tests, if any,
remain separate from this evidence-only PR and with their existing owners.
