"""Authored detached-packet checks for committed cycles and pending draw."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native/qemu-agi"))
from binding_catalog import encode_catalog
from binding_scene_trial import validate_binding
from draw_intent_harness import DRAW_INTENT_PROFILE, EVENTS_SCHEMA, STATE_SCHEMA, intent_guest_state
from draw_intent_trial import (collect, prepare_intent_case, validate_intent,
                               validate_intent_journal, validate_intent_reset)
from harness import HarnessError
from visual_binding_harness import binding_guest_state


VIEW = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 2, 2, 15, 0x11, 0x21, 0, 0x31, 0])


def intent_fixture():
    """Independent stopped state for load(0), set.view(1,0), pending draw(1)."""
    code = bytes([30, 0, 41, 1, 0, 35, 1, 0])
    catalog = encode_catalog({0: VIEW}, horizon=0)
    empty = {"x": 0, "y": 0, "prev_x": 0, "prev_y": 0, "view_bound": False,
             "view": 0, "loop": 0, "cel": 0, "width": 0, "height": 0,
             "animated": False, "update": False, "cycling": False,
             "ignore_horizon": False, "update_pos": False, "view_replaced": False,
             "motion": "normal", "cycle": "normal", "direction": 0}
    actors = [{"id": i, **empty} for i in range(16)]
    actors[1].update(view_bound=True, width=2, height=2, y=1,
                     update_pos=True, view_replaced=True)
    pending = {"kind": "draw", "reason": "draw_requires_host", "pc": 5,
               "opcode": 35, "bytes": [35, 1], "actor": 1, "retired": False,
               "committed": False, "completion_available": False}
    source = {"sha256": sha256(code).hexdigest(), "size": len(code), "logic_id": 0,
              "profile": DRAW_INTENT_PROFILE, "catalog_sha256": sha256(catalog).hexdigest()}
    guest = {"pc": 5, "variables": [0] * 256, "flags": [0] * 256, "actors": actors,
             "horizon": 0, "loaded_views": [0], "status": "effect", "fault": None,
             "retired": 2, "pending_effect": pending}
    state = {"schema": STATE_SCHEMA, "source": source, "guest": guest,
             "catalog": {"sha256": sha256(catalog).hexdigest(), "size": len(catalog),
                         "view_count": 1, "loop_count": 1, "cel_count": 1, "horizon": 0}}
    return state, code, catalog


def test_pending_validation_is_source_bound_and_does_not_change_pose():
    state, code, catalog = intent_fixture()
    state["guest"]["actors"][1].update(x=255, y=255, prev_x=255, prev_y=255)
    assert validate_intent(state, code=code, catalog=catalog) == state
    copied = intent_guest_state(state)
    copied["pending_effect"]["pc"] = 0
    assert state["guest"]["pending_effect"]["pc"] == 5
    for old in (binding_guest_state,):
        with pytest.raises(HarnessError):
            old(state)
    with pytest.raises(HarnessError):
        validate_binding(state, code=code, catalog=catalog)


@pytest.mark.parametrize("damage", [None, "actor", "variable", "flag", "loaded", "pc", "retired", "fault"])
def test_explicit_reset_claim_is_validated(damage):
    state, code, catalog = intent_fixture()
    guest = state["guest"]
    guest["actors"] = [{**deepcopy(guest["actors"][0]), "id": index} for index in range(16)]
    guest.update(pc=0, retired=0, status="ready", loaded_views=[], pending_effect=None)
    if damage is None:
        assert validate_intent_reset(state, code=code, catalog=catalog) == state
        return
    if damage == "actor": guest["actors"][0]["x"] = 13
    elif damage == "variable": guest["variables"][42] = 99
    elif damage == "flag": guest["flags"][42] = 1
    elif damage == "loaded": guest["loaded_views"] = [0]
    elif damage == "pc": guest["pc"] = 1
    elif damage == "retired": guest["retired"] = 1
    else: guest["fault"] = {"code": 1}
    with pytest.raises(HarnessError, match="zero-reset"):
        validate_intent_reset(state, code=code, catalog=catalog)


@pytest.mark.parametrize("damage", ["missing", "null", "committed", "retired", "completion",
    "actor", "actor_bool", "pc", "bytes", "byte_bool", "opcode", "unbound", "geometry",
    "wrong_profile", "wrong_schema", "wrong_catalog", "wrong_source", "wrong_status", "fault", "extra"])
def test_pending_validator_rejects_forged_or_incomplete_requests(damage):
    state, code, catalog = intent_fixture()
    g, p = state["guest"], state["guest"]["pending_effect"]
    if damage == "missing": del g["pending_effect"]
    elif damage == "null": g["pending_effect"] = None
    elif damage in ("committed", "retired"): p[damage] = True
    elif damage == "completion": p["completion_available"] = True
    elif damage == "actor": p["actor"] = 2
    elif damage == "actor_bool": p["actor"] = True
    elif damage == "pc": p["pc"] = 0
    elif damage == "bytes": p["bytes"] = [35, 2]
    elif damage == "byte_bool": p["bytes"] = [35, True]
    elif damage == "opcode": p["opcode"] = 36
    elif damage == "unbound": g["actors"][1]["view_bound"] = False
    elif damage == "geometry": g["actors"][1]["width"] = 3
    elif damage == "wrong_profile": state["source"]["profile"] = "agi-2917-view-binding-pilot-1"
    elif damage == "wrong_schema": state["schema"] = "fdisbull-agi-binding-state-1"
    elif damage == "wrong_catalog": state["source"]["catalog_sha256"] = "0" * 64
    elif damage == "wrong_source": code = code[:-1] + b"\x01"
    elif damage == "wrong_status": g["status"] = "return"
    elif damage == "fault": g["fault"] = {"code": 1}
    else: p["drawn"] = True
    with pytest.raises(HarnessError):
        validate_intent(state, code=code, catalog=catalog)


@pytest.mark.parametrize("status", ["ready", "budget", "return", "fault", "external"])
def test_other_stops_require_explicit_null_pending(status):
    state, code, catalog = intent_fixture()
    state["guest"].update(status=status, pending_effect=None)
    assert validate_intent(state, code=code, catalog=catalog)["guest"]["pending_effect"] is None


def write_game(tmp_path, terminal):
    game = tmp_path / "game"
    game.mkdir()
    code = bytes((33, 1, 41, 1, 0, 37, 1, 7, 9, terminal, 1, 0))
    logic = len(code).to_bytes(2, "little") + code + b"\0\x03\0"
    volume = bytearray()
    for directory, payload in (("LOGDIR", logic), ("PICDIR", b"\xff"), ("VIEWDIR", VIEW)):
        (game / directory).write_bytes(len(volume).to_bytes(3, "big"))
        volume.extend(b"\x12\x34\0" + len(payload).to_bytes(2, "little") + payload)
    (game / "SNDDIR").write_bytes(b"")
    (game / "VOL.0").write_bytes(volume)
    case = {"id": "authored-intent", "logic": 0, "picture": 0, "payload_span": [2, 13],
            "views": [0], "actors": [1], "horizon": 36, "stop_opcode": terminal,
            "endpoint": "pending_draw" if terminal == 35 else "authored_return"}
    return game, case


@pytest.mark.parametrize("terminal", [35, 70])
def test_case_preserves_original_span_and_explicit_authored_return(tmp_path, terminal):
    game, case = write_game(tmp_path, terminal)
    p = prepare_intent_case(game, case)
    assert p["code"] == bytes((30, 0, 33, 1, 41, 1, 0, 37, 1, 7, 9, terminal, 1, 0))
    assert p["sites"][-1]["payload_offset"] == 11
    assert p["mapping"]["authored_original_source_address"] is None
    assert p["spec"]["endpoint"] == case["endpoint"]


@pytest.mark.parametrize("change", [{"endpoint": "drawn"}, {"endpoint": "authored_return"},
                                  {"stop_opcode": 70}, {"unexpected": True}, {"actors": [2]}])
def test_bad_endpoint_fails_before_native(tmp_path, change):
    game, case = write_game(tmp_path, 35)
    with pytest.raises(ValueError):
        prepare_intent_case(game, {**case, **change})


def test_existing_output_preserved(tmp_path):
    game, case = write_game(tmp_path, 35)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "marker").write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        collect(tmp_path / "no-binary", game, output, case)
    assert list(output.iterdir()) == [output / "marker"]


@pytest.mark.parametrize("terminal", [35, 70])
def test_native_intent_packet_is_self_contained_and_keeps_commitment_explicit(tmp_path, terminal):
    binary = os.environ.get("FDISBULL_QEMU_AGI_INTENT")
    if not binary:
        pytest.skip("requires explicit FDISBULL_QEMU_AGI_INTENT")
    game, case = write_game(tmp_path, terminal)
    before = {p.name: p.read_bytes() for p in game.iterdir()}
    output = tmp_path / "collection"
    report = collect(binary, game, output, case, timeout=5)
    packet = json.loads((output / "helper/packet.json").read_text())
    assert report["status"] == "completed" and report["inputs_unchanged"] is True
    assert packet["schema"] == "fdisbull-agi-draw-intent-packet-1"
    assert set(packet["documents"]) == {"README.md", "DRAW_INTENT_PROFILE.md", "VIEW_BINDING_PROFILE.md"}
    for name, identity in {**packet["assets"], **packet["documents"]}.items():
        data = (output / "helper" / name).read_bytes()
        assert identity == {"file": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}
    complete_code = (bytes(packet["entry"]["load_prologue_bytes"])
                     + bytes(x for site in packet["sites"] for x in site["bytes"])
                     + bytes(packet["entry"]["authored_return_bytes"]))
    assert sha256(complete_code).hexdigest() == packet["native"]["snapshot"]["source"]["sha256"]
    g = packet["native"]["snapshot"]["guest"]
    assert (g["actors"][1]["x"], g["actors"][1]["y"]) == (7, 9)
    assert packet["render_contract"]["establishes_visibility"] is False
    assert packet["render_contract"]["establishes_presentation"] is False
    if terminal == 35:
        assert g["retired"] == 4 and g["actors"][1]["cycling"] is True
        assert packet["draw_request"]["native_descriptor"] == g["pending_effect"]
        assert packet["draw_request"]["committed_pose"] == g["actors"][1]
        assert packet["execution_endpoint"]["retired"] is False
        assert packet["execution_endpoint"]["committed"] is False
    else:
        assert g["retired"] == 6 and g["actors"][1]["cycling"] is False
        assert packet["draw_request"] is None and g["pending_effect"] is None
        assert packet["execution_endpoint"] == {"kind": "authored_return", "fragment_pc": 13,
            "bytes": [0], "original_source_address": None, "retired": True, "committed": True}
    prepared = prepare_intent_case(game, case)
    events = deepcopy(report["events"])
    events["events"] = []
    with pytest.raises(HarnessError):
        validate_intent_journal(report["initial_state"], report["final_state"], events, prepared=prepared)
    assert before == {p.name: p.read_bytes() for p in game.iterdir()}
