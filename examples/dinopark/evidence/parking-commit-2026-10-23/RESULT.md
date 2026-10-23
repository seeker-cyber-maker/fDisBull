# Parking-lot counter commit: observed on OK

The delivered package **cd13636** commits the live parking counter when the game processes the General Store's OK/thumbs-up action. It does not wait for a later attendance/simulation update. This was observed with the original, unmodified **pmm / DINOSG.001** save; STF7 is not present in this local collection.

## Decisive observation

The four live facility words at project `0x471a6` were `[0,0,0,0]` after selecting and buying one parking lot in the catalogue. The staged order buffer at project `0x4bb14` (`DS:b914`) held `[0,0,0,1]`.

At the byte-verified execution breakpoint **`334b:0aec`**, reached after clicking OK, the live words were still zero. This call passes eight bytes, source `DS:b914`, and destination `DS:6fa6` to the far-copy helper at `1000:4fb8`.

The [13-event runtime trace](17-ok-commit-call-to-write.json) enters that helper and reaches **`1000:4fcb` — `F3 A5`, REP MOVSW**. Immediately before it, `CX=4`, `SI=b914`, `DI=6fa6`, and runtime `DS=ES=3844`. Immediately after the repeat completes, `CX=0`, `SI=b91c`, `DI=6fae`, and the live words are `[0,0,0,1]`. Both stops have **PIC guest tick 53805**. The trace deliberately ends early on the data watch; the final `4fcd` event is the following-instruction snapshot at the stop.

The specific parking word is **static `4020:6fac` / project `0x471ac`**, translated in this session to **runtime `3844:6fac` / linear `0x3f3ec`**. A second trial retained only the two byte watches over that word: it stopped on an actual width-2 write at `0x3f3ec`, again from runtime **`0824:4fcb`**, with the parking count now `1`.

## Controls and replay

- With the purchase staged but no OK input, **2,023 guest ms** passed with all eight write watches armed. No watched write occurred and the live words stayed zero.
- Restoring the same pre-OK native checkpoint and confirming Cancel left all four words zero after a further **4,102 guest ms**. The game returned to the city.
- A byte-verified execution breakpoint on the known attendance entry `38ff:211f` remained armed in another OK replay. The counter-copy watch fired first; the attendance breakpoint had not fired.
- A **fresh emulator session**, using the extracted delivered wheel and backend, restored the native pre-OK checkpoint and repeated the parking-specific hit. [Fresh-session receipt](fresh-session-replay.json).
- A 128-event continuation after the parking-word hit completed without a second halfword watch hit. Byte-watch IDs must not be counted as independent word writes. This backend reports one selected overlap, and the repeated move has already copied the whole block by the time it stops.

## Reproduction and evidence

- [Structured result and hash identities](summary.json)
- [All requests, results, and failed attempts](actions.jsonl), with one-based row references in the structured result
- [Compact interaction timeline](timeline.tsv)
- [Focused original-byte static context](writer-static-context.txt), separate from the runtime trace
- [Pre-OK screenshot](13-before-ok-idle-control.png)
- [After-OK screenshot](18-after-ok-settled.png)
- [Confirmed-Cancel city screenshot](20-cancel-settled.png)
- [Replay script](replay_parking_commit.py): run with `/Users/tiga/Documents/ChatGPT/fDisBull/.venv/bin/python`. It imports the delivered wheel, restores the local checkpoint, and repeats the parking-word observation without navigating the intro.

Native checkpoints and the byte-retaining project are embedded in local `parking.fdb`; no native state was exported. The isolated game copy is in `game/`. All original project game files were hash-compared before/after and are unchanged. Both emulator sessions exited and were reaped. No fDisBull source was modified or pushed by this experiment.

The result establishes the RAM commit timing of this shop transaction. It does not establish save-file persistence until the next save, other transaction types, the revenue formula, or behavior of the unavailable STF7 fixture. Screenshots show completed video frames; counter values and writer identity come from memory/register/trace observations.
