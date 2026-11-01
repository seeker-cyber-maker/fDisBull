"""Offline source/terrain support for authoring an ordinary-input KQ1 movie.

No emulator calls, keyboard injection, guest writes, sleeps or execution here.
The caller observes the original game, chooses inputs, and records them in JPC-RR.
Static paths and source contracts are proposals, not evidence of native success.
"""
from __future__ import annotations

from collections import deque
from functools import lru_cache
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parent
WORKSPACE = RESULTS.parent
DEFAULT_GAME = WORKSPACE / "private-recovery/inputs/kings_quest"
DEFAULT_DECODER = WORKSPACE / "fDisBull/src/fdisbull/agi_picture.py"
CANDIDATE_PATH = RESULTS / "route-candidate.json"
WIDTH, HEIGHT = 160, 168

# Floors are admissible baseline y, not the last forbidden horizon row.
# Room3 starts with observe.blocks; f62 switches it to ignore.blocks later.
# The44 floor for47/48 is the conservative prior-planner policy, not a recovered
# set.horizon instruction in either local logic. All requested paths lie above it.
PLAN_REQUESTS = {
    3: dict(room=2, goal=(1, 140), y_min=51, allow_priority_one=True),
    5: dict(room=3, goal=(140, 134), y_min=47, allow_priority_one=False),
    14: dict(room=1, goal=(151, 51), y_min=51, allow_priority_one=True),
    62: dict(room=48, goal=(129, 140), y_min=44, allow_priority_one=False),
    70: dict(room=47, goal=(94, 90), y_min=44, allow_priority_one=True),
}
_DEFAULT_POLICIES = {p["room"]: (p["y_min"], p["allow_priority_one"]) for p in PLAN_REQUESTS.values()}
_DIRECTIONS = ((1, 0, "right"), (-1, 0, "left"), (0, 1, "down"), (0, -1, "up"),
               (1, 1, "se"), (-1, 1, "sw"), (1, -1, "ne"), (-1, -1, "nw"))


ACTOR_STRIDE = 43
ACTOR_FLAGS_OFFSET = 37
ACTOR_FLAG_MASKS = dict(drawn=0x0001, animated=0x0040, updating=0x0010, cycling=0x0020,
                        ignore_objects=0x0200, ignore_blocks=0x0002)
