# Reverse engineering as an ongoing world-model capability

Decision: 18 November 2026. Reverse engineering remains available throughout
play and preparation. It resolves ambiguous facts, discovers relationships and
improves Dot's internal model. AGI is one efficient evidence provider; it does
not define the world-model schema or limit which games DotBox can investigate.

Status: this guide defines the required workflow and current implementation
gaps. It does not add a native cross-reference analyzer or a live debugger
capture API. Read [the world model](WORLD_MODEL.md) for how evidence becomes
retained knowledge and [the kit](LEARNING_KIT.md) for shipped commands.

## Ask a question that changes understanding

An investigation can support a current action, explain a discrepancy, or prepare
a likely future consumer. Examples include:

- Does this value identify the selected troop or describe every troop?
- Which later branch consumes the flag written by this switch?
- Is the displayed number authoritative, a cached copy or a derived total?
- Does this menu option change a job immediately or queue it for a later tick?
- Is an indirect pointer selecting a different entity after a menu transition?
- Is the same address being reused after an overlay or object lifetime changes?

Keep that question, the competing explanations and the evidence that would
distinguish them. A useful result is a reusable relationship with conditions and
provenance, not merely another disassembly listing or a confident label.

Use the cheapest sufficient evidence. Known engine formats, resource tables,
save contrasts, string references, native code and runtime access observations
can complement one another. An engine reader may leave ambiguities that require
native analysis even when the game's engine is otherwise supported.

Check existing recovered work before starting a new investigation. The
[DinoPark reuse map](DINOPARK_REUSE.md) identifies mechanics reports, native
state readers, qualified routes and specific remaining questions. Reuse that
knowledge with its source and edition bindings. Investigate a missing consumer,
contradictory observation or unsupported context; do not repeat settled
economics or infer live readiness from an old successful run.

## Use coding knowledge to predict the mechanism

Sketch a few plausible implementations of the observed behavior, then ask what
would distinguish them. A direct callback predicts a target per control; a
shared handler predicts a selector argument or table entry; a mode write predicts
a later dispatcher; a modal routine or tail transfer predicts a different return
or continuation boundary. Deferred work predicts a producer and later consumer.
These sketches are hypotheses, not recovered source. Refine them against traces,
callers, tables and contrasts rather than rewarding a plausible story alone.

The [entry-point guide](BEHAVIOR_AND_ENTRY_POINTS.md) connects those hypotheses
to useful operations. Several hooks can observe one effect, and several qualified
routes may invoke it with different prerequisites. An address hit establishes
neither an ABI nor a safe continuation. Recover only the setup and witnesses
needed for the selected experiment; retain the ordinary route while exploring
cheaper alternatives in an isolated guest.

## Connect investigation to the world model

1. **Identify the unresolved claim.** Bind it to the relevant entities, source
   edition, current model revision and known observation context.
2. **Collect candidates from available evidence.** Reuse cached analyses; inspect
   relevant resources, byte ranges, readers, writers and callers. Preserve
   indirect references and missing coverage.
3. **Follow the value in context.** Determine which definition can reach a
   consumer under which conditions, including intervening writes, pointer or
   record selection and different lifetimes. A textual address match is only
   a candidate cross-reference.
4. **Choose a discriminating observation or experiment.** Compare controlled
   before/after reports or capture a bounded execution/access window when the
   qualified runtime supports it. Repeated unchanged-intent observations help
   separate timers and incidental changes from the selected action.
5. **Return a structured finding.** Record the candidate meaning, raw bindings,
   relevant readers/writers, conditions, evidence, alternatives and the next
   unresolved question. Update model knowledge without applying predicted game
   effects to the observation store.
6. **Reuse and invalidate deliberately.** Cache the result with resource/profile
   and model identities. Recheck dynamic bindings after a new observation,
   entity lifetime, code mapping, restart or rewind makes them stale.

Useful model relations include `reads`, `writes`, `derived_from`, `selects`,
`affects` and `requires`. Preserve the difference between a possible static
access, an access observed in one execution, and a supported causal conclusion.
Two values changing together do not establish causality. A runtime trace proves
what happened on that path, not that every path has been covered.

