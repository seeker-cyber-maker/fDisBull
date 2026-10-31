"""Authored stop/inventory guards; no original game or native execution."""
from copy import deepcopy
from hashlib import sha256
import json
import time
from types import SimpleNamespace

import pytest

import examples.agi.verify_troll as module


class AuthoredSession:
    def __init__(self):
        self.memory = bytearray(0x50000)
        self.calls = []
        self.runs = []
        self.register_state = {}

    def registers(self):
        return deepcopy(self.register_state)

    def call(self, method, *args, **kwargs):
        self.calls.append(method)
        raise AssertionError(f"Unexpected state-changing call: {method}")

    def run(self, **kwargs):
        self.runs.append(kwargs)
        raise AssertionError("Rejected stop must not resume the guest")


def memory_read(session, address, size):
    result = bytes(session.memory[address:address + size])
    assert len(result) == size, "Authored fixture read outside its memory"
    return result


def put_word(session, address, value):
    session.memory[address:address + 2] = value.to_bytes(2, "little")


def score_stop():
    return {
        "outcome": "breakpoint",
        "guest_elapsed_ms": 10,
        "session": {"stop_reason": {
            "breakpoint_id": "score-watch",
            "data_access": {
                "access": "w",
                "instruction": {
                    "space": "segmented", "segment": "0x1000", "offset": "0x72da"
                },
            },
        }},
    }


def score_run(monkeypatch):
    """Create an authored post-write stop at the specified +4 source site."""
    monkeypatch.setattr(module, "read", memory_read)
    run = object.__new__(module.TrollRun)
    run.d = AuthoredSession()
    run.cs, run.ds = 0x1000, 0x20000
    run.bp, run.watch, run.score_write = "print-watch", "score-watch", None
    run.guest_elapsed, run.journal = 0, []
    run.deadline = time.monotonic() + 10
    run.inventory = {"item": 3}
    code = bytearray(0x1bc)
    code[0x1b8:0x1bb] = bytes.fromhex("050304")
    run.resources = {25: SimpleNamespace(code=bytes(code), resource_sha256="authored-resource")}
    run.d.register_state = {
        "segments": {"cs": "0x1000", "ds": "0x2000"},
        "instruction_pointer": "0x72de",
        "general": {"ebx": "0x3", "eax": "0x4", "esi": "0x41bb"},
    }
    put_word(run.d, run.ds + 0x979, 0x3000)
    run.d.memory[run.ds + 0x3002] = 25
    put_word(run.d, run.ds + 0x3004, 0x4000)
    run.d.memory[run.ds + 0x4000:run.ds + 0x4000 + len(code)] = code
    run.d.memory[run.ds + 12] = 11
    return run


