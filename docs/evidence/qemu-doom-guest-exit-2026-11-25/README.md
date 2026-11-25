# Original Doom QEMU guest-exit gate

This record covers one opt-in run of original Doom E1M1 on the pinned QEMU DOS
backend. The run reached its pinned pistol/audio endpoint, dispatched F10 and Y
keyboard chords, and then reported a public DOS `guest_exit` with normal code 0
and a nonresident process. QEMU was still alive at the guest return and its
owner was later reaped with return code 0.

The stored frames differed by 3,002 pixels after F10, measured after normalizing
both images to 320x200 RGB. This is a frame-change measurement; no OCR or prompt
classification was performed. The F10 and Y input schedules each report two
dispatched edges. Those dispatch records do not establish guest consumption or
exclusive causation. The observation is that the guest exit followed the
dispatch sequence.

Before the quit sequence, the WAD-derived ammo decoder observed 50→49, and the
captured shot audio matched the pinned WAD's DSPISTOL sample at normalized
correlation 0.9493. The no-shot control scored 0.1291. Audio was captured as
32 kHz, signed 16-bit stereo with zero dropped frames. These are this run's
bounded gameplay/audio observations, not an audio-equivalence or broad parity
claim.

The source files matched their pinned hashes before and after the run. The four
staged files also matched before and after; `DEFAULT.CFG` was unchanged. The
QEMU owner returned code 0. No DOSBox-X result, cross-engine comparison, or
broader compatibility claim is included here.

The raw private receipt, WAV files, and frames are kept outside Git in the
private `qemu-doom-guest-exit-20261125` evidence directory. Their hashes and
selected sanitized observations are listed in
[verification.json](verification.json). The gate is implemented in
[`test_doom_qemu_pistol_guest_exit_native.py`](../../../tests/test_doom_qemu_pistol_guest_exit_native.py)
and requires `FDISBULL_REQUIRE_DOOM_QEMU_PISTOL_EXIT=1` plus the pinned private
inputs.
