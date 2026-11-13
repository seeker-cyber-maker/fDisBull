# CIV.EXE unit pathfinding trace (DOS 474.05)

Status: **static, address-linked and call-verified**. The trace follows the six
`PATH.C` routines in the byte-identical civd build and uses Civ64's DOS unit
documentation as the cross-source check for the unit-record fields. It does not
execute the game and makes no runtime pathfinding claim.

## Inputs

| Input | Identity |
| --- | --- |
| `CIV_UNP.EXE` | 340,791 bytes; SHA-256 `aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57` |
| `CIV.MAP` | SHA-256 `42de9270bbb6114d8ff087c11cb33e84f67421ced10c8c9f40f70a2d6f3de0c6` |
| civd source | `PATH.C` at revision `d9214fcd36aa6003d28aae60c3974b665f752280` |
| Civ64 cross-source | `docs/dos/SCENES-PLAY.md` 655–659; `docs/DOS-PROFILE.md` 122–127 |

All six functions are in root code segment `F1E31` and are contiguous:

| Function | Segment:offset | Linear | Source line | Bytes | Calls |
| --- | --- | ---: | ---: | ---: | ---: |
| `_unit_goal` | `F1E31:0000` | `0x1E31E` | 29 | 1,496 | 34 |
| `_path_coarse` | `F1E31:05D8` | `0x1E8F6` | 123 | 1,094 | 8 |
| `_path_select` | `F1E31:0A1E` | `0x1ED3C` | 224 | 497 | 6 |
| `_path_search` | `F1E31:0C0F` | `0x1EF2D` | 290 | 1,279 | 23 |
| `_path_probe` | `F1E31:110E` | `0x1F42C` | 404 | 127 | 3 |
| `_wrap_x` | `F1E31:118D` | `0x1F4AB` | 422 | 36 | 0 |

The first five functions end exactly where the next begins; `_wrap_x` ends at
`0x1F4CF`, followed by a one-byte NOP and the next function at `0x1F4D0`. Every
entry opcode and every call opcode/target in this table was checked against the
unpacked image by `civ_exe_atlas.py`.

## Unit record: civd and Civ64 agree

civd `CIV.H` defines a 12-byte unit record. Civ64 independently describes the
same DOS layout: `DGROUP:81DA/81DB` are `goto_x/goto_y`, the record has a `0Ch`
stride and a `600h` per-civilization stride.

| Offset | Field | Evidence |
| ---: | --- | --- |
| 0 | `status` | `CIV.H` |
| 1 | `x` | `CIV.H`; `unit_goal` reads `[si-7E2Bh]` = `81D5h` |
| 2 | `y` | `CIV.H`; `unit_goal` reads `[si-7E2Ah]` = `81D6h` |
| 3 | `type` | `CIV.H` |
| 4 | `moves` | `CIV.H` |
| 5 | `fuel` | `CIV.H` |
| 6 | `goto_x` | `CIV.H`; `unit_goal` reads `[si-7E26h]` = `81DAh`; Civ64 `DGROUP:81DA` |
| 7 | `goto_y` | `CIV.H`; `unit_goal` reads `[si-7E25h]` = `81DBh`; Civ64 `DGROUP:81DB` |
| 8 | `f8` | last direction; Civ64 notes `FFh` into `81DC` after wake/clear |
| 9 | `visibility` | `CIV.H` |
| 10 | `next` | `CIV.H` |
| 11 | `home_city` | `CIV.H` |

The binary evidence is in `_unit_goal`'s prologue and first field reads:

