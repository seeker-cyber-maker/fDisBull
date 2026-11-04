"""Raw hardware-input contracts preserve source entropy and transaction order."""
import hashlib

import pytest

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_hardware import SOURCE, configuration, input_batch
from fdisbull.shadowrun_snes_rng import SOURCE as RNG_SOURCE

PREFIX = '''typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;
u8 rom8(u8 region,u32 offset); u8 task_shared[65536],task_rng_tainted;
u16 scene_read(u16 at) {return (u16)task_shared[at]|((u16)task_shared[at+1U]<<8);}
void scene_write(u16 at,u16 value) {task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);}
'''
RNG_PREFIX = 'typedef unsigned char u8;\ntypedef unsigned int u16;\ntypedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n'


def machine():
    rom = bytes(0x455d) + bytes(range(256))
    source = PREFIX + RNG_SOURCE.read_text().replace(RNG_PREFIX, '') + SOURCE.read_text()
    return GameMachine(author_program(source,
        [{'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()}]), {0: rom})


def row(caller=3, context=0x22, **changes):
    return {'caller': caller, 'context': context, 'nmi_low': 0x34,
            'nmi_high': 0x12, 'beam_h': 0x56, 'beam_v': 0x78} | changes


def seed(m, value):
    shared = m.snapshot()['task_shared']
    shared[0x1d04] = value
    m.set_state({'task_shared': shared})


def test_recorded_raw_bytes_compute_the_source_word_and_advance_own_seed():
    m = machine();seed(m, 5)
    m.set_state(configuration('recorded') | input_batch([row()], ordinal=0))
    m.call('opening_hardware_begin');assert m.snapshot()['hardware_status'] == 1
    m.call('opening_hardware_rng', 3, 0x22)
    state = m.snapshot()
    assert (state['hardware_status'], state['hardware_result'], state['hardware_ordinal']) == (1, 0x7531, 1)
    assert state['task_shared'][0x1d04] == 0x0d
    assert state['task_shared'][:2] == [0x31, 0x75]
    m.call('opening_hardware_finish');assert m.snapshot()['hardware_status'] == 1
    # The following call is refused instead of repeating the recording.
    before = m.snapshot()['task_shared']
    m.call('opening_hardware_rng', 3, 0x22)
    assert m.snapshot()['hardware_status'] == 0
    assert m.snapshot()['hardware_ordinal'] == 1 and m.snapshot()['task_shared'] == before


@pytest.mark.parametrize('caller,context', [(1, 0xffff), (3, 0x24)])
def test_wrong_call_or_task_does_not_consume_a_reading(caller, context):
    m=machine();m.set_state(configuration('recorded') | input_batch([row()], ordinal=0))
    before=m.snapshot()['task_shared']
    m.call('opening_hardware_rng',caller,context)
    state=m.snapshot()
    assert state['hardware_status'] == state['hardware_input_index'] == state['hardware_ordinal'] == 0
    assert state['task_shared'] == before


def test_batch_ordinal_excess_rows_and_tainted_source_seed_refuse():
    m=machine();m.set_state(configuration('recorded') | input_batch([row()], ordinal=1))
    m.call('opening_hardware_begin');assert m.snapshot()['hardware_status'] == 0
    m.set_state(input_batch([row()],ordinal=0))
    m.call('opening_hardware_begin');assert m.snapshot()['hardware_status'] == 1
    m.call('opening_hardware_finish');assert m.snapshot()['hardware_status'] == 0
    m.set_state({'task_rng_tainted': 1})
    m.call('opening_hardware_begin');assert m.snapshot()['hardware_status'] == 0
    m.call('opening_hardware_rng',3,0x22)
    assert m.snapshot()['hardware_ordinal'] == 0


def test_counter_low_and_high_remain_separate_raw_reads():
    m=machine();m.set_state(configuration('recorded') | input_batch([
        row(nmi_low=255,nmi_high=1,beam_h=0,beam_v=0)],ordinal=0))
    m.call('opening_hardware_rng',3,0x22)
    assert (m.snapshot()['hardware_result'],m.snapshot()['task_shared'][0x1d04]) == (0xfeff,0xfe)


def test_bounded_sampler_rejects_and_consumes_next_raw_record():
    m=machine();seed(m, 0)
    # First result 3 is outside [0,3); seed becomes 4, next result 1 is accepted.
    rows=[row(2,0xffff,nmi_low=3,nmi_high=0,beam_h=0,beam_v=7),
          row(2,0xffff,nmi_low=5,nmi_high=0,beam_h=0,beam_v=0)]
    m.set_state(configuration('recorded') | input_batch(rows,ordinal=0) | {'hardware_bound':3})
    m.call('opening_hardware_bounded',0xffff)
    s=m.snapshot()
    assert (s['hardware_status'],s['hardware_result'],s['hardware_input_index'],s['hardware_ordinal']) == (1,1,2,2)
    assert s['task_shared'][2:6] == [3,0,3,0]


def test_seeded_input_is_repeatable_and_part_of_runtime_state():
    a,b=machine(),machine()
    for m in (a,b):m.set_state(configuration('seeded',0x12345678))
    words=[]
    for _ in range(8):
        for m in (a,b):m.call('opening_hardware_rng',3,0x22)
        assert a.snapshot() == b.snapshot()
        words.append(a.snapshot()['hardware_result'])
    assert len(set(words)) > 1
    assert a.snapshot()['hardware_ordinal'] == 8
    other=machine();other.set_state(configuration('seeded',0x12345679))
    other.call('opening_hardware_rng',3,0x22)
    assert other.snapshot()['hardware_result'] != words[0]


@pytest.mark.parametrize('record', [row() | {'result':0},row() | {'seed_before':0},
    row(context=1),row(1,0),row(4,0xffff),row(nmi_low=256),row(beam_h=True)])
def test_consumable_batch_rejects_game_outputs_and_invalid_raw_fields(record):
    with pytest.raises(ValueError):input_batch([record],ordinal=0)


@pytest.mark.parametrize('mode,seed_value', [('invalid',1),('seeded',0),('seeded',1<<32),('seeded',True)])
def test_configuration_rejects_ambiguous_or_invalid_seed_policy(mode,seed_value):
    with pytest.raises(ValueError):configuration(mode,seed_value)


def test_batch_capacity_and_ordinal_cannot_wrap():
    for records,ordinal in (([row()]*129,0),([row()],0xffffffff),([],True)):
        with pytest.raises(ValueError):input_batch(records,ordinal=ordinal)


def test_power_of_two_bound_keeps_the_source_rejection_mask():
    m=machine();m.set_state(configuration('recorded') | input_batch([
        row(2,0xffff,nmi_low=3,nmi_high=0,beam_h=0,beam_v=7),
        row(2,0xffff,nmi_low=5,nmi_high=0,beam_h=0,beam_v=0)],ordinal=0) | {'hardware_bound':2})
    m.call('opening_hardware_bounded',0xffff)
    s=m.snapshot()
    assert (s['hardware_result'],s['hardware_input_index'],s['hardware_status'])==(1,2,1)
    assert s['task_shared'][4:6]==[3,0]
