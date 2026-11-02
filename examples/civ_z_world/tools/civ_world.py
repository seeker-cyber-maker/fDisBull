"""Read a Civilization I DOS save pair as a bounded Z world snapshot.

The SVE supplies turn/entity state; the MAP file is the game's 320x200 map
page, RLE+LZW compressed. This module decodes both read-only. It does not run
the game, evaluate AI, or claim that a snapshot is a playable world.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

MAP_WIDTH = 80
MAP_HEIGHT = 50
PAGE_WIDTH = 320
PAGE_HEIGHT = 200
SVE_SIZE = 0x93E0

TERRAIN_NAMES = (
    "Desert",
    "Plains",
    "Grassland",
    "Forest",
    "Hills",
    "Mountains",
    "Tundra",
    "Arctic",
    "Swamp",
    "Jungle",
    "Ocean",
    "River",
)
SPECIAL_NAMES = (
    "Oasis",
    "Horses",
    "Grassland",
    "Game",
    "Coal",
    "Gold",
    "Game",
    "Seals",
    "Oil",
    "Gems",
    "Fish",
    "River",
)
TERRAIN_MAP = (-1, 10, 3, 8, -1, -1, 1, 6, -1, 11, 2, 9, 4, 5, 0, 7)
TERRAIN_GLYPHS = {
    "Desert": ":",
    "Plains": ".",
    "Grassland": ",",
    "Forest": "T",
    "Hills": "n",
    "Mountains": "^",
    "Tundra": "_",
    "Arctic": "*",
    "Swamp": "%",
    "Jungle": "J",
    "Ocean": "~",
    "River": "r",
    "Unknown": "?",
}
FLAG_NAMES = {
    0x01: "city",
    0x02: "irrigation",
    0x04: "mine",
    0x08: "road",
    0x10: "railroad",
    0x20: "fortress",
    0x40: "pollution",
}
DOMAIN_NAMES = {0: "land", 1: "air", 2: "sea"}
UNIT_TYPE_NAMES = (
    "Settlers",
    "Militia",
    "Phalanx",
    "Legion",
    "Musketeers",
    "Riflemen",
    "Cavalry",
    "Knights",
    "Catapult",
    "Cannon",
    "Chariot",
    "Armor",
    "Mech. Inf.",
    "Artillery",
    "Fighter",
    "Bomber",
    "Trireme",
    "Sail",
    "Frigate",
    "Ironclad",
    "Cruiser",
    "Battleship",
    "Submarine",
    "Carrier",
    "Transport",
    "Nuclear",
    "Diplomat",
    "Caravan",
)
TRIBE_NAMES = {
    0: "Barbarian",
    1: "Roman",
    2: "Babylonian",
    3: "German",
    4: "Egyptian",
    5: "American",
    6: "Greek",
    7: "Indian",
    8: "",
    9: "Russian",
    10: "Zulu",
    11: "French",
    12: "Aztec",
    13: "Chinese",
    14: "English",
    15: "Mongol",
}


class CivError(ValueError):
    """A Civilization snapshot is malformed or unsupported."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def decode_lzw(stream: bytes, *, min_bits: int = 8, max_bits: int = 11) -> bytes:
    """Decode MicroProse's LSB-first variable-width LZW stream.

    The dictionary starts with 256 roots and one reserved empty entry. Code 0x100
    terminates the stream. Code width follows the current dictionary size, and
    the dictionary is flushed when the next width would exceed max_bits. This
    matches the CivOne (CC0) reconstruction of the original decoder.
    """
    dictionary: dict[int, bytes] = {i: bytes([i]) for i in range(1 << min_bits)}
    dictionary[len(dictionary)] = b""
    seen = set(dictionary.values())
    value = 0
    counter = 0
    entry = b""
    output = bytearray()
    for byte in stream:
        for bit in range(8):
            value |= ((byte >> bit) & 1) << counter
            counter += 1
            width = min(len(dictionary).bit_length(), max_bits)
            if counter != width:
                continue
            if value == (1 << min_bits):
                return bytes(output)
            if value not in dictionary:
                candidate = entry + entry[:1]
                if candidate in seen:
                    raise CivError(
                        f"LZW code {value} is absent from a {len(dictionary)}-code dictionary"
                    )
                dictionary[len(dictionary)] = candidate
                seen.add(candidate)
            out_value = dictionary[value]
            new_entry = entry + out_value[:1]
            output.extend(out_value)
            if new_entry not in seen:
                dictionary[len(dictionary)] = new_entry
                seen.add(new_entry)
            entry = out_value
            value = 0
            counter = 0
            if len(dictionary).bit_length() > max_bits:
                dictionary = {i: bytes([i]) for i in range(1 << min_bits)}
                dictionary[len(dictionary)] = b""
                seen = set(dictionary.values())
                entry = b""
    return bytes(output)


