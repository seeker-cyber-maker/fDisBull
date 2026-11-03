Minimal Snake v1 - authored graphics and input conversion fixture

Canonical original: 8086 MS-DOS MZ executable, VGA 320x200, no external assets.
This is a newly authored baseline with known source, not recovered game code.
Run SNAKE.EXE in DOS or a compatible DOSBox. With DOSBox, mount this directory
as drive C, select C:, then run SNAKE.EXE.

The game STARTS PAUSED. Press N or click STEP to make one move.
Arrows or WASD: turn. Direct reversal is ignored; only one perpendicular turn
can be queued before each move. Space/P: pause or run. N: single step while
paused. R: reset to the same initial board and random seed. Esc: restore text
mode and exit. Eat red food, avoid walls and your body. Filling the board wins.

With a DOS mouse driver, click the blue UP/L/R/DN direction buttons and the
PAUSE, STEP and RESET buttons. Only a new left-button press is dispatched.
Keyboard controls remain available; the no-driver branch is source-reviewed,
but native acceptance was performed with a mouse driver present.

This fixture exercises a pure state-transition routine, array state, bounded
loops and deterministic food placement, plus independent graphics, clock,
keyboard and pointer services. It is a small original for conversion tests.
No converted backing or cross-platform equivalence is claimed by intake.

Source, maps, oracle vectors and build/verification scripts are kept separately
in sources/snake-fixture-v1/oracle at the private target-package root. Keep
that oracle closed for a blind analysis exercise. Native validation is
source-assisted. Saved frames and intake receipts are in
analysis/snake-intake-2026-10-31. The executable-only ZIP excludes the oracle.

License: CC0-1.0, see LICENSE.txt. Executable identity is in SHA256SUMS.
