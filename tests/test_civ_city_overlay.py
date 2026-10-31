"""The Civ city debugger-scene definition stays within the scene contract."""

import pytest

from examples.civ.civ_city_overlay import scene_definition
from fdisbull.scenes import action, context, name, predicate, region


def test_city_overlay_definition_uses_valid_geometry_and_predicates():
    document = scene_definition("reference", ["chooser-1", "chooser-2"])
    assert document["format"] == "fdisbull-scene-1"
    assert (document["width"], document["height"], document["mode_id"]) == (320, 200, 5)
    predicate(document["match"], 320, 200)
    context(document["context"])
    names = []
    for obj in document["objects"]:
        name(obj["name"])
        context(obj["context"])
        action(obj["action"])
        for key in ("visible", "ready", "enabled"):
            predicate(obj[key], 320, 200)
        predicate(obj["outcome"], 320, 200, allow_before=True)
        mask = region(obj["area"], 320, 200)
        assert mask.getpixel(tuple(obj["point"])), obj["name"]
        assert obj["evidence"]
        names.append(obj["name"])
    assert names == ["tab-happy", "tab-map", "change", "tab-city-view"]


def test_city_overlay_change_accepts_a_longer_chooser_list():
    document = scene_definition("reference", ["chooser-1", "chooser-2"])
    change = next(obj for obj in document["objects"] if obj["name"] == "change")
    samples = change["outcome"]["pixels"]
    assert len(samples["samples"]) == 3
    assert samples["min_matches"] == 2
    assert samples["tolerance"] == 0
    assert change["evidence"] == ["reference", "chooser-1", "chooser-2"]


def test_city_overlay_requires_a_chooser_frame():
    with pytest.raises(ValueError):
        scene_definition("reference", [])
