"""Scene contracts through real input, native RGB probes and offline artifacts."""

from copy import deepcopy
import io
import json
import re

from PIL import Image
import pytest

from fdisbull.project import Project
from fdisbull.scenes import SceneError
from fdisbull.scene_geometry import region
from test_debugger import emulator
from test_dos_loader import mz_file
from test_keyboard import keyboard_game


def test_composite_regions_keep_holes_and_disconnected_actions():
    shape = {
        "union": [
            {"subtract": [{"rect": [1, 1, 8, 8]}, {"rect": [3, 3, 6, 6]}]},
            {"rect": [10, 1, 12, 3]},
        ]
    }
    mask = region(shape, 16, 12)
    assert mask.getpixel((2, 2)) == 255 and mask.getpixel((4, 4)) == 0
    assert mask.getpixel((11, 2)) == 255 and mask.getpixel((8, 2)) == 0
    assert region(
        {"intersection": [{"rect": [0, 0, 4, 4]}, {"rect": [2, 2, 6, 6]}]}, 8, 8
    ).getbbox() == (2, 2, 4, 4)
    concave = region(
        {"polygon": [[0, 0], [7, 0], [7, 2], [2, 2], [2, 7], [0, 7]]}, 8, 8
    )
    assert concave.getpixel((1, 5)) == 255 and concave.getpixel((5, 5)) == 0
    for shape in (
        {"rect": [0, 0, 0, 2]},
        {"rect": [0, 0, True, 2]},
        {"subtract": [{"rect": [1, 1, 2, 2]}, {"rect": [0, 0, 3, 3]}]},
    ):
        with pytest.raises(ValueError):
            region(shape, 8, 8)


@pytest.fixture
def mouse_game(tmp_path):
    # Mode 13h; reset mouse; poll BX button bit; paint VGA pixel zero red on
    # the first real mouse press. No GUI/decoder replacement or host RAM edit.
    code = bytes.fromhex(
        "b81300cd1031c0cd33b80300cd33f7c3010074f5b800a08ec026c606000004ebfe"
    )
    game = tmp_path / "game"
    game.mkdir()
    binary = game / "SCENE.EXE"
    binary.write_bytes(mz_file(code + bytes(1024), ss=0, sp=0x400))
    path = tmp_path / "scene.fdb"
    with Project.create(path, binary) as p:
        p.analyze(max_instructions=30)
    return path, binary


def pixel(rgb):
    return {"pixels": {"samples": [{"x": 0, "y": 0, "rgb": rgb}]}}


def definition(snapshot):
    return dict(
        format="fdisbull-scene-1",
        width=320,
        height=200,
        mode_id=snapshot["metadata"]["mode_id"],
        reference=snapshot["artifact"],
        context=dict(
            state="waiting for a mouse press",
            triggers=["authored guest initialization"],
        ),
        match=pixel([0, 0, 0]),
        objects=[
            dict(
                name="test.button",
                context=dict(
                    state="input control", triggers=["mouse driver initialized"]
                ),
                original_area={"rect": [1, 1, 30, 30]},
                area={
                    "subtract": [{"rect": [1, 1, 30, 30]}, {"rect": [15, 15, 25, 25]}]
                },
                point=[10, 10],
                visible=pixel([0, 0, 0]),
                ready={"memory": {"address": "1000:0100", "length": 1, "hex": "00"}},
                enabled={"constant": True},
                action={"kind": "click"},
                outcome=pixel([170, 0, 0]),
                guest_ms=1000,
                timeout_ms=3000,
            )
        ],
    )