PLAYER_CONTROL_OFFSET = 0x139  # u16LE: program.control writes0, player.control writes1.
# These offsets belong to the original AGI2.917 DOS executable after unpacking,
# not to a modern reimplementation's structure. The handler dispatch records
# anchor hash-only witnesses to original AGI commands; paired set/clear operations
# establish the masks. Addresses below are offsets relative to the captured CS
# or DS, so a caller can requalify a relocated instance using a passive RAM copy.
ACTOR_LAYOUT_EVIDENCE = {
    "interpreter": "original DOS AGI2.917, KQ1 2.0F input",
    "qualification": "native instruction and opcode-dispatch witnesses; read-only analysis",
    "capture": "private-recovery/kq1-standard-tas-20261101/authoring-smoke/ram.bin",
    "capture_sha256": "85802319daa5eee98649f0552945511f962e981d1bc10edd502437acc4013659",
    "capture_length": 655360,
    "capture_time_ns": 2880000000,
    "capture_cs_base": 0x36AE0,
    "capture_ds_base": 0x40A30,
    "dispatch_offset": 0x61D,
    "dispatch_stride": 4,
    "actor_table_pointer_offset": 0x963,
    "player_control_offset": PLAYER_CONTROL_OFFSET,
    "dispatch": [
        {"opcode": 18, "command": "new.room", "length": 4, "sha256": "eb258a68bdef9c57bb5d8ddd650818f0a069132179039d124f6647d1cd27f333"},
        {"opcode": 19, "command": "new.room.v", "length": 4, "sha256": "aae039cfefb8de6fe453c17962c79e0d2275d2057be8a0f5c3187038b9aad325"},
        {"opcode": 33, "command": "animate.obj", "length": 4, "sha256": "1bb551af457623f29df8fc45c62172cdaf75e9fb9bfd950b6528421d011426bf"},
        {"opcode": 34, "command": "unanimate.all", "length": 4, "sha256": "a76536b63d9e06867efdc17c94fb8b0b97c63da328bd36bd33669a0240c7276e"},
        {"opcode": 35, "command": "draw", "length": 4, "sha256": "9abd29c79ab4c20c7c90cd91fef679c280ec96ae189933b86303291c03c00a03"},
        {"opcode": 36, "command": "erase", "length": 4, "sha256": "613693bcd5eb14df06488fe4146f5c4be954a87a0075664f6580a8a4fb326835"},
        {"opcode": 37, "command": "position", "length": 4, "sha256": "6617679f879f880082100f44ab694ee01e733b756ca028882c3d994f9044199a"},
        {"opcode": 38, "command": "position.v", "length": 4, "sha256": "c8c78245d64b27509d2f052addb6c237ebc095a6d86d438d7d4ef2127b47f150"},
        {"opcode": 39, "command": "get.pos", "length": 4, "sha256": "eabc8f06d30e2e921db17e9a259bfa31f9aaa43aa516c5af2386c84a59f2be67"},
        {"opcode": 40, "command": "reposition", "length": 4, "sha256": "fb6344c58803a97e31cc67ea899eb40dfe286b07c66da0891739ceb763763d8d"},
        {"opcode": 58, "command": "stop.update", "length": 4, "sha256": "57b44052a24de11c7568c340c4faaec1f314e43cc3a0cbffa44d244a1010e4ab"},
        {"opcode": 59, "command": "start.update", "length": 4, "sha256": "80f8bb40a2dcff664bcc7abaf10032aa83c081cc913503ab52e172b271411b27"},
        {"opcode": 67, "command": "ignore.objs", "length": 4, "sha256": "122fb2709159bf1864989e531dc2374bb9c4bb8623b7b4ee56716f10421f0d60"},
        {"opcode": 68, "command": "observe.objs", "length": 4, "sha256": "5722a2d133e3b448ff8d55dab3e024599ef78a03f6ec1c26cdea3cb97b425d7c"},
        {"opcode": 70, "command": "stop.cycling", "length": 4, "sha256": "93001a4b9ed10c2c0bc74d04ef2a0728f0d4976eaace66f9bff022d4b73a10d8"},
        {"opcode": 71, "command": "start.cycling", "length": 4, "sha256": "e99d3a3be6e4290b4f19a0c60463e9e4120c2960758206f93713173ac6799e39"},
        {"opcode": 88, "command": "ignore.blocks", "length": 4, "sha256": "c479d8d8b072e59fa3b019e466c99b911d61b5a205d773790554b1f02bb486f9"},
        {"opcode": 89, "command": "observe.blocks", "length": 4, "sha256": "a7a0328114675c9ca462b0a18c15fa6574847a8c5999d24ce0d17737e200c8f3"},
        {"opcode": 131, "command": "program.control", "length": 4, "sha256": "3400f29a0d3a3deccf002707d08e624e20df006de8e81a4e608f317594b19503"},
        {"opcode": 132, "command": "player.control", "length": 4, "sha256": "583afb0fa0c0af81993282cee75048bec9d60584f5c38fc2dc76106dac1cb712"},
    ],
    "code": [
        {"offset": 0x0A70, "length": 5, "sha256": "e34b8fb135c4c1df3837b4ba34b4b54c5d23ceb36369b113a94bc56e231a11be", "meaning": "draw sets actor drawn0001h"},
        {"offset": 0x0B08, "length": 5, "sha256": "671367cab59bc776f216033752bebd966f829e55bcf85ed252dde4cdf293328a", "meaning": "erase clears actor drawn0001h"},
        {"offset": 0x0521, "length": 5, "sha256": "df6c02fb333224384c8813a15102f22a3fe58e788a961838055773fd0ee19f07", "meaning": "animate.obj tests animated0040h"},
        {"offset": 0x0528, "length": 5, "sha256": "915294fc22ae7e181d3029fcc79f1ae677428bb731b782d59101a04f742985af", "meaning": "animate.obj initializes animated+updating+cycling0070h"},
        {"offset": 0x0555, "length": 5, "sha256": "3a077b9f2f35b9625310a39dfb21b65d4a203b253cc94704666fea70b5565211", "meaning": "unanimate.all clears drawn0001h and animated0040h"},
        {"offset": 0x17B6, "length": 5, "sha256": "3a077b9f2f35b9625310a39dfb21b65d4a203b253cc94704666fea70b5565211", "meaning": "new.room clears actor drawn/animated BEFORE writing v0"},
        {"offset": 0x17ED, "length": 6, "sha256": "ebcb60cae66bfe7ddc6c0bb936e00eb2d28a359420aed0d9054713485caae5c3", "meaning": "new.room sets player control BEFORE v0; ownership alone is not initialized readiness"},
        {"offset": 0x1808, "length": 3, "sha256": "4496626a63846457a350f20ce757f93956fb542367d0701e27c28699df35b7af", "meaning": "new.room writes v0 at DS+9 before loading new logic"},
        {"offset": 0x1893, "length": 10, "sha256": "71fc9321e91fb54c6ddab9ed6ac6973a14cad990479b3abe30962d3203d9d124", "meaning": "new.room later sets flag5 for room initialization"},
        {"offset": 0x6F6D, "length": 6, "sha256": "6784c0e634b41c5f25ef1585ebab9b7fb3201044943d527b3fb6a87e7fab08b5", "meaning": "program.control writes word DS+139h=0"},
        {"offset": 0x6F7F, "length": 6, "sha256": "ebcb60cae66bfe7ddc6c0bb936e00eb2d28a359420aed0d9054713485caae5c3", "meaning": "player.control writes word DS+139h=1"},
        {"offset": 0x6A10, "length": 5, "sha256": "1f58a2d0d26e2181ae6660a77b45bc1be51f8808c5d18c0d058df6ea63423ed8", "meaning": "actor index times word at CS:6AB9"},
        {"offset": 0x6AB9, "length": 2, "sha256": "206014a4266c2082b9433011fb2991059f972d570a8b3c976e5b2b8dfcfbfc8d", "meaning": "actor stride43"},
        {"offset": 0x6A17, "length": 3, "sha256": "51c91fd2d490ffca00a6b0107e11ad84da3b9da51cbc3865f2a28d8dadc4b308", "meaning": "load actor table offset from DS:0963"},
        {"offset": 0x6A85, "length": 5, "sha256": "4d981506b8995b9231edb38e3442ff6ebe7a353ec8f8569c4a6ab7d4cd22fcbf", "meaning": "test actor flags+25h bit0010h"},
        {"offset": 0x6A8F, "length": 5, "sha256": "3825b50d8eb6d0402cc75a28d836af822c67951c772db1ea2dc47261d4453f96", "meaning": "stop.update clears0010h"},
        {"offset": 0x6AAD, "length": 5, "sha256": "203fd02f08c77145f342b58633ec1d808c73589ad295aeb9c8bd610322dad9fe", "meaning": "start.update sets0010h"},
        {"offset": 0x47BC, "length": 5, "sha256": "b62b4845c9c33991462ce3eab7e0aeb2b13dabd016430f595b4df711581bd088", "meaning": "ignore.objs sets0200h"},
        {"offset": 0x47E4, "length": 5, "sha256": "f004fc1df7b36116838667b37e834baf4b40b721417e75df492b19f5ee2f9b2e", "meaning": "observe.objs clears0200h"},
        {"offset": 0x6BEA, "length": 5, "sha256": "5b0f3da32ba9effd07bedb6743d6f9406185e247279949e827ff3669459c7d71", "meaning": "stop.cycling clears0020h"},
        {"offset": 0x6C0F, "length": 5, "sha256": "0aa1db4df1615f8bd2fc327f8f3f1c9cfac39ccba2b0f1ed24a0a683230a91dc", "meaning": "start.cycling sets0020h"},
        {"offset": 0x7AEF, "length": 5, "sha256": "e30ad325320d6818b51873ae8ee9f7af07d6c7617982b4a877fcb3920fcb6f89", "meaning": "ignore.blocks sets0002h"},
        {"offset": 0x7B14, "length": 5, "sha256": "29c7ae7ca5743a641e4ce5da10d4c907acd7b366d6007a1e9ad9ef3758846ba9", "meaning": "observe.blocks clears0002h"},
    ],
}


