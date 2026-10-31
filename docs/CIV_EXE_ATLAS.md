# CIV.EXE address/source atlas (DOS 474.05)

Status: **proven for the declared static metadata**. The atlas joins the
byte-identical civd build, its LINK map and compiler listings, the unpacked
runtime image, and Civ64's DOS correspondence anchors. It does not execute the
game and does not copy game code into the repository.

## Identity and inputs

| Input | Identity |
| --- | --- |
| Packed `CIV.EXE` | 305,030 bytes; SHA-256 `22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a` |
| Unpacked `CIV_UNP.EXE` | 340,791 bytes; SHA-256 `aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57` |
| `CIV.MAP` | SHA-256 `42de9270bbb6114d8ff087c11cb33e84f67421ced10c8c9f40f70a2d6f3de0c6` |
| civd source revision | `d9214fcd36aa6003d28aae60c3974b665f752280` |
| Root header | 10,128-byte header; 203,584-byte load module; 2,525 relocations; declared end 213,712 |
| Overlay tail | 23 MZ records; images end at file offset 340,791 |

The unpacked hash equals the published `CIV_UNP.EXE` identity. The atlas refuses
an input whose root or packed hash differs.

## What the atlas contains

`examples/civ/civ_exe_atlas.py` parses the LINK map and every `*.COD` listing and
writes `examples/civ/civ_exe_atlas.json`:

- 97 segment records (22 root code segments, 23 overlays, data and stack);
- 1,188 public symbols (resident and overlay, code and data);
- 430 C functions from 42 source files, with segment, definition line, size,
  entry bytes, calls and Civ64 anchor resolution;
- 23 overlay records with file offset, image size and source mapping;
- the 21 Civ64 DOS anchors from `CIV_DOS_CIV64_CROSSWALK.md`.

## Verification

| Check | Result |
| --- | ---: |
| Root code segment extents | 145,213 bytes |
| Overlay images | 104,260 bytes |
| Public symbols | 1,188 |
| C functions | 430 |
| C function bytes | 229,991 |
| C call sites | 5,951 |
| C entry first opcode matches binary | **430 / 430** |
| C entry first instruction bytes exact | 411 / 430 |
| C function starts equal `CIV.MAP` public address | 428 / 430 |
| Call opcode matches binary | **5,951 / 5,951** |
| Call target matches binary | **5,951 / 5,951** |
| Overlay image size equals map segment length | **23 / 23** |
| Civ64 anchors resolved to a civd function | **21 / 21** |

The 19 non-exact entry instructions differ only in linker-resolved operands
(DGROUP offsets, symbol offsets or overlay entry numbers); their opcodes all
match. The two C functions without a public-map address are the static
`show_label` and `next_credit` functions in `INTRO.C`; both are present in the
COD listing and have verified entry opcodes.

All 5,951 calls have a verified opcode and a decoded target:

- near calls use `E8 rel16`;
- far calls to root code use `9A off16 seg16`;
- far calls to another overlay use `CD 3F <overlay> <entry offset>`;
- intra-overlay calls are near `E8` calls, not `INT 3F`.

The last distinction is easy to get wrong: all 23 overlays load at linear
`0x23740`, so an address alone cannot identify an overlay function. Resolution
must carry `(overlay number, linear address)`. Before that key was enforced, the
`O19` anchor resolved to an `ADVISORS.C` function because it also starts at
`0x23740`; with the overlay key it resolves to `CITYVIEW.C`.

## Root code segments

