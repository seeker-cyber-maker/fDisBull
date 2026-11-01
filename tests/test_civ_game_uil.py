"""Regression coverage for the partial game-level Civilization UIL scene."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from examples.civ.civ_game_uil import (
    GAME_OVER,
    SCREEN_NAMES,
    TITLE,
    VARIABLES,
    build_scene,
    canonical_json,
)
from fdisbull.il_scenes import ILSceneBackend

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "examples/civ/civ_game_scene.json"
PROVENANCE = ROOT / "examples/civ/civ_game_scene.provenance.json"


def _act(backend, verb, target):
    observation = backend.observe()
    assert observation["complete"], observation
    return backend.act(
        {
            "verb": verb,
            "target": target,
            "item": None,
            "context_token": observation["context"]["token"],
        }
    )


def _to_world(backend):
    for verb, target in (
        ("activate", "title-new"),
        ("activate", "birth-continue"),
        ("activate", "difficulty-prince"),
        ("activate", "competition-five"),
        ("activate", "tribe-row-1"),
        ("activate", "name-accept"),
        ("activate", "intro-begin"),
    ):
        assert _act(backend, verb, target)["status"] == "success", (verb, target)
    assert backend.observe()["context"]["id"] == "world"


def test_scene_has_bounded_screens_and_validates():
    scene = build_scene()
    assert scene["format"] == "fdisbull-il-scene-1"
    assert scene["partial"] is True
    assert len(scene["contexts"]) == 23
    assert len(scene["objects"]) == 93
    assert len(scene["programs"]) == 45
    context_ids = {context["id"] for context in scene["contexts"]}
    assert context_ids == set(SCREEN_NAMES.values()) | {"production", "units"}
    object_ids = {item["id"] for item in scene["objects"]}
    assert {
        "city-change",
        "build-militia",
        "world-reports",
        "game-over-new",
    } <= object_ids
    assert "city-change" in {
        item["id"] for item in scene["objects"] if item["context"] == "city"
    }
    used = {
        binding["program"] for item in scene["objects"] for binding in item["bindings"]
    }
    assert used == set(scene["programs"])
    ILSceneBackend(scene)


def test_difficulty_menu_binds_all_five_cur_tier_rows():
    for target, level in (
        ("difficulty-chieftain", 0),
        ("difficulty-warlord", 1),
        ("difficulty-prince", 2),
        ("difficulty-king", 3),
        ("difficulty-emperor", 4),
    ):
        backend = ILSceneBackend(build_scene())
        assert _act(backend, "activate", "title-new")["status"] == "success"
        assert _act(backend, "activate", "birth-continue")["status"] == "success"
        assert backend.observe()["context"]["id"] == "difficulty"
        assert _act(backend, "activate", target)["status"] == "success"
        assert backend.state["$difficulty"] == level
        assert backend.observe()["context"]["id"] == "competition"


def test_competition_menu_binds_civ_total_and_players_mask():
    for target, civ_total, players in (
        ("competition-seven", 6, 255),
        ("competition-six", 5, 127),
        ("competition-five", 4, 63),
        ("competition-four", 3, 31),
        ("competition-three", 2, 15),
    ):
        backend = ILSceneBackend(build_scene())
        assert _act(backend, "activate", "title-new")["status"] == "success"
        assert _act(backend, "activate", "birth-continue")["status"] == "success"
        assert _act(backend, "activate", "difficulty-prince")["status"] == "success"
        assert backend.observe()["context"]["id"] == "competition"
        assert _act(backend, "activate", target)["status"] == "success"
        assert backend.state["$competition"] == civ_total
        assert backend.state["$players"] == players
        assert backend.observe()["context"]["id"] == "tribe"


def test_first_tribe_row_binds_civnow_and_tribe():
    backend = ILSceneBackend(build_scene())
    assert _act(backend, "activate", "title-new")["status"] == "success"
    assert _act(backend, "activate", "birth-continue")["status"] == "success"
    assert _act(backend, "activate", "difficulty-prince")["status"] == "success"
    assert _act(backend, "activate", "competition-five")["status"] == "success"
    assert backend.observe()["context"]["id"] == "tribe"
    assert _act(backend, "activate", "tribe-row-1")["status"] == "success"
    assert backend.state["$human_civ"] == 1
    assert backend.state["$tribe"] == 1
    assert backend.observe()["context"]["id"] == "leader-name"


def test_second_tribe_group_row_binds_alternate_tribe():
    backend = ILSceneBackend(build_scene())
    assert _act(backend, "activate", "title-new")["status"] == "success"
    assert _act(backend, "activate", "birth-continue")["status"] == "success"
    assert _act(backend, "activate", "difficulty-prince")["status"] == "success"
    assert _act(backend, "activate", "competition-five")["status"] == "success"
    assert backend.observe()["context"]["id"] == "tribe"
    assert _act(backend, "activate", "tribe-row-9")["status"] == "success"
    assert backend.state["$human_civ"] == 1
    assert backend.state["$tribe"] == 9
    assert backend.observe()["context"]["id"] == "leader-name"


def test_startup_flow_reaches_world_and_end_turn_advances_declared_state():
    backend = ILSceneBackend(build_scene())
    assert backend.observe()["context"]["id"] == "title"
    _to_world(backend)
    turn, year = backend.state["$turn"], backend.state["$year"]
    assert _act(backend, "activate", "world-end-turn")["status"] == "success"
    assert backend.state["$turn"] == turn + 1
    assert backend.state["$year"] == year + 1


def test_city_subcontexts_and_all_world_overlays_round_trip():
    backend = ILSceneBackend(build_scene())
    _to_world(backend)

    assert _act(backend, "open", "world-city")["status"] == "success"
    assert backend.observe()["context"]["id"] == "city"

    assert _act(backend, "activate", "city-change")["status"] == "success"
    assert backend.observe()["context"]["id"] == "production"
    assert _act(backend, "build", "build-settlers")["status"] == "success"
    assert backend.state["$production"] == 0
    assert backend.observe()["context"]["id"] == "city"

    assert _act(backend, "open", "city-units")["status"] == "success"
    assert backend.observe()["context"]["id"] == "units"
    assert _act(backend, "exit", "unit-close")["status"] == "success"
    assert backend.observe()["context"]["id"] == "city"

    assert _act(backend, "open", "city-view")["status"] == "success"
    assert backend.observe()["context"]["id"] == "city-view"
    assert _act(backend, "exit", "city-view-exit")["status"] == "success"
    assert backend.observe()["context"]["id"] == "city"
    assert _act(backend, "exit", "city-exit")["status"] == "success"
    assert backend.observe()["context"]["id"] == "world"

    for target, context, close in (
        ("world-reports", "reports", "report-back"),
        ("world-pedia", "pedia", "pedia-back"),
        ("world-diplomacy", "diplomacy", "diplomacy-back"),
        ("world-spaceship", "spaceship", "spaceship-back"),
        ("world-newspaper", "newspaper", "newspaper-back"),
        ("world-palace", "palace", "palace-back"),
        ("world-audience", "audience", "audience-back"),
    ):
        assert _act(backend, "open", target)["status"] == "success", target
        assert backend.observe()["context"]["id"] == context
        assert _act(backend, "exit", close)["status"] == "success", close
        assert backend.observe()["context"]["id"] == "world"


def test_city_auto_build_toggles_status_projection():
    backend = ILSceneBackend(build_scene())
    _to_world(backend)
    assert _act(backend, "open", "world-city")["status"] == "success"
    assert backend.state["$auto_build"] is False
    assert _act(backend, "activate", "city-auto")["status"] == "success"
    assert backend.state["$auto_build"] is True
    assert _act(backend, "activate", "city-auto")["status"] == "success"
    assert backend.state["$auto_build"] is False
    assert backend.observe()["context"]["id"] == "city"


def test_city_buy_computes_rush_price_and_commits_shields():
    backend = ILSceneBackend(build_scene())
    _to_world(backend)
    assert _act(backend, "open", "world-city")["status"] == "success"
    assert backend.state["$money"] == 1500
    assert backend.state["$shield_box"] == 0
    assert backend.state["$unit_cost"] == 10
    assert _act(backend, "buy", "city-buy")["status"] == "success"
    assert backend.state["$buy_price"] == 1400
    assert backend.state["$shield_box"] == 100
    assert backend.state["$money"] == 100
    assert _act(backend, "buy", "city-buy")["status"] == "success"
    assert backend.state["$buy_price"] == 0
    assert backend.state["$shield_box"] == 100
    assert backend.state["$money"] == 100


def test_city_unit_list_cursor_clamps_and_stores_selection():
    backend = ILSceneBackend(build_scene())
    _to_world(backend)
    assert _act(backend, "open", "world-city")["status"] == "success"
    assert _act(backend, "open", "city-units")["status"] == "success"
    assert backend.observe()["context"]["id"] == "units"
    assert backend.state["$unit_count"] == 3
    assert backend.state["$unit_last"] == 2
    assert _act(backend, "next", "unit-next")["status"] == "success"
    assert backend.state["$unit_cursor"] == 1
    assert _act(backend, "next", "unit-next")["status"] == "success"
    assert backend.state["$unit_cursor"] == 2
    assert _act(backend, "next", "unit-next")["status"] == "success"
    assert backend.state["$unit_cursor"] == 2
    assert _act(backend, "select", "unit-select")["status"] == "success"
    assert backend.state["$city_cursor"] == 2
    assert backend.observe()["context"]["id"] == "city"
    assert _act(backend, "open", "city-units")["status"] == "success"
    assert _act(backend, "previous", "unit-previous")["status"] == "success"
    assert backend.state["$unit_cursor"] == 0
    assert _act(backend, "next", "unit-next")["status"] == "success"
    assert _act(backend, "previous", "unit-previous")["status"] == "success"
    assert backend.state["$unit_cursor"] == 0


def test_game_over_context_is_state_reachable_and_new_game_resets():
    state = {name: declaration["initial"] for name, declaration in VARIABLES.items()}
    state["$screen"] = GAME_OVER
    state["$game_over"] = True
    backend = ILSceneBackend(build_scene(), state=state)
    assert backend.observe()["context"]["id"] == "game-over"
    assert _act(backend, "activate", "game-over-new")["status"] == "success"
    assert backend.observe()["context"]["id"] == "title"
    assert backend.state["$screen"] == TITLE
    assert backend.state["$game_over"] is False


def test_committed_scene_and_provenance_match_and_all_anchors_resolve():
    scene = json.loads(SCENE.read_text(encoding="utf-8"))
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert scene == build_scene()
    assert provenance["scene"] == "examples/civ/civ_game_scene.json"
    assert (
        provenance["scene_sha256"] == hashlib.sha256(canonical_json(scene)).hexdigest()
    )
    assert len(provenance["screens"]) == 23
    anchors = [anchor for row in provenance["screens"] for anchor in row["anchors"]]
    assert anchors
    assert all(anchor["function"] for anchor in anchors)
    assert all(anchor["position"] in ("entry", "inside") for anchor in anchors)
    assert (
        provenance["authorities"]["civd"]["commit"]
        == "d9214fcd36aa6003d28aae60c3974b665f752280"
    )
    assert provenance["authorities"]["civd"]["sources"]
    assert all(
        len(source["sha256"]) == 64
        for source in provenance["authorities"]["civd"]["sources"]
    )
    atlas = ROOT / "examples/civ/civ_exe_atlas.json"
    assert (
        provenance["authorities"]["atlas"]["sha256"]
        == hashlib.sha256(atlas.read_bytes()).hexdigest()
    )
    assert provenance["limits"]


def test_game_scene_serves_the_z_player_without_a_debugger():
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src") + ":" + str(ROOT / "player"))
    backend = shlex.join([sys.executable, "-m", "fdisbull.il_scenes", str(SCENE)])
    result = subprocess.run(
        [sys.executable, "-m", "fdisbull_player", "--backend-command", backend],
        input="look\nactivate new game\nlook\nquit\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Title menu" in result.stdout
    assert "Success: Birth begins" in result.stdout
    assert "Birth - world generation" in result.stdout
