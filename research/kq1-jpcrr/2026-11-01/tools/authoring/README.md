# Headless authoring with stock JPC-RR 11.2

This is a thin front end to the unmodified JPC-RR engine. It records ordinary PC keyboard edges, pauses execution for observations, and saves native JRSR movies. It does not implement an emulator, replace AGI, write guest RAM/registers, change clock rates, patch firmware, or inject game commands through a debugger. Its output must still be replayed and checked with the unmodified stock `PCRunner`, without this front end.

Source review and compilation succeeded on Java 17 against the official `jpcrr-r11.2.jar`. `--help` was exercised. The authoring-module agent did not execute a guest. Native replay and timing results belong in the parent experiment's evidence, not in this compilation claim.

## Build and launch

Only the stock JAR and a Java runtime with the `jdk.compiler` module are needed. No `javac` executable, display server, or Java dependencies are required.

```sh
java --module jdk.compiler/com.sun.tools.javac.Main \
  -cp /path/to/jpcrr-r11.2.jar \
  -d /path/to/authoring/classes \
  /path/to/authoring/src/kq1tas/HeadlessAuthor.java

java -cp /path/to/authoring/classes:/path/to/jpcrr-r11.2.jar \
  kq1tas.HeadlessAuthor --library /path/to/disklibrary
```

An optional `--capture /new/path/capture.jmd` loads the stock `RAWDumper` plugin before execution. Its output uses the native timestamped JMD stream. Capture filenames cannot contain commas or parentheses because the stock plugin parses its argument string. All output paths must be new; existing files are preserved. A capture that spans multiple loads is an authoring-session recording with concatenated segments; create the timing/acceptance encode from one fresh final-movie replay instead.

Use a single driver, with stdin and stdout pipes and stderr redirected to a log file. The front end owns stdin; do not also load it into the interactive `JPCApplication` console. `client.py` provides a small Python standard-library driver. JVM and stock-core diagnostics go to stderr; stdout contains JSON replies only.

## Protocol

Each request is one line with literal tab separators and no tabs or line endings inside a field. The first stdout line is a ready message. There is one JSON reply per nonempty request, with `ok`, `command`, and command-specific fields. Exceptions return `ok:false`, `error`, and `message`. No game execution occurs while waiting for the next request.

Integer arguments are decimal or `0x` hexadecimal. All emulated timestamps and durations are **nanoseconds**. All addresses are physical conventional-RAM addresses below `0xA0000`. Device-memory inspection is deliberately unavailable: even reads of VGA memory can change unrecorded hardware latches. The optional host budget is **milliseconds**.

| Request fields, separated by tabs | Behavior |
| --- | --- |
| `load`, path, `movie` | Load using `PC.loadSavestate(..., false, true, previousStatus)`, forcing power-on initialization even when the source also contains a savestate. Does not reuse the previous input stream. Remains paused. |
| `load`, path, `state` | Load a native JPC state when present, including its original event history; otherwise initialize from the movie. Remains paused. |
| `info` | Current emulated ns, VGA frame, dimensions, input count, next pending event, final input timestamp, and executed pressed keys. |
| `run_until_ns`, target, optional host-budget-ms | Execute toward the absolute target using stock `TraceTrap`. Return actual time and stop reason. A call advances at most 60 emulated seconds. |
| `next_frame`, optional host-budget-ms | Stop at the next VGA retrace-start trap after stock display update, or after the 1-second emulated fallback deadline. |
| `keyedge`, scan-code, earliest-ns | Append a stock `Keyboard KEYEDGE`, returning the actual timestamp selected by `EventRecorder`. |
| `truncate_future` | Explicitly discard pending future events at the current point; retain already executed inputs. Needed before branching from a movie that contains future inputs. |
| `read`, address, length | Read a range wholly inside conventional RAM below `0xA0000`; reply contains hexadecimal bytes. |
| `dump_ram`, address, length, path | Read the same range and write a new raw file. |
| `registers` | Read current x86 registers and CS/DS/SS/ES selectors/bases. No setters are exposed. |
| `snapshot`, path | Save the current VGA display buffer as a new PNG without redrawing or changing guest state. |
| `events`, first-sequence, count | Inspect up to 10,000 existing movie events, including native save markers. |
| `save_movie`, path | Use stock `PC.saveSavestate(..., true, false)` to write initialization, headers, disk information and input events, with no savestate start. |
| `save_state`, path | Use stock `PC.saveSavestate(..., false, false)` to save a native authoring checkpoint. |
| `header`, KEY, optional value fields | Replace a supplementary movie header; KEY alone deletes it. Core system/project/state/rerecord headers cannot be edited. |
| `quit` | Return current status and gracefully close stock capture plugins. EOF also closes gracefully. |

