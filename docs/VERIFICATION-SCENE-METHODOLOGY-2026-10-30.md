# Scene recovery methodology, 2026-10-30

## Outcome and scope

The bundled `fdisbull-investigate` skill now gives a concrete method for
recovering scenes from their required elements. It directs an investigator to
qualified scene/object/resource tables first, then to the smallest source slice
or observation needed for a missing requirement. The intended output is named
game rules with source-bound UDL and explicit residual behavior.

The method is available through the installed CLI:

```sh
fdisbull agent-skill --reference references/scene-recovery.md
```

This is a methodology and skill-delivery change. It does not implement a new
general data-flow engine, an incremental cache, another Zork conversion or a
scene-only replacement for the existing runnable package. The supported Zork
producer still accepts or builds and validates the preserved intent/IR package.
Its earlier playable conversion, semantic consumers and reference checks remain
unchanged.

The exact pre-change source tree is the scene PR head
`91308535d9967c1e277a1272fd7b0c49b20a6897`; the equivalent local reconstruction
is `fc673720850407cfd3cfda902f65e1ef74aa2ff9`, with tree
`4963b277ed75d34c92a4cee746e188b23b2424a3`. Prior full-route and native evidence
is recorded separately in [Zork scene verification](VERIFICATION-ZORK-SCENES-2026-10-30.md).
Those earlier execution results are not new gameplay from this pass.

## Why the investigation order changes

The existing skill already required complete operation contracts, explicit
unknowns and bounded evidence. It lacked a direct route from each required scene
element to the source structure most likely to define it. Its command routing
also stopped at the older Zork IR and mailbox-intent layers.

In the current Zork implementation, much of the required scene information is
already expressed as data. The source consumers establish how to interpret those
records. Recovering the same information by playing every exit or tracing the
entire dispatcher repeats work without adding evidence for those definitions.

| Scene requirement | Direct recovery method | Separate obligation |
| --- | --- | --- |
| Identity | Object membership plus direction/kind/destination graph constraints | Unique naming; display titles can collide. |
| Exit and target | Qualified directional property record | Reachability, admission and arrival behavior. |
| Condition | Typed live global or door-attribute binding | Setter semantics and interacting conditions. |
| Description/refusal | Resource reference and complete text dependencies | Callback suppression, output ordering and presentation side effects. |
| Action/handler entry | Grammar, action/preaction tables, callback properties and setter alternatives | Parser filters, stage reachability and handler-body effects. |
| Committed movement | The admitted actor-containment/current-scene effect boundary | Hazards, scoring, events, narration and turn completion. |
| Suspension/resume | Residual call and checkpoint-visible live state | Matching the full continuation, not only visible output. |

These mappings are grounded in `zork_scenes._objects`, `_associate_scenes`,
`_lower_exit`, `_documents`, and the table/grammar/dispatch functions in
`zork_scene_dispatch.py`. The independent `scene_bindings.py` validator and
`scene_runtime.py` adapter retain their existing qualification boundaries.
See [the scene format and implementation contract](ZORK_SCENES.md).

## The deterministic procedure

1. **Declare the scene requirements.** Create an obligation for each required
   identity, resource, affordance, guard, transition, effect and temporal or
   persistence behavior. Keep structure, recovered meaning, runtime observation
   and ordinary reachability on separate axes.
2. **Reuse qualified definitions.** Pin source, profile, decoder and dependency
   identities. Reuse settled bindings after their required checks rather than
   rediscovering them from an execution trace.
3. **Parse direct structures once.** Bound object/property/resource tables and
   qualify their consumer's interpretation. Apply a known convention to all
   compatible records, keeping unsupported forms explicit.
4. **Resolve the missing values.** Follow definitions and controlling conditions
   backward from an unresolved selector or effect. Distinguish constants, typed
   references, live semantic inputs, guarded alternatives and unknowns. Retain
   alias/write and effect barriers.
5. **Remove proven transport.** Replace qualified address arithmetic and
   temporary stack carriers with named destinations, predicates or residual
   handler selection. Keep actual arguments, ordered effects and required
   residual-join state.
6. **Validate at the required boundary.** Check source correspondence, branch
   cases and applicable interaction/resume behavior. Record unresolved
   dependencies instead of defaulting them to false, absent or harmless.