def decode_actor(raw: bytes | bytearray | memoryview) -> dict[str, Any]:
    """Decode one already-copied native43-byte actor; never reads the emulator.

    The caller must qualify this executable layout and its actor-table binding.
    cycle_mode has no inferred mode enumeration. raw_param39 is a union byte:
    end.of.loop/reverse.loop use it as their completion flag, whereas move.obj
    uses it for target x (and puts its completion flag at+42). It must not be
    interpreted without the active operation. An actor being marked updating
    or cycling does not alone prove its current scene branch advances it.
    """
    raw = bytes(raw)
    if len(raw) != ACTOR_STRIDE:
        raise ValueError(f"Expected exactly {ACTOR_STRIDE} bytes of original actor state")
    def word(offset: int) -> int:
        return int.from_bytes(raw[offset:offset + 2], "little")
    flags = word(ACTOR_FLAGS_OFFSET)
    return dict(x=word(3), y=word(5), view=raw[7], loop=raw[10], cel=raw[14],
                width=word(26), step=raw[30], direction=raw[33],
                cycle_mode=raw[35], raw_param39=raw[39], flags_word=flags,
                **{name: bool(flags & mask) for name, mask in ACTOR_FLAG_MASKS.items()})


def verify_native_actor_layout(ram: bytes | bytearray | memoryview, *, cs_base: int,
                               ds_base: int) -> dict[str, Any]:
    """Check original handler witnesses in a passive conventional-RAM snapshot.

    This checks the represented executable layout, not whether every actor or
    pointer is currently meaningful. A mismatch must remain unqualified.
    This sanitized import retains lengths/hashes and never emits target bytes.
    """
    evidence = ACTOR_LAYOUT_EVIDENCE
    checks = []
    def check(address: int, row: dict[str, Any], meaning: str) -> None:
        length = row["length"]
        accessible = 0 <= address and address + length <= min(len(ram), 0xA0000)
        observed_sha256 = sha256(bytes(ram[address:address + length])).hexdigest() if accessible else None
        checks.append(dict(address=address, length=length, expected_sha256=row["sha256"],
                           observed_sha256=observed_sha256, meaning=meaning,
                           match=accessible and observed_sha256 == row["sha256"]))
    for row in evidence["dispatch"]:
        check(ds_base + evidence["dispatch_offset"] + evidence["dispatch_stride"] * row["opcode"],
              row, f"opcode {row['opcode']}: {row['command']}")
    for row in evidence["code"]:
        check(cs_base + row["offset"], row, row["meaning"])
    return dict(complete=all(row["match"] for row in checks), checks=checks,
                actor_stride=ACTOR_STRIDE, actor_flags_offset=ACTOR_FLAGS_OFFSET,
                masks=ACTOR_FLAG_MASKS.copy(), source_capture_sha256=evidence["capture_sha256"])


