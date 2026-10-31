# Original DOS AGI host adapter

`AGIDOSHostAdapter` advances an admitted original-interpreter invocation to
resolve the compact AGI model's draw, erase and print requests. It compares the
source path and a declared native-state projection at the original return.
The Python API is explicit; `execute_il` and `il-run` still perform no native
operation and retain their existing model-only semantics.

This first profile is qualified for the supplied DOS KQ1 edition, whose AGI
file SHA-256 is `5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74`.
The unpacked interpreter code has a separate live fingerprint. Other AGI
editions, nested logic calls, nonzero cached scan starts, opaque operations,
cycles, a game scheduler and autonomous dialogue input are outside this
profile. The current native object projection covers ego 0 and actor 13.
This is a host boundary for selected source routines, not an entire AGI engine.

## Bind the invocation before advancing it

The caller supplies its own licensed input, immutable `AGILogicResource`,
prepared DOSBox backend, live session and observed CS/DS/code offset. Segment
values are run-specific. A filename or static address is insufficient.

```python
from fdisbull.agi_dos import AGIDOSMonitor
from fdisbull.agi_host import AGIDOSHostAdapter, capture_state
from fdisbull.agi_lift import lift_logic

# session is paused at the original evaluator's initial fetch. scalar_names
# contains the source routine's explicitly selected variable/flag bindings.
monitor = AGIDOSMonitor(session, resource, cs=cs, ds=ds,
                        code_offset=observed_code_offset)
state = capture_state(monitor, scalar_names)
projection = lift_logic(resource, initial_state=state,
                        control_flow="compact", effect_profile="agi-2.917")
host = AGIDOSHostAdapter(monitor, projection,
                         viewdir=private_game / "VIEWDIR",
                         volume_dir=private_game)
receipt = host.run()
# Repeated run/readback calls only inspect this retained result.
assert host.readback() == receipt
```

The monitor verifies the full unpacked code fingerprint, command table,
complete selected bytecode, current logic descriptor, initial scan pointer
and evaluator call frame. Its identity includes the live session and runtime
epoch. Restoring a checkpoint invalidates it. Active code layers refuse this
original-interpreter profile. The lifted projection is independently rebuilt
from the immutable resource and captured scalars before the guest advances.

`CS:294a` and `CS:0303` are the qualified pre-fetch sites in this edition;
they expose every selected source opcode, including tests and jumps. The
final witness is an actual evaluator return to `CS:1306` with the expected
stack, not a DOS process exit, a timer pause or an arbitrary native `RET`.
The lower-level legacy `CS:02c4` mode only observes one fetched action's
handler return. It cannot certify an entire invocation.

Default limits are 128 source instructions, 1,000 guest milliseconds and
10,000 wall milliseconds per step, with independent totals of 10,000 guest
milliseconds and 60,000 wall milliseconds. `AGIDOSMonitor` accepts explicit
`max_instructions`, `guest_ms`, `timeout_ms`, `total_guest_ms` and
`total_timeout_ms`. Paused inspection consumes the wall budget. A limit never
counts as a return.

## Observations and equality scope

Variable bytes and high-bit-first packed flags are captured from paused RAM.
Object records retain signed positions, dimensions, indices, flags, controller
settings and previous-position data. Loaded-view lists are traversed with
cycle/count bounds; every loaded payload must match its captured resource.
Object view, loop and cel pointers and dimensions must bind to those payloads.
Nonzero previous-cel pointers must also refer to a bound cel. Paused-state
revisions are checked across captures, after owned breakpoint cleanup.

The adapter follows the original source path in lockstep with the model's
continuations. It accepts only its own execution breakpoints; foreign stops,
watchpoints, hooks, guest exits, timeouts and missing captures stop the trial.
Draw results come from the returned original object's position. Erase and
print completions come from the corresponding original handler's return.
Each native completion retains its source occurrence, identity and screenshot
artifact before the model proceeds. A failed screenshot preserves the
already completed handler and makes the trial incomplete.

A print protocol result named `shown` or `dismissed` records the original
handler's completion in the declared output mode. It is not a pixel/text
assertion. Receipts carry `visual_verified: false`. In particular, the tested
nonblocking print frame did not establish a visible message window. A blocking
message awaiting input remains incomplete; the adapter does not dismiss it
automatically or silently continue through a stop.

`status: verified` and `complete: true` mean the observed source path, selected
scalars, loaded resources and declared object projection matched at the
qualified return. Capture key/count mismatches are differences. The result
lists `excluded_fields`: the model helper `view_replaced` has no qualified
original field; follow/cycler union bytes have no independent follow meaning
outside follow mode; previous dimensions with a null previous-cel pointer
have no qualified native value. Their model initialization conventions are
explicit projection loss, not measured native facts. Intermediate native
snapshots are retained, but equality is evaluated at the final return; this
does not prove equality of every transient value or rendered frame.

## Preserve effects and reconcile before retrying

An attempted operation is recorded before the guest continues. `native_execution`
is false before execution, true when native progress is observed, and null
when a transport failure leaves execution unknown without an earlier observed
completion. `native_execution_attempted` distinguishes a request from its
outcome. Model failure, lost response, foreign stop, capture failure or a
detected difference preserves prior completions and requires reconciliation.
Neither the guest nor a mounted host file is rolled back by the model.

`run()` is single-use with idempotent readback. It never automatically retries
an interrupted operation. Inspect the stopped guest or deliberately restore
a qualified native checkpoint, then create a new monitor/adapter. A retained
JSON result cannot reconnect an exited emulator. The context, source-retaining
projection, model checkpoint, raw native snapshots, message texts and native
states must remain outside Git.

## Reproduce with private originals

[`examples/agi/verify_host.py`](../examples/agi/verify_host.py) supplies bounded
baseline, initialization, horizon, print, erase and interrupted-operation
trials. Select a fresh private output directory for each case:

```text
PYTHONPATH=src:. python examples/agi/verify_host.py \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/host-print --case print
```

The script labels its interventions: a temporary caller operand selects
logic 103 and is restored before that logic executes; authored scalar states
select branches. Erase requires a second diagnostic invocation from a checked,
completed call frame. The original native CALL creates that new frame. These
are original-handler differential tests under controlled inputs, not ordinary
gameplay, naturally reachable saves, deterministic replay or whole-game parity.
See [the verification report](VERIFICATION-AGI-HOST-2026-10-31.md).
