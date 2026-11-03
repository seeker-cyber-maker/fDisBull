# Rewind for runtime crash investigation

Anchor Stones and rewind can help reproduce a failure and narrow the interval
where state first becomes wrong. The current automatic frame timeline records
only execution advanced through its owned frame API. It does not sample an
arbitrary normally running process in the background.

This assessment follows source at main
`3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7` and existing local contract tests.
No native crash-survival experiment or new crash-recorder implementation is
claimed here. Read [the frame contract](FRAME_INPUT_TIMELINE.md),
[delta storage](FRAME_STATE_DELTAS.md) and
[instruction rewind](DEBUGGER_REWIND.md) for backend admission and limits.

## What is useful, and what survives

| Situation | Available use and evidence boundary |
| --- | --- |
| State corruption or a bug appears while the session still returns valid completed frames | A valid live timeline can return to an earlier point and replay a known input suffix. Sparse RAM predicates or canaries can help locate the first bad frame. |
| A fault, guest exit or other stop produces a non-frame result during an attempted frame advance | The completed-frame contract rejects that result. The attempted operation closes the owned session, clearing unpinned frame history; a responsive emulator alone does not guarantee rewind access. |
| Frame execution, input delivery, capture, restore or its receipt becomes uncertain | Guards may invalidate and close the session. Use already committed recovery artifacts; do not assume the interrupted frame was recorded or automatically repeat the uncertain action. |
| The emulator dies while idle and the controller has not entered its close path | Cached pinning may be possible because pinning does not require a native RPC. This is an implementation inference, not a tested post-crash guarantee. Pin before the risky operation. |
| The controller owning the session exits | Its unpinned RAM cache is lost. Already committed Anchor Stones, exported images, traces and receipts remain separate project artifacts, subject to ordinary storage durability. |
| An instruction-rewind trace interval or CPU/RAM-delta operation fails | Instruction rewind saves `rewind-before.sav` before each trace interval; CPU-delta startup saves a recovery Anchor. Those committed artifacts can outlive invalidated navigation. A saved run does not reconnect its old emulator or live cursor. |

Full and delta frame storage have the same failure/persistence boundary.
Delta mode changes how cached native checkpoints are retained; both modes still
capture a full native state at every recorded point. The earlier prepared-KQ1
measurement saved cache bytes but increased forward-loop time, so normal-speed
continuous recording is not qualified by that result.

`timeline_pin()` persists the selected complete state as an Anchor Stone.
`timeline_image()` separately exports a cached PNG when that point has a
completed stored frame. Pinning is not an automatic image export. Neither method
needs to advance the guest or operate a GUI. An initial paused point can lack a
stored image; report that absence rather than running another frame to invent
pre-failure evidence.

## A bounded investigation workflow

1. Select the matching source/version, native backend and private mounted inputs.
   Start from a verified Anchor. Record its artifact ID and SHA-256 before the
   risky suffix; verify its persistence receipt rather than relying on a name.
2. In a healthy stopped DOS frame context, start a bounded full timeline, or
   choose delta retention if its storage tradeoff is useful. Advance in small
   owned frame/input batches and inspect a sparse state predicate between them.
   Ordinary unrecorded `run` calls and mutations invalidate the timeline.
3. Pin useful known-good points before the expected failure. Export their
   stored PNGs separately if visual evidence is needed. Record point/frame,
   branch, source/backend identities and the input plan with the artifact IDs.
   No automatic periodic pinning or background monitor is supplied by this guide.
4. If a bad state is observed while the timeline remains valid, preserve that
   evidence before branching. Rewind to an earlier point, replay the declared
   suffix and compare the state predicate. A completed-frame observation only
   localizes the interval; it does not identify the corrupting instruction.
5. Pin before changing to breakpoints, watchpoints, hooks or instruction tracing.
   Those mutations can invalidate the frame history, and active layers/hooks
   are refused by timeline admission. Load the committed Anchor in a compatible
   context and perform a short writer/trace investigation as a separate phase.
6. If the session closes or the controller exits, recover from a previously
   committed artifact in a fresh compatible session. Preserve failure receipts
   and unknown in-flight outcomes. Do not describe an uncommitted cache point
   as a surviving checkpoint.

For the first reproduction attempt, restore RNG with the complete state.
Preserving RNG or other RAM with `allow_partial_resume: true` creates an
intentional mixed experiment and retains that provenance; it is not evidence of
the original crash replay. Without explicit partial-resume permission, the mixed
state is frozen until trusted recovery. Mounted host files and external I/O are
not rolled back by these state loads. A matching state/input plan is a starting
condition; actual reproduction must still be observed.

## Backend and handoff scope

The frame timeline is qualified for its compatible DOS native backend. It does
not establish general rewind for an arbitrary native macOS application. Wine/QEMU
has separate selected CPU/RAM-delta contracts; that is not DOS frame-history
parity or qualification on Microsoft Windows. Confirm the actual backend
capabilities before planning an operation.

The file-delivery delta utility reviewed in MR !42 has a different role: it can
package selected, sanitized text findings or reproduction plans for a handoff.
It does not collect runtime state, capture crashes or reverse execution. The
project is public, so private game files, core/RAM dumps, native states, raw
captures and byte-containing databases remain outside Git and report uploads.

## Evidence and the next useful runtime check

Relevant source seams are
[frame admission/failure/pinning](../src/fdisbull/debug_timeline.py),
[session close and artifact transactions](../src/fdisbull/debugger.py),
[instruction checkpoints](../src/fdisbull/debug_rewind.py),
[CPU-delta recovery](../src/fdisbull/debug_cpu_deltas.py), and
[RPC channel failure](../src/fdisbull/dosbox_rpc.py).

Existing local tests cover live-only history, cached pin/image export,
unrecorded-mutation invalidation, uncertain forward/restore/input failure and
terminal cleanup. In particular,
`test_failed_transport_cleanup_releases_cache_and_terminal_ownership` verifies
that close clears the live cache even when native cleanup or its receipt fails.
These are offline/stopped-RPC contracts, not an actual emulator crash test.

A future authorized native probe should use a small authored target and compare
three distinct cases: an observed bad state at a completed frame, an in-flight
fault/non-frame stop, and backend loss. Commit an Anchor and stored PNG first;
then verify their artifact hashes and fresh-session recovery. Record whether
the live history remained valid in each case. Recheck storage admission before
that capture phase and keep one guest owner. This guide starts no probe, watcher,
CI job, installation or release.