@pytest.mark.parametrize("fault, message", [
    ("foreign-breakpoint", "Foreign stop preserved"),
    ("missing-access", "Foreign stop preserved"),
    ("read-access", "Foreign stop preserved"),
    ("linear-writer", "Unexpected score writer preserved"),
    ("writer-segment", "Unexpected score writer preserved"),
    ("writer-offset", "Unexpected score writer preserved"),
    ("resume-cs", "Unexpected score resume binding"),
    ("resume-ds", "Unexpected score resume binding"),
    ("resume-ip", "Unexpected score resume binding"),
    ("wrong-logic", "Score source is not logic 25"),
    ("source-crosses-segment", "Score source is not logic 25"),
    ("source-byte-mismatch", "Score source bytes differ"),
    ("wrong-source-operation", "Score source bytes differ"),
    ("wrong-variable", "Score operands differ"),
    ("wrong-addend", "Score operands differ"),
    ("wrong-source-cursor", "Score operands differ"),
    ("uncommitted-score", "Original score write did not commit 11"),
])
def test_incorrect_score_stop_refuses_before_trace_or_continuation(monkeypatch, fault, message):
    run = score_run(monkeypatch)
    out = score_stop()
    reason = out["session"]["stop_reason"]
    access = reason["data_access"]
    registers = run.d.register_state
    if fault == "foreign-breakpoint":
        reason["breakpoint_id"] = "somebody-elses-watch"
    elif fault == "missing-access":
        del reason["data_access"]
    elif fault == "read-access":
        access["access"] = "r"
    elif fault == "linear-writer":
        access["instruction"]["space"] = "linear"
    elif fault == "writer-segment":
        access["instruction"]["segment"] = "0x1001"
    elif fault == "writer-offset":
        access["instruction"]["offset"] = "0x72de"
    elif fault.startswith("resume-"):
        key = fault.removeprefix("resume-")
        if key == "ip":
            registers["instruction_pointer"] = "0x72da"
        else:
            registers["segments"][key] = "0x1001"
    elif fault == "wrong-logic":
        run.d.memory[run.ds + 0x3002] = 24
    elif fault == "source-crosses-segment":
        put_word(run.d, run.ds + 0x3004, 0xff00)
    elif fault == "source-byte-mismatch":
        run.d.memory[run.ds + 0x4000] ^= 1
    elif fault == "wrong-source-operation":
        code = bytearray(run.resources[25].code)
        code[0x1ba] = 3
        run.resources[25].code = bytes(code)
        run.d.memory[run.ds + 0x4000:run.ds + 0x4000 + len(code)] = code
    elif fault == "wrong-variable":
        registers["general"]["ebx"] = "0x4"
    elif fault == "wrong-addend":
        registers["general"]["eax"] = "0x5"
    elif fault == "wrong-source-cursor":
        registers["general"]["esi"] = "0x41b8"
    elif fault == "uncommitted-score":
        run.d.memory[run.ds + 12] = 7
    else:
        raise AssertionError(f"Unhandled authored fault: {fault}")

    with pytest.raises(RuntimeError, match=message):
        run.handle_stop(out)

    assert run.d.calls == []
    assert run.d.runs == []
    assert run.score_write is None
    assert run.watch == "score-watch"
    assert run.journal == []


def test_route_advance_preserves_foreign_stop_without_second_native_run(monkeypatch):
    run = score_run(monkeypatch)
    out = score_stop()
    out["session"]["stop_reason"]["breakpoint_id"] = "foreign-watch"

    def first_run(**kwargs):
        run.d.runs.append(kwargs)
        assert len(run.d.runs) == 1, "Foreign stop was resumed"
        return out

    run.d.run = first_run
    with pytest.raises(RuntimeError, match="Foreign stop preserved"):
        run.advance(20)

    assert len(run.d.runs) == 1
    assert run.d.calls == []
    assert run.guest_elapsed == 10
    assert run.journal == [{"kind": "run", "attempted": True, "result": out}]
    assert run.score_write is None


