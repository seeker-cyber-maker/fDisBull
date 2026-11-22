"""Authored sound resources against the production native AGI 2.917 sequencer.

Expected timing, command order, and envelope values are literal independent
behavioral examples, not values produced by another opcode interpreter.
"""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native/qemu-agi/overlay/target/agi"
U8, U32, U64 = C.c_uint8, C.c_uint32, C.c_uint64


class Event(C.Structure):
    _fields_ = [("sequence", U64), ("tick", U64), ("kind", U32),
                ("channel", U32), ("value", U32), ("enabled", U32)]


class Output(C.Structure):
    _fields_ = [("count", U32), ("events", Event * 16)]


class Channel(C.Structure):
    _fields_ = [(name, U32) for name in (
        "offset", "countdown", "finished", "tone", "divisor", "base_attenuation",
        "attenuation", "envelope_index", "envelope_value")] + [("remaining", U64)]


class State(C.Structure):
    _fields_ = [(name, U32) for name in (
        "active", "resource", "completion_flag", "device", "channel_count", "resource_size"
    )] + [(name, U64) for name in ("ticks", "output_sequence", "remaining")] + [
        ("channels", Channel * 4), ("last_output", Output)]


class Info(C.Structure):
    _fields_ = [("offsets", U32 * 4), ("durations", U64 * 4)]


RESOURCE = C.CFUNCTYPE(C.c_int, C.c_void_p, U8, C.POINTER(C.POINTER(U8)),
                      C.POINTER(C.c_size_t))
OBSERVER = C.CFUNCTYPE(None, C.c_void_p, C.POINTER(Output))


class Callbacks(C.Structure):
    _fields_ = [("resource", RESOURCE), ("output", OBSERVER), ("opaque", C.c_void_p)]


@pytest.fixture(scope="module")
def sound_native(tmp_path_factory):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("native C compiler required")
    directory = tmp_path_factory.mktemp("agi-runtime-sound")
    bridge = directory / "sizes.c"
    bridge.write_text('#include "runtime_sound.h"\n'
                      'size_t sound_state_size(void){return sizeof(AgiRuntimeSound);}\n'
                      'size_t sound_output_size(void){return sizeof(AgiRuntimeSoundOutput);}\n')
    library = directory / "sound.so"
    subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                    "-shared", "-fPIC", "-I", str(NATIVE), str(bridge),
                    str(NATIVE / "runtime_sound.c"), "-o", str(library)],
                   check=True, capture_output=True, text=True)
    lib = C.CDLL(str(library))
    ptr, state, flags, cb = C.c_void_p, C.POINTER(State), C.POINTER(U8), C.POINTER(Callbacks)
    signatures = {
        "sound_state_size": ([], C.c_size_t), "sound_output_size": ([], C.c_size_t),
        "agi_runtime_sound_init": ([state], None),
        "agi_runtime_sound_validate": ([ptr, C.c_size_t, C.POINTER(Info)], C.c_int),
        "agi_runtime_sound_state_valid": ([state, cb], C.c_int),
        "agi_runtime_sound_start": ([state, U8, U8, U8, flags, cb], C.c_int),
        "agi_runtime_sound_tick": ([state, flags, U8, cb], C.c_int),
        "agi_runtime_sound_stop": ([state, flags, cb], C.c_int),
    }
    for name, (args, result) in signatures.items():
        getattr(lib, name).argtypes = args
        getattr(lib, name).restype = result
    assert lib.sound_state_size() == C.sizeof(State)
    assert lib.sound_output_size() == C.sizeof(Output)
    return lib


def payload(*channels):
    """Each tuple is (duration, raw tone word, control byte)."""
    streams = []
    for channel in (*channels, *([[]] * (4 - len(channels)))):
        streams.append(b"".join(d.to_bytes(2, "little") + t.to_bytes(2, "little")
                                + bytes([a]) for d, t, a in channel) + b"\xff\xff")
    offsets, at = [], 8
    for data in streams:
        offsets.append(at.to_bytes(2, "little"))
        at += len(data)
    return b"".join(offsets + streams)


