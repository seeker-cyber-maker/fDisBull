# Learn transition families and expand the analysis frontier

Decision: 18 November 2026. Use an event-conditioned state transition as the
common foundation for menus, screens, rooms, selections, transactions and timed
events. A useful discovery can explain a family of related transitions and
enable several further investigations. Dot should retain and exploit that
structure instead of restarting analysis for every visible interaction.

Status: design and operating guidance, packaged as `dotbox guide --topic transitions`.
This does not implement a transition store, generic structural scanner, task
scheduler or new live control. Existing evidence and reusable components are
identified below; the [world model](WORLD_MODEL.md) owns their proposed records.

## One transition contract, many bindings

A transition relates relevant state and an event, under a context and guard,
to possible effects and continuations. Use a relation rather than assuming a
fully known deterministic function. Outcomes may be conditional, partly known,
random, deferred, or accompanied by other events.

Mouse clicks, keys, spatial crossings, script calls, callbacks and timer events
are event sources. Their physical production remains in the binding: a door
crossing may require monitored movement, while a menu shortcut needs one key.
These costs, timing, guards and cancellation behavior survive the abstraction.
An input can be ignored, emit several events, or begin a chain of transitions.
Dispatch alone does not prove an effect; a visible difference alone does not
prove which event caused it.

The following are authored examples, not recovered rules for a specific game:

| Binding/event | Possible guard | State effect |
| --- | --- | --- |
| Click Inventory or press its shortcut | Correct context; no blocking modal | Activate an inventory panel while preserving location |
| Cross a doorway boundary | Actor at edge; door unlocked | Change location and initialize relevant room state |
| Select a menu row | Selection valid; action available | Set a value, replace a context, or queue an operation |
| A tick consumes a queued order | Required phase and pending record | Apply an effect and emit a completion event |

All use the same contract. Context push/pop, location replacement, local writes,
queued work and emitted events retain their actual meanings. A screen can show
several contexts at once; a common abstraction does not reduce all state to one
screen or room ID. Scenes are relevant projections of that state and knowledge.
Existing [phase and clock semantics](BOOTSTRAP_AND_EVENT_LOOPS.md) describe
transition dependencies and scheduling; they do not require a separate model
for each input modality or one universal phase pipeline.

Keep three records distinct:

| Record | Contents |
| --- | --- |
| Transition family/rule | Parameter roles, event pattern, guards/state reads, effects, continuations, ordering and applicability scope |
| Concrete binding | Family reference, actual selector/target/context, code site/script/table entry and supported input or movement route |
| Observed occurrence | Binding/attempt identity, live branch and context, event receipt, relevant before/after evidence and unresolved outcome |

Attach source/edition and mapping identities, evidence, assumptions, conflicting
examples and coverage to each claim. Populate only fields needed for a useful
claim; unknown effects or guards stay explicit. A family can explain many
bindings, and several routes can invoke the same semantic operation. Shared
code can also serve different operations selected by arguments and state.

Use [behavior hypotheses and entry bindings](BEHAVIOR_AND_ENTRY_POINTS.md) to
recover those alternatives. An agent's plausible implementation sketch predicts
which callers, selectors, mode writes or continuations to inspect. Several
routes may converge on one operation while omitting different setup or effects.
Retain a graph of qualified entries with scoped equivalence claims; an observed
hook alone does not authorize invoking that address. Deeper original operations
and coherent research states complement the working visible-play route.

## Learn one mechanism, enumerate its instances

A qualified example, supported decoder or recovered schema can expose the
mechanism shared by other transitions. Search code and data according to that
mechanism; identical-looking buttons need not have duplicated handlers.

1. Retain the useful seed and its concrete evidence. Identify the relationship
   it establishes, such as selector-to-handler or handler-to-state effect.
2. Separate structural invariants from parameters. Keep selectors, guards and
   meaningful constants as bindings; mask incidental relocation differences
   only where justified. Preserve source mapping, widths and calling context.
3. Enumerate siblings within declared bounds: callers, comparison arms,
   registration sites, callback tables, object records or script opcodes.
   A recovered table schema may expose more operations than repeated byte scans.
4. Retain deduplicated bindings and their unresolved questions. Record scanned
   ranges/resources, truncation, indirect paths and opaque continuations. A
   return to a caller or a queued request may cause the later context change.
5. Transfer evidence for the invariant parts. Investigate material differences
   and contrasting cases; refine or split a family when a counterexample appears.
6. Publish useful findings with dependencies and cheap applicability witnesses.
   Reevaluate the analyses whose prerequisites they satisfy, and keep ordinary
   supported play moving while independent work proceeds.

Use the cheapest sufficient representation: exact/masked bytes for a bounded
identity question, decoded structural/data-flow patterns for an operation
family, or a known script/data schema for bulk extraction. Matching a byte
sequence is not semantic equivalence, and equivalent transitions may have
different native implementations. Preserve site-plus-selector/argument/context
when multiple controls share a dispatcher; site-only subtraction can discard
the useful shared mechanism.

Evidence transfers by claim, not by treating every match as fully qualified:

| Evidence dimension | What it establishes |
| --- | --- |
| Structural/schema match | This binding satisfies the recovered pattern within the stated coverage |
| Semantic interpretation | Supported or hypothesized meaning, guards and effects of that binding |
| Execution qualification | A supported invocation route and outcome/continuation witnesses |
| Current applicability | The live context, guards, ownership and readiness allow the selected action now |

