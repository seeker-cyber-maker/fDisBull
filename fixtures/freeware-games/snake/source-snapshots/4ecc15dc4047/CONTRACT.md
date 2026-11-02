# Snake fixture semantic contract, revision 1

This is a newly authored, source-known local fixture, not recovered third-party
source. Keep these answers and vectors in the oracle lane. The learner delivery
contains the canonical executable, licensing, controls and identities only.
A later converter can use a blind binary lane or a declared source-assisted lane;
these are different evidence claims.

## Observation boundary

The first conversion question is whether a source-bound game step and shell can
preserve logical movement, palette-index graphics and physical input behavior.
The pure step has no BIOS, DOS, time, renderer, keyboard or mouse calls. The DOS
shell owns scheduling, mode changes, input sampling, cursor lifetime and drawing.
A successful kernel check does not prove keyboard delivery, rendered pixels,
platform ABI, timing, focus, teardown or whole-game conversion.

## State and step

The board is 30 columns by 20 rows. Cell `(x,y)` has packed value `30*y+x`.
`snake_cells` holds head first; its active prefix has `snake_length` unique cells.
Directions are 0=up, 1=right, 2=down, 3=left. A directly opposite pending turn is
ignored, including when a caller bypasses the shell's turn filter. The resolved
legal direction is committed before checking collisions. Every active step normalizes the pending-direction slot to the resolved
direction, including a rejected reverse. That slot is not evidence that movement
happened.

At an active `snake_step` call, `tick_count` increments once, even when the attempt
collides. `turn_queued` clears. A legal non-growth move drops the previous tail,
then inserts the new head. Moving into that vacated tail is allowed. A growth
move preserves the tail and adds one segment and one score point. Wall or body
collision sets `game_status=1` and `paused=1`; it does not move cells or change
length, score, RNG or food. No toroidal wrapping is permitted. Calls with dead
or won status are exact state no-ops. The shell calls the kernel only when an
automatic running tick or explicit paused single-step is due; paused is not a
kernel refusal condition.

Initial state is head `(8,10)`, then `(7,10)`, `(6,10)`, right-facing, food
`(12,10)`, length 3, score 0, seed `0x1234`, status active and paused. The first
ordinary rightward step therefore yields cells `[309,308,307]` and still food 312.
Restart restores that same state and deterministic random sequence.

After eating, unless the board becomes full, advance the unsigned 16-bit LCG:
`seed = (seed * 25173 + 13849) mod 65536`.
Start with `seed mod 600`, then scan forward with wrap to the first free cell;
at most 600 candidates may be examined. This is a bounded search, not repeated
random draws. Example: seed 4660 advances to 10589, whose remainder is 389.
If growth fills all 600 cells, set `game_status=2`, `paused=1` and food to65535;
do not advance the RNG. A full-board marker must never be used as a framebuffer
coordinate. Counters use the fixture's declared unsigned word representation.

## Shell and input

The shell starts paused. Arrow/WASD keys request turns; a reverse is rejected and
at most one turn is queued per tick. Space/P toggles pause, N single-steps only
while paused, R restarts, and Esc exits through mode3 restoration. Mouse buttons
are edge-triggered controls, rather than a polling-loop repeat stream. An absent
mouse driver retains keyboard operation. Logical click rectangles use half-open
pixel intervals on a 320x200 frame:

| Control | x interval | y interval |
| --- | --- | --- |
| Up | [280,304) | [40,60) |
| Left | [256,280) | [64,84) |
| Right | [288,312) | [64,84) |
| Down | [280,304) | [88,108) |
| Pause | [256,312) | [120,140) |
| Step | [256,312) | [144,164) |
| Restart | [256,312) | [168,188) |

BIOS mouse coordinates are normalized to logical 320x200 coordinates before hit
testing. A frame redraw hides/shows an installed driver cursor so the background
is not corrupted. Board origin is `(8,24)` with 8x8 cells; rendering and logical
state must be compared separately. VGA mode13h is an original shell service, not
an intrinsic property of the game kernel.

## Vectors and claim ceiling

`vectors.json` contains explicit, hand-selected one-step initial/expected states.
They cover four directions, reverse refusal, eating, four walls, vacating-tail
permission, body collision, frozen outcomes, bounded food search and full-board
victory. Constructed states are diagnostic kernel inputs, not a claim of ordinary
player reachability. Expected values come from this contract; the oracle does
not call or decode the implementation to generate its answers. Build verification
must execute the actual retained machine code separately. Future target-format
comparisons must use the same vector identities and keep original-code, UIL and
converted-shell observations as distinct gates.