## A shared variable and reused storage are different cases

**One state value used elsewhere**
: A writer in one location and a consumer in another can reveal a cross-scene
  dependency. Establish whether the consumer receives that definition, whether
  another write intervenes, and which guards apply. This can connect a switch
  to a remote exit or a resource count to an action prerequisite.

**One storage location with several meanings**
: Registers, scratch memory, unions, object slots, selected-record pointers and
  overlays can reuse storage. Equal addresses or indexes are insufficient to
  merge semantic entities.

For example, in authored pseudocode a scratch value might hold a troop ID in
one menu and a destination ID in another. That does not make the destination a
troop. Conversely, several routines reading the same persistent job field may
belong to one meaningful dependency.

Bind a native storage hypothesis to the applicable executable/resource identity,
loaded module or overlay, address space and segment/base mapping, width/bit
mask, record or object instance, program/menu context and lifetime. Retain the
session/branch and observation identity for dynamic evidence. Distinguish file
offsets from runtime addresses and symbolic field roles from their current
physical locations. Only include fields established by evidence; unknown
mapping components remain unresolved.

Graph relationships can be contextual. A mapping such as "this field is the
selected entity's job while this menu is active" is more useful and accurate
than permanently renaming one byte as a global job variable.

## Trace one selected event, then retain the useful relation

Use [bootstrap and event loops](BOOTSTRAP_AND_EVENT_LOOPS.md) for action-bound
capture and isolated state experiments. Begin from one prompt or operation:
retain its attempt, selected entity/context, applicable code mapping and clocks.
Compare repeated A with idle and a contrasting B when useful; bind bounded frames,
native state and trace/hit records to the same evidence context. Separate local
mutation, context transition and deferred work.

Reuse fDisBull's existing `event_search.py`, `execution_trace.py` and serializer
discovery as source candidates; [DinoPark](DINOPARK_REUSE.md) already brackets
known transaction boundaries and [XCOM](XCOM_REUSE.md) records generic selector
leads and original-menu experiments. Their source/backend conditions still need
DotBox integration. Real-mode trace support does not imply LE support.

A finite spread of candidate breakpoints can narrow the action's path without
recovering the whole game. Preserve argument/value distinctions when multiple
buttons share a dispatcher. A hit, a changed pixel or a staging-buffer write is
evidence at that boundary, not proof of complete causality or later adoption.
For deferred work, pursue the smallest relevant producer/consumer connection.
Record instrumentation interference and remove only the experiment's probes.
Use richer discovery captures to derive cheap qualified runtime predicates;
unknown predicates return to bounded observation without weakening the guard.