@pytest.mark.parametrize('fault', [None, 'lost', 'short', 'foreign'])
def test_score_trace_requires_complete_observation_and_retains_known_write(monkeypatch, fault):
    run = score_run(monkeypatch)
    files = {}

    class MemoryPath:
        def __init__(self, name=""):
            self.name = name

        def __truediv__(self, name):
            return MemoryPath(name)

        def write_text(self, text):
            files[self.name] = text.encode()

        def read_bytes(self):
            return files[self.name]

    run.root = MemoryPath()
    events = [{"offset": number} for number in range(31 if fault == 'short' else 32)]

    def call(method, *args, **kwargs):
        run.d.calls.append(method)
        if method == "trace.read":
            return {"events": events, "next_cursor": None}
        assert method in ("breakpoints.delete", "trace.start", "trace.stop")
        return {}

    def continuation(**kwargs):
        run.d.runs.append(kwargs)
        assert run.watch is None
        assert run.score_write["after_score"] == 11
        assert not run.score_write["complete"]
        if fault == 'lost':raise TimeoutError('response lost after dispatch')
        return {"outcome": "breakpoint" if fault == 'foreign' else "pause", "guest_elapsed_ms": 3}

    run.d.call, run.d.run = call, continuation
    if fault:
        with pytest.raises((RuntimeError, TimeoutError)):
            run.handle_stop(score_stop())
        assert len(run.d.runs) == 1
        assert run.score_write['after_score'] == 11
        assert run.score_write['status'] == 'incomplete' and not run.score_write['complete']
        assert run.d.calls[-1] == 'trace.stop'
        assert json.loads(files['troll-score-write.private.json'])['complete'] is False
        trace = json.loads(files['troll-score-trace.private.json'])
        assert not trace['complete']
        if fault == 'lost':
            assert run.journal == [{'kind': 'score-trace', 'attempted': True, 'result': None}]
            assert trace['run'] is None and run.guest_elapsed == 0
        return
    run.handle_stop(score_stop())

    assert run.d.calls == ["breakpoints.delete", "trace.start", "trace.read", "trace.stop"]
    assert len(run.d.runs) == 1
    assert run.guest_elapsed == 3
    assert run.score_write["status"] == "verified"
    assert run.score_write["complete"]
    assert run.score_write["source_offset"] == 0x1b8
    assert run.score_write["trace"]["count"] == 32
    assert set(files) == {"troll-score-trace.private.json", "troll-score-write.private.json"}


def inventory_fixture(monkeypatch, base=0x4000):
    session = AuthoredSession()
    cs, ds = 0x1000, 0x20000
    source_bytes = b"authored object index fixture"
    engine_bytes = b"authored engine!"

    class Source:
        def __truediv__(self, name):
            assert name == "OBJECT"
            return SimpleNamespace(read_bytes=lambda: source_bytes)

    monkeypatch.setattr(module, "read", memory_read)
    monkeypatch.setattr(module, "OBJECT_SHA256", sha256(source_bytes).hexdigest())
    monkeypatch.setattr(module, "_ENGINE_LENGTH", len(engine_bytes))
    monkeypatch.setattr(module, "_ENGINE_SHA256", sha256(engine_bytes).hexdigest())
    session.memory[cs * 16:cs * 16 + len(engine_bytes)] = engine_bytes
    put_word(session, cs * 16 + 0x7601, 3)
    put_word(session, ds + 0x969, base)
    put_word(session, ds + 0x96b, base + 81)
    put_word(session, ds + base + 9, 0x60)
    session.memory[ds + base + 0x60:ds + base + 0x67] = b"carrot\0"
    session.memory[ds + base + 11] = 255
    return session, Source(), cs, ds


@pytest.mark.parametrize("base", [0x4000, 65536 - 0x67])
def test_inventory_binding_reads_named_item_at_last_valid_name_boundary(monkeypatch, base):
    session, source, cs, ds = inventory_fixture(monkeypatch, base)
    binding = module.bind_carrot(session, source, cs, ds)
    assert binding["item"] == 3
    assert binding["location_linear"] == ds + base + 11
    assert binding["carried_value"] == 255
    assert memory_read(session, binding["location_linear"], 1) == b"\xff"
    assert session.calls == session.runs == []


