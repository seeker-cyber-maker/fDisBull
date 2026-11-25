# Original Doom reverse save cross-load and pistol sound

The guarded reverse-direction native gate passed once on 2026-11-25 (`1 passed
in 58.12s`). QEMU created a pinned original Doom 1.9 E1M1 save. After the
pre-load control shot, that save was staged by host file admission while the
DOSBox-X guest was stopped; DOSBox-X then loaded those exact 24,702 bytes.
WAD-derived ammo read **50 before the pre-load shot, 49 after it, 50 after
loading the QEMU save, and 49 after the post-load shot**.

The source-bound pre-load observation bracketed a no-shot control at
pre-increment leveltime 64→84 and a Ctrl shot through tic 114. The post-load
no-shot audio control scored 0.15375 against the pinned WAD's `DSPISTOL`
sample; the post-load shot window scored 0.96638 at pitch ratio 1.0, above the
0.55 threshold. This is a bounded WAD sample correlation in the captured
window. It does not attribute a sound call to an instruction, calibrate onset
to guest time, establish PCM identity or capture completeness, or qualify
general save compatibility or QEMU/DOSBox-X parity.

DOSBox-X `session.stop` returned a terminal wait with `state=failed` and
`stop_reason.kind=fault`, even though the DOSBox-X process owner was reaped
with return code 0. The retained post-stop audio bytes were still analyzed;
capture completeness remains **unknown**. This route did not observe or claim
a normal Doom guest exit.

Earlier b1, b2, and b3 artifacts remain preserved outside the repository. b1
has only staged progress; b2 and b3 retained preload-shot failures where a
queued Ctrl input left ammo at 50. The b4 attempt was a setup typo and is not a
native result. These attempts are not folded into the accepted b4c result.

The accepted JSON receipts, 24,702-byte save, WAV/frontier snapshots, and
relevant PNGs remain outside Git under
`fDisBull-private/qemu-doom-reverse-crossload-sfx-20261125/`. Their hashes and
the bounded result are recorded in [`verification.json`](verification.json).
No commercial game files, project database, VM state, or raw game assets are
included in this repository evidence. No CI, release, merge, or installation
qualification is implied.