def decode_rle(stream: bytes, expected: int) -> bytes:
    """Expand the 0x90 escape byte after LZW decoding, including a trailing run."""
    output = bytearray()
    previous = 0
    repeat = 0
    index = 0
    while index < len(stream) or repeat:
        if repeat:
            output.append(previous)
            repeat -= 1
            continue
        value = stream[index]
        index += 1
        if value == 0x90:
            if index >= len(stream):
                raise CivError("truncated RLE escape")
            count = stream[index]
            index += 1
            if count == 0:
                output.append(0x90)
            else:
                repeat = count - 1
        else:
            output.append(value)
            previous = value
        if len(output) > expected:
            raise CivError(f"RLE expansion exceeds {expected} bytes")
    if len(output) != expected:
        raise CivError(
            f"RLE expansion produced {len(output)} bytes, expected {expected}"
        )
    return bytes(output)


def decode_map(data: bytes) -> bytes:
    """Decode a CIVIL?.MAP page into exactly 320x200 bytes."""
    if len(data) < 10:
        raise CivError("map file is shorter than its header")
    if data[:2] != b"X0":
        raise CivError("unsupported map signature")
    width = int.from_bytes(data[4:6], "little")
    height = int.from_bytes(data[6:8], "little")
    if (width, height) != (PAGE_WIDTH, PAGE_HEIGHT):
        raise CivError(f"unsupported map dimensions {width}x{height}")
    limit = data[8]
    if not 8 <= limit <= 12:
        raise CivError(f"unsupported LZW width limit {limit}")
    lzw = decode_lzw(data[9:], max_bits=limit)
    return decode_rle(lzw, width * height)


def _text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def _city_records(sve: bytes) -> list[dict[str, Any]]:
    cities = []
    for index in range(128):
        offset = 0x1508 + index * 28
        record = sve[offset : offset + 28]
        buildings = struct.unpack_from("<I", record, 0)[0]
        x, y, status, size, visible_size, production, trade, owner = struct.unpack_from(
            "<8b", record, 4
        )
        food_box, shield_box = struct.unpack_from("<2h", record, 12)
        workers = struct.unpack_from("<I", record, 16)[0]
        specialists = struct.unpack_from("<h", record, 20)[0]
        name_id = record[22]
        routes = tuple(record[23:26])
        garrison = struct.unpack_from("<2b", record, 26)
        if (
            size <= 0
            or not (0 <= owner < 8)
            or not (0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT)
        ):
            continue
        cities.append(
            {
                "index": index,
                "x": x,
                "y": y,
                "owner": owner,
                "size": size,
                "visible_size": visible_size,
                "status": status,
                "production": production,
                "trade": trade,
                "buildings": buildings,
                "food_box": food_box,
                "shield_box": shield_box,
                "workers": workers,
                "specialists": specialists,
                "name_id": name_id,
                "name_raw": _text(
                    sve[0x6970 + name_id * 13 : 0x6970 + (name_id + 1) * 13]
                ),
                "routes": list(routes),
                "garrison": list(garrison),
            }
        )
    return cities


