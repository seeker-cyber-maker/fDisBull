# Scoped digital SB16 checkpoints

This incremental QEMU 10.0.13 patch adds the explicit `sb16` audio profile over
the exact [input-completion stack](../qemu-input-checkpoint-completion/README.md).
The adjacent manifest pins prerequisites and every changed source member.
Build into a new private directory; preserve the qualified old runtime for its
existing checkpoints. No cross-binary saved-state compatibility is claimed.

The profile selects `fdisbull-sb16`, a timer-driven `none` audiodev at 32 kHz
mono U8, and one SB16 at 220h/IRQ7/DMA1/HDMA5, DSP version 4.5. There is no OPL,
MIDI or host playback. `x-fdisbull-query-sb16` API 1 passively reports the
selected device, voice, DMA and auxiliary-timer state without reading a port,
acknowledging an IRQ, transferring DMA or advancing time. The Python launcher
requires this extension before accepting `qemu_audio='sb16'`.

## Saved-state contract

The supported guest voice is unsigned 8-bit mono/stereo at 5–45 kHz. A new bounded
audio-core format 2 retains exact software-voice settings, volume, rate-converter
phase/last sample and resample buffer, hardware/capture mixer rings, backend
pending bytes, and inactive-draining flags. Zero-voice and capture-only graphs
are represented explicitly. Encodings, sizes, indices and destination graph are
validated before import; pointers, converters and callbacks are reconstructed.
The existing PC-speaker format-1 path stays separate.

The scoped SB16 subsection retains the extant voice independently of settings
for the next DSP transfer, audio credit and mixer/auxiliary deadlines. Ordinary
SB16 VMState v1 fields stay unchanged. A scoped i8257 subsection retains DREQ/
status and deferred DMA work; ordinary v1 fields stay unchanged there too.
Restore does not call `control()`, assert DREQ or execute a channel transfer.
Pending DMA work is scheduled only when the VM resumes normally. Nonzero
reentrant-DMA state refuses capture. Voice reconstruction, exact core import,
observer notification and timer rearm remain separate stopped operations.

The outer instrumented format and ownership renewal rules are unchanged.
Snapshots are authorized only through the existing one-use scoped token;
ordinary migration blockers remain effective. Host synchronization, unresolved
input schedules and ordinary held leases remain excluded. LE checkpoints earn
a freshly verified stopped source relation, not continuous task lifetime.

The pinned integer mixer resamples each channel and sums L+R for mono capture.
A mono source is duplicated. Its existing gain, clipping and integer-cast edge
behavior is preserved, including the negative-full-scale cast boundary. The
authored oracle follows that foreign arithmetic exactly without fitted gain,
rate or source offset. This qualifies retained output identity, not ideal
amplitude or DOSBox-X waveform parity.

## Apply and build

Before applying, verify the prerequisite manifest and its required input-source
hash, then each non-null `before_sha256` in `patch.files`. New-file paths must
be absent. Apply the pinned patch with `patch --batch --forward -p1`, then check
every `after_sha256`. Include the new QAPI module in schema/trace generation.
Use the existing separately prepared x86_64-softmmu TCG build configuration
without host audio drivers. Keep source/build products outside the tool tree.

The local candidate uses a copied qualified build, regenerated QAPI and trace
sources, and recompiles all recorded affected ABI-header consumers plus changed
and new C files: 30 serial compilations. It updates only the copied archive and
replays the retained linker/resource-signing commands. This is an incremental
same-Mac build, not a clean-build or portable-toolchain qualification. Exact
commands and declared-input hashes are retained in the private build receipt;
the manifest pins the resulting binary.

## Qualification

The authored fixtures are `tests/test_qemu_sb16_native.py` (known PCM/DMA/IRQ
and DSP80 delay) and `tests/test_qemu_sb16_initial_native.py` (initial and
inactive voice graphs). Supply the separate `FDISBULL_QEMU_SB16` executable,
pinned DOS boot image, mcopy, firmware, qemu-img and NASM; set
`FDISBULL_REQUIRE_QEMU_SB16=1` to prohibit missing-input skips. Native execution
uses the current host policy and one owner. Fresh results belong in the dated
handoff/!117 receipt; source and compilation alone do not qualify behavior.

Full auto-init/16-bit/HDMA playback, D0/D4 pause behavior, OPL/FM and a
paired DOSBox waveform reference remain separate gates. DOSBox-X stays default
and retained. This package changes no installation and dispatches no CI.
