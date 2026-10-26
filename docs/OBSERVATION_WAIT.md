# Bounded observation waits

`DebugSession.wait`, live JSON `debug-wait` and saved-script `wait` poll explicit
observations between bounded guest slices. A measured DOS guest clock is required;
Wine/PE does not currently offer this operation.

```json
{"format":"fdisbull-script-1","steps":[{
  "op":"wait","as":"changed",
  "observations":{"counters":{"kind":"memory","address":"0x471a6","length":8}},
  "until":{"observation":"counters","not_equals":"0300030003000300"},
  "guest_ms":2000,"slice_ms":20,"timeout_ms":10000,"max_polls":1000,
  "fast_forward":true,"timeout_screenshot":"counter-diagnostic.png"
}]}
```

Addresses/expected bytes belong to the caller's project and checkpoint. The
example waits for bytes to change; it does not establish that a control exists.
No DinoPark knowledge is built into the debugger.

| Observation kind | Descriptor | Compared value |
|---|---|---|
| `memory` | `address`, `length`, optional `cs` | Exact hexadecimal bytes |
| `register` | `path`, e.g. `general.eax` or `cs` | Integer |
| `status` | Explicit integer field `path` | Integer, only if that field exists |

Predicates select `observation` and one comparison: `equals`, `not_equals`, `lt`,
`le`, `gt`, `ge`, or `greater_than_initial: true`. Optional `mask` applies to both
sides. `all`/`any` combine lists of predicates. Memory constants/masks must match
the capture length; ordered comparisons treat memory as little-endian unsigned.
Registers/status use integer or hexadecimal integer constants. No expressions
or implicit address discovery execute.

The first observation happens while paused, before guest execution. A true
initial predicate succeeds without a run. All requested captures are mandatory,
including observations in an `any` predicate. Missing/short captures are
incomplete evidence, never success.

Guest budget and host deadline are independent. Polls retain values, original
capture responses, elapsed guest/host time and all run receipts. DOSBox's host
polling boundaries can overshoot a requested guest slice; measured overshoot is
reported and a match first observed beyond the total guest budget is rejected.
Pause, synchronous captures and diagnostic cleanup can extend measured host time
beyond the polling deadline. This is not a hard process-kill timer.

Breakpoints, watches, hooks, exit and guest errors stop waiting. A hook's action
is dispatched once, but the wait does not resume past it. Its full stop receipt
is preserved even if post-stop bytes would match. `last_observed_guest_ms`
identifies the last completed observation, which may precede that stop.

Only `complete: true, matched: true, outcome: predicate` lets a saved route
continue. Other results fail the step with evidence retained. A requested
diagnostic screenshot is stored on failure; capture errors remain explicit.
Saved experiments retain the operation and report; comparisons include poll
values/outcomes rather than discarding intermediate observations.

A completed-frame counter can be requested if a backend exposes one; absence
fails closed. Frame freshness or camera equality alone does not prove that a
clickable control exists. A byte-verified control-builder return breakpoint can
supply a separate stop. No game-specific widget or screen-name inference occurs.
Limits: 16 observations, 256 bytes each, 1000 polls, 256 predicate nodes and
eight nesting levels. Comparison remains observed evidence, not deterministic replay.
