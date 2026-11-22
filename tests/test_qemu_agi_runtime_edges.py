"""Independent authored edge cases for the portable AGI runtime.

These tests execute production C through the resource-only bridge. Reference
facts come from pinned Sarien text.c and the AGI 2.917 behavioral specification:
https://peterkelly.github.io/agi-re/spec/sound.html
https://peterkelly.github.io/agi-re/spec/runtime_state.html
https://peterkelly.github.io/agi-re/spec/session_and_persistence.html
No original game resources or a second opcode interpreter are embedded here.
"""
from __future__ import annotations

import ctypes as C
import shutil
import subprocess

import pytest

from test_qemu_agi_runtime import Engine, NATIVE, VIEW, native  # noqa: F401


@pytest.fixture(scope="module")
def state_layout(tmp_path_factory):
    """Read public POD fields using this build's C offsetof, without an executor."""
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("native C compiler required")
    directory = tmp_path_factory.mktemp("agi-runtime-edge-layout")
    source, library = directory / "layout.c", directory / "layout.so"
    source.write_text('#include "runtime.h"\n#include <stddef.h>\n'
                      'size_t offset(unsigned n){switch(n){'
                      'case 0:return offsetof(AgiRuntimeState,text);'
                      'case 1:return offsetof(AgiRuntimeState,text_fg);'
                      'case 2:return offsetof(AgiRuntimeState,text_bg);'
                      'case 3:return offsetof(AgiRuntimeState,dialogue);'
                      'case 4:return offsetof(AgiRuntimeState,hold_key);'
                      'case 5:return offsetof(AgiRuntimeState,simple_save);'
                      'case 6:return offsetof(AgiRuntimeState,simple_description);'
                      'default:return (size_t)-1;}}\n')
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(NATIVE), str(source), "-o", str(library)], check=True,
                   capture_output=True, text=True)
    lib = C.CDLL(str(library))
    lib.offset.argtypes, lib.offset.restype = [C.c_uint], C.c_size_t
    return [lib.offset(n) for n in range(7)]


@pytest.fixture(scope="module")
def timing_api(native):
    # TestEngine's first member is the public AgiRuntime. These are production
    # APIs, not a second implementation of clock or sound behavior.
    for name in ("agi_runtime_clock_ticks", "agi_runtime_sound_ticks",
                 "agi_runtime_set_sound_device"):
        function = getattr(native, name)
        function.argtypes, function.restype = [C.c_void_p, C.c_uint32], C.c_bool
    return native


def text_planes(engine, layout):
    address = engine.lib.rt_state(engine.ptr)
    return tuple(C.string_at(address + offset, 25 * 40) for offset in layout[:3])


def scalar_field(engine, offset):
    address = engine.lib.rt_state(engine.ptr)
    return C.c_uint32.from_address(address + offset).value


def sound_with_one_event(duration: int) -> bytes:
    """Four authored streams, each one event followed by its terminator."""
    event = duration.to_bytes(2, "little") + bytes([0x04, 0x8A, 0x90, 0xFF, 0xFF])
    offsets = b"".join((8 + n * len(event)).to_bytes(2, "little") for n in range(4))
    return offsets + event * 4


def test_escaped_substitution_stays_literal(native):
    with Engine(native, [3, 1, 123, 101, 1, 0],
                messages={(0, 1): r"\%v1"}) as e:
        assert e.run() == 0 and e.probe(2) == 4
        assert native.rt_pending_text(e.ptr) == b"%v1"


def test_fixed_width_variable_expansion_keeps_low_digits(native):
    # Pinned Sarien agi_sprintf selects the rightmost requested digits.
    with Engine(native, [3, 1, 123, 101, 1, 0],
                messages={(0, 1): "%v1|2"}) as e:
        assert e.run() == 0 and e.probe(2) == 4
        assert native.rt_pending_text(e.ptr) == b"23"


