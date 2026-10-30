# Named DinoPark terminal actions — original-game batch, 30 October 2026

## Result and identity

**Passed in one continuous original-game guest.** Luna exercised the ordinary
`ProcessBackend`/`Player` interface with **19 Player commands, 80 provider
requests and two additional token probes**. The parent independently checked
the raw native calls, kernel exit, source snapshot and original file hashes.
No investigator controls, caller coordinates, guest reset, restored snapshot
or input replay supplied the acceptance path.

Tested production source:
`cbefec3a96df2f7ee2eb7dca82e0222401d48426`. All **173** frozen source/player
files match the PR's production files; subsequent commits add documentation.
The earlier `0173a8a` snapshot was superseded preparation before the sole native
launch. Resume was bound to the already verified original menu thumb control.

The existing native macOS **0.26.1** backend was selected explicitly, SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
Live capabilities included selected-DOS lifecycle reporting. The original EXE
remained `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
No package, backend build, installation or activation was performed.

## Shared-context batch

| Commands | Original-backed result |
| --- | --- |
| `open game menu`, `resume park` | Menu opened; its original thumb returned to the office. All twenty park fields stayed equal across resumption. |
| `go bank`, `repay loan`, `borrow loan`, `go office` | Existing routes and transactions still worked after the new menu path. Repayment reached cash/debt $0/$0; borrowing reached $5,000/$5,000. |
| `check status` | Correctly refused before the first qualified park entry; this is existing operating-report coverage. |
| `open menu`, `quit park`, `cancel quit` | Quit confirmation was exposed as a partial stage. Cancellation returned to the office; all twenty park fields stayed equal. |
| `open game menu`, `quit park`, `confirm quit`, `decline save` | A new quit intent followed the confirmed cancellation. Confirmation exposed the save-first question. Declining reached the matched original title menu. |
| `exit dos`, `continue transition`, `continue transition` | Exit input was sent once. The public continuations advanced only original execution; the last reached the selected program's kernel exit. |
| `look`, `look` | The cached exited context remained stable, offered no game actions, and made zero native calls. |

The **ten terminal input gestures** were three menu opens, one resume, two
separate quit requests, one cancellation, one confirmation, one save decline
and one Exit to DOS. Each gesture occurred once for its declared action.
Pointer preparation is accounted for separately. Neither input-free
continuation sent keyboard, mouse-button or pointer-movement input.

The two token probes selected an otherwise valid current action and changed
only its context token. Both were rejected before execution/input. Full native
status, PIDs, registers, frame, guest ticks and all twenty park fields remained
equal. Modal checkpoint creation was also refused without native effects or a
recovery latch; that refusal did not stop the rest of the batch.

## Completion evidence

Prompts returned `accepted` with partial effects; they did not certify park
departure. `decline save` returned success only after the original title menu
matched. The initial `exit dos` remained a partial transition, and its two
continuations shared the original twenty-second requested-time budget.

The native terminal event reported `guest_exit`, session `exited`, selected PSP
**`0x0814`**, parent PSP **`0x0701`**, requested exit code **0** and
`resident:false`, from **`DOS_Terminate`** at **`after-process-cleanup`**.
The selected PSP matched independently retained entry registers/load mapping.
The public action reply retained that certificate. Later provider EOF returned
worker **0**; the native emulator returned **0**, and no owned process survived.
There were no native call errors or post-exit heap/frame reads.

All **183 original shipped files** remained unchanged across the source copy,
UDC output, compiled deployment and native runtime closure. The prior sealed
reply-recovery investigation also remained unchanged. Actual launches retained
SDL dummy audio, disabled mixer output and disabled host MIDI.

The largest public reply was **1,606 bytes**. This batch produced no naturally
oversized public response. The earlier [oversized-reply acceptance](VERIFICATION-DINOPARK-Z-REPLY-RECOVERY-2026-10-30.md)
remains separate evidence; diagnostics and native records stay private.

## Friction and remaining coverage

- **Operating-report preconditions:** `check status` is advertised in the office
  but the current handler requires an earlier qualified park entry. A future
  availability predicate or explicit precondition label could avoid this known
  refusal while preserving unknown operating quantities.
- **Modal checkpoints:** New live-checkpoint creation is refused while terminal
  prompts are open. Its existing generic `complete:false/incomplete` reply could
  distinguish known unavailability from an unknown native save outcome. Broader
  modal checkpoints need a qualified terminal-state descriptor and restoration
  evidence before that restriction can be relaxed.
- **Prompt coverage:** The affirmative save-first route, original Load/Save menu
  controls, title-menu New/Old Game, About and Sell Park remain outside this new
  named-action subset. Existing native park saves remain available through the
  qualified pre-quit path. This batch does not certify a complete playthrough.
- **Alias scope:** The native exit used `exit dos`; `exit to dos` was checked as
  equivalent parser resolution without repeating a terminated game's action.

No verifier failure or corrective second guest was needed. The existing
cancel/resume and bank paths were batched with final termination in the same
running context. Original-game fidelity beyond these observed paths remains
bounded by the existing scene and native-save contracts.

## Portable checks and delivery

The affected suites passed **211 tests**, with one existing native checkpoint
test skipped because `FDISBULL_DOSBOX` was not globally configured. New tests
cover named public dispatch, modal action visibility, stale/wrong-context
refusal, cancellation, shared wait budgets, recovery holds, unsupported/foreign
exit evidence, prompt precedence and cached post-exit observation. An explicit
baseline check confirmed that `8ebe686` exposed no named terminal action.

Source helpers, sparse recognition profiles, synthetic tests and sanitized
findings are included in PR #41. Raw frames, original game resources, databases,
native state, snapshots and verifier receipts remain outside Git and packages.
