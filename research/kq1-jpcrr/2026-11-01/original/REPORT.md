# King's Quest I: accepted-tool TAS evaluation

Date: 2026-11-01

## Result

The independently authored Robb-style route now completes in **stock JPC-RR
11.2** from a power-on input movie. It reaches the same visible endpoint as
Robb's clip — “You move aside as the King steps from his throne” — with all
three treasures and **63 points**, and continues to the full credits.

A separate ordinary **BOW** variant reaches that same visible message **0.385239324
seconds sooner**, scores **66**, and reaches the complete credits **0.513652433
seconds sooner**. Both variants were replayed twice in fresh stock-JAR-only
processes. Each pair of complete native audio/video captures is byte-for-byte
identical.

**This does not reproduce Robb's 9.89-second time.** The recreation takes
29.891690004 seconds from the recorded intro-dismissal key to the matching
king message; BOW takes 29.506450680 seconds. It is a verified experimental
recreation using an accepted TAS tool, not an optimized record or a submission
accepted by TASVideos.

## The two videos

- `video/KQ1-JPC-RR-Automatic-63-Points.mp4`: the 63-point route and automatic ending.
- `video/KQ1-JPC-RR-BOW-66-Points.mp4`: the same prefix with the ordinary BOW shortcut.

Both videos play at **1×**, include boot and the full ending, and retain the
original timestamped PC-speaker signal. They last 34.985001 seconds, including
a short hold on the final credits. Their first captured video event (0×0, before pixels are available) is at native
15 milliseconds, so video-player time is native power-on time minus 0.015
seconds. The final one-microsecond duplicate frame is encoding bookkeeping,
not an additional game frame.

## Timing: explicit boundaries

All following source timestamps are the emulator's native integer nanoseconds.
Visible endpoints mean the first complete captured native VGA image, not an
inferred script instruction or a rounded frame-count calculation.

| Measurement | Automatic, 63 points | BOW, 66 points |
| --- | ---: | ---: |
| Power-on → complete king-steps-aside message | 32.736528222 s | 32.351288898 s |
| Final intro Escape press → same message | 29.891690004 s | 29.506450680 s |
| First newly authored gameplay key → same message | 29.235829896 s | 28.850590572 s |
| Power-on → complete final credits | 33.378593764 s | 32.864941331 s |
| Final intro Escape press → complete credits | 30.533755546 s | 30.020103113 s |
| Last keyboard edge in complete-game movie | 33.323066766 s | 32.823005100 s |
| Last keyboard edge in king-endpoint-only movie | 32.035146312 s | 32.290010430 s |

The final intro Escape **press** is at `2,844,838,218 ns`; its release is at
`2,845,504,878 ns`. The first new gameplay key, the `f` in `FAST`, is at
`3,500,698,326 ns`. These are reproducible input boundaries. Neither is claimed
to be an independently adjudicated leaderboard start rule or the exact instant
the game enabled control. The intro-key interval includes subsequent loading
and retained idle time; the first-gameplay-key interval excludes that idle.

The endpoint-only automatic movie stops supplying input earlier, then waits for
the game's timer. BOW adds inputs and reaches the visible endpoint sooner. Thus
**last input and visible completion are different metrics**. For the complete
movies, BOW also moves the last required input earlier by **0.500061666 s**.

## Actual host wall time

The host monotonic timer was measured from process launch through exit, including
JVM startup, emulation, native capture and shutdown. Each run captured the same
35-second native timeline. The four emulator processes ran sequentially.

| Fresh replay | Measured host duration |
| --- | ---: |
| Automatic, first | 66.869211883 s |
| Automatic, repeat | 66.515641507 s |
| BOW, first | 67.662908548 s |
| BOW, repeat | 67.884776130 s |

The sandbox computed these recordings at roughly half real-time speed. The
delivered videos show their native timeline at 1×. Host processing time is
reported separately because a slower or busier host changes capture speed
without changing the movie's recorded game timeline. This is a shared host,
not a controlled hardware performance benchmark.

## Why JPC-RR is an appropriate tool

TASVideos lists JPC-RR as an accepted DOS rerecording emulator. Its published
King's Quest I submission **8484**, by DrD2k9, uses JPC-RR 11.2, game version
2.0F and a power-on start. The site's movie rules require reproducible playback
on an accepted official emulator and disclosure of synchronization settings.

