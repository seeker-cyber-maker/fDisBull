# Civilization I: one world snapshot in the Z method

Date: 31 October 2026. Source: a privately held Civilization DOS **47501**
save pair. Read-only; no guest process, input, memory write or gameplay route was
executed for this result. Derived artifacts contain no original save bytes.

## Result

A real 80 × 50 world snapshot was decoded from `CIVIL0.SVE` and `CIVIL0.MAP`:
41 cities, 172 units, 230 special-resource tiles, 181 human-explored tiles and a
complete terrain/flag/owner representation. The same pair was rendered as JSON,
an ASCII index, an offline HTML map and an SVG.

The map page is a 320 × 200 byte database, not a screenshot. The decoder expands
the MicroProse LZW stream and then the 0x90 RLE escape, producing exactly 64,000
bytes. Terrain, flags, unit-owner and exploration planes are read with the
game's own offsets.

## Source identity

| Item | Value |
| --- | --- |
| Edition | 47501 |
| `CIVIL0.SVE` | 37,856 bytes; `a6164c93bcb5ee75ba09b407b2dff527a2433993b963c48b3e573c6e06ffc63b` |
| `CIVIL0.MAP` | 13,128 bytes; `ea82bbca9ee1e6c87cc7ed17fa153ab7251c5e94968f35d8eb3bc1f0fff0b922` |
| Decoded page | 64,000 bytes; `e4616630dcab0e8198b776c2fc324c42d87eb7db1774d5c67bd5ec01b0666226` |
| Turn / year | 308 / 1540 AD |
| Human | civilization slot 1; tribe mapping says Roman |

The save's `civ_tribe_of` array is used for labels; the raw city/leader names
are retained but not decoded because the Russian edition uses an unresolved
character mapping.

## One scene, four views

| Layer | Meaning |
| --- | --- |
| Terrain | 12 base terrain indices per tile |
| Improvement flags | city, irrigation, mine, road, railroad, fortress, pollution |
| Unit owner / present | last-owner byte low three bits plus occupied bit |
| Explored | human civilization bit from `map_visible_to` |
| Cities | 128 city records; 41 active |
| Units | 8 × 128 records; 172 active |
| Resources | `patterned_cell` derived from `map_rng_state` |

## Census

Terrain: 34 desert, 165 plains, 195 grassland, 103 forest, 77 hills, 52
mountains, 76 tundra, 152 arctic, 36 swamp, 76 jungle, 2,969 ocean, 65 river.

Cities by civilization slot: 0, 5, 1, 0, 7, 11, 12, 5. Units by slot: 0, 9, 8,
0, 20, 57, 54, 24. Unit types present include 73 Riflemen, 23 Phalanx, 19
Settlers, 7 Catapults, 7 Musketeers and 7 Knights.

Validation:

- All 41 city records appear on tiles marked with the city flag.
- 171/172 units match the unit-present bit and last-owner civilization.
- One unit (Chinese slot 20 at `(36,24)`) is on a tile whose last owner is
  Greek. It is retained as `unit-stacked-or-stale-owner`; the map layer cannot
  distinguish a stack from a stale byte without a further source.
- Declared city count equals parsed active cities (41).
- No unknown terrain codes.

## Method and limits

The representation is an original-save observation, not a reconstruction of
the game's world generator or AI. The save pair is needed together: the SVE
contains turn, city and unit records; the MAP contains the map page.

The example deliberately does not attach a debugger or send input. The
Syndicate PR's guarded actions have no counterpart here because no action was
attempted. A future live provider would need a source-qualified debugger session
and separate action receipts.

JSON/HTML/SVG positions are tile coordinates. The map page has no camera,
world-to-screen transform or terrain mesh; no collision, movement cost or
line-of-sight proof is claimed.