def _unit_types(sve: bytes) -> list[dict[str, Any]]:
    types = []
    for index in range(28):
        offset = 0x2308 + index * 34
        record = sve[offset : offset + 34]
        fields = struct.unpack_from("<11h", record, 12)
        types.append(
            {
                "index": index,
                "name": UNIT_TYPE_NAMES[index],
                "name_raw": _text(record[:12]),
                "obsolete_by": fields[0],
                "domain": fields[1],
                "moves": fields[2],
                "fuel": fields[3],
                "attack": fields[4],
                "defense": fields[5],
                "cost": fields[6],
                "sight": fields[7],
                "capacity": fields[8],
                "role": fields[9],
                "prereq": fields[10],
            }
        )
    return types


def _units(
    sve: bytes, unit_types: list[dict[str, Any]], civ_labels: list[str]
) -> list[dict[str, Any]]:
    units = []
    for civ in range(8):
        for slot in range(128):
            offset = 0x26C0 + (civ * 128 + slot) * 12
            record = sve[offset : offset + 12]
            status, x, y = struct.unpack_from("<3B", record, 0)
            unit_type, moves, fuel, goto_x, goto_y, f8, visibility, next, home = (
                struct.unpack_from("<9b", record, 3)
            )
            if unit_type < 0 or unit_type >= len(unit_types):
                continue
            if not (0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT):
                continue
            definition = unit_types[unit_type]
            units.append(
                {
                    "civ": civ,
                    "slot": slot,
                    "x": x,
                    "y": y,
                    "type": unit_type,
                    "type_name": definition["name"],
                    "type_name_raw": definition["name_raw"],
                    "domain": definition["domain"],
                    "domain_name": DOMAIN_NAMES.get(definition["domain"], "unknown"),
                    "status": status,
                    "sentry": bool(status & 0x01),
                    "fortified": bool(status & 0x08),
                    "veteran": bool(status & 0x20),
                    "moves": moves,
                    "fuel": fuel,
                    "goto": [goto_x, goto_y],
                    "last_direction": f8,
                    "visibility": visibility & 0xFF,
                    "next": next,
                    "home_city": home,
                }
            )
    return units


def _civ_names(sve: bytes) -> list[str]:
    return [_text(sve[0x80 + i * 12 : 0x80 + (i + 1) * 12]) for i in range(8)]


def _leader_names(sve: bytes) -> list[str]:
    return [_text(sve[0x10 + i * 14 : 0x10 + (i + 1) * 14]) for i in range(8)]


def _patterned(x: int, y: int, seed: int) -> bool:
    if y <= 1 or y >= 48:
        return False
    value = (x >> 2) * 13 + (y >> 2) * 11 + seed
    return (x & 3) * 4 + (y & 3) == (value & 0x0F)