def test_zero_sound_duration_wraps_instead_of_completing_at_start(native):
    # Zero is a 16-bit countdown wrap, not an empty or zero-time event.
    with Engine(native, [98, 1, 99, 1, 8, 0],
                blobs={(2, 1): sound_with_one_event(0)}) as e:
        assert e.run() == 0
        assert (e.probe(26), e.probe(1, 8)) == (1, 0)
        assert native.rt_tick(e.ptr, 1)
        assert (e.probe(26), e.probe(1, 8)) == (1, 0)


def test_sound_gate_is_rechecked_during_playback(native):
    with Engine(native, [98, 1, 99, 1, 8, 13, 9, 0],
                blobs={(2, 1): sound_with_one_event(100)}) as e:
        assert e.run() == 0 and e.probe(26) == 1
        assert native.rt_tick(e.ptr, 1)
        assert (e.probe(26), e.probe(1, 8)) == (0, 1)


def test_ordered_view_discard_releases_later_family_members(native):
    # 2.917 resources retain load order within each family.
    with Engine(native, [30, 1, 30, 2, 30, 3, 32, 2, 0],
                blobs={(0, n): VIEW for n in (1, 2, 3)}) as e:
        assert e.run() == 0
        assert [e.probe(35, n) for n in (1, 2, 3)] == [1, 0, 0]


def test_resource_loads_are_recorded_for_script_checkpoint(native):
    with Engine(native, [30, 1, 171, 30, 2, 172, 0],
                blobs={(0, n): VIEW for n in (1, 2)}) as e:
        assert e.run() == 0
        # push.script remembers the active replay prefix; pop restores it.
        assert (e.probe(36), e.probe(37)) == (1, 1)


def test_new_cycle_clears_prior_input_flags(native):
    with Engine(native, [0], words={"look": 10}) as e:
        assert native.rt_cycle(e.ptr)
        assert native.rt_input(e.ptr, b"look")
        assert e.probe(1, 2) == 1
        assert e.run() == 0
        assert native.rt_cycle(e.ptr)
        assert (e.probe(1, 2), e.probe(1, 4)) == (0, 0)


def test_nonrestorable_snapshot_is_rejected_at_export(native):
    # A successful public snapshot must be acceptable as a later continuation;
    # otherwise exporting that state must explicitly report unsupported.
    with Engine(native, [101, 1, 126, 0], messages={(0, 1): "wait"}) as e:
        assert e.run() == 0 and e.probe(11) == 101
        data = C.create_string_buffer(native.rt_snapshot_size())
        exported = native.rt_snapshot(e.ptr, data, len(data))
        if not exported:
            return
        assert e.complete()
        assert e.run() == 0 and e.probe(11) == 126
        assert native.rt_restore(e.ptr, e.probe(10), data, len(data)), (
            "snapshot reported success but its own runtime rejects the emitted state"
        )


def test_snapshot_preserves_supported_horizon_above_picture(native):
    # set.horizon accepts the full operand byte; snapshot admission must agree
    # with the actor command's supported state domain.
    with Engine(native, [63, 200, 125, 126, 0]) as e:
        assert e.run() == 0 and e.probe(11) == 125
        saved = e.snapshot()
        assert e.complete()
        assert e.run() == 0 and e.probe(11) == 126
        assert native.rt_restore(e.ptr, e.probe(10), saved, len(saved))


def test_init_disk_is_a_noop_with_normal_continuation(native):
    with Engine(native, [127, 3, 1, 7, 0]) as e:
        assert e.run() == 0
        assert (e.probe(2), e.probe(0, 1), e.probe(10)) == (3, 7, 0)


def test_quit_selector_two_requires_confirmation(native):
    with Engine(native, [134, 2, 3, 1, 7, 0]) as e:
        assert e.run() == 0 and e.probe(2) == 4
        assert (e.probe(11), e.probe(12)) == (134, 3)
        assert e.complete(accepted=False)
        assert e.run() == 0 and e.probe(0, 1) == 7 and e.probe(2) == 3


