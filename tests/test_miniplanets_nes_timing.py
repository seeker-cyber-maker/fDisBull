"""Audio timing gates keep latency visible and reject impossible raw counters."""
import importlib.util
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('nes_tempo', SCRIPTS/'check_miniplanets_nes_timing.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def sample(due, served, entries, ticks, physical):
    return dict(due=due, served=served, interrupt=entries, tick=ticks,
                physical=physical, catchup=0, late_calls=0, max_owed=4, late_requests=0)


def test_clock_catchup_can_finish_more_than_four_slots_in_a_hostframe():
    # Four old credits plus two newly due credits can finish in an old
    # in-flight entry and the next entry. It must not look like a torn read.
    result = CHECK.clock_statistics([
        sample(100, 96, 96, 95, 70), sample(102, 102, 102, 101, 71)], 1, 60)
    assert not result['counter_discontinuities']
    assert result['observed_per_hostframe_peaks']['services'] == 6
    assert result['scheduler_debt']['before'] == 4
    assert result['classification'] == 'failed-tempo'


def test_balanced_clock_debt_does_not_erase_a_slow_wallclock_window():
    rows = [sample(100, 100, 100, 99, 70)]
    rows += [sample(100+2*i, 100+i, 100+i, 99+i, 70+i) for i in range(1, 11)]
    result = CHECK.clock_statistics(rows, 10, 60)
    assert not result['counter_discontinuities']
    assert result['scheduler_debt']['after'] == 10
    assert result['counter_deltas']['due'] == 20
    assert result['counter_deltas']['served'] == 10
    assert result['classification'] == 'failed-tempo'


def test_counter_wrap_is_valid_but_a_torn_word_is_unknown():
    good = CHECK.clock_statistics([
        sample(65534, 65534, 65534, 65534, 70), sample(0, 0, 0, 0, 72)], 1, 60)
    assert good['classification'] == 'passed'
    torn = CHECK.clock_statistics([
        sample(254, 254, 254, 254, 70), sample(256, 0, 256, 256, 72)], 1, 60)
    assert torn['classification'] == 'inconclusive-counter-discontinuity'
    assert torn['counter_discontinuities']


def atomic_rows(*,slow_service=False,slow_source=False,torn=False):
    rows=[]
    for frame in range(3001):
        calls=frame if slow_service else frame*2
        ticks=(calls*64828)//65536
        if slow_source:ticks=(ticks*3)//4
        row=sample(calls&65535,calls&65535,calls&65535,ticks&65535,frame&65535)
        if torn and frame==128:row['served']=511
        rows.append(row)
    return rows


def test_atomic_protocol_keeps_raw_word_tears_unknown_while_qualifying_low_bytes():
    fps=CHECK.SOURCE_TIMER_HZ/(2*64828/65536)
    result,_=CHECK.atomic_clock_statistics(atomic_rows(torn=True),3000,fps)
    assert result['classification']=='passed'
    assert result['counter_deltas']['served']==6000
    assert result['raw_word_observation_status']=='torn-or-unknown-high-words-present'
    assert result['raw_word_inconsistencies'][0]['raw16']==511


def test_atomic_protocol_rejects_balanced_but_slow_service_and_source_clocks():
    fps=CHECK.SOURCE_TIMER_HZ/(2*64828/65536)
    for options in ({'slow_service':True},{'slow_source':True}):
        result,_=CHECK.atomic_clock_statistics(atomic_rows(**options),3000,fps)
        assert result['scheduler_debt']['after']==0
        assert result['classification']=='failed-tempo'
