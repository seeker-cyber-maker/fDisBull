"""Build the partial game-level Civilization UIL scene and its evidence index.

The scene is a navigation/state projection, not a playable reconstruction of
the whole game. Screen identities come from Civ64's DOS scene records; each
screen boundary is resolved against the civd function atlas generated from the
pinned CIV_UNP.EXE. Rule slices stay in their existing contracts and are linked
from the provenance document instead of being re-guessed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

TITLE = 0
LOAD = 1
CUSTOMIZE = 2
BIRTH = 3
DIFFICULTY = 4
COMPETITION = 5
TRIBE = 6
LEADER_NAME = 7
INTRO = 8
WORLD = 9
CITY = 10
CITY_VIEW = 11
REPORTS = 12
PEDIA = 13
DIPLOMACY = 14
SPACESHIP = 15
HALL = 16
GAME_OVER = 17
NEWSPAPER = 18
PALACE = 19
AUDIENCE = 20

SCREEN_NAMES = {
    TITLE: "title",
    LOAD: "load",
    CUSTOMIZE: "customize",
    BIRTH: "birth",
    DIFFICULTY: "difficulty",
    COMPETITION: "competition",
    TRIBE: "tribe",
    LEADER_NAME: "leader-name",
    INTRO: "intro",
    WORLD: "world",
    CITY: "city",
    CITY_VIEW: "city-view",
    REPORTS: "reports",
    PEDIA: "pedia",
    DIPLOMACY: "diplomacy",
    SPACESHIP: "spaceship",
    HALL: "hall",
    GAME_OVER: "game-over",
    NEWSPAPER: "newspaper",
    PALACE: "palace",
    AUDIENCE: "audience",
}

PACKED_SHA256 = "22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a"
UNPACKED_SHA256 = "aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57"
CIVD_COMMIT = "d9214fcd36aa6003d28aae60c3974b665f752280"
CIV64_COMMIT = "4e46572d727544722d90c24dc2ce51a9c6d22f15"
OVERLAY_BASE = 0x23740

VARIABLES = {
    "$screen": {"type": "u8", "initial": TITLE},
    "$turn": {"type": "u16", "initial": 1},
    "$year": {"type": "i16", "initial": -4000},
    "$difficulty": {"type": "u8", "initial": 2},
    "$competition": {"type": "u8", "initial": 4},
    "$tribe": {"type": "u8", "initial": 0},
    "$human_civ": {"type": "u8", "initial": 0},
    "$treasury": {"type": "i32", "initial": 0},
    "$tax_rate": {"type": "u8", "initial": 0},
    "$science_rate": {"type": "u8", "initial": 0},
    "$luxury_rate": {"type": "u8", "initial": 10},
    "$selected_city": {"type": "u8", "initial": 0},
    "$selected_unit": {"type": "u16", "initial": 0},
    "$production": {"type": "i16", "initial": 0},
    "$chooser_open": {"type": "bool", "initial": False},
    "$unit_list_open": {"type": "bool", "initial": False},
    "$unit_count": {"type": "u8", "initial": 0},
    "$unit_cursor": {"type": "u8", "initial": 0},
    "$city_cursor": {"type": "u8", "initial": 0},
    "$auto_build": {"type": "bool", "initial": False},
    "$report": {"type": "u8", "initial": 0},
    "$view_x": {"type": "u8", "initial": 0},
    "$view_y": {"type": "u8", "initial": 0},
    "$earth_world": {"type": "bool", "initial": False},
    "$game_over": {"type": "bool", "initial": False},
}

STATE_EVIDENCE = {
    "$screen": "UIL scene selector; no direct DOS symbol.",
    "$turn": "Turn loop R:0238:0092; Civ64 SCENES-PLAY 7.17.",
    "$year": "DGROUP:B220 absolute year; Civ64 SCENES-PLAY 5.2.",
    "$difficulty": "Setup result recorded by Civ64 SCENES 9.1; the menu result binding is not modelled.",
    "$competition": "Setup result recorded by Civ64 SCENES 9.2; the menu result binding is not modelled.",
    "$tribe": "Setup result recorded by Civ64 SCENES 9.3; the menu result binding is not modelled.",
    "$human_civ": "DGROUP:D7F0 player civilization; Civ64 SCENES-PLAY 7.19.",
    "$treasury": "DGROUP:B1D6[civ]; Civ64 SCENES-PLAY 5.2.",
    "$tax_rate": "DGROUP:DF0E[civ]; Civ64 SCENES-PLAY 7.20.",
    "$science_rate": "DGROUP:B210[civ]; Civ64 SCENES-PLAY 7.20.",
    "$luxury_rate": "Derived as 10 - tax - science; Civ64 SCENES-PLAY 7.20.",
    "$selected_city": "UIL selector into the 128 city records at DGROUP:70EC; no direct DOS symbol.",
    "$selected_unit": "UIL selector into DGROUP:81D4 + civ*600h + unit*0Ch; Civ64 SCENES-PLAY 2.2.",
    "$production": "City record production field; civd CITYMGT.C and reference/struct_city.md.",
    "$chooser_open": "UIL context flag for key c / R:0ADE:0421; Civ64 SCENES-PLAY 7.12.",
    "$unit_list_open": "UIL context flag for key a / 0A99:7785; Civ64 SCENES-PLAY 7.1.",
    "$unit_count": "Declared unit-list length; not a committed DOS field.",
    "$unit_cursor": "Declared unit-list cursor; not a committed DOS field.",
    "$city_cursor": "The source stores the unit cursor at [0x70DC]; Civ64 SCENES-PLAY 7.1.",
    "$auto_build": "City-screen automatic-production display state; civd CITYMGT.C.",
    "$report": "UIL report selector; F1..F10 table at R:0403 3B7D..3BFF; Civ64 SCENES-PLAY 7.14.",
    "$view_x": "DGROUP:D4CC viewport x; Civ64 SCENES-PLAY 3.",
    "$view_y": "DGROUP:D75E viewport y; Civ64 SCENES-PLAY 3.",
    "$earth_world": "DGROUP:D76A EARTH branch; Civ64 SCENES 7.3.",
    "$game_over": "UIL end-state flag; Civ64 SCENES-PLAY 7.17.",
}

CIVD_SOURCES = [
    "GAME.C",
    "SAVE.C",
    "WORLDGEN.C",
    "NEWGAME.C",
    "NAMES.C",
    "MAP.C",
    "TURN.C",
    "CONTROL.C",
    "UNITS.C",
    "CITYMGT.C",
    "ECONOMY.C",
    "CITYVIEW.C",
    "ADVISORS.C",
    "REPORTS.C",
    "PEDIA.C",
    "AUDIENCE.C",
    "DIPLOMAC.C",
    "SPACESHP.C",
    "FAME.C",
    "REPLAY.C",
    "NEWS.C",
    "PALACE.C",
    "CITY.C",
    "DIALOG.C",
    "MENUS.C",
    "MESSAGE.C",
]


def _eq(var: str, value: int | bool) -> dict:
    return {"op": "eq", "left": {"var": var}, "right": value}


def _not(condition: dict) -> dict:
    return {"op": "not", "condition": condition}


def _and(*conditions: dict) -> dict:
    return {"op": "and", "conditions": list(conditions)}


def _screen(value: int) -> dict:
    return _eq("$screen", value)


def _object(
    ident: str,
    label: str,
    aliases: list[str],
    description: str,
    verb: str | None = None,
    program: str | None = None,
) -> dict:
    binding = [] if verb is None else [{"verb": verb, "program": program}]
    return {
        "id": ident,
        "label": label,
        "aliases": aliases,
        "description": description,
        "bindings": binding,
    }


def _screen_spec(
    ident: str,
    value: int,
    title: str,
    description: str,
    civ64: list[str],
    civd: list[str],
    anchors: list[tuple[str, str]],
    objects: list[dict],
    when: dict | None = None,
) -> dict:
    return {
        "id": ident,
        "screen": value,
        "title": title,
        "description": description,
        "civ64": civ64,
        "civd": civd,
        "anchors": anchors,
        "objects": objects,
        "when": when or _screen(value),
    }


SCREEN_SPECS = [
    _screen_spec(
        "title",
        TITLE,
        "Title menu",
        "DOS title menu over the logo; five entries. Civ64 SCENES.md 6; civd GAME.C _game_menu.",
        ["SCENES.md 4.4-6"],
        ["GAME.C"],
        [("R:01A8:0486", "title menu")],
        [
            _object(
                "title-new",
                "Start a New Game",
                ["new game", "start"],
                "Starts world generation, then the new-game setup.",
                "activate",
                "new-game",
            ),
            _object(
                "title-load",
                "Load a Saved Game",
                ["load", "saved game"],
                "Opens the drive/slot loader.",
                "open",
                "enter-load",
            ),
            _object(
                "title-customize",
                "Customize World",
                ["customize", "custom world"],
                "Opens the four world-parameter questions.",
                "open",
                "enter-customize",
            ),
            _object(
                "title-hall",
                "View Hall of Fame",
                ["hall", "hall of fame"],
                "Reads FAME.DTA and shows six entries.",
                "open",
                "toggle-hall",
            ),
        ],
    ),
    _screen_spec(
        "load",
        LOAD,
        "Load a saved game",
        "Drive prompt and ten fixed CIVIL0..9.SVE slots. Civ64 SCENES.md 7.2; civd SAVE.C _load_game.",
        ["SCENES.md 7.2"],
        ["SAVE.C"],
        [("O11:0000", "load screen")],
        [
            _object(
                "load-slot",
                "Load first slot",
                ["slot", "first slot", "load game"],
                "Declared slot 0; the save-file parser is outside this scene.",
                "open",
                "load-world",
            ),
            _object(
                "load-cancel",
                "Cancel load",
                ["cancel", "back"],
                "Returns to the title menu.",
                "exit",
                "load-cancel",
            ),
        ],
    ),
    _screen_spec(
        "customize",
        CUSTOMIZE,
        "Customize world",
        "CUSTOM.PIC with land-mass, temperature, climate and age questions. Civ64 SCENES.md 7.4; civd GAME.C _game_menu.",
        ["SCENES.md 7.4"],
        ["GAME.C"],
        [("R:01A8:0591", "customize world")],
        [
            _object(
                "custom-land",
                "Land mass",
                ["land", "land mass"],
                "World parameter DGROUP:7EF6; the selected item is not modelled.",
            ),
            _object(
                "custom-temperature",
                "Temperature",
                ["temperature", "temp"],
                "World parameter DGROUP:7EF8; the selected item is not modelled.",
            ),
            _object(
                "custom-climate",
                "Climate",
                ["climate"],
                "World parameter DGROUP:7EFA; the selected item is not modelled.",
            ),
            _object(
                "custom-age",
                "Age",
                ["age"],
                "World parameter DGROUP:7EFC; the selected item is not modelled.",
            ),
            _object(
                "custom-begin",
                "Begin world",
                ["begin", "continue"],
                "Enters Birth with the declared parameters.",
                "activate",
                "customize-world",
            ),
            _object(
                "custom-cancel",
                "Cancel customize",
                ["cancel", "back"],
                "Returns to the title menu; the DOS path has no cancel, so this is an authored navigation aid.",
                "exit",
                "customize-cancel",
            ),
        ],
    ),
    _screen_spec(
        "birth",
        BIRTH,
        "Birth - world generation",
        "Eight picture scenes and STORY.TXT events. Civ64 SCENES.md 8; civd WORLDGEN.C _make_world.",
        ["SCENES.md 8"],
        ["WORLDGEN.C"],
        [("O7:0012", "Birth")],
        [
            _object(
                "birth-story",
                "World-generation story",
                ["story", "birth"],
                "Picture/text sequence; timing and assets are outside this scene.",
            ),
            _object(
                "birth-continue",
                "Continue after Birth",
                ["continue", "next"],
                "Moves to the difficulty question.",
                "activate",
                "birth-continue",
            ),
        ],
    ),
    _screen_spec(
        "difficulty",
        DIFFICULTY,
        "Difficulty level",
        "DIFFS.PIC portraits and five levels. Civ64 SCENES.md 9.1; civd NEWGAME.C _new_game.",
        ["SCENES.md 9.1"],
        ["NEWGAME.C"],
        [("O5:0031", "difficulty question")],
        [
            _object(
                "difficulty-menu",
                "Difficulty menu",
                ["difficulty", "level"],
                "Five portrait levels; only the declared initial value is represented.",
            ),
            _object(
                "difficulty-continue",
                "Continue difficulty",
                ["continue", "next"],
                "Advances to the competition question.",
                "activate",
                "difficulty-continue",
            ),
        ],
    ),
    _screen_spec(
        "competition",
        COMPETITION,
        "Level of competition",
        "Civilization count menu. Civ64 SCENES.md 9.2; civd NEWGAME.C _new_game.",
        ["SCENES.md 9.2"],
        ["NEWGAME.C"],
        [("O5:012E", "competition question")],
        [
            _object(
                "competition-menu",
                "Competition menu",
                ["competition", "civilizations"],
                "Number of civilizations; only the declared initial value is represented.",
            ),
            _object(
                "competition-continue",
                "Continue competition",
                ["continue", "next"],
                "Advances to the tribe question.",
                "activate",
                "competition-continue",
            ),
        ],
    ),
    _screen_spec(
        "tribe",
        TRIBE,
        "Pick your tribe",
        "Tribe records and portraits. Civ64 SCENES.md 9.3; civd NEWGAME.C _new_game.",
        ["SCENES.md 9.3"],
        ["NEWGAME.C"],
        [("O5:0309", "tribe question")],
        [
            _object(
                "tribe-menu",
                "Tribe menu",
                ["tribe", "civilization"],
                "Tribe choice; only the declared initial value is represented.",
            ),
            _object(
                "tribe-continue",
                "Continue tribe",
                ["continue", "next"],
                "Advances to leader naming.",
                "activate",
                "tribe-continue",
            ),
        ],
    ),
    _screen_spec(
        "leader-name",
        LEADER_NAME,
        "Your name",
        "White text-entry box. Civ64 SCENES.md 9.4-9.5 and 10.4; civd NAMES.C _rename_leader/_edit_line.",
        ["SCENES.md 9.4-9.5", "SCENES.md 10.4"],
        ["NAMES.C"],
        [("O23:00D6", "leader name"), ("O23:0414", "text entry")],
        [
            _object(
                "leader-name",
                "Leader name field",
                ["name", "leader"],
                "Thirteen-character edit field; text entry is not executed by this scene.",
            ),
            _object(
                "name-accept",
                "Accept name",
                ["accept", "continue"],
                "Advances to the introduction text.",
                "activate",
                "name-continue",
            ),
        ],
    ),
    _screen_spec(
        "intro",
        INTRO,
        "Introduction text",
        "KING.TXT *INIT text with the leader, tribe and starting advances. Civ64 SCENES.md 9.6; civd NEWGAME.C _new_game.",
        ["SCENES.md 9.6"],
        ["NEWGAME.C"],
        [("O5:0657", "introduction text")],
        [
            _object(
                "intro-text",
                "Opening text",
                ["intro", "introduction"],
                "The selected starting advances and tune are outside this scene.",
            ),
            _object(
                "intro-begin",
                "Begin play",
                ["begin", "continue", "play"],
                "Enters the world map.",
                "activate",
                "intro-begin",
            ),
        ],
    ),
    _screen_spec(
        "world",
        WORLD,
        "World map - play screen",
        "15x12 viewport, minimap, status and unit panels. Civ64 SCENES-PLAY.md 1-6; civd MAP.C/TURN.C/CONTROL.C/UNITS.C.",
        ["SCENES-PLAY.md 1-6"],
        ["MAP.C", "TURN.C", "CONTROL.C", "UNITS.C"],
        [
            ("R:1AEA:0008", "full map redraw"),
            ("R:1AEA:03BA", "one map square"),
            ("R:0238:0FEA", "menu bar"),
            ("R:0238:107E", "status panel"),
            ("R:0403:4060", "unit panel"),
            ("R:0403:0676", "play-screen input"),
            ("R:0866:0AD6", "active-unit blink"),
            ("R:0866:1D55", "move animation"),
            ("R:0866:1F69", "unit stack popup"),
        ],
        [
            _object(
                "world-map",
                "World map",
                ["map", "viewport"],
                "15 columns x 12 rows of 16x16 squares; terrain/unit/city layers are not rendered.",
            ),
            _object(
                "minimap",
                "Minimap",
                ["minimap", "small map"],
                "80x50 world overview with the view rectangle.",
            ),
            _object(
                "status-panel",
                "Status panel",
                ["status", "economy"],
                "Population, year, research and treasury/rate projection.",
            ),
            _object(
                "unit-panel",
                "Unit panel",
                ["unit panel", "units"],
                "Active-unit name, moves, home city and stack.",
            ),
            _object(
                "menu-bar",
                "Menu bar",
                ["menu"],
                "GAME, ORDERS, ADVISORS, WORLD, CIVILOPEDIA drop-downs.",
            ),
            _object(
                "world-city",
                "Open city",
                ["city", "open city"],
                "Enters the selected city screen.",
                "open",
                "enter-city",
            ),
            _object(
                "world-reports",
                "Reports",
                ["reports", "advisors"],
                "F1-F10 report frame and pages.",
                "open",
                "toggle-reports",
            ),
            _object(
                "world-pedia",
                "Civilopedia",
                ["pedia", "civilopedia"],
                "Index and entry lookup.",
                "open",
                "toggle-pedia",
            ),
            _object(
                "world-diplomacy",
                "Diplomacy",
                ["diplomacy", "audience"],
                "Leader audience and government change.",
                "open",
                "toggle-diplomacy",
            ),
            _object(
                "world-spaceship",
                "Spaceship",
                ["spaceship", "ship"],
                "Spaceship screen and launch surface.",
                "open",
                "toggle-spaceship",
            ),
            _object(
                "world-newspaper",
                "Newspaper",
                ["newspaper", "news"],
                "Newspaper page with headline and continuation cue.",
                "open",
                "toggle-newspaper",
            ),
            _object(
                "world-palace",
                "Palace",
                ["palace"],
                "Palace improvement and view scene.",
                "open",
                "toggle-palace",
            ),
            _object(
                "world-audience",
                "Leader audience",
                ["audience", "leader"],
                "Throne-room/leader screen.",
                "open",
                "toggle-audience",
            ),
            _object(
                "world-end-turn",
                "End turn",
                ["end turn", "turn"],
                "Advances the declared turn/year counters; economy, AI and unit resets are outside the model.",
                "activate",
                "end-turn",
            ),
        ],
    ),
    _screen_spec(
        "city",
        CITY,
        "City screen",
        "Info/Happy/Map/View city screen. Civ64 SCENES-PLAY.md 7.1; civd CITYMGT.C _city_process.",
        ["SCENES-PLAY.md 7.1"],
        ["CITYMGT.C"],
        [
            ("R:0D12:0045", "city screen"),
            ("R:0D12:7045", "building icons"),
            ("R:0D12:710D", "panel background"),
            ("R:0ADE:03EA", "root city caller"),
            ("R:0ADE:0093", "root city caller"),
            ("R:1459:0597", "root city caller"),
        ],
        [
            _object(
                "city-header",
                "City header",
                ["header", "title"],
                "City name and population; name catalog is outside the fixture.",
            ),
            _object(
                "city-resources",
                "City resources",
                ["resources", "income"],
                "Food, shields, trade, luxury, tax and science rows.",
            ),
            _object(
                "city-radius",
                "City radius",
                ["radius", "tiles"],
                "21-square worked map; tile assets are not rendered.",
            ),
            _object(
                "city-buildings",
                "Buildings and wonders",
                ["buildings", "wonders"],
                "Improvement list, MORE paging and wonder precedence.",
            ),
            _object(
                "city-production",
                "Production box",
                ["production", "shields"],
                "Selected unit/improvement and stored shields.",
            ),
            _object(
                "city-tabs",
                "City tabs",
                ["tabs", "info", "happy", "map", "view"],
                "INFO/HAPPY/MAP/VIEW tabs; detailed tab text is in the city fixture.",
            ),
            _object(
                "city-units",
                "City units",
                ["units", "unit list"],
                "Unit panel/cursor; opens the bounded unit-list context.",
                "open",
                "open-units",
            ),
            _object(
                "city-change",
                "Change production",
                ["change", "build"],
                "Opens the production chooser (key c).",
                "activate",
                "open-production",
            ),
            _object(
                "city-buy",
                "Buy production",
                ["buy", "purchase"],
                "Buy price/guard/commit are recovered in the separate buy contract; not exercised here.",
            ),
            _object(
                "city-rename",
                "Rename city",
                ["rename", "name"],
                "Text entry and city-name storage are outside this scene.",
            ),
            _object(
                "city-view",
                "City view",
                ["view city", "city view"],
                "Calls O19:0000(city, -1); opens the full-screen city view.",
                "open",
                "toggle-city-view",
            ),
            _object(
                "city-exit",
                "Exit city",
                ["exit", "leave city"],
                "Returns to the world map.",
                "exit",
                "leave-city",
            ),
        ],
        when=_and(
            _screen(CITY),
            _not(_eq("$chooser_open", True)),
            _not(_eq("$unit_list_open", True)),
        ),
    ),
    _screen_spec(
        "production",
        CITY,
        "City production chooser",
        "What shall we build? Civ64 SCENES-PLAY.md 7.12; civd ECONOMY.C _find_slot.",
        ["SCENES-PLAY.md 7.12"],
        ["ECONOMY.C"],
        [("R:0ADE:0421", "production menu")],
        [
            _object(
                "build-settlers",
                "Settlers",
                ["settlers", "build settlers"],
                "Commits production code 0; supported by the bounded city fixture and runtime record read.",
                "build",
                "build-settlers",
            ),
            _object(
                "build-militia",
                "Militia",
                ["militia", "build militia"],
                "Commits production code 1; supported by the bounded city fixture and runtime record read.",
                "build",
                "build-militia",
            ),
        ],
        when=_and(
            _screen(CITY),
            _eq("$chooser_open", True),
            _not(_eq("$unit_list_open", True)),
        ),
    ),
    _screen_spec(
        "units",
        CITY,
        "City unit list",
        "Unit cursor opened by key a. Civ64 SCENES-PLAY.md 7.1; civd CITYMGT.C.",
        ["SCENES-PLAY.md 7.1"],
        ["CITYMGT.C", "CONTROL.C", "UNITS.C"],
        [("R:0403:4060", "unit panel"), ("R:0866:1F69", "unit stack popup")],
        [
            _object(
                "unit-list",
                "Unit list",
                ["list", "units"],
                "Cursor and count are declared state; the detailed next/previous/select model is in the city fixture.",
            ),
            _object(
                "unit-close",
                "Close unit list",
                ["close", "exit"],
                "Stores the cursor at [0x70DC] and returns to the city.",
                "exit",
                "close-units",
            ),
        ],
        when=_and(
            _screen(CITY),
            _eq("$unit_list_open", True),
            _not(_eq("$chooser_open", True)),
        ),
    ),
    _screen_spec(
        "city-view",
        CITY_VIEW,
        "City view",
        "19x12 city view; new wonder dissolve and animations. Civ64 SCENES-PLAY.md 7.2-7.3; civd CITYVIEW.C _city_scene.",
        ["SCENES-PLAY.md 7.2-7.3"],
        ["CITYVIEW.C"],
        [
            ("O19:0000", "city view"),
            ("O19:167B", "invaders"),
            ("O19:18C1", "civil disorder"),
            ("O19:1AE1", "celebration"),
        ],
        [
            _object(
                "city-view-scene",
                "City view scene",
                ["scene", "houses"],
                "Assets, palette, seeded grid and animation timing are outside this scene.",
            ),
            _object(
                "city-view-exit",
                "Exit city view",
                ["exit", "back"],
                "Returns to the city screen.",
                "exit",
                "toggle-city-view",
            ),
        ],
    ),
    _screen_spec(
        "reports",
        REPORTS,
        "Reports and advisors",
        "O14 report frame with F1-F10 pages. Civ64 SCENES-PLAY.md 7.14; civd ADVISORS.C/REPORTS.C.",
        ["SCENES-PLAY.md 7.14"],
        ["ADVISORS.C", "REPORTS.C", "TURN.C"],
        [
            ("O14:0000", "report frame"),
            ("O14:186F", "city status"),
            ("O14:03AD", "military status"),
            ("O14:014B", "science"),
            ("O14:07F1", "trade"),
            ("O12:0000", "world map"),
        ],
        [
            _object(
                "report-frame",
                "Report frame",
                ["frame", "header"],
                "Title, realm, leader and year header.",
            ),
            _object(
                "report-city",
                "City status",
                ["city status", "cities"],
                "O14:186F; rows and paging are not rendered.",
            ),
            _object(
                "report-military",
                "Military status",
                ["military", "losses"],
                "O14:03AD/061F.",
            ),
            _object(
                "report-science", "Science report", ["science", "research"], "O14:014B."
            ),
            _object("report-trade", "Trade report", ["trade", "economy"], "O14:07F1."),
            _object(
                "report-world",
                "World map report",
                ["world map", "map report"],
                "O12:0000; 4x4 terrain tiles.",
            ),
            _object(
                "report-back",
                "Close reports",
                ["exit", "back"],
                "Returns to the world map.",
                "exit",
                "toggle-reports",
            ),
        ],
    ),
    _screen_spec(
        "pedia",
        PEDIA,
        "Civilopedia",
        "Index and entry lookup. Civ64 SCENES-PLAY.md 7.13; civd PEDIA.C _civilopedia/_pedia_show.",
        ["SCENES-PLAY.md 7.13"],
        ["PEDIA.C"],
        [("O8:0000", "pedia index"), ("O8:062A", "pedia entry")],
        [
            _object(
                "pedia-index",
                "Civilopedia index",
                ["index"],
                "Advances, units and terrain tables.",
            ),
            _object(
                "pedia-entry",
                "Civilopedia entry",
                ["entry", "article"],
                "BLURB text and picture cells are outside this scene.",
            ),
            _object(
                "pedia-back",
                "Close Civilopedia",
                ["exit", "back"],
                "Returns to the world map.",
                "exit",
                "toggle-pedia",
            ),
        ],
    ),
    _screen_spec(
        "diplomacy",
        DIPLOMACY,
        "Diplomacy and audience",
        "Leader audience and government change. Civ64 SCENES-PLAY.md 7.9-7.10; civd AUDIENCE.C/DIPLOMAC.C.",
        ["SCENES-PLAY.md 7.9-7.10"],
        ["AUDIENCE.C", "DIPLOMAC.C"],
        [("O6:1D2B", "leader screen"), ("R:1517:04A1", "government change")],
        [
            _object(
                "audience-scene",
                "Leader audience",
                ["audience", "leader"],
                "Throne room/leader picture path; dialogue and attitudes are outside this scene.",
            ),
            _object(
                "government-change",
                "Government change",
                ["government", "cabinet"],
                "New Cabinet display; government rules are not modelled.",
            ),
            _object(
                "diplomacy-back",
                "Leave diplomacy",
                ["exit", "back"],
                "Returns to the world map.",
                "exit",
                "toggle-diplomacy",
            ),
        ],
    ),
    _screen_spec(
        "spaceship",
        SPACESHIP,
        "Spaceship",
        "Spaceship screen and launch surface. Civ64 SCENES-PLAY.md 7.16; civd SPACESHP.C.",
        ["SCENES-PLAY.md 7.16"],
        ["SPACESHP.C"],
        [("O18:0000", "spaceship open"), ("O18:0F83", "spaceship build")],
        [
            _object(
                "spaceship-scene",
                "Spaceship scene",
                ["ship", "parts"],
                "Part grid, stats and star field are not rendered.",
            ),
            _object(
                "spaceship-build",
                "Build spaceship",
                ["build", "launch"],
                "Build/launch rules are outside this scene.",
            ),
            _object(
                "spaceship-back",
                "Leave spaceship",
                ["exit", "back"],
                "Returns to the world map.",
                "exit",
                "toggle-spaceship",
            ),
        ],
    ),
    _screen_spec(
        "hall",
        HALL,
        "Hall of Fame",
        "FAME.DTA entries. Civ64 SCENES.md 7.5 and SCENES-PLAY.md 7.17; civd FAME.C.",
        ["SCENES.md 7.5", "SCENES-PLAY.md 7.17"],
        ["FAME.C"],
        [("O3:002B", "Hall of Fame load"), ("O3:00D7", "Hall of Fame show")],
        [
            _object(
                "hall-entries",
                "Hall entries",
                ["entries", "fame"],
                "Six entries from FAME.DTA; file parsing is outside this scene.",
            ),
            _object(
                "hall-back",
                "Close Hall of Fame",
                ["exit", "back"],
                "Returns to the title menu.",
                "exit",
                "toggle-hall",
            ),
        ],
    ),
    _screen_spec(
        "game-over",
        GAME_OVER,
        "Game over",
        "End checks and ending screens. Civ64 SCENES-PLAY.md 7.17; civd TURN.C _game_turn/REPLAY.C.",
        ["SCENES-PLAY.md 7.17"],
        ["TURN.C", "REPLAY.C"],
        [("R:0238:0092", "end checks"), ("O9:0DDE", "conqueror ending")],
        [
            _object(
                "game-over-text",
                "Game-over ending",
                ["ending", "game over"],
                "Trigger conditions are outside this scene; the context is state-reachable for inspection.",
            ),
            _object(
                "game-over-new",
                "New game after ending",
                ["new game", "restart"],
                "Resets the declared scene state to the title menu.",
                "activate",
                "new-game-after-end",
            ),
        ],
    ),
    _screen_spec(
        "newspaper",
        NEWSPAPER,
        "Newspaper",
        "Newspaper page with headline and torn edge. Civ64 SCENES-PLAY.md 7.7; civd NEWS.C _news_box.",
        ["SCENES-PLAY.md 7.7"],
        ["NEWS.C"],
        [("O21:0000", "newspaper")],
        [
            _object(
                "newspaper-page",
                "Newspaper page",
                ["news", "headline"],
                "Headline text and torn-edge art are outside this scene.",
            ),
            _object(
                "newspaper-back",
                "Continue from newspaper",
                ["continue", "exit"],
                "Returns to the world map.",
                "exit",
                "toggle-newspaper",
            ),
        ],
    ),
    _screen_spec(
        "palace",
        PALACE,
        "Palace",
        "Palace view and improvement scene. Civ64 SCENES-PLAY.md 7.8; civd PALACE.C _palace_view.",
        ["SCENES-PLAY.md 7.8"],
        ["PALACE.C"],
        [("O17:0000", "palace view")],
        [
            _object(
                "palace-view",
                "Palace view",
                ["palace", "castle"],
                "Section composition and assets are not rendered.",
            ),
            _object(
                "palace-back",
                "Leave palace",
                ["exit", "back"],
                "Returns to the world map.",
                "exit",
                "toggle-palace",
            ),
        ],
    ),
    _screen_spec(
        "audience",
        AUDIENCE,
        "Leader audience",
        "Throne room/leader screen. Civ64 SCENES-PLAY.md 7.9; civd AUDIENCE.C _load_leader.",
        ["SCENES-PLAY.md 7.9"],
        ["AUDIENCE.C"],
        [("O6:1D2B", "leader screen")],
        [
            _object(
                "audience-view",
                "Audience view",
                ["audience", "leader"],
                "Leader portrait, expression and lower text strip; dialogue is outside this scene.",
            ),
            _object(
                "audience-back",
                "Leave audience",
                ["exit", "back"],
                "Returns to the world map.",
                "exit",
                "toggle-audience",
            ),
        ],
    ),
]


def _set_block(name: str, var: str, value, suffix: str = "") -> dict:
    return {
        "id": f"{name}-set-{var[1:]}{suffix}",
        "op": "set",
        "var": var,
        "value": value,
    }


def _text_block(name: str, resource: str, suffix: str = "") -> dict:
    return {"id": f"{name}-text{suffix}", "op": "text", "resource": resource}


def _program(name: str, body: list[dict], resources: dict) -> dict:
    return {
        "format": "fdisbull-il-1",
        "role": "uil",
        "variables": deepcopy(VARIABLES),
        "resources": resources,
        "body": body,
    }


def _transition(
    name: str, screen: int, text: str, *sets: tuple[str, int | bool | dict]
) -> dict:
    body = [_set_block(name, "$screen", screen)]
    for var, value in sets:
        body.append(_set_block(name, var, value))
    body.append(_text_block(name, f"{name}-text"))
    return _program(name, body, {f"{name}-text": {"kind": "text", "text": text}})


def _toggle(
    name: str, first: int, second: int, first_text: str, second_text: str
) -> dict:
    first_key = f"{name}-first-text"
    second_key = f"{name}-second-text"
    body = [
        {
            "id": f"{name}-branch",
            "op": "if",
            "condition": _screen(first),
            "then": [
                _set_block(name, "$screen", second, "-then"),
                _text_block(name, second_key, "-then"),
            ],
            "else": [
                _set_block(name, "$screen", first, "-else"),
                _text_block(name, first_key, "-else"),
            ],
        }
    ]
    return _program(
        name,
        body,
        {
            first_key: {"kind": "text", "text": first_text},
            second_key: {"kind": "text", "text": second_text},
        },
    )


def build_programs() -> dict:
    programs = {}

    def add(name: str, program: dict) -> None:
        if name in programs:
            raise ValueError(f"duplicate program {name}")
        programs[name] = program

    add(
        "new-game",
        _transition(
            "new-game",
            BIRTH,
            "Birth begins; the new-game setup follows world generation.",
        ),
    )
    add(
        "enter-load",
        _transition(
            "enter-load", LOAD, "Load game: drive prompt and ten fixed save slots."
        ),
    )
    add(
        "load-world",
        _transition(
            "load-world",
            WORLD,
            "Loaded game enters the world map; save parsing is not modelled.",
        ),
    )
    add("load-cancel", _transition("load-cancel", TITLE, "Returned to the title menu."))
    add(
        "enter-customize",
        _transition(
            "enter-customize",
            CUSTOMIZE,
            "Customize world: land mass, temperature, climate and age.",
        ),
    )
    add(
        "customize-world",
        _transition(
            "customize-world",
            BIRTH,
            "Custom parameters enter Birth; selected values are not modelled.",
        ),
    )
    add(
        "customize-cancel",
        _transition("customize-cancel", TITLE, "Returned to the title menu."),
    )
    add(
        "birth-continue",
        _transition(
            "birth-continue", DIFFICULTY, "Birth finished; difficulty question."
        ),
    )
    add(
        "difficulty-continue",
        _transition(
            "difficulty-continue",
            COMPETITION,
            "Difficulty choice recorded as declared state; competition question.",
        ),
    )
    add(
        "competition-continue",
        _transition(
            "competition-continue",
            TRIBE,
            "Competition choice recorded as declared state; tribe question.",
        ),
    )
    add(
        "tribe-continue",
        _transition(
            "tribe-continue",
            LEADER_NAME,
            "Tribe choice recorded as declared state; leader name.",
        ),
    )
    add(
        "name-continue",
        _transition("name-continue", INTRO, "Name field accepted; introduction text."),
    )
    add(
        "intro-begin",
        _transition("intro-begin", WORLD, "Play begins at the world map."),
    )
    add(
        "toggle-hall",
        _toggle("toggle-hall", TITLE, HALL, "Title menu.", "Hall of Fame entries."),
    )
    add(
        "enter-city",
        _transition(
            "enter-city",
            CITY,
            "City screen; city 0 is the declared selector.",
            ("$selected_city", 0),
            ("$chooser_open", False),
            ("$unit_list_open", False),
        ),
    )
    add(
        "leave-city",
        _transition(
            "leave-city",
            WORLD,
            "Returned to the world map.",
            ("$chooser_open", False),
            ("$unit_list_open", False),
        ),
    )
    add(
        "open-production",
        _transition(
            "open-production",
            CITY,
            "Production chooser: key c / R:0ADE:0421.",
            ("$chooser_open", True),
            ("$unit_list_open", False),
        ),
    )
    add(
        "build-settlers",
        _transition(
            "build-settlers",
            CITY,
            "Settlers committed as production code 0.",
            ("$production", 0),
            ("$chooser_open", False),
        ),
    )
    add(
        "build-militia",
        _transition(
            "build-militia",
            CITY,
            "Militia committed as production code 1.",
            ("$production", 1),
            ("$chooser_open", False),
        ),
    )
    add(
        "open-units",
        _transition(
            "open-units",
            CITY,
            "City unit list opened with cursor 0.",
            ("$unit_list_open", True),
            ("$chooser_open", False),
            ("$unit_cursor", 0),
        ),
    )
    add(
        "close-units",
        _transition(
            "close-units",
            CITY,
            "Unit cursor stored at [0x70DC]; returned to the city.",
            ("$city_cursor", {"var": "$unit_cursor"}),
            ("$unit_list_open", False),
        ),
    )
    add(
        "toggle-city-view",
        _toggle(
            "toggle-city-view",
            CITY,
            CITY_VIEW,
            "City screen.",
            "City view; assets and animation are outside this scene.",
        ),
    )
    add(
        "toggle-reports",
        _toggle(
            "toggle-reports", WORLD, REPORTS, "World map.", "Reports and advisors."
        ),
    )
    add(
        "toggle-pedia",
        _toggle("toggle-pedia", WORLD, PEDIA, "World map.", "Civilopedia."),
    )
    add(
        "toggle-diplomacy",
        _toggle(
            "toggle-diplomacy",
            WORLD,
            DIPLOMACY,
            "World map.",
            "Diplomacy and audience.",
        ),
    )
    add(
        "toggle-spaceship",
        _toggle("toggle-spaceship", WORLD, SPACESHIP, "World map.", "Spaceship."),
    )
    add(
        "toggle-newspaper",
        _toggle("toggle-newspaper", WORLD, NEWSPAPER, "World map.", "Newspaper."),
    )
    add(
        "toggle-palace",
        _toggle("toggle-palace", WORLD, PALACE, "World map.", "Palace."),
    )
    add(
        "toggle-audience",
        _toggle("toggle-audience", WORLD, AUDIENCE, "World map.", "Leader audience."),
    )
    add(
        "end-turn",
        _program(
            "end-turn",
            [
                {"id": "end-turn-add-turn", "op": "add", "var": "$turn", "value": 1},
                {"id": "end-turn-add-year", "op": "add", "var": "$year", "value": 1},
                _text_block("end-turn", "end-turn-text"),
            ],
            {
                "end-turn-text": {
                    "kind": "text",
                    "text": "Turn and year counters advanced; economy, AI and unit resets are outside the model.",
                }
            },
        ),
    )
    add(
        "new-game-after-end",
        _program(
            "new-game-after-end",
            [
                _set_block("new-game-after-end", "$screen", TITLE),
                _set_block("new-game-after-end", "$game_over", False),
                _set_block("new-game-after-end", "$turn", 1),
                _set_block("new-game-after-end", "$year", -4000),
                _text_block("new-game-after-end", "new-game-after-end-text"),
            ],
            {
                "new-game-after-end-text": {
                    "kind": "text",
                    "text": "Game-over state cleared; returned to the title menu.",
                }
            },
        ),
    )

    if not 1 <= len(programs) <= 32:
        raise ValueError(f"program count {len(programs)} exceeds the scene budget")
    return programs


def build_scene() -> dict:
    programs = build_programs()
    contexts = []
    objects = []
    seen_contexts = set()
    seen_objects = set()
    for spec in SCREEN_SPECS:
        if spec["id"] in seen_contexts:
            raise ValueError(f"duplicate context {spec['id']}")
        seen_contexts.add(spec["id"])
        contexts.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "description": spec["description"],
                "when": deepcopy(spec["when"]),
            }
        )
        for obj in spec["objects"]:
            item = deepcopy(obj)
            item["context"] = spec["id"]
            if item["id"] in seen_objects:
                raise ValueError(f"duplicate object {item['id']}")
            seen_objects.add(item["id"])
            for binding in item["bindings"]:
                if binding["program"] not in programs:
                    raise ValueError(f"unresolved binding {binding['program']}")
            objects.append(item)
    if not 1 <= len(contexts) <= 64:
        raise ValueError(f"context count {len(contexts)} exceeds the scene budget")
    if len(objects) > 256:
        raise ValueError(f"object count {len(objects)} exceeds the scene budget")
    return {
        "format": "fdisbull-il-scene-1",
        "partial": True,
        "programs": programs,
        "contexts": contexts,
        "objects": objects,
    }


def canonical_json(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _parse_address(address: str) -> tuple[int, int | None]:
    if address.startswith("R:"):
        segment, offset = address[2:].split(":")
        return int(segment, 16) * 16 + int(offset, 16), None
    if address.startswith("O"):
        overlay, offset = address[1:].split(":")
        return OVERLAY_BASE + int(offset, 16), int(overlay, 10)
    raise ValueError(f"unsupported address {address}")


def resolve_anchor(atlas: dict | None, address: str, role: str) -> dict:
    row = {
        "address": address,
        "role": role,
        "linear": None,
        "overlay": None,
        "function": None,
        "source": None,
        "position": "unresolved",
    }
    if atlas is None:
        return row
    linear, overlay = _parse_address(address)
    row.update(linear=linear, overlay=overlay)
    for function in atlas.get("functions", []):
        if function.get("overlay") != overlay:
            continue
        if function.get("start", 0) <= linear < function.get("end", 0):
            row.update(
                function=function.get("name"),
                source=function.get("source"),
                position="entry" if function.get("start") == linear else "inside",
            )
            break
    return row


def build_provenance(
    scene: dict,
    *,
    scene_name: str = "examples/civ/civ_game_scene.json",
    atlas: dict | None = None,
    atlas_name: str = "examples/civ/civ_exe_atlas.json",
    atlas_sha256: str | None = None,
    civd_src: Path | None = None,
) -> dict:
    screens = []
    for spec in SCREEN_SPECS:
        screens.append(
            {
                "id": spec["id"],
                "screen": spec["screen"],
                "civ64": spec["civ64"],
                "civd": spec["civd"],
                "objects": len(spec["objects"]),
                "anchors": [
                    resolve_anchor(atlas, address, role)
                    for address, role in spec["anchors"]
                ],
            }
        )
    sources = []
    if civd_src is not None:
        for name in CIVD_SOURCES:
            path = civd_src / name
            if path.is_file():
                sources.append({"path": f"src/{name}", "sha256": sha256_file(path)})
    return {
        "format": "fdisbull-civ-game-uil-provenance-1",
        "scene": scene_name,
        "scene_sha256": sha256_bytes(canonical_json(scene)),
        "edition": {
            "label": "pinned Civ 474.05 / Civ64 475.05 DOS root",
            "packed_sha256": PACKED_SHA256,
            "unpacked_sha256": UNPACKED_SHA256,
            "edition_status": "conflict",
            "note": "civd calls the packed hash 474.05; Civ64 documentation calls the same bytes 475.05. The scene does not merge the labels.",
        },
        "authorities": {
            "civd": {
                "repository": "sjmelia/civd",
                "commit": CIVD_COMMIT,
                "sources": sources,
            },
            "civ64": {
                "repository": "Buyukcaglar/Civ64",
                "commit": CIV64_COMMIT,
                "documents": ["docs/dos/SCENES.md", "docs/dos/SCENES-PLAY.md"],
                "label": "DOS listing",
            },
            "atlas": {
                "path": atlas_name,
                "sha256": atlas_sha256
                or (sha256_bytes(canonical_json(atlas)) if atlas is not None else None),
                "functions": len(atlas.get("functions", [])) if atlas else None,
                "overlays": len(atlas.get("overlays", [])) if atlas else None,
            },
        },
        "screens": screens,
        "state": [
            {
                "name": name,
                "type": VARIABLES[name]["type"],
                "initial": VARIABLES[name]["initial"],
                "evidence": STATE_EVIDENCE[name],
            }
            for name in VARIABLES
        ],
        "entities": [
            {
                "name": "map",
                "evidence": "80x50 world; terrain/unit/improvement page map; Civ64 SCENES-PLAY 1.1/2.",
            },
            {
                "name": "city",
                "evidence": "128 records of 1Ch at DGROUP:70EC; civd reference/struct_city.md; Civ64 SCENES-PLAY 2.3.",
            },
            {
                "name": "unit",
                "evidence": "DGROUP:81D4 + civ*600h + unit*0Ch; civd reference/struct_unit.md; Civ64 SCENES-PLAY 2.2.",
            },
            {
                "name": "civilization",
                "evidence": "Human civilization DGROUP:D7F0; Civ64 SCENES-PLAY 7.19.",
            },
        ],
        "rule_links": [
            "docs/CIV_CITY_UIL_UDC.md#bounded-udc-module",
            "docs/CIV_CITY_UIL_UDC.md#buy-price-guard-and-commit-module",
            "docs/CIV_PATHFINDING_TRACE.md",
            "docs/CIV_CITY_STATIC_TRACE.md",
        ],
        "limits": [
            "Partial scene graph and state projection, not a full game simulation.",
            "No DOS execution, VGA rendering, input decoding, AI, combat, technology, diplomacy, save parsing or economy model.",
            "Setup choices advance the declared state; individual menu choices are not bound.",
            "The game-over context is state-reachable for inspection; its trigger conditions are not modelled.",
            "Every screen boundary is resolved against a civd function; this is address resolution, not Windows-to-DOS byte equivalence.",
        ],
    }


def validate_scene(scene: dict) -> None:
    from fdisbull.il_scenes import ILSceneBackend

    backend = ILSceneBackend(scene)
    observation = backend.observe()
    if not observation.get("complete"):
        raise ValueError("Initial scene context is not unique")


def validate_provenance(provenance: dict) -> None:
    unresolved = [
        f"{row['id']}:{anchor['address']}"
        for row in provenance["screens"]
        for anchor in row["anchors"]
        if anchor["position"] == "unresolved"
    ]
    if unresolved:
        raise ValueError("unresolved screen anchors: " + ", ".join(unresolved))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the scene JSON here")
    parser.add_argument(
        "--provenance", type=Path, help="write the provenance JSON here"
    )
    parser.add_argument(
        "--atlas", type=Path, default=Path("examples/civ/civ_exe_atlas.json")
    )
    parser.add_argument(
        "--civd-src", type=Path, help="civd src/ directory for source hashes"
    )
    parser.add_argument("--scene-name", default="examples/civ/civ_game_scene.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the scene and every evidence anchor",
    )
    args = parser.parse_args(argv)

    scene = build_scene()
    atlas = None
    if args.atlas.is_file():
        atlas = json.loads(args.atlas.read_text(encoding="utf-8"))
    provenance = build_provenance(
        scene,
        scene_name=args.scene_name,
        atlas=atlas,
        atlas_name=str(args.atlas),
        atlas_sha256=sha256_file(args.atlas) if atlas is not None else None,
        civd_src=args.civd_src,
    )
    if args.check:
        validate_scene(scene)
        validate_provenance(provenance)
    if args.out:
        _write(args.out, scene)
    if args.provenance:
        _write(args.provenance, provenance)
    if not args.out and not args.provenance:
        print(
            json.dumps(
                {
                    "contexts": len(scene["contexts"]),
                    "objects": len(scene["objects"]),
                    "programs": len(scene["programs"]),
                    "scene_sha256": provenance["scene_sha256"],
                    "screens": len(provenance["screens"]),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
