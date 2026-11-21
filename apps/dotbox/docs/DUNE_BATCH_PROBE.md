# Dune: deterministic probe and memory-rewind batch

Measured 18 November 2026 (America/New_York; raw receipts use UTC).

The supplied English DOS RIP edition was executed in an isolated local native
guest. One scripted batch restored a common memory checkpoint, armed candidate
dispatch sites, delivered each declared input, recorded ordered hits and bounded
the observation window. No agent decision was made between its nine trials.

The reviewed **dispatch-only batch completed in 3.233 seconds** for nine trials,
plus **0.418 seconds** to create its checkpoint and validation baseline. A
separate full observation batch completed in **18.080 seconds**. It exercised six
visible controls, one empty command row, one idle comparison and one repeated
map command. All nine trials completed 120 renderer frames, or 1,712 guest
milliseconds each. The idle row ended with the declared no-hit timeout.

The [sanitized receipt](evidence/dune-batch-probe-2026-11-18.json) retains source
identities, timings, observed mappings, comparison witnesses and limits.
Original game files, emulator checkpoints, raw RAM and screenshots remain private.

## Exact scope and starting state

The frozen generic source baseline was primary commit
`c44b6ae47f4cfd604031059c1f968bb9384ed1c3`, mirrored independently as
`93a23777c43cdbced3362f9c00fbcdf77ac12266`, with tree
`231c8e94f1614faa31ff8230d5163ccd4b6a1c40`. Static Dune bindings and the batch
driver were added after that baseline. Prior assisted Dune CD exposure is
recorded in [DUNE_VALIDATION.md](DUNE_VALIDATION.md); this was not a blind test.

| Input | Recorded identity |
| --- | --- |
| User archive | `Dune_DOS_EN_RIP-Version.zip`, 1,780,417 bytes, 141 files |
| Archive SHA-256 | `9f9f9137a1af68ab155fa65b5e309c40d89fd2c9120b3de0ccb66fc4a1861b52` |
| Main executable | `DUNEPRG.EXE`, 74,757 bytes, real-mode DOS MZ |
| Executable SHA-256 | `32439602abe95e0ff778653ad58052bfed56a73e103b92f079455daa2ee886e7` |
| Native executable | fDisBull offline 0.34.1 Linux DOSBox-X agent |
| Native SHA-256 | `d9236f1178855524a74516eb37cbb636431f9bdec599d9d675e6d69ea6309251` |

The launch used `DUNEPRG.EXE ENG VGA EMS 386`, matching the arguments in the
supplied batch file while omitting its separate `LOGO.EXE` invocation. A normal
Escape keypress left the intro. No bundled saved game was loaded. The reference
view was the opening throne room with the map and Duke Leto command rows.
The observed code/data segments were `0824`/`16F3`. Those bindings are checked
against the live process and the exact file; they are not portable addresses.

Both batches use the retained fDisBull native executable. The first used its
research transport; the reviewed dispatch batch used DotBox's own
`dotbox.native_rpc.DOSBoxRPC`. The newer DotBox-owned native binary and
original-Dot desktop integration were not exercised. The reusable research
driver accepts an already-owned session-bound call adapter and contains no
fDisBull import. It is not a new player-facing rewind command or a release
qualification.

## What the full batch observed

All coordinates are original 320 by 200 frame pixels. Addresses below are code
offsets in the observed `0824` segment. Labels describe this starting context.

| Selected control | Input | Observed callback / row destination | Frame after the observation window |
| --- | --- | --- | --- |
| See Dune map | Left click `(160,163)` | `CE85`, row 0, then `1BBF` | Dune map panel |
| Duke Leto Atreides | Left click `(160,171)` | `CE80`, row 1, then `9DDC` | Leto portrait, text and conversation choices |
| Up-arrow control | Left click `(274,167)` | `4179` | Bedroom view with a mirror command |
| Right-arrow control | Left click `(289,177)` | `417E` | Exterior/balcony view |
| Down-arrow control | Left click `(274,186)` | `4183` | Leto interrupts the attempted departure with dialogue |
| Center control | Left click `(274,177)` | `1C36` | Local floorplan overlay |
| Empty third command row | Left click `(160,179)` | Generic paths `D2FE` and `D33D`; no admitted row dispatch observed | Throne room remains visible |
| Idle | No input | No armed probe hit in 120 frames | Throne room remains visible |
| Map repeat | Same map click after intervening trials | Same ordered sites, row and destination | Same image, registers and conventional RAM hashes |

