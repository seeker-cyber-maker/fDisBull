# Civilization I world snapshot in the Z method

This example reads a real Civilization I DOS save pair read-only and builds one
world representation: an 80 × 50 terrain/entity snapshot, a JSON observation, an
ASCII index, a self-contained HTML viewer and a static SVG. It follows the
Syndicate Z-scene method: source-qualified input, a single spatial scene, an
asset-free viewer, explicit censuses and bounded claims.

No original game files, story assets or save bytes are included. The checked-in
`generated/` artifacts are derived observations from one private save.

## Snapshot

| Item | Value |
| --- | --- |
| Edition | Civilization DOS **47501** (Russian install) |
| SVE | `CIVIL0.SVE`, 37,856 bytes, SHA-256 `a6164c93…` |
| MAP | `CIVIL0.MAP`, 13,128 bytes, SHA-256 `ea82bbca…` |
| Map page | 320 × 200 decoded, 64,000 bytes |
| World | 80 × 50 tiles, 4,000 cells |
| Turn / year | 308 / 1540 AD |
| Human civilization | 1 (Roman in the save's tribe mapping) |
| Cities | 41 (declared and parsed) |
| Units | 172 |
| Special resources | 230 |
| Tiles explored by the human | 181 / 4,000 |
| Terrain | 2,969 ocean, 1,031 land/river tiles |

The save-derived map has 34 deserts, 165 plains, 195 grassland, 103 forest, 77
hills, 52 mountains, 76 tundra, 152 arctic, 36 swamp, 76 jungle, 65 river and
2,969 ocean tiles. These counts are an observation, not a generated world seed.

Validation found zero city-flag mismatches and one unit-owner mismatch: one
Chinese unit shares a tile whose last-owner byte names the Greeks. That is
retained as **stacked-or-stale**, not silently corrected.

## Files

- `tools/civ_world.py` — SVE/MAP decoder, world builder and renderers.
- `tools/build_map.py` — writes `world.json`, `world.txt`, `world.html`,
  `world.svg` and `world-summary.json`.
- `tools/z_provider.py` — read-only JSON provider; no guest process, input or
  memory write.
- `generated/` — the real 47501 snapshot.
- `tests/` — synthetic fixture plus a real-save test that skips when the private
  pair is absent.

## Run

```sh
python tools/build_map.py \
  --save-dir /path/to/private/47501 \
  --out generated \
  --edition 47501
```

The directory must contain `CIVIL0.SVE` and `CIVIL0.MAP`. The private pair is
read in place and never copied into the output.

```sh
python tools/z_provider.py --save-dir /path/to/private/47501 --summary
```

Tests:

```sh
python -m pytest tests -q
```

`CIV_SAVE_DIR` overrides the private save directory for the real-save test.

## Representation

`world.json` has:

- `source` identity and hashes;
- `terrain[50][80]` terrain indices and `terrain_names`;
- `flags[50][80]` improvement bits (city, irrigation, mine, road, railroad,
  fortress, pollution);
- `unit_owner[50][80]` and `unit_present[50][80]` from the map owner layer;
- `explored[50][80]` for the human civilization;
- `resources` with coordinates and special-resource names;
- `cities` with coordinates, owner, size, production, buildings, workers,
  specialists, name id and raw name bytes;
- `units` with civilization, slot, coordinates, canonical type, raw type name,
  domain, status bits, moves, fuel and home city;
- `civ_labels` and `civ_tribe_of` from the save's tribe mapping;
- `stats` and `diagnostics`, then a `source_state_sha256`.

The map page layout follows the game's own accessors: terrain at `(x,y)`,
improvement flags at `(x,y+100)`/`(x,y+150)`, unit owner at `(x+160,y)`, and
exploration in the separate 4,000-byte `map_visible_to` array.

## Limits

- **Read-only.** There is no debugger attach, keyboard input, teleport, turn
  advance or gameplay claim. This is a snapshot, not a playable scene.
- The save pair is one turn of one game. Terrain and entity positions are
  current state, not a world-generation seed or a full history.
- The 47501 city and leader names are stored in an edition-specific encoding;
  `name_raw` is retained but not interpreted. Unit type indices use the
  canonical English names from the source table.
- Fog is the human civilization's exploration bits; it is not a full
  per-civilization visibility reconstruction.
- The map page is an internal rendered database, not the original map resource
  bytes. No native code execution or collision/route proof is implied.
- LZW/RLE behavior is implemented from the documented Civ I format and the
  CivOne CC0 decoder; the real-save test pins this one edition and save pair.