@pytest.mark.parametrize("fault, message", [
    ("source-hash", "Unqualified inventory source"),
    ("engine-hash", "Unqualified inventory interpreter"),
    ("stride", "Inventory stride differs"),
    ("zero-base", "Inventory record bounds differ"),
    ("reversed-bounds", "Inventory record bounds differ"),
    ("short-table", "Inventory record bounds differ"),
    ("name-outside-segment", "Inventory name outside data segment"),
    ("name-offset", "Carrot source name binding differs"),
    ("name-text", "Carrot source name binding differs"),
    ("unterminated-name", "Carrot source name binding differs"),
])
def test_inventory_binding_refuses_unqualified_bounds_or_name(monkeypatch, fault, message):
    base = 65536 - 0x66 if fault == "name-outside-segment" else 0x4000
    session, source, cs, ds = inventory_fixture(monkeypatch, base)
    if fault == "source-hash":
        monkeypatch.setattr(module, "OBJECT_SHA256", "0" * 64)
    elif fault == "engine-hash":
        session.memory[cs * 16] ^= 1
    elif fault == "stride":
        put_word(session, cs * 16 + 0x7601, 4)
    elif fault == "zero-base":
        put_word(session, ds + 0x969, 0)
    elif fault == "reversed-bounds":
        put_word(session, ds + 0x96b, base - 1)
    elif fault == "short-table":
        put_word(session, ds + 0x96b, base + 80)
    elif fault == "name-outside-segment":
        pass
    elif fault == "name-offset":
        put_word(session, ds + base + 9, 0x61)
    elif fault == "name-text":
        session.memory[ds + base + 0x60] = ord("x")
    elif fault == "unterminated-name":
        session.memory[ds + base + 0x66] = ord("x")
    else:
        raise AssertionError(f"Unhandled authored fault: {fault}")

    with pytest.raises(RuntimeError, match=message):
        module.bind_carrot(session, source, cs, ds)
    assert session.calls == session.runs == []


@pytest.mark.parametrize('failure, exception, message, errors', [
    ('trace-artifact', OSError, 'trace artifact persistence failed', 'persistence_errors'),
    ('trace-stop', TimeoutError, 'trace stop response lost', 'cleanup_errors'),
])
def test_trace_failure_preserves_score_proof_and_attempts_cleanup_independently(
        monkeypatch, failure, exception, message, errors):
    """A qualified write survives later delivery failure without claiming success."""
    run = score_run(monkeypatch)
    files = {}

    class MemoryPath:
        def __init__(self, name=''):
            self.name = name

        def __truediv__(self, name):
            return MemoryPath(name)

        def write_text(self, text):
            if failure == 'trace-artifact' and self.name == 'troll-score-trace.private.json':
                raise OSError('trace artifact persistence failed')
            files[self.name] = text.encode()

        def read_bytes(self):
            return files[self.name]

    run.root = MemoryPath()

    def call(method, *args, **kwargs):
        run.d.calls.append(method)
        if method == 'trace.read':
            return {'events': [{'offset': number} for number in range(32)], 'next_cursor': None}
        if method == 'trace.stop' and failure == 'trace-stop':
            raise TimeoutError('trace stop response lost')
        assert method in ('breakpoints.delete', 'trace.start', 'trace.stop')
        return {}

    def continuation(**kwargs):
        run.d.runs.append(kwargs)
        assert len(run.d.runs) == 1, 'A failed capture or cleanup must not resume the guest'
        return {'outcome': 'pause', 'guest_elapsed_ms': 0}

    run.d.call, run.d.run = call, continuation
    with pytest.raises(exception, match=message):
        run.handle_stop(score_stop())

    assert run.d.calls == ['breakpoints.delete', 'trace.start', 'trace.read', 'trace.stop']
    assert len(run.d.runs) == 1
    assert run.journal == [{'kind': 'score-trace', 'attempted': True,
                            'result': {'outcome': 'pause', 'guest_elapsed_ms': 0}}]
    assert 'troll-score-write.private.json' in files
    proof = json.loads(files['troll-score-write.private.json'])
    assert proof['status'] == 'incomplete' and proof['complete'] is False
    assert proof['native_execution'] is True
    assert proof['source_logic_sha256'] == 'authored-resource' and proof['source_offset'] == 0x1b8
    assert (proof['before_score'], proof['after_score']) == (7, 11)
    assert proof['writer'] == {'source_offset': 0x72da, 'resume_offset': 0x72de, 'bx': 3, 'al': 4}
    assert proof['code_binding']['offset'] == 0x4000
    expected_error = ({'artifact': 'troll-score-trace.private.json', 'error': message}
                      if failure == 'trace-artifact' else {'operation': 'trace.stop', 'error': message})
    assert expected_error in proof[errors]
