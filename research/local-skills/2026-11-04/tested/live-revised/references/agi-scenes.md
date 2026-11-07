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

### Close admission, completion and acknowledgement together

The KQ1 initial-audience bow is a worked example of a bounded accepted
interaction. `kq1-bow-intents` exports its exact-source package;
`kq1-bow-evaluate` executes named rules and bound engine requests against a
declared carrier. Neither command replaces the native scheduler or renderer.
Keep the complete census alongside it and retain other contexts as IR.

Use the following method when promoting another candidate:

1. Establish the dispatch boundary and its caller obligations before naming
   the action. Separate room entry, earlier global exits, ending phases and
   ordinary command handling. Preserve unsupported contexts explicitly.
2. Trace each state field through both writers and consumers. Distinguish
   this-visit admission from a persistent reward latch, and count carried
   objects separately from delivered objects. Give unknown fields no semantic
   name beyond what the evidence supports.
3. Recover ordered conditions and their effects. A recognized refusal can
   consume input. Preserve short-circuit `said` order, current actor geometry
   and source arithmetic; a temporary animation shift can change which refusal
   a new command receives.
4. Separate action admission, outstanding animation, completion and modal
   acknowledgement. Record when the reward occurs. Test a new command and a
   completion in the same dispatch, including a refusal that pauses before a
   second response. Restore from current state when the source does so.
5. Define named game effects in UIL and exact original operations in UDL.
   Retain scratch/implementation flags as explicit residual IR. Execute the
   UIL definition itself; listing semantic labels beside source execution does
   not show that the higher-level representation ran.
6. Compare full declared state, request order and every suspension/resumption
   against independent source execution. Cover boundaries, refusal, repeat,
   re-entry latches, score arithmetic and event ties. Authored tests and a
   source matrix do not establish normal-play reachability.
7. Qualify selected original-game observations separately. Verify raw snapshot
   identities and bit/field decoding before trusting derived values. If a
   native field is unbound, report it and test relevant alternatives; do not
   silently invent a measured value. Mark parser bridges explicitly.

Bind a modal continuation to the state the suspended interaction owns, together
with the exact model and source mapping. The original clock may continue while
a message waits: the KQ1 contract permits changes to clock variables 11–14 and
preserves their current values on acknowledgement. Other fields remain bound.
Do not generalize that exception to unqualified callbacks, timed messages or
arbitrary host state. An acknowledgement resumes the suspended dispatch before
the next cycle; it does not automatically declare the whole action finished.

Keep animation duration and presentation behavior as host obligations until
verified. Original loop/view ordering can matter even when the domain effect
is simply “finish the bow.” Sampled native frames bracket a phase transition;
they do not establish an exact cycle count. Report executed intent coverage,
source-equivalence coverage and native-observation coverage independently.

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
