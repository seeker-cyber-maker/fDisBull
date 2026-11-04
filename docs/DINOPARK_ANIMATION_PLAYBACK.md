# DinoPark ACT animation and ABT playback profiles

These modules extend the [byte decoders](DINOPARK_MEDIA_DECODERS.md). Sequence
operand decoding, supported interpreter semantics, authored presentation and
observed original-gameplay graphics/sound remain distinct evidence surfaces.
The modules never patch an executable or rewrite an original resource.

## Inspect sequences and simulate explicit ticks

```text
fdisbull media-inspect /private/actor.ACT --adapter dinopark-act-sequence
fdisbull dinopark-animate /private/actor.ACT --program 0 --tick 0 --tick 1 --tick 2
```

Sequence inspection follows the original operand reader, including signed and
big-endian operands, biased relative branches and variable-command lookahead.
The report includes instruction boundaries, authored mnemonic interpretations,
local flow candidates and unsupported runtime opcodes. It excludes original
program, operand and scratch buffers. An operand shape is not a qualified
instruction meaning; a local successor is not a whole-game flow graph.

`fdisbull.dinopark_animation.AnimationRuntime` accepts a decoded ACT resource,
optional program indices and a bounded per-actor instruction budget. Its profile
uses an initially zeroed 16-record actor bank with explicit initialization time,
display mode and optional positions; defaults are zero. The supported operation subset comes from the earlier attributed
DinoMart/ABOUT research runtime and the retained original-code contracts. The
extension implements all 32 operation families observed in the supplied corpus;
all 48 programs in eleven resources are admitted. It includes finite-width
motion, forward/reverse/ping-pong/custom-frame cycles, coordinate and endpoint
waits, signal writes/branches and draw arguments. This is an observed-vocabulary
subset, not a general interpreter for every possible ACT opcode or scene context.
Unknown operations and invalid program/sprite/branch extents refuse. State
updates commit only after a successful bounded tick; that host failure policy
does not claim the original game's malformed-input behavior.

```python
from fdisbull.dinopark_images import decode_act
from fdisbull.dinopark_animation import AnimationRuntime

runtime = AnimationRuntime(decode_act(original_bytes), program_indices=[0])
first = runtime.tick(0)
second = runtime.tick(1, signals={0: 1}, hidden=0, suspended=0)
```

Time, signal words and actor masks are caller inputs. No wall-clock rate is
invented. Rendering requests precede scheduling in a tick; a frame selected by
the script may first be drawn on the following update. Draw tuples contain
sprite index, drawing mode, coordinates and drawing flags; they are not images.
The Python API also exposes separate `update(time)` and `schedule(time)` phases
for normal consumers whose clock advances between those calls. Display modes
alter cached widths and do not imply a host color calibration. The CLI provides
`--display-mode`, `--initial-time` and repeatable `--initial-position X Y` inputs.
It accepts at most 128 explicit ticks and does not invoke callbacks, draw a
scene or serialize packed original RAM records. Use the Python API for explicit
signal/visibility inputs. Palettes, clipping and display composition require
their own qualified adapter.

## Bind ABT to the original consumer and driver

```text
fdisbull media-inspect /private/sample.ABT --adapter dinopark-abt-playback
fdisbull media-decode /private/sample.ABT /private/new-audio --adapter dinopark-abt --playback-profile dinopark-digpak-sbpro-mono-v1
```

This explicitly selected profile binds the supplied original DINOPARK.EXE and
SBPRO.COM default unsigned-eight-bit mono route. It does not infer a profile
from an extension. The game copies the little-endian ABT word at offset two to
the DigPak descriptor's frequency word at offset ten, then calls INT 66h service
068Bh. The selected driver's mono path computes the DSP command-40h time
constant from the integer divisor `floor(1,000,000 / requested_rate)`.

The module reports both requested PCM timing and exact rational ideal device
timing. For example, a request for 22,000 Hz has divisor 45, time constant 211
and ideal device rate `1,000,000 / 45` Hz. These values must not be collapsed
into one rate. DOSBox's device implementation may round the timer rate before
mixing; mixer interpolation, filtering, gain and startup/IRQ tails are separate.