@lru_cache(maxsize=4)
def _decoder(path: str):
    spec = importlib.util.spec_from_file_location("kq1_offline_picture_decoder", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load picture decoder: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Planner:
    """Complete base-PIC decoding plus bounded unit-step BFS; no live-state claim."""

    def __init__(self, game_dir: str | Path = DEFAULT_GAME, *, decoder_path: str | Path = DEFAULT_DECODER):
        self.game_dir = Path(game_dir).resolve()
        self.decoder_path = Path(decoder_path).resolve()
        self.decoder = _decoder(str(self.decoder_path))
        self._pictures: dict[int, tuple[bytes, str]] = {}

    def picture(self, room: int) -> tuple[bytes, str]:
        if room not in self._pictures:
            resource = self.decoder.extract_v2_resource(self.game_dir / "PICDIR", self.game_dir, room)
            decoded = self.decoder.decode_picture(resource["payload"])
            if not decoded.get("complete") or not decoded.get("priority_complete"):
                raise ValueError("Picture decoder did not qualify a complete priority plane")
            plane = decoded["priority"]
            if (decoded["width"], decoded["height"], len(plane)) != (WIDTH, HEIGHT, WIDTH * HEIGHT):
                raise ValueError("Unexpected original picture dimensions")
            self._pictures[room] = (plane, resource["sha256"])
        return self._pictures[room]

    def plan_step(self, step_id: int, start: tuple[int, int], *, width: int = 6, diagonals: bool = True,
                  forbidden_rects: tuple = ()) -> dict[str, Any]:
        request = PLAN_REQUESTS[step_id]
        return self.plan(request["room"], start, request["goal"], width=width, diagonals=diagonals,
                         y_min=request["y_min"], allow_priority_one=request["allow_priority_one"],
                         forbidden_rects=forbidden_rects)

    def plan(self, room: int, start: tuple[int, int], goal: tuple[int, int], *, width: int = 6,
             y_min: int | None = None, allow_priority_one: bool | None = None, diagonals: bool = True,
             forbidden_rects: tuple = (), reject_all_water: bool = True, max_nodes: int = 26880) -> dict[str, Any]:
        """Plan a destination-baseline path. Rectangles are inclusive ego-anchor guards.

        Priority0/2 are blocked,1 is policy dependent, and a wholly priority3
        baseline is rejected by default. Mixed water is not declared universally
        safe. Dynamic actors, add.to.pic, block rectangles and logic-driven hazards
        remain unknown unless the caller supplies explicit forbidden rectangles.
        """
        start, goal = tuple(start), tuple(goal)
        if width < 1 or width > WIDTH or max_nodes < 1 or max_nodes > WIDTH * HEIGHT:
            raise ValueError("Invalid footprint or work bound")
        if y_min is None or allow_priority_one is None:
            if room not in _DEFAULT_POLICIES:
                raise ValueError("Supply explicit horizon and priority1 policy for this room")
            floor, blocks = _DEFAULT_POLICIES[room]
            y_min = floor if y_min is None else y_min
            allow_priority_one = blocks if allow_priority_one is None else allow_priority_one
        plane, digest = self.picture(room)
        blocked = {0, 2} if allow_priority_one else {0, 1, 2}

        @lru_cache(maxsize=26880)
        def admissible(point: tuple[int, int]) -> bool:
            x, y = point
            if not (0 <= x <= WIDTH - width and y_min <= y < HEIGHT):
                return False
            if any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in forbidden_rects):
                return False
            baseline = plane[y * WIDTH + x:y * WIDTH + x + width]
            return not any(pixel in blocked for pixel in baseline) and not (reject_all_water and all(p == 3 for p in baseline))

        result = dict(room=room, start=list(start), goal=list(goal), width=width, y_min=y_min,
                      allow_priority_one=allow_priority_one, diagonals=diagonals,
                      reject_all_water=reject_all_water, picture_sha256=digest,
                      decoder_sha256=sha256(self.decoder_path.read_bytes()).hexdigest(),
                      qualification="base-PIC destination-baseline proposal; original engine is authority",
                      unresolved=["dynamic actors", "add.to.pic overlays", "live block rectangles", "room-logic hazards", "input/stop phase"],
                      stock_emulator_validated=False)
        if not admissible(start) or not admissible(goal):
            return {**result, "status": "inadmissible_start" if not admissible(start) else "inadmissible_goal", "path": [], "waypoints": []}
        queue = deque([start]); parent = {start: None}
        directions = _DIRECTIONS if diagonals else _DIRECTIONS[:4]
        while queue and goal not in parent:
            point = queue.popleft()
            for dx, dy, _ in directions:
                nxt = (point[0] + dx, point[1] + dy)
                if nxt not in parent and admissible(nxt):
                    if len(parent) >= max_nodes:
                        return {**result, "status": "budget_exhausted", "visited": len(parent), "path": [], "waypoints": []}
                    parent[nxt] = point
                    queue.append(nxt)
        if goal not in parent:
            return {**result, "status": "no_path_in_model", "visited": len(parent), "path": [], "waypoints": []}
        path = []; point = goal
        while point is not None:
            path.append(point); point = parent[point]
        path.reverse()
        waypoints = []; segments = []
        for index, point in enumerate(path[1:], 1):
            direction = (point[0] - path[index - 1][0], point[1] - path[index - 1][1])
            if index == len(path) - 1 or direction != (path[index + 1][0] - point[0], path[index + 1][1] - point[1]):
                origin = path[0] if not waypoints else waypoints[-1]
                waypoints.append(point)
                key = next(key for dx, dy, key in _DIRECTIONS if (dx, dy) == direction)
                segments.append(dict(key=key, target=list(point), unit_steps=max(abs(point[0] - origin[0]), abs(point[1] - origin[1]))))
        return {**result, "status": "found", "visited": len(parent), "steps": len(path) - 1,
                "path": [list(p) for p in path], "waypoints": [list(p) for p in waypoints], "segments": segments}