def world_from_page(
    sve: bytes,
    page: bytes,
    *,
    edition: str,
    sve_name: str,
    map_name: str,
) -> dict[str, Any]:
    if len(sve) != SVE_SIZE:
        raise CivError(f"SVE is {len(sve)} bytes, expected {SVE_SIZE}")
    if len(page) != PAGE_WIDTH * PAGE_HEIGHT:
        raise CivError(
            f"map page is {len(page)} bytes, expected {PAGE_WIDTH * PAGE_HEIGHT}"
        )
    turn, civnow, human_set, seed, year, tier, players, selected = struct.unpack_from(
        "<8h", sve, 0
    )
    civ_names = _civ_names(sve)
    leader_names = _leader_names(sve)
    tribe_of = struct.unpack_from("<8h", sve, 0x0778)
    civ_labels = [
        TRIBE_NAMES.get(value & 0x0F, "unknown") if value >= 0 else "Barbarian"
        for value in tribe_of
    ]
    unit_types = _unit_types(sve)
    cities = _city_records(sve)
    for city in cities:
        city["owner_label"] = civ_labels[city["owner"]]
    units = _units(sve, unit_types, civ_labels)

    def cell(plane_x: int, plane_y: int) -> int:
        return page[plane_y * PAGE_WIDTH + plane_x]

    terrain = [[-1] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    flags = [[0] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    unit_owner = [[-1] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    unit_present = [[False] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    explored = [[False] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
    resources: list[dict[str, Any]] = []
    terrain_counts = {name: 0 for name in TERRAIN_NAMES}
    terrain_counts["Unknown"] = 0
    explored_count = 0
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            encoded = cell(x, y)
            index = TERRAIN_MAP[encoded] if 0 <= encoded < len(TERRAIN_MAP) else -1
            terrain[y][x] = index
            name = (
                TERRAIN_NAMES[index] if 0 <= index < len(TERRAIN_NAMES) else "Unknown"
            )
            terrain_counts[name] += 1
            flags[y][x] = cell(x, y + 100) | (cell(x, y + 150) << 4)
            raw_owner = cell(x + 160, y)
            unit_present[y][x] = bool(raw_owner & 0x08)
            unit_owner[y][x] = (raw_owner & 0x07) if unit_present[y][x] else -1
            explored[y][x] = bool(
                sve[0x56C0 + x * MAP_HEIGHT + y] & (1 << (civnow & 7))
            )
            explored_count += int(explored[y][x])
            if index >= 0 and _patterned(x, y, seed):
                resources.append(
                    {
                        "x": x,
                        "y": y,
                        "terrain": name,
                        "special": SPECIAL_NAMES[index],
                    }
                )

    diagnostics: list[dict[str, str]] = []
    city_mismatches = 0
    for city in cities:
        if not flags[city["y"]][city["x"]] & 0x01:
            city_mismatches += 1
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "city-tile-not-marked",
                    "subject": f"city-{city['index']}",
                    "message": f"({city['x']},{city['y']}) lacks the city flag",
                }
            )
        if unit_owner[city["y"]][city["x"]] not in (-1, city["owner"]):
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "city-unit-owner-differs",
                    "subject": f"city-{city['index']}",
                    "message": f"tile unit owner {unit_owner[city['y']][city['x']]} != city owner {city['owner']}",
                }
            )
    unit_mismatches = 0
    for unit in units:
        if not unit_present[unit["y"]][unit["x"]]:
            unit_mismatches += 1
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "unit-tile-not-marked",
                    "subject": f"unit-{unit['civ']}-{unit['slot']}",
                    "message": f"({unit['x']},{unit['y']}) lacks the unit-present bit",
                }
            )
        elif unit_owner[unit["y"]][unit["x"]] != unit["civ"]:
            unit_mismatches += 1
            diagnostics.append(
                {
                    "severity": "info",
                    "code": "unit-stacked-or-stale-owner",
                    "subject": f"unit-{unit['civ']}-{unit['slot']}",
                    "message": f"tile owner {unit_owner[unit['y']][unit['x']]} != unit civ {unit['civ']}",
                }
            )
    declared_cities = sum(struct.unpack_from("<8h", sve, 0x06C8))
    if declared_cities != len(cities):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "city-count-mismatch",
                "subject": "city_count",
                "message": f"declared {declared_cities}, parsed {len(cities)}",
            }
        )
    unknown_terrain = terrain_counts["Unknown"]
    if unknown_terrain:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unknown-terrain",
                "subject": "terrain",
                "message": f"{unknown_terrain} tiles use an unmapped encoded terrain",
            }
        )

    city_counts = [0] * 8
    for city in cities:
        city_counts[city["owner"]] += 1
    unit_counts = [0] * 8
    for unit in units:
        unit_counts[unit["civ"]] += 1
    unit_type_counts: dict[str, int] = {}
    for unit in units:
        unit_type_counts[unit["type_name"]] = (
            unit_type_counts.get(unit["type_name"], 0) + 1
        )

    payload = {
        "format": "civ-world-0",
        "dimensions": [MAP_WIDTH, MAP_HEIGHT],
        "turn": turn,
        "year": year,
        "tier": tier,
        "players_mask": players,
        "human_civ": civnow,
        "human_set": human_set,
        "selected_index": selected,
        "map_rng_state": seed,
        "civ_labels": civ_labels,
        "civ_tribe_of": list(tribe_of),
        "civ_names_raw": civ_names,
        "leader_names_raw": leader_names,
        "terrain_names": list(TERRAIN_NAMES),
        "terrain": terrain,
        "flags": flags,
        "unit_owner": unit_owner,
        "unit_present": unit_present,
        "explored": explored,
        "resources": resources,
        "cities": cities,
        "units": units,
        "unit_types": unit_types,
        "stats": {
            "terrain_counts": terrain_counts,
            "resources": len(resources),
            "cities": len(cities),
            "units": len(units),
            "cities_by_civ": city_counts,
            "units_by_civ": unit_counts,
            "unit_types": unit_type_counts,
            "explored_tiles": explored_count,
            "declared_cities": declared_cities,
            "city_tile_mismatches": city_mismatches,
            "unit_tile_mismatches": unit_mismatches,
        },
        "diagnostics": diagnostics,
    }
    payload["source_state_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    payload["source"] = {
        "edition": edition,
        "sve": sve_name,
        "map": map_name,
        "sve_sha256": hashlib.sha256(sve).hexdigest(),
        "map_sha256": hashlib.sha256(page).hexdigest(),
        "map_file_sha256": hashlib.sha256(page).hexdigest(),
        "sve_size": len(sve),
        "map_page_size": len(page),
        "format": "civ-world-0",
    }
    return payload


