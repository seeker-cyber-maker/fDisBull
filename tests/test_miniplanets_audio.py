"""Authored stream fixtures; no original game or audio bytes are fixtures."""
import copy

import pytest

from fdisbull.miniplanets_audio import (
    AudioFormatError, NES_PHASE_STEP, SOURCE_TIMER_HZ, SonaEngine,
    _dpcm, decode_sona, encode_sona, period_table, pitch_value, recover_audio,
)


def synthetic_audio(effect=b'\xe5\x05\x00\x15\x04\xd0\x25\xd0\xff'):
    # One authored note followed by rest; every ID uses that same tiny fixture.
    return {'tracks':[{'event_program':decode_sona(b'\xd0\xfd' if i<13 else effect)}
                      for i in range(32)]}


def test_complete_decode_preserves_offsets_args_and_ticks():
    data=b'\xfa\x20\xfc\x00\x01\x10\x73\x24\xd2\x20\xfe\x00\xfd'
    program=decode_sona(data)
    assert program['source_bytes']==len(data)
    assert program['stream_ticks']==259
    assert program['loop_offset']==3 and program['looped']
    assert program['events'][3]['pitches']==[[0x73,0x24]]
    assert program['events'][4]['duration']==3
    assert program['events'][-1]['target']==3
    assert program['events'][-1]['next_offset']==len(data)
    assert encode_sona(program)==data


@pytest.mark.parametrize('change',[
    lambda p:p['events'][0].update(value=256),
    lambda p:p['events'][0].update(value=True),
    lambda p:p['events'][1].update(target=99),
    lambda p:p['events'][-1].update(next_offset=999),
    lambda p:p.update(source_sha256='0'*64),
    lambda p:p['events'][2].update(kind='volume'),
    lambda p:p['events'][0].update(offset=0.0),
    lambda p:p['events'][1].update(target=True),
    lambda p:p.update(source_bytes=float(p['source_bytes'])),
])
def test_audio_output_compiler_validates_widths_targets_and_full_extent(change):
    program=decode_sona(b'\xfa\x20\xfc\x10\x04\xd0\xfd')
    changed=copy.deepcopy(program)
    change(changed)
    with pytest.raises(AudioFormatError):encode_sona(changed)


@pytest.mark.parametrize('data,reason',[
    (b'\x15','truncated'),(b'\xf5\xff','unsupported'),
    (b'\x15\x60\xff','noncanonical'),(b'\xff\x00','follow'),
    (b'\xd0','no loop or stop'),(b'','size'),
])
def test_invalid_or_unsupported_streams_fail_closed(data,reason):
    with pytest.raises(AudioFormatError,match=reason):decode_sona(data)


def test_type_priority_zero_is_accepted_and_status_is_latched():
    engine=SonaEngine(synthetic_audio())
    engine.request(2,1)
    assert engine.streams[1]['track']==13
    assert not engine.busy
    engine.tick()
    assert not engine.busy
    engine.tick()
    assert engine.busy
    assert [e['kind'] for e in engine.events]==['lock','instrument','note_on','delay']
    assert {e['clock'] for e in engine.events}=={2}
    engine.tick();engine.tick()
    assert engine.busy and engine.events[-2]['kind']=='note_off'
    engine.tick();engine.tick()
    assert not engine.busy and engine.streams[1] is None


def test_priority_rejects_lower_and_accepts_equal_replacement():
    engine=SonaEngine(synthetic_audio())
    engine.request(2,19)
    engine.tick();engine.tick()
    stream=engine.streams[1]
    engine.request(2,1)
    assert engine.streams[1] is stream
    engine.request(2,19)
    assert engine.streams[1] is not stream
    assert engine.streams[1]['wait']==1
    engine.request(1,4)
    assert engine.streams[1] is None and engine.streams[0]['track']==3
    # The source playback-status byte is updated by the next SFX tick.
    assert engine.busy
    engine.tick();engine.tick()
    assert not engine.busy


def test_nes_interrupt_clock_follows_measured_original_timer():
    engine=SonaEngine(synthetic_audio())
    for _ in range(12000):engine.nes_tick()
    assert engine.clock==12000*NES_PHASE_STEP//65536
    assert engine.nes_phase==12000*NES_PHASE_STEP%65536
    nes_rate=2*1789772.7272727273/29780.5
    assert abs(nes_rate*NES_PHASE_STEP/65536-SOURCE_TIMER_HZ)/SOURCE_TIMER_HZ<0.00001


def test_bgm_default_stream_rate_is_half_timer_rate():
    engine=SonaEngine(synthetic_audio())
    engine.request(1,1)
    engine.tick()
    assert engine.events==[]
    engine.tick()
    assert [(e['clock'],e['kind']) for e in engine.events]==[(2,'delay')]
    engine.tick();engine.tick()
    assert [(e['clock'],e['kind']) for e in engine.events[-2:]]==[(4,'loop'),(4,'delay')]


def test_non_progressing_loop_is_bounded():
    engine=SonaEngine(synthetic_audio(b'\xfc\xfd'))
    engine.request(2,1)
    engine.tick()
    with pytest.raises(AudioFormatError,match='non-progressing'):engine.tick()


def test_pitch_encoding_covers_absolute_fine_relative_and_hold():
    assert pitch_value([4],0)==4*12*16
    assert pitch_value([4],0,psg=True)==6*12*16
    assert pitch_value([0x73,0x24],0)==(4*12+4)*16+3
    assert pitch_value([0x89],100)==100+13*16
    assert pitch_value([0x8d],500)==500-13*16
    assert pitch_value([0xf3,0x81],500)==500-(12*16+3)
    assert pitch_value([0x80],123)==123


def test_source_psg_periods_preserve_real_octave_and_quarter_steps():
    # A physical PSG divisor of851 is ~131.44Hz, irrespective of MML naming.
    table=period_table(psg=True,frequencies=[851]*48)
    assert table[24*16]==850
    assert table[36*16]==424
    assert table[24*16+1]==table[24*16+3]==850
    assert len(table)==1536 and all(8<=value<=2047 for value in table)


def test_dpcm_transfer_length_and_quiet_center_are_bounded():
    encoded=_dpcm(bytes([127])*400)
    assert (len(encoded)-1)%16==0 and len(encoded)<=4081
    bits=[(byte>>bit)&1 for byte in encoded for bit in range(8)]
    assert abs(sum(bits)/len(bits)-0.5)<0.05


def test_unqualified_rom_is_refused_before_any_asset_is_returned():
    with pytest.raises(AudioFormatError,match='qualified'):recover_audio(b'authored test input')
