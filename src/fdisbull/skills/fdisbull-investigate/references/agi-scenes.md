# AGI: inventory scene elements before qualifying interactions

Use this for a qualified DOS AGI 2.917 resource set, including matching original
PQ1/KQ1 editions. A title alone does not select this profile: SCI remakes, AGI3,
early KQ1 GAL/booters and platform-specific command tables need other frontends.

## Start with requirements and a denominator

Record the exact edition, resource hashes and interpreter-profile evidence.
List the required scene elements: identity, entry/phase, background, actors,
interaction conditions, state effects, output, progression, and cycle effects.
Run the installed projectless `agi-scenes` command with `--profile 2.917` and
`--stage outline`. Read coverage before inspecting individual scenes.

The census snapshots indexed resources and parses each present LOGIC, messages,
vocabulary and inventory names. Missing directories, malformed resources and
undecodable fields remain explicit. Resource enumeration, valid byte layout,
scene discovery and accepted intent have different denominators. Never call
the LOGIC count a scene count. A helper can display a background; a named
helper can also be entered as a room. Preserve both possibilities.

## Recover directly from the relevant elements

| Requirement | First useful evidence | Still needed for an executable claim |
| --- | --- | --- |
| Identity / progression | Typed `new.room` targets | Guards, room dispatch, entry/reset/abort behavior |
| Entry / phases | Initial entry and `set.scan.start` successor | Which phase applies and what state survives re-entry |
| Background / actors | Picture/view references and setup sites | Conditional composition, geometry and live actor state |
| Interactions | Ordered tests and `said` vocabulary groups | Admission, short-circuit effects and all relevant branches |
| State / output | Write sites and literal message templates | Named state meaning, ordering, substitutions and failure effects |
| Time | Motion, cycle, sound, timer and RNG sites | Engine scheduling and completion contracts |

Keep room, LOGIC, picture, view, sound, message, word-group, inventory-object,
screen-object, variable and flag identities separate. Message numbers are local
to a LOGIC. A view and an inventory object with the same integer are unrelated
without additional evidence. Vocabulary names do not define parser behavior.

## Resolve the small uncertain frontier

Use `--stage resolve` to add bounded local byte-value propagation. Read its
fixed-point and pending-work fields. A resolved reference is conditional on
reaching that source instruction under the stated profile, not proof of normal
player reachability. Keep literal references in unreachable spans as lexical
evidence, with their entry-flow classification.

The current analysis unions small finite sets at joins, retains unknown entry
values, and discards facts across calls or unmodeled effects. Unknown indirect
writes invalidate aliases. It preserves saturating increment/decrement and
wrapping byte arithmetic. Timer variables 11–14 and input variable 19 stay
volatile. A budget stop invalidates partial variable-target conclusions for the
unfinished LOGIC. It does not become success by omitting the pending work.

Treat each saved scan entry as a possible fresh invocation with unknown state;
do not reuse initialization assignments merely because they precede it in the
file. Do not reorder `said` or other tests as pure Boolean expressions. A
successful `said` changes input-acceptance state. Room change aborts active logic
execution and invokes engine transition behavior. AGI cycles are not Zork turns.

## Back one complete interaction with source semantics

Use the census to choose a bounded interaction, then retrieve `--include-ir`
and, when needed, `--include-text` privately. Bind the candidate to the exact
resource, source spans, entry, complete ordered conditions, relevant helpers,
state changes, output and cycle effects. Confirm variable meanings using both
writers and consumers. Close only the dependencies needed by the claim.

Define named intent primitives and their UDL correspondence. Execute the candidate
against an independently qualified source/runtime boundary with success,
refusal, repeat and relevant timing cases. Promote only the covered contract;
keep the remaining LOGIC operations as low-level IR. The census itself emits
zero accepted UIL interactions and has no execution capability.

This follows the existing [semantic contract](semantic-contracts.md) and
[research workflow](recovery-research.md). Full IR, names and message exports
can contain game-derived content; they are private investigation data. A
metadata-only census is not a universal publication sanitizer.

## Measure the claim you actually completed

Report resource entries, decoded LOGICs, background-producing scripts, static
room targets, unresolved references, malformed resources and accepted
interactions separately. Measure outline and resolve stages on the same exact
inputs, with timing outside the canonical result. State cold/warm conditions,
serialization and validation cost. A subsecond census does not measure analyst
discovery time or prove a speedup over complete interaction recovery.
