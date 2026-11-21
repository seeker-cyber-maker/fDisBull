# Dot's internal game model

Decision: 18 November 2026. Dot should build, retain and revise her own internal
representation of a game. A z-scene is a bounded account of what is happening,
what exists and what actions are applicable in the current situation. It is a
projection from a larger model and current observations, not the limit of what
Dot can remember or reason about.

Status: architecture and operating guidance. The existing package implements
scene projection, provider-observation memory, immutable control records and a
bounded AGI reader. It does not yet implement the world store, rule compiler,
semantic index or automatic world-to-scene adapter described here. The `world`
guide topic makes this design available to an installed agent; it is not a new
world-query command or a gameplay qualification.

The [deterministic pseudo-oracle](PSEUDO_ORACLE.md) now implements a bounded
slice above the existing scene API: typed current-state conditions, separate
forecast sidecars and ranked provider choices. It does not implement the full
persistent graph or independently authenticate live observations.

## Three meanings of state

**The original game**
: Owns actual progression, inventory, timers, traffic and outcomes. DotBox
  observes and controls it through the supported engine and input contracts.

**Dot's internal model**
: Stores what Dot knows, suspects and has learned about entities, relationships,
  rules and past attempts. It can include source-derived future possibilities,
  guide expectations, causal models and useful abstractions. It is the record
  of Dot's understanding; it does not independently advance the player's game.

**The current z-scene**
: Selects relevant facts, happenings and possible actions for the present
  context, with observation and action identities. Its player-facing view
  respects discovery and assistance preferences. Its internal view can retain
  uncertainty and reconstruction questions without narrating them as facts.

Changing a model hypothesis is not a game-state transition. An expected effect
is not an observation. A scene's knowledge of a supported verb is not proof
that the input route is enabled and ready now.

## Start from recovered game knowledge