The six visible controls were observed reaching their callback entries; the two
menu commands additionally reached their selected handler entries. The full
batch continued through those boundaries and captured the visible effects.
The down-arrow result is evidence for an intercepted transition, not proof of
the underlying story flag or a universally blocked exit.

The original log called `D33D` `generic_right`. This is a historical probe label,
not a right-click claim: every delivered click was left-button input. The
published mapping uses addresses or release-path wording. The blank-row trial
shows why generic input activity must be separated from an admitted command.

## Mechanical trial recipe

The live control table contains 23 rectangle records of 14 bytes each. Five
central command rectangles have small row wrappers that converge on the same
resolver. Only the first two were active in the observed throne-room context.
This supplied a bounded probe set without recovering the complete game.

For each declared trial, the script performs these steps:

1. Remove surviving probes that it owns, then restore the memory checkpoint.
2. Compare CPU registers and SHA-256 over conventional RAM `00000`–`9FFFF`.
   Record current mounted-file identities without replacing any file.
3. Advance one fixed settling frame with no probes. Restore invalidates the
   framebuffer, so this obtains a fresh frame and becomes part of the baseline.
4. Revalidate the code binding and arm the candidate sites together: `D326`,
   `CE8A`, `CE93`, `D2FE`, `D33D` and `D2C1`.
5. Queue the declared click using that fresh frame, or deliver no input for idle.
6. At `D326`, capture the selected control record and arm its callback entry.
   At `CE8A`/`CE93`, capture row, metadata and selected near handler; arm the
   admitted handler entry. These are fixed rules, not model decisions.
7. Record each owned one-shot stop and continue according to the profile.
   Bound completed frames and probe stops independently.
8. Save the result outside guest rewind, clean owned probes, then start the
   next row. On ordinary completion, restore the reference memory state again.

The recording contains first visits to the chosen sites and dynamically resolved
entries. It is not an exhaustive instruction trace or evidence that unprobed
paths did not execute. A breakpoint observes arrival before the target instruction
executes. Entry-only captures must not claim the handler's gameplay effect.

The reusable [experimental runner](../scripts/experiments/dune_probe_batch.py)
has full-observation and dispatch-only profiles. The latter stops at the useful
destination witness instead of waiting for every animation. Game interpretation
can happen after the completed batch; it is not in the mechanical inner loop.
It checks the exact opening-menu pointers, handler words and active row geometry
before accepting the fixed trial names and coordinates.

The reviewed dispatch profile reached all six control destinations and the
repeated map destination after one guest millisecond, before the first new
renderer frame. The blank row reached its generic fallback at that same point.
The idle row completed 30 frames, or 428 guest milliseconds, without a hit.
Each destination is recorded before its body executes; those screenshots cannot
replace the full pass's effect observations.

## Rewind and repeatability evidence

The initial batch performed nine per-trial restores and a final restore. All ten
matched the saved CPU registers and the 640 KiB conventional-RAM hash. Every
fixed settling step also produced the same RAM witness. After several different
actions, the repeated map trial matched the original map trial's ordered hits,
final registers, final conventional RAM and screenshot SHA-256.

The native operation uses the full-machine serializer. The independent equality
checks cover CPU registers and conventional RAM; they do not independently hash
every EMS, VGA or device field. Debugger revisions and probe identities remain
host metadata and are expected to change across restore epochs.

An authored file in the disposable mount was changed after checkpoint capture.
All restores preserved its newer contents. Hashes and sizes of all mounted files
were compared around each restore and trial, with no changes observed. No actual
game autosave was modified in these trials. This directly exercises the memory-only
boundary for this run; it does not yet qualify arbitrary changed/open save-file
cases, the later native generation protocol, or Police Quest's missed briefing.

