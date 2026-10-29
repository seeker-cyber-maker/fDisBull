# Assisted travel: bounded contract and verification

Plans may pin a `destination_scene` revision as a required displayed-state
postcondition. A matching memory predicate alone then cannot finish the route:
the destination must also return a complete scene match within the same budget.
An incomplete capture preserves a partial result; it is never promoted to success.

A typed write can use `set_bits` instead of `value`. It ORs the declared mask
into the freshly verified field while preserving other bits. The AGI example
uses a runtime-verified position routine's refresh bit so position edits are
adopted by rendering, rather than merely changing the observed coordinates.

For latched controls, optional `cleanup` contains an observed `when` predicate
and bounded keyboard `inputs`. It fires once, after queued input has drained,
and the guest executes another slice before final success is considered. This
lets a room-entry route stop a surviving direction latch without guessing from
a transient actor-direction zero. Initial and cleanup inputs retain separate
attempt/acknowledgment records. Both are validated before the first memory edit.

Assisted travel is an explicitly authored, debugger-assisted operation. It modifies declared runtime actor fields, runs guest code, and observes an authored stop condition. It does not infer actor identity, discover a route, reconstruct a game, or establish that an arbitrary destination is safe. A workflow should bind the plan to an edition, resource inventory, scene revision, evidence and dependencies before dispatch. The caller must provide accurate provenance and supervise live input through one controller.

`session.assisted_travel(plan, timeout_ms=...)` accepts `fdisbull-assisted-travel-1`. A plan declares `kind` (`within-room` or `room-jump`), exact `scene_revision`, named typed `observations`, a start `context` predicate, actor `writes` through session-bound runtime bindings, bounded keyboard `inputs`, an `until` predicate, and a `destination` containing a label, observed `room_field`, and expected integer `room_value`. The `provenance`, `guest_ms` and `slice_ms` fields declare evidence and execution limits. Every binding needs an independently established address, range and identity witness; it is invalidated with its session/epoch. A room jump requires keyboard input intended to invoke the guest's original transition logic. The observed result should be treated as a bounded report, not proof of global game equivalence.

A fresh complete scene check, drained keyboard and complete matching start observations precede the writes. Declared ranges are preflighted and must not overlap each other, the identity witness, or the memory range designated as the room observation. The caller must identify the actual room field correctly. Each write has an expected-byte check and readback. Write records distinguish an unknown RPC outcome from an acknowledged write and include a verified flag for readback. At least one bounded guest slice follows; success requires the specified observation, destination room and drained keyboard. A breakpoint, hook or other non-guest-time stop is preserved as a stop rather than reported as arrival. A failed operation can have already changed memory or sent input; it does not imply rollback. Save checkpoints and reconcile guest state as appropriate for the experiment.

## Verification status

The authored synthetic MZ fixture in `tests/test_assisted_travel.py` uses a visible guest screen and a keyboard loop. Its guest code changes room 1 to room 2 only after receiving `x` while the actor position is 5. With the macOS ARM64 DOSBox backend, the test observed a same-room position edit, the guest-input room transition, and a preserved breakpoint stop. This is a bounded synthetic result, not evidence for a Sierra title or another game.

Regression checks also verify that a direct write overlapping the declared room observation is rejected before input, and that a successful write followed by a readback failure remains recorded as an unverified attempt. This protects the declared room range; it cannot establish that the caller chose the correct field or that another modified field is harmless. A missing terminal/readback result must be treated as unknown, not as evidence that no mutation occurred.
