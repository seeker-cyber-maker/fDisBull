# KQ1 replay and rewind comparison on macOS/ARM64

The recovered JPC-RR evaluation replays successfully on this Mac. Automatic
fDisBull rewind reduces checkpoint bookkeeping, but its current full-state
capture has a substantial per-frame cost. The evidence supports using a durable
Anchor Stone plus a short automatic timeline around uncertain inputs.

This is a local, prepared-state comparison, dated 2026-11-01. Exact numeric
results and private-receipt hashes are in [measurements.json](measurements.json).
The complete recovered ZIP is retained as the private upload linked in the
[parent README](../README.md); its authenticated readback is byte-identical.
No game media, native states, raw RAM or screenshots are committed here.

## Fresh stock replay

The unchanged stock JPC-RR 11.2 JAR, matching original media identifiers and
Homebrew Java 21.0.13 ran on macOS 27.2/ARM64. Both the Java VM and DOSBox-X
candidate were freshly checked as ARM64 Mach-O binaries. The replay JAR hash is
`be63fea4c746ec3823432b7e2ef27b19b75a25a4bcbbc124f4683d99c4f4d314`.
The four stock runs use PCRunner/RAWDumper directly, without the authoring helper.

| Complete input movie | First host run | Repeat host run | Native capture |
| --- | ---: | ---: | --- |
| Automatic, 63 points |53.381 s |54.996 s |15,828,730 bytes, both exact original-capture matches |
| BOW, 66 points |54.183 s |58.334 s |15,862,773 bytes, both exact original-capture matches |

Each native recording spans 35 emulated seconds and logs 2,450 frames. All four
exit 0, with unchanged movie/JAR inputs and no critical native log lines.
Both repeated pairs are byte-identical; each also matches the corresponding
capture from the archived Linux/Java 17 evaluation. All five runtime files,
including original and copied media, retain their initial hashes.

Independent exact-RGB landmark scans and local visual inspection confirm the
king-steps-aside modal and credits, with scores 63 and 66 respectively. First
modal times are 32.736528222 s and 32.351288898 s; first credits times are
33.378593764 s and 32.864941331 s. Each immediately preceding frame fails the full
modal-window comparison. These are native movie timestamps, separate from host
elapsed time. This confirms the delivered movies; it does not authenticate
Robb's original 9.89-second movie/settings or establish a new record.

## Warm input loops

Each timed unit accepts a physical keypad-5 make/break pair, advances one native
frame, and observes CPU plus 65,536 bytes of conventional RAM. There are 4 warmups
and 32 timed samples per mode. The two JPC-RR runs use fresh JVMs and an external
Python controller around the unchanged authoring helper. The four fDisBull modes
use the same warm session and frozen MR !30 source
`865542a26b5406b2bc81e0e3bc7c542a287eec25`, with candidate-v3 backend
`a32b8285ea412413e9d60bf8b1c8735b9ee082b683a46dcba3fce65d47c47474`.

| Controller and recording mode | Loop median | Loop p95 |
| --- | ---: | ---: |
| JPC-RR, no per-frame state/image |22.256 ms |25.129 ms |
| JPC-RR, external full-state history plus PNG each frame |121.379 ms |134.701 ms |
| fDisBull, recording off |21.311 ms |21.699 ms |
| fDisBull, manual dense Anchor Stones plus PNG |234.668 ms |277.825 ms |
| fDisBull, automatic full-state timeline |252.488 ms |258.630 ms |
| fDisBull, coarse Anchor plus active timeline |252.065 ms |258.725 ms |

These totals describe the individual controllers and are **not a normalized
cross-emulator speed comparison**. JPC-RR stops at VGA retrace start and spaces
the two key edges by 1 ms; DOSBox stops after a completed renderer frame and safe
CPU fetch and queues both edges before execution. JPC-RR uses a ready early-game
scene; fDisBull uses the prepared rat-room Anchor. Hardware settings, wire
encoding, observation processing and logging/output-guard costs differ.
The scripts establish accepted/dispatched inputs and frame progress; game-level
key consumption remains unknown for these keypad-5 probes. Model/network latency
is excluded. API/RPC counts are local operations, not model turns.