The WAV uses the requested integer rate with the exact decoded sample sequence.
Its manifest preserves the rational device rate/duration separately. Selecting
a profile cannot be combined with `--sample-rate` or `--channels`. Existing
explicit caller-authored WAV adapters remain available without a profile.
Other drivers, dynamic stereo, interrupted/looped playback and arbitrary header
rates outside the non-wrapping divisor domain refuse or remain unqualified.
The three other ABT header bytes remain opaque.

## Observe actual mixer output

The separate optional [audio capture backend overlay](../experimental/dosbox-x/audio-capture.patch)
adds `audio.capture.start`, `audio.capture.status` and `audio.capture.stop` to an
explicitly selected compatible DOSBox agent. It is not automatically installed
or enabled by the Python tool. Start requires a stopped owned session and a
four-byte-aligned limit of at most 4 MiB. The capture is owned by that session
and a unique capture ID. The emulation thread records the stock mixer conversion
to signed sixteen-bit little-endian stereo independently of host speakers.

```python
from fdisbull.dosbox_audio import start_mixer_capture, stop_mixer_capture, write_mixer_wav

started = start_mixer_capture(rpc, session_id, max_bytes=4 * 1024 * 1024)
# Continue the original guest through a bounded ordinary-input route, then stop.
captured = stop_mixer_capture(rpc, session_id, started['capture_id'])
write_mixer_wav(captured, '/private/new-observed.wav')
```

The stop helper checks session/ID, encoding, source, sample rate, frame counters,
clock interval, complete frame alignment, byte budget, base64 and SHA-256. No
uncertain request is retried. Reaching the byte limit closes a truncated capture
without pausing or modifying the game. A closed window is not evidence that a
game sample completed. Changing/restoring a session invalidates stale capture
ownership. The helper's report has hashes/scalars; PCM stays in the private API
object or an explicitly requested new private WAV outside Git.

## Unused and malformed-resource claims

The prior list recorded absent literal filename references, not proven unused
assets. The follow-up audited all 96,768 existing ACT/PIC/ABT paths under the
private DinoPark project root, collapsing them into 125 byte identities for 126
canonical resource names. All unique resources and all twelve earlier media
candidates decoded unchanged. No malformed alternate was found within that
search boundary. One pair of filenames shares identical ABT content.

The historical UNC2-only sprite reader rejects BUS.ACT and PEOPLE.ACT with
`not a UNC2 file`. They are valid legacy UNCS resources, accepted by the current
decoder and earlier original-raster comparisons. Those old refusals establish
an unsupported variant, not corruption. This is a concrete reproduced refusal;
it does not identify every file a user may remember from another investigation.

Original files, native states, captures, exact code maps and raw receipts remain
private. Source and packages contain authored implementation, authored fixtures,
methodology and sanitized claim boundaries only.

## Normal-gameplay verification

Fresh original-game runs used ordinary new-game and mouse interactions through
the office, land purchase and DinoMart. They installed no guest instructions and
made no host RAM/register edits. All 183 original files and runtime input copies
remained unchanged. Normal graphics evidence is deliberately bounded:

- Eight DinoMart sequence pointers were bound to their exact original resource
  programs. Thirty-six clock-quiescent update/scheduling phases matched their
  modeled entry/exit contracts across three fresh runs. Twenty-three phases
  whose clock crossed during the call remain unqualified. These are separate
  phase comparisons, not a whole-trajectory equivalence claim.
- Final-module replay of the unchanged observations also matched nine ordered
  draw groups containing 52 tuples. Two initial groups lack a complete entry
  marker and mix initialization draws, so their ordering remains unqualified.
- The T-REX sign's visible and hidden states each matched all 1,314 pixels in a stored native
  73-by-18 region. Source composition uses the original picture frame, sprite
  indices/opacity and `replicate6` palette expansion. The region ends at the
  observed higher-order actor's occlusion boundary; its covered sprite pixels
  and transparent/background pixels are both included. This is not a full-scene,
  all-palette, clipping or mirroring qualification.

