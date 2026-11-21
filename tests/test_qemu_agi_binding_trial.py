"""Authored geometry/catalog and source-to-native binding packet contracts."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native/qemu-agi"))
from binding_catalog import decode_catalog, encode_catalog
from binding_scene_trial import collect, prepare_case, validate_binding, validate_journal
from harness import HarnessError
from fdisbull_core.agi_scene import AGISceneConsumer, SceneInputError


VIEW = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 2, 2, 15, 0x11, 0x21, 0, 0x31, 0])


def test_catalog_exact_bytes_and_resource_identity():
    expected = b"FDBAGIV1\x24\0\x01\0\x07\x01" + bytes.fromhex(sha256(VIEW).hexdigest()) + b"\x01\x02\x02"
    assert encode_catalog({7: VIEW}, horizon=36) == expected
    assert decode_catalog(expected) == {
        "profile": "agi-2917-view-binding-pilot-1", "sha256": sha256(expected).hexdigest(),
        "horizon": 36, "views": {7: {"sha256": sha256(VIEW).hexdigest(),
                                    "loops": [[{"width": 2, "height": 2}]]}}}
    assert encode_catalog({8: VIEW, 1: VIEW}, horizon=0) == encode_catalog({1: VIEW, 8: VIEW}, horizon=0)


@pytest.mark.parametrize("views,horizon", [({}, 36), ({True: VIEW}, 36), ({256: VIEW}, 36),
    ({0: VIEW}, True), ({0: VIEW}, -1), ({0: VIEW}, 168), ({0: VIEW[:-1]}, 36)])
def test_catalog_builder_refuses_invalid_ids_seed_and_payload(views, horizon):
    with pytest.raises(ValueError):
        encode_catalog(views, horizon=horizon)


@pytest.mark.parametrize("mutate", [lambda c: c[:-1], lambda c: c + b"\0",
    lambda c: b"badmagic" + c[8:], lambda c: c[:9] + b"\x01" + c[10:],
    lambda c: c[:8] + b"\xa8" + c[9:], lambda c: c[:10] + b"\0\0" + c[12:],
    lambda c: c[:13] + b"\0" + c[14:], lambda c: c[:-2] + b"\0\x02",
    lambda c: c[:-1] + b"\xa9"])
def test_catalog_reader_rejects_malformed_structure(mutate):
    with pytest.raises(ValueError):
        decode_catalog(mutate(encode_catalog({0: VIEW}, horizon=36)))


def test_catalog_reader_rejects_duplicate_ids():
    catalog = encode_catalog({0: VIEW}, horizon=36)
    with pytest.raises(ValueError, match="ascend"):
        decode_catalog(catalog[:10] + b"\x02\0" + catalog[12:] * 2)


@pytest.fixture
def authored(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    code = bytes((33, 1, 41, 1, 0, 37, 1, 7, 9, 35, 1, 0))
    logic = len(code).to_bytes(2, "little") + code + b"\0\x03\0"
    volume = bytearray()
    for directory, payload in (("LOGDIR", logic), ("PICDIR", b"\xff"), ("VIEWDIR", VIEW)):
        (game / directory).write_bytes(len(volume).to_bytes(3, "big"))
        volume.extend(b"\x12\x34\0" + len(payload).to_bytes(2, "little") + payload)
    (game / "SNDDIR").write_bytes(b"")
    (game / "VOL.0").write_bytes(volume)
    return game, {"id": "authored", "logic": 0, "picture": 0, "payload_span": [2, 13],
                  "views": [0], "actors": [1], "horizon": 36, "stop_opcode": 35}


def test_preparation_has_no_manual_pose_and_preserves_contiguous_source(authored):
    game, case = authored
    value = prepare_case(game, case)
    assert value["code"] == bytes((30, 0, 33, 1, 41, 1, 0, 37, 1, 7, 9, 35, 1, 0))
    assert [site["payload_offset"] for site in value["sites"]] == [2, 4, 7, 11]
    assert [site["fragment_pc"] for site in value["sites"]] == [2, 4, 7, 11]
    assert value["mapping"]["copied_fragment_span"] == [2, 13]
    assert value["mapping"]["authored_original_source_address"] is None
    assert value["mapping"]["containing_logic_executed"] is False
    assert value["cels"][0]["source_sha256"] == sha256(VIEW).hexdigest()
    assert value["cels"][0]["asset"] == "view-000-loop-000-cel-000.idx"


@pytest.mark.parametrize("field,value", [("payload_span", [3, 13]), ("payload_span", [2, 12]),
    ("payload_span", [2, 14]), ("stop_opcode", 70), ("views", [0, 0]), ("actors", [True]),
    ("horizon", 168), ("loop", 0), ("id", "../escape")])
def test_invalid_case_rejected_before_native(authored, field, value):
    game, case = authored
    with pytest.raises(ValueError):
        prepare_case(game, {**case, field: value})


def test_existing_collection_not_overwritten(authored, tmp_path):
    game, case = authored
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "preserve"
    marker.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        collect(tmp_path / "no-binary", game, target, case)
    assert marker.read_bytes() == b"keep" and len(list(target.iterdir())) == 1


def journal_fixture():
    """Hand-authored load/animate transitions, independent of the collector."""
    actor = {"x": 0, "y": 0, "prev_x": 0, "prev_y": 0, "view_bound": False,
             "view": 0, "loop": 0, "cel": 0, "width": 0, "height": 0,
             "animated": False, "update": False, "cycling": False,
             "ignore_horizon": False, "update_pos": False, "view_replaced": False,
             "motion": "normal", "cycle": "normal", "direction": 0}
    actors = [{"id": i, **actor} for i in range(16)]
    initial = {"guest": {"actors": actors, "loaded_views": []}}
    state = {"source": {"sha256": "a" * 64}, "guest": deepcopy(initial["guest"]),
             "observation": {"epoch": 2, "control_generation": 3, "mask": 3,
                             "dropped": 0, "count": 4, "eligible": 4,
                             "per_channel": {"disasm": {"eligible": 2, "stored": 2, "dropped": 0},
                                             "scene": {"eligible": 2, "stored": 2, "dropped": 0}}}}
    after = {**actor, "animated": True, "update": True, "cycling": True}
    state["guest"]["actors"][1] = {"id": 1, **after}
    state["guest"].update(loaded_views=[0], retired=2)
    first = {"control_generation": 3, "pc": 0, "opcode": 30, "bytes": [30, 0],
             "next_pc": 2, "retired": 1}
    second = {"control_generation": 3, "pc": 2, "opcode": 33, "bytes": [33, 1],
              "next_pc": 4, "retired": 2}
    events = {"schema": "fdisbull-agi-binding-events-1", "source": deepcopy(state["source"]),
              "epoch": 2, "events": [
                  {**first, "seq": 1, "kind": "retire"},
                  {**first, "seq": 2, "kind": "view_load", "view": 0, "before": False, "after": True},
                  {**second, "seq": 3, "kind": "retire"},
                  {**second, "seq": 4, "kind": "actor", "actor": 1, "before": actor, "after": after}]}
    inputs = {"code": bytes([30, 0, 33, 1, 35, 1, 0]), "prelude": bytes([30, 0]),
              "sites": [{"fragment_pc": 2, "opcode": 33, "bytes": [33, 1]},
                        {"fragment_pc": 4, "opcode": 35, "bytes": [35, 1]}]}
    return initial, state, events, inputs


def test_journal_reconstructs_all_actors_and_loaded_membership():
    initial, state, events, inputs = journal_fixture()
    assert validate_journal(initial, state, events, **inputs) == {
        "retired_sites": 2, "scene_transitions": 2, "journal_records": 4,
        "all_actors_and_loaded_views_match": True}


@pytest.mark.parametrize("damage", ["empty", "missing_middle", "disconnected", "wrong_bytes",
                                    "wrong_generation", "wrong_count", "missing_retire",
                                    "wrong_channels", "wrong_final_actor", "wrong_epoch"])
def test_journal_refuses_gaps_even_when_dropped_is_zero(damage):
    initial, state, events, inputs = journal_fixture()
    if damage == "empty":
        events["events"] = []
    elif damage in ("missing_middle", "missing_retire"):
        events["events"].pop(1 if damage == "missing_middle" else 2)
    elif damage == "disconnected":
        events["events"][-1]["before"]["x"] = 7
    elif damage == "wrong_bytes":
        events["events"][0]["bytes"] = [30, 1]
    elif damage == "wrong_generation":
        events["events"][0]["control_generation"] = 1
    elif damage == "wrong_count":
        state["observation"]["count"] += 1
    elif damage == "wrong_channels":
        state["observation"]["per_channel"]["disasm"]["stored"] = 1
    elif damage == "wrong_final_actor":
        state["guest"]["actors"][7]["x"] = 6
    else:
        events["epoch"] = 3
    if damage in ("empty", "missing_middle", "missing_retire"):
        # Even plausible rewritten counts and sequence numbers cannot establish
        # the missing retired instructions or semantic transitions.
        for sequence, event in enumerate(events["events"], 1):
            event["seq"] = sequence
        state["observation"].update(count=len(events["events"]), eligible=len(events["events"]))
    with pytest.raises(HarnessError):
        validate_journal(initial, state, events, **inputs)


def test_native_packet_binds_pose_and_reports_unretired_draw(authored, tmp_path):
    configured = os.environ.get("FDISBULL_QEMU_AGI_BINDING")
    if not configured:
        pytest.skip("requires explicit FDISBULL_QEMU_AGI_BINDING")
    game, case = authored
    before = {p.name: p.read_bytes() for p in game.iterdir()}
    output = tmp_path / "collection"
    report = collect(configured, game, output, case)
    packet = json.loads((output / "helper/packet.json").read_text())
    assert report["status"] == "completed" and report["inputs_unchanged"] is True
    assert report["expected_retired"] == 4
    assert packet["stop_boundary"]["retired"] is False
    assert packet["stop_boundary"]["committed"] is False
    assert packet["stop_boundary"]["opcode"] == 35
    assert packet["entry"]["original_room_checkpoint"] is False
    complete_code = (bytes(packet["entry"]["load_prologue_bytes"])
                     + bytes(value for site in packet["sites"] for value in site["bytes"])
                     + bytes(packet["entry"]["authored_return_bytes"]))
    assert sha256(complete_code).hexdigest() == packet["native"]["snapshot"]["source"]["sha256"]
    assert set(packet["documents"]) == {"README.md", "VIEW_BINDING_PROFILE.md"}
    for name, identity in packet["documents"].items():
        data = (output / "helper" / name).read_bytes()
        assert identity == {"file": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}
    actor = packet["native"]["snapshot"]["guest"]["actors"][1]
    assert (actor["view"], actor["loop"], actor["cel"], actor["width"], actor["height"]) == (0, 0, 0, 2, 2)
    assert (actor["x"], actor["y"], actor["prev_x"], actor["prev_y"]) == (7, 9, 7, 9)
    with pytest.raises(SceneInputError, match="schema"):
        AGISceneConsumer.from_snapshot(report["final_state"], session_id="binding-compatibility-check")
    prepared = prepare_case(game, case)
    for mutation in ("profile", "geometry", "loaded", "actor"):
        state = deepcopy(report["final_state"])
        if mutation == "profile":
            state["source"]["profile"] = "agi-2917-scalar-position-pilot-1"
        elif mutation == "geometry":
            state["guest"]["actors"][1]["width"] = 3
        elif mutation == "loaded":
            state["guest"]["loaded_views"] = []
        else:
            del state["guest"]["actors"][1]["view_bound"]
        with pytest.raises(HarnessError):
            validate_binding(state, code=prepared["code"], catalog=prepared["catalog"])
    assert before == {p.name: p.read_bytes() for p in game.iterdir()}