def raw(value):
    return C.string_at(C.addressof(value), C.sizeof(value))


class Sound:
    def __init__(self, lib, data, *, observe=True):
        self.lib, self.state, self.flags = lib, State(), (U8 * 256)()
        self.flags[9] = 1
        self.blobs, self.outputs, self.reads = {}, [], []
        self.set_blob(1, data)

        @RESOURCE
        def resource(_opaque, number, result, length):
            self.reads.append(number)
            if number not in self.blobs:
                return 0
            blob, size = self.blobs[number]
            result[0] = C.cast(blob, C.POINTER(U8))
            length[0] = size
            return 1

        @OBSERVER
        def output(_opaque, result):
            result = result.contents
            self.outputs.extend((e.sequence, e.tick, e.kind, e.channel, e.value, e.enabled)
                                for e in result.events[:result.count])

        self.callbacks = Callbacks(resource, output if observe else OBSERVER(), None)
        lib.agi_runtime_sound_init(C.byref(self.state))

    def set_blob(self, number, data):
        self.blobs[number] = (C.create_string_buffer(data), len(data))

    def start(self, *, resource=1, flag=8, device=0):
        return self.lib.agi_runtime_sound_start(C.byref(self.state), resource, flag, device,
                                                 self.flags, C.byref(self.callbacks))

    def tick(self, count=1, *, attenuation=0):
        for _ in range(count):
            result = self.lib.agi_runtime_sound_tick(C.byref(self.state), self.flags,
                                                    attenuation, C.byref(self.callbacks))
            if result:
                return result
        return 0

    def stop(self):
        return self.lib.agi_runtime_sound_stop(C.byref(self.state), self.flags,
                                               C.byref(self.callbacks))

    def valid(self):
        return self.lib.agi_runtime_sound_state_valid(C.byref(self.state),
                                                      C.byref(self.callbacks))

    def checkpoint(self):
        return raw(self.state), bytes(self.flags), list(self.outputs)

    def commands(self, *, tick=None, channel=None):
        return [e[4] for e in self.outputs if e[2] == 2
                and (tick is None or e[1] == tick)
                and (channel is None or e[3] == channel)]


def test_first_record_and_terminator_have_distinct_ticks(sound_native):
    s = Sound(sound_native, payload([(5, 0x8037, 0x90)]))
    assert s.start() == 0 and s.state.remaining == 6 and s.flags[8] == 0
    assert s.tick() == 0 and s.valid() == 0
    assert s.outputs == [(1, 1, 1, 0, 10560, 1)]
    assert s.state.channels[0].countdown == s.state.remaining == 5
    assert s.tick(4) == 0 and s.state.active == 1 and len(s.outputs) == 1
    assert s.tick() == 0 and s.state.active == 0 and s.flags[8] == 1
    assert s.outputs[-1] == (2, 6, 1, 0, 0, 0)


def test_zero_duration_takes_65536_ticks_between_reads(sound_native):
    s = Sound(sound_native, payload([(0, 0x8037, 0x90)]), observe=False)
    assert s.start() == 0 and s.state.remaining == 65537
    assert s.tick() == 0 and s.state.channels[0].countdown == 65536
    assert s.tick(65535) == 0 and s.state.active == 1 and s.state.remaining == 1
    assert s.tick() == 0 and s.state.ticks == 65537 and s.state.active == 0
    assert s.flags[8] == 1


@pytest.mark.parametrize("when", ["before", "during"])
def test_f9_gate_stops_without_consuming_resource(sound_native, when):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    if when == "before":
        s.flags[9] = 0
    assert s.start() == 0 and s.state.active == 1 and s.flags[8] == 0
    if when == "during":
        assert s.tick() == 0
        s.flags[9] = 0
    reads = len(s.reads)
    s.blobs.clear()
    assert s.tick() == 0 and len(s.reads) == reads
    assert s.state.active == 0 and s.flags[8] == 1
    assert s.outputs[-1][-4:] == (1, 0, 0, 0)