These are independent dimensions, not an automatic promotion ladder. A verified
table decoder can establish many structural or semantic facts at once without
clicking every control. Reuse proven family behavior where its assumptions hold;
test the instance-specific boundary needed by the consumer. Representative
samples alone do not prove every heterogeneous branch, and a static enumeration
does not grant live input. A helper finding never applies predicted effects to
the player's observation store.
Keep invocation/admission conditions separate from conditions determining
success. An unknown outcome does not prohibit an otherwise qualified attempt;
the operation may legitimately report failure or a newly discovered condition.

## Findings expose more answerable questions

Keep an analysis dependency graph alongside the play frontier. The useful
frontier is not limited to adjoining rooms. It includes questions that become
answerable after a schema, convention, field role or shared routine is learned.

For example, learning a control-table schema can expose independent work on
selector bindings, destination candidates and disabled-state guards. Learning
the effect of one shared routine can then clarify several previously found
calls. Learning a persistent flag's role can connect writers and consumers in
different contexts. These are authored dependency examples, not claims that
the native scanner already performs them automatically.

Each analysis task records its question, required claims/artifacts and evidence
level, alternative sufficient prerequisites where applicable, intended consumer,
possible downstream uses, source/model revision, useful-by point and hard bound.
Track unresolved prerequisites separately from ready, running, completed,
superseded or blocked work. An uncertain claim may enable a hypothesis test;
it does not satisfy a prerequisite requiring established semantics.

When a finding is accepted into the model:

1. Update only the affected reverse dependency links.
2. Identify newly answerable tasks and deduplicate overlapping work.
3. Prefer current-goal needs, likely upcoming uses and discoveries that cheaply
   unblock several useful consumers. Raw match count alone is not priority.
4. Batch deterministic scans first; assign independent semantic questions or
   isolated experiments to available helpers. Avoid one agent per byte match.
5. Merge evidence with its assumptions and counterexamples. If a dependency is
   revised or contradicted, invalidate or requeue affected interpretations.

Cycles and recursive dispatch need finite expansion bounds and retained visited
identities. No worker count removes a serial dependency. The same queue can be
processed by one agent when workers are unavailable; this document adds no
automatic scheduler or background lifetime guarantee.

Knowledge becoming available does not make a game location reachable. Static
analysis can inspect a locked room before the player unlocks it. Conversely,
usable ordinary controls need not wait for their analysis task to finish.
Preserve one foreground missing-control focus and its existing budget; newly
unblocked background work cannot renew it. Helpers consume frozen evidence or
use their own isolated guests and mutable files. Dot retains live input and
adopts applicable results between actions.

After rewind, retain compatible static families and source findings. Invalidate
dynamic selection, phase, pending-attempt and current-applicability bindings
from the abandoned branch. A changed source, code mapping or family assumption
also invalidates its affected dependent claims, regardless of game progression.

## Existing evidence and implementation boundary

- DotBox's [offline inspector](LEARNING_KIT.md) already supplies bounded masked
  byte search. Its [AGI census](ENGINE_AWARE_PREPARATION.md) extracts supported
  conditions, state-write sites and resource candidates broadly, preserving
  unresolved targets and coverage. These are inputs to a future family store.
- The recovered [XCOM menu-discovery note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/82#note_4184930917)
  describes a shared pattern comprising a scalar comparison, its conditional
  arm, and the first call, write or return.
  It found 481 UFO and 556 TFTD source-arm candidates. They are candidate arms,
  not button counts or complete transition semantics. The exact source-only
  add-on archive has since been recovered and its checksums verified; see
  [the corrected recovery scope](XCOM_REUSE.md). Its separate private profiles
  and raw game evidence remain outside that recovery.
  This demonstrates applying an implemented generic rule across programs;
  automatic induction of that rule from one click was not established.
- Inspected fDisBull [event-search guidance](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/skills/fdisbull-investigate/references/execution-event-search.md)
  retains site/register/value distinctions during repeated-action and contrast
  refinement. Its [serializer candidate extractor](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/serializer_candidates.py)
  uses an explicitly identified ABI to recover bounded caller candidates and
  group file bindings. This is a concrete precedent for one learned contract
  unlocking broader analysis, with unresolved control flow retained.

A useful future offline slice is a family/binding/evidence ledger accepting
existing census outputs and exposing newly satisfied task dependencies. A
generic native structural scanner and DotBox-owned live capture are separate
implementation slices. Required analysis components must eventually ship in
DotBox; the player should not need a separate analyzer installation.

Acceptance should include multiple routes to one operation, shared dispatch
with different arguments, local/context/mixed effects, deferred versus incidental
events, bulk schema facts without blanket live admission, a finding enabling
independent tasks, counterexample invalidation, stale dynamic bindings after
rewind, and bounded cyclic expansion. No such new runtime gate was executed
by this documentation change.

The [multi-probe survey](BEHAVIOR_AND_ENTRY_POINTS.md#record-transient-paths-across-controls)
adds a cheap source of observed bindings: arm several candidate sites and compare
controls from a declared baseline. Retain control-to-site/selector/target records
before complete effect interpretation. These relations can be many-to-many;
shared exits and first-hit truncation must not produce invented one-button/one-
handler mappings or negative evidence beyond the actual observation window.
