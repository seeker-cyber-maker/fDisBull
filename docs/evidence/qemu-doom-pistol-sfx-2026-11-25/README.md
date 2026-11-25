# Paired Doom E1M1 pistol SFX (2026-11-25)

This bounded private-input test observes original Doom 1.9 E1M1 pistol sound on
the pinned QEMU and DOSBox-X backends. Both runs use the same source-qualified
LE `leveltime` landmarks: a no-shot control from tic 64 to 84, one accepted
Ctrl shot at tic 84, and an observation endpoint at tic 114. WAD status-number
patches decode each sequence as 50 rounds before and after the control, then
49 after the shot. Each backend is checked independently against its pinned
WAD `DSPISTOL` sample.

| Backend | PCM format | Control frames | Control correlation | Shot frames in observed window | Shot correlation |
| --- | --- | ---: | ---: | ---: | ---: |
| QEMU | 32 kHz, signed 16-bit stereo | 16,645 | 0.1337 | 28,884 | 0.9311 |
| DOSBox-X | 48 kHz, signed 16-bit stereo | 98,304 | 0.2241 | 49,152 | 0.9567 |

The no-shot correlations are below 0.55 and the shot correlations are above
0.55. QEMU's captured WAVs report zero dropped frames. DOSBox-X's live audio
frontier advanced from frame 933,888 at the shot boundary to frame 983,040 at
the tic 114 endpoint. The shot search is restricted to this observed frontier
and a 12,000-frame pre-frontier margin. Although the retained post-stop file
contains 1,703,936 available frames, the additional 720,896 frames after the
live endpoint are excluded from the correlation.

The DOSBox-X `session.stop` request did not provide a successful lifecycle
result: its terminal `execution.wait` reply reported `state=failed` and
`stop_reason.kind=fault` at breakpoint `bp-88`. Its owner was nevertheless
reaped with return code 0. The retained post-stop payload has a zero-size
RIFF/data placeholder header; capture completeness is unknown. The bounded
audio result therefore does not qualify DOSBox-X shutdown or a finalized WAV.
QEMU's owner was reaped with return code 0.

The [sanitized verification record](verification.json) lists the claim ceiling
and SHA-256 values. The receipt, diagnostic and three WAVs remain in private
storage outside this checkout; no commercial media is embedded here.

This is shot-associated WAD-sample correlation, not sound-call instruction
attribution. It does not claim byte-identical PCM, calibrated onset timing,
normal Doom guest exit, or broad audio/gameplay parity. Clock and BDA values
remain engine-local anchors; BDA deltas are not converted to milliseconds.