def test_real_probe_mask_action_outcome_and_restart(mouse_game, emulator, tmp_path):
    path, binary = mouse_game
    with Project(path) as p, p.debugger(emulator, binary.parent) as d:
        d.run(guest_ms=100, timeout_ms=3000, fast_forward=True)
        probe = d.frame_probe([[0, 0], [319, 199]])
        assert [s["rgb"] for s in probe["samples"]] == [[0, 0, 0], [0, 0, 0]]
        assert (
            "png_base64" not in probe
            and probe["source"] == "last_completed_guest_frame"
        )
        snapshot = d.screenshot()
        scene = p.debug_save_scene("test", definition(snapshot))
        revision = scene["id"]
        oid = scene["definition"]["objects"][0]["id"]
        assert scene["definition"]["objects"][0]["original_area"] == {
            "rect": [1, 1, 30, 30]
        }
        assert d.scene(revision).object("test.button").exists()
        checkpoint = d.save_state("before-click.sav")
        overlay = p.debug_scene_overlay(revision)
        p.debug_export(overlay["artifact"], tmp_path / "overlay.png")
        with Image.open(tmp_path / "overlay.png") as rendered:
            assert rendered.size == (320, 200)
        report = d.script(
            {
                "format": "fdisbull-script-1",
                "steps": [
                    {
                        "op": "scene-click",
                        "scene": revision,
                        "object": "test.button",
                        "as": "action",
                    },
                    {"op": "assert", "value": "$action.status", "equals": "matched"},
                ],
            },
            timeout_ms=120000,
        )
        assert report["ok"], report
        assert d.frame_probe([[0, 0]])["samples"][0]["rgb"] == [170, 0, 0]
        stale = probe["frame_id"]
        with pytest.raises(Exception, match="changed|STALE"):
            d.click(10, 10, frame_id=stale)
        d.load_state(checkpoint["artifact"])
        assert d.scene_check(revision)["status"] == "unavailable"
        d.run(guest_ms=100, timeout_ms=3000, fast_forward=True)
        assert d.scene_assert(revision)["status"] == "matched"
        first_pid = d.rpc.process.pid
    assert d.rpc.process.poll() is not None
    with Project(path) as p:
        saved = p.debug_scene_info(revision)
        assert saved["definition"]["objects"][0]["id"] == oid
        regenerated = p.debug_scene_overlay(revision, grid_step=None)
        assert regenerated["metadata"]["source_sha256"] == snapshot["sha256"]
        with p.debugger(emulator, binary.parent) as d:
            assert d.rpc.process.pid != first_pid
            d.load_state(checkpoint["artifact"])
            d.run(guest_ms=100, timeout_ms=3000, fast_forward=True)
            assert d.scene_assert(revision)["status"] == "matched"
        # Scene evidence is never implicitly inherited into a patched byte view.
        child = p.patch(address="0x10000", data="90")
        with pytest.raises(ValueError, match="byte version"):
            p.debug_scene_info(revision, version=child["version"])
        assert p.debug_scene_info(revision, version=1)["id"] == revision


