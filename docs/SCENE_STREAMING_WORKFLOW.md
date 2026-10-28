# Draft workflow: progressive scene recovery during gameplay

Status: **draft experiment design**, 28 October 2026. Author: **Codex**, from
the user's clarification that the priority is simplifying and accelerating
use of the working tool. This supplements the
[intent pipeline RFC](INTENT_PIPELINE_RFC.md) and its
[recovery cases](INTENT_PIPELINE_RECOVERY_CASES.md). It specifies no new API,
canonical UIL syntax or implemented scheduler, and reports no Sierra trial.

## Goal and two consumers

An agent should reach a useful, verified interaction after recovering a small
part of its current context. Further analysis produces usable increments as
gameplay progresses. Complete-game understanding is a separate deliverable;
it need not precede every live-game harness action. Both efforts can preserve
the same scene identities, source evidence, actions, observations and revisions.

| Consumer | What a scene needs | Who executes game rules |
| --- | --- | --- |
| Live-original agent harness | Recognizable current context, supported named actions, fresh availability conditions, real input and observable outcomes, with bounded stops. | The original game. A scene package supplies interaction knowledge; it does not replace the game's implementation. |
| Reconstructed scene/runtime | The above interface contract plus defined state transitions, time, randomness, services and required semantic dependencies for the supported slice. | A qualified downstream implementation of the recovered semantics. A required unknown effect cannot be filled in by guessing. |

An incomplete scene can expose individually qualified actions. Record the
unmodeled actions and conditions separately; an unknown interaction is not
known to be impossible. A harness can use a verified input/outcome contract
while deeper internal rules remain under investigation. Each resulting claim
keeps its actual scope. The [UIL ownership boundary](UIL_BOUNDARY.md) remains
unchanged; recovery orchestration is distinct from owning a downstream player.

## Existing support and remaining workflow work