| Segment | Map start | Bytes | C source | Functions |
| --- | ---: | ---: | --- | ---: |
| `F0000` | `00000` | 6,186 | assembly | 0 |
| `F0182` | `0182A` | 360 | `DRAW.C` | 8 |
| `F0199` | `01992` | 246 | assembly | 0 |
| `F01A8` | `01A88` | 2,304 | `GAME.C` | 16 |
| `F0238` | `02388` | 7,350 | `TURN.C` | 17 |
| `F0403` | `0403E` | 17,960 | `CONTROL.C` | 10 |
| `F0866` | `08666` | 10,112 | `UNITS.C` | 38 |
| `F0ADE` | `0ADE6` | 9,028 | `ECONOMY.C` | 11 |
| `F0D12` | `0D12A` | 29,798 | `CITYMGT.C` | 19 |
| `F1459` | `14590` | 3,044 | `CAPTURE.C` | 7 |
| `F1517` | `15174` | 3,648 | `DIPLOMAC.C` | 11 |
| `F15FB` | `15FB4` | 16,266 | `UNITAI.C` | 16 |
| `F19F3` | `19F3E` | 3,946 | `BATTLE.C` | 6 |
| `F1AEA` | `1AEA8` | 6,552 | `MAP.C` | 31 |
| `F1C84` | `1C840` | 2,064 | `MENUS.C` | 6 |
| `F1D05` | `1D050` | 3,066 | `DIALOG.C` | 8 |
| `F1DC4` | `1DC4A` | 1,748 | `CORE.C` | 24 |
| `F1E31` | `1E31E` | 4,530 | `PATH.C` | 6 |
| `F1F4D` | `1F4D0` | 1,354 | `MESSAGE.C` | 6 |
| `F1FA1` | `1FA1A` | 2,194 | `FILEIO.C` | 29 |
| `F202A` | `202AC` | 424 | `IMAGE.C` | 3 |
| `_TEXT` | `20454` | 13,033 | assembly | 0 |

`F0000`, `F0199`, `_TEXT` and the zero-length segments carry resident assembly
or linker scaffolding; the 430 C functions do not cover the assembly routines or
the C runtime.

## Overlays

All paths are relative to `CIV_UNP.EXE`; every image size equals the map length.

| # | Segment | Source | Functions | Bytes | Image file offset |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | `O01_TEXT` | `SETUP.C` | 1 | 1,018 | 213,937 |
| 2 | `O02_TEXT` | `INTRO.C` | 6 | 6,588 | 215,473 |
| 3 | `O03_TEXT` | `FAME.C` | 7 | 3,192 | 223,153 |
| 4 | `O04_TEXT` | `NOTES.C` | 4 | 1,146 | 227,249 |
| 5 | `O05_TEXT` | `NEWGAME.C` | 8 | 7,534 | 229,297 |
| 6 | `O06_TEXT` | `AUDIENCE.C` | 12 | 9,642 | 238,001 |
| 7 | `O07_TEXT` | `WORLDGEN.C` | 15 | 7,512 | 248,753 |
| 8 | `O08_TEXT` | `PEDIA.C` | 7 | 6,134 | 257,457 |
| 9 | `O09_TEXT` | `REPLAY.C` | 11 | 5,468 | 264,625 |
| 10 | `O10_TEXT` | `MAPVIEW.C` | 3 | 1,702 | 271,281 |
| 11 | `O11_TEXT` | `SAVE.C` | 12 | 3,994 | 273,841 |
| 12 | `O12_TEXT` | `REPORTS.C` | 8 | 7,000 | 278,449 |
| 13 | `O13_TEXT` | `STATUS.C` | 3 | 2,472 | 286,641 |
| 14 | `O14_TEXT` | `ADVISORS.C` | 12 | 7,026 | 289,713 |
| 15 | `O15_TEXT` | `CIVWAR.C` | 3 | 2,426 | 297,905 |
| 16 | `O16_TEXT` | `QUIZ.C` | 2 | 1,372 | 300,977 |
| 17 | `O17_TEXT` | `PALACE.C` | 5 | 4,246 | 303,025 |
| 18 | `O18_TEXT` | `SPACESHP.C` | 12 | 5,842 | 308,145 |
| 19 | `O19_TEXT` | `CITYVIEW.C` | 10 | 7,332 | 315,313 |
| 20 | `O20_TEXT` | `CITY.C` | 4 | 5,188 | 324,017 |
| 21 | `O21_TEXT` | `NEWS.C` | 1 | 1,066 | 330,673 |
| 22 | `O22_TEXT` | `DIPLOMAT.C` | 5 | 4,434 | 332,721 |
| 23 | `O23_TEXT` | `NAMES.C` | 7 | 1,926 | 338,353 |