def read_world(
    sve_path: Path, map_path: Path, *, edition: str = "unknown"
) -> dict[str, Any]:
    sve = sve_path.read_bytes()
    map_file = map_path.read_bytes()
    page = decode_map(map_file)
    world = world_from_page(
        sve,
        page,
        edition=edition,
        sve_name=sve_path.name,
        map_name=map_path.name,
    )
    world["source"]["map_file_sha256"] = hashlib.sha256(map_file).hexdigest()
    return world


def render_ascii(world: dict[str, Any]) -> str:
    terrain = world["terrain"]
    rows = []
    for y in range(MAP_HEIGHT):
        row = []
        for x in range(MAP_WIDTH):
            index = terrain[y][x]
            name = (
                TERRAIN_NAMES[index] if 0 <= index < len(TERRAIN_NAMES) else "Unknown"
            )
            row.append(TERRAIN_GLYPHS[name])
        rows.append("".join(row))
    city_at = {(city["x"], city["y"]): city for city in world["cities"]}
    units_at: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for unit in world["units"]:
        units_at.setdefault((unit["x"], unit["y"]), []).append(unit)
    entity_rows = []
    for y in range(MAP_HEIGHT):
        row = []
        for x in range(MAP_WIDTH):
            if (x, y) in city_at:
                row.append(str(city_at[(x, y)]["owner"] + 1))
            elif (x, y) in units_at:
                row.append(chr(ord("a") + units_at[(x, y)][0]["civ"]))
            else:
                row.append(".")
        entity_rows.append("".join(row))
    lines = [
        f"Civilization I world: {world['source']['edition']}",
        f"turn {world['turn']}  year {world['year']}  human civ {world['human_civ']}",
        f"cities {world['stats']['cities']}  units {world['stats']['units']}  resources {world['stats']['resources']}",
        "",
        "== terrain (80x50; ~ ocean, . plains, , grass, T forest, n hills, ^ mountains, _ tundra, * arctic, % swamp, J jungle, : desert, r river) ==",
        *rows,
        "",
        "== entities (city owner 1-8; unit owner a-h; * both) ==",
        *entity_rows,
        "",
        "diagnostics:",
    ]
    if not world["diagnostics"]:
        lines.append("  none")
    for entry in world["diagnostics"]:
        lines.append(
            f"  {entry['severity']}: {entry['code']} {entry['subject']} - {entry['message']}"
        )
    return "\n".join(lines) + "\n"


