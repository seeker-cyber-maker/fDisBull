# Original Doom DOSBox-X quit and capture evidence

This folder records one bounded native run of the opt-in original Doom E1M1 DOSBox-X quit/capture gate. The test passed once (1 passed, 20.60 seconds). It measured a pinned no-shot control, one Ctrl shot, an F10 quit prompt followed by Y, DOS guest termination, and the DX-CAPTURE WAV after guest exit.

The shot changed the WAD-decoded ammo count from 50 to 49. Within the bounded shot audio window, the captured PCM matched the WAD `DSPISTOL` sample at correlation score 0.955978943 (acceptance threshold 0.55); the no-shot control score was 0.198228923. The audio file has a finalized RIFF extent of 4,746,668 bytes and a 4,746,624-byte PCM data chunk (48 kHz, stereo, signed 16-bit). The captured tail after the shot frontier includes buffered audio through the quit prompt and exit and was excluded from the shot match.

The guest reported `DOS_Terminate`, requested exit code 0, nonresident status, and `after-process-cleanup`; the owned host process was reaped with return code 0. `DEFAULT.CFG` had the same SHA-256 before and after guest exit and owner close. The two retained PNGs are the observed frame before F10 and the frame after F10 but before Y confirmation. The latter is not a post-exit screenshot; the reported 2,890 changed pixels is only a frame-difference count, not OCR or prompt classification.

`verification.json` contains sanitized run facts and hashes. Exact receipts, WAV and PNG copies are retained outside Git under `/Volumes/GitHub/GitHub/fDisBull-private/qemu-doom-dosbox-quit-20261125/`. Commercial game bytes and raw private capture data are not included in this evidence folder.

## Scope limits

This is one DOSBox-X execution with one observed guest quit. It verifies the reported DOS guest exit and finalized RIFF/data extents for this capture, plus one bounded DSPISTOL match. Audio capture completeness is not claimed. It does not establish QEMU behavior, cross-engine parity, general DOSBox-X compatibility, or repeatability across runs.