Within fDisBull, equal-work checks are stronger: all four aligned initial DS
hashes match, all 36 corresponding CPU/DS observations match, and all four endpoint
PNG hashes match. All 32 timed samples per mode complete exactly one frame and
release the input pair. Manual state/image capture alone has a 213.228 ms median.
Automatic capture occurs inside timeline advancement and cannot be removed from
that mode's core cost. The current MR !30 timeline stores **full native states and
images**; this is not a benchmark of MR !16 CPU/memory deltas.

The fixed mode order and 32 correlated samples support descriptive medians and
nearest-rank p95 values. They are not independent-trial confidence intervals.

## Return and retry practicality

Every fDisBull mode returned to the prior observed CPU/DS state and reproduced
the same subsequent pair/frame result. Single observed return costs were:

| fDisBull mode | Return to prior point | Return plus retry and verification |
| --- | ---: | ---: |
| Recording off, coarse seed load and replay |598.054 ms |624.288 ms |
| Manual dense Anchor Stones |20.438 ms |267.968 ms |
| Automatic timeline |33.660 ms |297.507 ms |
| Coarse Anchor plus active timeline |31.754 ms |292.207 ms |

The return values are one check per mode, not repeated timing medians. Recording
off has no retained recent state, so its return loads the seed and replays the
known inputs. Dense manual capture and automatic rewind both restore retained
full states. Automatic rewind improves access to recent points and branch
management; it does not make the underlying full-state restore faster here.

Across 32 timed loops, manual dense capture used 256 caller operations and 736
backend dispatches; automatic timeline used 192 caller operations and 768 backend
dispatches. The timeline keeps bounded live RAM history and automatically records
input/frame associations. Manual capture requires naming and retaining durable
state/image pairs. A pinned Anchor Stone survives the live session; an unpinned
timeline does not.

JPC-RR completed 9 retry trials per run, at depths 1/3/5 frames with 3 trials each.
Restored time/frame, RAM projection, exposed registers, pressed keys and actual
PNG hashes match for anchor restoration, repeated segments and endpoint loads.
Baseline endpoint-load medians are 39.348/34.887/35.037 ms. JPC-RR can support this
workflow, but the measured helper's history, file names and branch handling are
maintained by the external Python controller. Its fixed power-on input movies
provide the independently verified complete-route replay in this evaluation.

For narrow agent experiments, keep a durable Anchor Stone at a useful boundary,
enable a bounded timeline around the uncertain input window, rewind by a small
frame count while trying alternatives, then pin the useful result. Stop dense
recording outside that window. The combined row above leaves the timeline active
throughout its measured window, so adding an Anchor does not remove its capture
cost. A short-window policy is a workflow recommendation, not an extra measured
performance result.

## Selective RNG safeguard

In the real prepared rat room, a natural RNG transition occurred at frame 6:
63,240 to 33,942. Full rewind restored the prior CPU/DS; replay reproduced the
subsequent DS hash. A selective return kept 33,942 while the other 65,534 DS bytes
matched the prior state. The mixed state was frozen: execution and safe resume
were false, and attempted advancement was refused without changing DS. Full
Anchor Stone recovery restored the seed DS. This run did not continue the mixed
state or qualify whole-machine equivalence. The warm probes do not constitute a
new rat/bag handoff or a complete fDisBull route run.

## Review, preservation and publication

Independent read review corrected the measurement harness before its first
fDisBull guest run: it now sends both edges and includes CPU observation in the
timer. No fDisBull production source was changed. Post-run review independently
recomputed all timing summaries, cross-mode CPU/DS and image equality, return and
retry projections, RNG safeguards, and receipt/file identities. The original
FDB, preparation receipt, backend, helper, controller, 24 game files and five loaded
modules retain their recorded identities. All owned native processes exited 0
and were reaped. The fDisBull run completed 195 controller frames.

GitLab draft MR !37 contains this research import/comparison. Recovered Zork scene
work is preserved separately in draft MR !36 with its three integration conflicts;
it remains separate from main. MR !14, !16 and !30 remain unmerged. GitHub, Linux and
hosted CI, releases, installation changes and merges were not used for this run.
The user's additional 1 GiB allocation and 20 GB minimum reserve apply to these local
outputs; storage admission was rechecked before material growth phases.
