# Scoped YM3812 and SB16 checkpoint graph

This incremental QEMU 10.0.13 package extends the exact
[SB16 DMA-service parent](../qemu-sb16-dma-service/README.md). The adjacent
[source manifest](source-manifest.json) pins that prerequisite, the nine-file
patch and every before/after source hash. Keep earlier runtimes for their own
producer-bound states. This package does not enable cross-binary snapshot
loading or change the default DOSBox-X backend.

## Explicit profile and saved state

Only the `sb16-opl` profile selects audiodev `fdisbull-sb16-opl` and the scoped
AdLib checkpoint property. Audio-core format 3 has one shared 32 kHz mono U8
none-backend output/capture graph: a mandatory AdLib 32 kHz signed-16 mono
software voice and an optional SB16 unsigned-8 mono/stereo voice in the
existing 5,000–45,000 Hz range. Initial inactive AdLib/no-SB graphs are supported
with an idle observer or an empty capture window. Ordinary PC-speaker format 1,
SB16 format 2 and unscoped AdLib paths remain separate.

The pointer-free synthesizer record retains nine channels/eighteen operators,
phase/envelope/feedback/rhythm state, address latch/register shadow, table
selectors, actual cached LFO depths and private noise state. Loading validates
all selectors and bounded scalar values before adopting state. Fresh OPL tables,
channel relationships and callbacks are reused; no guest OPL write, reset or
key-on sequence is replayed. Wrapper state retains its 1,025-sample buffer,
position/remaining contiguous extent, sample accounting, voice activity and
stock timer state.

Core format 3 preserves both software voices by stable card/voice identity,
their saved callback order, formats, volumes, resampler state and buffered
samples. It also retains the aggregate hardware ring/backend queue, pending
disable, capture and capture-voice state. All bounds, source records and
replacement geometry are validated and allocations complete before mutation;
the blob remains bounded to 8 MiB. The shared timer deadline is checked against
the separately saved device deadline after graph import, then restored without
advancing samples or executing guest code. Passive OPL query API 1 exposes
state hashes without emulating a guest port access.

## Reconstruction and qualification

Verify the prerequisite and each `before_sha256`, apply the pinned patch with
`patch --batch --forward -p1`, then verify every `after_sha256`. Work in a
separate source/build copy. The accepted macOS arm64 TCG recipe regenerates
QAPI/trace sources, performs 32 serial compilations including all 25 recorded
affected-header consumers, updates the copied archive and replays the retained
782-argument link/sign recipe. This is an incremental same-Mac build, not a
clean portable build or CI result.

The [dated qualification](../../docs/evidence/qemu-opl-checkpoint-2026-11-16/README.md)
records the exact tool/wheel/native tuple, authored pitch/status and mixed-graph
hot/cold checks, initial graph recovery, original Doom LE checkpoint/history
continuation and the passing independent closed SQL/CAS/input audit. The adjacent
[standalone synth harness](tests/opl-state-harness.c) additionally checks full
future PCM/state recovery with all channels/operators, cached-depth divergence,
pending DATA-only writes and atomic corruption refusal. Its exact-state oracle
qualifies persistence, not bit-accurate hardware audio.

## Limits

The scoped synth is YM3812 OPL2 only. It retains stock port-triggered AdLib timer
expiration and uses private checkpointed xorshift32 noise; neither is a hardware
fidelity claim. OPL3, MIDI, unsupported mode bits, general audio graphs, analog
fidelity and broader concurrent-device stress remain outside this gate. Mixer
amplitude/clipping laws are unchanged. Exact bounded continuation does not prove
general deterministic replay or paired DOSBox-X parity. DOSBox-X remains default
and retained; no CI, release, shared activation or installation is performed.
Commercial inputs, media, emulator states and byte-retaining project data stay
private.
