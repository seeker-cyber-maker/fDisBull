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

import pytest

from test_qemu_agi_runtime import Engine, VIEW, native  # noqa: F401


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
