# Semantic contracts and projection comparisons

Use this reference when recovering an operation's meaning, linking a user interface to native or
interpreted effects, or comparing a recovered model or projection. Apply the parts relevant to the
requested claim; a static format question does not require a complete game reconstruction.

These are investigation records and comparison rules, not a new fDisBull command, schema, extension
identifier or runtime. Keep them in project notes or supported evidence fields. Check the installed
contract before adding fields to a scene, proof, shared-IL document or export.

## Contents

- [Recover an operation contract](#recover-an-operation-contract)
- [Link interfaces to effects](#link-interface-evidence-to-effects)
- [Preserve time and partial effects](#preserve-time-and-partial-effects)
- [Declare save and restore](#declare-what-save-and-restore-mean)
- [Separate observation from control](#separate-observation-from-control-policy)
- [Account for projection losses](#account-for-recovery-and-projection-losses)
- [Authored quantity-editor example](#authored-example-a-quantity-editor)

## Recover an operation contract

Start with the observable operation and its supported domain. Record its context, entities, state
ownership, typed inputs and units, guards, ordered effects, intermediate states, rejection/cancellation
behavior, time and randomness, external effects, completion boundaries and evidence. Mark missing facts
unknown and material alternatives explicitly; a friendly action name is not its meaning.

Recover one complete interaction at a time while preserving the working low-level representation
and its reference checks. Connect each proposed intent primitive to its original operations through
an explicit UDL mapping. Compare the higher-level candidate at the same inputs, guards, state,
output and time boundaries; add the relevant refusal, repeat and persistence cases. Retain opaque
low-level operations and dependencies wherever meaning remains unresolved. This procedure does
not expand the operations supported by an installed lifter or consumer.

Keep the chain from original bytes/resources through load or interpreter fetch, source operations,
candidate intent and observed outcomes inspectable. ASM, guest instructions and C-like views support
that chain; they do not replace it. Preserve observable wrap, rounding, dependencies and side effects
even when a higher-level name is convenient. Equal final values can hide different behavior.

Z is a behavioral view, not the Z-machine source VM. Current shared IL is a small primitive
representation; changing its UDL/UIL role metadata is not translation or evidence of full-world
recovery. Follow [udl-uil-udc.md](udl-uil-udc.md) for supported mappings and the original-backed DOS
path.

## Link interface evidence to effects

Maintain a compact ledger only for the surfaces and effects relevant to the task:

- Stable context, control and semantic action identities, with revision and source evidence. The same
  label or command code can mean different actions by context.
- Ordinary input binding and focus/modal/availability conditions. Keep existence, visibility or
  occlusion, readiness and enabled state separate, including unknowns.
- Model fields behind displayed values: draft, committed, cached or derived; units, rounding/formatting,
  refresh conditions and observation generation.
- Semantic event/effect identities and completion relationships. One action can cause several events;
  one event can have several interfaces. Autonomous events need no invented button, and nonvisual
  interfaces need no invented pixels.
- Qualified resource/geometry/transform dependencies and unresolved details.

Distinguish delivery, target consumption, draft acceptance, commitment, control update, displayed result
and persistence. Record observed order or unknown order; do not invent a total order from timestamps or
one global ready flag. A completed frame may still contain old application pixels. Background animation
need not block an otherwise qualified action. Use [methodology.md](methodology.md) and
[scenes.md](scenes.md) for the corresponding runtime evidence.

## Preserve time and partial effects

A signal assignment changes a value; a predicate wait observes it at a phase; an event records an
occurrence; a queue retains deliveries. Repeated writes need not enqueue repeated work. Recover
exact-value guards, phase/tie ordering, re-entry, cancellation and clock-input rules rather than
substituting a plausible queue or generic truthiness test.

Keep guest execution time, simulation ticks, turns, frames and host deadlines distinct. Record measured
progress, not just a requested budget. A text interface does not make a continuous game turn-based.
Rendering or media callbacks may advance logic, timers or RNG; hiding output or retaining valid media is
not evidence that altered presentation preserves those effects.

Track dispatch, native effects, presentation/follow-up and persistence separately. A confirmed commit
remains confirmed if later narration or redraw fails. Preserve partial effects and reconcile unknown
effects before retrying. An invocation ID is an audit identity, not proof of exactly-once execution. Do
not transfer the pure v1 evaluator's refusal/commit behavior or pending_host contract to an original
native invocation; each execution surface retains its own semantics.

## Declare what save and restore mean

Record which state belongs to the world, transaction, session, scene, process or external service, and
what survives each relevant boundary:

| Operation | Required distinction |
| --- | --- |
| Original game save/load | Fields written, restored, retained or reset; failure and subsequent scene reconstruction. |
| Native/evaluator checkpoint | Captured state, pending input/work, callbacks, clocks, RNG and explicitly excluded effects. |
| External persistence | Requested write, completion/error, durable observation and applicable restart/service boundary. |

A game load may retain session state that a checkpoint restores. Rebuilding a scene can run more logic
after load. Establish a durable game-save claim through the original writer and a fresh qualified loader
when required; file equality or an emulator restore alone does not establish that contract. Re-resolve
runtime bindings and readiness, and never assume host-file writes were rolled back.

## Separate observation from control policy

Declare the player-equivalent and investigator observation profiles separately from physical, assisted
or story control policy. Check information disclosure through descriptions, target IDs, action
discovery, guards, hints, errors and provenance links, not only raw state. Keep privileged evidence
available to the authorized investigator; do not silently give it to a player-facing projection.

Bind a command to an unambiguous current target, context and revision, then recheck before dispatch.
Narration follows the authoritative outcome and does not maintain a second game state. Passive
projection reads and the game's own look/inventory commands may consume different time or effects.
Declare timing for failed commands, clarification and reasoning intervals where it matters.

## Account for recovery and projection losses

For a bounded source/text → model → projection comparison, pin the exact source, model, adapter/runtime,
initial state, inputs, observation/control profiles and clock/RNG assumptions. Where evidence permits,
also compare model → text → recovered observable model. The second direction concerns the authorized
observable projection; it cannot reconstruct hidden state merely from prose.

Assess these axes independently. Record equal, different, unknown or explicitly outside scope; state the
finite reference set, denominator and evidence:

| Axis | Report and denominator |
| --- | --- |
| Observable facts | Retained, omitted and invented typed facts; counts against the reference facts and emitted facts. |
| Knowledge state | Changed present/absent/occluded/unknown/inferred classifications, unjustified promotions and leaks; identify tested propositions and hidden-information cases. |
| Affordances | Missing/invented actions, target bindings, aliases and lost ambiguity; counts against reference and exposed affordances. |
| Transitions | State deltas, intermediate effects, failures and event-order differences at explicitly aligned action/trace boundaries; report boundaries compared. |
| Time and RNG | Delays, ticks and random consumption/order under the declared profile; report intervals, draws or other observations actually compared. |
| Narrative payload | Required messages, clues and labels retained against their declared inventory; check the verbatim subset exactly and separate optional paraphrasing. |
| Unresolved meaning | Ambiguity, unsupported constructs and conflicts retained or guessed away against the identified unresolved inventory. |

For fact/affordance precision use correct emitted items / all emitted items; for recall use retained
reference items / all reference items. Report zero or unavailable denominators explicitly rather than
manufacturing a perfect score. Missing oracle coverage is unknown, not zero loss. Keep leak counts and
timing or trace differences separate; one aggregate prose-similarity score hides them.

## Authored example: a quantity editor

The following is an illustrative contract, not a game fact or executable schema.

| Contract part | Authored example |
| --- | --- |
| Identity/domain | quantity.commit in summary; pending and committed are unsigned integers in 0..9. |
| Input/context | summary.ok requires current focus, no blocking modal and an enabled control. detail.ok only accepts the draft and is a different action. |
| State/event | With pending=2 and committed=0, commitment sets committed=2 and emits quantity.committed; do not infer idempotency from the name. |
| Projection | total displays 10 × pending whole credits, so 20 can be visible before commitment. Refresh completion is a separate observation. |
| Persistence | This fixture's game save stores committed only; checkpoint coverage is declared separately. Do not generalize either behavior to a target. |
| Discriminators | Compare detail acceptance, summary commitment and an unchanged-state control; investigate repeated confirmation, cancellation and invalid input within scope. |
| Claim | Trace the declared effect and later display/save boundaries independently. A failed follow-up must not trigger a second confirmation automatically. |
