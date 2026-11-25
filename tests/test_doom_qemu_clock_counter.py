"""Pure host checks for the Doom QEMU clock counter diagnostic."""
import pytest

from test_doom_timing_bda_paired_native import _qemu_machine_counter_interval


def observation(counter, virtual_ns, *, epoch="epoch-1"):
    return dict(
        clock_profile=dict(profile="virtual"),
        session=dict(state="stopped"),
        epoch=epoch,
        virtual_ns=virtual_ns,
        counter=dict(state="observed", source="query-replay.icount",
                     unit="instructions", value=counter),
    )


def test_machine_counter_interval_reports_whole_machine_icount_without_cycle_claim():
    result = _qemu_machine_counter_interval(
        observation(100, 1_000), observation(145, 2_000))

    assert result == dict(
        scope="whole QEMU machine",
        source="query-replay.icount",
        unit="instructions",
        start=100,
        end=145,
        delta=45,
        virtual_ns_start=1_000,
        virtual_ns_end=2_000,
        virtual_ns_delta=1_000,
        interpretation_limit=("execution instruction count only; not retired instructions "
                              "or hardware cycles"),
    )


@pytest.mark.parametrize("bad_counter", [
    dict(state="unsupported", source=None, unit="instructions", value=None),
    dict(state="observed", source="other", unit="instructions", value=1),
    dict(state="observed", source="query-replay.icount", unit="cycles", value=1),
    dict(state="observed", source="query-replay.icount", unit="instructions", value=True),
])
def test_machine_counter_interval_fails_closed_without_supported_counter(bad_counter):
    start = observation(100, 1_000)
    end = observation(110, 2_000)
    end["counter"] = bad_counter

    with pytest.raises(ValueError, match="counter is unsupported"):
        _qemu_machine_counter_interval(start, end)


def test_machine_counter_interval_refuses_epoch_or_counter_regression():
    with pytest.raises(ValueError, match="epochs"):
        _qemu_machine_counter_interval(
            observation(100, 1_000), observation(110, 2_000, epoch="epoch-2"))
    with pytest.raises(ValueError, match="regressed"):
        _qemu_machine_counter_interval(observation(101, 1_000), observation(100, 2_000))
