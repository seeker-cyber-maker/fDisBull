# Original Doom: paired E1M1 input and leveltime landmarks

The current native QEMU candidate and installed DOSBox-X reference ran the
same hash-pinned original Ultimate Doom executable, WAD and private config.
The game media, staged directories, project databases, screenshots, PCM and
emulator states remain outside Git. The [sanitized record](verification.json)
pins both binaries, inputs and private result digests.

## Direct-start keyboard witness

The new public DOSBox-X `dos_arguments` path and the existing QEMU path both
launched `-warp 1 1 -skill 2 -nomonsters -nosound -nomouse`. A 40-second guest
startup reached E1M1. The pinned WAD's `STTNUM0`–`STTNUM9` patches and
`PLAYPAL` decoded the stored HUD crop as **50**, then **50** after a no-input
control, then **49** after one physical Ctrl hold. This sequence passed on
each engine. The control crop was pixel-identical; the ammo-number crop changed
300 pixels on each. Both emulator owners were reaped with return code 0.
The test ended by closing the owners; this particular run did not measure a
guest Doom exit, save/load, mouse or audio.

## Protected leveltime and audio frontiers

A separate sound-enabled E1M1 run independently matched the relocated original
LE instruction at object 1 offset `0x33120` and its object 3 counter at
`0x2d354`. Each engine stopped before the instruction with `leveltime` 64
and again at 128. QEMU reacquired source binding at both endpoints without
advancing the guest. DOSBox-X used an independent GDT/fixup matcher and
normal-speed execution during the measured interval, with sparse pauses near
the second endpoint. Both owners closed cleanly.

QEMU reported **1,755,663,360 virtual ns**, **52,563** retained 32 kHz signed
stereo frames and **zero dropped frames**. DOSBox-X reported **2,299 PIC guest
ticks** and **458,752 bytes** of growth in its live 48 kHz signed stereo WAV
writer. DOSBox-X's writer may buffer samples beyond the file-size frontier;
its debugger stops and speed transition also affect this measured counter.
These are paired game-progress landmarks with different clock and audio
observers, not a sample-aligned waveform, gain, onset, music-mix or gameplay
speed qualification.

The argument-forwarding host selection passed 28 cases. The bounded new
gameplay and leveltime tests each passed once on the pinned native binaries.
Selected Tic-Tac-Toe, Five Dice and protected Doom LE regression checks passed
separately. Earlier setup failures (startup keys before graphics, a misplaced
HUD crop, receipt-field mistakes, DOSBox's rejected drive-qualified argument
and an intrusive dense-tic timing route) remain outside the accepted runs.

No inventory surface or required campaign was promoted. The parity ledger
still has 143 surfaces and seven required campaigns without qualification.
DOSBox-X remains the default in fDisBull and is retained for DotBox. No CI,
release, merge or shared installation was performed.