The host budget defaults to 30,000 ms and must be 1–60,000 ms. It is checked after each stock `PC.execute()` batch, so it is cooperative, not a hard process timeout. A response with `reason:host_budget` is a partial advance; the driver may issue the same absolute target again. `time_ns` is always the actual engine time. Native instruction/timer granularity can put it slightly beyond the requested target. A triple fault is reported explicitly. `next_frame` uses VGA display frames, not AGI logic cycles or an assumed 60 Hz.

`KEYEDGE` toggles a key; the initial state is normally released. A press and release are two edges. This interface accepts the documented normal/extended scan-code ranges. The stock keyboard imposes its own timing grid and serial transmission spacing. The requested time is a **lower bound**, not a promise: the recorder also clamps to current time and the previous movie input. Inspect `scheduled_ns` and the final event stream. Calling `keyedge` never silently deletes an existing movie's future.

Event sequence counts include native savestate markers. Loading the same project supplies the previous status to the stock loader so its rerecord counter can advance across repeated loads, while the requested file supplies the input stream. A new project starts with that project's count. This is recorder metadata, not a measure of the number of agent decisions or test attempts.

`snapshot` at an arbitrary time shows the most recently completed stock VGA image. Use `next_frame` first when a fresh display frame is needed. The saved PNG timestamp is observation time; the native JMD stream is the source of precise presentation timestamps. Slow host inspection does not advance the paused emulated clock.

## Python example

This is an authoring example, not a claimed completed run:

```python
from client import Author

with Author(jar, disk_library, new_log_path) as author:
    author.command("load", original_movie, "movie")
    result = author.run_until(3_000_000_000)
    while result["reason"] == "host_budget":
        result = author.run_until(3_000_000_000)
    state = author.command("registers")
    # Decide actions from read-only observations; no AGI assumptions in this module.
    author.command("truncate_future")
    press = author.command("keyedge", 28, result["time_ns"])
    author.command("keyedge", 28, press["scheduled_ns"] + 1_000_000)
    author.command("save_movie", new_movie_path)
```

Loading a published movie retains its headers and input history. Preserve attribution for reused input and change headers honestly for new work. For example, `header`, `AUTHORS` deletes that header; it does not remove other author-related headers. Creating a movie with this front end is not a claim of publication acceptance or a new record.

## Independent playback and timing

Replay the saved movie using the stock JAR alone, with exact matching disk/BIOS IDs and the same machine settings. A stock autoexec can load `org.jpc.plugins.RAWDumper(rawoutput=...)` and then `org.jpc.plugins.PCRunner(movie=...,stoptime=...)`. Keep the interactive stock console's stdin pipe open until playback exits; it does not handle immediate EOF cleanly. The external classes must be absent from this replay's classpath.

Check final game state, inputs, timestamps and visible completion against the original reference. When encoding JMD, preserve its presentation timestamps and resolution changes. Report separately: input-movie duration from power-on; an explicitly defined gameplay interval; visible completion time; and host computation/authoring time. The final input time is not necessarily the moment the ending becomes visible.