Fixed traversal order, typed rules, dependency identities, canonical output and
count budgets make an implemented parsing pass reproducible. A host deadline
can still produce a different unfinished frontier. An agent applying prose
instructions has empirical repeatability, not guaranteed deterministic reasoning.

The guide specifies three separate caches as a future implementation strategy:
parsed definitions, qualified semantic summaries and path-specific observations.
It requires dependency invalidation and current live-state checks. These caches
are not new features of the current exporter.

## Accuracy constraints that affect speed

The most useful shortcut is to qualify a shared record convention once and
reuse it. The most dangerous shortcut is to treat a value observed once as a
constant. The method makes that distinction explicit.

- A mutable flag remains a live predicate even when its initial value is zero.
- A finite set of targets needs its selecting predicates; an unordered set is
  insufficient to choose a target at execution.
- A routine identity can be recovered while its body remains residual.
- A missing direction does not inherit the behavior of an explicit blocked exit.
- A static description can be a fallback after a callback handles presentation.
- A chosen destination is a travel request until the movement boundary commits.
- Stack-target elimination must preserve real argument order and consumption,
  null-call behavior, result placement and continuation.
- An unknown writer invalidates a constant-table assumption unless a qualified
  guard or writer analysis restores it.
- Saved caller locals can matter even when narration and world memory match.
- After a partial effect, falling back to the original block can duplicate work;
  retain the completed/unknown effect record instead.

