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

Need actual commands and example responses? Start with [next steps](next-steps.md);
use [types and addresses](analysis-types.md) for mapping and layout questions.

## Start with an outcome and a finite evidence ledger

For ordinary discovery, a question, useful result and next unlocked action are
enough. Reuse identities and observations supplied by tools; do not prepare a
manual ledger before a cheap probe. Use the fuller outline below for a broad
investigation or handoff, filling only what its next consumer needs.

1. **Intake and identity.** Reuse the allowed target/edition, current project,
   backend and policies. Check only missing or changed capabilities. A hash
   identifies bytes, not behavior. A saved run record is not a live connection.
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
Retain the missing critical edge and its next discriminator. If it cannot be
resolved now, take another ready task that advances the requested outcome.
Publish partial inputs so branches can start while neighboring work continues;
do not park every worker behind one blocker or substitute irrelevant easy checks.

Declare the observable contract before trying to reproduce every hidden field.
If an unknown scratch or display field lies outside the bounded read-set of the
requested motion or combat path, preserve it as unknown while verifying that
projection. Establish that independence from source/dataflow and execution
evidence when claiming replacement fidelity. For exploration, a scoped candidate
label can be used while that independence remains open. An unrelated unknown must not automatically
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

Keep one bounded question per worker, or a compatible batch sharing one visit.
Write down alternatives, rationale and detailed costs only when they help a
handoff or a consequential choice. Retain execution bounds in the operation.
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
| Runtime input is rejected in the current mode or state. | Identify the unmet prerequisite; try an already supported entry/readiness boundary within a short budget, preserving the guard. | Record a state-specific rejection, not permanent target incompatibility. Publish a working recipe as soon as one exists. |
| Input is accepted but the requested effect is absent. | Distinguish queued, delivered and acted-on input. Check release/readiness and one changed timing or same-session press/release cycle when repetition is appropriate. | Stop on the requested effect; otherwise retain the exact unresolved condition. Do not restart and repeat the same first input indefinitely. |
| A diagnostic step suggests guest behavior is broken. | Observe the next boundary through ordinary execution; the diagnostic itself may alter or omit dispatch. | Keep observer failure separate from guest failure. A normal-run result can unblock the action without repairing that observer first. |
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

For runtime cases, use `runtime-navigation.md`, "Establish one input and outcome."
Return the failed condition, useful output and next discriminator. A blocked
operation remains recorded if another route succeeds; it does not make the
successful route unusable. Send the working recipe to dependent workers while
other branches continue, without requiring them to read the diagnostic history.

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
- **Follow the actual read set into the model.** When a source operation reads
  geometry, saved data or other state, make each dependency an explicit,
  identity-bound input. Check the entry point and every memory region the
  native backend can access. A captured static region supports only that
  context; preserve mutable or unobserved updates as unknown or unsupported.
- **Test a complete control sequence.** A held direction alone may conceal
  release, reversal or turn behavior. Compare ordinary press, release and turn
  cases and an independent held-out sequence from a known start; examine the
  first mismatch. If later actor fields leave the qualified domain, keep the
  supported coordinate observations while refusing dependent claims.

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
