# Z read-only reconciliation: verification

PR #26 was merged at `83d74494fec2e8267111762cde04915c4bb2c5ce` after fresh
readback of its clean merge status and passing checks. This follow-up starts
from that merge. Candidate runtime:
`ee8d606bcd1771aff0a0424ff32672150ea70f17`, private core/player 0.25.0 packages.

## Change and evidence boundary

The [batch contract](Z_BATCH_RECOVERY.md) defines `reconcile` and opt-in history
inspection. A fresh same-session/context/state witness and an already durable
complete reply are required. Reconciliation can repair local journal state; it
sends no game action, checkpoint save/load, acknowledgment or guest-time request.
It never runs the next step. Missing, incomplete, stale or foreign evidence stays
unresolved. A partial original intent does not become complete through a later
continuation.

Restore replies are now persisted before the following client read. Reconciliation
requires the real checkpoint handle and the provider's qualified restore result.
History retains that receipt and superseded attempts. An already finished restore
can be verified without another load or history entry. The CLI remains available
when an operation leaves a durable recovery latch, including blocked run/resume
and checkpoint requests. Python callers still receive the original read error.

## Portable verification

Eighteen new regression cases cover action/restore readback recovery, journal
reopening, no implicit later step, idempotence, opt-in history isolation, CLI
operations/lifetime, absent/incomplete/unbound replies, mismatched checkpoint
certificates, foreign sessions, intervening actions and partial-original intent
guards. Fourteen initial cases failed before implementation for the missing API
or missing durable restore reply. The CLI lifetime regression separately failed
before its operation-boundary fix.

Focused checks: **198 passed**, from both the checkout and extracted source tar.
Required `python -m pytest -q`: **1,898 passed, 118 skipped, 13 failed, 23 errors**.
All 36 failing/error identities match the recorded PR26/main baseline (1,880
passed, 118 skipped, 13 failed, 23 errors). None were added or removed; the local
whole suite remains red. Linux CI is a separately reported gate.

Both wheels, source tar and tool ZIP pass the tool-only archive guard. All **165**
source/wheel/source-tar/tool-ZIP runtime payloads agree. The new test file is
retained in both source distributions. The original native TextScene class and
recognition profiles are unchanged; the Z bridge adds only response witnesses.

| Candidate artifact | SHA-256 |
|---|---|
| Core wheel | `6b944a2fae2219ff744a7d4bc17ac222acbbfd445b89112f14e96acea611c465` |
| Player wheel | `344f080b3f9b0358d08ec47d303d26e450da63b3473f4f92b6ac9f71decf8933` |

## Original-game acceptance

Native acceptance uses the exact funded26k seed SHA
`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`
and retained quiet native backend SHA
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
The installed candidate, original financial/food commits, state witnesses,
provider requests and native clock/input boundaries are qualified separately
from the portable boundary doubles above.

Luna verified the exact installed candidate in one completed original-game
trial. All 165 installed payloads, wheel hashes and actual imports matched the
manifest. The following cases passed with the same provider/native processes:

| Case | Native result |
|---|---|
| A: confirmed purchase, failed following client read | The complete accepted/applied-confirmed reply and witness survived. Reopening the journal and reconciling changed unknown to paused/continuation-required without another BUY. One later explicit authorized ACK reached the street. |
| B: restore reply, failed following client read | The real restore certificate was durable in `recovery.result`. The installed CLI returned recovery-incomplete and kept accepting operations. Read-only reconcile finished the local rewind without another LOAD or guest-time advance. |
| C: consumer expects compact history | After an ordinary explicitly requested restore, the caught history-read error was resolved by `reconcile` returning verified and opt-in history exposing the stored receipt. No new restore or history entry appeared. |
| Lost client-delivered reply | A matching original scene could not replace the missing reply; reconciliation remained unresolved/unknown. |
| Explicitly incomplete client-delivered reply | The confirmed effect remained recorded, but reconciliation refused to complete the intent. A separately requested certified rewind was required before more purchases. |
| Idempotence and later state | Repeated reads sent no action and duplicated no history. After an intervening action, the old restore was no longer verified. |

