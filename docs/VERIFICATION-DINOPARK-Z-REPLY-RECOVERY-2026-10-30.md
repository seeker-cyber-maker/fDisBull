# DinoPark oversized reply recovery — 30 October 2026

## Changed boundary

The bridge previously replaced any JSON response exceeding 32,768 UTF-8 bytes
with an incomplete error. The original action had already run, but its returned
native evidence was no longer retrievable through the protocol. A regression
reproduced that exact failure before the change.

The [reply recovery protocol](Z_REPLY_RECOVERY.md) retains the exact full JSON
before returning a bounded reference. Filesystem-only retrieval is separate
from witness-bound delivery acknowledgement and from further game execution.
An unresolved delivery blocks observation/action/checkpoint dispatch, and cannot
be recorded as clean completion merely because the worker shuts down.

The implementation reuses the existing private output-artifact store. It does
not alter original game bytes, decode new game semantics or add public terminal
scene verbs. This earlier native verification used the declared investigator terminal
adapter with fresh stored-frame preconditions and the ordinary original-backed
UDC. The subsequent [named-action follow-up](DINOPARK_Z_TERMINAL_ACTIONS.md)
adds public Z terminal verbs in later PR #41 commits.

## Source and native identity

Native trials 1–3 used committed source
`97b4e65eb441a5916cc3b64634a777f7a038e1f7`, copied into a private raw source
snapshot before launch. Final source normalizes the actual native status field
`last_stop` into the retained stop witness, rejects missing/invalid stop evidence,
and tests a changed stop even at the same revision. Real captured before/after
native statuses also passed a separately labeled host-only check of that final
normalization. No new guest was launched by that host-only check.

Final native cohort 4 ran the complete production fix at
`2c868ce6e4104ef8c42bb033e42f6f70f5599730`, including that stop normalization,
from a separately frozen raw source snapshot. Later documentation commits do
not change the tested production modules.

