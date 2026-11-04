# Rewind for runtime crash investigation

Anchor Stones and rewind can help reproduce a failure and narrow the interval
where state first becomes wrong. The current automatic frame timeline records
only execution advanced through its owned frame API. It does not sample an
arbitrary normally running process in the background.

This assessment follows product source at main
`3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`, local contract tests and the bounded
native backend-loss proof below. The native proof covers deliberate termination
of an owned emulator, not discovery of a guest vulnerability or a new automatic
crash recorder. Read [the frame contract](FRAME_INPUT_TIMELINE.md),
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

## Native backend-loss proof, November 3

The authored [recovery probe](../scripts/check_native_crash_recovery.py) passed
both full and delta cases on macOS/ARM64 at source
`1afeb55cfa9822874d2d4a9435ed972ce901e75d`. It used the existing authored
512-byte `FRAMES.COM` fixture, no game assets. The fixture's signature and BIOS
key-consumption fields verified that the intended target and input ran.

The probe first committed an Anchor and a separate stored PNG, then recorded a
golden one-frame suffix. It wrote another frame request and delivered SIGKILL
only to that session's owned backend before reading its response. Guest progress
and response completion at injection are unknown. Both cases observed RPC EOF,
closed the failed session and cleared the unpinned cache.

| Case | Cache at the pinned point | Failed backend | Committed state/PNG after loss and project reopen | Fresh native recovery |
| --- | --- | --- | --- | --- |
| Full | Three full points | SIGKILL, return code -9 | Hashes match their committed artifacts | Pinned exposed CPU/full 64 KiB DS match; one-frame suffix CPU/DS and actual PNG match |
| Delta | One full point and two deltas; selected pin materializes a delta | SIGKILL, return code -9 | Hashes match their committed artifacts | Same within-case comparisons pass |

Each recovery used a new native process with empty live history. Its normal exit
was observed and reaped, as was the failed process. The final proof used four
owned processes serially. No cross-mode CPU/machine-parity comparison is claimed.
The retained raw DS reads and all exported/replayed PNG bytes support an
independent artifact audit; they stay private outside Git.

The independent audit rehashed eight DS sidecars (524,288 bytes), 14 state/image
exports, both retained replay PNGs, six persisted artifact rows and 27 private
stored objects. All four within-case CPU comparisons and four raw-DS comparisons
matched, as did both replay PNGs and all 75 post-run source modules. Its sanitized
receipt SHA-256 is
`6c4a938197a8eb5d7e892af8ef182bbf936c4f1d527e1a17a224fb243ac7d6ac`.
The delta selection is supported by the recorded history and committed assertion;
the in-memory descriptors were cleared on close and were not separately archived.

The first setup attempt failed before injection because of an RPC address-format
error; its one backend exited normally and was reaped. After correction, an
earlier successful run established artifact survival. The final run repeated the
same operations while retaining actual replay PNG bytes for independent hashing.
All nine owned processes across these three attempts were reaped. Sealed receipts
from every attempt are retained; the failed setup is not counted as a crash.
Its original `failure_class` field carried the planned SIGKILL label before
injection; the address-format error, absent injection record and normal exit
supersede that label.

The final receipt is bound by these identities:

| Evidence | SHA-256 |
| --- | --- |
| Final native receipt | `5820aeda20e76c311131efde48836801c2c518c2e4ba8ad950cc91411ed41e0d` |
| Probe source | `4eec7153e3f49b2888f911b509d9b7d03b26e16637209893bc045ccd34621473` |
| Native backend | `a32b8285ea412413e9d60bf8b1c8735b9ee082b683a46dcba3fce65d47c47474` |
| Authored target | `64a5686a1c87d784aa59913b1ac1ac1de9486ce7cc3c9962531c49dfca8b4171` |

The three attempts and derived audit receipts occupied 4,901,336 bytes when
independently measured, within the approved 64 MiB allocation and preserving the
20 GB floor. The final local codec/timeline/interface regression selection also
passed 148 tests, separate from the native proof.
Source-module origins/bytes were checked against the declared Git commit before
launch and after execution. Pins survived this injected backend loss; unpinned
frame history did not. This does not qualify controller death, power loss,
arbitrary native applications, guest fault detection or general crash replay.

To repeat, select the exact qualified source above, an existing compatible
Python environment and verified native backend. Choose a new private external
output directory, obtain current storage admission and run:

```sh
PYTHONPATH="$FD_REPO/src" PYTHONDONTWRITEBYTECODE=1 TMPDIR="$FD_RUN/tmp" \
  "$FD_PY" -B "$FD_REPO/scripts/check_native_crash_recovery.py" \
  --backend "$FD_BACKEND" --output "$FD_NEW_OUTPUT" \
  --expected-head 1afeb55cfa9822874d2d4a9435ed972ce901e75d \
  --storage-admit "$FD_STORAGE_ADMIT" --max-new-bytes 50331648 \
  --wall-seconds 120 --destination-reserve-bytes "$FD_APPROVED_RESERVE" --execute
```

Without `--execute` it validates and prints a plan without creating runtime
output. The execution path has a 120-second deadline, a finite owned-process
ledger and final kill/wait cleanup. It never signals a process discovered by a
global search. This is one finite test, not a persistent monitor.

