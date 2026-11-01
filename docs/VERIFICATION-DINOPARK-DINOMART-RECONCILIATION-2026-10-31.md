# DinoMart timeout, retained-provider reconciliation and continued inventory

This follows the [caller/filename-producer review](VERIFICATION-DINOPARK-CALLER-PRODUCERS-2026-10-31.md).
It changes source on the 0.26.1 research branch, starting at
`cc4501079dc411d5b8bdb23d561a20e212d08f42`, and uses the existing native backend.
It does not qualify the concurrent 0.27 candidate, a system installation or a
distribution. Original files, databases, frames and raw probes remain private.

## Timeout diagnosis and implemented behavior

The earlier DinoMart failure retained a street frame with the original
"please wait" sign. Its 10-second host budget ended after 2,080 guest
milliseconds and 21 polls. Resource loading had progressed, but the destination
was not qualified. The active observer workload's causal contribution remains
unisolated; neither the frame nor resource reads established arrival.

The `street.mart` scene action now has a 40-second host budget. Its 12-second
guest budget and destination predicate are unchanged. The player transport's
existing maximum remains 60 seconds. This is a bounded adjustment, not a promise
that arbitrary instrumentation or a whole multi-stage purchase fits that bound.

A scene postcondition failure now retains the original queued-input receipt,
source scene revision, action identity and before-observation. The DinoPark
provider keeps the held command, effect status and unique attempt ID after a
recoverable action error. Further action input remains blocked. Confirmed
purchase commits do not become unknown merely because a follow-up is unsupported.

For a held `go dinomart`, the `reconcile` text command and corresponding
JSON-line operation can requalify the existing paused destination from the
stored original frame and current selector. Eligibility requires the original
ticket, source revision, canonical action and same session/run. A supplied
attempt ID must match. This path sends no input, runs no guest code and restores
no checkpoint. A successful reply carries the original action, attempt ID and
fresh destination witness; the original failure file stays unchanged.

An unresolved destination or unsupported hold stays unresolved. Read-only
reconciliation cannot finish a still-loading scene or reconnect an exited
process. The normal EOF/signal cleanup contract remains in force.

The player can reach reconciliation without first requiring an ordinary scene
observation, which is deliberately unavailable while held. Batch reconciliation
also checks the attempt, action and session. It persists a returned provider
certificate **before** the following observation, preserving the original
unknown reply. A later failed or unqualified read leaves the step unknown with
the certificate available after journal reopen. Only a fresh matching witness
can then classify the step; it sends neither the original action nor the next
planned step.

## Luna original-game verification

All three ready native contexts used the original-backed UDC and the supplied
game, with SDL dummy audio, mixer `nosound=true` and MIDI device `none`.
Original EXE SHA-256:
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Unchanged backend SHA-256:
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.

The normal routes purchased the desert plot through original inputs, confirming
cash $5,000 to $4,500, entered DinoMart and read the Vegasaurus encyclopedia
through Z. This qualifies those routes under the new budget; it does not turn
the historical, already-closed unknown guest into a reconciled action.

For the recovery experiment, Luna injected one **host-only diagnostic timeout**
after the second original `street.mart` call had already returned matched, but
before adapter destination qualification. There were no forced guest writes or
extra inputs for the injection. The provider remained live and held, ordinary
action input was blocked, and the corrected probe issued read-only reconciliation.
The parent independently checked the raw provider reply and the player's result:

| Reconciliation property | Observed result |
|---|---|
| Native PID, session and run | Identical before and after |
| Additional execution calls | 0 |
| Additional input calls | 0 |
| Total `street.mart` calls | 2 before and 2 after; no replay |
| Original failure diagnostic | Same hash |
| Canonical result | Complete, success, `applied-confirmed`, `read_only: true` |
| Witness | Same session, `context_id: dinomart`, fresh context token |
| Player result | Preserves the witness and reports `action_sent: false` |

This tests reconciliation of a destination already reached at the failure
boundary. A real timeout while the original frame is still loading must remain
held. No complete original-native BatchSession end-to-end claim is made; its
durability and identity paths are regression-tested separately.

Two private probe defects remain in the evidence. The first wrapper accepted
no optional argument, although the selected service forwards an optional attempt
ID. It rejected reconciliation before its body. After correcting that wrapper,
the provider and player successfully reconciled, but a later private assertion
read `witness.context.id` instead of canonical `witness.context_id`. That probe's
overall route remains incomplete despite the valid recovery response. The test
results were preserved rather than rewritten as a full-route pass.

The third context independently reached the bank, returned through the office,
bought land, entered DinoMart and read the encyclopedia. Its subsequent
Coelophysis order hit the 60-second transport deadline. Its dispatch and partial
shop observations remain, with no returned purchase result or commit certificate.
The purchase is **unknown and unreplayed**. Later businesses, park setup and the
planned operating-day tests were not executed. Fresh host inspection found the
worker and native process absent; the last receipt's null return code is stale,
not proof of a live provider or clean shutdown. This is a transport-boundary
failure, separate from the recoverable scene hold verified above. Its exact
low-level cause was not isolated by a live stack.

## Candidate coverage and remaining obligations