def test_real_availability_collisions_revision_history_and_stop(
    mouse_game, emulator, tmp_path
):
    path, binary = mouse_game
    with Project(path) as p, p.debugger(emulator, binary.parent) as d:
        d.run(guest_ms=100, timeout_ms=3000, fast_forward=True)
        doc = definition(d.screenshot())
        doc["objects"][0]["ready"] = {"constant": False}
        first = p.debug_save_scene("test", doc)
        before = len(
            [e for e in p.debug_events(d.run_id)["events"] if e["operation"] == "click"]
        )
        with pytest.raises(SceneError) as rejected:
            d.scene_click(first["id"], "test.button")
        assert rejected.value.result["availability"]["ready"] is False
        assert rejected.value.result["snapshot"] and rejected.value.result["overlay"]
        assert (
            len(
                [
                    e
                    for e in p.debug_events(d.run_id)["events"]
                    if e["operation"] == "click"
                ]
            )
            == before
        )
        modified = deepcopy(first["definition"])
        modified["objects"][0]["ready"] = {"constant": True}
        modified["objects"][0]["name"] = "test.renamed"
        second = p.debug_save_scene("test", modified, parent=first["id"])
        assert (
            second["definition"]["objects"][0]["id"]
            == first["definition"]["objects"][0]["id"]
        )
        assert (
            p.debug_scene_info(first["id"])["definition"]["objects"][0]["name"]
            == "test.button"
        )
        with pytest.raises(ValueError, match="current revision"):
            p.debug_save_scene("test", modified, parent=first["id"])
        competitor = p.debug_save_scene("ambiguous", definition(d.screenshot()))
        with pytest.raises(SceneError) as collision:
            d.scene_assert(second["id"])
        assert (
            collision.value.result["status"] == "ambiguous"
            and collision.value.result["snapshot"]
        )
        assert (
            collision.value.result["conflicts"][0]["scene_revision"] == competitor["id"]
        )
        off = deepcopy(competitor["definition"])
        off["match"] = {"constant": False}
        p.debug_save_scene("ambiguous", off, parent=competitor["id"])
        assert d.scene_assert(second["id"])["status"] == "matched"
        # The polling instruction may already be the paused PC. Resuming at a
        # breakpoint there can legitimately step over it and immediately take
        # the click path. Pin that pause position, then break on the unavoidable
        # post-click instruction before the guest paints the success pixel.
        loop = d.breakpoint("1000:0009")
        assert d.run(timeout_ms=3000, fast_forward=True)["outcome"] == "breakpoint"
        d.delete_breakpoint(loop["breakpoint_id"])
        bp = d.breakpoint("1000:0014")
        assert bp["bytes_verified"]
        with pytest.raises(SceneError) as stopped:
            d.scene_click(second["id"], "test.button")
        assert stopped.value.result["status"] == "stopped"
        assert stopped.value.result["stop"]["outcome"] == "breakpoint"
        d.delete_breakpoint(bp["breakpoint_id"])
        assert any(
            x["kind"] == "ambiguous"
            for x in p.debug_scene_observations()["observations"]
        )
        bad = deepcopy(second["definition"])
        bad["objects"][0]["point"] = [20, 20]
        with pytest.raises(ValueError, match="outside"):
            p.debug_save_scene("test", bad, parent=second["id"])


def test_real_wait_initial_timeout_and_missing_capture(mouse_game, emulator):
    path, binary = mouse_game
    with Project(path) as p, p.debugger(emulator, binary.parent) as d:
        d.run(guest_ms=100, timeout_ms=3000, fast_forward=True)
        scene = p.debug_save_scene("test", definition(d.screenshot()))
        result = d.scene_wait(scene["id"], guest_ms=100, timeout_ms=3000)
        assert result["guest_elapsed_ms"] == 0 and len(result["polls"]) == 1
        before = d.frame_probe([])
        with pytest.raises(Exception):
            d.call("video.probe", {"points": [[0, 0], [320, 200]]})
        after = d.frame_probe([])
        assert (
            before["frame_id"] == after["frame_id"]
            and before["state_revision"] == after["state_revision"]
        )
        off = deepcopy(scene["definition"])
        off["objects"][0]["ready"] = {"constant": False}
        waiting = p.debug_save_scene("test", off, parent=scene["id"])
        with pytest.raises(SceneError) as failure:
            d.scene_wait(
                waiting["id"],
                object="test.button",
                guest_ms=30,
                timeout_ms=3000,
                slice_ms=10,
            )
        assert (
            failure.value.result["status"] == "timeout"
            and not failure.value.result["complete"]
        )
        assert (
            failure.value.result["snapshot"]
            and failure.value.result["availability"]["ready"] is False
        )
        d.rpc.capabilities["video"]["pixel_probe"] = False
        with pytest.raises(SceneError) as unavailable:
            d.scene_click(scene["id"], "test.button")
        assert (
            unavailable.value.result["status"] == "unavailable"
            and not unavailable.value.result["complete"]
        )
        d.rpc.capabilities["video"]["pixel_probe"] = True
        missing = deepcopy(scene["definition"])
        missing["objects"][0]["ready"] = {
            "memory": dict(address="0x0", length=1, hex="00")
        }
        missing["handlers"] = [
            dict(
                name="known",
                when={"constant": True},
                action={"kind": "click"},
                point=[10, 10],
                outcome={"constant": False},
            )
        ]
        blocked = p.debug_save_scene("test", missing, parent=waiting["id"])
        with pytest.raises(SceneError) as absent:
            d.scene_click(blocked["id"], "test.button", handle_popups=True)
        assert absent.value.result["status"] == "unavailable"
        assert d.frame_probe([[0, 0]])["samples"][0]["rgb"] == [0, 0, 0]


