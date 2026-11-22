"""Authored packages and host-boundary contracts; no original game data."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

import pytest


NATIVE = Path(__file__).resolve().parents[1] / "native/qemu-agi"


def _module(name):
    spec = importlib.util.spec_from_file_location(name, NATIVE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pack():
    return _module("runtime_pack")


def _authored(pack, **overrides):
    values = {
        "logics": [{"id": 0, "code": b"\xff", "messages": ["Hello %v1", None, "é"]}],
        "views": [{"id": 3, "data": b"opaque view"}],
        "pictures": [{"id": 3, "data": b"\xff"}],
        "sounds": [{"id": 2, "data": b"opaque sound"}],
        "words": [{"text": "take", "id": 7}, {"text": "pick up", "id": 7}],
        "objects": [{"name": "key", "room": 255}],
    }
    return pack.build_package(**(values | overrides))


def test_package_roundtrip_preserves_literal_slots_and_exact_byte_identity(pack, tmp_path):
    package = _authored(pack)
    assert set(package) == {"schema", "profile", "entry_logic", "logics",
                            "views", "pictures", "sounds", "words", "objects"}
    assert package["schema"] == "fdisbull-agi-runtime-package-1"
    assert package["profile"] == "agi-2917-runtime-1"
    assert package["logics"][0] == {
        "id": 0, "code": "ff", "sha256": sha256(b"\xff").hexdigest(),
        "messages": ["Hello %v1", None, "é"],
    }
    encoded = pack.dump_package(package)
    assert pack.load_package(encoded) == package
    path = tmp_path / "package.json"
    receipt = pack.write_package(path, package)
    assert receipt["sha256"] == sha256(path.read_bytes()).hexdigest()
    assert receipt["size"] == len(encoded)
    with pytest.raises(FileExistsError):
        pack.write_package(path, package)
    assert path.read_bytes() == encoded
    # Whitespace belongs to package identity; resource code has its own hash.
    alternate = json.dumps(package, indent=2).encode()
    assert pack.load_package(alternate) == package
    assert sha256(alternate).hexdigest() != sha256(encoded).hexdigest()


def test_duplicate_json_keys_and_resource_ids_are_refused(pack):
    package = _authored(pack)
    encoded = pack.dump_package(package)
    duplicate = encoded.replace(b'"entry_logic":0', b'"entry_logic":0,"entry_logic":0')
    with pytest.raises(ValueError, match="duplicate"):
        pack.load_package(duplicate)
    nested = encoded.replace(b'"code":"ff"', b'"code":"ff","code":"ff"')
    with pytest.raises(ValueError, match="duplicate"):
        pack.load_package(nested)
    for field in ("logics", "views", "pictures", "sounds", "words"):
        bad = deepcopy(package)
        bad[field].append(deepcopy(bad[field][0]))
        with pytest.raises(ValueError, match="duplicate"):
            pack.validate_package(bad)
    # Synonyms share IDs, but word text is the unique key.
    assert package["words"][0]["id"] == package["words"][1]["id"]


@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("sounds"),
    lambda p: p.update(variables={"0": 1}),
    lambda p: p.update(entry_logic=True),
    lambda p: p.update(entry_logic=1),
    lambda p: p.update(profile="auto"),
    lambda p: p["logics"][0].update(code="FF"),
    lambda p: p["logics"][0].update(code="f"),
    lambda p: p["logics"][0].update(sha256="0" * 64),
    lambda p: p["logics"][0].update(id=False),
    lambda p: p["logics"][0].update(messages=["zero\0byte"]),
    lambda p: p["logics"][0].update(messages=["\ud800"]),
    lambda p: p["logics"][0].update(messages=["é" * 4096]),
    lambda p: p["logics"][0].update(messages=["\U0001f600"]),
    lambda p: p["logics"][0].update(messages=[None] * 256),
    lambda p: p["pictures"][0].update(data="", sha256=sha256(b"").hexdigest()),
    lambda p: p["words"][0].update(text="Take"),
    lambda p: p["words"][0].update(text="caf\u00e9"),
    lambda p: p["words"][0].update(text="take\tkey"),
    lambda p: p["words"][0].update(text="x" * 64),
    lambda p: p["words"][0].update(id=65536),
    lambda p: p["objects"][0].update(room=True),
    lambda p: p["objects"][0].update(name="key\0"),
    lambda p: p["objects"][0].update(name="\U0001f600"),
    lambda p: p["objects"][0].update(name="─" * 256),
    lambda p: p["objects"][0].update(number=0),
])
def test_package_contract_rejects_invalid_fields_without_normalizing(pack, mutate):
    package = _authored(pack)
    mutate(package)
    with pytest.raises(ValueError):
        pack.validate_package(package)


def test_package_size_resource_and_table_bounds(pack, monkeypatch):
    package = _authored(pack, logics=[{
        "id": 0, "code": b"\0" * 65536, "messages": ["x" * 4095] * 255,
    }], views=[{"id": 0, "data": b"v" * (2 * 1024**2)}],
        objects=[{"name": "", "room": 0}] * 256)
    assert len(bytes.fromhex(package["logics"][0]["code"])) == 65536
    assert len(package["objects"]) == 256
    for values in (
        {"logics": [{"id": 0, "code": b"", "messages": []}]},
        {"logics": [{"id": 0, "code": b"\0" * 65537, "messages": []}]},
        {"views": [{"id": 0, "data": b"v" * (2 * 1024**2 + 1)}]},
        {"words": [{"text": f"word{i}", "id": i} for i in range(10001)]},
        {"objects": [{"name": "", "room": 0}] * 257},
    ):
        with pytest.raises(ValueError):
            _authored(pack, **values)
    # Exercise the same package-size gate without allocating a 64 MiB fixture.
    monkeypatch.setattr(pack, "MAX_PACKAGE_BYTES", 64)
    with pytest.raises(ValueError, match="package"):
        pack.load_package(b" " * 65)
    with pytest.raises(ValueError, match="package"):
        pack.dump_package(_minimal_package())


def _minimal_package():
    return {"schema": "fdisbull-agi-runtime-package-1", "profile": "agi-2917-runtime-1",
            "entry_logic": 0, "logics": [{"id": 0, "code": "00",
                                       "sha256": sha256(b"\0").hexdigest(), "messages": []}],
            "views": [], "pictures": [], "sounds": [], "words": [], "objects": []}


def _logic_payload(code, messages):
    strings, pointers = b"", []
    for message in messages:
        if message is None:
            pointers.append(0)
        else:
            pointers.append(2 + 2 * len(messages) + len(strings))
            strings += message + b"\0"
    key = b"Avis Durgan"
    encrypted = bytes(value ^ key[index % len(key)] for index, value in enumerate(strings))
    return (len(code).to_bytes(2, "little") + code + bytes([len(messages)])
            + (2 + 2 * len(messages) + len(strings)).to_bytes(2, "little")
            + b"".join(value.to_bytes(2, "little") for value in pointers) + encrypted)


def _v2_game(path, logics):
    volume, directory = bytearray(), bytearray()
    for logic in logics:
        directory.extend(len(volume).to_bytes(3, "big"))
        volume.extend(b"\x12\x34\0" + len(logic).to_bytes(2, "little") + logic)
    (path / "LOGDIR").write_bytes(directory)
    (path / "VOL.0").write_bytes(volume)
    for name in ("PICDIR", "VIEWDIR", "SNDDIR"):
        (path / name).write_bytes(b"")


def test_full_raw_and_v2_resource_conversion_has_no_host_opcode_decoder(pack, tmp_path, monkeypatch):
    from fdisbull import agi, agi_layout, agi_source
    from fdisbull.agi_resources import V2Resources

    def forbidden(*args, **kwargs):
        raise AssertionError("Host opcode decoding must not be used by the package adapter")

    monkeypatch.setattr(agi.AGI2917Processor, "decode", forbidden)
    monkeypatch.setattr(agi_layout, "logic_layout", forbidden)
    monkeypatch.setattr(agi_source, "boundary_evidence", forbidden)
    # Deliberately truncated IF code is valid opaque package data. Native
    # execution, rather than this host resource reader, will diagnose it.
    payload = _logic_payload(b"\xff", [b"First %v23", None, b"\x82"])
    _v2_game(tmp_path, [payload])
    store = V2Resources(tmp_path)
    package = pack.package_from_v2(store)
    assert package["logics"][0]["messages"] == ["First %v23", None, "é"]
    assert package["logics"][0]["code"] == "ff"
    assert package["logics"][0]["sha256"] == sha256(b"\xff").hexdigest()
    assert package == pack.package_from_raw(logics=[{"id": 0, "data": payload}])
    # Existing snapshots are reused, even after the explicit source is removed.
    (tmp_path / "VOL.0").unlink()
    assert pack.package_from_v2(store) == package
    with pytest.raises(pack.ResourcePackageError) as caught:
        pack.package_from_v2(tmp_path)
    assert any(item.get("id") == 0 for item in caught.value.failures)


def test_v2_reports_every_malformed_resource_without_a_partial_success(pack, tmp_path):
    _v2_game(tmp_path, [_logic_payload(b"\0", []), b"\x01\0\0", b"\x01\0\0"])
    (tmp_path / "SNDDIR").write_bytes(b"\0")  # malformed directory
    (tmp_path / "WORDS.TOK").write_bytes(b"invalid")
    with pytest.raises(pack.ResourcePackageError) as caught:
        pack.package_from_v2(tmp_path)
    failures = caught.value.failures
    assert {item["id"] for item in failures if "id" in item} == {1, 2}
    assert {"sound", "words", "logic"} == {item["kind"] for item in failures}
    with pytest.raises(pack.ResourcePackageError) as raw:
        pack.package_from_raw(logics=[{"id": 2, "data": b"bad"},
                                     {"id": 3, "data": b"bad"}])
    assert [item["id"] for item in raw.value.failures] == [2, 3]


def test_v2_auxiliary_tables_keep_synonyms_phrases_and_inventory_order(pack, tmp_path):
    _v2_game(tmp_path, [_logic_payload(b"\0", [])])
    words = bytearray(52)
    for word, number in (("ignore", 0), ("take", 7), ("pick up", 7)):
        encoded = bytearray(ord(char) ^ 0x7f for char in word)
        encoded[-1] |= 0x80
        words.extend(b"\0" + encoded + number.to_bytes(2, "big"))
    (tmp_path / "WORDS.TOK").write_bytes(words)
    plain = b"\x06\0\x10\x06\0\xff\x0a\0\x03key\0book\0"
    key = b"Avis Durgan"
    (tmp_path / "OBJECT").write_bytes(bytes(value ^ key[index % 11]
                                           for index, value in enumerate(plain)))
    package = pack.package_from_v2(tmp_path)
    assert package["words"] == [{"text": "ignore", "id": 0}, {"text": "take", "id": 7},
                                {"text": "pick up", "id": 7}]
    assert package["objects"] == [{"name": "key", "room": 255}, {"name": "book", "room": 3}]


def test_package_file_read_is_bounded_and_rejects_non_json_numbers(pack, tmp_path, monkeypatch):
    for data in (b'{"x":NaN}', b'{"x":Infinity}', b"\xff", b"[]"):
        with pytest.raises(ValueError):
            pack.load_package(data)
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * 65)
    monkeypatch.setattr(pack, "MAX_PACKAGE_BYTES", 64)
    with pytest.raises(ValueError, match="package"):
        pack.read_package_bytes(path)


@pytest.fixture(scope="module")
def runtime(pack):
    return _module("runtime_harness")


@pytest.fixture(scope="module")
def services(runtime):
    return _module("runtime_services")


@pytest.fixture
def boundary(runtime, pack):
    class NativeBoundary(runtime.QemuAGIRuntime):
        """Fake only the QOM boundary; never decode or execute a guest program."""

        def __init__(self):
            self.package = pack.build_package(logics=[
                {"id": 0, "code": bytes(range(128)), "messages": []},
                {"id": 1, "code": b"\0", "messages": []},
            ])
            self.package_bytes = pack.dump_package(self.package)
            self.package_sha256 = sha256(self.package_bytes).hexdigest()
            self.package_size = len(self.package_bytes)
            self.binary_sha256 = "b" * 64
            self._logic_hashes = {r["id"]: r["sha256"] for r in self.package["logics"]}
            self._logic_sizes = {r["id"]: len(r["code"]) // 2 for r in self.package["logics"]}
            self.context_id = "boundary-owner"
            self.initial_context, self.commands = [], []
            self._state = {
                "schema": runtime.STATE_SCHEMA,
                "source": {"sha256": self.package_sha256, "profile": runtime.PROFILE,
                           "logic_id": 0, "logic_sha256": self._logic_hashes[0]},
                "observation": {"count": 0, "capacity": 4096},
                "guest": {"status": "ready", "retired": 0, "pc": 0, "pending_effect": None,
                          "variables": [0] * 256, "flags": [0] * 256,
                          "future_architectural_field": {"retained": [1, 2, 3]}},
            }
            self.snapshot_bytes = b"opaque native snapshot: not interpreted by Python"
            self.snapshot_reads = 0
            self.reject_next = False

        def request(self, opcode=101, reply="ack", *, ident=1, args=(), text="Literal output"):
            self._state["guest"].update(status="pending", pc=0, pending_effect={
                "id": ident, "opcode": opcode, "logic": 0, "pc": 0,
                "next_pc": 1 + len(args), "reply": reply, "args": list(args), "text": text,
            })
            return self.pending()

        def get(self, name):
            if name == "agi-state-json":
                return json.dumps(self._state)
            if name == "agi-events-json":
                return json.dumps({"schema": runtime.EVENTS_SCHEMA,
                                   "source": self._state["source"], "events": []})
            if name == "agi-runtime-scene-json":
                return json.dumps({"schema": runtime.SCENE_SCHEMA,
                                   "source": self._state["source"], "width": 160, "height": 168,
                                   "visual": "0f" * 26880, "priority": "04" * 26880})
            if name == "agi-runtime-snapshot-hex":
                self.snapshot_reads += 1
                return self.snapshot_bytes.hex()
            raise AssertionError(f"Unexpected QOM read: {name}")

        def set(self, name, value):
            assert name == "agi-runtime-command"
            command = json.loads(value)
            if self.reject_next:
                self.reject_next = False
                raise runtime.QMPError("Authored boundary rejection")
            self.commands.append(command)
            action = command["action"]
            guest = self._state["guest"]
            if action in ("complete", "restore"):
                assert command["id"] == guest["pending_effect"]["id"]
                guest.update(status="ready", pending_effect=None)
                guest["retired"] += 1
            elif action == "seed":
                for field in ("variables", "flags"):
                    for key, item in command[field].items():
                        guest[field][int(key)] = item

    return NativeBoundary()


def test_harness_constructor_selects_runtime_without_reencoding_package(runtime, pack, tmp_path,
                                                                       monkeypatch):
    captured = {}

    def base_init(self, binary, code, **kwargs):
        captured.update(binary=binary, code=code, **kwargs)
        self.binary_sha256 = "b" * 64
        self.source_sha256 = sha256(code).hexdigest()
        self.failure_evidence = None

    monkeypatch.setattr(runtime.QemuAGI, "__init__", base_init)
    monkeypatch.setattr(runtime.QemuAGI, "close", lambda self, **kwargs: None)
    monkeypatch.setattr(runtime.QemuAGIRuntime, "state", lambda self: {"schema": runtime.STATE_SCHEMA})
    package = json.dumps(_authored(pack), indent=3).encode()
    with runtime.QemuAGIRuntime(tmp_path / "explicit-native", package) as vm:
        assert captured["code"] == b"\0"
        assert captured["extra_args"][:2] == ("-M", f"agi-test,runtime-package={vm.package_path}")
        assert vm.package_path.read_bytes() == package
        assert vm.package_sha256 == sha256(package).hexdigest()
        assert vm.source_sha256 == vm.package_sha256
        assert vm.initial_context == []
        path = vm.package_path
    assert not path.exists()


def test_runtime_observation_is_complete_and_checks_package_and_current_logic(runtime, boundary):
    state = boundary.state()
    copied = runtime.runtime_guest_state(state)
    copied["future_architectural_field"]["retained"].append(9)
    assert state["guest"]["future_architectural_field"]["retained"] == [1, 2, 3]
    assert boundary.events()["events"] == []
    assert len(boundary.scene()["visual"]) == 53760
    for key, bad in (("sha256", "0" * 64), ("profile", "pilot"),
                     ("logic_id", True), ("logic_id", 2), ("logic_sha256", "0" * 64)):
        original = boundary._state["source"][key]
        boundary._state["source"][key] = bad
        with pytest.raises(runtime.HarnessError, match="identity"):
            boundary.state()
        boundary._state["source"][key] = original
    boundary._state["source"].update(logic_id=1, logic_sha256=boundary._logic_hashes[1])
    assert boundary.state()["source"]["logic_id"] == 1


def test_runtime_event_client_refuses_oversize_batch_before_serializing(runtime, boundary,
                                                                     monkeypatch):
    reads = []
    actual_get = boundary.get

    def traced(name):
        reads.append(name)
        return actual_get(name)

    monkeypatch.setattr(boundary, "get", traced)
    with pytest.raises(ValueError, match="capacity"):
        boundary.configure(mask=3, capacity=4097)
    assert boundary.commands == []
    boundary._state["observation"].update(count=4097, capacity=65536)
    with pytest.raises(runtime.HarnessError, match="4096"):
        boundary.events()
    assert reads == ["agi-state-json"]
    assert boundary._state["observation"]["count"] == 4097
    boundary._state["observation"]["count"] = 4096
    assert boundary.events()["events"] == []


def test_event_transport_cap_has_margin_for_maximum_current_record_contract(runtime):
    # Use the widest native domains, including impossible combinations such
    # as full actor deltas accompanying a 1024-byte instruction.
    actor_fields = (
        "id x y prev_x prev_y target_x target_y width height prev_width prev_height "
        "view loop cel loop_count cel_count priority flags motion cycle direction "
        "step_size step_time step_time_count cycle_time cycle_time_count motion_flag "
        "cycle_flag saved_step follow_step follow_count"
    ).split()
    actor = {name: 2**32 - 1 for name in actor_fields}
    for name in ("x", "y", "prev_x", "prev_y", "target_x", "target_y"):
        actor[name] = -(2**31)
    actor.update(animated=False, drawn=False, updating=False, cycling=False, view_bound=False)
    event = {name: 2**32 - 1 for name in (
        "seq retired scene_revision logic pc opcode next_logic next_pc size actor kind channel_id"
    ).split()}
    event.update(seq=2**64 - 1, retired=2**64 - 1, scene_revision=2**64 - 1)
    event.update(channel="disasm", logic_sha256="a" * 64, bytes=[255] * 1024,
                     resolved=[2**32 - 1] * 7, before_actor=actor, after_actor=actor)
    # QMP wraps the serialized event page in a JSON string, escaping quotes.
    worst_row = len(json.dumps(json.dumps(event)).encode())
    assert runtime.MAX_EVENT_CAPACITY * (worst_row + 1) + 1024**2 < 32 * 1024**2


def test_runtime_explicit_commands_and_seed_admission(runtime, boundary):
    result = boundary.seed(variables={3: 19}, flags={"4": 1})
    assert result["guest"]["variables"][3] == 19
    assert boundary.initial_context == [
        {"action": "seed", "variables": {"3": 19}, "flags": {"4": 1}}]
    for call in (
        lambda: boundary.seed(variables={1: 1, "1": 2}),
        lambda: boundary.seed(variables={"01": 2}),
        lambda: boundary.seed(flags={0: True}),
        lambda: boundary.tick(0),
        lambda: boundary.tick(4097),
        lambda: boundary.input("é" * 41),
        lambda: boundary.input("\U0001f600"),
        lambda: boundary.key(1, 1),
        lambda: boundary.controller(True),
    ):
        before = len(boundary.commands)
        with pytest.raises(ValueError):
            call()
        assert len(boundary.commands) == before
    boundary.cycle()
    boundary.tick(4096)
    boundary.input("take key")
    boundary.key(0x4800, True)
    boundary.key(0x4800, False)
    boundary.controller(255)
    assert boundary.commands[-6:] == [
        {"action": "cycle"}, {"action": "tick", "ticks": 4096},
        {"action": "input", "text": "take key"},
        {"action": "key", "key": 0x4800, "pressed": True},
        {"action": "key", "key": 0x4800, "pressed": False},
        {"action": "controller", "controller": 255},
    ]
    ticket = boundary.request()
    with pytest.raises(runtime.HarnessError, match="seed"):
        boundary.seed(variables={0: 1})
    boundary.complete(ticket, accepted=False)
    with pytest.raises(runtime.HarnessError, match="seed"):
        boundary.seed(variables={0: 1})


def test_pending_tickets_bind_full_record_owner_binary_and_package(runtime, boundary):
    ticket = boundary.request(ident=2**64 - 1)
    for key, value in (("context", "another-owner"), ("package_sha256", "c" * 64),
                       ("binary_sha256", "c" * 64), ("schema", "unknown")):
        bad = deepcopy(ticket)
        bad[key] = value
        with pytest.raises(runtime.HarnessError, match="stale"):
            boundary.complete(bad, accepted=True)
    bad = deepcopy(ticket)
    bad["effect"]["text"] = "changed"
    with pytest.raises(runtime.HarnessError, match="modified"):
        boundary.complete(bad, accepted=True)
    boundary.request(ident=17)
    with pytest.raises(runtime.HarnessError, match="stale"):
        boundary.complete(ticket, accepted=True)
    assert boundary.commands == []
    current = boundary.pending()
    boundary.complete(current, accepted=True)
    with pytest.raises(runtime.HarnessError, match="stale"):
        boundary.complete(current, accepted=True)
    assert boundary.commands == [{"action": "complete", "id": 17, "accepted": True}]


def test_completions_require_explicit_typed_replies_and_do_not_ignore_fields(runtime, boundary):
    ticket = boundary.request(115, "text", args=(0, 1, 2, 3, 5))
    for kwargs in ({}, {"text": "longer"}, {"text": "é" * 6}, {"text": "\U0001f600"},
                   {"text": "ok", "number": 1}, {"text": "zero\0"}):
        with pytest.raises(ValueError):
            boundary.complete(ticket, accepted=True, **kwargs)
    boundary.complete(ticket, accepted=True, text="yes")
    assert boundary.commands[-1] == {"action": "complete", "id": 1,
                                     "accepted": True, "text": "yes"}
    for opcode, reply in ((118, "number"), (161, "menu")):
        ticket = boundary.request(opcode, reply, ident=opcode)
        for number in (None, True, -1, 256):
            with pytest.raises(ValueError):
                boundary.complete(ticket, accepted=True, number=number)
        boundary.complete(ticket, accepted=True, number=23)
        assert boundary.commands[-1]["number"] == 23
    ticket = boundary.request(134, "choice", ident=500)
    with pytest.raises(ValueError):
        boundary.complete(ticket, accepted=1)
    with pytest.raises(ValueError):
        boundary.complete(ticket, accepted=False, number=0)
    boundary.complete(ticket, accepted=False)
    assert boundary.commands[-1] == {"action": "complete", "id": 500, "accepted": False}
    ticket = boundary.request(126, "restore", ident=501)
    with pytest.raises(ValueError, match="restore"):
        boundary.complete(ticket, accepted=True)


def test_snapshot_is_opaque_and_restore_is_bound_to_current_request(runtime, boundary):
    snapshot = boundary.snapshot()
    assert snapshot == boundary.snapshot_bytes
    wrong = boundary.request(125, "ack")
    with pytest.raises(ValueError, match="restore"):
        boundary.restore(wrong, snapshot)
    ticket = boundary.request(126, "restore", ident=9)
    boundary.restore(ticket, snapshot)
    assert boundary.commands[-1] == {"action": "restore", "id": 9, "snapshot": snapshot.hex()}
    boundary.request(126, "restore", ident=10)
    with pytest.raises(runtime.HarnessError, match="stale"):
        boundary.restore(ticket, snapshot)


def test_pending_display_expansion_preserves_inspection_of_native_byte_strings(runtime, boundary):
    # Each native CP437 box-drawing glyph expands to three UTF-8 display bytes.
    ticket = boundary.request(text="─" * 4095)
    assert len(ticket["effect"]["text"].encode()) == 12285
    boundary._state["guest"]["pending_effect"]["text"] += "─"
    with pytest.raises(runtime.HarnessError, match="display text"):
        boundary.pending()


def test_cp437_glyphs_roundtrip_and_limits_count_native_bytes(pack, boundary):
    literal = "é ┌─┐"
    payload = _logic_payload(b"\0", [literal.encode("cp437")])
    package = pack.package_from_raw(logics=[{"id": 0, "data": payload}],
                                    objects=[{"name": literal, "room": 3}])
    assert package["logics"][0]["messages"] == [literal]
    assert pack.load_package(pack.dump_package(package))["objects"][0]["name"] == literal
    long_message = "é" * 4095
    package = pack.build_package(logics=[{"id": 0, "code": b"\0", "messages": [long_message]}])
    assert len(package["logics"][0]["messages"][0].encode("cp437")) == 4095
    assert len(package["logics"][0]["messages"][0].encode("utf-8")) == 8190
    package = pack.build_package(logics=[{"id": 0, "code": b"\0", "messages": []}],
                                 objects=[{"name": "─" * 255, "room": 0}])
    assert len(package["objects"][0]["name"].encode("cp437")) == 255
    boundary.input("é" * 40)
    assert boundary.commands[-1]["text"] == "é" * 40
    answer = "┌─┐" * 13 + "é"
    ticket = boundary.request(115, "text", args=(0, 1, 2, 3, 40))
    boundary.complete(ticket, accepted=True, text=answer)
    assert len(answer.encode("cp437")) == 40
    assert boundary.commands[-1]["text"] == answer


@pytest.mark.parametrize("action", ["complete", "restore"])
def test_readback_must_show_that_native_consumed_request(runtime, boundary, monkeypatch, action):
    ticket = boundary.request(126 if action == "restore" else 101,
                              "restore" if action == "restore" else "ack")
    monkeypatch.setattr(boundary, "set", lambda *args: None)
    with pytest.raises(runtime.HarnessError, match="did not consume"):
        if action == "restore":
            boundary.restore(ticket, b"opaque snapshot")
        else:
            boundary.complete(ticket, accepted=True)


def test_snapshot_and_scene_transport_validation(runtime, boundary, monkeypatch):
    actual_get = boundary.get
    for raw in ("Ff", "0", "not hex", ""):
        monkeypatch.setattr(boundary, "get", lambda name, raw=raw: raw)
        with pytest.raises(runtime.HarnessError, match="snapshot"):
            boundary.snapshot()
    valid = json.loads(actual_get("agi-runtime-scene-json"))
    for replacement in ({"visual": "10" * 26880}, {"priority": "00"},
                        {"width": True}, {"schema": "unknown"}):
        monkeypatch.setattr(boundary, "get",
                            lambda name, replacement=replacement: json.dumps(valid | replacement))
        with pytest.raises(runtime.HarnessError):
            boundary.scene()


@pytest.mark.parametrize("opcode", [101, 102, 135, 141, 144, 151, 152])
def test_implemented_text_outputs_are_recorded_before_ack(services, boundary, opcode):
    adapter = services.RuntimeServices(boundary)
    boundary.request(opcode, text="Caller-visible literal text")
    result = adapter.handle()
    assert result["status"] == "output"
    entry = adapter.ledger["entries"][0]
    assert entry["text"] == "Caller-visible literal text"
    assert entry["status"] == "completed"
    assert entry["request"]["effect"]["opcode"] == opcode
    assert boundary.commands == [{"action": "complete", "id": 1, "accepted": True}]


@pytest.mark.parametrize("opcode", [29, 110, 124, 127, 129, 133, 139, 162])
def test_unimplemented_devices_remain_pending_without_silent_success(services, boundary, opcode):
    adapter = services.RuntimeServices(boundary)
    boundary.request(opcode)
    before = boundary.state()
    assert adapter.handle()["status"] == "unsupported"
    assert adapter.handle(choice={"accepted": True})["status"] == "unsupported"
    assert boundary.state() == before and boundary.commands == []
    assert adapter.ledger["entries"] == []
    assert adapter.handle(choice={"accepted": False})["status"] == "cancelled"
    assert boundary.commands[-1]["accepted"] is False


@pytest.mark.parametrize("opcode,reply,args,choice", [
    (115, "text", (0, 1, 1, 1, 8), {"accepted": True, "text": "name"}),
    (118, "number", (1, 2), {"accepted": True, "number": 7}),
    (161, "menu", (), {"accepted": True, "number": 3}),
    (128, "choice", (), {"accepted": True}),
    (134, "choice", (), {"accepted": True}),
    (136, "ack", (), {"accepted": True}),
])
def test_input_choices_and_pause_never_get_implicit_answers(services, boundary,
                                                           opcode, reply, args, choice):
    adapter = services.RuntimeServices(boundary)
    boundary.request(opcode, reply, args=args)
    assert adapter.handle()["status"] == "choice_required"
    assert boundary.commands == []
    assert adapter.handle(choice=choice)["status"] == "completed"
    assert boundary.commands[-1]["accepted"] is True


def test_memory_save_restore_slot_identity_and_explicit_selection(runtime, services, boundary):
    adapter = services.RuntimeServices(boundary)
    boundary.request(125, "ack", ident=5)
    assert adapter.handle()["required"] == ["accepted", "slot"]
    assert boundary.snapshot_reads == 0
    assert adapter.handle(choice={"accepted": True, "slot": "first"})["status"] == "saved"
    saved = adapter.slots["first"]
    assert saved["snapshot"] == boundary.snapshot_bytes
    assert saved["sha256"] == sha256(saved["snapshot"]).hexdigest()
    saved["snapshot"] = b"caller mutation"
    assert adapter.slots["first"]["snapshot"] == boundary.snapshot_bytes
    boundary.request(126, "restore", ident=6)
    assert adapter.handle()["status"] == "choice_required"
    with pytest.raises(runtime.HarnessError, match="does not exist"):
        adapter.handle(choice={"accepted": True, "slot": "missing"})
    assert adapter.handle(choice={"accepted": True, "slot": "first"})["status"] == "restored"
    assert boundary.commands[-1] == {"action": "restore", "id": 6,
                                     "snapshot": boundary.snapshot_bytes.hex()}
    saved = adapter.slots["first"]
    for key, value in (("package_sha256", "c" * 64), ("binary_sha256", "c" * 64),
                       ("sha256", "c" * 64), ("snapshot", b"modified")):
        bad = {**saved, key: value}
        with pytest.raises(runtime.HarnessError):
            adapter.install_slot("wrong", bad)
    adapter.install_slot("copy", saved)
    assert adapter.slots["copy"] == saved
    assert set(adapter.slots) == {"first", "copy"}


def test_failed_save_does_not_replace_slot_and_limits_do_not_complete_guest(runtime, services,
                                                                           boundary):
    adapter = services.RuntimeServices(boundary, max_slots=1, max_saved_bytes=200)
    boundary.request(125, ident=1)
    adapter.handle(choice={"accepted": True, "slot": "keep"})
    original = adapter.slots["keep"]
    boundary.snapshot_bytes = b"new opaque state"
    boundary.request(125, ident=2)
    with pytest.raises(runtime.HarnessError, match="capacity"):
        adapter.handle(choice={"accepted": True, "slot": "other"})
    assert boundary.pending()["effect"]["id"] == 2
    boundary.reject_next = True
    with pytest.raises(runtime.QMPError):
        adapter.handle(choice={"accepted": True, "slot": "keep"})
    assert adapter.slots["keep"] == original
    assert adapter.ledger["entries"][-1]["status"] == "completion_failed_or_unknown"


def test_failed_output_is_recorded_once_and_never_automatically_replayed(runtime, services, boundary):
    adapter = services.RuntimeServices(boundary, max_outputs=2)
    boundary.request(text="Output survives an uncertain acknowledgement")
    boundary.reject_next = True
    with pytest.raises(runtime.QMPError):
        adapter.handle()
    assert adapter.ledger["entries"][0]["text"].startswith("Output survives")
    assert adapter.ledger["entries"][0]["status"] == "completion_failed_or_unknown"
    with pytest.raises(runtime.HarnessError, match="already attempted"):
        adapter.handle()
    assert len(adapter.ledger["entries"]) == 1 and boundary.commands == []
    # Explicit cancellation resolves the request without re-emitting output.
    adapter.handle(choice={"accepted": False})
    boundary.request(ident=2)
    with pytest.raises(runtime.HarnessError, match="capacity"):
        adapter.handle()
    assert boundary.pending()["effect"]["id"] == 2