## Headless quit-dialog correction, November 3

An ordinary shutdown exposed a separate host-UI problem. The Python transport
sends SIGTERM and waits two seconds before force-stopping its owned emulator.
SDL can convert SIGTERM to a quit event; the headless backend's ordinary event
path then consults the default `quit warning=auto`. On macOS its confirmation
uses a separate AppleScript dialog process, which can remain orphaned after
the emulator is force-stopped. Headless video alone does not suppress that
native dialog.

At source `19c298edcae016e042a5e04f2267d61375d86831`, the transport now passes
`-set "dosbox quit warning=false"` only for headless launches. Explicit visible
launches keep their previous arguments. Subprocess-backed regression checks
failed for both default and explicit headless launches before the correction,
while the visible control passed; all three pass after the correction.

Fresh local macOS validation used the existing authored 512-byte COM fixture
and installed backend SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`:

| Launcher | Repeated native result |
| --- | --- |
| Source checkout at `19c298e` | Five fresh startup/bounded-run/shutdown cycles; every process exited normally with code 0, without the forced-kill fallback. |
| Locally hot-patched installed 0.31.1 | Five equivalent cycles; all exited normally with code 0 and no forced kill. |

Each cycle verified headless acknowledgement, the launch override and the
authored target's memory signature after bounded guest execution. No new
quit-warning helpers were observed after any cycle; both five-cycle runs began
and ended with none. Observed close times were 21–137 ms. All eleven owned
processes, including one earlier setup attempt, were reaped. That first attempt
requested an optional frame-timeline capability unavailable in this installed
backend; it was retained as a failed setup and its shutdown exited normally.
The successful repeats used ordinary bounded execution, not frame-timeline
qualification or the earlier full/delta crash experiment.

The source receipt SHA-256 is
`2f227abd72eb667be0212c736b42ed3c52135a840515b336398e583a721bb494`;
the installed receipt is
`36613d72b60fbbe078d323da920225dd8c3ea3b3bee10637682dcfec889c0100`.
The integrated local transport/debugger/codec/timeline selection passed
182 tests and skipped 21 optional-native or platform-specific checks.
The focused window-contract file separately passed 31 tests with two skips.
Native repeated shutdown is independently covered by the explicit runs above.

The user separately authorized an immediate installed hot-patch. The installed
transport now matches the source transport byte-for-byte, SHA-256
`b6112a55b710ca10de454f499e1c74a8dd6d684d9a71ddc8c36f31bd83f8c17e`.
Its original file, SHA-256
`c6f4ebcc66df1ffe5c1f3da6e8b5145f06f0fb7d399ad12be01c654353478a30`,
is backed up privately. The selector, native binary, package version and wheel
metadata were preserved. Consequently the installed payload is intentionally
locally modified, and its original wheel `RECORD` does not describe this one
patched file. This is an explicit local hot-patch, not a release or a pristine
release-payload verification. Existing Python controllers can retain the earlier
launcher in memory; fresh controllers use the patch.

One warning helper was cleaned up only after verifying its executable, owner,
orphan status, exact previously observed dialog command and unchanged identity
immediately before SIGTERM. Its exit was verified. The three helpers recorded
in the earlier investigation had already disappeared. No emulator or unrelated
AppleScript process was signalled during cleanup. Private process identities,
backups, databases and logs stay outside Git.

## What wrfuzz contributes to the methodology

The inspected reference is
[wrfuzz at `1fb1a8907700dcc48193b7535c62d85156862822`](https://gitlab.com/mscupcakegkill/wrfuzz/-/tree/1fb1a8907700dcc48193b7535c62d85156862822).
Its [engine](https://gitlab.com/mscupcakegkill/wrfuzz/-/blob/1fb1a8907700dcc48193b7535c62d85156862822/fuzz.c#L262)
separates an exception-derived crash result from a synthetic target result,
saves triggering input and resets per-execution coverage feedback. The useful
adaptations here are explicit failure classification, an exact reproducer and
clean state between attempts. A SIGKILL has no observed guest fault address;
inventing one would confuse backend loss with a target bug.

The [documented limitations](https://gitlab.com/mscupcakegkill/wrfuzz/-/blob/1fb1a8907700dcc48193b7535c62d85156862822/README.md#L230)
also explain why isolated fresh recovery matters: in-process exception handling
can leave heap contamination. Its SEH recovery wrapper is Windows-specific;
the non-Windows branch invokes the target directly. It is not a macOS fault
recovery implementation. Minimization and stronger crash deduplication are
listed as future work; their availability and the author's performance claims
were not assumed or reproduced. No wrfuzz code was installed, compiled or run,
and no GitHub source was accessed.

## Other evidence and remaining runtime questions

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
Those are offline/stopped-RPC contracts, separate from the injected native loss
proof above.

Guest faults/non-frame stops, controller loss and post-crash behavior before the
close path remain separate qualification questions. Any future probe should use
an authored target, precommitted artifacts, a declared failure oracle and one
guest owner, with fresh storage admission. No watcher, CI job, installation or
release is implied by this guide.