## Civ64 anchor resolution

The 21 addresses in `CIV_DOS_CIV64_CROSSWALK.md` were resolved against the
civd atlas. “Entry” means the address is the function start; “inside” means it
lies inside the function. The Civ64 role text is kept separate from the civd
function identity.

| DOS anchor | Civ64 role | Resolved civd function | Position |
| --- | --- | --- | --- |
| `R:1AEA:03BA` | city layer | `_seen_map` (`MAP.C`) | entry |
| `R:0D12:0045` | city screen | `_city_process` (`CITYMGT.C`) | entry |
| `R:0D12:7045` | building icons | `_draw_icon` (`CITYMGT.C`) | entry |
| `R:0D12:710D` | city panel background | `_tile_panel` (`CITYMGT.C`) | entry |
| `R:1F4D:04F7` | truncate to width | `_truncate_text` (`MESSAGE.C`) | entry |
| `R:1459:08C6` | city name | `_append_place_name` (`CAPTURE.C`) | entry |
| `R:0ADE:03EA` | city caller | `_kill` (`ECONOMY.C`) | entry |
| `R:0ADE:0093` | city caller | `_civ_economy` (`ECONOMY.C`) | inside |
| `R:1459:0597` | city caller | `_capunit` (`CAPTURE.C`) | inside |
| `O19:0000` | city view | `_city_scene` (`CITYVIEW.C`) | entry |
| `O19:13A1` | houses/roads | `_city_load` (`CITYVIEW.C`) | inside |
| `O19:14FB` | buildings | `_city_load` (`CITYVIEW.C`) | inside |
| `O19:167B` | invaders | `_invasion_scene` (`CITYVIEW.C`) | entry |
| `O19:18C1` | civil disorder | `_riot_anim` (`CITYVIEW.C`) | entry |
| `O19:1AE1` | celebration | `_love_anim` (`CITYVIEW.C`) | entry |
| `O22:0EAF` | city founded | `_city_founded` (`DIPLOMAT.C`) | entry |
| `R:0ADE:0421` | production menu | `_find_slot` (`ECONOMY.C`) | entry |
| `O20:0540` | disasters and city events | `_city_disaster` (`CITY.C`) | entry |
| `O20:047C` | founding caller | `_city_create` (`CITY.C`) | inside |
| `R:0238:107E` | status panel | `_status_draw` (`TURN.C`) | entry |
| `R:0403:35CE` | rate menus | `_ai_turn` (`CONTROL.C`) | inside |

This is **address resolution**, not Windows-to-DOS byte equivalence. The
crosswalk's byte-verification count remains 0/21 because no authenticated PE64
address/code range has been paired with these DOS ranges.

The atlas also expands the `_city_process` caller graph. The C call sites
include `_civ_economy` (two), `_kill`, `_find_slot`, `_capunit`,
`_city_disaster` (two), `_trade_rpt`, `_top_five`, `_historian_report`,
`_city_revolt`, `_civ_score`, `_demographics`, `_mood_rpt` and `_city_rpt`.
The earlier five-root-caller receipt was bounded to reloc-backed root calls;
these overlay callers use verified `INT 3F` dispatch.

## Next use

- `CIV_PATHFINDING_TRACE.md` follows the six `PATH.C` routines and verifies the
  unit-record field arithmetic used by the first movement decision.
- The map is the basis for adding symbol names to fDisBull projects without
  guessing: every C entry carries its segment, linear address and map identity.
- Unresolved work remains outside the C tier: resident assembly, C runtime
  symbols, indirect callbacks, and any runtime claim.

## Limits

- The 430 functions are the C functions present in the `*.COD` listings. The
  resident assembly, compiler runtime and some static/library symbols are not
  semantically reconstructed here.
- The two static functions without `CIV.MAP` addresses are identified by their
  COD segment/offset and entry opcode, not by a public-map name.
- The atlas proves addresses, boundaries, call opcodes and targets. It does not
  prove that every C source line is historically original; civd names and
  declarations are reconstructed.
- No DOS program was executed for this atlas.