Luna continued the individual 97-entry and 13-asset ledgers against retained
original analysis and new native evidence. Each new context retained the same
34 candidate PC arrivals: 31 repeat the earlier 41, and **three are first native
arrivals among the 62 previously published targets**. Those three have exact
stored CALL-return and live far-slot correlations. Across old and new captures,
44 distinct candidates now have PC-arrival evidence. The overall 104/201
positive PC/publication union is unchanged because these three already had
static publications; their evidence level has advanced.
The parent independently checked all nine new-entry/run pairs against raw
register DS, slot-window bytes, runtime CS:IP, CALL operands and far-return
stack words under the recorded mapping and normal ABI.

The 34-entry captures contain 33 stored CALL-return matches, 25 entries with
strict live far-slot matches and four with live near-table-cell matches. One
arrival still has no matched ordinary CALL return. These are scoped transfer
correlations, not function-effect or universal call-graph proofs.

None of the 97 remaining candidates was hit in these retained captures. The
third interval has no complete end record, so its missing observations stay
unknown. All 97 remain open. A fresh stored-fact screen checked
4,765 decoded direct calls and 107 memory-indirect calls. No direct target in
that screen adds a qualified caller for the 97. Three repeated candidate near
slots for `23c5:0009` still lack a recovered owner/consumer; their values alone
do not establish dispatch. These are additional bounded observations, not a
dead-code proof or a replacement for the per-entry obligations.

The parent also screened **all 183 pinned original runtime inputs**, including
code, configuration and media, for all 13 case-normalized exact ASCII filenames
and padded DOS FCB 8.3 forms. Every input hash matched the native source manifest;
all 13 had zero matches in both representations. Derived IDA metadata and
preexisting saves were outside that runtime-input manifest. This extends the
earlier executable-only negative. Split, compressed, formatted or externally
supplied names remain outside this exclusion; it establishes no new producer
and certifies no asset globally unused.

All 13 also have zero exact-name opens or positive reads in the three retained
native event sets. The first two contexts record 47 distinct successfully opened
and read names; the third records 48. `DINOMART.ACT` and `DINOMART.PIC` are
positive in all three, as is the neighboring `RICOCHE3.ABT`, which does not
establish use of `RICOCHE2.ABT`. Each context reached eight supplied shared-open
producer sites. The unresolved 13 remain individually accounted for.

Every unresolved entry and asset retains its disposition, checked scope and
next discriminator in the private ledgers. Static publication, potential
consumer, retained PC arrival and actual effect remain separate evidence levels.

## New friction and follow-ups

- Keep scene and transport deadlines distinct. A recoverable scene error can
  retain a paused provider; the current process transport closes on its own
  deadline. Heavy multi-stage purchase probes need bounded progress or explicit
  continuations before that outer deadline, with known commits preserved.
- Preflight diagnostic wrapper signatures, canonical witness fields and public
  commands before native execution. Provide shared typed probe helpers rather
  than repeating private wrappers. A valid provider result can outlive a failed
  test assertion. A stale receipt cannot establish process liveness.
- Retain reconciliation certificates before follow-up readback. The independently
  found batch durability defect is fixed here, with raised and unqualified
  observation regressions that reopen the journal without replay.
- Continue correlated callback/near-table and constructed-filename research.
  Absence from a static reference query or finite route is insufficient to
  discard code or media. The relevant mechanisms may be present or absent;
  requested coverage must account for both without assuming either outcome.

The reusable investigation guidance is a separate documentation proposal,
[PR #80](https://github.com/seeker-cyber-maker/fDisBull/pull/80). It includes
finite candidate accounting, caller/producer discriminators, relocation-window
ownership, failure-boundary triage and qualified read-only recovery. It does not
add a new automatic analysis capability or promise these mechanisms in every
binary.

## Tests and preservation

- 50 affected batch/reconciliation/navigation tests pass, including both new
  consumed-certificate/readback failure regressions.
- Two separately run real-native scene tests pass, including timeout input-ticket
  persistence across database restart and actual stored image export.
- Full source suite: **2,070 passed, 131 skipped, 12 failed and 23 errors**.
  All 35 failed/error node IDs exactly match the earlier sealed baseline.
  Optional managed dependencies and macOS ELF fixtures remain existing limits;
  the full suite is not green.
- Native-tested scene/provider source bytes match delivery. The player's only
  later change is the help sentence; reversing that sentence reproduces its
  tested file hash. The later batch persistence change is independently reviewed
  and regression-qualified, not claimed as a separate native batch run.
- All **13,511 members of seven earlier sealed packets** rehash unchanged.
  All 192 original-folder names and hashes also match the native baselines.
  Raw original files, native state, failure receipts and databases remain outside
  Git. No package, backend build, installation, activation, merge or release was
  performed. CI remains skipped because it also creates distributions.

The new private packet contains **2,622 files / 221,922,187 bytes**. Its manifest
SHA-256 is
`8c78f11ecc7727a1f82e45be6c8acea8e04a49de49d674a40131a10bc0c3d877`.
All three native outcomes, private probe failures, unqualified final cleanup,
per-candidate ledgers and parent verification receipts are retained. The packet
does not contain a claim that all code is understood or that all assets are used.