Five distinct ABT consumers were observed during startup or gameplay. Expanded
PCM matched completely. Passive driver observations matched requested frequency,
default mono mode and programmed DSP time constants. During normal land-plot
purchase, POPP1 played 3,264 samples at requested 22,000 Hz/time constant 211.
The original cleanup boundary followed 146 guest milliseconds later; the ideal
payload model is 146.88 ms, with a one-millisecond observation clock.

Actual mixer PCM was recorded with the dummy host audio driver. A source-derived
resampling and pinned default-device filter model, using fixed alignment and
explicit affine gain/DC parameters, was compared densely over all 123,312
expected startup payload frames and all 7,051 gameplay payload frames. Dense
correlations were 0.999528 and 0.976240. Header-rate controls were 0.139484 and
0.853621; a deliberately wrong rate gave 0.110173 and 0.222782. These are
approximate waveform/timing checks, not bit-exact mixer equality. Recorded tails
outside the modeled payload, other mixer/device configurations and physical
speaker output remain unqualified.

The optional stable capture backend was built and tested on macOS ARM64. Its
overlay source also replays on the layers base; that variant was not compiled or
run. Authored native checks cover a PIT-derived tone, byte-limit truncation,
requested stop, state-load invalidation, natural target exit, stale IDs and
paused observer invariants. The installed shared backend is unchanged.

## Prepared original-core corpus comparison

A separate fresh original-DOS matrix covers every embedded program in its
original resource grouping: eleven resources, 48 programs, two declared input
profiles and 192 logical ticks per case. All 22 cases matched:

- 8,448 original update/scheduler calls and 18,432 actor-ticks;
- 36,864 complete 234-byte actor phase snapshots, signal buffers and AX results;
- 14,388 ordered draw requests and the same number of device-pump requests.

This is an assisted context-zero/display-zero core fixture. It prepares audited
original data fields, supplies explicit clocks with interrupts disabled, and
places the program and fixture-stack banks outside the complete file-backed
image/data span inside verified DOS-owned memory. After strict original
CALL/argument/return checks, draw and device-pump service entries are redirected
to an existing original RETF. Those 28,776 declared service bypasses install no
stubs or instruction patches, but they do substitute host-service behavior.
The result qualifies core state and ordered requests, not unmodified complete
routine execution, actual drawing, event pumping or ordinary gameplay.

Every case restored the full loaded image exactly, with no changes outside its
enumerated data whitelist, and retained exact program/stack guards. All 183
original and runtime-copy files remained unchanged, and all owned guests were
reaped. A read-only replay independently recomputed every retained phase from
the final module. Finite corpus profiles do not exhaust all clocks, branches,
signal producers, contexts, reset/lifetime behavior or host presentation.

Private acceptance selector SHA-256:
`b521f73242be64ecd3ec809585fb92876489130384e793badef0d34294b70da6`.
Normal-gameplay evidence remains the separate 36-phase/52-draw/2,628-pixel check.

## Tool verification and remaining host failures

The 71 authored animation cases include 28 independently authored boundary tests.
The complete fresh suite has 9,370 passed, 317 skipped, five failed, 23 fixture
errors and 2,316 passing subtests. Failure/error identities match the previous
run. Three compiler/filesystem failures and all 23 errors have prior reproduced
baseline identities. Both unchanged LLDB timeout cases also failed in one fresh
focused current arm and one fresh focused baseline arm; their exact host timing
cause is unknown. The full suite remains non-green.

The isolated wheel's 572 source files match the frozen source. All seven
installed inspection/simulation/export/catalog checks and the selective skill
gate pass. The installed PNG export recomposes both sealed native image regions
exactly; the selected profile's WAV preserves its requested integer rate and
complete PCM bytes. The catalog retains all prior 133 format/15 module rows and
adds two modules with three links, for 17 reader/profile modules. No shared
installation, release or hosted native-CI qualification is implied.
