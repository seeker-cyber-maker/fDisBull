# Bounded stopped pending QMP event batch

`x-fdisbull-take-pending-events` is a private cooperative observation command.
It returns the currently retained bounded monitor event batch while the
original monitor and machine satisfy its stopped eligibility checks. Its
model is `stopped-pending-qmp-events-v1`; its boundary is
`matching-response-event-batch`. It does not establish an event-free stream,
discarded history, event causation order, or atomic frame/CPU observation.

## Native ownership and eligibility

The native patch targets QEMU 10.0.13 with the recovered FDisBull Build03
extensions. It requires the sole initialized original stdio QMP monitor,
without multiplexing, pretty printing, out-of-band dispatch, or reconnection.
The provider refuses unsupported or running states, replay, migration,
checkpoint and other competing native controllers. Native stopped-control
scope checks remain separate from cooperative revision accounting.

Durable frame keys may remain held, or released but attached. They do not by
themselves prevent this event cut. No frame-key query, detach, release, guest
advance, input injection, or controller mutation is part of the command.

The native throttle table is bounded at **64 total states**, including entries
whose retained event dictionary is null. Overflow invalidates this facility
permanently for the monitor lifetime before iteration or event consumption.
The complete selected batch is validated and all result references are
allocated before any retained dictionary is cleared. Existing timer ownership,
key identities, and event coalescing remain in place.

## Exact reply and finite limits

The success envelope contains exactly `id` and `return`. The request ID is an
exact positive integer captured before dispatch. The return object contains
exactly `model`, `boundary`, `monitor-id`, `monitor-epoch`, `status`,
`event-count`, and `events`. The monitor UUID is canonical lowercase ASCII;
epoch is an exact integer in 1..2^64−1. Status is `prelaunch`, `debug`, or
`paused`. Count is an exact integer equal to the event-list length.

A native refusal is an exact `id`/`error` envelope with typed `class` and
`desc` strings. It remains a failure; it is never converted to an empty batch.
Malformed IDs, duplicate keys, extra or conflicting fields, non-object packets,
floats, nonfinite numbers, Unicode strings, NULs, and out-of-range integers
refuse. This stricter decoder is local to this command.

| Limit | Bound |
| --- | ---: |
| Retained events | 64 |
| Native throttle states, including null entries | 64 |
| Event depth, root at depth one | 8 |
| Value nodes per event / complete batch | 256 / 4096 |
| Members per object / items per list | 64 / 256 |
| ASCII key / string leaf length | 128 / 4096 bytes |
| Aggregate decoded keys and string values | 32 KiB |
| Encoded event / complete event list | 16 KiB / 128 KiB |
| Actual response line, including newline | 256 KiB |
| Bare events before matching response | 64 and 256 KiB total |
| Incoming wire, including initial buffer and final read-ahead | 512 KiB |

Encoded sizes use QEMU's ordinary JSON spacing and ASCII escaping, including
escaped DEL characters. Each receive is capped at the remaining wire budget.
The matching response ends the operation; any later bytes already read remain
in the original buffer. An uncertain dispatched operation closes its captured
original resources without retry. Bounded received bytes and the validated
pre-callback reply remain available on a failure, including late arrivals.

## Delivery and retained reads

The complete retained list is validated before its first callback. Delivery
uses the original event objects and captured original admission handler. The
owner, authority, revision authority, protocol lock, socket, monitor lifetime,
handler binding, full reply contents, and all container identities are checked
before and after each callback. Equal-valued replacement containers are still
replacements. Started and returned callback counts are separate for bare and
retained events. A partial callback failure preserves the same exception and
the effects already applied; no later event is replayed or rolled back.

Probe, RGBA, local screenshot, and source-frame artifact capture share the
sequence: capture original owner and deadline; establish the existing stopped
clock context; take one eligible cut; complete callbacks; admit one revision;
perform the existing frame selection, read, encoding and publication checks.
The existing eight-part frame identity remains unchanged. Later events or
cooperative effects still invalidate the admitted frame. An earlier status
does not get rewritten when a later frame succeeds at a new revision.

The command is dispatch-passive only when advertised and called with `None`
or an actual empty dictionary. Each event retains its normal revision effect.
Strict `ObservationAuthority` leases continue to exclude the command and
refuse it before dispatch. Cooperative observation does not weaken that gate.

## Status and verified DOS return

Supported status captures its original owner and minimum existing deadline
before waiting for the first lock. It retains the original native query, whose
`running` field must be an exact boolean. Tracker projections finish before
the eligible stopped cut, and the final snapshot uses the captured revision
authority. Running status takes no cut. The cut state must agree with the
original stopped observation; disagreement preserves the delivered batch as
failure evidence and closes the original owner.

When an outer DOS status owns a dispatched asynchronous run, the base cut is
deferred. Only the existing complete nonce-bound memory and UART return
verification, launch-identity checks, process classification and cleanup may
authorize a final cut. Normal exit and TSR follow this sequence. Tracker
controls and process projections complete before the cut and final snapshot.
The permitted process/runtime epoch transition is predicted from that verified
original return, rather than copied from callback-modified state.

A genuine layer-ending return may close its owner. It returns its final
original revision snapshot without another QMP or GDB call. Helper PC alone,
a cleared pending marker, an unverified report, and an ordinary asynchronous
stop provide no return proof. A non-return stop has no return-specific cut;
a later ordinary status may take its own cut. General guest control remains
excluded during return reconciliation and stop enrichment.

## Verification scope

The authored host tests use actual QMP framing, schema validation, callback
delivery, public frame/status entry points, original-resource cleanup, and
real helper report parsing and persistence. Native QMP/GDB/UART peers and OS
processes are authored boundaries; no QEMU executable or private guest input
is run by these tests.

The native patch and its six-file source manifest are source artifacts. Host
tests do not qualify monitor scheduling, native allocation failure, actual
64-state overflow, timer retention, held-key device behavior, armed native
scope refusal, or guest timing. Those require a newly built, identified native
binary and separately retained probes. Prior build or test totals are not
evidence for this reconstruction.