## Native lesson: an early effect is not completed interaction

The first gnome greeting exposed a real false-completion boundary in the route
assistant. In original room 40 logic, code offset `0x111` sets flag 22 (the name
challenge has begun), then `0x113` prints message5 (the introduction). There is
a real interval after the flag changes but before the message window opens.
Checking `flag22 == true` and `window == 0` at one arbitrary CPU stop can accept
that interval. A matching state predicate is necessary but does not by itself
prove the interaction, output, and input-consumption sequence has finished.

In the retained native failed control, step 52 was incorrectly accepted at
**9.629737250 seconds** with flags 2, 4, and 22 set and window 0. The next `GET KEY`
inputs were scheduled while the greeting was entering its print. The output
captured under step 53 was still the introduction, and the guess counter stayed
at 0. This was an assistant synchronization error. The original game did not
reject a properly delivered first guess.

The original interpreter's instructions qualify the parser flags directly:

| Observation in original executable | Captured physical address | Meaning |
| --- | --- | --- |
| Store nonempty parsed-word count and set flag 2 | `0x38424`–`0x3842F` | Parsed input is available to the logic |
| Test flag 4 clear and flag 2 set before matching words | `0x37448`–`0x37454` | A `said` test must have available, unconsumed input |
| Set flag 4 after the full word match | `0x3748B`–`0x37490` | A `said` test consumed/matched this parse |
| Reset flags 2 and 4 in the next main-loop input phase | `0x36C41`–`0x36C52` | Previous parser-cycle status is cleared |

These addresses refer to the passive RAM capture at emulated 2.88 s, CS base
`0x36AE0`, DS base `0x40A30`, SHA256
`85802319daa5eee98649f0552945511f962e981d1bc10edd502437acc4013659`.
The shared bit-addressing routine at `0x3DF2A` uses DS+`0x109` and MSB-first
flag numbering. No guest memory was altered to inspect these instructions.

The authoring driver now requires the intended effects, a closed window, and
flags 2/4 cleared, followed by an additional 3 ms of stable observations. It
captures observed output, dismisses that window once, and continues observing
before sending a new parser command. The 3 ms interval is a conservative
authoring choice retained in the movie; it is not a universal engine theorem.
Game scripts can manipulate these flags, so output and scene-specific effects
remain required. The corrected greeting contract explicitly includes the
settled parser flags. Historical HI snapshots with flags 2/4 still set establish
the early flag effect only and are not classified as completed readiness.

The expected counter progression remains source-grounded: greeting leaves
`v84=0`; first recognized wrong guess prints message 19 then increments to 1;
second prints 20 and 21 then increments to 2; third creates the fallback key,
prints 22, then assigns 3. The fourth `GET KEY` picks up that key and leaves the
counter at 3. Source offsets in this paragraph are code-relative offsets, not the
resource-header-inclusive offsets in the census JSON.

The corrected native continuation then matched that sequence. Retained
`route-authoring-2/authoring-events.jsonl` receipts show the following settled
states, all with window 0 and parser flags 2/4 clear:

| Step | Native time | Guess counter | Committed result |
| --- | --- | --- | --- |
| 52, greeting completed | 9.684437250 s | 0 | Challenge active, score 12 |
| 53, first wrong guess | 9.782803050 s | 1 | Challenge remains active |
| 54, second wrong guess | 9.932385400 s | 2 | Both response windows completed |
| 55, third wrong guess | 10.033033900 s | 3 | Fallback key branch, `v83=2` |
| 56, key pickup | 10.133299600 s | 3 | Item 5 carried, `v85=1`, score 15 |

These are native observations from the corrected authoring continuation, not a
whole-game result or an independent final-movie replay claim.

## Native lesson: room identity precedes scene initialization