| Address | Bytes | Instruction | Meaning |
| --- | --- | --- | --- |
| `0x1E326` | `A1 EE D7` | `mov ax, [D7EEh]` | `civnow` (`_civnow` = `2B01:D7EE`) |
| `0x1E331` | `B8 00 06` | `mov ax, 600h` | 1,536 bytes per civilization |
| `0x1E334` | `F7 6E 06` | `imul word [bp+6]` | multiply by `player` |
| `0x1E339` | `B8 0C 00` | `mov ax, 0Ch` | 12 bytes per unit |
| `0x1E33C` | `F7 6E 08` | `imul word [bp+8]` | multiply by `unit` |
| `0x1E341` | `8A 84 DA 81` | `mov al, [si-7E26h]` | `armydata[player][unit].goto_x` |
| `0x1E347` | `8A 8C D5 81` | `mov cl, [si-7E2Bh]` | `.x` |
| `0x1E352` | `8A 84 DB 81` | `mov al, [si-7E25h]` | `.goto_y` |
| `0x1E358` | `8A 8C D6 81` | `mov cl, [si-7E2Ah]` | `.y` |

The two offset bases are consistent: `0x81D4 + 6 = 0x81DA`,
`0x81D4 + 1 = 0x81D5`, `0x81D4 + 7 = 0x81DB`, `0x81D4 + 2 = 0x81D6`.
The source operations at `PATH.C:33-34` therefore have a concrete DOS record
layout, and Civ64's Windows-side `Unit.gotoX/gotoY` identity is corroborated on
the DOS side without claiming identical Windows code.

## Call graph

Internal targets, with call counts:

| Caller | Internal calls |
| --- | --- |
| `_unit_goal` | `_map_random` 3; `_path_search` 2; `_path_coarse` 1; `_map_flags` 3; `_if_open` 2; `_terrain_at` 1; `_map_owner` 1; `_map_city` 1; `_map_region` 1 |
| `_path_coarse` | `_path_select` 2; `_map_dist` 2; `_wrap_x` 1; `_terrain_at` 2 |
| `_path_select` | `_path_probe` 1; `_half_dist` 1; `_terrain_at` 4 |
| `_path_search` | `_wrap_x` 4; `_has_road` 2; `_map_flags` 2; `_map_in_bounds` 1; `_terrain_at` 2; `_map_stack` 2; `_stack_len` 2; `_map_dist` 2 |
| `_path_probe` | `_path_search` 1 |
| `_wrap_x` | none |

The external calls are compiler/runtime helpers (`_abs`, `_memset`). The atlas
verified the opcode and decoded target of all 34 + 8 + 6 + 23 + 3 calls.

## Algorithm summary (source-shaped, not original source)

- `unit_goal` (`PATH.C:29-121`) chooses the next direction. If the active
  player's target is within one tile, it randomizes the residual direction and
  returns a spiral index. Otherwise it fixes a path target, preferring the
  direct target for domain-1 units, and tries short-target `path_search` before
  `path_coarse`/`path_search`. If neither returns a direction, it scans the
  eight neighbours with a cost function:
  - terrain cost × 3 for units with more than one movement point, otherwise 3;
  - 1 when both the current and candidate tiles have the road flag;
  - plus `new_distance * 4 + abs(remaining_x) + abs(remaining_y)`;
  - plus the squared turn angle when `f8` is not `-1`;
  - with owner, city, terrain/domain, region and blocked-origin gates.
  - It clears `goto`/`f8` and returns `-1` when no direction remains, and stops
    when the best direction is the exact reverse of `f8`.
- `path_coarse` (`PATH.C:123-221`) runs a coarse 20×13 BFS from the target to the
  unit, using `coarse_ocean_map` for sea units and `block_ground_way` for land
  units, then chooses the first coarse step back toward the target.
- `path_select` (`PATH.C:224-287`) maps a map coordinate to a coarse cell,
  searches adjacent coarse cells, and calls `path_probe` with an 18-step limit
  before committing to a coarse target.
- `path_search` (`PATH.C:290-402`) runs a local 16×16 cost search around the
  target with a 225-entry queue, road/terrain costs, wrap handling and an
  origin-reached cost cutoff; it returns the best first step.
- `path_probe` (`PATH.C:404-420`) temporarily uses unit slot `[0][127]` as a
  probe, sets its domain to 16 (sea) or 1 (land), and runs `path_search`.
