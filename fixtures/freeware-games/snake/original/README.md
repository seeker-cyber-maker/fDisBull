# Minimal Snake v1 - conversion fixture

Start with learner/SNAKE.EXE. The accompanying learner/README.txt explains
DOSBox launch and controls. It starts paused: press N or click STEP to move.
Use arrows/WASD or the mouse direction buttons; Space/P pauses, R resets,
and Esc restores text mode and quits. No assets or sound files are needed.

This is a newly authored known-source DOS original, not recovered commercial
code. Keep oracle/ closed for blind recovery. For source-assisted work it
contains SNAKE.ASM, the exact LINK map, semantic contract, independent vectors,
porting boundaries, a build recipe and verification scripts. All are CC0-1.0;
see LICENSE.txt. External compiler/emulator tools are not included.

To build with an explicitly supplied MASM5.1/LINK toolchain and DOSBox-X:
python3 oracle/build.py --tools /path/to/compiler --dosbox /path/to/dosbox-x --output /new/private/build

The compiler folder must contain BIN/MASM.EXE and BIN/LINK.EXE. Build output
must be new. Oracle verification uses that build directory. Run verify.py
--help for arguments; the pure phase needs Unicorn2.1.4 and the native phase
needs an installed fDisBull and its compatible native DOSBox backend.

Evidence records17 compiled-step cases and35 native graphics/input/lifecycle
checks, with unchanged original bytes. Evidence paths identify the original
validation workspace; supply your own new destinations when reproducing.
The final source built twice to identical bytes. MANIFEST.json hashes every
other archive member. No converted backing or whole-frame converted equality
is qualified by this intake. Start with oracle/PORTING.md for the next slice.