def load_candidate(path: str | Path = CANDIDATE_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


_MISSING = object()


def value(state: dict[str, Any], field: str) -> Any:
    """Adapt either prior evidence dictionaries or a compact live reader schema."""
    if field.startswith("var."):
        number = int(field.split(".")[1])
        variables = state.get("variables", state.get("vars", state.get("v", state.get("selected_variables", {}))))
        if isinstance(variables, (list, tuple, bytes, bytearray)):
            return variables[number] if number < len(variables) else _MISSING
        return variables.get(number, variables.get(str(number), _MISSING))
    if field.startswith("flag."):
        number = int(field.split(".")[1]); flags = state.get("flags_on", state.get("flags", _MISSING))
        if flags is _MISSING: return _MISSING
        if isinstance(flags, dict): return flags.get(number, flags.get(str(number), _MISSING))
        if isinstance(flags, (bytes, bytearray)) and len(flags) == 32:
            return bool(flags[number // 8] & (0x80 >> (number % 8)))
        return number in flags
    if field.startswith("actor."):
        _, number, name = field.split(".", 2); actors = state.get("actors", {})
        actor = actors[int(number)] if isinstance(actors, list) and int(number) < len(actors) else actors.get(int(number), actors.get(number, {})) if isinstance(actors, dict) else {}
        return actor.get(name, _MISSING)
    if field == "items":
        items = state.get("carried_items", state.get("items", _MISSING))
        return sorted(items) if items is not _MISSING else _MISSING
    if field in ("x", "y", "direction"):
        return state.get("ego", {}).get(field, state.get(field, _MISSING))
    aliases = {"view": "ego_view", "width": "ego_width", "window": "window_depth",
               "control_direction": "control", "game_speed": "speed"}
    if field in state: return state[field]
    if field in aliases and aliases[field] in state: return state[aliases[field]]
    numbers = {"room": 0, "previous_room": 1, "score": 3, "control_direction": 6, "game_speed": 10}
    return value(state, f"var.{numbers[field]}") if field in numbers else _MISSING


def condition(field: str, expected: Any, op: str = "eq") -> dict[str, Any]:
    return dict(field=field, op=op, value=expected)


def _test(check: dict[str, Any], state: dict[str, Any]) -> bool | None:
    if "all" in check or "any" in check:
        key = "all" if "all" in check else "any"
        results = [_test(item, state) for item in check[key]]
        if key == "all": return False if False in results else None if None in results else True
        return True if True in results else None if None in results else False
    if "not" in check:
        result = _test(check["not"], state); return None if result is None else not result
    actual = value(state, check["field"])
    if actual is _MISSING: return None
    expected = check["value"]; op = check.get("op", "eq")
    if op == "eq": return actual == expected
    if op == "in": return actual in expected
    if op == "contains": return expected in actual
    if op == "absent": return expected not in actual
    if op == "lt": return actual < expected
    if op == "le": return actual <= expected
    if op == "gt": return actual > expected
    if op == "ge": return actual >= expected
    if op == "between": return expected[0] <= actual <= expected[1]
    raise ValueError(f"Unsupported check operator: {op}")


def evaluate(checks: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    results = [dict(check=check, result=_test(check, state)) for check in checks]
    return dict(complete=all(row["result"] is True for row in results),
                pending=[row["check"] for row in results if row["result"] is False],
                unknown=[row["check"] for row in results if row["result"] is None], results=results)


def rect(x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
    return {"all": [condition("x", [x1, x2], "between"), condition("y", [y1, y2], "between")]}


def f(number: int, expected: bool = True) -> dict[str, Any]: return condition(f"flag.{number}", expected)
def v(number: int, expected: Any, op: str = "eq") -> dict[str, Any]: return condition(f"var.{number}", expected, op)
def item(number: int, carried: bool = True) -> dict[str, Any]: return condition("items", number, "contains" if carried else "absent")


CONTRACTS: dict[int, dict[str, Any]] = {}


def contract_for(step_id: int) -> dict[str, Any]:
    return CONTRACTS[step_id]


def check_step(step_id: int, state: dict[str, Any], phase: str = "post") -> dict[str, Any]:
    if phase not in ("pre", "post"): raise ValueError("Phase must be pre or post")
    return evaluate(contract_for(step_id)[phase], state)


def _add(step: int, intent: str, pre: list, post: list, *, source: list[str], output: list = (), notes: str = "") -> None:
    CONTRACTS[step] = dict(intent=intent, pre=[f(63, False), condition("window", 0), *pre],
        post=[f(63, False), condition("window", 0), *post], source=source, output=list(output), notes=notes,
        qualification="source-derived predicate with prior receiving-runtime evidence; newly authored stock run unverified")


def pulse_contract(step_id: int) -> dict[str, Any]:
    return PULSES[step_id]


def thief_decision(state: dict[str, Any]) -> dict[str, Any]:
    """Inspect the original branch; this never chooses or dispatches input edges."""
    if value(state, "room") != 68: return dict(status="wrong_room", action="inspect")
    safety = evaluate([f(63, False), f(102), item(21), v(74, 1), condition("score", 26)], state)
    if not safety["complete"]:
        return dict(status="treasure_or_state_unqualified", action="stop_and_preserve", checks=safety)
    no_thief = _test({"any": [f(23, False), {"all": [f(24, False), v(70, 0)]}]}, state)
    if no_thief is True:
        return dict(status="no_thief_at_settled_observation", action="continue_candidate", proof="!f23 OR (!f24 AND v70==0)")
    if no_thief is None: return dict(status="unknown", action="inspect", missing="flags23/24 and v70")
    return dict(status="thief_pending_or_active", action="consider_ordinary_retreat",
        retreat=[dict(kind="walk_to", x=94, y=160), dict(kind="walk_until_room", key="down", room=67),
                 dict(kind="walk_to", x=120, y=41), dict(kind="walk_until_room", key="up", room=68)],
        source="L68 init previous_room67 and random v62<150; prospective retreat requires native qualification",
        warning="Do not copy the historical retry count or wait near125,131. v70==0 alone does not prove no prior spawn.")


def window_action(step_id: int | str, state: dict[str, Any], observed_message: tuple[int, int] | None = None) -> dict[str, Any]:
    """Pure callback advice. Caller records screenshot/edges; no auto-dismiss loop."""
    window = value(state, "window")
    if window is _MISSING: return dict(action="inspect", reason="window depth unknown")
    if not window: return dict(action="none")
    if value(state, "flag.63") is True: return dict(action="retain", reason="failure; preserve evidence")
    if step_id == "finish":
        return dict(action="retain", reason="endpoint candidate; verify L53 message25 and first matching frame",
                    state_checks=evaluate(FINISH_CHECKS, state), message_verified=observed_message == (53, 25))
    expected = [tuple(x) for x in CONTRACTS.get(step_id, {}).get("output", [])]
    if observed_message is not None and expected and observed_message not in expected:
        return dict(action="inspect", reason="output is not a listed success/continuation message", expected=expected)
    return dict(action="capture_then_dismiss_once", expected=expected,
                message_verified=observed_message in expected if observed_message is not None else False,
                reason="Only an observed open window may consume Enter; recheck after it closes before typing or claiming effects")


PULSES = {
    79: dict(intent="step onto hole trigger", room=48, start=[75,129], key="up", target=[75,128],
             mode="one ordinary direction activation; original descent takes over", allow_water=True,
             continuation_step=80, uncertain="Fresh input phase and transition latency"),
    102: dict(intent="enter king proximity region", room=77, start=[104,109], key="down", target=[104,112],
              mode="short movement into y110..112 with observed message18 handling; then neutral", allow_water=False,
              uncertain="Old250ms is not a duration; actual modal and stopping edge must be recorded"),
    116: dict(intent="leave through tiny opening", room=78, start=[2,81], key="left", target=[1,81],
              mode="ordinary left activation; accept room36 transition rather than require old-room stationary target",
              required_view=60, required_width=4, continuation_step=117, uncertain="Original transition latency"),
    214: dict(intent="descend off lowered rope and wait for swimming", room=49, start=[81,114], key="down", target=[81,164],
              mode="preserve x79..83 until y>115, then original fall animation; wait VIEW93 and v94 in1,2",
              allow_water=True, do_not_require_flag98_clear=True,
              uncertain="Old6500ms is not a duration; scripted fall should not receive continued blind steering"),
}

FINISH_CHECKS = [condition("room",53), condition("score",63), f(63,False), v(74,3),
                 v(30,245), v(70,0), v(71,0), item(2), item(19), item(21), condition("window",0,"gt")]

# Conditions below are deliberately expressed in the game's variables/flags and
# source guards. Missing observations return unknown, never implicit success.
_add(8,"move rock from its safe side",
     [condition("room",3),f(62,False),f(20,False),rect(115,114,133,133)],
     [condition("room",3),condition("score",2),f(20)],source=["L3@D0,EE,102..104"],output=[(3,13)],
     notes="Southern rectangle118..133,134..148 is lethal; score commits after the print. f62 is the separate animation completion.")
_add(9,"wait for moved rock",
     [condition("room",3),condition("score",2)], [condition("room",3),condition("score",2),f(62)],
     source=["L3 move.obj actor1→118,145 completionf62"],notes="Do not copy the historical2000ms wait.")
_add(10,"take exposed knife",[condition("room",3),f(62),f(69,False),rect(112,108,134,133)],
     [condition("score",7),item(1),f(67),f(69)],source=["L3@1AE..1BC"],output=[(3,8)])
_add(20,"take clover",[condition("room",24),f(86,False),v(62,25,"lt")],
     [condition("score",9),item(8),f(86),f(87)],source=["L24@82,AA..BA"],output=[(24,4)],
     notes="v62 is original ego-to-clover distance, not a substituted geometry metric.")
_add(41,"take closed pouch",[condition("room",6),f(71,False),f(72,False),rect(0,103,35,146)],
     [condition("score",12),item(16),f(71),f(72)],source=["L6@188..1A1"],output=[(6,3)],
     notes="LOOK IN STUMP would add an extra point and is not a prerequisite.")
_add(52,"start gnome name challenge",[condition("room",40),f(22,False),v(62,50,"lt")],
     [condition("score",12),f(22),v(84,0),f(2,False),f(4,False)],
     source=["L40@B9 distance into v62; 10A..115 first greeting; original parser-cycle flags2/4"],output=[(40,5)],
     notes="f22 is set at111 BEFORE print5 at113. An instantaneous window0 with f22 set is not completed output. Require original introduction observation/dismissal and settled parser cycle before guessing. The native failed control at9.629737250s had f22/f2/f4 set and window0; early GET KEY never became a guess. Prior HI receipt likewise only witnessed the early effect, not readiness. Original distance must be current.")
_add(53,"first recognized wrong guess",[condition("room",40),f(22),v(84,0)],
     [condition("score",12),f(22),v(84,1)],source=["L40@1CF..1E0"],output=[(40,19)],
     notes="GET KEY is our chosen valid wrong guess, not a recovered exact video string.")
_add(54,"second recognized wrong guess",[condition("room",40),f(22),v(84,1)],
     [condition("score",12),f(22),v(84,2)],source=["L40@1EE..201"],output=[(40,20),(40,21)])
_add(55,"third wrong guess produces fallback key",[condition("room",40),f(22),v(84,2)],
     [condition("score",12),v(84,3),v(83,2),f(21),f(22,False),f(23,False)],source=["L40@20F fallback branch"],
     output=[(40,22)],
     notes="No score for losing. Fourth GET KEY is the pickup.")
_add(56,"take fallback key",[condition("room",40),f(21),v(71,20,"le")],
     [condition("score",15),item(5),f(84),f(21,False),v(85,1)],source=["L40@2C0..2DB"],output=[(40,12)])
_add(71,"take mushroom",[condition("room",47),rect(74,70,94,90)],
     [condition("score",16),item(24),f(121),f(123)],source=["L47@162,183..198"],output=[(47,9)])
_add(79,"enter front hole",[condition("room",48),condition("x",75),condition("y",129)],
     [{"any":[{"all":[condition("room",48),f(0)]},condition("room",73)]}],source=["L48@E3..114"],
     notes="Intentional water/control-plane3 trigger. See pulse_contract(79); no parser ENTER HOLE command.")
_add(80,"finish cave landing and recovery",[],
     [condition("room",73),condition("previous_room",48),condition("x",90),condition("y",139),
      condition("view",0),condition("width",6),f(98,False),f(5,False),condition("actor.0.drawn",True),
      condition("player_control",True),condition("direction",0),condition("control_direction",0)],
     source=["L73@16..2A initial fall; 88..CD landing/recovery; original90,139 receiving pose"],output=[(73,4)],
     notes="Must first observe initialized fall/recovery (room73,previous48,x90,f98,VIEW105/103/104), then these final predicates. Use separate transition_evidence or caller history; no hidden history field is required here. v0 changes before room init, so room73 plus old VIEW0/!f98/neutral is false readiness. Native draw bit1 and !f5 qualify initialization; OUCH precedes recovery.")
_add(81,"open pouch into diamonds",[condition("room",73),item(16),f(72),f(106,False)],
     [condition("score",19),item(15),item(16,False),f(106),f(72,False)],source=["L0@E33..E57"],output=[(0,79)])
_add(85,"pretype GIVE BAG while traversing tunnel",[condition("room",74),item(15)],
     [condition("input_line","give bag")],source=["Video parser line; prior request pretype"],
     notes="No submission or game effect yet. input_line observation may be unavailable; retain unknown and driver input receipt.")
_add(90,"give diamonds to rat",[condition("room",75),item(15),f(106),f(21,False),v(70,[16,34],"between")],
     [condition("room",75),condition("score",13),item(15,False),f(106,False),f(107)],
     source=["L75@1AF..201"],output=[(75,21)],
     notes="v70 must be strictly greater15 and less35. Rat-caught flag21 must not already own the failure branch.")
_add(91,"wait until rat has left",[condition("room",75),item(15,False)],
     [condition("room",75),condition("score",13),f(138)],source=["L75@33C..348"],output=[(75,25)])
_add(94,"open rat-room door",[condition("room",75),f(138),v(71,25,"lt")],
     [condition("score",13),{"any":[condition("room",76),condition("actor.2.cel",0,"gt")]}],
     source=["L75@371..397"],output=[(75,7)],notes="Door animation completionf23 causes room76; follow with step95.")
_add(95,"enter clover-safe leprechaun passage",[],
     [condition("room",76),condition("previous_room",75),condition("x",113),condition("y",146),
      condition("score",13),item(8),f(87),condition("view",0),f(5,False),condition("actor.0.drawn",True),
      condition("player_control",True),condition("direction",0),condition("control_direction",0)],
     source=["L75@391..397; L76@C..13 entry pose,74..9B draw/show/clover print"],output=[(76,3)],
     notes="The new-room initialization flag5 remains set during this entry print. Source-specific113,146 pose plus drawn and !f5 excludes a new v0 still carrying old room75 actor state.")
_add(102,"cross king proximity threshold",[condition("room",77),f(87)],
     [condition("room",77),condition("x",104),condition("y",[110,112],"between")],
     source=["L77@133..151"],output=[(77,18)],notes="Use pulse_contract(102), then ordinary neutral; not a copied250ms pulse.")
_add(103,"settle after king proximity message",[condition("room",77)],
     [condition("room",77),f(25),condition("direction",0),condition("control_direction",0)],
     source=["L77@133..151; prior request12 neutral result"],output=[(77,18)])
_add(106,"take shield protected by clover",[condition("room",77),rect(121,118,144,138),f(188,False),f(87)],
     [condition("score",21),item(21),f(102),f(188),v(74,1)],source=["L77@394..3E2"],output=[(77,24)],
     notes="This recreates the clover branch, not the fiddle branch.")
_add(114,"eat mushroom at small exit",[condition("room",78),item(24),f(123),f(79,False),v(94,0)],
     [condition("score",23),condition("view",60),condition("width",4),item(24,False),f(120),f(124),v(82,1,"gt")],
     source=["L0@824..892; L78@67..95"],output=[(0,11)],
     notes="Global guard also excludes flying/climbing states. Tiny form has a finite local-cycle timer; do not wait arbitrarily.")
_add(116,"pass tiny cave exit",[condition("room",78),condition("view",60),condition("width",4),f(120),condition("y",81)],
     [{"any":[{"all":[condition("room",78),condition("x",1)]},condition("room",36)]}],
     source=["L78@F1..FD; prior tiny exit receipt"],notes="Transition endpoint can occur immediately; allow new-room completion.")
_add(117,"finish original regrowth",[],
     [condition("room",36),condition("previous_room",78),condition("x",88),condition("y",131),
      condition("score",24),condition("view",0),condition("width",6),f(120,False),f(20,False),v(82,0),
      f(5,False),condition("actor.0.drawn",True),condition("player_control",True),
      condition("direction",0),condition("control_direction",0)],
     source=["L36@25..5C"],output=[(36,13)],
     notes="Entry from78 sets v82=0,adds1,places tiny ego110,131 and moves toward88,131. Completion sets VIEW0,prints13,THEN clearsf120/f20. Retain this phase ordering; old-room tiny pose cannot establish recovery.")
_add(129,"unlock tree door with gold key",[condition("room",19),f(84),item(5),v(66,0),rect(90,93,125,114)],
     [condition("room",19),condition("score",26),v(66,1),f(85)],source=["L19@12F..1A2"],output=[(19,6)],
     notes="Unlock only; the separate OPEN DOOR starts opening.")
_add(130,"start tree-door opening",[condition("room",19),v(66,1)],
     [condition("room",19),condition("score",26),v(66,2)],source=["L19@20A..224"],
     notes="v66=2 is an animation-start state, not passable-door proof.")
_add(131,"wait for tree door fully open",[condition("room",19),v(66,2)],
     [condition("room",19),condition("score",26),v(66,2),f(20,False),condition("actor.1.cel",3),
      condition("actor.1.updating",False),condition("actor.1.ignore_objects",True)],
     source=["L19@24E..25A; init open cel3 at4A"],
     notes="Actor flags need a qualified native reader or equivalent observed completion-history witness; missing fields stay unknown.")
_add(144,"qualify thief-free ascent",[condition("room",68)],
     [condition("room",68),condition("score",26),item(21),f(102),v(74,1),{"any":[f(23,False),{"all":[f(24,False),v(70,0)]}]}],
     source=["L68 initialization and spawn countdown; source support thief analysis"],
     notes="Use thief_decision. Native RNG history chooses branch; retry count cannot be copied.")
_add(157,"wait for giant's deterministic sleep",[condition("room",58),item(21),f(102)],
     [condition("room",58),condition("score",33),v(86,1),f(205)],source=["L58@426..450"],output=[(58,1),(58,29)],
     notes="749 eligible local invocations, not78000ms; sleep output resumes before pickup.")
_add(161,"take chest from sleeping giant",[condition("room",58),v(86,1),f(104,False)],
     [condition("room",58),condition("score",41),item(2),f(104),f(169),v(74,2),v(86,3)],
     source=["L58@20F..254 and post-print effects"],output=[(58,10)],
     notes="Original success guard is freshly computed ego/giant distance v70<=30. That sample occurs inside GET CHEST at234, so a prior RAM v70 is not a reliable precondition. Use the qualified approach40,153, submit and verify committed effects; preserve a distance refusal.")
CONTRACTS[161]["source_guard"] = [v(70,30,"le")]
CONTRACTS[161]["source_guard_freshness"] = "Only after L58@234 distance executes in this invocation"
_add(208,"cut bucket rope",[condition("room",12),f(67),item(1),rect(10,109,71,153),f(176,False),f(177,False)],
     [condition("room",12),condition("score",43),item(11),f(81),f(176)],source=["L12@64F..6DA"],output=[(12,3)])
_add(209,"lower cut rope",[condition("room",12),f(176),f(179,False),rect(60,108,77,129)],
     [condition("room",12),condition("score",43),f(179)],source=["L12@749..77E"],output=[(12,25)])
_add(210,"wait until rope and crank stop",[condition("room",12),f(179)],
     [condition("room",12),condition("score",43),f(179),f(24,False),
      condition("actor.3.view",17),condition("actor.3.loop",0),condition("actor.3.cel",5),
      condition("actor.3.cycling",False),condition("actor.1.updating",False)],
     source=["L12@779 end.of.loop(3,f24); L12@785..78F; VIEW17 loop0 has six cels"],
     notes="The live lowering animation ends at cel5. Cel2 at L12@95 is a separate already-lowered room-entry pose. Missing actor state is unknown.")
_add(211,"climb lowered rope",[condition("room",12),f(179),f(75,False),f(79,False),rect(10,100,75,150)],
     [f(180),{"any":[{"all":[condition("room",12),condition("view",143)]},{"all":[condition("room",49),condition("view",74)]}]}],
     source=["L12 lowered-rope climbing branch; L49 entry"],
     notes="Keep x35..44 in12 and x79..83 in49. New view/width is intentional.")
_add(214,"finish well fall into swimming",[condition("room",49),condition("x",[79,83],"between"),f(179)],
     [condition("room",49),condition("score",44),condition("view",93),v(94,[1,2],"in"),condition("direction",0),condition("control_direction",0)],
     source=["L49 y>115 fall to164, f22 completion; L101 swimming"],
     notes="f98 remains set in the receiving evidence. Do not require it clear.")
_add(216,"dive and fill bucket automatically",[condition("room",49),v(94,[1,2],"in"),item(11),f(81)],
     [condition("room",52),condition("score",48),condition("view",73),item(26),f(88),f(91),f(164)],
     source=["L49@4DC..507; L52@42..58"],notes="Dive adds2; room52 autofill adds2. No FILL BUCKET command.")
_add(217,"pretype TOSS WATER during underwater traversal",[condition("room",52),item(26)],
     [condition("input_line","toss water")],source=["Video parser line and original request pretype"],
     notes="Original breath countdown continues while guest executes. No Enter before the dragon success guard.")
_add(222,"throw water from outside too-far rectangle",[condition("room",51),v(75,0),f(88),item(26),f(20,False),
      {"not":rect(105,96,145,166)}],
     [condition("room",51),condition("score",54),v(75,2),f(88,False),f(91,False),item(26,False)],
     source=["L51@3DF,432..473"],output=[(51,34)],
     notes="Water effect and score commit after success print. Shield does not protect against dragon capture.")
_add(223,"retain committed water success while retreat progresses",[condition("room",51)],
     [condition("room",51),condition("score",54),v(75,2),item(26,False),f(88,False)],
     source=["L51 water success and f21→f22→f23 retreat/boulder chain"],
     notes="This proves throw effects, not the final boulder opening. Later movement remains original-engine qualified.")
_add(226,"take mirror",[condition("room",51),rect(26,104,59,127),v(75,2),f(100,False),f(165,False)],
     [condition("room",51),condition("score",62),item(19),f(100),f(165),v(74,3)],
     source=["L51@32D..385"],output=[(51,24)],
     notes="Object and flags commit before print; treasure count and score after it. Require all.")
_add(274,"open castle doors",[condition("room",2),rect(105,120,121,128),f(75,False),f(125,False)],
     [condition("room",[2,55],"in"),condition("score",63),f(193)],source=["L2@212..261"],output=[(2,25)],
     notes="One point commits after print; animation and sound separately control entry.")
_add(275,"finish castle door animation and sound",[],
     [condition("room",55),condition("score",63),v(74,3),item(2),item(19),item(21),condition("view",0)],
     source=["L2@261 waits f24 and f28, then room55"],notes="Do not infer room55 from the door text.")


TRANSITION_PHASES = {
    80: dict(required=["initialized_fall"], phases={
        "initialized_fall": [condition("room",73),condition("previous_room",48),condition("x",90),
                             f(98),condition("view",[105,103,104],"in")],
        "landing_window": [condition("room",73),condition("view",103),f(98),condition("window",0,"gt")],
        "recovery_animation": [condition("room",73),condition("view",104),f(98)],
    }),
    95: dict(required=["initialized_entry_pose"], phases={
        "initialized_entry_pose": [condition("room",76),condition("previous_room",75),
                                   condition("x",113),condition("y",146),condition("actor.0.drawn",True)],
        "entry_window": [condition("room",76),condition("previous_room",75),f(5),f(87),condition("window",0,"gt")],
    }),
    117: dict(required=["initialized_tiny_exit"], phases={
        "initialized_tiny_exit": [condition("room",36),condition("previous_room",78),
                                  condition("view",60),condition("x",[88,110],"between"),condition("y",131),
                                  condition("score",24),v(82,0),f(120)],
        "regrowth_window": [condition("room",36),condition("view",0),f(120),condition("window",0,"gt")],
    }),
}


def transition_evidence(step_id: int, state: dict[str, Any], history: dict[str, Any] | None = None,
                        *, attempt_id: str | None = None) -> dict[str, Any]:
    """Return a new pure observation history and combined completion result.

    Pass the previous return value as history. No incoming object is mutated.
    The history is separate from check_step's instantaneous postconditions.
    A recorded window is not proof of its exact message ID; retain its image.
    Some initialization phases deliberately cannot be reconstructed after the
    fact from a final state. Missing historical observations stay missing.
    Reset history after every checkpoint load, rewind, or new attempt. Supplying
    a fresh attempt_id additionally prevents reuse across identified branches;
    decreasing native timestamps are rejected even without an attempt token.
    """
    definition = TRANSITION_PHASES[step_id]
    if history is not None and history.get("step_id") != step_id:
        raise ValueError("Transition history belongs to another step")
    if history is not None and history.get("attempt_id") != attempt_id:
        raise ValueError("Transition history belongs to another attempt; reset it after loading")
    timestamp = state.get("time_ns")
    prior_time = (history or {}).get("last_time_ns")
    if timestamp is not None and prior_time is not None and timestamp < prior_time:
        raise ValueError("Native time moved backward; reset transition history after loading")
    seen = dict((history or {}).get("seen", {}))
    observations = {}
    for name, checks in definition["phases"].items():
        result = evaluate(checks, state)
        observations[name] = result
        if result["complete"] and name not in seen:
            sampled = {}
            for field in ("room","previous_room","x","y","view"):
                observed = value(state,field)
                if observed is not _MISSING: sampled[field] = observed
            seen[name] = dict(time_ns=state.get("time_ns"), state=sampled)
    missing = [name for name in definition["required"] if name not in seen]
    final = check_step(step_id,state)
    return dict(step_id=step_id, attempt_id=attempt_id, last_time_ns=timestamp,
                seen=seen, missing_history=missing,
                phase_checks=observations, final_checks=final,
                complete=not missing and final["complete"],
                message_identity_verified=False)
