# Native accepted source-raster fence

This increment controls one accepted raster from the already defined
`qemu-vga-chain4-scanline-v1` source stream. Sampling phase, source addressing,
DAC conversion and frame acceptance remain unchanged. An accepted raster and
the reason execution stopped are separate facts. No DOSBox phase equivalence,
guest input consumption, or public legacy capability promotion is claimed.

## Frozen QMP fence v1

- `x-fdisbull-arm-video-frame {token, stream-token,
  expected-stream-generation, expected-frame-sequence, expected-epoch}`
- `x-fdisbull-query-video-frame-fence {token}`
- `x-fdisbull-cancel-video-frame-fence {token}`

All expected generation/sequence/epoch fields are unsigned 64-bit integers.
Tokens are strings. A fresh fence token is 1..128 bytes and differs from the
preceding fence token. A stale token or compare-and-set tuple refuses without
changing the existing fence, source stream, input state, timer, or guest time.

Every command requires the existing stable stopped virtual-clock profile with
one stopped CPU, no armed/fired clock budget, no checkpoint transaction, and a
matching producing epoch. PRELAUNCH, PAUSED, and DEBUG are legal. Arm also
requires the exact observing source stream and current source admission.
Query/cancel remain legal for an aborted source stream when the stopped clock
is still valid. No new launch property is introduced.

All three commands return `FdisbullVideoFrameFenceInfo`:

| Field | Meaning |
| --- | --- |
| `api-version`, `model` | `1`, `qemu-video-frame-fence-v1` |
| `token`, `stream-token` | Exact fence and source-stream ownership tokens |
| `stream-generation`, `epoch` | Frozen source generation and producing clock epoch |
| `configuration-generation`, `timing-generation` | Frozen source identities bound at arm |
| `baseline-frame-sequence` | Accepted raster count at arm; may be zero |
| `baseline-rows-sampled` | Partial source rows already sampled at arm, 0..199 |
| `armed-ns` | Native stopped timestamp at arm |
| `state` | `armed`, `completed`, `aborted`, or `cancelled` |
| `released` | Explicit cancellation released this fence's controller exclusion |
| `stop-pending` | Private safe-stop request awaiting an actual stopped VM |
| `stop-consumed` | This fence's main-loop handler itself stopped the running VM |
| `completed-frame` | Optional frozen `FdisbullVideoFrame`, present only for `completed` |
| `stop-ns` | Optional first known terminal stopped native time |
| `reason` | Optional first failure reason, present only for `aborted` |

Arm returns `state=armed`, all three flags false, and no optional terminal
fields. It preserves partial source rows and original row deadlines. The next
accepted raster may contain rows sampled before arming; this is reported by
`baseline-rows-sampled` and is not a whole-raster-after-input guarantee.

A completion contains exactly `baseline-frame-sequence + 1` with the bound
stream token/generation/epoch/configuration/timing identity. Its nested source
receipt is immutable and includes all 200 row samples. A completed fence is
still unreleased until cancelled. An external debugger stop can win even after
publication, leaving the completed raster but `stop-consumed=false`.

When an armed source stream invalidates, the fence becomes `aborted`, retains
the first reason, has no completed frame, and requests a safe stop if running.
If the abort occurs while already stopped, `stop-ns` records that actual time
and `stop-consumed` stays false. Ordinary early DEBUG stops can leave the arm
active for the hook runner's intentional displaced-instruction step protocol.

Cancel changes `armed` to `cancelled` and sets `released=true`. For `completed`
or `aborted`, it preserves state and every terminal field while setting
`released=true`. It refuses an unsettled private stop request. Repeated cancel
and passive query return the same receipt. A new arm can replace only a released
receipt, using a different token. A native load/reset cannot restore or rebind
an old fence into a new epoch.

Authoritative native clock invalidation or clock-owner restore retires any
fence and invalidates its source stream. Retirement releases controller
exclusion and clears private pending work without inventing a stopped timestamp
or changing historical frame/epoch/stop evidence. The retired token is refused
even if a later restore repeats a numeric epoch. A device-local VGA reset/load
at the same clock identity still aborts an armed fence and requests its safe
stop; source reason strings are not used to infer clock retirement.

## Stop and controller ownership

The source callback only publishes the accepted raster and requests a private
stop. The main loop handles existing debug, shutdown, reset and generic stop
requests before the new source-fence handler. That handler sets
`stop-consumed=true` only when it actually changes a running VM to PAUSED.
The expected owned debugger packet uses the ordinary SIGINT class, `T02` or
`S02`. Host success also requires the real stop classification, no pending stop,
and exact agreement with the retained source frame. A receipt alone does not
authorize hiding a breakpoint, hook, guest exit, or another native stop.

The private pending flag participates in the existing no-idle-warp predicate.
Clock budgets, renderer fences, scheduled input, source start/stop mutations,
stopped frame-key mutations, and instrumented save/load refuse an unreleased
fence. Reverse arm order is checked too. Passive source query/probe/export remain
available while stopped. Cancel before checkpointing; fences are never serialized.

The first host integration is a separate `video_frame_advance` operation. Hook
and automatic tracker displaced-instruction paths must both inspect this typed
fence before any automatic continuation. Existing renderer and legacy frame
routes retain their existing contracts. Optional input scheduling and durable
source histories are outside the first host control slice.

## Qualification

The exact hashed production fence helpers passed 34 source-only C cases. These
cover bound next-frame identity, first-stop attribution, cancellation and
controller release, earlier generic/debug stops, checkpoint exclusion, and
clock-owner retirement without fabricated stop evidence. The probe compiles
extracted production functions and the actual main-loop stop tail with
controlled external stubs; it does not execute QEMU. The full combined QAPI
schema also passed the admitted parser with documentation required.

Those helper checks do not themselves claim a native build or device/runtime
integration. The subsequent [twelve-case native gate](../../docs/QEMU_VIDEO_FRAME_FENCE_GATE.md)
passed on a fresh producer, with thirteen VM lifetimes and all owners reaped.
It records the exact tested host/source/binaries, retained failed attempt,
real stop/input/controller witnesses and remaining limits. The source manifest
retains the earlier source-probe checkpoint; the linked gate is the later
runtime disposition. Paired legacy phase evidence remains pending.
