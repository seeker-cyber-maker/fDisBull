# DinoPark leaderboard persistence with delivered fDisBull 0.16.0

Verified 26 October 2026 on macOS ARM64, Python 3.13.14, using the delivered
0.16.0 module and native DOSBox backend. The exact backend SHA-256 is
`315beb4e01c7d81a96209dd949c239675517af53102dd97bd0eb30bde7a0fdbb`.
The unchanged delivery verifier freshly checked all 453 payload files, including
wheel-to-module equality. [Integrity receipt](evidence/0.16.0-leaderboard/DELIVERY-INTEGRITY.json).

**Passed:** the original game accepted `DeepSeek016` through guest keyboard input
and an actual mouse OK click. The TOP TEN screen showed it at **rank 7, $9,608**.
After the first emulator exited, a second emulator and a separate new analysis
project loaded exactly the same 250 leaderboard bytes through the game's own
reader. No native state was saved or loaded in this accepted replay.

![Actual TOP TEN frame](evidence/0.16.0-leaderboard/dinopark/leaderboard-after-write.png)

## Evidence chain

1. The driver copied all 192 original files into a new private directory. It
   loaded the existing PMM save through OLD GAME, entered the office, and chose
   Businesses Bought & Sold. Normal, unmodified gameplay qualified for top ten.
2. `keyboard.type` entered `DeepSeek016`. A read of the original name buffer
   (`4020:CCE3` in this static load context) confirmed the text. The driver then
   captured the [typed dialog](evidence/0.16.0-leaderboard/dinopark/typed-name.png).
3. It clicked OK at native screenshot coordinates **(160,126)** using `click-frame`
   with the **8-pixel grid**. The game stopped on the byte-verified writer
   breakpoint **27E5:0379 / static linear 0x281C9**, before opening `topten.dat`
   in `wb+` mode. The score file was still unchanged at that stop.
4. A bounded [128-instruction writer trace](evidence/0.16.0-leaderboard/dinopark/writer-entry.trace.json)
   records entry into that path. Continuing the original game changed TOPTEN.DAT
   and produced the actual TOP TEN screenshot above. The trace is bounded; the
   disk readback and screen establish the completed write, not the trace alone.
5. The first emulator was reaped. A second new emulator, with a different PID,
   used a separate fresh `.fdb` and the same private game directory. No checkpoint
   restoration, RAM edits, register edits or execution layer was involved.
6. In that second session the game reached its reader at **27E5:03D8**, captured a
   [second 128-instruction trace](evidence/0.16.0-leaderboard/dinopark/fresh-reader-entry.trace.json),
   then stopped at **27E5:0527 / static linear 0x28377** after the read returned.
   The driver's read of the game's SS:BP-FA buffer matched **all 250 disk bytes**
   and parsed the same name, rank and value. [Fresh guest readback](evidence/0.16.0-leaderboard/dinopark/fresh-guest-readback.json).
   This fresh-session proof is a guest-memory readback; the TOP TEN image above
   belongs to the writing session. The second session was closed before any
   second score write, and the disk hash stayed unchanged.
7. Both owned emulator processes exited. All 192 original files remained
   byte-identical. **Only `TOPTEN.DAT` changed in the private copy.**
   [Complete verification receipt](evidence/0.16.0-leaderboard/dinopark/VERIFICATION.json).

The original TOPTEN.DAT SHA-256 was
`901f80a6d89ecf7107561f2cfdf5fcf7ff864c7d3ad2a09edf70b8d3559b8b4e`.
The completed write and the second guest's full buffer both hashed to
`537ad9cace9ec0a4eff40ea32173abf19d8fbf47c4d5fecf8ee7b55d39ea3ec6`.
The payload retains these hashes and the selected parsed entry, not a copy of
the score file or a full RAM dump.

## Important input detail for DeepSeek

The original game's modal text editor consumes keyboard input while mouse OK
clicks have no effect. Direct clicks timed out without reaching the writer;
Enter accepted the whole dialog, while Escape discarded the typed text. The
working mouse route is:

```json
[
  {"op":"keyboard.type","text":"DeepSeek016"},
  {"op":"run","guest_ms":1600,"timeout_ms":15000,"fast_forward":true,"expect":"guest_time"},
  {"op":"keyboard.press","key":"o","modifiers":["ctrl"]},
  {"op":"run","guest_ms":300,"timeout_ms":15000,"fast_forward":true,"expect":"guest_time"},
  {"op":"click-frame","x":160,"y":126,"name":"ok.png","grid_step":8,"hold_ms":80},
  {"op":"run","timeout_ms":5000,"fast_forward":true,"expect":"breakpoint"}
]
```

**Ctrl+O** releases that game's text editor while preserving the entered name;
then mouse OK activates the score writer. This behavior was observed in the
original executable. It is a version-specific DinoPark route, not a generic
fDisBull readiness rule. The [exploratory input records](evidence/0.16.0-leaderboard/input-focus-probes/)
retain a failed direct click and the successful focus-release/mouse sequence;
they are separate from the clean accepted replay and its value.

The finite route uses bounded guest-time waits. Actual game progress during
preparation varies: the exploratory run sold for 9,176, the first clean replay
for 9,356, and this final replay for 9,608. All three recorded rank 7. The final
script asserts that the newly written entry survives unchanged; it does not
assume a fixed sale price or claim deterministic replay. Bounded analysis
receipts retain `stable: false` and their pending work.

## Replay from your own files

[verify_leaderboard.py](../examples/dinopark/verify_leaderboard.py) is the exact final script exercised
for the accepted receipt. It refuses existing work/evidence directories, refuses
private output beneath Git, verifies the executable and PMM save hashes, and
creates its own private game copy and two analysis projects. It never edits a
game file directly. Your original input must still have the supplied PMM save
and must not already contain the chosen leaderboard name.

```bash
python examples/dinopark/verify_leaderboard.py \
  --delivery /path/to/extracted/fdisbull-0.16.0-delivery \
  --game-dir /path/to/your/original/dinopark \
  --work-dir /path/outside/git/to/new-private-run \
  --evidence-dir /path/to/new-evidence
```

Use a Python environment with the genuine delivered dependencies. This run
qualifies the Mac native backend; this task did not repeat the actual gameplay
on Linux or Python 3.13.5. Linux release CI and offline-kit qualification remain
separate evidence. `--delivery` must contain `fdisbull_delivery.py` with
`activate()` and `dos_options()`.

## Contents and exclusions

The packet contains the replay source, saved script JSON, per-step results,
clean and 8-pixel-grid screenshots, two bounded instruction traces, and receipts.
Game files, DINOSG saves, TOPTEN.DAT, native checkpoints, project databases and
emulator binaries are absent. Private game copies/databases remain only under
`~/Conversions/DinoParkTycoon/debugger-runs/`. The published 0.16.0 delivery and
release assets were not modified. This is follow-up runtime verification.

## Latest investigation example

The subsequent [E35 Library handoff](../examples/dinopark/notes/INVESTIGATION_E35.md)
reports its own Linux keyboard/persistence acceptance and the pinned build's
100-byte save-padding finding. It is useful context for the next investigation:
NEW GAME profitability and remaining meaningful save-field writers/consumers.
The note distinguishes those reported results from this Mac replay, preserves
the late-checkpoint timing caution, and corrects the report's historical release
availability statement against a fresh GitHub read.
