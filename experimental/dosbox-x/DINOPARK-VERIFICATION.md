# DinoPark runtime verification — 2026-10-23

Result: **pass for the requested bounded session**. The unchanged headless DOSBox backend ran the actual DOS game, captured screenshots, accepted clicks that advanced through several screens, stopped on a game-code breakpoint, and returned a useful 512-instruction trace of the game consuming a click.

## Inputs and execution boundary

- Source archive: `/Volumes/PATRIOT/Downloads/Dinopark_Tycoon_1993.zip`.
- Archive SHA-256: `22e299e900af2c52c72d071a172326d7ba98b49c74d207af053574e133452944`.
- `DINOPARK.EXE` SHA-256: `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`, matching the prior static investigation's executable.
- Emulator SHA-256: `9c1f4be93208798f2d7c27de2ca443646831336cb8aeeb691c0f286df439e0b3`, matching the previously verified native Apple Silicon build.
- All 21 backend source-file hashes still match `source-manifest.json`. No backend fix was needed for this run.
- Game files were extracted into `examples/dinopark/local/dosbox-20261023/dinopark/`, a separate ignored working copy. At session end, no extracted input files were changed and no game files had been added. Original archive and game executable were unchanged. Game binaries/resources/saves are not included in this evidence directory.
- Execution used `HeadlessAgent`, SDL dummy video/audio, inherited RPC pipes, and native-resolution rendering. No GUI automation or guest-memory patch was used to drive the game.

## Observed UI sequence

Screenshots are native 320×200 guest frames, not reconstructions:

1. [Title menu](evidence/dinopark-2026-10-23/05-after-intro-click.png).
2. Left-click **New Game** at screenshot `(75,160)`.
3. [Startup bank loan message](evidence/dinopark-2026-10-23/07-new-game-ready.png): the game approves the initial $5,000 loan.
4. Left-click the confirmation icon at `(160,132)`; [bank account screen](evidence/dinopark-2026-10-23/09-bank-ready.png) shows bank balance $5,000, loan $5,000, and monthly payment $75.
5. Right-click to leave the bank; [Dino City](evidence/dinopark-2026-10-23/10-after-bank.png) appears.
6. Left-click Real Estate at `(60,140)`; [Desert/Plains/Marsh selection](evidence/dinopark-2026-10-23/12-real-estate-ready.png) appears with current capital $5,000.

The images were visually reviewed. The action log binds each screenshot to its RPC metadata and PNG SHA-256. Repeated final screenshots have identical bytes, frame/tick metadata, and CPU register snapshots, establishing that requesting a screenshot while stopped did not advance this game.

## Breakpoint and trace

The mouse poll was located in the actual EXE: `mov ax,3; int 33h` at original file offset `BDBCh`. Runtime memory around that code matches the original executable bytes.

The requested execution breakpoint was `0824:75BC`, linear `0F7FCh`. It fired with stop reason `breakpoint`, ID `bp-1`, while the actual CPU address was `0EB7:0C8C`. Those two segmented addresses resolve to the same linear address. This is the game's own code; the subsequent INT33 callback is separately visible in the trace.

After queuing the New Game click and hitting the breakpoint, the breakpoint was deleted and a bounded 512-instruction normal trace was collected. The trace is a delta stream of **register values before each listed instruction**. The readable export reconstructs those register snapshots from the deltas.

| Event | Runtime address | Instruction / observation |
| --- | --- | --- |
| 1 | `0EB7:0C8C` | `mov ax,0003`: request mouse position/button state |
| 2 | `0EB7:0C8F` | `int 33h` |
| 4 | `C402:0019` | DOSBox's mouse callback, distinct from game code |
| 5 | `C402:001D` | Return has BX=1, CX=150, DX=160 |
| 6 | `0EB7:0C91` | `mov [009A],bx`: game stores pressed-button word |
| 7 | `0EB7:0C95` | `mov [7BB0],cx`: game stores INT33 X |
| 8 | `0EB7:0C99` | `sar word [7BB0],1`: converts X to the game's 320-pixel grid |
| 9 | `0EB7:0C9D` | `mov [7BAE],dx`: game stores Y |
| 11 | `0EB7:034E` | `and word [009A],0001`: caller masks the left button |

Independent memory reads after the trace confirmed:

- `3844:009A` = `0001h`, left button pressed.
- `3844:7BB0` = `004Bh` = **75**, screenshot X.
- `3844:7BAE` = `00A0h` = **160**, screenshot Y.

Thus the trace connects the injected click to values consumed and stored by DinoPark. The later loan screen establishes the visible New Game transition; the first 512 traced instructions alone are not claimed to contain the entire scene-loading path.

## Receipts and cleanup

- [Machine-readable verification](evidence/dinopark-2026-10-23/verification.json).
- [Full 512-event trace with register deltas](evidence/dinopark-2026-10-23/new-game-mouse-trace.json).
- [Readable trace with reconstructed register snapshots](evidence/dinopark-2026-10-23/new-game-mouse-trace.txt).
- [Complete action log](evidence/dinopark-2026-10-23/actions.jsonl), including the successful breakpoint, screenshots, clicks, memory reads, and cleanup.

The local probe remains at `.recovery/2026-10-23/dinopark_probe.py`. Its finite session closed normally: session state `exited`, then the emulator process was reaped. No test emulator remains running. One diagnostic read initially used a four-digit offset where the client requires an eight-digit offset string; the rejected request and successful retry are retained in the log. It did not mutate the guest.

This verifies startup and the listed UI/input/debugger path on this executable and host. It does not establish a complete playthrough, save/load behavior, all game functions, sound output, or complete memory-access tracing. No commit, push, or publication was performed.
