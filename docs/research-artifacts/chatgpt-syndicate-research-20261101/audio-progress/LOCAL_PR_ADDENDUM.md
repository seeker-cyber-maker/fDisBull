# Local addendum: audio service contracts and timer forward progress

**Status: saved locally, not submitted.** GitHub remains disabled by user request.
No remote head, permission, PR state or CI result was queried. Existing PR #69
and other branches were not modified. The earlier graphics patch remains intact;
this addendum must be reconciled with accepted code before eventual publication.

## Motivation and new evidence

The earlier driver-location question is resolved using the existing DOSBox
backend. The fresh continuation adds 42 natural entry/return observations in
that environment, not a proposed new protected-mode emulator.

1. Digital service 133 returns the entry pointer left in EAX by dispatch and
   changes arithmetic flags through stack adjustment. Eighteen calls have no
   observed module-data changes. This is not a generic success/status result.
2. Nine digital service-125 calls all change the selected state from 0 to 2,
   while returning five different EAX values. Entry/return, state change and
   playback completion need distinct contracts.
3. A natural FM timer callback uses SS=0x0088, unlike the foreground flat stack.
   Internal calls also omit the bank-prefixed dispatch frame. Stack and argument
   interpretation must use the actual invocation context.
4. FM start initializes an event cursor and leaves that pointer in EAX. Cursor
   progress was observed, but the end-of-track branch was not hit in this bounded
   session. Source-derived terminal state remains explicitly distinct.
5. A separate controlled experiment executes the original FM callback with
   authored loop events. Zero-count/no-delay reaches 8,000 instructions and 87
   rewinds without returning. Finite counts and a delay inside the loop return.
   Three callback preparations with the delay return at 132/149/149 steps.
   Six distinct cases were reproduced twice, for 18 reaped host children.
6. The natural observer used 3,353 requests, including 2,893 breakpoint creates
   and deletes. That is a measured limitation of this conservative observer,
   not proof the backend inherently requires this volume.

The loop test uses Linux x86-32 compatibility execution, fabricated sequence state
and exact pinned driver instructions. It is not a DOSBox hang, real music edit,
CPU-utilization measurement or demonstration that current assets are defective.
The corresponding original timer callback was observed separately in DOSBox.
All 897 restored original files remain unchanged. All live and host children
were closed/reaped; debugger cleanup is not labelled guest DOS termination.

## Proposed acceptance criteria

| ID | Requirement |
| --- | --- |
| AP01 | Model service-specific results, side effects and completion predicates separately. Entry addresses, cursor pointers and incidental EAX values cannot become success booleans. Retain flags when relevant. |
| AP02 | Read the stack through the current SS:ESP and distinguish registry tail-dispatch, internal calls and timer callbacks. Preserve nested-call identities and reject an unknown argument layout instead of guessing. |
| AP03 | Validate media forward progress per callback, including repeat counters and delay/yield placement. Use bounded non-return and delayed-return controls, with unchanged original instructions and explicit preparation/runtime identities. |
| AP04 | Bind modules, handles and field meanings to load generation and lifecycle. Inactive cursor fields must not be interpreted as currently valid pointers; stale intro breakpoints must not survive driver reloads into MAIN. |
| AP05 | Support or document efficient reusable/filtered call observers while retaining entry/return pairing, interruption semantics, private evidence and bounded output. Measure observer cost rather than assuming a speedup. |
| AP06 | Report mode-sensitive input support and distinguish queued, consumed and completed input. Refused absolute clicking must not trigger an unqualified fallback or a claim that the entire emulator lacks mouse support. |

These are prospective requirements. This local addendum does not implement them,
claim a general music interpreter, expand the production LX profile, or establish
whole-game behavior. It complements the DG requirements and the prior DOSBox
load-mapping correction rather than replacing them.

## Files prepared for later reconciliation

- `docs/AUDIO_PROGRESS_FRICTION_2026-10-31.md`
- `docs/evidence/audio-progress-2026-10-31/summary.json`

The separate research delivery contains authored reproduction scripts requiring
the exact owned GAMEFM file and a new private directory. No original driver,
game asset, raw memory/trace, screenshot or byte-containing project is included.
The source-free arithmetic checker and original graphics patch are unchanged.

## Verification boundary

Rechecked all 42 natural pairs, fresh driver tables/entry windows/fixups, final
keyboard neutrality, emulator cleanup, all 897 original file identities, and
three runs of the six prepared loop cases. The final six cases used the exact
delivered probe script with its clarified pre-step instruction-check label.
Local syntax, JSON/count consistency, links, checksums and archive integrity are
checked separately. No remote CI, fresh repository test suite, release, merge,
shared installation or scheduled publication is claimed.