def test_cancelled_interactive_inventory_returns_255(native):
    with Engine(native, [124, 0], objects=[("coin", 255)]) as e:
        native.rt_flag(e.ptr, 13, 1)
        native.rt_var(e.ptr, 25, 7)
        assert e.run() == 0 and e.probe(11) == 124
        assert e.complete(accepted=False)
        assert e.probe(0, 25) == 255


def test_first_key_binding_clears_controller_occurrence(native):
    with Engine(native, [121, 65, 0, 7, 0]) as e:
        assert native.rt_controller(e.ptr, 7) and e.probe(16, 7) == 1
        assert e.run() == 0 and e.probe(16, 7) == 0
        assert native.rt_key(e.ptr, 65, True) and e.probe(16, 7) == 1


def test_fullscreen_text_suppresses_post_logic_actor_motion(native):
    code = [30, 1, 33, 0, 41, 0, 1, 37, 0, 10, 60, 35, 0,
            3, 6, 3, 106, 0]
    with Engine(native, code, blobs={(0, 1): VIEW}) as e:
        assert native.rt_cycle(e.ptr)
        assert e.run() == 0 and e.probe(2) == 3
        assert (e.probe(19, 0), e.probe(20, 0)) == (10, 60)


def test_menu_input_respects_flag14_gate(native):
    code = [156, 1, 157, 2, 7, 158, 161, 3, 30, 1, 0]
    with Engine(native, code, messages={(0, 1): "File", (0, 2): "Save"}) as e:
        native.rt_flag(e.ptr, 14, 0)
        assert e.run() == 0
        assert (e.probe(2), e.probe(0, 30), e.probe(10)) == (3, 1, 0)


@pytest.mark.parametrize("addition", [[156, 3], [157, 3, 8]])
def test_menu_additions_after_submission_are_ignored(native, addition):
    code = [156, 1, 157, 2, 7, 158, *addition, 0]
    with Engine(native, code, messages={(0, 1): "File", (0, 2): "Save",
                                        (0, 3): "Ignored"}) as e:
        assert e.run() == 0 and e.probe(2) == 3
        assert e.probe(39) == 1


def test_pause_stops_sound_before_waiting(native):
    with Engine(native, [98, 1, 99, 1, 8, 136, 0],
                blobs={(2, 1): sound_with_one_event(100)}) as e:
        assert e.run() == 0 and e.probe(11) == 136
        assert (e.probe(26), e.probe(1, 8)) == (0, 1)
        assert e.complete()
        assert e.run() == 0 and e.probe(26) == 0


def test_script_size_resets_replay_sequence_and_checkpoint(native):
    with Engine(native, [30, 1, 171, 142, 8, 0], blobs={(0, 1): VIEW}) as e:
        assert e.run() == 0 and e.probe(2) == 3
        assert (e.probe(36), e.probe(37)) == (0, 0)


def test_nonblocking_print_consumes_flag15_once(native):
    with Engine(native, [12, 15, 101, 1, 101, 2, 0],
                messages={(0, 1): "first", (0, 2): "second"}) as e:
        assert e.run() == 0 and e.probe(2) == 4
        assert e.probe(1, 15) == 0
        assert native.rt_pending_text(e.ptr) == b"second"


def test_close_window_restores_saved_text_and_attributes(native, state_layout):
    code = [109, 2, 0, 103, 10, 8, 1, 12, 15, 151, 2, 10, 8, 10, 169, 0]
    with Engine(native, code, messages={(0, 1): "underneath", (0, 2): "window"}) as e:
        assert e.run(3) == 1
        before = text_planes(e, state_layout)
        assert e.run(1) == 1 and e.probe(38) == 1
        assert e.run() == 0 and e.probe(38) == 0
        assert text_planes(e, state_layout) == before