def test_new_sound_completes_old_flag_then_clears_new(sound_native):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    assert s.start(flag=7) == 0 and s.tick() == 0
    assert s.start(flag=8) == 0 and (s.flags[7], s.flags[8]) == (1, 0)
    assert s.outputs[-1][-4:] == (1, 0, 0, 0)
    assert s.start(flag=8) == 0 and s.flags[8] == 0
    assert s.state.channels[0].countdown == 1


def test_inactive_stop_does_not_repeat_completion(sound_native):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    assert s.start() == s.stop() == 0
    s.flags[8] = 0
    count = len(s.outputs)
    assert s.stop() == 0 and s.flags[8] == 0 and len(s.outputs) == count
    assert s.state.last_output.count == 0


@pytest.mark.parametrize("device,completion", [(0, 2), (8, 2), (1, 5), (2, 5), (255, 5)])
def test_device_selects_channel_participation(sound_native, device, completion):
    data = payload(*[[(n, 0x8037, 0x90)] for n in (1, 2, 3, 4)])
    s = Sound(sound_native, data)
    assert s.start(device=device) == 0 and s.state.remaining == completion
    assert s.tick(completion - 1) == 0 and s.state.active == 1
    assert s.tick() == 0 and s.state.active == 0 and s.flags[8] == 1
    if device not in (0, 8):
        assert s.commands()[-4:] == [0x9F, 0xBF, 0xDF, 0xFF]


def test_tone_latch_data_and_noise_latch_order(sound_native):
    s = Sound(sound_native, payload([(2, 0x8037, 0x95)], [], [], [(2, 0xE037, 0xF5)]))
    assert s.start(device=1) == 0 and s.tick() == 0
    assert s.commands(tick=1, channel=0) == [0x80, 0x37, 0x93]
    assert s.commands(tick=1, channel=3) == [0xE0, 0xF5]
    assert s.state.channels[0].tone == 0x8037
    assert s.state.channels[3].tone == 0xE037


def test_envelope_deltas_are_from_base_not_accumulated(sound_native):
    s = Sound(sound_native, payload([(10, 0x8037, 0x95)]))
    assert s.start(device=1) == 0 and s.tick(6) == 0
    assert [s.commands(tick=t, channel=0)[-1] for t in range(1, 7)] == [
        0x93, 0x92, 0x93, 0x94, 0x95, 0x95]
    assert s.state.channels[0].base_attenuation == 5 and s.valid() == 0


def test_envelope_clamps_and_terminator_preserves_last_value(sound_native):
    s = Sound(sound_native, payload([(100, 0x8037, 0x90)]))
    assert s.start(device=1) == 0 and s.tick(68) == 0
    c = s.state.channels[0]
    assert s.commands(tick=1, channel=0)[-1] == 0x90
    assert c.envelope_index == 0xFFFFFFFF and c.envelope_value == c.base_attenuation == 13
    assert s.commands(tick=68, channel=0) == [0x9D]
    assert s.tick() == 0 and s.commands(tick=69, channel=0) == [0x9D]


def test_new_tone_resets_tone_channel_envelope(sound_native):
    s = Sound(sound_native, payload([(2, 0x8037, 0x95), (4, 0x8110, 0x99)]))
    assert s.start(device=1) == 0 and s.tick(3) == 0
    assert s.commands(tick=3, channel=0) == [0x81, 0x10, 0x97]
    assert s.state.channels[0].envelope_index == 1


@pytest.mark.parametrize("device,adjust,expected", [(1, 2, 0x95), (2, 2, 0x97),
                                                     (1, 255, 0x9F), (2, 255, 0x9F)])
def test_global_and_device_attenuation_order(sound_native, device, adjust, expected):
    s = Sound(sound_native, payload([(5, 0x8037, 0x95)]))
    assert s.start(device=device) == 0 and s.tick(attenuation=adjust) == 0
    assert s.commands(tick=1, channel=0)[-1] == expected