The cave transition demonstrated a second false-completion boundary. At
12.032846600 s, `v0` already said room 73, while the actor still had the old
position `(75,160)`, normal view 0, width 6, neutral directions, and flag 98
clear. Those values remained stable for 3 ms. They did not represent a
completed landing: the new room had not yet initialized its fall sequence.
The premature continuation even let `OPEN BAG` succeed during the later fall,
then stopped at the original landing output. The failed control is retained.

Original `new.room` clears each actor's drawn and animated bits **before**
writing the new room number, then loads room resources and later sets flag 5.
The relevant captured instruction addresses are `0x38296` (clear bits `0x41`),
`0x382E8` (write `v0`), and `0x38373` (set flag 5). Thus an instantaneous
`!flag5` can mean either "initialization has not begun" or "its first logic
cycle has finished." Original `draw` sets actor bit `0x0001`, and `erase`
clears it. Actor bit `0x0040` means animated; it is a separate property.
These actor bits are distinct from the global game flags with the same numbers.

Room-transition waits now combine an actor that has been drawn, flag 5 clear,
and source-specific entry or recovery evidence. The original ownership word
at DS+`0x139` is also available: `program.control` writes 0 and
`player.control` writes 1. Variable 6 and actor direction describe movement;
both being zero does not by itself prove player control. `new.room` itself
sets the ownership word to 1 before changing the room number, so ownership
alone cannot prove scene initialization either.

For the front-hole branch, room 73 must first be observed in its initialized
fall or recovery phase: previous room 48, x 90, flag 98 set, and view 105, 103,
or 104. The source starts with view 105 at `(90,63)`, changes to view 103 for
the landing message, then view 104 for the recovery animation. Only afterward
does it return to view 0, clear flag 98, and restore player control. The
corrected native continuation observed the initial fall at 12.073446600 s and
completed recovery at 12.666846600 s at `(90,139)`.

The earlier failed control also established that the original parser permits
`OPEN BAG` during the fall: its diamonds and score effects committed at
12.134246200 s while view 105 and flag 98 were still active. Issuing the command
early and then waiting for full recovery is an optimization candidate. It
still needs a complete timing comparison: modal output can pause animation,
so a legal overlap does not automatically save elapsed game time.

Room 76's branch from room 75 has a distinct initialized position `(113,146)`;
its clover entry message executes while flag 5 is still set. Room 36's branch
from room 78 sets the mushroom timer to 0, adds the exit point, places tiny
Graham at `(110,131)`, and moves him toward `(88,131)`. It changes to normal
view, prints the regrowth message, and only then clears flags 120 and 20.
The route contracts retain these ordering distinctions.

`route_support.transition_evidence(step_id, state, history)` provides pure
observation-history accumulation for steps 80, 95, and 117. Its history is
separate from instantaneous postconditions; no unobserved historical phase is
invented from a final screenshot. A short stability interval supplements
these semantic guards and does not replace them. Discard history after every
checkpoint load, rewind, or new attempt. The optional `attempt_id` binds it to
an identified branch, and decreasing timestamps are rejected. The helper
cannot discover a restore that the caller does not report.

## Stock API basis

The bundled official source archive `sources.zip` supplies the contracts used here:

- `PC.loadSavestate`, `PC.saveSavestate`, `PCFullStatus`, `PC.execute/start/stop/getTime`.
- `EventRecorder.addEvent`, `truncateEventStream`, `setPCRunStatus`, and event inspection.
- `TraceTrap.setTrapTime` and `TRACE_STOP_VRETRACE_START`.
- `PhysicalAddressSpace.getByte`, readable `Processor` fields and `Segment` accessors.
- `VGACard.getOutputDevice/getFrameNumber` and `VGADigitalOut.getBuffer/getWidth/getHeight`.
- The unchanged `Plugins` manager and `RAWDumper` plugin.

The only core state mutations requested by this front end are normal loading/saving, run/pause/trap control, input recording, and movie metadata changes. There are no memory/register writers, guest patches, clock-divisor setters, or emulator accuracy hacks.