def test_window_restore_preserves_later_writes_outside_window(native, state_layout):
    code = [103, 0, 0, 1, 12, 15, 151, 2, 10, 8, 10, 103, 0, 0, 3, 169, 0]
    with Engine(native, code, messages={(0, 1): "A", (0, 2): "window", (0, 3): "Z"}) as e:
        assert e.run(2) == 1
        before = text_planes(e, state_layout)
        assert e.run() == 0
        expected = b"Z" + before[0][1:]
        assert text_planes(e, state_layout) == (expected, before[1], before[2])


def test_replacement_window_does_not_restore_old_window(native, state_layout):
    code = [12, 15, 151, 1, 10, 8, 10, 12, 15, 151, 2, 12, 8, 10, 169, 0]
    with Engine(native, code, messages={(0, 1): "first", (0, 2): "second"}) as e:
        before = text_planes(e, state_layout)
        assert e.run() == 0 and e.probe(38) == 0
        assert text_planes(e, state_layout) == before


def test_dialogue_flags_do_not_claim_saved_window_activity(native, state_layout):
    with Engine(native, [163, 0]) as e:
        assert e.run() == 0
        assert scalar_field(e, state_layout[3]) == 1 and e.probe(38) == 0
    with Engine(native, [12, 15, 151, 1, 10, 8, 10, 163, 164, 0],
                messages={(0, 1): "window"}) as e:
        assert e.run() == 0
        assert scalar_field(e, state_layout[3]) == 0 and e.probe(38) == 1


def test_close_window_clears_dialogue_override_without_window(native, state_layout):
    with Engine(native, [163, 169, 0]) as e:
        assert e.run() == 0
        assert scalar_field(e, state_layout[3]) == 0 and e.probe(38) == 0


def test_show_picture_closes_saved_window_and_clears_flag15(native, state_layout):
    with Engine(native, [12, 15, 151, 1, 10, 8, 10, 12, 15, 26, 0],
                messages={(0, 1): "window"}) as e:
        before = text_planes(e, state_layout)
        assert e.run() == 0
        assert (e.probe(38), e.probe(1, 15), e.probe(42)) == (0, 0, 1)
        assert text_planes(e, state_layout) == before


def test_parser_treats_braces_and_brackets_as_word_separators(native):
    with Engine(native, [0], words={"look": 10, "at": 0, "tree": 20}) as e:
        assert native.rt_input(e.ptr, b"look [at] {tree}")
        assert e.probe(13) == 2
        assert [e.probe(14, n) for n in range(2)] == [10, 20]
        assert e.probe(0, 9) == 0


def test_simple_save_owns_description_and_empty_string_disables_it(native, state_layout):
    code = [114, 1, 1, 170, 1, 114, 1, 2, 170, 1, 0]
    with Engine(native, code, messages={(0, 1): "checkpoint", (0, 2): ""}) as e:
        address = native.rt_state(e.ptr) + state_layout[6]
        assert e.run(2) == 1
        assert scalar_field(e, state_layout[5]) == 1
        assert C.string_at(address) == b"checkpoint"
        assert e.run(1) == 1 and native.rt_string(e.ptr, 1) == b""
        assert C.string_at(address) == b"checkpoint"
        assert e.run() == 0
        assert scalar_field(e, state_layout[5]) == 0
        assert C.string_at(address) == b""


def test_hold_key_counter_wraps_and_changes_release_behavior(native, state_layout):
    with Engine(native, [132] + [173] * 256 + [0]) as e:
        assert e.run(256) == 1
        assert scalar_field(e, state_layout[4]) == 255
        assert native.rt_key(e.ptr, 0x4D00, True)
        assert native.rt_key(e.ptr, 0x4D00, False)
        assert e.probe(0, 6) == 0
        assert e.run(1) == 1
        assert scalar_field(e, state_layout[4]) == 0
        assert native.rt_key(e.ptr, 0x4D00, True)
        assert native.rt_key(e.ptr, 0x4D00, False)
        assert e.probe(0, 6) == 3