def render_html(world: dict[str, Any]) -> str:
    data = json.dumps(world, separators=(",", ":"), sort_keys=False).replace(
        "</", "<\\/"
    )
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Civilization I | world snapshot</title>
<style>
body {{ margin:0; background:#101820; color:#e8eff4; font:15px system-ui,sans-serif; }}
header {{ padding:18px 24px; border-bottom:1px solid #384854; }}
h1 {{ font-size:24px; margin:2px 0 8px; }} p {{ max-width:980px; line-height:1.45; }}
main {{ padding:18px 24px; display:grid; grid-template-columns:minmax(520px,1fr) 300px; gap:18px; }}
.panel {{ background:#192630; border:1px solid #3b4b58; border-radius:8px; padding:14px; }}
canvas {{ width:100%; max-width:900px; image-rendering:pixelated; background:#0b1218; cursor:crosshair; }}
small,.muted {{ color:#b2c3ce; }} table {{ border-collapse:collapse; width:100%; }}
td,th {{ padding:5px 4px; border-bottom:1px solid #344652; text-align:left; font-size:13px; }}
#tip {{ min-height:62px; }} .swatch {{ display:inline-block; width:11px; height:11px; border-radius:2px; vertical-align:-1px; margin-right:5px; }}
</style>
<header><small>ORIGINAL-SAVE OBSERVATION · READ-ONLY · {world["source"]["edition"]}</small>
<h1>Civilization I: one world snapshot, not a playthrough</h1>
<p>80 × 50 tiles from the saved map page. Turn {world["turn"]}, {world["year"]} AD.
{world["stats"]["cities"]} cities and {world["stats"]["units"]} registered units.
Terrain and entity positions are decoded from the save pair; fog, gameplay state and AI are not reconstructed.</p></header>
<main><section class="panel"><canvas id="map" width="800" height="500"></canvas>
<p id="tip" class="muted">Point at a tile for terrain, flags, city and unit records.</p></section>
<section class="panel"><h3>Snapshot</h3><table id="counts"></table>
<h3>Diagnostics</h3><ul id="diag"></ul></section></main>
<script>const w={data};
const c=document.getElementById('map'),ctx=c.getContext('2d');const s=10;
const colors={{Desert:'#b9a36a',Plains:'#9daa62',Grassland:'#6f9b4d',Forest:'#3f6b3b',Hills:'#8b754c',Mountains:'#77736d',Tundra:'#b7b9ae',Arctic:'#e8edf0',Swamp:'#5d7055',Jungle:'#2f6b43',Ocean:'#2f5d86',River:'#3d83a8',Unknown:'#ff00ff'}};
const ownerColors=['#d9534f','#5bc0de','#5cb85c','#f0ad4e','#9b59b6','#e67e22','#1abc9c','#cccccc'];
const cities=new Map(w.cities.map(x=>[x.x+','+x.y,x])),units=new Map();
for(const u of w.units){{let k=u.x+','+u.y;if(!units.has(k))units.set(k,[]);units.get(k).push(u)}}
function draw(){{ctx.fillStyle='#0b1218';ctx.fillRect(0,0,c.width,c.height);
for(let y=0;y<50;y++)for(let x=0;x<80;x++){{let t=w.terrain[y][x],n=w.terrain_names[t]||'Unknown';ctx.fillStyle=colors[n]||'#333';ctx.fillRect(x*s,y*s,s-.5,s-.5)}}
for(const u of w.units){{ctx.fillStyle=ownerColors[u.civ];ctx.beginPath();ctx.arc(u.x*s+5,u.y*s+5,2.6,0,Math.PI*2);ctx.fill()}}
for(const city of w.cities){{ctx.fillStyle=ownerColors[city.owner];ctx.fillRect(city.x*s+1,city.y*s+1,s-2,s-2);ctx.strokeStyle='#101820';ctx.lineWidth=1.5;ctx.strokeRect(city.x*s+1,city.y*s+1,s-2,s-2);ctx.fillStyle='#fff';ctx.font='bold 9px system-ui';ctx.fillText(String(city.size),city.x*s+2,city.y*s+9)}}}}
document.getElementById('counts').innerHTML='<tr><th>Item</th><th>Value</th></tr>'+[['Turn',w.turn],['Year',w.year],['Human civ',w.human_civ],['Cities',w.stats.cities],['Units',w.stats.units],['Resources',w.stats.resources],['Explored by human',w.stats.explored_tiles+' / 4000']].map(([a,b])=>`<tr><td>${{a}}</td><td>${{b}}</td></tr>`).join('');
document.getElementById('diag').innerHTML=w.diagnostics.length?w.diagnostics.map(d=>`<li><b>${{d.code}}</b> ${{d.subject}}: ${{d.message}}</li>`).join(''):'<li>none</li>';
c.onmousemove=e=>{{let r=c.getBoundingClientRect(),x=Math.floor((e.clientX-r.left)/r.width*80),y=Math.floor((e.clientY-r.top)/r.height*50);if(x<0||y<0||x>=80||y>=50)return;let t=w.terrain[y][x],name=w.terrain_names[t]||'Unknown';let fl=w.flags[y][x],names=Object.entries({{1:'city',2:'irrigation',4:'mine',8:'road',16:'railroad',32:'fortress',64:'pollution'}}).filter(([m])=>fl&+m).map(([,n])=>n);let city=cities.get(x+','+y),us=units.get(x+','+y)||[];document.getElementById('tip').textContent=`(${{x}},${{y}}) ${{name}}; flags ${{names.join(', ')||'none'}}; city ${{city?('#'+city.index+' size '+city.size+' '+city.owner_label):'none'}}; units ${{us.map(u=>u.type_name+' ('+u.civ_label+')').join(', ')||'none'}}`}};
draw();
</script></html>
"""


def render_svg(world: dict[str, Any]) -> str:
    """A self-contained terrain/entity SVG; positions are tile coordinates."""
    colors = {
        "Desert": "#b9a36a",
        "Plains": "#9daa62",
        "Grassland": "#6f9b4d",
        "Forest": "#3f6b3b",
        "Hills": "#8b754c",
        "Mountains": "#77736d",
        "Tundra": "#b7b9ae",
        "Arctic": "#e8edf0",
        "Swamp": "#5d7055",
        "Jungle": "#2f6b43",
        "Ocean": "#2f5d86",
        "River": "#3d83a8",
        "Unknown": "#ff00ff",
    }
    owner_colors = [
        "#d9534f",
        "#5bc0de",
        "#5cb85c",
        "#f0ad4e",
        "#9b59b6",
        "#e67e22",
        "#1abc9c",
        "#cccccc",
    ]
    cell = 8
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 430" width="660" height="430">',
        '<rect width="660" height="430" fill="#101820"/>',
        f'<text x="10" y="18" fill="#e8eff4" font-family="system-ui" font-size="13">Civilization I world — turn {world["turn"]}, {world["year"]} AD — {world["stats"]["cities"]} cities, {world["stats"]["units"]} units</text>',
    ]
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            index = world["terrain"][y][x]
            name = (
                TERRAIN_NAMES[index] if 0 <= index < len(TERRAIN_NAMES) else "Unknown"
            )
            parts.append(
                f'<rect x="{10 + x * cell}" y="{26 + y * cell}" width="{cell}" height="{cell}" fill="{colors[name]}"/>'
            )
    for unit in world["units"]:
        parts.append(
            f'<circle cx="{10 + unit["x"] * cell + 4}" cy="{26 + unit["y"] * cell + 4}" r="2.2" fill="{owner_colors[unit["civ"]]}" stroke="#101820" stroke-width="0.5"/>'
        )
    for city in world["cities"]:
        parts.append(
            f'<rect x="{10 + city["x"] * cell + 1}" y="{26 + city["y"] * cell + 1}" width="{cell - 2}" height="{cell - 2}" fill="{owner_colors[city["owner"]]}" stroke="#101820" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{10 + city["x"] * cell + 3}" y="{26 + city["y"] * cell + 8}" fill="#ffffff" font-family="system-ui" font-size="6">{city["size"]}</text>'
        )
    legend = [
        ("Desert", 10),
        ("Plains", 80),
        ("Grassland", 160),
        ("Forest", 240),
        ("Hills", 320),
        ("Mountains", 390),
        ("Tundra", 470),
        ("Arctic", 540),
        ("Ocean", 610),
    ]
    for index, (name, x) in enumerate(legend):
        parts.append(
            f'<rect x="{x}" y="426" width="8" height="8" fill="{colors[name]}"/>'
        )
        parts.append(
            f'<text x="{x + 10}" y="433" fill="#b2c3ce" font-family="system-ui" font-size="6">{name[:4]}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def summarize(world: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": world["format"],
        "source": world["source"],
        "turn": world["turn"],
        "year": world["year"],
        "human_civ": world["human_civ"],
        "stats": world["stats"],
        "diagnostics": world["diagnostics"],
    }
