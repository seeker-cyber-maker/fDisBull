# Selected DOS Syndicate save profile

Profile identity: MAIN SHA-256
`bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078`.
Little-endian fields. Exact selected file extent 28,247 bytes. This is not a
universal `.gam` decoder and provides no magic-based authenticity test. See the
report for native load and original-source evidence. Offsets below are decimal
unless prefixed `0x`. Do not conflate saved offsets, preferred addresses, or live
relocated addresses.

## Top-level partition

| Start | Length | Meaning |
| ---: | ---: | --- |
| 0 | 20 | Save-slot label; bounded bytes, not executable text |
| 20 | 8376 | 8 company records, stride 1047 |
| 8396 | 500 | 50 territory records, stride 10 |
| 8896 | 10020 | 20 weapon-project records, stride 501 |
| 18916 | 8838 | 18 modification records, stride 491 |
| 27754 | 489 | Active research |
| 28243 | 4 | Opaque retained trailer |

No bytes are silently discarded. The reader extracts qualified fields but does
not rewrite the original or pretend unknown fields have no effect.

## Company and territory fields

Company +0: u32 cash; +4: u32 within-day timing value; +8/+10: two u16 calendar
values. The decoder labels calendar values raw; it does not invent a full modern
calendar. Remaining company bytes include additional campaign/agent state and
remain outside this reader's interpreted subset.

Territory +0: u16 status, with the admission consumer distinguishing 255;
+2: u8 owner; +3/+4: tax-related bytes retained separately; +5: unknown;
+6: u32 population. Raw ownership and taxes are not automatically player knowledge.
The selected company and the mission-admission override are **runtime context**,
not supplied by this save layout.

## Project records

| Relative field | Weapon | Modification |
| --- | ---: | ---: |
| Code byte | 0 | 0 |
| Price i32 (interpretation scoped) | 1 | 1 |
| Base hourly research charge u16 | 13 | 6 |
| Stored progress i16 | 17 | 8 |
| 240 history u16 values | 19 | 10 |
| Successor project byte | 499 | 490 |
| Weapon category byte | 500 | Not asserted |

Progress -1 is the observed locked value; 0 is an available unresearched value;
2400 is the completed value. This does not by itself establish purchase permission,
UI visibility or every disabled-slot behavior. Code 254 identifies disabled weapon
records in the examined data. The active graph can be newer than this stored
progress: UZI is 600/2400 in the accepted seed while its stored word remains zero.
The reader does not collapse those fields.

## Active research, 489 bytes

+0 state byte; +1 kind (0 none, 1 modification, 2 weapon); +2 project index;
+3 signed 32-bit funding index (-1 paused/unset, 0..9 active tiers); +7 u16 hourly
base; +9 240 little-endian u16 graph samples. State names 0 running, 1 completion
pending, 2 idle, 3 insufficient funds reflect the studied original caller paths.

A contiguous prefix of positive graph samples is followed by zero unused slots
in the qualified model. The model refuses a hole, reversal, full unfinished graph
or values outside its admitted range. That refusal is a model boundary, not proof
that every such file would be rejected by the original loader.

## Exact original I/O contract and risks

The writer constructs `%s/%02.2d.gam`. The observed configuration is
`C:/SYND/SAVE`, producing `00.GAM` for slot zero. Use the actual guest drive mapping;
a guessed directory or menu return is not a successful persistence witness.
The original reader and writer transfer all six blocks in the partition above.
All six matched after write, same-process load and fresh-process load.

The writer mutates cash above 30,000 **before opening the output file**. Preserve
that effect in original-backed tests, and keep native save, emulator snapshot,
file-copy and synthetic-state construction as different operations. Native
checkpoints do not imply host-file rollback. Always work on copied private saves.

No original save file or byte payload is included. `tools/campaign.py` is a reader
and semantic model, not a save editor or purported later-progression donor.