The extracted `DUNE21S0.SAV` had already changed before the first checkpoint:
9,569 bytes in the supplied archive, 9,565 at the first baseline. Its baseline,
second-baseline and final hashes are identical. This bounds the change to the
pre-checkpoint startup interval; the exact write was not traced. The source
archive stayed unchanged. Thus the no-file-change claim applies to the measured
trials/restores, not to all startup activity in the disposable game copy.

The reviewed dispatch batch repeated the same ten-restore checks, including
guest-clock equality and neutral input after early stops with a pending click.
Its map repeat also matched ordered hits, registers and RAM. The old interactive
process handle became unavailable before this second run; the retained checkpoint
was recovered in a fresh owned native process and its original register/RAM
witnesses matched before the new batch was prepared. The one-shot process was
closed and reaped after recording a clean final probe inventory. This recovery
is recorded separately from the warm timing.

Later [continued play](DUNE_PROGRESS.md) exposed a narrower restore limit:
restoring this graphics checkpoint into a process still in DOS text mode can
match those CPU/RAM witnesses while preserving incorrect VGA memory handlers.
The initial restored image appears, but subsequent guest graphics writes do not
render correctly. Normally initializing Dune graphics before that restore passed
a later visible-action check. The native repair remains unimplemented. Treat
the comparisons above as the recorded CPU/RAM/clock evidence, not arbitrary
cross-process graphical-continuation qualification.

## Timing and failure limits

| Measurement | Host duration | Coverage |
| --- | --- | --- |
| Reviewed checkpoint preparation | 0.418 seconds | Edition/menu checks, memory save, witnesses and authored canary |
| Reviewed dispatch batch | 3.233 seconds | All nine trials, restores, probes, input, first useful entry/fallback, idle timeout, evidence and cleanup |
| Preparation plus dispatch batch | 3.651 seconds | Already loaded opening context and already learned bindings |
| Original full observation batch | 18.080 seconds | All nine trials, each continued for 120 completed frames |

Individual dispatch input trials took approximately 0.276–0.299 seconds;
the bounded idle trial took 0.676 seconds. Full observation trials took
approximately 1.92–2.08 seconds. Batch timings include restore, probe setup,
input, RAM/file checks, screenshots and final cleanup. They are single-run
measurements, not a performance distribution or a latency guarantee.

Preparation is separate. From the first logged native interaction to completion
of the first batch was **452.216 seconds**, including startup interaction,
target-specific investigation and script construction. Archive extraction and
some earlier preparation preceded that interval. This is not an 18-second cold
bootstrap or evidence that the first-run foreground buffering target was met.

The no-hit result is an exhausted **frame observation window**, with the guest
stopped and responsive afterward. It is not a deliberately expired transport
request. A pipe/RPC timeout leaves completion uncertain and terminates the
experiment without replay. Host guards are cooperative admission checks;
individual RPC and cleanup limits remain distinct and must be reported as such.

Independent review found two weaknesses in the initial private driver: ownership
matching relied on address alone, and an unexpected stop would have allowed the
outer loop to restore the next trial. Neither occurred: all 32 recorded stops
were independently matched to the created one-shot IDs and addresses, and final
probe inventory was empty. The reusable runner checks stop kind, ID, address and
consumption, and aborts the batch on an unexpected stop. Uncertain transport
failure permits no further calls. The initial private log remains unchanged.

## Consequence for incremental harness creation

Separate choosing an experiment from executing it. Once an agent has a current
context, a bounded candidate set and input recipes, the controller can complete
restore/arm/input/record/timeout mechanically. Retain the partial dispatch map
immediately. Agents can then investigate independent destinations or reuse the
observed table pattern to enumerate more candidates while ordinary gameplay
continues in its own guest.

The original game still determines current action availability and outcomes.
One navigation callback may lead to a room, dialogue or a guard-dependent result.
The map here supports the next hypotheses; it does not establish complete
conversation semantics, strategy orders, the simulation loop, callable deep
entry contracts or a complete Dune harness.
