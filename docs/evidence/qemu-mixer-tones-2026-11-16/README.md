# Passive mixer gains and paired tones — local qualification

The native QEMU engine now exposes stopped software-voice gains through
`mixer_observe()`, JSON `debug-mixer-observe` and script `mixer-observe`.
Two authored tone cases run the same COM bytes on QEMU and DOSBox-X, with
independent pitch/channel checks and normal guest completion. **2,198 installed
host cases and 28 distinct native cases pass**, with zero failures/errors/skips.
These gates evaluate this bounded slice, not migration completion.

DOSBox-X remains default and retained. No CI, release, merge or shared
installation/activation occurs. Existing OPL/FM, SB16, CPU/RTC/DMA timing,
trials, histories, layers, hooks, checkpoints and IRQ contracts are preserved.
Mixer math, gain application, channel conversion and native state formats do
not change. Full 1:1 audio parity remains open.

Pi-DOS's [mixer readback](https://github.com/rtomasa/Pi-DOS/blob/d8f7e697d0e559d758b7c2ac2bb3c925ff684f1f/src/runtime/mixer_control.h)
and small audio probes prompted this slice. This implementation uses the
existing QEMU graph and a new authored guest; no Pi-DOS code/assets are imported.

## Observable software gain

Capability `mixer_gain_readback` requires optional native command
`x-fdisbull-query-mixer` API 1 and an explicit virtual-clock audio profile.
Older binaries retain their existing operations. The stopped query returns
actual audiodev/card/voice names, mute and exact left/right Q32 software gains,
source/HW formats, activity/draining flags and existing capture descriptors.
Unity is `4294967296 / gain-scale`, or 1. There is no invented master control,
default voice or inference that guest SB mixer-register writes were applied.
`software-volume-applied` distinguishes software scaling from backend volume.

The Python wrapper validates identities, integer geometry/gain bounds and
clock brackets under the shared machine lock/deadline. It preserves both
ordinary/protected history and selected-undo read-only guards. Host tests
exercise real QMP envelopes, database persistence, malformed replies, missing
capability, transaction refusal, shared deadlines and unchanged history cursors.
An initial missing-route check failed before implementation; the finished
routes and hostile-receipt checks pass.

The native handler only validates/copies the existing graph under BQL while
stopped. It never flushes samples, changes gain, activates voices, runs the CPU
or rearms a timer. Removing its new query/include reproduces the parent audio
source exactly. Only that C file and the private QAPI audio schema change.
The [native package](../../../native/qemu-mixer-observe/README.md) retains source
before/after hashes and a reconstructable delta. The existing integer mono
duplication/sum-then-clip law is reported, not corrected.

DOSBox-X's retained native RPC has no equivalent passive mixer query. The test
records that absence instead of invoking shell `MIXER`, which updates volume
state. Its reference binary/default mixer/recording format remain unchanged.

## Same program, independent audio expectations

The original homegrown 17,289-byte COM accepts OPL-only or SB16-only arguments.
Every final run uses SHA-256 `c903924f5470d3e9c38a4406c5a3722af1197b52bcad2d2483b34c4c2c46d7db`.
Native breakpoints bracket the authored ready/done labels; the actual sound
phase runs once without intermediate clock-budget stops or capture restarts.
Guest reports verify phase, DSP identity, IRQ7 completion and cleanup. The
IRQ7 vector and original PIC mask are restored; IRQ0/PIT remain intact.

| Case | Independent input | Observed result |
| --- | --- | --- |
| OPL | YM3812 FNUM 580/block 4 predicts 439.9906 Hz; six BIOS tick transitions followed by key-off/tail | Approximately 440 Hz on both engines |
| SB16 stereo | 32 kHz U8 source, periods 64/40 and unequal bounded amplitudes | QEMU mono retains both 500/800 Hz components; DOSBox left/right retain the respective components with channel dominance |

The four final guests exit through normal DOS completion code 42; all native
owners close/reap with code 0 and no owned group members remain. QEMU retains
zero dropped frames. Its raw output remains 32 kHz mono U8; DOSBox's finalized
WAV is 48 kHz stereo S16 through native `DX-CAPTURE /A /-D`. QEMU gain snapshots
show actual unity software scalars and unchanged stopped CPU/ns/instruction
counts around observation. Voice presence changes only through guest/device
execution and restore, not readback.