The [scene framework](SCENE_FRAMEWORK.md) already supplies immutable revisions,
named real guest actions, separate visibility/readiness/enabled predicates,
bounded waits, fresh observations, diagnostic captures and retained evidence.
[Scene bundles](SCENE_IMPROVEMENTS.md#portable-scene-bundles) already transfer
declarative definitions and clean reference PNGs into a compatible project.

The inspected implementation has relevant limits:

- A scene handle pins a revision. A new definition is not automatically adopted
  by an active route. Import remaps local identities and rejects an existing
  scene name; it is not a merge or incremental-update protocol.
- Bundle compatibility binds the original executable and mapped byte view.
  It does not bind a complete Sierra resource dependency inventory. Logic,
  picture, view, vocabulary and other resource identities need an additional
  declared binding before a gameplay package can rely on them.
- Observations evaluate competing stored scenes. A growing library can increase
  probe and ambiguity costs. A future context index must preserve applicable
  competing recognizers and global/modal blockers rather than hiding conflicts.
- The inspected [0.20 AGI inspector](https://github.com/seeker-cyber-maker/fDisBull/blob/001901d1361ab3a536de61e0292520af1ac32afd/src/fdisbull/agi.py)
  is partial static 2.917 decoding. It does not implement guest execution or a
  cross-resource dependency analysis; its supported action table does not yet
  cover calls or room-change commands. Instruction-budget completion is not
  completion of a room's behavior.

These observations follow the current [bundle implementation](../src/fdisbull/scene_bundles.py)
and [scene implementation](../src/fdisbull/scenes.py), plus the pinned development
inspector above. The scheduling, resource binding and reconciliation described
below are proposed workflow requirements, not existing bundle-format features.

## Smallest useful increment

Use the current interaction context and one useful action as the first unit.
A room number is a locator; subpage, camera, input mode, modal state and relevant
game state can change what is actionable. Prefer parameterized predicates and
stable identities to creating a new scene for every possible world-state value.

Each usable action needs:

1. Source/edition and definition identities, clean supporting evidence and an
   explicit scope for the context in which it applies.
2. Recognition and separate visible, ready and enabled conditions. A background
   match alone does not establish registered or usable controls.
3. A real guest input operation, expected observable outcome, relevant before
   values and declared guest-time and wall-time bounds.
4. Explicit handling of mismatch, unknown context, modal ambiguity, debugger
   stops and exhausted budgets, with evidence preserved for further analysis.

Store partial research separately until it satisfies the implemented scene
schema. Publish a valid scene revision with the qualified action subset; do not
invent placeholder actions that look executable. Report supported actions and
remaining coverage independently of live availability.

## Foreground interaction and background analysis

The proposed loop is:

1. Identify the current context and look for a compatible local or downloaded
   definition. Reuse it only after fresh recognition and availability checks.
2. If the intended action lacks a usable contract, analyze the minimum evidence
   and dependencies needed for that action. Unrelated gaps remain queued.
3. Publish an immutable usable revision and pin it for the action. Perform the
   real input, observe the outcome and retain the transition evidence.
4. At the next explicit action boundary, adopt a newer revision if appropriate,
   recheck its prerequisites and choose the next useful action.
5. Refine incomplete contexts and likely next interactions within a separate
   analysis budget. On an unexpected result, pause the affected action, record
   the mismatch, and resume after the contract has been resolved or revised.

One controller owns live guest advancement and input. Background workers can
inspect immutable bytes and saved observations without moving the live game.
An experiment that requires execution uses a serialized probe or an explicitly
isolated session with declared state and external-service handling. Two workers
must not independently resume, restore or send input to the same live guest.

Declare the live-time policy: whether the guest is paused during analysis or
continues to run. Record guest progress separately from analysis wall time.
Otherwise a faster strategy may encounter a different timer, animation or
random sequence and appear to have a different semantic result.

## Sequential and on-demand strategies

Both strategies expose the first usable increment promptly. They differ in
which work receives the next analysis budget; neither requires all rooms to be
processed before the first interaction.

| Strategy | Work-selection rule | Expected tradeoff to measure |
| --- | --- | --- |
| Sequential | Follow a declared ordered route of contexts and interactions, preparing the next increment while the current one is usable. Record whether that route came from a walkthrough, prior investigation or exploration. | Predictable preparation and potentially fewer stalls on that route, with work possibly spent on contexts the player never reaches. |
| On demand | Prioritize the current context and intended action, then only dependencies needed to establish that action's contract. | Less unused analysis, with possible pauses at novel interactions or unexpected transitions. |
| Bounded lookahead variant | Add a fixed analysis budget for plausible next contexts to the on-demand strategy, using declared accessible evidence. | May reduce transition stalls at extra analysis cost; evaluate separately after the two basic strategies. |

An optional whole-package-before-play run can provide an offline latency
baseline. Keep it separate from the sequential streaming strategy. A known
route or downloaded package is advance knowledge, and its cost and access
profile must be recorded rather than counted as free discovery.

## Dependency-aware Sierra recovery

The [content adapter proposal](GAME_CONTENT_AND_PLAYER.md) supplies the longer
term boundary. For an AGI experiment, identify the actual supplied edition and
profile before using a decoder. Recover a shared context for global logic,
variables/flags, vocabulary, inventory and engine behavior incrementally.
Bootstrap only the common identity, input mode and shared-state observations
needed for the first intended action. Expand shared recovery when a later
action needs it; complete global-logic or engine recovery is not a startup gate.

A room's numbered logic resource is not automatically its whole behavior.
Global logic, called scripts, dynamic targets, timers, sound completion and
shared state can affect the action. Keep unresolved targets visible. If an
unresolved dependency prevents qualification of the action, stop that action's
promotion; an unrelated unresolved resource need not block a different,
already-qualified live-original action.

For a live-original harness, relevance means evidence needed to justify the
declared input/outcome contract. A bounded observed contract can be usable while
the original executes undecoded internals. A standalone reconstruction needs
the executable meaning of those required internal dependencies as well.

Native input, snapshots and bounded state observations can establish a harness
contract when static decoding is incomplete. They do not establish a complete
standalone reconstruction. Add supported processor operations only when the
next investigation needs them and verify their encoding/behavior separately.

Do not feed investigator-only variables, unseen resource text or recovered
future puzzle solutions to a player-equivalent agent. Resource inspection can
help build the harness while its player view exposes only the declared
observations, action discovery and outcomes. An investigator run may use a
broader view, with a separate performance claim.

## Packages, revisions and invalidation

A prebuilt package and an incrementally authored package should eventually
offer the same action interface. The difference is their declared coverage.
An incomplete package lists its usable contexts, unresolved dependencies and
missing pieces; installation is not evidence that all scenes are understood.

Keep a proposed resource/dependency manifest beside the existing scene bundle
until an accepted format defines the binding. Do not silently add fields to
`fdisbull-scene-bundle-1`. The manifest needs source and relevant resource hashes,
engine/profile and adapter versions, origin-to-local identity mappings,
definition revisions, observation scope and evidence references. Claim the
whole source edition is bound only when its required inventory is covered.

For the first experiment, import a compatible package into a fresh project and
retain the returned ID maps. Create local improvements through the existing
parent-revision mechanism. Repeatedly importing an updated package over local
scenes is unsupported. A later reconciliation protocol must preserve local
edits, historical revisions and conflicts explicitly.

Adopt revisions between actions; never change an in-flight action's guards or
postcondition. A new counterexample can stop further input with the original
revision and partial outcome retained; it does not authorize silent retargeting
or rollback. Ordinary flag, camera or modal changes require fresh availability
checks within the existing qualified domain. Restart and restore also require
fresh runtime bindings where applicable. These events do not by themselves
discard a still-applicable behavioral contract.

Changes to pinned code, resources, engine assumptions, definitions or relevant
dependencies require requalification of affected contracts. Crossing a
contract's supported domain has the same consequence. Historical snapshots
remain historical after import. Re-evaluate fresh state before any input, even
with a complete package; redo analysis when evidence or assumptions require it.

## First Sierra experiment

Use one identified original AGI edition of PQ1 or KQ1, then repeat the workflow
on the second game to measure reuse. The first route should include two
contexts, a blocked interaction, a modal or text-input state, a transition,
and a revisit after changing inventory or another relevant condition. Bind the
route to actual supplied artifacts and evidence before claiming it is runnable.

Compare sequential and on-demand strategies in two knowledge conditions:

- **Cold:** no authored scene package for the route. Both strategies receive
  the same initial artifacts, observations, task and route/goal information.
- **Warm:** the same pinned compatible package is available to both. Account
  separately for download/import/validation and fresh runtime recognition.

Use matched starting game state, agent/analysis versions and worker concurrency,
observation profile, input-task conditions, total budgets and guest-time policy.
Clear or explicitly inventory analysis caches for each cold trial. A fixed-input
replay isolates orchestration overhead; a separate adaptive-agent run measures
gameplay usefulness. Do not merge their performance claims. For timing-sensitive
tests, record and reproduce the declared guest-tick input schedule; a live-time
run whose analysis delays alter that schedule is a separate experiment.

Record time to the first successfully verified useful action; per-action and
transition stalls (median, tail and maximum); analysis effort per accepted
action/context; bytes or resources inspected; unused lookahead; successful and
failed outcomes; stale/ambiguous checks; and verified package or adapter reuse.
Break out setup, import, analysis and guest-execution time. Compare latency only
at equal declared behavior/observation requirements, and report failure rates
alongside speed. Count unresolved budget stops as incomplete work.

Choose the first policy from these measurements. The target is lower latency
to useful interaction and less repeated analysis while retaining the action's
required evidence. This document makes no measured speedup claim.

## Proposed workflow acceptance cases

These are authored requirements for a future experiment, not executed tests.
They complement the 14 semantic vectors in the recovery amendment.

| ID | Situation | Required observation |
| --- | --- | --- |
| W1 | The first action is qualified while unrelated later contexts remain unanalyzed. | That action can run with fresh checks; the pending analysis remains explicitly incomplete. |
| W2 | The agent enters an unknown context. | Prior-context inputs are withheld; the new evidence is retained and only the missing contract/dependencies are prioritized. |
| W3 | A compatible scene bundle is imported. | No guest input or claim of current readiness arises from import; fresh recognition is required before the first action. |
| W4 | The relevant game resource differs although the executable hash matches. | Package qualification is withheld until the changed binding and affected definitions/evidence are requalified; replacing a hash alone is insufficient. |
| W5 | A new scene revision is published during an action. | The action and its receipt retain the pinned revision; adoption occurs at an explicit boundary followed by fresh checks. |
| W6 | Restore, modal state or a shared flag changes an action's conditions. | Previous availability is not reused; the next action observes the changed conditions and preserves ambiguity or refusal. |
| W7 | A dependency needed to justify the declared action contract is unresolved or exceeds budget. | The affected action is not promoted on invented semantics; unrelated qualified actions remain usable. Undecoded internals alone do not block a live-original action already justified by its bounded observed contract. |
| W8 | A background analysis worker requests guest execution while the live controller is acting. | The request is serialized or routed to a declared isolated session; the live timeline has one owner. |

Implementation should first exercise this protocol with the existing scene
operations. Extend import/revision or dependency machinery only when the
experiment exposes a concrete limitation. Full recovery and standalone UIL
execution can then reuse the accumulated scene evidence at their own stricter
semantic qualification boundary.