Primary references:

- [Accepted DOS tool and setup](https://tasvideos.org/EmulatorResources/JPC)
- [Published KQ1 submission 8484](https://tasvideos.org/8484S)
- [Movie rules and reproducibility](https://tasvideos.org/MovieRules)
- [Official 11.2 binary archive](https://files.tasvideos.org/emulatordownloads/tastools/jpcrr-r11.2-precompiled.zip)

The exact official JAR used here has SHA-256:

`be63fea4c746ec3823432b7e2ef27b19b75a25a4bcbbc124f4683d99c4f4d314`

The machine uses divider 50, 16 MiB RAM (MEMORYSIZE 4096), initial RTC 10000, VGA timing method 1,
BasicFPU and SoundCard modules, with all **15 initialization rows** identical
to the qualified reference. Exact rows, disk identities and file hashes are
retained in the movie audits and `evidence/input-identities.json`.

The reference uses its documented **original BIOS identity**
`740f01be58103af0996220bdeb7c4d12`, not the later BIOS-updated download's identity.
The conversion of that reference restores the documented original BIOS
identifier while retaining its exact input event bytes; it is explicitly
recorded in `provenance/original-bios-variant.json`. This is not a game or
firmware patch. The complete candidate initialization matches this qualified
original-BIOS reference.

## Reference control and Robb comparison

The existing published-reference replay was independently rescanned. Its
first complete king message is at **13.988214419 s**, its final keyboard event
at **14.294723718 s**, and its complete credits at **14.373453744 s**. Both
image landmarks exactly match the earlier retained evidence. This control
establishes that the stock replay/capture path can reproduce the known run.

That reference is a different optimized route: its submission describes using
the back entrance and avoiding the clover. It is not the route recreated here.
Its successful short playback also means the recreation's longer duration
cannot simply be attributed to JPC-RR being slow to compute on this host.

Robb's direct primary clip is
[Kings Quest 1 TAS speedrun in 9.89 (no audio)](https://www.youtube.com/watch?v=DgW6hNJZjxQ).
The user-supplied [OneShortEye documentary](https://www.youtube.com/watch?v=KPlKetNSAtE)
is a separate reference. Saved video evidence shows the direct clip's timer
stopping at the king-steps-aside modal, rather than the later credits.

Robb's clip identifies DOSBox ECE r4319 at 157600 cycles and visibly uses a
restore followed by restart in its preparation. Its original input movie,
save state, exact game hashes and complete key schedule have not been
authenticated here. The current run starts from power-on in JPC-RR with its
own explicit clock settings. A DOSBox cycle setting is not assumed equivalent
to JPC-RR's divider. These differences prevent a claim of a byte-exact
reproduction or a directly comparable new record.

The recreated route preserves the principal interactions: rock/knife, clover,
pouch, failed gnome guesses and fallback key, mushroom, front cave, rat payment,
shield, small exit, giant's chest, well and bucket, water thrown at the dragon,
mirror, castle and king. The exact failed-guess strings in the original clip
remain unknown; the authored route uses its verified ordinary GET KEY guesses.

The current movie retains conservative neutral stops, precise waypoint checks,
short observation intervals and 30 ms display holds before dismissing observed
dialog. Those emulated delays remain in the fixed movie. Authoring pauses on
the host do not become game time, and failed rerecording branches are discarded
through normal emulator checkpoint loading. A quantified breakdown of all
remaining optimization opportunities was not performed.

## What BOW changes

The two variants have an identical **1,660-edge input prefix** through the
shared throne-room checkpoint at `32,035,330,750 ns`. In the automatic branch,
the original timer leads to the king's message. In the alternative, ordinary
movement reaches `(86,113)` and the parser receives `BOW`.

The original game awards three points and performs its bow animation and
response. After that response is dismissed, it advances the king sequence.
The result is score 66 rather than 63. The comparison includes the extra movement,
typing, animation and response. No game state is directly edited.

This particular fixed-input comparison saves **27 captured VGA intervals**
to the matching king message and **36 intervals** to complete credits. Those
differences are measured from native timestamps, not by assuming 60 Hz. The
later credits difference also includes the ensuing original movement and
ending dialogs; it is not all attributable to skipping the initial timer.

## Verification and its scope

1. All four exported movies passed the ordinary-keyboard, power-on structure
   audit. They contain no embedded starting savestate. Historical rerecord
   markers are metadata, not playback restore commands.
2. All 15 initialization rows were independently reparsed and compared. The
   24 borrowed boot edges through 2.845504878 s match DrD2k9's reference and are
   explicitly attributed in movie headers. The boot-prefix F5 occurs before
   the C: and KQ1 launch commands; it is not an in-game intervention.
3. Four fresh processes ran the official JAR alone with stock `PCRunner` and
   `RAWDumper`. The adaptive authoring classes were absent from the playback
   classpath. All runs exited zero without timeout or critical errors.
4. Movie, JAR and media hashes were freshly checked. Direct full-file byte
   comparisons independently confirm equality within each repeated native
   capture pair: **15,828,730 bytes** for automatic and **15,862,773** for BOW.
   Each contains 2,450 native video frames through 35 s.
5. The first complete king and credits windows were found by exact RGB matching
   of their full fixed modal rectangles. Every preceding frame was decoded
   and checked. Matching and immediately preceding PNGs were visually reviewed;
   each predecessor lacks some or all of the completed modal.
6. Video encoding was checked against every native PTS and packet duration.
   The maximum timestamp quantization error is 500 ns. PC-speaker rendering
   uses the native signal timestamps at 48 kHz, with no playback-rate change.
   Audio muxing leaves all video payloads/timestamps unchanged and verifies
   AAC priming compensation. Preview audio is lossy AAC; the original native
   event signal remains in the included JMD captures.

The repeat comparison proves equality of captured audio/video, timestamps and
container bytes over this interval. It is not a comparison of every hidden
machine state, a general proof over other RNG seeds, or publisher acceptance.
This continuation was verified on Linux/Java 17; no macOS run was performed.

## Corrections made while continuing the interrupted run

The continuation recovered the native checkpoint after LOWER ROPE. Its failure
was in the author's completion check: live lowering ends at VIEW17 loop 0 cel 5,
whereas cel 2 is a different room-entry pose for an already-lowered rope. The
check was corrected from source/resource evidence. No game code changed.

A later native arrival in room 7 was two pixels above the old candidate's
assumed start. Adding two ordinary downward steps to `(29,50)` before its
existing diagonal avoided the room's scripted water rectangles. The final
movie replays this successful path; failed trials are retained only in the
authoring history. `evidence/continuation-changes.json` and the helper diff
record both findings.

## Replay and inspect

Use the exact JPC-RR JAR and matching disk images identified by the movie.
The played HDD identity is `bd183c472bf2c054bfa944a768f10592`; the VGA BIOS is
`5555c682e62336cb37eb17c903322be1`; FreeDOS disk 0 is
`f334bc4d5dc5f393feb0ca2d1e1cdc25`. Original game and firmware images are not
included in this evidence package.

```sh
python3 tools/run_stock_replay.py \
  --jar /path/to/jpcrr-r11.2.jar \
  --library /path/to/disklibrary \
  --movie movies/KQ1-Robb-Route-63-complete.jrsr \
  --out new-automatic-replay \
  --stop-ns 35000000000 --host-timeout 300
```

Substitute the BOW movie for the alternative. The `*-endpoint.jrsr` movies
stop supplying input at the Robb-style landmark sequence; the `*-complete.jrsr`
movies include the six ending-dialog dismissals needed to reach credits.

The package retains both complete native captures, the reference control,
four input movies, landmark images, timing/static/replay/encoding receipts,
authoring histories and source, attribution, and a file hash manifest.
Some raw receipts preserve original absolute workspace paths; package paths
are listed in `README.md`. Authoring requires the original game resources;
replaying the fixed movies requires only the stock tool and matching images.

## Continuation knowledge pack

**Outcome:** accepted-tool power-on replay and measured visible timing are
complete; both variants synchronize twice and reach full credits.

**Architecture:** ordinary input authoring → native JRSR movie → independent
stock playback → native JMD → timestamp-checked 1× preview.

**Decision:** preserve these frozen movies as baselines. Any further speed
work should keep the same machine settings and compare matching endpoints.

**Next useful work:** replace conservative stop-at-waypoint authoring with
continuous steering, reduce unnecessary retained display waits, and resynchronize
each changed segment. Match Robb's exact input/save/build only if those
original artifacts can be authenticated. No new record is currently claimed.