Whole recordings remain untrimmed at native rates. Pitch detection alone
subtracts the mean and uses fixed expected-frequency searches; raw DC-inclusive
RMS, DC and native sample-limit counts are separate. The OPL gate additionally
requires meaningful signal strength, rejecting a dominant wrong tone with a
weak expected-frequency residual. No time/gain fit, resampling, synthesized
silence, equal-waveform requirement or cross-engine CPU comparison is used.
Independent whole-record NumPy FFT and scalar calculations confirm the signals;
coarse FFT bins and the 1 Hz component-search grid are distinct estimators.
All four final recordings have zero native sample-limit hits. This is not a
claim that Doom's earlier DC/sample-limit differences have been fixed.

## A transfer-length difference retained as evidence

The first paired acquisition exposed a frame-unit assumption in the fixture
description. Its buffer holds 4,096 stereo frames, but command C0h with length
0x0fff requests 4,096 eight-bit **channel samples**, or 2,048 stereo frames.
That convention is specified in Creative's
[Hardware Programming Guide, section 6-24](https://pdos.csail.mit.edu/6.1810/2017/readings/hardware/SoundBlaster.pdf#page=109).

The current QEMU source deliberately doubles this single-cycle stereo block
length for an inherited Miles Sound Systems compatibility behavior; it leaves
the auto-init branch separate, explicitly mentioning Doom. DOSBox follows the
documented count in this fixture: its DMA address advances 4,096 bytes and its
8,192-byte buffer has count 4,095 remaining. QEMU's final DMA counters wrap;
those registers alone do not prove how many bytes were consumed. The native
source branch and retained audio/report evidence establish the differing
models; no hardware reproduction or new device fix is claimed.

The corrected test adds explicit request units and strict DOSBox DMA-progress
assertions. Its guest source literal and COM bytes are unchanged; no frequency,
channel, IRQ, exit or passivity gate is weakened. The initial acquisition and
finding remain retained, and repeated cases are not counted twice. Equal
transfer extents/durations remain unqualified. This is an existing compatibility
difference exposed by the test, not a readback-induced regression.

## Preservation and exact candidate

The candidate uses tool source `641a90e7…`, a 714-file wheel/private prefix
`779ddbd6…`, and native binary `055b58eb…`. Test-only unit clarification is
`9500b0b5…`; production payloads remain identical. The separate incremental
macOS arm64 build performs 30 serial compilations, including the recorded
generated-header consumers, then updates nine archive members and replays the
retained 782-argument link/sign recipe. Source reconstruction and 2,161 declared
build inputs rehash correctly. This is not a clean portable build.

The 28 distinct native cases comprise 23 existing SB16/RTC/media/mouse,
checkpoint/layer/frame-key, cascade/nested-IRQ, history and trial/undo cases;
one combined OPL/SB16 case; two initial OPL graph parameters; and two paired
tones. The combined hot/separate-Python cold restores and strict 600 ms futures
now include exact native mixer payloads alongside full exposed CPU, OPL/SB16,
PCM/chunks, virtual time and instruction count. Initial inactive/absent voices
and idle/armed capture graphs also restore and reproduce their tone future.
The host suite's sole warning comes from an intentional duplicate ZIP member
in a malformed-archive test.

Independent retention checks preserve the old 713-file package/native binary,
original inputs, prior Doom database and all 588 CAS objects, plus the earlier
paired Doom recordings/analysis. This slice runs authored guests, not another
commercial Doom campaign. Earlier qualified artifacts remain bound to their
original producer; unchanged state wire layouts do not authorize cross-binary
loading.

The [sanitized verification record](verification.json) contains exact identities,
aggregate observations and receipt hashes. Raw recordings, states and FDB/CAS
stay private. Calibrated gain, physical audio fidelity, DC conditioning, stereo
capture, long/rolling capture, OPL3/MIDI and full DOSBox-X parity remain open.
