# Recover scenes from their required elements

Use this procedure to recover scene definitions and progression into game-intent
UIL. Start with the facts a scene consumer needs, then find their smallest
qualified source definitions. Reuse the operation contract in
[semantic-contracts.md](semantic-contracts.md) for full interaction semantics.

This is an investigation and implementation method, not a new document format,
API, general abstract interpreter or automatic scene extractor. The Zork recipe
below describes the existing source-specific implementation; the more general
dependency-slice procedure is guidance for subsequent recovery work. Preserve
the working executable IR, earlier semantics and reference checks throughout.

## Contents

- [Define the required result](#define-the-required-result)
- [Choose the most direct evidence](#choose-the-most-direct-evidence)
- [Apply the qualified Zork recipe](#apply-the-qualified-zork-recipe)
- [Resolve values and eliminate transport](#resolve-values-and-eliminate-transport)
- [Close the semantic and residual boundary](#close-the-semantic-and-residual-boundary)
- [Make the work deterministic and reusable](#make-the-work-deterministic-and-reusable)
- [Validate accuracy before comparing cost](#validate-accuracy-before-comparing-cost)
- [Hand off the next recovery step](#hand-off-the-next-recovery-step)

## Define the required result

For exploratory work, start with the next useful scene fact or action; its
contract can grow as facts arrive. Before accepting an executable replacement,
write the bounded contract its consumer needs. A scene is a context for
entities, actions, conditions and effects; it need not be a screenshot or one
routine. Different scenes can share a handler, and one scene can use several.
Require the following elements when they matter to the requested consumer:

| Required element | First source to inspect | Obligation before acceptance |
| --- | --- | --- |
| Identity and membership | Object/resource catalogue, parent relationship, entry references and graph | Stable identity distinct from display text; compatible context and edition. |
| Description and presentation | Resource references, text decoder and description callback | Actual resource and dependencies; trigger, fallback/suppression and output order. |
| Entities and affordances | Object records, containment, grammar and callback associations | Correct target/context; distinguish present, visible, reachable, enabled and unknown. |
| Entry and action binding | Scene/verb tables and the operation that consumes them | Named entry/handler plus precedence and input roles; a resolved link is not a recovered body. |
| Transition and destination | Exit/portal record and its selector | Named destination or explicit residual; no invented target for an indirect unresolved exit. |
| Conditions | Guard reads, field definitions and relevant writers | Exact predicate over live typed state; initial values are not permanent conditions. |
| State changes | Writes, containment operations and relevant helper contracts | Ordered effects and ownership; destination selection and committed relocation are distinct. |
| Refusal, repeat and failure | Alternative branches and return consumers | Applicable output, side effects, result and continuation on each covered branch. |
| Turns, events and RNG | Action completion, scheduler and random-call boundaries | Whether, when and how often these effects occur, including failed actions. |
| Suspension and persistence | Nested input, save/checkpoint and residual joins | Required live state, resume behavior and partial effects; no lost continuation. |

For that acceptance contract, create one obligation per required field or behavior, not one task per source
instruction. Record: stable obligation ID; candidate value/rule; evidence and
dependencies; alternatives; result status; cheapest next discriminator; stopping
condition. Use private notes or existing evidence fields, not invented runtime
keys. Mark irrelevant requirements explicitly outside scope.

Track definition recovery, handler meaning, execution observation and ordinary
reachability separately. A complete inventory can contain residual handlers;
it is not a complete semantic reconstruction. A field can be statically supported
without having been exercised in play. Missing, absent, false and not-yet-read
are different results.

## Choose the most direct evidence

Choose the cheapest available method that can settle the next question. The
methods below are alternatives, not a mandatory order: a quick runtime
observation need not wait for parsing, slicing or constraint solving. Reuse a
settled result; retain a contradiction instead of resolving it by priority.

| Option | Method | Stop or escalate when |
| --- | --- | --- |
| 1 | Reuse an exact-version definition with its source witnesses and current dependency checks. | Its assumptions or dependencies changed, or it does not cover the requirement. |
| 2 | Parse a bounded object, scene, grammar, resource or transition table using a qualified layout. | Bounds, reference type, default semantics or layout interpretation remain unqualified. |
| 3 | Inspect the small consumer of that record; establish its branch/effect convention once and apply it to compatible records. | Record data alone cannot establish guard polarity, ordering or side effects. |
| 4 | Follow a backward definition/use slice from the unresolved selector, guard, effect or return; summarize pure helpers. | Aliasing, a join, an unknown call or a mutable dependency prevents a sound expression. |
| 5 | Run a bounded abstract evaluation or constraint check over that slice. | The declared domain/budget is exhausted or a relevant effect is unmodeled. |
| 6 | Restore a qualified state and take one targeted observation that distinguishes the remaining alternatives. | The observation cannot establish the wider rule; retain its path-specific scope. |

Use strings, guides and related source editions to locate candidates and suggest
labels. Retain useful guesses explicitly; check selected-source interpretation
when using it as operational meaning. Do not begin
with exhaustive control-flow recovery, a whole-game walkthrough, or every caller
of a shared interpreter when a table and its consumer answer the question.
Conversely, a promising table is insufficient without its interpretation.

Start from known effect sinks when records are absent: actor relocation,
inventory transfer, flag writes, resource emission, scheduled events or action
completion. Work backward through the control and data dependencies that can
change those effects. Keep an unknown relevant helper in the obligation; a short
slice that omits it is not an accurate slice.

To name an unfamiliar state write, inspect its smallest relevant consumer as
well as its writer. In the kitchen-window follow-up, an unconditional flag write
alone did not establish intent. The nearby examination branch showed that the
flag dismisses an initial hint, separately from the door's open state. Recover
that bounded meaning; keep the rest of the examination action residual. If no
consumer establishes meaning, retain the write as an explicit low-level effect.

## Apply the qualified Zork recipe

Check `fdisbull --help` and `fdisbull zork-scenes --help` for CLI commands and
options; `fdisbull methods` lists the separate JSON method surface. The current `zork-scenes`
producer supports Zork I R88, serial `840726`, qualified by the exact source
hash in `zork_scenes.py`/`zork_intents.py`. It accepts or builds the existing
intent package and retains its complete executable IR. This method changes
investigative order; it does not make the existing runnable exporter independent
of that base package. Reuse a supplied, verified intent package through
`--intents` instead of rebuilding it for each scene question.

### Parse definitions once

1. Qualify story version, full-file identity and declared extent. Keep padding
   identity distinct from executable memory. Read the object, global,
   dictionary and abbreviation roots from the header and validate their bounds.
2. Parse the object records and each descending property list once. Validate
   short-name extent, record bounds, property sizes/numbers and termination.
   The v3 object count is not stored in the header: the current exact-edition
   profile supplies it. Do not extend the catalogue by decoding arbitrary bytes.
3. Identify room membership and build a graph labelled by direction, exit kind
   and destination. Associate source-language symbols by compatible graph
   constraints and one-to-one identity. Require a unique solution before
   assigning those names. Identical displayed names and numeric profile hints
   do not choose a solution. For an ambiguous new target, retain distinct opaque
   source-linked identities and the candidate associations, or refuse a profile
   that requires unique names; never select the first candidate.
4. Bind the directional-record interpretation to this edition's V-WALK
   selector. Then parse every compatible exit without executing a route through
   it. Keep unsupported sizes, padding or targets unqualified.

The existing R88 selector establishes these payload conventions. These are
game/compiler conventions, not generic Z-machine property semantics. `D` is a
destination object, `F` a live global-variable selector, `O` a door object, and
`P` a big-endian packed reference. The size is payload bytes, not the header:

| Size | Payload | Recovered definition |
| --- | --- | --- |
| 1 | `D` | Direct request to the named destination. |
| 2 | `P:text` | Bound refusal text followed by the source newline behavior. |
| 3 | `P:routine, 0` | Named residual exit handler; destination/effects remain unresolved. |
| 4 | `D, F, P:text-or-zero` | Live nonzero condition selects travel; false selects custom/default refusal. |
| 5 | `D, O, P:text-or-zero, 0` | Live door-open predicate selects travel; closed selects custom/default refusal. |

Keep missing direction properties on their own residual path. They are not
equivalent to the explicit two-byte blocked record: darkness and other behavior
can matter. A missing callback property can use a property default, whereas
V-WALK's missing property-address path has different semantics. Establish the
consumer before substituting any default.

### Resolve references by role

Resolve v3 packed routine references to the routine header and then skip its
local-count byte and initial-local words to find the instruction entry. Validate
both extents and retain initial locals and argument/result conventions in UDL.
Do not decode the routine header as an instruction. Packed zero at a call is a
defined no-call/zero-result case, not a routine at address zero. A packed text
reference has a different role: resolve and decode it as text, including its
abbreviation dependencies. The same integer type does not make the two roles
interchangeable.
In the window case, a packed text value numerically coincided with an instruction
address. Its consuming operation established the text role. Membership in a code
address index cannot decide how a value is interpreted.

The applicable VM rules are specified in the Z-machine standard's
[memory map](https://inform-fiction.org/zmachine/standards/z1point1/sect01.html),
[instruction operands](https://inform-fiction.org/zmachine/standards/z1point1/sect04.html),
[state and calls](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html)
and [object table](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html).
Qualify the game-specific meaning against the actual source operations.

Read action/preaction tables and grammar associations directly. Index object
callback properties, defaults and qualified setter alternatives. Resolve finite
handler identities once, retaining live semantic selection between them. Do
not freeze the current action, room, door, flag or callback pointer merely
because one execution or the initial image supplied a concrete value.

The current dispatch producer recognizes qualified adjacent
`get_prop`/`loadw -> stack target -> call` chains, with a bounded optional
parent lookup. It is not a general interprocedural value resolver. Preserve
actual argument consumption, result storage and return continuation while
removing only admitted target transport. A gap containing an unexplained call
or write is not covered by this existing optimization.

Treat static description resources as available content, not unconditional
narration. In R88 a room callback can handle presentation before its static
fallback. Keep condition setters, parser filters, first-handled stage control,
room/routine bodies and arrival/scheduler behavior residual until their own
effects are qualified. The scene definition can be useful before these bodies
are understood.

Use these source seams without re-discovering the dispatcher:

| Obligation | Existing implementation seam |
| --- | --- |
| Records, graph identity and five exit forms | `zork_scenes._objects`, `_associate_scenes`, `_lower_exit` |
| Live field bindings, resources and primitive witnesses | `zork_scenes._documents`, `_Evidence.text_dependencies` |
| Grammar, callback alternatives and target transport | `zork_scene_dispatch._grammar`, `_pseudo_definitions`, `_dispatch_sites`, `recover_dispatch` |
| Address-free exit selection and relocation plan | `player/fdisbull_player/scene_intents.py` |
| Independent binding checks and residual compatibility | `scene_bindings.py`, `scene_runtime.py` in the same player package |
| Window open/close effects from the resolved callback and small helpers | `zork_window.recover_window` |
| Address-free door effects and independently checked source correspondence | `door_intents.py`, `door_bindings.py` in the player package |

Consult source-checkout `docs/ZORK_SCENES.md` for the executable formats and
`docs/VERIFICATION-ZORK-SCENES-2026-10-30.md` for prior evidence and its limits.

## Resolve values and eliminate transport

For a new unresolved source slice, use typed symbolic values rather than a
recording of one concrete stack. A compact analysis can distinguish:

| Value class | Meaning and treatment |
| --- | --- |
| Constant | Exact value with width, signedness and provenance; fold pure operations with the source's overflow rules. |
| Source reference | Typed object, table, resource or routine reference; resolve by the qualified format and keep its source identity in UDL. |
| Live semantic value | Named field or action input; retain it as a UIL input/predicate instead of replacing it with its initial value. |
| Guarded finite alternatives | Preserve the predicates relating alternatives to current state; select a named target at execution. |
| Unknown | Keep the unresolved expression/effect as residual, with the dependency or budget that prevented resolution. |

Maintain a separate not-yet-visited state for the worklist; it is not a known
zero, an absent effect or an unreachable branch. At a control-flow join, keep
equal typed values, otherwise retain a guarded choice when its predicate is
known. A bare set of possible targets does not establish which target to call.
If paths disagree on stack shape, effects or a relevant alias, keep that
boundary unresolved unless a supported path-sensitive analysis settles it.

Apply the following bounded procedure; the names are pseudocode, not APIs:

```text
freeze source, format/profile, requested elements and deterministic budgets
index the validated definitions and their dependency identities
queue unresolved obligations in a stable dependency order
for each obligation:
    reuse a still-qualified definition, or read its direct record
    if a semantic value is unresolved:
        slice backward from its use through relevant data and control edges
        evaluate pure definitions with typed values and guarded joins
        retain live state reads; stop at unmodeled effects or budget frontiers
    emit supported semantic fields and explicit residual dependencies
    attach witnesses, mutation assumptions and residual-join obligations
    validate the claim at its declared boundary
stop when each requested obligation is closed or explicitly unresolved
```

Preserve operand evaluation order. In Z-machine instructions, operands are
evaluated left to right; ordinary variable-zero reads pop and stores push.
Indirect variable-reference operations have different stack behavior. Model
that distinction rather than replacing every zero with a generic pop. A call
target and its real arguments can consume different stack entries. When a
resolved target is removed from the sequence, preserve argument consumption,
default locals, null-call behavior, result placement and continuation.

Treat memory reads as constants only with a valid immutability argument or an
explicit live guard over their complete dependencies. Object property tables
are mutable in the VM; a fixed address is not proof of fixed content. Check
relevant direct and aliased writers. An unknown call can invalidate knowledge
of any state it may modify. Absence of a discovered writer is not a proof that
none exists. Retain a live read or a residual boundary when that proof is absent.

Preserve correlations: if a guard selects both a target and its argument, keep
them together. Do not form an arbitrary cross-product of finite value sets.
Check value types as part of source correspondence. Host-language equality can
equate a Boolean with an integer even when the executable operation accepts only
the integer. A type-erasing comparison is not an equivalence check.
Use fixed worklist order, bounded alternatives and explicit widening to unknown
for loops; record the unresolved frontier. Never turn a timeout or an unseen
path into a constant result.

After proving that a stack shuffle, pointer calculation, table lookup or dispatch
loop only selects a known semantic object, remove it from the UIL execution
path. Express `travel to destination when condition`, `emit resource`, or
`invoke selected residual handler` directly. Do not retain a computed PC under
a more attractive field name. Keep the source mechanism in UDL evidence and
any required residual adapter, not in the recovered scene rule.

## Close the semantic and residual boundary

For each admitted primitive, bind its domain, typed inputs, guards, ordered
effects, refusal/return behavior and source operations. Include read/write,
resource, callback, time/RNG and continuation dependencies where relevant.
Identify exactly where residual execution begins and resumes, and which values
that residual execution can read or save. Hash agreement binds evidence to a
source; it does not establish that a proposed interpretation is correct.

Selection is a decision, not automatically a state change. R88's
`scene.select_exit` requests travel or produces ordered refusal effects;
`scene.move_actor` covers qualified actor containment and current-scene updates.
Admission, lighting, hazards, scoring, callbacks and turn completion have their
own boundaries. Do not attach a generic one-turn cost to every scene primitive.

Preserve side effects hidden in presentation helpers. The current default
closed-door refusal also changes discourse referents; its custom-text branch
does not imply the same writes. Text output may target memory and alias
resources, so cached prose alone cannot authorize replacing every print path.
Record effect order and retain unsupported output-stream behavior as residual.

Presentation can also own RNG and shared mutable state. Window repeat feedback
uses a live shuffled bag: preserve the draw even when its range is one, both
swap writes even when they address the same slot, immediate cursor wrap, and
then output. Sampling without replacement applies within a cycle; it does not
exclude equal responses across the cycle boundary. If residual callers share
the bag, project and update that shared state rather than copying its initial
order into private state. The same interaction emits its success message before
changing the door state and its newline afterwards. A familiar helper name or
plausible final transcript does not establish these effects.

At a mixed semantic/IR join, compute the required live-out state: real arguments,
return destination/value, frame locals, object links, pending work and any
checkpoint-visible state. Existing Zork evidence includes a nested-input case
where prose and game memory agreed but suspended caller locals differed.
Materialize already-resolved compatibility values at that join; this does not
require rerunning the eliminated selector. Remove such adapter state only after
its residual consumers and checkpoint requirements have also been replaced or
explicitly migrated. Do not weaken snapshot comparison to hide a mismatch.

If a semantic realization fails after mutation, preserve completed effects and
mark interrupted effects unknown. Never replay the original block as fallback
after partial effects. A preflight failure can choose a residual path only
before any effect, with that choice recorded.

## Make the work deterministic and reusable

Freeze source hash, address space/byte version, format/profile revision,
decoder/rule revision, requested scope, observation policy and budgets. Specify
stable ordering for obligations, graph constraints, source records and output.
Prefer count budgets for reproducible analysis frontiers; a host deadline is a
safety bound and may stop at a different frontier. Report it honestly.

Keep three caches distinct:

1. **Definition cache:** parsed tables, typed references, decoded resources and
   source correspondence, keyed by source/profile/decoder identities and all
   transitive dependencies. Share repeated abbreviation and routine-header work.
2. **Semantic summary cache:** proven pure helper or primitive contracts, keyed
   by source dependencies, admitted input domain, effects and residual boundary.
   A summary for one role/domain does not qualify every caller.
3. **Observation cache:** path-specific runtime evidence with run/load identity,
   state version, input, policy and boundary. Historical evidence never supplies
   fresh live state or current readiness.

Parse common structures once; batch dependent reads in one qualified snapshot
when possible. Recompute only descendants of changed dependencies while keeping
the mandatory source and live-binding checks. Reuse a validated result within
one immutable phase only when the validation contract permits it. Deduplication
must not remove an independent consumer-side check or a mutation boundary.

Schedule independent resource parsing or distinct handler obligations in
parallel after shared identities are fixed. Give one owner to a live guest,
schema, or write surface. Queue ready obligations by a declared priority,
dependency depth and stable ID; include the priority policy in a comparison.
Do not parallelize two probes whose result changes the other's assumptions.

Record parse/slice/validation/export time, source bytes or instructions actually
examined, probes, repeated work and aggregate worker effort. Stop escalating a
field once its evidence obligation is met. If blocked, retain the smallest
unresolved dependency and its next discriminator. Closing every requested row
as supported, contradicted, outside scope or explicitly unresolved is a complete
method pass; unresolved material rows still prevent a complete recovery claim.

Keep the cost denominator explicit. The window replacement covers 39 instructions
across 157 bytes including routine headers, reusing prior scene, dispatch and IR
definitions. Its hint consumer and resource/table dependencies require additional
checks. This is a bounded additional slice, not a whole-game analysis budget,
cold-discovery measurement or demonstrated speedup.

## Validate accuracy before comparing cost

This section evaluates executable substitutions or a recovery method's claimed
coverage. Select the cases needed for that claim; it is not the admission cost
of a useful label, positive pickup observation or initial text harness.

Validate structure and meaning separately. Check record extents, typed references
and unique associations; then check selector polarity, effect ordering and
residual boundaries against source operations. Use an independent consumer-side
binding check where available. A generated digest or tests derived solely from
the proposed UIL cannot independently prove fidelity.

For a new executable primitive, select representative and discriminating cases:
success, refusal, repeat, each relevant live-condition value, unknown input,
changed binding, custom/default output, missing direction, residual callback,
and any applicable interruption/resume boundary. Choose combinations that test
actual interacting guards; isolated Boolean rows are not full path coverage.
Diagnostic state injection can test a rule's truth table, not player reachability.

Run one complete interaction through the higher-level evaluator and existing
reference at matching boundaries. Compare required state, ordered output/effects,
turns, RNG and save/resume state. Instrument which semantic primitives ran and
which selector operations were skipped; a fallback-only pass proves no semantic
substitution. Keep a deliberately failing old-selector trap or equivalent
execution witness when it can distinguish the two paths. Broaden execution
only for a remaining risk or required gate. A skill-only edit needs skill delivery
and method-use checks, not an automatic full-game replay.

When evaluating a substantial method revision, forward-test on frozen raw cases.
Give fresh agents the task,
relevant guide, permitted source/profile evidence and budgets. Withhold recovered
UIL, expected assertions, previous answers and the hidden oracle. Include a
duplicate-label graph, mutable selector, unknown writer, stack-argument case,
misleading layout and suspended continuation. Include solvable cases so that
marking everything unknown cannot pass. Evaluate what the agent actually derives
and the evidence it cites, not whether it repeats the checklist.

Report exact supported requirements and total requirements, false accepted
claims, missing supported fields, preserved unresolved obligations, effect-order
errors and relevant branch coverage. Score names/entries separately from recovered
effects. Compare cost only at matched scope, accuracy, prior information and
evidence obligations. A deterministic parser can produce identical artifacts;
an agent following instructions has empirical repeatability, not guaranteed
deterministic reasoning. A warm export is not cold discovery. Use the matched
comparison guidance in [recovery-research.md](recovery-research.md).

## Hand off the next recovery step

Deliver the compact requirement/evidence ledger, recovered scene rules, UDL
bindings, explicit residual inventory, decisive counterexamples and measured
costs. Keep game bytes, prose and checkpoints private. For an unresolved handler,
start the next pass from its already-resolved identity and the missing semantic
obligation; do not rediscover its stack-carried target or surrounding dispatcher.

State which steps were executed, which are proposed improvements, and what
would reopen a settled definition. Use the supported export and partial-effect
contracts in [udl-uil-udc.md](udl-uil-udc.md) when producing a runnable package.
