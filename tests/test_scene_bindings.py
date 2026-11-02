"""Adversarial source-correspondence checks using only authored miniature data.

Real R88 whole-package validation and route comparisons are private integration
checks. These fixtures exercise the independent consumer's dependency and field
checks without distributing that story, its narrative, or a derived package.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.scene_bindings import (
    SourceReader, Witnesses, _dispatch_shape, _operations, _scene_bindings,
    validate_package,
)
from fdisbull_player.scene_intents import FORMAT as SCENE_FORMAT, validate_uil
from fdisbull_player.word16 import Word16Error
from test_zork_scenes import scene_image


def fixture_bindings(image):
    """Bind the authored hall, garden and gate, with every exit record form."""
    def word(at): return int.from_bytes(image[at:at + 2], "big")
    records = {}
    for number, identity in ((1, "hall"), (2, "garden"), (3, "gate")):
        record = 64 + 62 + 9 * (number - 1)
        table = word(record + 7)
        end = table + 1 + 2 * image[table]
        cursor, properties, headers = end, {}, []
        while image[cursor]:
            number_, size = image[cursor] & 31, (image[cursor] >> 5) + 1
            properties[number_] = (cursor + 1, size)
            headers.append((cursor, cursor + 1))
            cursor += 1 + size
        records[identity] = (number, record, table, end, properties,
                             [(record + 7, record + 9), (table, table + 1), *headers, (cursor, cursor + 1)])
    ir = {"memory": {"initial": image.hex(), "writable_end": 600},
          "layout": {"objects": 64, "globals": 32, "abbreviations": 600, "dictionary": 1200},
          "blocks": {
              "903": {"guard": image[903:904].hex(), "next": 904, "nodes": [{"op": "return", "value": 1}]},
              "904": {"guard": image[904:905].hex(), "next": 905, "nodes": [{"op": "emit", "value": "\n"}]},
              "905": {"guard": image[905:906].hex(), "next": 906, "nodes": [{"op": "return", "value": 0}]},
          }, "functions": {"900": {"entry": 903, "locals": [7], "guard": image[900:903].hex()}}}
    source = SourceReader(ir)
    witnesses = {}
    def guard(name, spans):
        names = []
        for index, (start, end) in enumerate(spans):
            identity = f"{name}.{index}"
            raw = image[start:end]
            witnesses[identity] = {"start": start, "end": end, "bytes": raw.hex(),
                                   "sha256": hashlib.sha256(raw).hexdigest()}
            names.append(identity)
        return names
    text, text_reads = source.text(700)
    uil = {"format": SCENE_FORMAT, "id": "authored.hall-and-garden", "entry_scene": "hall",
           "resources": {name: text for name in ("default_blocked", "default_closed_prefix", "default_closed_suffix", "wall")},
           "scenes": {"hall": {"name": "hall", "exits": {}}, "garden": {"name": "garden", "exits": {}}},
           "facts": {"passage_enabled": {"type": "boolean", "initial": False}},
           "doors": {"gate": {"name": "gate", "initial_open": False}},
           "handlers": {"authored_exit": {"representation": "low_level_ir", "role": "exit"},
                        "missing_direction": {"representation": "low_level_ir", "role": "exit"}},
           "missing_exit": "missing_direction"}
    uil["resources"]["newline"] = "\n"
    direction_names = ["north", "east", "west", "south", "northeast", "northwest", "southeast",
                       "southwest", "up", "down", "in", "out", "land"]
    udl = {"scenes": {}, "facts": {}, "doors": {}, "resources": {}, "handlers": {}, "exits": {},
           "selection": {"direction_properties": dict(zip(direction_names, range(31, 18, -1)))}}
    for identity in ("hall", "garden"):
        number, record, table, end, props, spans = records[identity]
        _, reads = source.text(table + 1, end)
        udl["scenes"][identity] = {"object": number, "record": record, "property_table": table,
            "structure_guards": guard(identity + ".structure", spans),
            "name_dependencies": guard(identity + ".name", reads), "exits": {}}
    udl["facts"]["passage_enabled"] = {"global": 16, "address": 32, "initial_value": 0,
        "interpretation": "nonzero", "mutable": True, "source_operation": 1000,
        "witness": guard("fact", [(32, 34)])[0]}
    number, record, table, end, _, spans = records["gate"]
    _, reads = source.text(table + 1, end)
    udl["doors"]["gate"] = {"object": number, "record": record, "attribute": 11,
        "address": record + 1, "mask": 16, "mutable": True, "source_operation": 1001,
        "structure_guards": guard("gate.structure", spans), "name_dependencies": guard("gate.name", reads)}
    for name in uil["resources"]:
        udl["resources"][name] = ({"source_operation": 904, "dependencies": guard("newline", [(904, 905)])}
            if name == "newline" else {"address": 700, "dependencies": guard(name + ".text", text_reads)})
    udl["handlers"]["authored_exit"] = {"kind": "routine", "packed": 450, "header": 900,
        "entry": 903, "locals": [7], "guard_witnesses": guard("routine.header", [(900, 903)])}
    udl["handlers"]["missing_direction"] = {"kind": "source_region", "entry": 905, "end": 906,
        "guard_witnesses": guard("missing.body", [(905, 906)])}
    rules = {
        "north": {"kind": "direct", "destination": "garden"},
        "east": {"kind": "blocked", "failure_resource": "wall"},
        "west": {"kind": "routine", "residual": "authored_exit"},
        "south": {"kind": "conditional", "destination": "garden", "fact": "passage_enabled"},
        "northeast": {"kind": "door", "destination": "garden", "door": "gate"},
    }
    for direction, rule in rules.items():
        identity = "hall.exit." + direction
        rule["id"] = identity
        prop = udl["selection"]["direction_properties"][direction]
        address, size = records["hall"][4][prop]
        row = {"scene": "hall", "direction": direction, "property": prop, "address": address,
               "header": address - 1, "size": size, "bytes": image[address:address + size].hex(),
               "guard_witnesses": [*udl["scenes"]["hall"]["structure_guards"],
                                   *guard(identity, [(address - 1, address + size)])]}
        if size in (1, 4, 5): row["destination"] = 2
        if size in (4, 5): row["failure_packed"] = 0
        if size == 4: row["fact"] = "passage_enabled"
        if size == 5: row["door"] = "gate"
        if size == 3: row["handler"] = "authored_exit"
        uil["scenes"]["hall"]["exits"][direction] = rule
        udl["exits"][identity] = row
        udl["scenes"]["hall"]["exits"][direction] = identity
    validate_uil(uil)
    return source, uil, udl, witnesses


def test_authored_all_five_exit_forms_pass_independent_source_binding_checks(scene_image):
    source, uil, udl, witnesses = fixture_bindings(scene_image)
    assert _scene_bindings(source, uil, udl, Witnesses(source, witnesses)) == {1: "hall", 2: "garden"}


@pytest.mark.parametrize("mutate", [
    lambda u, d: u["scenes"]["hall"]["exits"]["north"].update(destination="hall"),
    lambda u, d: d["exits"]["hall.exit.north"].update(destination=1),
    lambda u, d: d["exits"]["hall.exit.north"].update(address=200),
    lambda u, d: d["exits"]["hall.exit.north"].update(guard_witnesses=[]),
    lambda u, d: d["scenes"]["hall"].update(structure_guards=[]),
    lambda u, d: d["scenes"]["hall"].update(name_dependencies=[]),
    lambda u, d: d["scenes"]["garden"].update(object=1),
    lambda u, d: u["scenes"]["garden"].update(name="wrong room"),
    lambda u, d: u["scenes"]["hall"]["exits"].pop("east"),
    lambda u, d: u["scenes"]["hall"]["exits"]["south"].update(kind="direct"),
    lambda u, d: d["facts"]["passage_enabled"].update(global_=17),  # unused metadata must not alter valid semantics
    lambda u, d: d["facts"]["passage_enabled"].update(address=34),
    lambda u, d: d["facts"]["passage_enabled"].update(mutable=False),
    lambda u, d: u["facts"]["passage_enabled"].update(initial=True),
    lambda u, d: d["doors"]["gate"].update(attribute=12),
    lambda u, d: d["doors"]["gate"].update(mask=8),
    lambda u, d: u["doors"]["gate"].update(initial_open=True),
    lambda u, d: d["doors"]["gate"].update(name_dependencies=[]),
    lambda u, d: u["resources"].update(wall="invented text"),
    lambda u, d: d["resources"]["wall"].update(dependencies=[]),
    lambda u, d: d["handlers"]["authored_exit"].update(entry=904),
    lambda u, d: d["handlers"]["authored_exit"].update(locals=[8]),
    lambda u, d: d["handlers"]["authored_exit"].update(packed=451),
    lambda u, d: d["handlers"]["missing_direction"].update(guard_witnesses=[]),
    lambda u, d: u["scenes"]["hall"].update(initial_traits={"land": True, "naturally_lit": False, "ruined": False}),
])
def test_changed_binding_is_rejected_even_when_its_own_hash_could_be_recomputed(scene_image, mutate):
    source, uil, udl, witnesses = fixture_bindings(scene_image)
    mutate(uil, udl)
    # This one unused metadata field is deliberately harmless: UDL can carry
    # additional evidence without changing executable descriptor semantics.
    if "global_" in udl["facts"]["passage_enabled"]:
        assert _scene_bindings(source, uil, udl, Witnesses(source, witnesses))
        return
    with pytest.raises(Word16Error):
        _scene_bindings(source, uil, udl, Witnesses(source, witnesses))


def test_a_guard_covering_adjacent_bytes_cannot_stand_in_for_the_dependency(scene_image):
    source, _, _, witnesses = fixture_bindings(scene_image)
    row = next(iter(witnesses.values()))
    guard = Witnesses(source, witnesses)
    name = next(iter(witnesses))
    with pytest.raises(Word16Error, match="omit"):
        guard.covers([name], [(row["end"], row["end"] + 1)])


def test_read_only_text_reader_tracks_referenced_abbreviation_bytes():
    memory = bytearray(256)
    # One abbreviation selector then padding; expansion spells 'abc'.
    memory[64:66] = (0x8000 | (1 << 10) | 5).to_bytes(2, "big")
    memory[100:102] = (80).to_bytes(2, "big")
    memory[160:162] = (0x8000 | (6 << 10) | (7 << 5) | 8).to_bytes(2, "big")
    source = SourceReader({"memory": {"initial": memory.hex(), "writable_end": 64},
                           "layout": {"abbreviations": 100}, "blocks": {}})
    text, reads = source.text(64)
    assert text == "abc"
    assert reads == [(64, 66), (100, 102), (160, 162)]
    assert isinstance(source.memory, bytes)
    with pytest.raises(TypeError):
        source.memory[64] = 0


def test_symbolic_source_inspection_does_not_execute_calls_or_writes():
    source = SourceReader({"memory": {"initial": "00" * 128, "writable_end": 64}, "layout": {},
        "blocks": {"100": {"guard": "00", "next": 101, "nodes": [
            {"op": "read_var", "index": 16, "dest": "actor"},
            {"op": "let", "name": "destination", "value": 3},
            {"op": "library", "name": "tree.insert", "args": [{"tmp": "actor"}, {"tmp": "destination"}]},
        ]}}})
    before = source.memory
    assert _operations(source, 100) == [{"op": "library", "name": "tree.insert", "args": [{"variable": 16}, 3]}]
    assert source.memory == before
    assert not hasattr(source, "frames")


@pytest.mark.parametrize("value", [None, {}, {"format": "wrong"}, {"format": "fdisbull-zork-scene-package-1"}])
def test_public_package_refuses_incomplete_envelopes_without_starting_execution(value):
    with pytest.raises(Word16Error):
        validate_package(value)


def test_player_scene_validator_imports_with_no_core_tool_installed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = """import sys
sys.path.insert(0, sys.argv[1])
from fdisbull_player.scene_bindings import SourceReader, validate_package
assert not any(name == 'fdisbull' or name.startswith('fdisbull.') for name in sys.modules)
print('standalone')
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(root / "player")],
                            cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "standalone"
