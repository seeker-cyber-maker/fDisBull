# Bootstrap an interface and learn how its game advances

Decision: 18 November 2026. Dot needs a process model as well as scenes,
entities and controls: what accepts an action, when its effects occur, what
advances the game, and when another action becomes usable. Recover the smallest
useful part while retaining ordinary input routes and verified prior work.

Status: design and operating guidance. This adds no live capture facade,
event-loop analyzer, scheduler, XCOM provider or new gameplay qualification.
The source-backed [XCOM reuse map](XCOM_REUSE.md) and
[DinoPark reuse map](DINOPARK_REUSE.md) identify existing components and limits.
Read this document through `dotbox guide --topic loops`.

## Contents

- [Use the shared transition contract](#use-the-shared-transition-contract)
- [Start with the current prompt](#start-with-the-current-prompt)
- [Use saves as structured evidence](#use-saves-as-structured-evidence)
- [Represent processes and clocks](#represent-processes-and-clocks)
- [Correlate one input with its effects](#correlate-one-input-with-its-effects)
- [Prepare with isolated helpers](#prepare-with-isolated-helpers)
- [Separate readiness and preparation time](#separate-readiness-and-preparation-time)
- [Small implementation and acceptance slices](#small-implementation-and-acceptance-slices)

## Use the shared transition contract

Menu opening, screen switching, room entry and local state mutation are
instances of [event-conditioned transitions](EVENT_TRANSITIONS.md). Input
modality is a binding; guards, effects and continuations describe the operation.
The examples below use menus to explain discovery, not to define a separate
semantic foundation. Phase/timer rules schedule or constrain the same transitions.

One recovered mechanism can expose sibling callers, selector arms, script
instructions or table entries. Retain a family, its parameterized bindings and
actual occurrences separately. Transfer evidence for the common parts, inspect
material differences and qualify the boundaries needed by the current consumer.
New findings can unlock several independent analyses; use that dependency
frontier alongside preparation for likely next locations.

## Start with the current prompt

Ask: **What does this screen require to make the next intended progress?**
Use a fresh observation and a known applicable control immediately for that
intent. A named scene, complete screen model or complete game loop is not a
prerequisite. Investigate only the missing condition or control.

A main menu offers useful research branches, not a compulsory checklist:

| Observed branch | Potential evidence | Stop when |
| --- | --- | --- |
| Options, help or controls | Input conventions, key assignments, mouse mode and settings | The needed control is understood; leave unrelated settings unchanged |
| Load or save | Slot selection, component files, record structure, loader adoption and reconstructed state | The current persistence/state question has a testable answer |
| New game or Continue | Startup transitions, chosen difficulty/region, intro prompts and first operating interface | One useful selected action and its next state are supported |
| A changing intro or attract screen | Automatic progression, a skippable segment or a prompt waiting for input | The next actual context is observed, including its readiness |

For an intro, separate waiting from input. Observe whether the guest and screen
progress, then send one qualified click/key only when appropriate and observe
the next context. Do not queue repeated clicks across an unknown boundary;
the next click could choose a difficulty, start a transaction or skip a decision.
Background art appearing does not establish that controls have appeared.

Retain useful actions as soon as learned. Progress from a named input-backed
control to a composed route, then a richer semantic operation when evidence
warrants it. Preserve the ordinary route when optimizing a repeated operation.
A blocked UI task need not block independent file analysis or record census.

## Use saves as structured evidence

Save/load often exposes important persistent state. It is evidence about what
this edition serializes, not a complete inventory of every live value. A loader
may rebuild geometry, pointers, caches, derived displays or transient state.
Serialized file order, live memory order and simulation update order are
different relationships and require separate evidence.

Repeated record sizes and a consistent scene/object traversal can suggest the
developers' organizing scheme. Retain that as a hypothesis: neighboring fields
do not automatically name entities, and adjacent records need not update in
that order. Compression, checksums, indirection and versioned layouts can make
raw byte differences misleading. Reuse an existing decoder and loader contract.

Run controlled experiments in a helper's isolated guest and mutable filesystem:

1. Record edition, baseline identity, selected entity/context and applicable
   clocks. Compare repeated baseline saves to find incidental changes.
2. Compare a meaningful ordinary action against a matched no-action window.
   Preserve raw differences and their file/buffer/record coordinates.
3. Change one candidate value with a reversible, distinguishable sentinel, or
   batch independent candidates whose effects can be distinguished. Keep field
   width, signedness, bounds and format integrity explicit. Restore the isolated
   baseline between variants; do not let one variant contaminate the next.
4. Distinguish a native-memory edit from a save-file edit. When the hypothesis
   concerns saved state, use the original save/load path or an independently
   qualified equivalent to test serialization and reconstruction. A successful
   file read or a changed staging buffer does not establish authoritative adoption.
5. Observe original continuation, relevant native state, display and control
   readiness. A delayed redraw is a separate question from whether the field
   changed. Verify restoration in the state scope being claimed.
6. Return the conditional mapping and competing explanations. A single matching
   number is a lead; repeated controls/interventions strengthen its interpretation.

Complete only the boundaries required by the finding's consumer. A file-layout
or record-census question can finish without a display or input-readiness test;
a claim about live adoption or a usable player action needs those relevant
witnesses. Do not turn the diagnostic boundary list into a mandatory full cycle
for every investigation.

These are research interventions, not ordinary player progression. Dot's player
rewind still restores machine memory/state while preserving current disk files.
Helper save restoration does not change that policy. See
[recovery and saves](RECOVERY_AND_SAVES.md).

## Represent processes and clocks

Extend the proposed [internal model](WORLD_MODEL.md) with evidence-bound process
records. Keep a partial graph of relevant phases and events instead of imposing
one universal linear state machine on every game or subsystem.

| Record | Required meaning |
| --- | --- |
| Process/subsystem | Mode, relevant entities and context in which a rule applies |
| Phase or boundary | Observed entry/exit predicates, accepted commands and interruption behavior |
| Trigger | Input, turn end, guest tick, calendar boundary, movement-step counter, callback, queue or another observed event |
| Pending operation | Attempt identity, selected target, accepted parameters, observed phases and remaining work |
| Effect and dependency | Immediate, deferred, conditional or unknown effect; producer/consumer evidence and applicable state |
| Ordering claim | Observed or inferred happens-before relation, coverage and counterexamples; unknown order stays unknown |
| Clock binding | Counter/domain, advancement, speed setting, pause behavior and relationship to other clocks when measured |
| Observation recipe | Context-bound pixels, memory fields, trace sites or serializer evidence that witness the claim |

Keep local state change and navigation as independent axes. One input can change
a value, change context, do both, or queue later work. A menu can be modal while
some simulation subsystem continues. A calendar hold does not prove all actor,
input or rendering work stopped. Rendering, persistence and readiness can occur
in different orders for different operations.

Track three time domains separately:

- **Host monotonic time:** player-visible delay, model/tool work and request budgets.
- **Guest execution:** execution actually allowed, emulated ticks and instrumented stops.
- **Game time:** turns, phases, days, movement steps or other title-defined counters.

Do not infer game time from a host sleep. Record how menus, animations, speed
controls and debugger stops affect each relevant domain. Counters from different
machines do not share a monotonic origin. A breakpoint trace can establish a
path or partial order while distorting natural timing; qualify timing again
without those stops before calling it ordinary-play latency.

For random or threshold-triggered events, record the counter, condition and RNG
state/seed only where available. Matched baselines may diverge because execution
consumes randomness differently. Do not promise deterministic prediction from
step count alone or require complete RNG recovery before a useful bounded action.
The user's step/RNG encounter and battle-phase analogies motivate this contract;
they are not recovered rules for a particular Final Fantasy or card-game edition.

## Correlate one input with its effects

Use richer observation during discovery and cheap qualified predicates for
routine recognition. One before/after image can miss a transient menu, a queued
operation or a state change that precedes rendering. Capture a bounded sequence
around the unresolved boundary, with frames and native reads joined to the same
context where the backend supports coherent capture. Mark gaps when it does not.

A reusable experiment packet should contain:

1. Baseline game/resources, code mapping, context/entity selection, branch,
   relevant state, capture profile and clock origins.
2. One selected-action trial A, with repeats, a matched no-input window or a
   contrasting B when they resolve a concrete ambiguity. Retain the initial
   observed relationship immediately. Reset isolated state deliberately between
   comparisons and retain RNG/environment differences.
3. A finite, declared set of candidate breakpoints/watchpoints or a bounded
   execution window, with byte/mapping checks, stop conditions and cleanup owner.
4. One input attempt with an intent/attempt ID, dispatch receipt and timing.
5. Sampled frames/pixels, selected state windows and execution/access records,
   retaining first observed dispatch, effect, presentation, readiness and
   persistence separately. Unobserved boundaries stay unknown.
6. A finding: candidate relationship, evidence coverage, alternative explanations,
   applicability predicate and next discriminating probe.

A broad breakpoint spread is a finite search campaign, not a claim of complete
downstream coverage. Retain each observed control/site/value association first;
use repeated A, idle or B to narrow a concrete unresolved relationship.
When choices share a dispatcher, preserve site-plus-argument/register/value
candidates: deleting every site also visited by B can discard the correct shared
handler. A hit proves observed execution at that site; it does not automatically
identify the unique handler, a causal effect or every deferred consumer.

For several visible controls, use [comparable multi-probe trials](BEHAVIOR_AND_ENTRY_POINTS.md#record-transient-paths-across-controls):
arm candidate exits/destinations together, record one input's transient path,
then memory-restore, verify and re-arm for another control. Retain useful
control-to-site/selector relationships before detailed handler analysis. A
first-hit watch and a bounded sequence recorder have different coverage; save
the ending condition and keep recordings outside the guest rewind. File effects
survive memory restore, so comparable trial setup must account for them explicitly.

Use executable/address-space capability checks. The shipped fDisBull live
`debug-trace-until` workflow's owned, stopped real-mode entry conditions do not
qualify a generic capture path for XCOM's LE executables. Recover edition/backend-specific support
before transferring a tracing recipe. This guide does not port those APIs.

For deferred effects, follow the smallest useful producer/consumer relationship:
which field, queue entry or callback request did the action produce, and what
later observed event consumes it? A queue, a latch and a direct call can look
similar in one screenshot. Leave their distinction unresolved until supported.

Pixel patterns establish presentation witnesses. Keep scene recognition,
selected item/value, modal exclusion, input readiness and semantic commit as
separate checks. Learn stable positive and negative anchors, reserve checks and
layout/context bindings. Unknown or conflicting samples trigger bounded richer
observation; they must not silently weaken a classifier or renew a research budget.
Retain full frames at meaningful discovery/action/diagnostic boundaries without
requiring expensive full-frame analysis for every routine poll.

Release only probes owned by the experiment, and preserve existing stop reasons.
For a short capture-only pause in live play, resume before model reasoning only
through a known safe resumption/continuation path owned by that capture. Ownership
alone does not make an arbitrary native stop safe to resume. Do not automatically
resume an unknown stop or issue cleanup input after human takeover. An isolated
helper may remain stopped for debugging; retain that instrumentation time and
its continuation requirements. A confirmed effect with a missing display/readiness
witness requires reconciliation or a qualified continuation of the same attempt,
not resubmission.

## Prepare with isolated helpers

Dot owns live input and the selected harness revision. Helpers can investigate
independent branches: startup controls, serialization/records, action dispatch,
or a later event phase. A copied machine checkpoint is insufficient isolation
if mounted save/config files remain shared. Each experimental guest needs its
own mutable files, process/session state and probe namespace.

Give each helper a concrete consumer, frozen evidence identity, explicit bounds,
early partial result and dependencies. A single serial click route cannot be
accelerated merely by assigning more agents; parallelize work whose inputs are
already available. Do not substitute a menu research branch for the player's
chosen New Game/Load route.

Return reusable knowledge and a candidate observation/action recipe. Helper
progress is not player progress. Static evidence may survive a route change;
dynamic readiness, selection, phase, timers and attempt bindings need a fresh
check against the live session before adoption between actions. Never transplant
a helper's save/state or replay its successful probe as part of adopting knowledge.

## Separate readiness and preparation time

Record milestones independently:

| Milestone | Evidence required |
| --- | --- |
| First interface visible | An observed screen; says nothing by itself about control readiness |
| First useful control | One selected action with observed effect and applicable input route |
| Current operating slice | Enough selection, submission, cancellation/continuation and observation for the present goal |
| Relevant loop understood | Evidence for the phase/trigger/clock relationships needed by that slice, with unknowns preserved |
| Broader autonomous coverage | Separately qualified additional goals and recovery domains |

The existing **180-second profile** evaluates an initial usable control slice;
it is not a promise to reconstruct every unfamiliar interface and game loop in
three minutes. A complex cold-preparation job may declare a longer bound and
specific milestones before that job starts. Record the profile and actual
elapsed time. The user's **10+ minute XCOM estimate is unmeasured**, not a default
or an inherent lower bound; historical results in [XCOM_REUSE.md](XCOM_REUSE.md)
demonstrate why reaching Geoscape and completing a state operation differ.

Keep the original start and any missed deadline. A deliberately separate longer
job must not relabel the old miss, reset an active learning focus or become a new
startup allowance at every menu. The **15-second/two-probe** foreground policy
still bounds investigation of a blocked live action. A helper's longer budget
does not extend that interval. When no applicable fallback exists, state the real
block and let the user continue through available controls, wait for explicitly
described preparation, or choose another available route. No debugger decisions
or blanket new permission ritual are needed.

Use selected movement, necessary animation and player decision time when they
occur naturally. A menu-only transition may offer almost no buffering. Do not
slow input, change game speed, pad speech, hold an intro or invent a pause mode
to conceal preparation. Persist the compatible result so later sessions measure
warm reuse rather than repeating cold discovery.

## Small implementation and acceptance slices

First establish one ownership-aware coherent capture packet through DotBox's
supported session interface. Then connect one existing menu action to phase and
effect witnesses; adapt existing discovery/refinement machinery only where an
actual unresolved relationship needs it. Store process claims in the proposed
world model, separate from current SceneStore observations and input admission.

Required future acceptance cases include queued commit, delayed rendering after
commit, an incidental timer changing without input, independent subsystem pause
behavior, original-loader reconstruction, ambiguous serialized record order,
shared dispatch with different arguments, missing breakpoint coverage, observer
timing interference, helper filesystem isolation, stale results after rewind,
RNG divergence, long preparation with early usable controls, and expiry without
a useful fallback. Evidence from authored fixtures and actual game runs remains
separate. This documentation change implements none of those runtime gates.