- `wrap_x` wraps x into `0..79`.

## Verified leaf: `_wrap_x`

`_wrap_x` is small enough to verify completely against the binary:

| Address | Bytes | Instruction |
| --- | --- | --- |
| `0x1F4AB` | `55` | `push bp` |
| `0x1F4AC` | `8B EC` | `mov bp, sp` |
| `0x1F4AE` | `83 7E 06 00` | `cmp word [bp+6], 0` |
| `0x1F4B2` | `7D 08` | `jge 0x1F4BC` |
| `0x1F4B4` | `8B 46 06` | `mov ax, [bp+6]` |
| `0x1F4B7` | `05 50 00` | `add ax, 0x50` |
| `0x1F4BA` | `EB 11` | `jmp 0x1F4CD` |
| `0x1F4BC` | `83 7E 06 50` | `cmp word [bp+6], 0x50` |
| `0x1F4C0` | `7C 08` | `jl 0x1F4CA` |
| `0x1F4C2` | `8B 46 06` | `mov ax, [bp+6]` |
| `0x1F4C5` | `2D 50 00` | `sub ax, 0x50` |
| `0x1F4C8` | `EB 03` | `jmp 0x1F4CD` |
| `0x1F4CA` | `8B 46 06` | `mov ax, [bp+6]` |
| `0x1F4CD` | `5D` | `pop bp` |
| `0x1F4CE` | `CB` | `retf` |

This exactly implements `PATH.C:422-427`: `x < 0 → x + 80`,
`x >= 80 → x - 80`, otherwise `x` unchanged.

## Path symbols

| Symbol | Address | Linear |
| --- | --- | ---: |
| `_armydata` | `2B01:81D4` | `0x331E4` |
| `_civnow` | `2B01:D7EE` | `0x387FE` |
| `_path_target_x` | `2B01:6590` | `0x315A0` |
| `_path_target_y` | `2B01:6592` | `0x315A2` |
| `_path_queue_x` | `2B01:6594` | `0x315A4` |
| `_path_queue_y` | `2B01:6694` | `0x316A4` |
| `_path_limit` | `2B01:6794` | `0x317A4` |
| `_path_cache_x` | `2B01:6796` | `0x317A6` |
| `_path_cache_y` | `2B01:6798` | `0x317A8` |
| `_walk_cost` | `2B01:B780` | `0x36790` |
| `_block_steps` | `2B01:D816` | `0x38826` |
| `_block_ground_way` | `2B01:DB44` | `0x38B54` |
| `_coarse_ocean_map` | `2B01:7F38` | `0x32F48` |
| `_spiral_x` | `2B01:1882` | `0x2C892` |
| `_spiral_y` | `2B01:18E4` | `0x2C8F4` |
| `_terrains` | `2B01:0282` | `0x2B292` |

## What is proven and what is not

**Proven here**

- The six `PATH.C` functions occupy the stated DOS addresses; entries, sizes,
  boundaries and call graph match the binary.
- The unit-record stride and `goto_x/goto_y` offsets are used by the binary at
  `_unit_goal`; Civ64's DOS description and civd's structure agree.
- `_wrap_x` is byte-for-byte consistent with its source rule.

**Not proven here**

- That every branch is reachable at runtime, or that the reconstructed source is
  historically the original source.
- Any particular path chosen in a live game; that requires a runtime
  observation of a unit's `goto`, position, moves and next direction.
- Windows/DOS code equivalence; Civ64's Windows routines remain a semantic
  crosswalk, not a byte comparison.
- Complete coverage of indirect calls, resident assembly or compiler runtime.

## Next probe

A bounded runtime observation can bind the static model: set a unit's
`goto_x/goto_y`, step once, and record the unit record fields plus the returned
direction. The expected state transition is `f8 := direction`,
`moves := moves - cost`, with `goto`/`f8` cleared when the target is reached or
the reverse direction is selected. This would promote the pathfinding slice from
static address proof to runtime agreement; it should not be assumed from the
source alone.