The Z-machine standard independently specifies
[operand evaluation order](https://inform-fiction.org/zmachine/standards/z1point1/sect04.html),
[stack and call behavior](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html),
and [mutable object/property tables](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html).
The five Zork exit layouts and their effects are game-specific conventions
qualified against the selected binary; the VM standard does not supply them.

## Descriptive warm measurements

Three instrumented calls to the existing
`recover_scenes(story, base_intents=existing)` used the already qualified R88
story and intent package. Fresh intent recovery and whole-story conversion were
trapped. No native game was launched, no gameplay route was run, and no generated
game package was written. All current producer checks remained enabled.

| Measurement | Median | Observed range or sample scope |
| --- | ---: | --- |
| Complete warm recovery call | 13.04 s | 11.96–16.14 s; three samples |
| Scene document production | 0.133 s | 0.121–0.648 s; inclusive stage |
| Dispatch recovery | 0.163 s | 0.155–2.636 s; inclusive stage |
| Seeded dispatch traversal | 0.137 s | 0.109–2.604 s; included in dispatch recovery |
| Scene object decoding | 0.0054 s | 0.0041–0.575 s; included in scene production |
| Scene graph association | 0.0031 s | 0.0024–0.0036 s; included in scene production |
| Independent player binding validation | — | One additional static sample: 3.37 s |
| Separate copy of the preserved base package | — | One separate-process sample: 4.48 s |

Every recovery produced canonical package digest
`43e8b845cdce96aea441bb5d273a7a898829d6e9bc1f271e41b10ba705ce108d`,
and the supplied base intent package remained unchanged. The recovered inventory
was still 110 scenes and 352 exits. Dispatch traversal visited 6,013 instruction
rows from 292 roots; its scope still explicitly leaves runtime targets unproven.

The dependable conclusion is that scene definition and dispatch production
occupied a minority of total elapsed time in each measured call. A future
performance pass should first separate repeated validation, serialization,
copying and ownership costs. These measurements do not authorize removing an
integrity check, changing mutation isolation or treating a cache hit as fresh
runtime evidence.

The timers are nested, so their rows must not be added indiscriminately. The
separate copy timing is not an exact attribution of total recovery cost. The
host was shared with other agent work and several stage times varied sharply.
Imports, compressed-intent loading, prior source research, naming-profile
construction and earlier verification are outside the warm total. No speedup,
cold-discovery time or statistically controlled performance result is claimed.

## Skill and source verification

The changes add one selectively readable reference and concise routes from the
entry skill, scene, semantics, research, workflow and UDL guides. The CLI index,
quickstart, distribution inventory and exact resource fixtures include it.
An existing missing-resource test now rejects a package that omits this guide.

The focused discovery, skill-gate, output and distribution checks passed:
**91 passed**. The first run had 86 passes and five failures because the default
temporary location was under a Git marker and correctly triggered the existing
private-output guard. The unchanged tests passed with a qualified temporary
directory. Both outcomes were retained; no runtime guard was relaxed.

After the CLI-discovery wording correction and evidence integration, a fresh
coordinator run passed **82 checks** covering discovery, skill resources,
distribution and the two projectless bundle tests. The nine output tests had
passed in the earlier qualified-temporary-directory run and were unchanged.

An independently built wheel passed the installed skill gate: **11 resources,
36 local links**, read through isolated CLI subprocesses. The guide resources
were byte-identical to the working source. The wheel passed the tool-only
distribution check with **168 entries**.

A fresh source comparison confirmed **45 protected producer, processor, player
and game-test files unchanged**. The only modified runtime Python module is
`cli.py`; its AST is identical to the prior source after excluding the skill
catalogue assignment. The only added behavior is discovery/delivery of the new
instructions. No full game replay was necessary for this skill-only change.

## Applying the method to raw cases

Two fresh top-level agents received only the frozen revised guide and the same
five [authored cases](evidence/scene-methodology-2026-10-30/authored-cases.json).
They had no expected answers, implementation tests, recovered game package or
prior analysis. One agent requested an additional independent reasoning review
of its stack and suspension cases using the same raw evidence.

The cases supplied small records, consumer operations and observations:

| Case | Required distinctions |
| --- | --- |
| A: scene records | Four exit forms, a changing nonzero guard, a door, ordered refusal effects, routine header/entry/default locals, and unresolved travel/turn semantics. |
| B: dispatch | Live table selection, exact real-argument order, an unknown callback-table writer, and a zero-target call that still consumes an argument and stores zero. |
| C: graph identity | A uniquely recoverable graph with wrong numeric hints, plus a symmetric graph that must retain both naming alternatives under record reordering. |
| D: continuation | Callback-controlled narration, checkpoint-visible caller locals, missing temporal evidence and a fault after the first effect committed. |
| E: negative evidence | Nonzero padding, truncation, null text reference, a single missing-direction observation and a conflicting sibling-edition predicate. |

Before the agents started, 29 required decisions were fixed. The coordinator
manually checked each complete result: **29/29 supported in each application**,
with **zero false acceptances among those scored requirements**. Both agents
recovered the solvable records and the unique graph; neither gained a passing
result by leaving everything unknown. They also preserved the symmetric naming
ambiguity, unknown callback mutation, missing handler effects and the observed
suspended-state incompatibility.

The [complete applications](evidence/scene-methodology-2026-10-30/applications.json)
and [verification receipt](evidence/scene-methodology-2026-10-30/verification.json)
retain the evidence, rubric, source hashes, measured stages and limitations.
All **79 evidence selectors** in the two applications were resolved against the
authored input, and every cited local evidence ID resolved. The tool source
archive includes the three exact evidence files and passed its distribution gate.
The receipt records a failed pre-write command and authorized corrective write
in one application, as well as the other application's extra reviewer. These
were not equal-cost experimental arms.

This is a bounded method-use check. The fixtures supply qualified format and
consumer evidence; they do not test cold discovery of an unknown VM or edition.
There was no original-skill comparison arm, no gameplay, and no measured agent
wall-time/token budget. Agreement on the scored semantic decisions demonstrates
usable guidance on these cases, not universal accuracy or a discovery-speed gain.
The two prose/JSON outputs also differ; only the required semantic decisions
were compared. Create fresh cases before making a future holdout claim using
this now-published material.

## Next implementation priorities

Use the method on the next named residual interaction, beginning with its missing
guards and effects. Preserve its already-resolved handler identity and source
calling contract. Do not reconstruct the surrounding dispatcher again.

For a later processor improvement, implement the smallest typed value resolver
that closes a real unresolved obligation, with explicit joins, aliases and
effect barriers. Use an unresolved or contradictory case as its regression.
Only expand to a general slice engine when repeated cases justify that work.

For a later export-speed improvement, establish a controlled baseline and a safe
immutable ownership/validation contract before attempting copy or cache changes.
Measure equal accepted scope, not only fewer decoded instructions or a smaller
output. Keep the current conversion and its independent checks as the reference.