Ten bounded reconciliation intervals each contain exactly **one provider
observe** and no action/save/load. Independent before/after reads match all 20
native ranges, captured guest ticks, frame ID and pixels, native state revision,
provider session, run and both PIDs. Native event bytes remain unchanged. The
allowlisted native methods are reads of memory, registers, status, mouse state,
screenshots or completed-frame pixel probes. The backing uses no GUI input.
A witness binds the original stopped state; no matching-destination inference
is substituted for the complete original reply.

The completed trial used eight Player commands (four current and four superseded),
77 provider requests: 65 observations, eight actions, one checkpoint save and
three explicit checkpoint loads. All three native restores matched 20/20 saved
ranges before input-free frame preparation and Dino Diner requalification.
Four protected original purchases each had cash **26,941 -> 26,441**, food
**10 -> 30**, and one confirmation. Reconciliation added none of these purchases
or loads. The final normal purchase, one ACK and ordinary office travel proved
the context remained usable. Actual provider stdin EOF returned worker/native
zero, completed receipts and cleanup, no unsolicited response and no survivors.
Actual quiet launches/logs, original assets/seed and installed payloads passed
all 19 final checks. The bounded completed trial took about 109.332 s; this is
verifier elapsed time, not a model-performance benchmark.

Parent raw readback independently rechecked all ten physical/wire boundaries,
all four protected money/food deltas, three native20 restore witnesses and three
184-resource closures (UDC output, compiled game, native working game) against
the original assets. A separate initial trial and its failed verifier check are
preserved below rather than included in the completed-trial verdict.

## Preserved verifier friction and total accounting

The first trial's read-only guard omitted `video.probe`, an existing sparse RGB
read from the last completed frame. Its physical equality/input checks had passed
before the allowlist check held the controller. The error printed the whole read
method set rather than only its unrecognized member. The bounded controller
subsequently closed the guest; this is a partial verifier trial, not a failed
provider reconciliation or a completed set of native requirements.

The frozen interval was rechecked offline against the corrected narrow read
allowlist. Negative fixtures containing execution, keyboard input or state load
must fail. The original helper source, held control record and closure are kept.
An explicitly declared additional finite cohort used the same candidate in a
new guest and completed all cases above; no running game code was patched and no
uncertain action was blindly replayed. Reconciliation itself kept the completed
trial's guest throughout.

Across both trials: **two guests, ten Player commands** (six current and four
superseded), **94 provider requests**: 79 observations, ten actions, two checkpoint
saves and three explicit loads. There were five original food commits including
the partial trial. No trial or discarded branch is omitted. Both workers/native
processes exited zero with no owned survivors. The first trial's all-pass flag
remains false; the completed trial's flag is true.

Future verifier tooling should qualify its read vocabulary against real frozen
protocol records and report only unexpected methods. A readback validator must
retain the successful operation's response/witness before its own checks, and
use read-only reconciliation instead of redispatching that operation. Finite
controller deadlines remain separate from provider action success.

Native evidence and seals are under
`Conversions/DinoParkTycoon/luna-z-reconciliation-20261030-01`, with the completed
trial in `trial-02`. Parent package/test/readback receipts are under
`Conversions/DinoParkTycoon/dinopark-z-reconciliation-20261030-01`.

## Limits

Reconciliation does not reconnect a dead transport or resurrect a dead guest.
An intervening action invalidates the witness even at the same scene. Checkpoint
save failures and native-load session-handoff readbacks remain conservative and
are not reconciled. The caller must serialize other users of the provider.
Witnesses bind public observations; they are not original-intent completion
certificates or general game-equivalence proofs. Original-backed UDC qualification
remains `original_bytes_only`, with zero recovered semantic blocks. Private game
files, saves, databases and screenshots remain outside Git and tool packages.