def test_bundled_investigation_skill_is_readable_without_project():
    from fdisbull.cli import invoke, respond

    result = invoke("agent-skill", {})
    assert result["name"] == "fdisbull-investigate"
    assert set(result["files"]) == {
        "SKILL.md",
        "references/scenes.md",
        "references/methodology.md",
        "references/runtime-navigation.md",
        "references/proofs.md",
        "references/workflows.md",
        "references/udl-uil-udc.md",
        "references/recovery-research.md",
        "references/semantic-contracts.md",
        "references/formats-and-media.md",
        "references/media-modules.md",
        "references/binary-claim-verification.md",
    }
    local_links = {
        target
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", result["files"]["SKILL.md"])
        if "://" not in target and not target.startswith("#")
    }
    assert local_links <= set(result["files"])
    assert respond(
        {"method": "agent-skill", "params": {"index": True}},
        default_project="/nonexistent-project",
    )["ok"]


def test_bundled_skill_selective_read_and_invalid_paths(capsys):
    from fdisbull.cli import invoke, main, respond

    full = invoke("agent-skill", {})
    for path in full["files"]:
        selected = invoke("agent-skill", {"reference": path})
        assert selected["files"] == {path: full["files"][path]}
    assert main(["agent-skill", "--reference", "SKILL.md"]) == 0
    assert set(json.loads(capsys.readouterr().out)["result"]["files"]) == {"SKILL.md"}
    for path in ("../pyproject.toml", "/etc/passwd", "references/missing.md", [], True):
        assert not respond({"method": "agent-skill", "params": {"reference": path}})[
            "ok"
        ]
    assert not respond({"method": "agent-skill", "params": {"unknown": "field"}})["ok"]


def test_real_named_keyboard_action_requires_a_new_outcome(keyboard_game, emulator):
    path, binary = keyboard_game
    with Project(path) as p, p.debugger(emulator, binary.parent) as d:
        d.run(guest_ms=100, timeout_ms=3000, fast_forward=True)
        frame = d.screenshot()
        meta = frame["metadata"]
        obj = dict(
            name="name.letter",
            context=dict(
                state="BIOS name entry", triggers=["authored fixture waits in INT16"]
            ),
            area={"rect": [1, 1, 8, 8]},
            point=[4, 4],
            visible={"constant": True},
            ready={"constant": True},
            enabled={"constant": True},
            action={"kind": "press", "key": "a"},
            outcome={"memory": dict(address="1000:0100", length=2, hex="611e")},
        )
        doc = dict(
            format="fdisbull-scene-1",
            width=meta["width"],
            height=meta["height"],
            mode_id=meta["mode_id"],
            reference=frame["artifact"],
            context=dict(state="keyboard fixture", triggers=["startup"]),
            match={"constant": True},
            objects=[obj],
        )
        saved = p.debug_save_scene("keyboard", doc)
        report = d.script(
            {
                "format": "fdisbull-script-1",
                "steps": [
                    {"op": "scene-act", "scene": saved["id"], "object": "name.letter"}
                ],
            }
        )
        assert report["ok"], report
        assert d.memory("1000:0100", length=2)["hex"] == "611e"
        with pytest.raises(SceneError) as already:
            d.scene_act(saved["id"], "name.letter")
        assert already.value.result["status"] == "outcome-already-matched"
