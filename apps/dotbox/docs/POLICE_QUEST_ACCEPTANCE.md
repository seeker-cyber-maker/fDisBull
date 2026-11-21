# Police Quest controls and memory-rewind acceptance

Selected by the user on 17 November 2026: change in the locker room and reach
the showers to qualify controls; miss the briefing and rewind to qualify
recovery. **One ordinary-input functional controls run passed on the cloud
Linux computer on 17 November 2026.** Sonny changed into the towel, closed the
locker, reached the usable shower and successfully turned it on; the shower
was turned off afterward. Reusable harness and timing qualification remain
open. **The missed-briefing memory-rewind trial has not run.** This document
contains the edition-bound specification, static investigation and bounded
live result; it does not add a game adapter or a rewind API.

## Recorded local controls result

The [sanitized controls receipt](https://github.com/seeker-cyber-maker/DotBox/blob/codex/local-macos-build-20261117/docs/evidence/police-quest-local-controls-2026-11-17.json)
binds this run to the EGA resources, source tree and newly compiled Linux native
executable. One coordinator used the default desktop service and ordinary
keyboard input. Fresh native-window observations showed the lobby, locker-room
entry, assigned locker, changed outfit and return to the room. The final
shower interaction produced the game's success response and visible water;
an ordinary turn-off command removed the water effect. No guest memory edits,
teleports, game-load action or filesystem rollback was used. All 27 recorded
original and isolated-copy input file hashes remained unchanged.

The route required live correction. Arrow keys latched movement, while repeating
the same direction stopped motion in an unchanged room. The current keypad
mapping entered a digit when the center key was tried, so it was not adopted as
a stop control. NPC conversations interrupted movement. The shower picture's
collision barrier required a western approach followed by eastward movement;
head-pixel estimates were insufficient at the final interaction boundary.
The original game's response established arrival, rather than an inferred live
coordinate or flag value.

This was an exploratory functional run using retained guide/static findings.
It did not measure cold preparation, a complete movement/turn trace or player-
visible delay breakdown, and it did not satisfy the opening preparation budget.
No reusable route revision or live engine-state adapter was qualified. The
separate shell namespace could not read the desktop service's temporary token;
the run therefore makes no CLI lease-observation claim. Original-Dot takeover
synchronization, repeatable harness execution and the full instrumented
acceptance below remain separate work. The eight native fixture passes are
recorded independently in the [Linux native receipt](https://github.com/seeker-cyber-maker/DotBox/blob/codex/local-macos-build-20261117/docs/evidence/local-linux-native-2026-11-17.json).

## Bind the edition and the two starting states

The inspected original is **Police Quest I EGA 2.0G, DOS AGI 2.917**. The supplied
GOG installation also contains the SCI/VGA remake at its root; the original
resources are in its `EGA` directory. Root `VERSION=2.000` is not the identity
of this AGI target. Bind the executable and selected resources before applying
these findings. The inspected `LOGDIR` SHA-256 is
`bb8a07fb13a6af30ab587110ee4dfec66fb11f850776be8fdf5d3d55cedda0ec`;
this one hash is a useful cross-check, not a complete compatibility check.

Use separate controls and recovery starting states. Reaching the shower while
wearing a towel is a controls endpoint, not permission to leave for the briefing
in that state. Prepare the briefing checkpoint with the appropriate uniform,
first briefing still pending, and enough measured guest-clock headroom. The
controls exercise does not require completing a later story chapter first.

The original manual's opening walkthrough collects equipment and attends the
first briefing; a shower is not a mandatory opening prerequisite in that route.
The VGA opening and later EGA shower sequences must not be mixed into one
assumed script. The selected shower exercise is useful on its own.

## Controls: change, close the locker, walk to the shower

1. Establish the current input owner, edition, room, clothing, position and
   foreground/input-ready state. Retain the start observation and control
   revision. Use the game's ordinary controls throughout.
2. Approach and open Sonny's locker. Perform the ordinary clothing-removal
   interaction and observe its committed result. In the inspected ordinary
   branch, the locker close-up is room 47 and the change writes `v39=4`.
   Do not write that value or the actor coordinates to make the test pass.
3. Close the locker and observe the return to the locker/shower overview,
   **room 5**. Wait for the transition's actual input-ready state.
4. Walk to the usable shower approach, using long clear legs and bounded
   position feedback. Stop through the qualified movement controls and obtain
   a fresh completed frame and state observation.
5. Pass only when the clothing change and arrival are both observed, with no
   unaccounted input, takeover, collision or location change. Record movement
   time, turns, genuine foreground delays and any fallback used.

Static location clues for this edition are `LOGIC 5@388`, which checks ego
position inside x=90..106, y=90..96 and sets `f232`, and `5@372`, which clears
the unsuitable-clothing flag `f233` for clothing values 4 or 7. The ordinary
change selects 4; value 7 belongs to another story branch and must not be used
as an interchangeable fixture. These are AGI game coordinates, not screen or
mouse coordinates. They propose an arrival predicate; they do not qualify a
path, collision footprint, live address or screenshot recognizer.

**LOGIC 39 is a called locker-room helper, not a shower room.** Treating every
referenced LOGIC number as a destination would produce the wrong scene graph.
The locker close-up returns to room 5 through `LOGIC 47@2216–2233`.

Turning on the shower is a separate optional interaction, beyond the user's
requested arrival endpoint. If included, observe the on/off effect (`f70` at
`5@544/565`) and leave it off afterward. The other shower has a distinct
unavailable/occupied response; do not count arrival there as success.

## What the first briefing timer actually tests

The first briefing is not controlled by one wall-clock delay. The inspected
scripts separate the engine clock, a room-local elapsed counter, an event
countdown, and the briefing's phase/completion state.

| Mechanism | Static finding in the inspected resources |
| --- | --- |
| First-briefing selection | Room 4 selects LOGIC 44 while `v98=0` and `f119` is clear (`4@10–23`). The later briefing selects LOGIC 45 under different conditions. |
| Late arrival | On entry to the first briefing from lobby room 6, `v12>=5` while the briefing is incomplete sets room-local late flag `f239` (`44@16–32`). `v12` is the AGI minutes variable. This is not five minutes after entering the locker room or closing the newspaper. |
| Late outcome | With the late flag set, the first briefing reports lateness and sets end/failure flag `f140` after room counter `v120>5`, on a sampled second change (`44@147–164`). Waiting outside alone is not the visible failure assertion; enter and observe the specific late outcome. |
| Briefing start | An ordinary on-time entry from the lobby initializes event countdown `v140` randomly in 60..180. A non-lobby return, including closing newspaper room 116, assigns 3 (`44@112–126`). This accelerates the start sequence; it does not reset the late-arrival clock. |
| Countdown sampling | LOGIC 0 compares seconds `v11` with cached `v133`; a change increments `v120`. It decrements `v140` only when recent-key activity flag `f110` is clear, and signals an event when the result reaches 1 (`0@1024–1123`). The assigned value is not an exact number of remaining real seconds. |
| Input effect | Recognized key changes can temporarily inhibit that event countdown. Enter clears the inhibition, as does more than one observed second change without renewed activity. This is not a reset of the engine minutes or a reason to keep typing to evade the deadline. |
| Room changes | Entry setup clears local counters and flags, including `v120`, `v139`, `v140`, `v141` and `f138`; it does not reset the engine clock in the inspected opening path (`100@44–113`). |
| Successful recovery endpoint | Completing the first briefing sets `f119` and advances `v31` to 1 (`44@957–959`). Observe the original game's successful sequence as well; these static sites alone are not live evidence. |

Variables and flags are separate namespaces: countdown **`v140`** is not
failure flag **`f140`**. Likewise a LOGIC resource number is not necessarily a
room number. Keep these distinctions in the provider mapping and test receipt.

The script's lateness message uses fictional shift times. Do not convert those
times into a real-time waiting period. The source establishes the `v12>=5`
condition, but this investigation has not measured when the original DOS
interpreter starts its clock, pause/modal behavior, or elapsed host time under
the selected emulator settings. Its live clock must be observed.

## Rewind: demonstrate failure, restore time, then succeed

Use a neutral-input checkpoint in the lobby before the first briefing, with
the first-briefing branch active, appropriate clothing, no active failure, and
the guest clock comfortably below the late threshold. Record the actual clock
and phase; do not choose an arbitrary number of host seconds as a substitute.

1. **Establish the checkpoint.** Through the qualified controller, capture the
   complete memory/machine state, including clock/device state, and its source,
   session and input identity. Record the coherent predeadline observation.
2. **Make current disk data distinguishable.** After capture, create or update
   and close a test save or harmless mounted-file sentinel in the isolated
   acceptance session. Retain its newer bytes/hash. This exercises the explicit
   requirement that changed closed files survive memory revert.
3. **Miss the briefing naturally.** Remain outside until the actual late-entry
   predicate is reached, then enter normally and observe the specific late
   outcome. Use bounded observations and a trial timeout; do not patch clock
   values, speed up the guest, spam input, or classify an unrelated clothing or
   position failure as lateness.
4. **Restore memory.** Revert the checkpoint through the fenced recovery path.
   Keep current disk files, discard old movement/input admission, and create
   a fresh scene branch/context and observation store. Retain the failed attempt
   and its learned control information as history.
5. **Verify restoration before input.** Observe the earlier guest clock and
   predeadline phase, with the late/failure state cleared according to the
   checkpoint. Verify neutral device input, a fresh completed frame, and that
   the newer closed disk file still has its newer bytes. A historical frame or
   restored position alone cannot establish success.
6. **Prove useful recovery.** Reacquire the current ownership turn, enter the
   briefing in time, take the proper position, and observe completion. Confirm
   the restored clock resumes normally rather than immediately catching up to
   host elapsed time and retriggering the deadline.

Both branches matter: the unreverted attempt must visibly fail for lateness,
and the restored attempt must remain playable and complete the briefing.
An original-game Load action or resetting a timer variable does not pass this
memory-rewind test. Neither does merely loading a checkpoint without recovering
the opportunity to attend.

## Measure before assigning a duration

During qualification, keep host monotonic elapsed time, guest clock values,
room-local counters, phase/flags and logical observation order separate.
Characterize ordinary idle play, movement, command entry, an in-game message,
explicit game pause, and a stopped emulator as distinct cases. Do not assume
all visible dialogs pause either the clock or every script counter.

Official ScummVM source identifies `v11..14` as seconds/minutes/hours/days and
shows a message loop that updates its engine clock, while explicit pause uses a
pause token. It also documents a deliberate difference from Sierra's original
subsecond behavior. These are useful implementation references, **not a timing
qualification of the original DOS executable**. Inspect the actual selected
guest. A long tool call or agent deliberation is not an implied game pause.

Keep the trial within a recorded work/time bound. Stop with an explicit
unverified result if a coherent live clock or the qualified recovery path is
unavailable; never manufacture the deadline or mark static analysis as a pass.

## Evidence and current limits

The retained census was freshly matched against nine selected source files and
all 118 LOGIC payload hashes. A separate read-only site check decoded the current
resources and verified 34 operations and 16 conditions; input hashes and mtimes
were unchanged. The coordinator reran that check and read the relevant control
flow. That initial static investigation executed no original game, movement,
clock timing or native restore. The subsequent local controls run above adds
observed game progression; it does not add live clock or native-rewind evidence.

- [Original Sierra manual](https://www.sierragamers.com/wp-content/uploads/2019/12/Police_Quest_1_Manual.pdf), printed pages 20–21: newspaper, assigned position and first briefing sequence.
- [AGI walkthrough](https://sierrahelp.com/Walkthroughs/PQ1AGIWalkthrough.html): corroborating opening and later shower sequences; its prose is not a timer specification.
- [ScummVM clock variable definitions](https://github.com/scummvm/scummvm/blob/502dc222115f801702996b386f3e416e7346c1e3/engines/agi/agi.h), [clock update](https://github.com/scummvm/scummvm/blob/502dc222115f801702996b386f3e416e7346c1e3/engines/agi/global.cpp), [message loop](https://github.com/scummvm/scummvm/blob/502dc222115f801702996b386f3e416e7346c1e3/engines/agi/text.cpp), and [explicit pause](https://github.com/scummvm/scummvm/blob/502dc222115f801702996b386f3e416e7346c1e3/engines/agi/op_cmd.cpp), pinned for comparison only.

The public record contains authored structural notes and hashes, not original
game scripts, assets, saves, messages or raw runtime dumps. See
[recovery](RECOVERY_AND_SAVES.md) for the implemented native control fence and
the still-unqualified complete restore transaction.
