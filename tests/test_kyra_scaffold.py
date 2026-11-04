"""Authored protocol doubles only. These are NOT native ScummVM game tests."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
import struct

import pytest

from fdisbull.kyra_scaffold import KyraScaffold, KyraProtocolError, ScriptBinding


def authored(words=(0x4101, 0x4e04, 0x4801), entries=(0,), text=b"INVENTED"):
    def chunk(name, data):
        return name + struct.pack(">I", len(data)) + data + (b"\0" if len(data) % 2 else b"")
    body = b"EMC2" + chunk(b"ORDR", struct.pack(">" + "H" * len(entries), *entries))
    body += chunk(b"TEXT", text) + chunk(b"DATA", struct.pack(">" + "H" * len(words), *words))
    return b"FORM" + struct.pack(">I", len(body) + 8) + body


def script(profile="kyrandia1-dos", **kwargs):
    return ScriptBinding.from_bytes("AUTHORED.EMC", authored(**kwargs), profile=profile)


def position(span=10, parent=0):
    return dict(resource_id=1, generation=1, word_offset=0, context_id=1,
                span_id=span, parent_span_id=parent)


class ProtocolDouble:
    """Finite call/response fixture, not an engine implementation."""
    def __init__(self, original=None, profile="kyrandia1-dos"):
        self.original = original or script(profile)
        self.closed = False
        self.calls = []
        self.hello = dict(protocol="kyra-emc2-debug-1", engine="kyra", profile=profile,
                          game_id="lol" if profile == "lol1-dos" else "kyra1",
                          original_x86_executed=False, provider="test-double",
                          provider_sha256=sha256(b"authored protocol double").hexdigest(),
                          capabilities=["state.get", "resources.list", "resource.read", "run", "step",
                                        "break.add", "break.remove", "trace.get"])
        self.state = dict(paused=True, revision=1, phase="emc_before", position=position())
        self.records = [dict(resource_id=1, generation=1, name="AUTHORED.EMC",
                             data_words=len(self.original.data) // 2,
                             ordr_words=len(self.original.ordr) // 2, encoding="be16-canonical")]
        self.stop = dict(paused=True, reason="budget", phase="emc_after", completed=1, revision=2,
                         completed_spans=[10], position=position())
        self.trace = dict(events=[dict(kind="before", position=position()),
                                 dict(kind="after", position=position())], dropped=0)
        self.alter = None

    def call(self, op, params=None, *, timeout_ms=15000):
        self.calls.append((op, deepcopy(params), timeout_ms))
        if self.alter is not None:
            answer = self.alter(op, params)
            if answer is not None:
                return answer
        if op == "hello": return deepcopy(self.hello)
        if op == "state.get": return {"state": deepcopy(self.state)}
        if op == "resources.list": return {"resources": deepcopy(self.records)}
        if op == "resource.read":
            data = self.original.data if params["component"] == "DATA" else self.original.ordr
            start, size = params["offset"], params["length"]
            return {**params, "hex": data[start:start + size].hex(), "revision": self.state["revision"]}
        if op == "break.add": return {"breakpoint_id": 1}
        if op == "break.remove": return {"removed": True}
        if op in ("step", "run"): return {"stop": deepcopy(self.stop)}
        if op == "trace.get": return deepcopy(self.trace)
        raise AssertionError(op)

    def close(self): self.closed = True


@pytest.mark.parametrize("profile,expected", [("kyrandia1-dos", 0), ("lol1-dos", 1)])
def test_entry_profiles_and_coordinate_units(profile, expected):
    obj = script(profile)
    assert obj.entries == (expected,)
    pos = obj.location(1)
    assert pos["data_byte_offset"] == 2 and pos["file_byte_offset"] == obj.data_offset + 2
    assert obj.instruction(1)["facts"]["syscall_id"] == 4
    assert obj.instruction(1)["syscall_semantics"] == "game_specific_unbound"


def test_absent_entry_and_lol_last_word_refusal():
    assert script(entries=(65535, 1)).entries == (None, 1)
    with pytest.raises(ValueError, match="entry adjustment"):
        script("lol1-dos", words=(0x4801,), entries=(0,))
    with pytest.raises(ValueError, match="no admitted entry"):
        script(entries=(65535,))


@pytest.mark.parametrize("change", [
    {"protocol": "agi"}, {"game_id": "kyra2"}, {"profile": "lol1-dos"},
    {"original_x86_executed": True}, {"original_x86_executed": 0},
    {"provider": "DOS"}, {"provider_sha256": "bad"}, {"capabilities": ["run"]},
])
def test_handshake_refuses_wrong_provider_or_scope(change):
    peer = ProtocolDouble(); peer.hello.update(change)
    with pytest.raises(KyraProtocolError): KyraScaffold(peer, profile="kyrandia1-dos")
    assert peer.closed


def test_bind_checks_complete_code_and_entries_and_retains_unknowns():
    original = script()
    peer = ProtocolDouble(original)
    session = KyraScaffold(peer, profile=original.profile)
    bound = session.bind(original, 1)
    receipt = bound.receipt()
    assert receipt["data_sha256"] == sha256(original.data).hexdigest()
    assert receipt["text_verified"] is False and receipt["original_dos_execution_verified"] is False
    assert [p["component"] for op, p, _ in peer.calls if op == "resource.read"] == ["DATA", "ORDR"]
    assert session.engine_state()["position"]["source_binding"]["file_byte_offset"] == original.data_offset


@pytest.mark.parametrize("which", ["DATA", "ORDR"])
def test_source_mismatch_in_either_chunk_is_not_a_binding(which):
    original = script()
    peer = ProtocolDouble(original)
    session = KyraScaffold(peer, profile=original.profile)
    def alter(op, params):
        if op == "resource.read" and params["component"] == which:
            return {**params, "revision": 1, "hex": "ff" * params["length"]}
    peer.alter = alter
    with pytest.raises(KyraProtocolError, match="canonical words differ"):
        session.bind(original, 1)
    # A different original is a caller mismatch; malformed wire bytes are a
    # protocol failure and must close the owned peer instead of being retried.
    assert not peer.closed
    peer.alter = lambda op, p: {**p, "revision": 1, "hex": "zz" * p["length"]} if op == "resource.read" else None
    with pytest.raises(KyraProtocolError, match="exact hexadecimal"):
        session.bind(original, 1)
    assert peer.closed


def test_binding_uses_all_chunks_and_not_one_convenient_sample():
    original = script(words=(0x4100,) * 5000)
    peer = ProtocolDouble(original)
    session = KyraScaffold(peer, profile=original.profile)
    session.bind(original, 1)
    reads = [p for op, p, _ in peer.calls if op == "resource.read" and p["component"] == "DATA"]
    assert [p["offset"] for p in reads] == [0, 4096, 8192]
    assert sum(p["length"] for p in reads) == len(original.data)


def test_duplicate_names_require_explicit_resource_id():
    peer = ProtocolDouble()
    peer.records.append({**peer.records[0], "resource_id": 2})
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    bound = session.bind(peer.original, 2)
    assert bound.resource_id == 2
    assert all(p["resource_id"] == 2 for op, p, _ in peer.calls if op == "resource.read")


@pytest.mark.parametrize("bad_id", [True, -1, 0, 1.5])
def test_resource_ids_are_not_coerced(bad_id):
    peer = ProtocolDouble(); peer.records[0]["resource_id"] = bad_id
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    with pytest.raises(KyraProtocolError): session.resources()
    assert peer.closed


def test_source_replacement_during_binding_closes_session():
    peer = ProtocolDouble(); session = KyraScaffold(peer, profile="kyrandia1-dos")
    peer.alter = lambda op, p: {**p, "revision": 2, "hex": "00" * p["length"]} if op == "resource.read" else None
    with pytest.raises(KyraProtocolError, match="revision changed"):
        session.bind(peer.original, 1)
    assert peer.closed


def test_breakpoint_requires_owned_current_generation_and_exact_instruction_guard():
    peer = ProtocolDouble(); session = KyraScaffold(peer, profile="kyrandia1-dos")
    bound = session.bind(peer.original, 1)
    result = session.breakpoint(bound, 1)
    assert result["scope"] == "before EMC dispatch"
    call = next(p for op, p, _ in peer.calls if op == "break.add")
    assert call["expected_hex"] == "4e04" and call["word_offset"] == 1
    session.delete_breakpoint(1)
    peer.records[0]["generation"] = 2
    with pytest.raises(KyraProtocolError, match="generation changed"):
        session.breakpoint(bound, 1)
    with pytest.raises(KyraProtocolError, match="stale"):
        session.breakpoint(bound, 1)


def test_nested_completion_does_not_complete_starting_dispatch():
    peer = ProtocolDouble(); peer.stop["completed_spans"] = [11]
    peer.stop["position"] = position(11, 10)
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    out = session.step()
    assert out["budget_satisfied"] is True
    assert out["starting_dispatch_completed"] is False
    assert out["provider"] == "test-double"


def test_breakpoint_stop_is_not_an_exhausted_budget():
    peer = ProtocolDouble()
    peer.stop.update(reason="breakpoint", phase="emc_before", completed=0, completed_spans=[])
    out = KyraScaffold(peer, profile="kyrandia1-dos").run(max_instructions=10)
    assert not out["budget_satisfied"] and not out["starting_dispatch_completed"]


@pytest.mark.parametrize("change", [
    {"paused": False}, {"reason": "magic-success"}, {"completed": 2},
    {"completed_spans": [10, 10]}, {"completed": True},
])
def test_bad_execution_receipt_is_fail_closed(change):
    peer = ProtocolDouble(); peer.stop.update(change)
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    with pytest.raises(KyraProtocolError): session.step()
    assert peer.closed


def test_timeout_never_replays_uncertain_execution():
    peer = ProtocolDouble(); session = KyraScaffold(peer, profile="kyrandia1-dos")
    def fail(op, p):
        if op == "run": raise TimeoutError("authored timeout")
    peer.alter = fail
    with pytest.raises(TimeoutError): session.run()
    assert peer.closed and sum(op == "run" for op, _, _ in peer.calls) == 1


def test_trace_loss_and_native_only_operations_remain_explicit():
    peer = ProtocolDouble(); peer.trace["dropped"] = 2
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    trace = session.trace_records()
    assert not trace["lossless_window"] and not trace["whole_run_complete"]
    with pytest.raises(KyraProtocolError, match="checkpoints"): session.save_state()
    with pytest.raises(KyraProtocolError, match="original DOS CPU"): session.registers()


def test_hook_generator_exact_anchor_and_idempotence_refusal():
    path = Path(__file__).parents[1] / "experimental/scummvm/kyra-scaffold/apply_hooks.py"
    spec = importlib.util.spec_from_file_location("kyra_hooks_installer", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    # Authored anchor fixture, not a copy or test of the full ScummVM source.
    source = ('#include "common/endian.h"\n'
              '\tCommon::strlcpy(_scriptData->filename, filename, 13);\n'
              '\tdelete[] data->text;\n'
              '\tscriptStat->sp = EMCState::kStackLastEntry;\n'
              '\tint16 code = *script->ip++;\n'
              '\treturn (script->ip != nullptr);\n')
    result = module.instrument(source)
    assert result.count("#ifdef FDISBULL_KYRA_HOOKS") == 6
    assert result.index("FDisBullKyraHooks::before") < result.index("int16 code")
    assert result.index("FDisBullKyraHooks::after") < result.index("return (script")
    # The CLI's blob guard prevents applying to an already patched file.
    assert module.git_blob(result.encode()) != module.SCRIPT_BLOB
    with pytest.raises(ValueError, match="anchor"):
        module.instrument(source + '\tint16 code = *script->ip++;\n')


@pytest.mark.parametrize("trace", [
    {"events": [], "dropped": True},
    {"events": [{"kind": "before", "position": None}], "dropped": 0},
    {"events": [{"kind": "unknown", "position": position()}], "dropped": 0},
])
def test_malformed_traces_are_fail_closed(trace):
    peer = ProtocolDouble(); peer.trace = trace
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    with pytest.raises(KyraProtocolError): session.trace_records()
    assert peer.closed


def test_unknown_breakpoint_result_cannot_leave_unowned_control_active():
    peer = ProtocolDouble(); session = KyraScaffold(peer, profile="kyrandia1-dos")
    bound = session.bind(peer.original, 1)
    peer.alter = lambda op, p: {"breakpoint_id": True} if op == "break.add" else None
    with pytest.raises(KyraProtocolError): session.breakpoint(bound, 0)
    assert peer.closed


def test_shared_run_budget_is_not_restarted_after_preflight(monkeypatch):
    import fdisbull.kyra_scaffold as scaffold
    peer = ProtocolDouble(); session = KyraScaffold(peer, profile="kyrandia1-dos")
    ticks = iter([100.0, 100.8])
    monkeypatch.setattr(scaffold.time, "monotonic", lambda: next(ticks))
    session.run(timeout_ms=1000)
    request = next((p, t) for op, p, t in peer.calls if op == "run")
    assert 150 <= request[1] <= 201
    assert request[0]["max_ms"] < request[1]



def test_truncated_completion_history_leaves_missing_caller_unknown():
    peer = ProtocolDouble()
    peer.stop.update(completed=3000, completed_spans=list(range(1000, 3048)))
    result = KyraScaffold(peer, profile="kyrandia1-dos").run(max_instructions=3000)
    assert result["starting_dispatch_completed"] is None
    assert result["completion_spans_truncated"] is True


def test_emc_stop_without_position_is_invalid():
    peer = ProtocolDouble(); peer.stop["position"] = None
    session = KyraScaffold(peer, profile="kyrandia1-dos")
    with pytest.raises(KyraProtocolError, match="omitted its position"): session.step()
    assert peer.closed