def test_silent_event_skips_envelope_and_adjustments(sound_native):
    s = Sound(sound_native, payload([(5, 0x8037, 0x9F)]))
    assert s.start(device=2) == 0 and s.tick(attenuation=255) == 0
    assert s.commands(tick=1, channel=0)[-1] == 0x9F
    assert s.state.channels[0].envelope_index == 0
    pc = Sound(sound_native, payload([(5, 0x8037, 0x9F)]))
    assert pc.start() == 0 and pc.tick() == 0
    assert pc.outputs == [(1, 1, 1, 0, 0, 0)]


def test_empty_resource_finishes_on_first_tick(sound_native):
    s = Sound(sound_native, payload())
    assert s.start(device=1) == 0 and s.state.active == 1 and s.flags[8] == 0
    assert s.tick() == 0 and s.state.active == 0 and s.flags[8] == 1
    assert s.commands() == [0x9F, 0xBF, 0xDF, 0xFF] * 2


def test_validate_metadata_and_failure_are_atomic(sound_native):
    data = payload([(2, 0x8037, 0x90), (0, 0x8110, 0x94)])
    info = Info()
    assert sound_native.agi_runtime_sound_validate(data, len(data), C.byref(info)) == 0
    assert list(info.durations) == [65539, 1, 1, 1]
    before = raw(info)
    bad = bytearray(data)
    bad[0:2] = b"\x00\x00"
    assert sound_native.agi_runtime_sound_validate(bytes(bad), len(bad), C.byref(info)) == -2
    assert raw(info) == before
    assert sound_native.agi_runtime_sound_validate(data, 2 * 1024 * 1024 + 1, C.byref(info)) == -2
    assert raw(info) == before


@pytest.mark.parametrize("bad", [b"", b"12345678", b"\x08\x00" * 4 + b"\x01\x00\x80",
                                  b"\xff\xff" * 4 + b"\xff\xff"])
def test_failed_new_resource_preserves_playing_state(sound_native, bad):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    assert s.start(flag=7) == 0 and s.tick() == 0
    s.set_blob(2, bad)
    before = s.checkpoint()
    assert s.start(resource=2, flag=8) == -2 and s.checkpoint() == before


def test_missing_resource_at_tick_is_atomic(sound_native):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    assert s.start() == 0
    s.blobs.clear()
    before = s.checkpoint()
    assert s.tick() == -2 and s.checkpoint() == before


@pytest.mark.parametrize("corruption", ["envelope", "offset", "remaining", "clock"])
def test_corrupt_state_is_rejected_without_commit(sound_native, corruption):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    assert s.start() == 0
    if corruption == "envelope":
        s.state.channels[0].envelope_index = 900
    elif corruption == "offset":
        s.state.channels[0].offset = 100000
    elif corruption == "remaining":
        s.state.channels[0].remaining = 0
    else:
        s.state.ticks = (1 << 64) - 1
    before = s.checkpoint()
    assert s.tick() < 0 and s.checkpoint() == before


def test_snapshot_state_admission_checks_record_boundaries(sound_native):
    s = Sound(sound_native, payload([(20, 0x8037, 0x90)]))
    assert s.start() == 0 and s.valid() == 0
    s.state.channels[0].offset += 1
    assert s.valid() == -3


def test_observation_callback_does_not_change_sound_state(sound_native):
    data = payload([(5, 0x8037, 0x95)], [], [], [(3, 0xE037, 0xF8)])
    observed, silent = Sound(sound_native, data), Sound(sound_native, data, observe=False)
    assert observed.start(device=2) == silent.start(device=2) == 0
    for _ in range(7):
        assert observed.tick() == silent.tick() == 0
        assert raw(observed.state) == raw(silent.state)
        assert bytes(observed.flags) == bytes(silent.flags)
        assert observed.valid() == silent.valid() == 0
    assert observed.outputs and not silent.outputs
