import pytest

from fdisbull.cli import respond, parser
from fdisbull.dos_services import describe_interrupt, service_catalog
from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.mark.parametrize('selector,family,name', [
    (0x688, 'digpak', 'play_sample'), (0x689, 'digpak', 'sound_status'),
    (0x68e, 'digpak', 'set_completion_callback'), (0x69f, 'digpak', 'set_pcm_volume'),
    (0x702, 'midpak', 'play_sequence'), (0x704, 'midpak', 'register_xmidi'),
    (0x705, 'midpak', 'stop_music'), (0x70b, 'midpak', 'resume_playing'),
    (0x70c, 'midpak', 'sequence_status'), (0x70f, 'midpak', 'set_relative_volume'),
])
def test_named_audio_contracts_preserve_unverified_handler_and_outcome(selector, family, name):
    result = describe_interrupt(0x66, {'ax':selector, 'ds':0x1234, 'si':0x56})
    assert result['known'] and result['name'] == name and result['family'] == family
    assert result['function'] == hex(selector)
    assert not result['runtime_observed'] and not result['handler_verified']
    assert result['outcome'] == 'unknown'
    assert result['source'].startswith('https://')


def test_audio_selector_ambiguity_and_catalog_queries():
    for registers in ({}, {'ah':6}, {'ax':[0x688,0x689]}, {'ax':0x715}, {'ax':True}):
        assert describe_interrupt(0x66, registers)['known'] is False
    answer = respond({'method':'dos-services', 'params':{'vector':0x66,
        'registers':{'ax':0x688,'ds':0x1234,'si':0x56}}})
    assert answer['ok'] and answer['result']['name'] == 'play_sample', answer
    assert answer['result']['inputs']['ds:si']['value'] == [0x1234,0x56]
    assert answer['result']['argument_layouts']['ds:si']['size'] == 12
    assert answer['result']['memory_effects_complete'] is False
    assert describe_interrupt(0x66, {'ah':7, 'al':2})['name'] == 'play_sequence'
    assert any(x['family']=='midpak' for x in service_catalog()['entries'])
    args = parser().parse_args(['dos-services','--vector','0x66','--ax','0x705'])
    assert args.vector == 0x66 and args.ax == 0x705
    assert not respond({'method':'dos-services','params':{'registers':{'ax':0x688}}})['ok']


def test_named_int66_stored_state_restart_patch_and_raw_operands(tmp_path):
    binary=tmp_path/'AUDIO.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('b88806cd66b80207cd66cb')))
    database=tmp_path/'audio.fdb'
    with Project.create(database,binary) as p:
        p.analyze(max_instructions=64)
        row=p.disassembly('1000:0003',lines=1)['instructions'][0]
        assert row['raw_operands']==row['operands']=='66h'
        assert row['interrupt_service']['name']=='play_sample'
        assert 'DIGPAK.play_sample' in row['display_operands']
        child=p.patch('1000:0001','8906')['version']
        p.analyze(version=child,max_instructions=64)
        assert p.disassembly('1000:0003',lines=1,version=child)['instructions'][0]['interrupt_service']['name']=='sound_status'
    with Project(database) as p:
        assert p.disassembly('1000:0003',lines=1,version=1)['instructions'][0]['interrupt_service']['name']=='play_sample'