def test_clock_advances_time_without_an_extra_actor_phase(native, timing_api):
    code = [30, 1, 33, 0, 41, 0, 1, 37, 0, 10, 60, 35, 0,
            3, 6, 3, 86, 0, 6, 145, 0]
    with Engine(native, code, blobs={(0, 1): VIEW}) as e:
        assert native.rt_cycle(e.ptr)
        assert e.run() == 0
        assert (e.probe(19), e.probe(24), e.probe(33)) == (11, 1, 1)
        assert timing_api.agi_runtime_clock_ticks(e.ptr, 2)
        assert (e.probe(19), e.probe(24), e.probe(25)) == (11, 1, 2)
        assert native.rt_cycle(e.ptr)
        assert e.run() == 0
        assert (e.probe(19), e.probe(24), e.probe(33)) == (12, 2, 2)
        assert timing_api.agi_runtime_clock_ticks(e.ptr, 18)
        assert (e.probe(19), e.probe(24), e.probe(25), e.probe(0, 11)) == (12, 2, 20, 1)


@pytest.mark.parametrize("device,reported,active_after_two", [(0, 1, 0), (0, 3, 0), (1, 1, 1)])
def test_sound_device_does_not_reinterpret_guest_hardware_report(native, timing_api,
                                                                device, reported, active_after_two):
    events = [duration.to_bytes(2, "little") + bytes([4, 0x8A, 0x90, 0xFF, 0xFF])
              for duration in (1, 100, 100, 100)]
    data = b"".join((8 + 7 * n).to_bytes(2, "little") for n in range(4)) + b"".join(events)
    with Engine(native, [98, 1, 99, 1, 8, 0], blobs={(2, 1): data}) as e:
        assert timing_api.agi_runtime_set_sound_device(e.ptr, device)
        assert e.probe(0, 22) == (3 if device else 1)
        native.rt_var(e.ptr, 22, reported)
        assert e.run() == 0
        assert timing_api.agi_runtime_sound_ticks(e.ptr, 2)
        assert e.probe(26) == active_after_two
        assert e.probe(1, 8) == 1 - active_after_two
        if active_after_two:
            assert timing_api.agi_runtime_sound_ticks(e.ptr, 99)
            assert (e.probe(26), e.probe(1, 8)) == (0, 1)


@pytest.mark.parametrize("immediate", [False, True])
def test_accepted_restart_preserves_disabled_sound_flag(native, immediate):
    code = [13, 9] + ([12, 16] if immediate else []) + [128, 0]
    with Engine(native, code) as e:
        if immediate:
            assert e.run(3) == 1
        else:
            assert e.run() == 0 and e.probe(11) == 128
            assert e.complete()
        assert e.probe(1, 9) == 0
        assert e.probe(1, 6) == 1
        assert e.probe(3) == 0 and e.probe(8) == 0


@pytest.mark.parametrize("accepted", [False, True])
def test_modal_print_exposes_window_and_restores_on_completion(native, state_layout, accepted):
    with Engine(native, [103, 10, 8, 1, 151, 2, 10, 8, 10, 0],
                messages={(0, 1): "underlying", (0, 2): "modal"}) as e:
        assert e.run(1) == 1
        before = text_planes(e, state_layout)
        assert e.run() == 0 and e.probe(11) == 151
        assert e.probe(38) == 1 and text_planes(e, state_layout) != before
        assert e.complete(accepted=accepted)
        assert e.probe(38) == 0
        assert text_planes(e, state_layout) == before


@pytest.mark.parametrize("opcode", [103, 104])
def test_display_initial_column_is_not_a_continuation_indent(native, state_layout, opcode):
    code = [103, 2, 5, 1, 0] if opcode == 103 else [104, 1, 2, 3, 0]
    with Engine(native, code, messages={(0, 1): "X\nY"}) as e:
        if opcode == 104:
            for index, value in ((1, 2), (2, 5), (3, 1)):
                native.rt_var(e.ptr, index, value)
        assert e.run() == 0
        text, _, _ = text_planes(e, state_layout)
        assert text[2 * 40 + 5] == ord("X")
        assert text[3 * 40] == ord("Y")