[DinoPark's prior research and native provider](DINOPARK_REUSE.md) are concrete
inputs to this model design. Import scoped existing entities, state meanings,
conditional rules and evidence before repeating analysis. Its recovered
transactions distinguish committed park state, working drafts, continuing
session state, interface/selection state and presentation state. Preserve
those owners and lifetimes instead of flattening them into one current value.

Retain pending actions as attempts with observed phases and confirmed effects.
Input acceptance, semantic change, usable controls, displayed content and
persistence need independent evidence; they are not a universal ordered
pipeline. A confirmed purchase with a failed display readback remains a
confirmed purchase. Reconcile that attempt rather than issue it again.
These are requirements for the proposed store/adapter, not newly implemented
world records or a ported DinoPark harness.

## A typed graph with relational storage

Use a small typed foundation that can represent many games, with SQLite as the
initial local persistence choice. Entities and relationships form a graph even
when stored in relational tables; no separate graph server is required for
this first implementation. SQLite is intended for embedded use and application
file formats [1]. This is an architectural recommendation, not a measured
performance result for DotBox's proposed model.

The foundation should preserve:

| Record | Purpose |
| --- | --- |
| Game/model identity | Resource selection and hashes, edition/interpreter profile, schema/compiler and model revision |
| Entities and aliases | Stable typed identities for places, actors, items, transitions, goals and engine symbols |
| Relations and claims | Connections, containment, dependencies, candidate meanings and their evidence or conditions |
| Rules and action models | Ordered guard expressions, possible effects, state dependencies and references to existing input routes |
| Observations and episodes | Provider-scoped state reports, selected actions, receipts and reconciled outcomes with their timeline |
| Evidence and notes | Bytecode/resource locations, guide references, experimental results and Dot's semantic explanations |
| Processes, phases and triggers | Context-bound event/clock relationships, pending operations and partial ordering needed by the current goal |
| Transition families and bindings | Shared event/guard/effect rules, concrete code/data/input bindings and separately observed occurrences |
| Alternative entry bindings | Several routes to one operation, with arguments, setup, transfer/continuation contracts, effect scope and intended use |
| Analysis dependencies | Claims and artifacts that enable further questions, with source/revision scope and invalidation links |

Keep booleans, integers, enum values, entity references and explicitly unknown
values typed. A display label is an alias, not an entity identity. Two doors
called "door" remain separate. AGI animated-object slots, inventory object
numbers, resources, variables and flags are separate domains; equal numbers
do not establish identity. Reuse of an animated-object slot also does not
establish that the same persistent object has returned.

Store core relationships explicitly, such as `located_in`, `connects_to`,
`fits`, `requires`, `reveals`, `blocks`, `reads` and `writes`. A relation can be
conditional or uncertain. Use relation types and namespaced properties/views
for extensions rather than requiring a new hard-coded game schema for each
title. Foreign keys can preserve record references [2]; they do not validate
the semantic truth of a claim.

## Dot owns the useful abstractions

### One event/state-transition foundation

Use [generic transition families](EVENT_TRANSITIONS.md) across menus, screens,
rooms, local mutations and timed effects. Clicks, keys, spatial crossings and
callbacks are event sources; their concrete input/movement bindings retain
timing and guards. Preserve context push/pop, location changes, state writes
and queued effects within that common contract.

Separate a reusable family/rule, a concrete parameterized binding and an observed
occurrence. Structural similarity, semantic interpretation, execution support
and current applicability carry independent evidence. A recovered schema can
establish many facts at once; it does not turn every candidate into an enabled
live action. A new finding can satisfy prerequisites for multiple independent
analyses without changing the player's state or reachability. Retain those
dependencies so revised evidence invalidates the affected interpretations.

Retain a [survey of observed dispatch](BEHAVIOR_AND_ENTRY_POINTS.md#record-transient-paths-across-controls)
as useful partial knowledge. Each per-control trial records its baseline/branch,
armed sites, observed hit sequence and selector/target values, ending condition
and coverage. Several controls can share a site and one control can reach many
sites. Code destinations, scene destinations and inferred semantic effects are
separate claims. Preserve recordings outside guest rewind; newly observed routes
can direct later analysis without granting callable-entry or live-action support.

### Several entry routes can realize one operation

Retain [implementation hypotheses and alternative entry bindings](BEHAVIOR_AND_ENTRY_POINTS.md)
without forcing them into a universal sequence of layers. A key and a click may
converge on a shared dispatcher, while a qualified direct call joins later and
omits interface setup. Preserve which effects are equivalent, which differences
are deliberate, and which remain unknown. A shared destination image or callee
address does not establish equivalent state, timing, files or continuation.

Keep an observation site separate from authority to invoke it. Bind a callable
route to the relevant source/mapping, arguments, context, setup and completion
or transfer contract. These records support cheaper isolated experiments while
retaining the working original route. An unknown result can still be a useful
attempt when invocation is qualified.

Constructed helper states also need provenance: which values or entry arguments
were imposed, which original initialization ran, and what was subsequently
observed. A coherent room reached by a research shortcut may be unreachable at
that point in normal story progression. Its findings can enrich the model; they
cannot assert that the player's branch has reached the room or earned its flags.

### Model how the game advances

Keep [process knowledge](BOOTSTRAP_AND_EVENT_LOOPS.md) alongside the spatial and
entity graph. Record relevant subsystem/mode, phase boundaries, accepted events,
immediate or deferred effects, clock domains, dependencies and interruption
conditions. A selected command may write a pending record that a later tick,
turn or callback consumes. Current scene facts alone cannot express that work.

Use evidence-bound partial ordering. Independent subsystems can overlap; a
held calendar does not establish a global pause; display and readiness can lag
semantic commit. Keep local mutation and navigation independent. Serialized
record order is a useful structural clue, not proof of simulation order.
Unknown trigger/ordering/clock relationships remain hypotheses.

Retain host time, guest execution and game turns/days/steps separately, including
instrumented stops and available RNG provenance. A simulation or phase prediction
can guide planning but cannot advance the player's observation store. The
[XCOM evidence](XCOM_REUSE.md) supports independent adoption/continuation/display
witnesses and [DinoPark](DINOPARK_REUSE.md) supplies concrete bounded attempts;
neither is a newly implemented general process engine in DotBox.

### Add useful concepts without changing game truth

Dot can add semantic labels, aliases, groupings, plans, inferred relations,
reusable summaries and alternative hypotheses. Examples include:

- Preparations needed before briefing.
- Objects that might open a container.
- Routes with fewer junctions.
- Interactions that may start a timer.
- Locations reachable after a particular story event.
- Unresolved connections worth checking during an already selected route.

These can be stored as authored concepts and derived views over the typed
foundation. Dot need not force each game into a fixed list of room nouns and
verbs, and she need not keep the whole model in the conversation context.
Different planning tasks may use different derived representations: a city
graph, a puzzle dependency graph, an inventory index or a compact task list.

Evidence origin and interpretation are separate fields. Record whether a claim
comes from script extraction, a guide, a runtime report or an experiment, and
whether its meaning is direct, derived, hypothesized, disputed or superseded.
Retain supporting and contradicting evidence. Confidence can prioritize an
investigation; it cannot turn a hypothesis into current state or grant input.

Record model revisions independently of observation revisions. A better name
for a room can update the model without implying that the player moved. A
revised rule can invalidate dependent plans even when the live scene revision
has not changed. Workers propose evidence-bound additions against a model
revision; the lead reconciles them coherently. Worker completion order must
not overwrite newer observations or choose a disputed claim silently.

## Retrieval: exact queries plus semantic discovery

Use exact relational indexes and graph traversal for identities, current
inventory, state predicates, dependencies and route eligibility. Use aliases
and text search for named objects, messages and notes. SQLite FTS5 supplies
full-text queries and relevance ranking when included in the packaged runtime
[3]. Check that capability rather than assuming every host build includes it.

Optional embeddings are a derived discovery index over selected descriptions,
guide summaries, rule summaries and prior experiments. Similarity indexes
return nearby vectors [4]; their ranking does not prove identity, possession,
causality, current state or action applicability.

| Question | Retrieval path |
| --- | --- |
| Is this particular door currently locked? | Exact entity and branch-scoped observation query |
| Which known conditions block this route? | Guard/dependency query over the relevant graph |
| What did we try before the previous collision? | Episode query scoped to the recorded attempt |
| Where did we see something that could open this? | Alias/text/semantic candidates, followed by exact entity and applicability checks |
| Which guide passage discusses preparing for briefing? | Text or semantic retrieval with source and edition checks |
| Which scenes depend on a changed flag? | Reverse dependency index |

Search results return record IDs and evidence, not free-floating authoritative
prose. Scope candidates by game/edition, audience and purpose before exposing
them, then resolve exact records and recheck their current applicability. A
retrieved key that resembles another key does not establish that either fits
the selected lock. Historical observations retain their branch and as-of
revision even when their wording is a strong semantic match.

Index stable, useful summaries instead of re-embedding every variable update,
coordinate sample or repeated instruction. Bind embeddings to the source text
digest, model/content revision and embedding model/version so they can be
invalidated and rebuilt. No embedding provider or library is selected by this
decision. Basic local play must work with exact queries and available text
retrieval; measure a concrete retrieval gap before adding an embedding runtime.

Keep the controller's frequently read position, motion and hazard state in a
small live working set. It should not need a vector query or a cloud-model
response on each control cycle. Persist meaningful transitions and bounded
diagnostic captures rather than treating every frame as a new semantic memory.

## Compile broadly, verify incrementally

Reverse engineering remains a permanent source of model evidence. Use the
[investigation workflow](REVERSE_ENGINEERING.md) to resolve ambiguous facts,
follow writers and consumers across scenes, and distinguish shared persistent
state from storage reused for another meaning. The model can request further
analysis when a prediction fails or a relationship remains unclear. AGI is one
provider; native/resource analysis for other engines feeds the same entity,
relationship, evidence and action contracts.

For a supported engine, run cheap deterministic extraction across the complete
selected resource set once within the declared budgets. The existing AGI reader
already scans available LOGIC resources. Reuse its full instruction data for
shared-logic summaries, conditional exits and state read/write indexes. Keep
partial coverage and unsupported encodings explicit. Do not require complete
semantic recovery before a working control can be used.

Compile conditional templates, not a separate scene for every combination of
flags. A shared helper computing a destination from the current room can be
specialized for known room candidates while retaining the original guards.
Guide comparison and Dot's interpretation can enrich those templates later.

The proposed live adapter combines a relevant part of the model with coherent
current observations, evaluates supported conditions and publishes a bounded
z-scene. Missing conditions stay unknown. A supported attempt can still be an
action when its outcome is uncertain, provided the provider qualifies that
attempt and its readiness. A draft rule or control reference alone grants
nothing.

Illustrative authored sequence, not a recovered game rule:

1. The model contains a key entity, a door entity and a conditional claim that
   the key fits that lock, with the evidence for that claim.
2. An exact live query reports whether that key is currently possessed and
   whether the door is locked. Input readiness is checked separately.
3. The scene adapter offers a qualified unlocking attempt when appropriate,
   using the existing action route and permitted discovery context.
4. Dot describes the choice in the user's preferred detail and performs only
   the selected or delegated action through the existing live controller.
5. The resulting observation establishes the actual effect. The model can
   retain the attempt and improve its rule, while the current scene changes
   only from confirmed state and refreshed admission.

The state dependency index identifies which scene views and plans need
reevaluation after a reported change, including offscreen consequences. It
does not certify that unchanged dependencies are still fresh after a gap.
Keep the existing conservative scene-revision invalidation until a narrower
provider-backed freshness contract is implemented and qualified.

## Driving, concurrent work and rewind

The same internal model can hold streets, junction approaches, stop lines,
parking areas, signal rules and traffic behavior. A graphical room may contain
several navigation nodes. The route planner queries this model; the local
controller uses fresh vehicle and hazard observations for bounded ordinary
inputs; Dot narrates and handles meaningful choices.

Predictive traffic or puzzle simulation is allowed. Record its starting state,
dependencies, assumptions and horizon. A simulated effect is a candidate
future, not an update to the authoritative observation stream. Reconcile against
the game when inputs, timing, random state or other dependencies are unknown.

While ordinary movement proceeds, available cloud workers can enrich likely
upcoming locations using frozen observations or their own isolated guests.
Their world-model proposals can remain useful even if the player changes
direction, while branch-bound observations and action admission must be
rechecked. Do not extend movement or narration to wait for optional enrichment.

Memory rewind restores the relevant emulator state and preserves current disk
files. Dot's persistent knowledge database is therefore not rolled back with
the guest. Keep static game knowledge and useful lessons; establish a new live
branch, invalidate old dynamic bindings and reobserve before further input.
An observation from an abandoned future may remain an episode explaining a
failure, but cannot become the restored branch's inventory or current signal
state. Retained knowledge still follows the player's assistance preference.
No new rewind API is implemented by this design.

## Integration with the current package

The existing responsibilities remain useful:

- `scenes.py` validates and projects bounded scene packets and returns bound
  intents. Its `requires` field checks the presence of public fact IDs; it is
  not already a general value-based rule language. `enabled` and `ready` remain
  provider assertions requiring the existing live checks before input.
- `SceneStore` stores the latest packet and last reported facts for one provider
  session branch. It is not an append-only event journal or a full world model.
- The bounded [RTS observation and primitive layer](RTS_PRIMITIVES.md) supplies
  current entities with separate faction/control/visibility, logical groups and
  observed mission events. Its projector uses the existing scene schema and
  its controller dispatches one qualified provider action at a time. It does
  not implement the broader persistent world graph or a game-specific live reader.
- `ControlStore` retains immutable control recipes; model actions reference
  those qualified revisions rather than introduce another input executor.
- `LearningStore` retains a bounded current investigation. Broad cached
  knowledge does not enlarge or reset that foreground work allowance.

Start with a separate private, versioned world store. `SceneStore` currently
validates an exact table/column layout, so silently adding graph or embedding
tables would break reopening. A later consolidation requires an explicit
migration; it is not necessary to establish this design. World storage remains
private with original resources, save evidence and raw analysis. Share only
appropriately scoped authored harness knowledge.

The first useful implementation should import deterministic draft entities,
relations and unresolved rule references; link provider observations; answer
exact neighborhood/dependency queries; and produce scene candidates for the
existing admission path. Add semantic retrieval after measuring where exact
identities, aliases and text retrieval fall short.

Acceptance should cover distinct same-name objects, typed engine identities,
unknown and contradictory evidence, stale reports, an expected effect that
cannot set live state, an abandoned-future observation after rewind, a similar
but wrong key, model-revision invalidation, and a draft action that remains
unexecutable until its provider route is qualified. Retain an existing working
control during incomplete compilation or unavailable worker/embedding usage.

## References

1. [SQLite: appropriate uses](https://www.sqlite.org/whentouse.html).
2. [SQLite: foreign-key relationships](https://www.sqlite.org/foreignkeys.html).
3. [SQLite: FTS5 full-text search](https://www.sqlite.org/fts5.html).
4. [Faiss: similarity-search definition](https://faiss.ai/). This explains the
   retrieval operation; it is not a selected DotBox dependency.

Related contracts: [state and consequences](STATEFUL_SCENES.md),
[conversation](CONVERSATIONAL_PLAY.md), [guide reconstruction](GUIDE_RECONSTRUCTION.md),
[engine preparation](ENGINE_AWARE_PREPARATION.md), [movement](NAVIGATION.md)
and [memory recovery](RECOVERY_AND_SAVES.md).
