# Paired Doom pistol audio and normal guest exit

One opt-in native run passed for the pinned original Doom E1M1 inputs on QEMU
and DOSBox-X (`1 passed in 66.49s`). At the recorded leveltime landmarks, both
engines showed ammo changing from 50 to 49, and both guests returned normally
with exit code 0 and nonresident status. Each engine's shot capture independently
matched the pinned WAD `DSPISTOL` reference. QEMU captured 28,987 shot-window
frames with zero dropped frames; DOSBox-X produced a finalized 4,473,260-byte
RIFF containing 1,118,304 frames. Both owned emulator processes were reaped
with return code 0.

The start, control-end and shot-end landmarks were tics 64, 84 and 114. The
captures have different rates and finite extents. This result makes no PCM
waveform, audio onset, or timing parity claim. Input dispatch followed by guest
exit does not establish guest consumption or exclusive causation. This is one
bounded run per engine, not broad compatibility evidence.

Sanitized measurements and source pins are in
[`verification.json`](verification.json). The paired receipt, QEMU receipt,
DOSBox-X progress receipt and WAV captures remain outside Git in
`/Volumes/GitHub/GitHub/fDisBull-private/qemu-doom-paired-exit-audio-20261125/`;
its `manifest.json` records byte sizes and SHA-256 hashes. No game media, FDB,
VM state, screenshots, or WAV files are included in this evidence folder.
