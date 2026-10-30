# DinoPark funded26k return and provider recovery

The legacy funded26k food-order failure is a quarter notice over the street.
The retained original frame matches all 23 quarter probes. The street matcher
must continue rejecting that obscured view; its samples and rejection rules
are unchanged. The food backing now exposes the known notice after the original
500-debit/20-feeder commit instead of waiting for an unobscured street and failing.

## Confirmed purchase with a pending return

The public purchase response is accepted with `effects: applied-confirmed` and
`followup: pending`. Its public context is `food-return.quarter-notice` (or a
positively recognized `food-return.parking-notice`). Only the notice action is
visible. A new purchase is not available. One explicitly requested acknowledgment
uses the shared original-input continuation and qualifies the actual street
before completing the return. It does not issue another BUY or redefine the
original financial/food effect.

For a batch with the goal of returning to the street:

```json
[
  {
    "id": "food",
    "command": "buy 20 small feeders",
    "expect_context": "street",
    "continuations": {
      "food-return.quarter-notice": "acknowledge notice",
      "food-return.parking-notice": "acknowledge notice"
    }
  }
]
```

`run` pauses at the confirmed purchase; `resume` may execute the declared notice
action. A pre-order advisory remains a different context: acknowledging it does
not establish a purchase, and a new purchase intent must be explicitly requested.

## Recovery-only provider

An action failure no longer has to destroy a reachable paused native guest.
The original-scene command loop offers the Z provider an action-error callback
inside the native debugger's lifetime. The provider retains the guest only if
there is an active action and a fresh native status query confirms it is stopped.
Unreachable or running guests retain the fatal-error path; startup and transport
failure are not declared recovered.

The failed command receives exactly one incomplete response. Confirmed purchase
effects remain confirmed; an unproven effect stays unknown. The detailed failure
and its recovery requirement are persisted before that response. Later failures
use new diagnostic files rather than overwriting the first.

While `recovery_required` is true:

- Observation returns incomplete with the same opaque provider-session identity.
- Ordinary actions, including stale-token attempts, are refused without game input.
- New checkpoint creation is refused; an uncertain state cannot become a new anchor.
- An existing live checkpoint can be explicitly loaded through the existing protocol.
- EOF and cancellation remain available for owned cleanup.

Successful restore must match all 20 native ranges, prepare a completed frame
without input and requalify the saved scene. Only then are recovery-only and
failed-restore flags cleared, prior failures linked to their restoring checkpoint,
and fresh action tokens issued. No purchase or navigation input is replayed by
the error handler. See [batch recovery](Z_BATCH_RECOVERY.md) for journal/branch
semantics, mounted-file checks and live-checkpoint limits.

If EOF closes an unresolved recovery-only session, the native and service receipts
remain incomplete/recovery-required while recording cleanup independently. A
successfully restored session can finish normally with its failed/recovered
attempts retained. Standalone scene callers that supply no recovery callback
retain their previous error behavior.

## Verification scope

The portable regression retains 156 actual RGB probes from original frame 3852,
image SHA `3f4b0ff04418e396e6bbddcfc2b69af4a0752eb366bf8f50bf64f3914c94a91b`.
It proves quarter recognition and clear-street rejection without distributing a
full game image or inventing missing pixels. Native acceptance uses the exact
legacy funded26k save, SHA
`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`.
The final native findings are recorded separately after installed-candidate tests.