Use the [multi-probe control survey](BEHAVIOR_AND_ENTRY_POINTS.md#record-transient-paths-across-controls)
to retain transient dispatch evidence before explaining every branch. Arm the
declared candidate set, trigger one control, preserve observed site/selector/
target records, then restore a comparable isolated memory baseline and re-arm
for the next control. A cheap observed dispatch map is a useful finding even
without semantic names or a direct-call contract. First-hit stops truncate later
coverage; retain that boundary instead of interpreting missing hits as absence.
Keep recordings outside the rewound guest and preserve actual disk effects.

## Generalize the relationship and search for siblings

Use the [transition-family contract](EVENT_TRANSITIONS.md) to turn a useful
event/guard/effect finding into further work. Separate structural invariants
from selector, entity and context parameters. Enumerate compatible callers,
branch arms, script operations, registration sites or data-table entries rather
than assuming every button duplicates its code. Masked bytes, structural/data-flow
patterns and known schemas answer different questions.

Transfer established family facts under their assumptions; investigate new
bindings and material differences. Preserve site-plus-argument/context for shared
dispatch and unresolved indirect/return/queued continuations. Record scan bounds,
omissions and counterexamples. A matching instruction shape alone does not name
an action or prove an effect, while a verified schema can justify many facts
without a separate live experiment for each entry.

Index which analysis questions require each claim. A newly accepted schema or
field role can unlock parallel work on siblings and consumers. Reevaluate only
affected dependencies, deduplicate jobs and prioritize useful questions. Keep
this knowledge frontier separate from current game reachability and action admission.

## Current machinery and missing integration

The repository's [20 November capability inventory](https://github.com/seeker-cyber-maker/DotBox/blob/codex/keen-platformer-20261119/docs/REVERSING_INVENTORY.md)
audits installed tools, native primitives, experimental integration and concrete
fDisBull reuse candidates. It includes an offline scalar-search transfer trial
and separates measured candidate reduction from proposed preparation-time gains.

| Capability | Current source/package scope |
| --- | --- |
| Executable/resource identity | COM/MZ layout and hashes for explicitly selected files; not automatic complete-edition or runtime-mapping proof |
| Strings, masked search and differences | Bounded inspection of explicit files or frozen buffers through `dotbox inspect` |
| Native instruction decoding | Required iced-x86 dependency; bounded 16/32-bit linear disassembly with explicit mapping/reachability limits |
| AGI resource analysis | Supported-profile conditions, write sites, resource references and bounded local value propagation |
| Register/memory/trace/access-breakpoint primitives | Present in the bundled native source, subject to actual build and negotiated capabilities |
| General owned evidence capture/watch/trace workflow | Integration and qualification still required at the normal DotBox session interface |
| Native CFG, xrefs, definition/use chains and storage-lifetime analysis | Not provided by the current linear decoder; a separate analysis layer is required |
| General transition families and prerequisite-driven analysis expansion | Design guidance; existing masked search/AGI census provide inputs, but a family ledger and structural scanner remain implementation work |

The package must own the compatible modules and dependencies it needs. It must
not send an ordinary player to install fDisBull or another analyzer when an
ambiguity appears. Reuse appropriately scoped existing components during
development instead of requiring their source checkout at gameplay time.
Do not advertise the presence of raw native primitives as a qualified public
investigation workflow.

## Keep capture short and analysis off the play path

Cheap deterministic whole-resource scans and cached reader/writer indexes can
be prepared broadly. Semantic and runtime investigation can continue on a
bounded background frontier. The foreground missing-control allowance limits
how long research blocks the next interaction; it does not prohibit deeper
analysis on an isolated worker or during explicit preparation.

Only the live controller coordinates an investigation that affects guest
execution. A future capture operation must check current ownership, validate
the complete bounded request and retain one coherent observation context.
Capture only the selected register/memory windows, then resume a pause owned
by that operation before model reasoning or database work. Do not resume a
pre-existing breakpoint, exited guest or unknown stop automatically.

Watch/trace collection needs separate capability checks, execution/event limits,
cleanup and precise stop/ownership handling. It is not an unlimited breakpoint
that parks the player's game while Dot thinks. Workers consume frozen evidence
or investigate their own isolated guests. Controlled state changes belong in
those experiments, with their effects recorded; ordinary player actions remain
on the qualified input path.

When an existing control is sufficient, keep using it for the selected intent.
When ambiguous state really blocks the action, investigate that question or
state the actual game-facing block. Current uncertainty must not become an
invented rule just to keep a menu full.

## Next reusable implementation and acceptance

The first live integration is an ownership-aware bounded evidence capture
operation feeding the existing offline inspector and future world store.
Add access traces and native relationship analysis in independently qualified
slices. Keep their evidence/output contract engine-neutral so an AGI reader,
a native Dune binding and another engine adapter can feed the same model.

Use authored fixtures for a persistent flag with two consumers, an intervening
overwrite, two meanings sharing one byte, a pointer-selected record, overlay
reuse, a derived display value, an incidental timer change and a stale capture
after rewind. Verify that an observed access alone cannot set a semantic fact
or enable an unqualified action. Later test the useful workflow on the actual
selected game and record both discovery cost and reuse.

[Dune validation](DUNE_VALIDATION.md) defines the next non-AGI transfer target.
[Incremental play](INCREMENTAL_PLAY.md) and [stateful scenes](STATEFUL_SCENES.md)
retain the live action and observation contracts.
