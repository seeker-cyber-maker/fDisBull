# KQ1 capture, assisted travel and TAS harness findings

Date: 31 October 2026. This is a sanitized report of a private, original-game
experiment and the resulting public renderer regression work. Original game
files, emulator states, recorded game images and byte-containing databases are
not part of this change. The authored native fixture is independently runnable
without those inputs. Numerical observations and identities are also recorded
in [the aggregate receipt](verification/kq1-tas-2026-10-31.json).

## Findings and scope

The short experiment established three useful results:

1. Native AVI recording can retain a short run for exhaustive frame decoding
   and later sampling. Processing recorded frames while the guest was stopped
   did not advance its observed clock or state.
2. The agent's latest-frame cache can reject completed, changing frames even
   while native recording continues. The completion guard used a line counter
   that the simple scaler does not maintain for changed rows. This PR corrects
   that guard in both backend profiles and adds an authored regression.
3. A declared assisted room crossing was substantially faster than the ordinary
   movement controller under the same bounded finish conditions. No full-game
   assisted run or replay of a published TAS was completed.

The investigation used source commit
[`0b7f258cc0fa71daef5c60c068ade42904c5d1c6`](https://github.com/seeker-cyber-maker/fDisBull/commit/0b7f258cc0fa71daef5c60c068ade42904c5d1c6)
and an existing shipped Linux backend. This PR is based on current main
`90e748c8bc6a4f068f9136f4d4ec989672421a03`; it does not transplant the earlier
branch's scene or UIL work. The previously working conversion and its tests
remain intact. Neither input macros nor a successful path through the game are
being relabelled as recovered game intent.

## What was captured

The DOSBox-X profile used fixed CPU cycles of 157600, the normal core,
`frameskip=0`, and unchanged-frame retention. Native fast-forward was used in
both comparison arms; the game's own speed variable remained at its normal
value. These are separate settings. Automatic cycle adjustment or changing
the game's speed would change the experimental conditions.

The completed paired experiment produced two mode-specific AVI segments:

| Segment | Size | Decoded frames | Stream timebase | Every fourth frame exported |
| --- | --- | ---: | --- | ---: |
| Initial text mode | 720 × 400 | 213 | 15625/1095103 seconds | 54 |
| Game mode | 320 × 200 | 1,623 | 25000/1752157 seconds | 406 |

All **1,836 frames** were strictly decoded and hashed as canonical RGBA before
selecting every fourth frame. Duplicate images were retained. This verifies
the recorded stream and the sampling procedure; it does not prove that every
guest scanout reached the recording hook. Each segment retains its own PTS and
timebase. Restoring a checkpoint also prevents treating the recording as one
continuous guest-clock timeline.

In a separate stopped interval, decoding 209 already captured frames consumed
259.805701 ms of host time. Guest ticks remained 5405, the accepted snapshot
sequence remained 584, and the six observed game fields stayed unchanged.
That supports offline or paused inspection. It is not an experiment showing
identical physical input delivery at two live execution speeds.

For the proposed harness, retain the full short recording, decode and validate
it, then sample for the analyst's budget. Every-frame or every-Nth-frame review
can run more slowly than the guest recording. A live consumer would require a
native frame queue and explicit backpressure that stops guest advancement when
the queue fills. It must not slow the emulated CPU, reschedule input from host
wall time, or silently discard evidence. Those facilities are proposed in
[TAS routes as an analysis and test harness](TAS_ANALYSIS_HARNESS.md), not
implemented by this renderer fix.

## The snapshot defect and correction

Both shipped native profiles contain `CaptureCompletedAgentFrame()` in
`src/gui/render.cpp`. Before this change it rejected a frame when
`render.scale.inLine < render.src.height`.

That counter is insufficient: unchanged rows advance it in the start-line
handler, while changed rows switch to the simple scaler, which advances the
source-cache cursor without advancing `inLine`. `outLine` is also unsuitable
because linear and random simple scaler variants maintain it differently.
A frame whose pixels were fully processed can therefore be rejected. After
restore invalidates the snapshot cache, changing output can leave the caller
with `No complete framebuffer` rather than a fresh image.

The new guard first preserves the existing dimension, pixel-format, pitch and
allocation bounds. It then requires the source cursor to equal the bounded
end of the frame:

```cpp
const std::size_t source_frame_bytes = render.scale.cachePitch * height;
if (render.scale.cacheRead != scalerSourceCacheBuffer + source_frame_bytes)
    return;
```

Equality avoids pointer subtraction or ordering against an unrelated cursor.
The existing render-end call still excludes aborted updates. This changes the
evidence for completion; it does not unconditionally accept a partial cache.
Both complete patches and their source manifests are updated together.

The original patched renderer SHA-256 was
`ebd35b92b3d30484605cd1cc954d8eab9413970dc07ba75df3b6bda628b50de6`.
The corrected source SHA-256 is
`4e1c7a47e3f78b67442bf7287d370c3a60eac5fb9d3e5ce411d4267413055a85`.
Both derive from pinned upstream commit
`029bd65c5dcc7cdc7f2e14e35278620d9707d969`.

The private native reproduction queried the snapshot API immediately after
restoring a fast-game checkpoint and again after guest ticks advanced from
5557 to 6567. Both queries failed. During that observed interval the AVI grew
by 228,838 bytes. Packet boundaries and independent RGBA decoding identified
70 complete video payloads in the appended byte range, with 70 distinct pixel
hashes. Thus recording continued while the two snapshot queries failed.
File offsets do not supply exact guest timestamps; codec buffering was not
calibrated. No claim is made about unperformed intermediate API queries.

### Verification of this change

`tests/test_frame_cache_contract.py` compiles the actual added capture function
from each complete patch. Its two profile cases pass locally. They exercise a
completed source extent with zero line counters, palette-only changes,
partial/overrun/unrelated cursors, the exact allocation boundary, invalid
dimensions/pitch/format, and the existing 8/15/16/32-bit pixel conversions.
Both modified render patch sections apply cleanly to the pinned source and
produce the declared source hash.

The authored native regression in `tests/test_frame_capture_native.py` is
included in the required-native CI command for **both stable and layers
profiles**. Its DOS assembly fixture first qualifies a static 320 × 200 image,
then changes an eight-pixel sequence code at each guest retrace. One phase
changes the first row; the other changes every row. Execution checkpoints
stop the guest after exactly 17 animated retraces, before the next paint.
After restoring a checkpoint, the test requires the exact final sequence,
fresh frame metadata, and repeated paused screenshots that leave guest state
and time unchanged. It does not let host polling wait for an unchanged frame
to hide the defect.

Both phases were run against the shipped old backend. Static qualification,
guest counters, state save/restore and 17 subsequent retraces succeeded; both
then failed at the intended assertion because `video.probe` still reported
`No complete framebuffer`. Both processes were reaped. CI exports only this
authored fixture's JSON receipt, emulator log and successful PNG, with no
emulator states or game inputs. A locally compiled function contract is not
a substitute for the live renderer check on a rebuilt backend.

The focused local regression suite passed **236 tests**, with **32 native tests
skipped** because that invocation did not supply a backend. This includes the
source contract and existing Zork intent/UIL reference checks. The separate
old-backend native invocation above deliberately demonstrates the defect;
its two failures are not counted as passes.

The local environment lacked native build headers and autotools, and its
configured network proxy was unreachable. Rebuilt-native acceptance must be
read from the PR's required-native jobs and their backend identity receipts.
The PR must report their actual results before claiming the rebuilt backend
is verified. Neither the previous game observations nor the compiled function
contract qualify a rebuilt binary. The shipped binary remains the baseline
for failure reproduction.

## Offline capture audit now exposed as an API

The recording verifier is now available as `fdisbull capture-audit`, the
project-independent JSON method `capture-audit`, and
`fdisbull.capture_audit.audit_capture`. It strictly decodes and hashes every
recorded video frame before choosing PNG samples. Its optional inspection page
can play those samples more slowly while retaining their original frame indices
and exact video timestamp fractions. [Usage and limits](TAS_CAPTURE_AUDIT.md)
include budgets, private outputs and explicit failed-segment receipts.

The public CLI was run on the same two finalized KQ1 recordings, with every
fourth frame exported and an HTML viewer per segment. No emulator was launched
or attached. The pass took **5.56 host seconds** in this local environment; this
is one observed audit duration, not a cross-machine performance guarantee.

| Segment | Dimensions | Decoded frames | Exported PNGs | Adjacent identical frames | Video timebase |
| --- | --- | ---: | ---: | ---: | --- |
| 0 | 720 × 400 | 213 | 54 | 211 | `15625/1095103` |
| 1 | 320 × 200 | 1,623 | 406 | 1,222 | `25000/1752157` |

All **1,836 per-frame RGBA hashes**, original indices, source PTS, exact timestamp
fractions and **460 sampled PNG hashes** matched the retained earlier audit.
The new tool derives from that verifier, so this establishes regression parity,
not an independent algorithm or a new native run. Known-color authored fixtures
separately check decoded pixels against independently calculated expected hashes.

The new real-codec suite passed **28 tests**, including sampling invariance,
duplicate retention, independent segment clocks, corruption/truncation, byte and
time limits, late source/export failures, private-output guards, JSON dispatch,
and nonzero CLI failure status even when the response spills to an artifact.
The separate current regression invocation passed **366 tests**, with **one
native doctor test skipped** because no native backend was configured. That
invocation includes the existing Zork/UIL reference suites, output delivery,
media discovery and distribution checks; it does not overlap the 28 new tests.
Earlier test counts above describe the prior native-fix invocation and must not
be added to these counts as unique coverage.

Both native CI profiles now install FFmpeg and require the capture-audit suite
alongside the authored framebuffer regression. This offline tool makes no
guest-clock, input-schedule, audio-validation or whole-game completion claim.
Rebuilt-native acceptance of the framebuffer correction remains pending.

## Bounded ordinary versus assisted comparison

Every timed attempt restored the same checkpoint in room 1 at `(110,100)`
with score 0. The ordinary arm used the existing movement controller. The
assisted arm explicitly wrote actor position `(154,100)` and ORed actor flags
with `0x0400`, then used original Right input to let the original game perform
the exit. Assistance is part of the treatment and cannot be counted as a
physical-input speedrun.

The finish contract required room 8, x in `[0,4]`, y 100, score 0, both actor
and control direction neutral, drained input, and fresh destination-picture
evidence established against an ordinary-input reference. All six accepted
trials ended at **room 8, x 1, y 100, score 0**, with both directions neutral.

| Pair | Ordinary guest ms | Assisted guest ms | Ordinary host ms | Assisted host ms |
| --- | ---: | ---: | ---: | ---: |
| 0 | 4,675 | 410 | 24,195.075 | 2,293.296 |
| 1 | 4,684 | 410 | 24,869.956 | 2,223.154 |
| 2 | 4,715 | 419 | 27,340.373 | 2,873.436 |
| Median | **4,684** | **410** | **24,869.956** | **2,293.296** |

The median reduction was **91.2468% in measured guest time**, and 90.7789% in
host time. Three trials per arm describe this experiment; they do not establish
a general reliability or speed distribution.

The outer timer includes the route, input cleanup, fresh-frame wait,
destination checks and final state/input qualification. Final PNG encoding
and export happen after that paused endpoint and are excluded. Guest elapsed
time is the observed end tick minus the start tick, not the sum of requested
run durations. The final assisted trial retains a 3 ms difference between the
419 ms outer interval and 416 ms of component receipts.

Checkpoint preparation advanced 100 or 105 guest milliseconds, so starting
ticks were 5400 or 5405. Equal observed starting fields do not prove identical
hidden timer, RNG or CPU phase at the timed boundary. Raw outer host monotonic
endpoints were not retained: source inspection establishes the intended
brackets and component receipts check consistency, but those host durations
cannot be independently recomputed from endpoint timestamps.

The independent audit checked the six trial conjunctions, qualified field
observations, input drain, source and checkpoint identities, final frame
metadata, intervention readbacks, and durable receipts in a closed immutable
database. It passed 157 experiment/durability checks plus 795 trial checks.
Nine deliberately corrupted in-memory receipts were rejected. This was an
independent audit of one experiment, not a second native execution. The
aggregate receipt contains no private captured bytes; public readers can
recompute its arithmetic, but cannot recreate the game experiment from that
receipt alone.

### Failures retained in the record

| Attempt | Observed failure | Treatment |
| --- | --- | --- |
| First normal setup | Invalid breakpoint address representation | Failed setup; no timing result |
| Earlier normal pair | Movement reported `blocked`; later cleanup reached room 8 | Failed controller result; excluded despite eventual arrival |
| Two fast-checkpoint attempts | No fresh framebuffer after restore | Capture failures; motivated the renderer investigation |
| Fast reference from a normal checkpoint | Room 8 was first observed with control direction still Right; cleanup drifted to `(104,98)` | `destination_not_retained`; no fast comparison accepted |

For the accepted normal experiment, the no-progress allowance was increased
from 15 to 100 polls while retaining the overall bounds and finish checks.
That qualifies the successful controller configuration. It does not erase
the earlier failed result or repair the separate fast-speed settling problem.

## Consequences for TAS-assisted analysis

The short route is already useful as a repeatable way to reach an interaction,
place a watchpoint, inspect one committing operation, and compare a declared
branch. The current script, checkpoint, wait, movement, trace and artifact
facilities can support those bounded procedures. A harness should evaluate the
whole success conjunction and preserve failures; arriving at a room after an
operation failed is insufficient.

Exact imported TAS replay needs more: physical input edges scheduled in the
native guest clock, recorded actual delivery times, deterministic initial
machine/profile identity, and an explicit desynchronization result for late
events. Host polling and integer-millisecond press/type requests do not
reproduce every sub-millisecond input movie. CPU instruction stepping is not
video-frame stepping. A snapshot `frame_id` counts accepted cache refreshes;
it is not a universal frame count, and fixing freshness does not create an
all-frame recorder.

To test recovered UIL, use a short route to produce a source-bound reference
interaction: conditions, ordered state changes, output, modal continuations,
turn/timer effects and terminal state. Execute the intended UIL through its
UDL definitions and compare those effects with native execution and preserved
low-level IR. An unexplained effect remains explicit residual IR. A matching
route is one behavioral witness, not proof that all game intent was recovered.

The [harness guide](TAS_ANALYSIS_HARNESS.md) details checkpoint branches,
writer investigations, failure minimization, scene coverage, differential
checks, and acceptance gates for the missing scheduling/capture facilities.
The current evidence supports faster bounded assisted investigation. It does
not establish that teleportation beats a published full-game TAS.
