# Decide what to analyze

Use this guide when a game or program is unfamiliar, a reconstruction request
is broad, or there are several plausible next investigations. It helps choose
**what question to answer**, not just which tool to run. It does not authorize
new inputs, game downloads, external writes, or execution outside the user's
scope. Respect requested blind, spoiler and assistance policies. A narrow task
may start in the middle of this guide; do not make unrelated recovery a gate.

## Contents

- [Start with an outcome and a finite evidence ledger](#start-with-an-outcome-and-a-finite-evidence-ledger)
- [Map dependencies before choosing work](#map-dependencies-before-choosing-work)
- [Move from scene facts to interactions](#move-from-scene-facts-to-interactions)
- [Rank candidate questions and choose a probe](#rank-candidate-questions-and-choose-a-probe)
- [Respond to a capability mismatch](#respond-to-a-capability-mismatch)
- [Transfer an investigation to another target](#transfer-an-investigation-to-another-target)
- [Branch, stop and refuse explicitly](#branch-stop-and-refuse-explicitly)
- [Worked decision examples](#worked-decision-examples)
- [Choose the next reference](#choose-the-next-reference)

## Start with an outcome and a finite evidence ledger

1. **Intake and identity.** Record the requested outcome, allowed target and
   edition, input identities and hashes, current project/version, backend and
   observation/control policies. Check which inputs and capabilities actually
   exist. A hash identifies bytes, not authenticity, rights or behavior. Do not
   mistake a saved run record for a live emulator connection.
2. **Topology and state inventory.** From existing evidence and a bounded
   observation, list the relevant contexts/scenes, transitions, actors, placed
   items, player state, clocks/RNG, resources and persistence boundaries. For a
   program, substitute its processes, views, data and events. Retain source
   address, runtime address and display coordinate identities separately.
   Distinguish observed, source-derived, inferred, contradictory and unknown.
   An inventory is a prioritized frontier, not a claim of whole-world coverage.
3. **Choose one observable claim.** Write its context, desired outcome,
   dependencies, current support, unresolved alternatives, next discriminating
   probe, budget and stop condition. Existing evidence may already answer the
   question. If the useful next observation is missing, preserve unknown rather
   than converting absence of evidence into an empty scene, empty inventory,
   safe route, non-hostile NPC or failed effect.

Keep the ledger compact. For each claim record: evidence ID and source/version;
state before and after; input and observation policy; known and unknown fields;
result; and the next branch. A source table, visible sprite, authored label,
model value, original execution and target execution are distinct evidence.
Avoid logging private bytes into public artifacts.

## Map dependencies before choosing work

Draw a small graph for the requested outcome. Nodes are **claims or observable
capabilities**, not implementation milestones. Arrows mean that a claim needs
another claim or a declared independent witness. Include alternative paths and
unknown edges. For example:

```text
source identity + backend readiness
  -> scene/record identity -> coordinate and clock units -> actor observation
  -> input consumption -> actor motion -> contact/eligibility -> interaction
                                  |                            |
                                  +-> placed-item observation  +-> state/effect/readback
                                                               -> model/target comparison
  -> observation policy + current model -> Z/text description and action binding
```

This is a menu of dependencies, not a universal game architecture. A puzzle
may need turn rules before movement; a text adventure may have no pixels; a
specific bug may only need one writer trace. Multiple edges can be examined in
parallel only when their witnesses and mutable state are independent. One
controller owns each live guest; retain the exact input and observation order.

The user's requested result controls the stopping point. A graph node with a
useful local result can be qualified even if unrelated nodes remain unknown.
Conversely, reaching an intermediate node does not discharge downstream claims.
Choose a small complete path through the graph: for a playable combat request,
one qualified damage function is a component, while target selection, firing,
impact, recovery and another usable turn make the first useful vertical slice.
Keep following the missing critical edge instead of collecting more easy leaf
checks after the requested path is already blocked somewhere else.

Declare the observable contract before trying to reproduce every hidden field.
If an unknown scratch or display field lies outside the bounded read-set of the
requested motion or combat path, preserve it as unknown while verifying that
projection. Establish that independence from source/dataflow and execution
evidence; do not merely assume it. An unrelated unknown must not automatically
invalidate a recovered position, and a required unknown must not become zero.
For an item, track existence, identity, position, visibility, availability,
interaction, effect and persistence separately. For an actor, track stable
identity, position/velocity, state, animation, collision, target selection,
behavior and damage separately. Geometry, camera coverage and line of sight are
different claims. Never silently fill an unobserved actor or item with a default.

## Move from scene facts to interactions

A **“Pac-Man-like” intermediate view** means a bounded representation with
moving actor positions and placed items, grounded in a selected state or source.
It can make a large scene inspectable before its behavior is understood. Record
exact units, stable IDs, revision, camera/viewport, geometry/stacking and which
positions are live, frozen, captured or unknown. A displayed object is not
necessarily visible to the original player. This intermediate view does **not**
prove pickup, pathing, aggression, damage, persistence or normal reachability.
It is optional when the requested task does not benefit from a spatial view.

For each requested interaction, connect input/trigger -> dispatch -> guards ->
state changes -> events/presentation -> persistence. Before translating the
operation, identify the controlled actor, target and item, authority, mode,
units, timing, relevant intermediate states, expected rejection and effects of
repetition. Compare a short positive case with a relevant unchanged-state or
negative control. If direct state placement is used, label the result assisted
and separately test ordinary input/reachability when the claim requires it.

A Z or Zork-like text projection is another consumer of the qualified state,
not evidence that the game is a Z-machine story or that its entire script was
recovered. Bind descriptions and actions to the same authoritative runtime and
fresh context revision. Preserve unknown visibility and current/captured state;
do not let a renderer invent gameplay, maintain a second world or promote an
unobserved inventory to empty. A passive overview, an executable action and a
persisted save are separate qualifications. Consult
`semantic-contracts.md` for what is lost or changed.

## Rank candidate questions and choose a probe

List only a few realistic candidates. Score them qualitatively, not with fake
numeric precision. A useful next question changes a decision or unlocks a
critical dependency; a cheap observation is worthwhile only if its possible
outcomes distinguish the live hypotheses. Explicitly identify:

| Criterion | Ask before choosing |
| --- | --- |
| Decision value | What user-facing claim or blocked dependency will this settle? What changes if each outcome occurs? |
| Information gain | Which competing explanations are separated, including a negative/control outcome? Can the chosen observation distinguish them? |
| Confidence and evidence | What is already source-bound, observed or independently verified? Is the probe based on a reliable current state? |
| Risk and reversibility | Can it alter guest, host or external state? Is a valid reset available, and does that reset include the affected state? |
| Cost | Include setup, guest time, wall time, compute/storage, trace volume, human attention and downstream comparison. |
| Scope and prerequisites | Is it authorized and supported by the actual backend? What prerequisite must be tested first? |

Prefer a high-decision-value discriminator with lower risk and total cost,
while preserving the evidence needed for the requested claim. If two probes
have different claim ceilings, the cheaper one does not replace the required
stronger one. A screenshot may show a sprite but not the writer of health; a
watchpoint and short trace can identify the writer but do not alone prove the
same effect was caused by ordinary input. Use both where needed.

Record one active question, candidate alternatives, expected observable
outcomes, input and clock bounds, chosen probe, rationale and stopping point.
After each result, update the graph and pick again. A failed or low-information
probe is evidence for reconsidering the plan, not a reason to repeat it without
a changed discriminator. See `methodology.md` for causal and
independence boundaries.

## Respond to a capability mismatch

Record what failed, how the failure was recognized, the next cheapest probe
that distinguishes the alternatives, and the condition for stopping or
changing approach. Preserve the backend identity and exact error alongside the
result. Do not turn an advertised feature into a working capability without
testing the operation and configuration needed by the claim.

| Observation | Next discriminator | Stop or branch |
| --- | --- | --- |
| A parser identifies a format or header. | Check whether it actually supplies the required runtime mapping, checksum, entry context or decoder; test the relevant operation on a small known input. | Treat identification as intake evidence only; do not infer execution or address translation. |
| A library exposes an architecture or mode constant. | Instantiate that exact mode in the installed native library, then decode a short synthetic example with independently known expected boundaries and operands; repeat for each required mode. | An error or wrong boundary rules out that configuration, not every version or backend. Keep unsupported modes unknown. |
| Installed tools offer a related processor or version. | Inventory the exact language and its state/addressing model, then compare a discriminating instruction against an independent reference. | Do not substitute a related processor when instruction widths or semantics differ. Use a verified existing alternative, or record the capability gap. |
| A static decode changes with hidden context or addressing. | Capture or otherwise qualify the entry mode, bank and relevant state; decode one short region with those inputs and compare to a source execution trace. | If entry state or mapping is unknown, retain alternatives and do not extend the decode as a fact. |

For example, when an installed decoder advertises several width modes but
one mode fails at construction, first verify that exact error and test a
small known instruction in the remaining modes. A successful neighboring mode
does not establish the failed one. Check whether a different already-available
backend supports the missing mode before proposing a new adapter or installation.
Keep any resulting workaround separately qualified; stop before interpreting
target code that depends on unresolved instruction lengths.

## Transfer an investigation to another target

- **Re-establish identity and intake.** A shared title is a lead, not evidence
  of a shared implementation, scene name, control scheme or address layout.
  Check the existing manifest and archive members and verify their identities
  before declaring a raw input missing; reuse the qualified source without
  silently substituting another edition. Recheck scene labels against this
  target's evidence. Carry forward an available claim ledger and observable
  contract, but do not require common source lineage or ask for it when the
  current target is clear. Transfer the investigation process, not an assumed
  common implementation or equal controls; compare each recovered model to its
  own exact source edition and reuse harnesses or gates only after qualification.
- **Qualify the observer at the needed boundary.** If the existing backend
  cannot expose the writer, choose an available observer that can capture the
  instruction-start address, relevant processor context, memory address space
  and writes. Verify its version and compare it with the baseline on a selected
  route before trusting its newly instrumented trace. Establish address mirrors
  and byte ordering from that backend and target; do not assume the old
  platform's conventions or claim coverage of
  events the observer cannot see.
  Record the observer's actual event coverage, filters and dropped events;
  a trace of direct stores alone does not exclude DMA or other writers. When
  dependency version strings disagree, check distribution metadata, runtime
  API version and library identity instead of selecting one string by guess.
- **Follow the actual read set into the model.** When a source operation reads
  geometry, saved data or other state, make each dependency an explicit,
  identity-bound input. Check the entry point and every memory region the
  native backend can access. A captured static region supports only that
  context; preserve mutable or unobserved updates as unknown or unsupported.
  Equal frame-end snapshots do not prove that scratch data stayed constant
  within a frame. When a consumer depends on it, watch the producer/consumer
  stages and derive the intermediate from modeled state; feeding a later
  observed intermediate into replay qualifies only a component comparison.
- **Test a complete control sequence.** A held direction alone may conceal
  release, reversal or turn behavior. Compare ordinary press, release and turn
  cases and an independent held-out sequence from a known start; examine the
  first mismatch. If later actor fields leave the qualified domain, keep the
  supported coordinate observations while refusing dependent claims.
  Compare each claimed actor or world field against source observations at the
  same input and frame phase. Full model/native agreement qualifies that
  compiler edge separately; it cannot establish source behavior for fields
  that were never compared. A component fed observed source state is not an
  autonomous frame simulation; document its inputs and phase. When a sparse
  checkpoint fails, collect consecutive samples around the first transition
  before assigning a cause. Record a refusal or missing sample as incomplete.
- **Resume from the right state.** A saved run history is evidence, not a live
  emulator connection. After interruption, identify the current backend and
  resource owner and verify any restored capture and its phase before issuing
  more input; do not treat an old session identifier as a reconnected guest.

## Branch, stop and refuse explicitly

- **Branch** when an observation admits competing explanations: retain each
  plausible cause and select the cheapest probe whose outcomes differ. If a
  source read conflicts with runtime, preserve both with their versions and
  find the first divergence. If a screenshot is occluded or a writer is
  unobserved, label the value unknown and choose an observation that can reveal
  it; do not invent an answer.
- **Stop a probe** at its explicit time, instruction, frame, output or risk
  budget. A budget stop is incomplete, never a stable analysis fixed point.
  Stop or switch to independent work if a required source/backend is missing,
  the selected evidence is stale, or a meaningful result needs user input.
- **Refuse the operation** if identity, permission, policy, valid state,
  bounds, destination, input readiness or safe recovery preconditions are not
  established. State what is missing and retain the last supported result.
  Do not execute an invented fallback or rebind a divergent binary without the
  exact required approval.
- **Reconcile before retrying.** A timeout, partial response, lost observation or
  uncertain side effect does not imply rollback or no effect. Inspect the
  original action's state and use only a qualified recovery path before any
  replay. A checkpoint's coverage must include the state being restored.
- **Finish or hand off** by mapping each requested claim to fresh evidence,
  supported scope, counterexamples and remaining unknowns. List the next
  discriminator for material open questions. Do not silently turn a bounded
  experiment into whole-game parity, a runnable model into an original-game
  result, or a static source interpretation into runtime observation.

## Worked decision examples

### Action RPG: Shadowrun-style field encounter

Suppose the task asks for a bounded player-damage encounter. A useful chain is:

1. Pin the supplied edition and current prepared scene. Inventory player and
   NPC records, their positions, camera and current health with explicit live
   versus captured provenance. A rendered actor/item map is an observation,
   not proof of combat or that the NPC is reachable.
2. **Actor motion:** compare a short no-input observation and one controlled
   player movement with the same starting state. Determine whether the NPC
   record changes, identify its writer and timing, and retain no-motion as a
   possible result rather than assuming a frozen target is equivalent.
3. **Aggression:** compare the same NPC at two source-valid distances/contexts
   under ordinary time. If response differs, trace the predicate or state writer;
   if it does not, test whether the relevant state or clock was actually active.
   A placed actor is an assisted discriminator, not ordinary reachability.
4. **Aim and fire:** separate target acquisition, weapon readiness, projectile
   creation, travel and collision. Establish exact pointer/slot selection and
   guards; compare a miss/blocked case and one eligible case. A target marker or
   screen rectangle is not proof of line of sight or a hit.
5. **Player damage:** watch the player's health writer from the first incoming
   contact, compare before/after and a controlled no-contact case, then check
   depletion and recovery only if they are within scope. Preserve tick order,
   RNG and collision unknowns; a simulated hit is not original-game evidence.
6. **Native comparison:** align the same initial state, actor identity, inputs,
   frame/tick and observation boundary across source, GameIL and target. Report
   field matches and first divergence, with original/NES timing and NPC AI
   independently scoped. Repeat under ordinary input when required; keep an
   assisted placement and its claim visibly separate.

When investigating a menu or scripted opening, record the full controller
interval and sample before, during and after each press. In one SNES Shadowrun
title run, the source consumed DOWN and updated its selection during the first
held frame, while the display changed on the following frame. A correlated WRAM
byte was an interrupt stack copy of Y, not the selection variable; the trace
identified the actual direct-page writer. Treat these as run-specific observations
and qualify input, state and presentation separately.

Align comparisons to the clock that runs the modeled work. In the same opening,
two video frames elapsed without another observed actor pass; a
video-frame-aligned NPC step therefore reported a false divergence. Compare
coherent source loop checkpoints for logical state, while preserving video-frame
checks for presentation timing. Recover script, scheduler, actor and scene
dependencies separately before claiming the complete opening transition.

Follow dependencies beyond the actor that first diverges. In that opening, one
task set an entity flag and another actor's task cleared it before completing
an animation and resuming a waiting script. Freezing other ready tasks or
acknowledging a callback without its state effects would skip a producer.
Trace the active scheduler and callback ABI before treating a function name
as a script-dispatch boundary; the initially suspected selector chose actor
control, while a separate interpreter consumed the bytecode. Keep native-only
continuation and separately source-seeded single-pass checks below the claim
ceiling of a continuous original-backed replay.

For an initialization gap, work backward from the first real consumer and
classify its missing inputs: constructor writes, ROM copy/decompression,
allocator state, script effects, device input, or preserved earlier state.
Choose the earliest missing producer that prevents the requested transition;
more isolated checks of stable wait loops will not establish that producer.
In the SNES opening, ROM decompression produced the entity flags, while task
creation needed a heap header that an older captured-state model omitted.
Zeroing all state would also have erased a preserved forced-motion countdown
that the original script reset only after the player appeared.

Inspect scheduler head, current pointer, insertion and return semantics before
equating one visit with one update. The opening's first scheduler visit only
primed its current pointer; nested task calls then ran a child and resumed its
parent within the same pass. For apparent tables, resolve the complete bank,
pointer and operand width: a low address in a nominal ROM bank can alias live
WRAM. Supply that read set from the containing model, not a later source pose.

Treat output routines as dependencies when they allocate identities, change
cursors, consume resource budgets, or release ownership. The opening's text
call owned window slots and timeouts; animation allocation gated actor sort
metadata. A rendering projection may omit pixels while still deriving those
effects. If hardware timing makes a sound or random result unknown, identify
its consumers, retain explicit taint, and refuse a later dependent gameplay
read. An acknowledgement without the producer does not complete this edge.

When host and original clocks differ, observe external buttons at the actual
source consumer. Validate the sampled held value, its prior latch and any later
consumer; do not infer consumption solely from the containing video frame.
Replay observed external input through the model's producer and compare the
prior latch rather than injecting it. Bind the journal to the same uninterrupted
reference execution and qualify observer neutrality separately. Distinguish
defined reachable collision records from unused allocator bytes when reporting
coverage; equal reachable lists do not establish whole-array equality.

For interaction recovery, separate selection, reach, action availability, dispatch,
and committed effects. In the SNES morgue, a named Mortician could be selected
without having an actionable wait mask. An in-range attempt remained a no-op.
Opening a different object signalled an entity flag and woke the Mortician's
task, which produced scripted text. Trace that causal route rather than adding
a Talk action because the target has an NPC label. A task association identifies
the producing task, not automatically the visual speaker of every text box.

An interaction menu can suspend a main-loop pass across many video frames and
controller polls. Record each actual poll, including post-confirm and
post-dispatch polls; NMI can publish a changed held word while sound or display
work runs between them. A main/player input difference can be valid when the
intervening modal observations explain it. Resume the suspended scheduler once;
do not advance physics once per menu input or reuse an earlier held word merely
because the polling routine itself does not query hardware.

For pickups, observe count/owner writes and actor teardown separately. The
morgue item wrote its count and owner, then waited through a real child script
before removing its actor. A second item changed ownership without a count increment. A placed actor record can also differ from the inventory-type record;
follow the actual writer when choosing the displayed item state. A sprite
disappearing or an emitted Pickup event is
insufficient evidence of inventory transfer. Test cancellation and repeated
attempts against source availability as well as the successful path.

Follow camera and representation dependencies when extending a short route.
A previously fixed camera began scrolling before cursor targeting diverged;
recovering cursor arithmetic alone could not fix the missing producer. Compare
camera position/velocity while keeping unmodeled tile-stream and NMI display
latches explicitly unknown. Same-video-frame snapshots can lie on opposite
sides of a source call; inspect their phase before aligning by frame number.
Likewise distinguish a text ID, an encoded compressed-text pointer and a CPU
address. Low-valued font glyphs can be controller icons; classify their source
handling before treating them as formatting controls or discarding their width.

For room progression, distinguish a door's visual action, a trigger volume and
the room loader. Trace both direct trigger calls and queued scene requests;
watching only the request word can miss a direct load. Record coordinate units
at the comparison instruction: an actor position may be shifted before testing
a ROM volume. Plan a route in one declared coordinate system, then validate its
controller replay in the original. A blocked approach is evidence about that
approach, not proof that the exit cannot be reached.

Recover the reload boundary before reusing an initializer. A new-game routine
can clear world flags, inventory and learned keywords that an ordinary room
transition preserves. Follow the source's carried-party reconstruction, actor
and task reset, destination data expansion, camera and collision setup. Compare
both the new room's live state and retained persistent records; a changed room
number or plausible player placement alone does not qualify the transition.
Read past a decompressor call when recovering initialization: its caller can
clear counters, copy adjacent tables and initialize selected statistics while
preserving gaps. A later mismatch in those records is a missing-producer
question, not a reason to shrink the comparison to the decoded block.

At a room boundary, old dynamic-list heads can still point into memory reused
by display-resource decompression. Trace a changed link's actual writer and the
next consumer before classifying it as live geometry or stale scratch. Keep a
raw-byte mismatch visible until the producer is modeled or a guarded liveness
contract explicitly excludes it; equal negative terminator tests alone do not
establish byte identity.
Name the admitted execution paths and guard their consumers; one filtered trace
of the next read does not prove liveness safety on every alternate path.

For keyword dialogue, separate the conversation record decoder from the live
conversation coroutine. Trace how a target obtains its conversation tag, which
selector values request an introduction, a keyword or a fallback, when keywords
are inserted, and whether a response creates a child script. Verify menu input,
response text, learned-keyword changes, script effects and cancellation through
the same source execution. A synthetic record test cannot establish NPC access.
Keep non-input display waits separate from input polls: coalescing an adapted
display delay must not consume another edge or advance suspended world tasks.
When selector instructions are shared by several menus, qualify their caller
context and compare it with the model's active menu. A learned keyword alone
does not prove that Ask about opened, a keyword was confirmed or its response
returned. Inspect modal window/text state separately when that stronger claim
is needed; main-loop comparisons can skip the entire suspended conversation.

Before replacing an unknown random draw, trace its consumers. A discarded sound
choice and a draw that sets an NPC timer require different recovery depth.
Recover the generator's state update and its external observations separately;
counter bytes can be read across an interrupt, so do not assume an atomic word
without evidence. A pure generator check using observed hardware values does not
authorize feeding its return value or later game state into the live model.
Choose and disclose the platform-input boundary before claiming an exact replay;
keep unsupported timing-dependent gameplay refused while that boundary is open.
A declared journal of hardware observations can support an input-driven replay
when its sampling phase, order, completeness, continuity and observer neutrality
are qualified. Label that conditional result separately from an independently
modeled clock or autonomous hardware-timing parity; an observed RNG return or
later gameplay record is not a substitute for external observations.

For an expensive source-state comparison, first use a compiled candidate with
the same title seed and input journal to locate unsupported operations cheaply.
Recover and test those operations, then rerun the full source comparison on the
frozen candidate. This frontier run is a capability check, not accuracy evidence.

**When the first actors cannot exercise the claim:** In a locally inspected
Shadowrun source run, the three captured moving actor records had item/weapon
byte `+$57 = 0` in each of 15 sampled states from frame 5999 through 7399.
The player's health byte remained 10 in those samples after one shot and an
idle period; the native receipt records no memory patches. The actor positions
changed in sampled states. This is evidence of motion and an unarmed candidate
profile at those boundaries, not proof of hostility, a civilian's complete
behavior, the absence of transient damage between samples, or enemy-AI parity.
The private capture receipt SHA-256 is
`9a813e7042bd6a76d0bb7aeda3ea87e387453827c72274f32191b89b94bc9aec`; the native
receipt SHA-256 is
`1e067a53406f4571e0b9b0ad5c818c37d3c8ccf4348e9be58306e1bb40abbd00`.
The next discriminator for player damage is a source-qualified hostile
spawn/activation and weapon-decision path, or an explicitly constructed
source-valid hostile profile with its intervention and limitations recorded.
Do not arm these actor records merely to manufacture a hostile encounter or
call their movement enemy aggression.

If the immediate question is only “which instruction writes player HP?”, start
at step 5 with a watchpoint; do not first build a city map or recover all NPC AI.

### Unfamiliar arcade maze

The request is to describe moving characters and objects, with no pickup claim.
Identify the supplied build and map scene. Compare two ordinary frames under
no input, then a short direction input. Link candidate position records to a
sprite through a controlled displacement; retain a stationary decoration as a
competing explanation until discriminated. Output actor IDs, coordinate units,
placed-item IDs and captured/unknown status. Stop there if this is the requested
result. If pickup is later requested, trace contact, item disappearance, score
and persistence as a new interaction; adjacency alone is not pickup.

### Unfamiliar turn-based text game

The request is to explain whether a locked door can be opened. There may be no
spatial actor grid at all. Record the current context, door ID, carried items,
turn counter and input policy. Compare a normal `open` with and without the
relevant item, watching turn consumption and the door-state writer. If an item
name comes from an external guide, label it a hypothesis. A text projection can
then expose only observed actions and unknown prerequisites, bound to the same
runtime revision. Do not infer a global map or a complete interpreter.

## Choose the next reference

| Current need | Read next |
| --- | --- |
| Select an installed command, backend or player | [workflows.md](workflows.md) |
| Design controls, baselines, trace evidence or recovery | [methodology.md](methodology.md) |
| Qualify scene recognition, geometry and actor movement | [scenes.md](scenes.md), [runtime-navigation.md](runtime-navigation.md) |
| Recover an interaction or compare text/model losses | [semantic-contracts.md](semantic-contracts.md) |
| Reuse prior source, route reports or research | [recovery-research.md](recovery-research.md) |
| Qualify source/model/output edges and proofs | [udl-uil-udc.md](udl-uil-udc.md), [proofs.md](proofs.md) |
| Inventory a container or choose a media reader | [formats-and-media.md](formats-and-media.md), [media-modules.md](media-modules.md) |
