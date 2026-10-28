# Draft amendment: practical contracts from game recovery

Status: **draft design**, 28 October 2026. Author: **Codex**, acting as the
DinoPark recovery investigator at the user's request. This supplements the
[intent pipeline RFC](INTENT_PIPELINE_RFC.md) proposed in
[PR #13](https://github.com/seeker-cyber-maker/fDisBull/pull/13).

The parent RFC already requires typed effects, explicit timing, uncertainty,
bounded comparisons and separation of simulation from drawing. This amendment
turns those requirements into distinctions that a first evaluator can test.
It proposes no canonical encoding, reserved capability identifier, implemented
exporter or release commitment. Any eventual language change follows the
[UIL RFC process](UIL_RFC_PROCESS.md); the existing
[producer/consumer boundary](UIL_BOUNDARY.md) continues to apply.

## Evidence and attribution

The author inspected the DinoPark E55 report, game-story map, ABOUT host
contract and bounded-comparison summaries, including their retained earlier
mechanics evidence. That research corpus is outside this repository. The
following are attributed findings within those recorded bounds, not publicly
reproduced native-game claims supplied by this amendment:

| Research observation | Scope and design consequence |
| --- | --- |
| ABOUT initialization assigns the word value 1 to a shared signal. Repeated assignments during an active sequence can coalesce before the actor clears it. | Qualified host routines and a joined host/actor fixture motivate distinguishing stored signal state from queued work. Full page services and physical input timing remain outside that comparison. |
| A purchase can reserve money and post an expense before arrival and placement; cancellation after a month change can reverse the expense in the current month. | The retained transaction evidence motivates explicit intermediate states and cancellation effects. It does not establish every item, date or interruption. |
| Ordinary park loading preserves some live session state while restoring other fields and later reconstructing the scene. | The qualified load boundary motivates separate game-load and analysis-checkpoint contracts. Neither is an implicit reset of all external effects. |
| Interface acceptance, state changes, usable controls, displayed content and file persistence can occur at different boundaries. | The recorded interface and persistence routes motivate separate observations; they do not define one universal completion order. |
| Frame-list interpretation can depend on a neighboring actor record; money calculations can differ when rounding order changes. | Bounded actor-storage and arithmetic contracts motivate explicit compatibility behavior and intermediate numeric semantics. They do not make every memory-layout detail part of UIL core. |

No new original-game executions are claimed here. The examples below are
newly authored synthetic cases; their constants, schedules and expected results
are definitions for discussion, not extracted game assets or canonical UIL.
Private source artifacts and receipts remain outside this public amendment.

## 1. Use Z as a behavioral model with inspectable mappings

Z describes entities, state, guarded actions and continuing processes. It can
describe a graphical simulation whose processes run between player inputs.
Z-machine bytecode is a separate source language; Z does not require a text
parser or a rule that one player action advances exactly one turn.

Keep the correspondence from source facts through candidate Z behavior and
UDL recognition to each UIL block inspectable. Record the definition revision,
supported input domain, evidence and remaining alternatives at each mapping.
An authored correspondence is still a claim to validate. A friendly macro name
does not establish its numeric, temporal or persistence behavior.

## 2. Separate signal state, emitted events and queued work

A signal assignment changes a value. A predicate wait observes that value at a
declared phase. An emitted observation records an occurrence. A queue retains
individual pending deliveries according to its own ordering and capacity rules.
Those operations can be composed, but a mapping must state that composition.

The first scheduling profile should define phase order, tie order, wait
release, re-entry, cancellation and repeated or skipped clock inputs. It must
also distinguish a simulation tick from a frame and an external deadline.
Source comparisons retain their recovered ordering rather than adopting the
following synthetic ordering by default.

**Synthetic latch profile:** `signal` is uint16; `remaining` is an integer in
0..2; `starts` is a nonnegative integer. Initially all are zero. Each step
performs: (1) supplied signal assignments in listed order; (2) if an animation
was active at phase entry, decrement `remaining`, clearing `signal` when it
reaches zero; (3) when idle and `signal == 1`, set `remaining = 2`, increment
`starts` and append one `started` event. A new animation is not decremented
again in that step. Step indices increase by one; other clock input is rejected
before mutation in this fixture. This is a synthetic contract, not ACT timing.
Numeric inputs here are exact integers: booleans, strings and fractions are
invalid rather than coerced. Validate all assignments and the step index before
performing any phase.

Starting at step 0, assign 1 at steps 0 and 1. After step 2 the state is
`signal=0, remaining=0, starts=1`, with one `started` event. Assigning 1 again
at step 3 starts a second animation. Assigning 2 or 65535 to an idle actor
does not release its exact-one wait. A write at phase 1 of its finishing step
is overwritten by the phase-2 clear; it does not enqueue another animation.

## 3. Define intermediate action states and completion observations

A macro should identify its preconditions, ordered effects, yield points,
interruption behavior, cancellation and interaction with other processes.
Atomicity must be part of its definition. A sequence with visible pending
state cannot silently become one atomic update or a universal rollback.

Record these observations independently when relevant: input acceptance,
semantic effect, control readiness, rendered observation and persistence.
Their partial order belongs to the particular action. A renderer may present
an older state while a transaction has already committed; a convenience action
must not retry the transaction merely because the picture is stale.

**Synthetic reservation profile:** use signed 32-bit whole-unit balances and
ledger entries; reject an out-of-range intermediate before that operation
mutates state. Start with committed cash 100, working cash 100, no pending
reservation, no delivered item and zero entries for months A and B. Reserving
30 in month A sets working cash to 70, the A expense to 30 and the pending
reservation to 30; committed cash stays 100. Moving to month B changes only
the current-month selector. Cancellation adds 30 to working cash, subtracts
30 from B's expense and clears the pending reservation, delivering no item.
The resulting cash values are both 100, with A=30 and B=-30. Cancellation with
no pending reservation is a rejected action with no state change or refund.
Each named operation here is atomic; their sequence spans distinct boundaries.

## 4. Keep game persistence and evaluator checkpoints distinct

Define initialization and persistence by state ownership and lifetime: world,
transaction, session, scene, process and external service. A field can survive
one boundary and be reset at another. Reconstructing a scene can itself run
logic, consume randomness and change readiness after a load completes.

| Operation | Required contract |
| --- | --- |
| Evaluator checkpoint/restore | State, pending work, clock, random streams and recorded service results needed for the declared replay scope; excluded or non-restorable external effects. |
| Original-compatible game save/load | Exactly which fields are written, restored, retained or reset, plus follow-on scene reconstruction and original failure boundaries. |
| External persistence | Requested bytes or operations, completion/error result and the restart or external-service boundary under which restoration is possible. |

**Synthetic load profile:** `cash`, `rng` and `phase` are uint16. Save/load
stores and restores only cash; it leaves the incoming RNG and phase unchanged
and performs no follow-on work in this fixture. Save and checkpoint at
`(cash=10, rng=7, phase=2)`, then reach `(cash=4, rng=9, phase=5)`.
Game-load yields `(10,9,5)`. Independently restoring the checkpoint from that
same later state yields `(10,7,2)`. No external services exist in this fixture;
an implementation must not generalize that property to other packages.

## 5. Declare player and investigator access profiles

One authoritative simulation can expose a player-equivalent observation
profile and a privileged investigator profile. Each profile must govern state,
events, action discovery, availability and error detail. Filtering a state
query is insufficient if a guard explanation or action list reveals the same
hidden fact. Player-visible disclosure can still occur through a defined game
action; the profile must preserve that action's observable result.

A semantic action retains its acceptance conditions. A convenience operation
that performs inputs, waits or multiple actions declares that expansion, time
policy, stop conditions and observation profile. Investigator access and
convenience operations do not inherit player-equivalence claims automatically.

**Synthetic visibility profile:** two states have identical visible room and
inventory, but `secret_open` differs. The player can initially discover only
`look`; `look` returns the same room description without mutation. A submitted
`open_secret` action returns the same generic unavailable result without
mutation in both states. Player observations, action lists, guard details and
these responses must be identical. The investigator may read `secret_open`.
These restrictions are this fixture's chosen interface, not a universal rule
that every unsuccessful player action must conceal its cause.

## 6. Preserve observable quirks with explicit compatibility contracts

Numeric contracts specify storage and intermediate representations, signedness,
rounding, overflow, comparisons and conversion order. An authored label such
as "pay ninety percent" is insufficient when the observed computation rounds
at a different point. For a synthetic nonnegative uint16 gross of 1007, widen
to uint32 and compute `gross - floor(gross / 10)`: the result is 907.
`floor(gross * 90 / 100)` produces 906 and fails this contract.

Storage-derived behavior needs a declared dependency or a supported domain
where that dependency has a fixed effect. A compatibility definition may name
a bounded bank of logical records without adopting the original machine's
entire memory model. Reject access outside that declared domain. Do not turn
source memory access into authority over host memory or embedded host code.

**Synthetic compatibility profile:** a bank has two records, each with a
uint8 `marker`. A `next_marker(i)` operation accepts an exact integer source
index in 0..1 and returns record `i+1`'s marker; there is no wrapping or implicit
type coercion. With markers `[3,9]`, `next_marker(0)` returns 9. Replacing
the neighboring marker with 4 changes the result to 4. `next_marker(1)` fails
without mutation. This is a small test of a declared cross-record dependency,
not a proposed reproduction of the ACT layout. An isolated-object rewrite
that drops the dependency cannot claim to implement this profile.

Use an existing defined construct when it expresses the behavior honestly.
If a versioned compatibility extension is necessary, follow the RFC process
and require explicit consumer support. A game's accidental layout is not by
itself a reason to expand the universal core.

## Synthetic acceptance cases

These are prospective conformance vectors, not executed UIL test results.
They use the synthetic profiles defined above. The future encoding must make
their inputs, expected observations and failure boundaries independently
reproducible; accepting this document does not establish conformance.

| ID | Case | Expected result |
| --- | --- | --- |
| S1 | Latch: assignments of 1 at steps 0 and 1, then step 2 without input. | One `started` event; state `(signal=0, remaining=0, starts=1)`. |
| S2 | Latch: continue S1 with assignment of 1 at step 3. | A second `started` event; state `(1,2,2)`. |
| S3 | Latch: from initial state, separately assign 0, 2 or 65535 at step 0. | No start; `remaining=0`, `starts=0`; assigned signal is retained. |
| S4 | Latch: assign 1 at step 0, no input at step 1, assign 1 at step 2. | Phase-2 clear overwrites the finishing-step assignment; one start total. |
| S5 | Latch: supply signal -1, 65536, a boolean, a string or a fraction, an assignment list `[1,65536]`, or repeat/skip a step index. | Reject the entire step before state or event-log mutation, including the valid first assignment of a malformed list; report the invalid input. |
| T1 | Reserve in A, select B, cancel using the reservation profile. | Committed/working cash 100/100, A=30, B=-30, no pending reservation or delivered item. |
| T2 | Cancel again after T1. | Rejected with state unchanged; no second refund. |
| P1 | Independently compare game-load and checkpoint restore from the load profile's later state. | Game-load `(10,9,5)`; checkpoint `(10,7,2)`. |
| V1 | Observe, list actions, call `look` and submit `open_secret` in the two visibility-profile states. | Identical player-visible results with no mutation; investigator can distinguish the hidden value. |
| N1 | Apply the defined widened gross calculation to 1007. | 907; a result of 906 identifies a changed rounding rule. |
| C1 | Read the next marker with neighboring values 9 and 4. | Results 9 and 4 respectively; dependency preserved. |
| C2 | Read the next marker from the final record, or supply an invalid source index such as -1 or a boolean. | Explicit out-of-domain or invalid-type failure without mutation or fabricated memory. |
| U1 | A package declares a required block whose definition or capability is unsupported. | Refuse execution before simulation-state/event-log mutation or external effects; retain the missing identity/version in diagnostics or an intake receipt, subject to the access profile. |
| U2 | An agreed contract and consumer intake permit a declared partial-execution profile; its next rule is unresolved or conflicting. | Stop before that rule's effects and record the boundary and prior trace; no guessed effect or successful whole-path comparison. A required unknown capability instead follows U1 and is refused at intake. |

Fixtures must also include the declaration and envelope checks selected by the
eventual UIL contract, including missing required definitions, invalid numeric
types, dependency identity mismatches and malformed encodings. Their precise
wire representations remain an open language-design decision.

## First executable slice and independent acceptance

Use the following sequence to turn this proposal into an executable result:

1. Agree on a minimal, versioned UIL contract and public fixtures for the
   required constructs. Bind each macro to its definition and dependency
   identities. Keep source-specific capabilities explicit.
2. Map one bounded recovered story into that contract, retaining supported
   states, input/time mappings, evidence, unknowns and observable outputs.
   ABOUT's existing host/actor slice is a useful candidate; its full page,
   picture, audio, input and physical-timing paths remain separate work.
3. Compare the original observations with the UIL execution at named
   boundaries. Record source identity, initial state, matched input sequence,
   clock and random/service assumptions, divergence, stops and budgets.
4. Give an independent consumer only the semantic package, its export receipt,
   the declared UIL contract/dependencies and public fixture inputs. Its intake
   binds both digests, the supported contract version and capabilities. It must
   execute from those definitions without the original program or UDL
   recognition machinery. Compare consumer and evaluator outputs from the same
   declared initial state and inputs. Keep public synthetic conformance and
   recovered-game comparisons in separately scoped receipts. Package parsing
   and digest agreement do not establish behavioral agreement.
5. Expand to a transaction with reservation, arrival, placement and cancel or
   commit boundaries. Test interactions with time, drafts and persistence.
   Retain the claim ceiling of each comparison as the slice grows.

A small reference evaluator can validate this contract within the
[existing boundary](UIL_BOUNDARY.md#explicit-stop-line). A target-specific
interpreter or compiler remains an independent consumer. E55's research JSON
and ACT interpreter provide inputs and bounded comparisons; they are not an
already-qualified UIL implementation. No new syntax or runtime is introduced
by this amendment, and the exact encoding and evaluator remain decisions for
the UIL owner.
