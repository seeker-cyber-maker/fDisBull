# Original Ultimate Doom: stereo and recovery

The supplied original Ultimate Doom executable and WAD now have fresh Linux
execution on the installed **fDisBull 0.34.1 DOSBox-X baseline** and the new
native QEMU candidate. Both boot E1M1, consume a physical Ctrl press that
changes ammunition from 50 to 49, produce graphics and audio, and return
normally to DOS through physical F10/Y input. Original game bytes remain
unchanged. The sole private configuration change selects music device 2 in
place of 3, retaining music and sound effects.

The [sanitized verification record](verification.json) pins source, runtime,
game/configuration hashes, private receipts and the exact scope of each run.
Game files, databases, states, images and raw audio remain outside Git.

## Native QEMU recovery

The new combined SB16/OPL2 observer captures 32 kHz signed16 stereo. Before the
shot, the retained music window has 12,386 frames. After physical firing,
checkpoint A contains 34,814 frames, including 9,042 frames with different
left/right values. The next 600 ms extends the retained recording to 53,821
frames. The raw samples are not centered or normalized; nonzero DC remains
observed and no sample-limit rails occur in this window.

Hot restore and a separate-Python cold restore both reproduce checkpoint A
and the complete 600 ms future B: CPU, PNG hash, OPL, SB16, software mixer,
PCM bytes and chunks, virtual nanoseconds and instruction count all match.
Each restore explicitly reports `source_binding_restored=False`. No protected
LE source binding is requested or inferred. Four native owners in this
accepted recovery route are closed and reaped with return code 0.

A separate fresh original owner supplies the normal guest-exit observation.
F10 displays Doom's quit prompt; physical Y returns before the bounded advance
deadline with `guest_exit`, normal code 0 and nonresident state. The authored
DOS EXEC helper observes the parent callback and DOS AH=4Dh return status.
QEMU remains alive at that guest return and is then separately closed and
reaped. Closing an emulator is not used as evidence of guest exit.

## Comparison and limits

| Observable | Installed DOSBox-X baseline | Native QEMU candidate |
| --- | --- | --- |
| Inputs | Same original EXE, WAD and private configuration | Same byte identities |
| Physical Ctrl | Visible ammunition 50 to 49 | Visible ammunition 50 to 49 |
| Hot recovery | Exposed CPU/address context restored; fresh image shows ammunition 50 | Full selected machine/audio state plus exact 600 ms future |
| Separate-process cold recovery | Not attempted in this baseline | Exact selected state and 600 ms future |
| Native audio | 48 kHz signed16 stereo; whole recording finalized | 32 kHz signed16 stereo; retained PCM prefix and future verified |
| Normal DOS exit | Native DOS termination after cleanup, code 0 | Authored EXEC helper parent callback, code 0 |

The timelines and audio implementations are different. These observations do
not establish sample-aligned waveform, gain, DC or frame equivalence. Mouse,
whole-game playthrough, broader driver behavior and full migration parity
remain open.

An initial system-template launch timed out before helper readiness. The
accepted route uses the repository's hash-pinned minimal FreeDOS component and
an explicit C:/D: directory startup. A separate controller attempt requested
an oversized 90-second clock interval and was refused before that advance;
the corrected bounded intervals pass. The first failed constructor has no
measured return-code receipt; a later read-only process check is explicitly
limited to its current execution namespace. Those limits are retained rather
than combined with the measured accepted-owner cleanup.
## Subsequent SB16 count finding

A later independent nonwrapping DMA oracle demonstrates that this frozen native
producer doubles the programmed extent for single-cycle stereo Bx/Cx playback.
The game observations above remain exact persistence evidence on that producer;
they do not establish correct DSP count semantics. The separate correction and
its new producer require their own playback and persistence acceptance.