The existing **0.26.1 native macOS backend** was selected explicitly. Its SHA-256
is `bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
Live capabilities advertise `lifecycle.dos_guest_exit`. The older installed
0.26.0 backend has the same bytes as the previously used 0.22 backend and lacks
that capability; a newer directory name alone did not qualify selected-DOS exit.

The original executable remained
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Runtime inputs were the 183 shipped files, excluding the local analysis database.
Source, runtime-copy and backend identities are retained privately. Quiet native
launches use SDL dummy audio, disabled mixer output and disabled host MIDI.

## Independent cohort accounting

Each cohort is a fresh, separately declared test. Starting a later test never
resolves the earlier guest's pending delivery or supplies an earlier exit proof.
Within a cohort, recovering a lost reference uses its same surviving provider
and native guest; no original game input is replayed.

| Cohort | Confirmed observations | Qualification |
| --- | --- | --- |
| 1 | A genuine 37,954-byte result with 415 passive observer records survived a deliberately discarded compact reference. Exact bytes/hash were recovered; retrieval made zero native calls. All nine strict readback witnesses remained equal. Blocked duplicate input/checkpoint requests dispatched no native input. | The verifier incorrectly included a permitted bad-digest acknowledgement status query in its zero-RPC retrieval window. The run remained held and closed through real EOF, returning 1 with `complete:false`, delivery pending and clean process cleanup. It supplies no DOS-exit certificate. |
| 2 | A genuine 37,972-byte result was recovered in five data pages, repeated reads/selections agreed, and acknowledgement plus repeated acknowledgement succeeded in the same guest. All nine witnesses stayed equal. | The park's Quit sequence returned to the original title menu. Sixty seconds of input-free execution did not select its separate Exit to DOS button. No selected-DOS exit was claimed. |
| 3 | Same-guest delivery recovery and acknowledgement succeeded. A separately observed title-menu Exit to DOS button was selected once. | The first 1,000 ms interval ended on a black transition with the original process still paused. The finite verifier exposed no input-free continuation after that final button, so it closed without an exit certificate. This is a verifier control gap, not an observed game crash. |
| 4 | **Passed on final production source.** A genuine 37,812-byte result with 411 passive observer records survived the discarded compact reference. Exact paging, repeated reads, held-input probes and acknowledgement succeeded in the same guest. Exit to DOS was selected once; two separately requested input-free exit intervals reached an authoritative selected-DOS exit. | Original Quit/confirm/decline inputs were never replayed. The earlier three cohorts retain their own qualifications. |

The nine readback witnesses are complete native session identity, worker/native
PIDs, guest clock, frame hash, twenty native park fields, registers, input-call
counters and the native scene-event journal hash. `reply_status`, `read_reply`
and `select_reply` made **zero native RPCs**. Acknowledgement queried only
`session.status`; an invalid-digest query is accounted for as acknowledgement,
not as filesystem retrieval.

## Final selected-program exit and cleanup

The final original-game result has native `outcome:guest_exit`, session
`state:exited`, and stop kind `guest_exit`. Its kernel evidence records:

- selected PSP `0x0814`, matching the independently retained entry DS/ES and
  MZ runtime-load calculation established before any quit input;
- parent PSP `0x0701`, requested exit code **0**, and `resident:false`;
- source **`DOS_Terminate`**, stage **`after-process-cleanup`**.

This is target termination evidence, distinct from later host cleanup.
The test made five terminal input calls, each exactly once: menu, park Quit,
confirmation, decline-save and title-menu Exit to DOS. Two duplicate-input
probes were denied before native dispatch. Three separate startup clicks opened
the fresh original game; total native input calls were eight. The three
input-free runs were return-to-title and two exit-settling intervals.

The recovered 37,812-byte result has SHA-256
`fd55a672bd38191f87fe608f6a8caa18634fe0efd88f10696d7174df75c015e5`.
The parent independently verified exact artifact bytes, all nine equal readback
witnesses, zero retrieval RPCs, actual input-call counts, entry/exit PSP identity,
and all **183 original shipped files unchanged**. Actual provider stdin EOF then
returned worker code **0**; the emulator also returned **0**, and there were no
owned survivors. Earlier cohorts were closed independently with their pending
or uncertified states preserved.

The private tracer attempted one final interrupt-vector read after the target
had exited and recorded `TARGET_EXITED`. This leaves that post-exit vector check
unavailable. It is not a game crash, and it does not invalidate the earlier
kernel exit event or successful host cleanup. No freed-target park fields were
used as final exit evidence.

## New friction and recommended follow-ups

- Audit native calls by operation and interval. File retrieval must make zero
  native calls; receipt acknowledgement may query native status. Combining the
  two windows produces a false rejection despite unchanged guest state.
- Distinguish leaving a park from terminating the executable. The original title
  menu presents **New Game**, **Old Game** and **Exit to DOS** after the park's
  Quit sequence. The final exit button is a new visible action, not a replay or
  automatic continuation of the earlier click.
- A finite scene controller needs declared input-free continuations after every
  transitional terminal action, plus read-only inspection while held. Requiring
  an exit within one fixed input interval can strand a valid running context.
  Neither a black frame nor a timeout establishes a crash or completed exit.
- Keep backend capability and byte identity beside the selected version. An
  installed directory's version cannot stand in for actual lifecycle support.
- Instrumented cleanup should consume lifecycle evidence before requesting
  target-memory corroboration. After authoritative exit, retain an unavailable
  post-exit read as a qualification and finish host cleanup without treating it
  as an application crash.

The other discovery, filtered-observer and named-terminal-scene proposals remain
open in the [PR #41 friction record](DINOPARK_STATIC_ANALYSIS_FRICTION.md).

## Verification and delivery scope

The affected source suites passed **203 tests**, with one existing native
checkpoint test skipped because `FDISBULL_DOSBOX` was not globally configured.
The explicitly selected original-game cohorts are separate native evidence.
Tests cover exact byte accounting, paged integrity, retrieval without execution,
action/checkpoint holds, reference loss, journal reopen, stale/foreign/corrupt
receipts, storage failure, acknowledgement idempotence, native stop binding and
unresolved-delivery shutdown. All newly introduced documentation links resolve.

Only source, synthetic regression tests and documentation belong in the PR.
Original executables/resources, raw screenshots, native state, databases and
receipts remain private. No local packaging, publication, installation or system
activation is part of this task.
