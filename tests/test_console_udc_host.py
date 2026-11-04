"""Host contract checks do not substitute a fake core for native execution."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import hashlib
import math
import struct
import sys
import wave

import pytest


SPEC = spec_from_file_location('console_udc_host', Path(__file__).parents[1] / 'scripts/check_console_udc.py')
HOST = module_from_spec(SPEC)
SPEC.loader.exec_module(HOST)


def test_instruction_checkpoint_plan_requires_explicit_phase_and_bounded_storage():
    assert HOST.checkpoint_plan(None,None,10)==[]
    assert HOST.checkpoint_plan(0x80962e,'0,3,9',10,2)==[0,3,9]
    for pc,frames,limit in [(None,'0',1),(0x80962e,None,1),(0,'0',1),
                            (0x1000000,'0',1),(True,'0',1),(0x80962e,'0',9)]:
        with pytest.raises(ValueError):HOST.checkpoint_plan(pc,frames,10,limit)
    selected=','.join(map(str,range(129)))
    assert len(HOST.checkpoint_plan(0x80962e,selected,130,1)) == 129
    with pytest.raises(ValueError):HOST.checkpoint_plan(0x80962e,selected,130,2)
    assert len(HOST.checkpoint_plan(0x80962e,','.join(map(str,range(4097))),4097,1)) == 4097
    with pytest.raises(ValueError):HOST.checkpoint_plan(0x80962e,','.join(map(str,range(6001))),6001)


def test_controller_journal_reports_duplicate_conflicts_and_consumer_disagreement():
    main = {'kind': 'main', 'serial': 4, 'held': 0x100, 'previous': 0,
            'edge': 0x100, 'actor': None, 'video_frame': 12}
    player = {**main, 'kind': 'player', 'actor': 0x42}
    conflict = {**main, 'edge': 0}
    result = HOST.controller_journal_summary([main, player, conflict], 2)
    assert result['dropped'] == 2
    assert result['duplicate_serials'] == [{'kind': 'main', 'serial': 4}]
    assert result['conflicting_serials'] == [{'kind': 'main', 'serial': 4}]
    assert result['consumer_disagreements'] == []
    player['held'] = 0
    assert HOST.controller_journal_summary([main, player], 0)['consumer_disagreements'] == [4]


def test_modal_polls_may_repeat_with_different_input_within_a_single_main_pass():
    modal = {'kind':'modal','serial':5,'held':0,'previous':0,'edge':0,
             'actor':None,'pc':0x80a67d,'video_frame':12}
    second = {**modal,'held':0x1000,'edge':0x1000,'video_frame':13}
    result = HOST.controller_journal_summary([modal,second], 0)
    assert result['samples'] == [modal,second]
    assert result['duplicate_serials'] == []
    assert result['conflicting_serials'] == []
    conversation = {**modal,'kind':'conversation','context':'primary','source_return':0x91ac}
    assert not HOST.controller_journal_summary([conversation,conversation], 0)['duplicate_serials']


def test_watch_defaults_preserve_system_ram_and_allow_save_ram():
    watches = [{'name': 'old', 'offset': 0, 'length': 1},
               {'name': 'save', 'memory_id': 0, 'offset': 8191, 'length': 1}]
    assert HOST.validate_watches(watches) == watches
    assert 'memory_id' not in watches[0]


@pytest.mark.parametrize('entry', [
    {'name': 'bad', 'memory_id': 1, 'offset': 0, 'length': 1},
    {'name': 'bad', 'memory_id': False, 'offset': 0, 'length': 1},
    {'name': 'bad', 'offset': True, 'length': 1},
    {'name': 'bad', 'offset': 0, 'length': 0},
    {'name': 'bad', 'offset': 0, 'length': 1025},
    ['not', 'an', 'object'],
])
def test_invalid_watches_fail_before_native_loading(entry):
    with pytest.raises(ValueError):
        HOST.validate_watches([entry])


def test_duplicate_watch_names_are_rejected_across_memory_spaces():
    with pytest.raises(ValueError, match='unique'):
        HOST.validate_watches([{'name': 'same', 'offset': 0, 'length': 1},
                               {'name': 'same', 'memory_id': 0, 'offset': 0, 'length': 1}])


def test_patch_list_retains_order_and_normalizes_exact_bytes():
    patches = [{'frame': 1, 'memory_id': 0, 'offset': 0, 'data_hex': 'AA 10'},
               {'frame': 1, 'memory_id': 0, 'offset': 0, 'data_hex': '02'}]
    result = HOST.validate_patches(patches, 3)
    assert [x['data_hex'] for x in result] == ['aa10', '02']
    assert patches[0]['data_hex'] == 'AA 10'


@pytest.mark.parametrize('changes', [
    {'frame': -1}, {'frame': 3}, {'frame': True}, {'memory_id': 3},
    {'memory_id': False}, {'offset': -1}, {'offset': True},
    {'data_hex': ''}, {'data_hex': 'A'}, {'data_hex': 'GG'},
    {'data_hex': '00' * 16385}, {'unknown': 1},
])
def test_invalid_patches_are_rejected(changes):
    patch = {'frame': 0, 'memory_id': 2, 'offset': 0, 'data_hex': '01'}
    patch.update(changes)
    with pytest.raises(ValueError):
        HOST.validate_patches([patch], 3)


def test_patch_count_is_bounded():
    patch = {'frame': 0, 'memory_id': 2, 'offset': 0, 'data_hex': '01'}
    with pytest.raises(ValueError, match='finite'):
        HOST.validate_patches([patch] * 4097, 3)


@pytest.mark.parametrize('value', ['', '1,', '-1', '3', '1,1', 'one', '1.5'])
def test_selected_images_require_unique_existing_frames(value):
    with pytest.raises(ValueError):
        HOST.frame_numbers(value, 3)


def test_selected_images_use_zero_based_frames():
    assert HOST.frame_numbers(None, 3) == []
    assert HOST.frame_numbers(' 2,0 ', 3) == [0, 2]


def test_snes_trace_bus_filters_use_exclusive_end_and_24_bit_bounds():
    assert HOST.snes_range(None) == (0,0)
    assert HOST.snes_range('0x800d34:0x800ee0') == (0x800d34,0x800ee0)
    for invalid in ('0:0','-1:2','0:0x1000001','1','2:1','x:2'):
        with pytest.raises(ValueError):
            HOST.snes_range(invalid)


def test_snes_joypad_ids_include_all_twelve_standard_buttons():
    assert HOST.controller_buttons('snes') == {
        'B':0, 'Y':1, 'SELECT':2, 'START':3, 'UP':4, 'DOWN':5,
        'LEFT':6, 'RIGHT':7, 'A':8, 'X':9, 'L':10, 'R':11,
    }
    assert HOST.controller_buttons('genesis')['A']==1
    assert HOST.controller_buttons('nes')['A']==8


@pytest.mark.parametrize(('fmt', 'word', 'size'), [(0, 0x7C00, 2), (1, 0xFF0000, 4), (2, 0xF800, 2)])
def test_pixel_formats_preserve_existing_rgb_contract(fmt, word, size):
    raw = word.to_bytes(size, sys.byteorder)
    image, rgb = HOST.frame_image((raw, 1, 1, size, fmt))
    assert image.size == (1, 1)
    assert rgb == bytes([255, 0, 0])


def test_audio_wav_and_statistics_use_actual_signed_stereo_samples(tmp_path):
    pcm = struct.pack('<hhhh', -32768, 0, 1000, -1000)
    counts = {'single_callback_frames': 1, 'batch_callback_frames': 1}
    receipt = HOST.write_audio_capture(tmp_path, pcm, 22050.0, counts)
    assert receipt['stereo_frames'] == 2
    assert receipt['sample_count'] == 4
    assert receipt['nonzero_samples'] == 3
    assert receipt['peak'] == 32768
    assert receipt['rms'] == pytest.approx(math.sqrt((32768 ** 2 + 2000000) / 4))
    assert receipt['pcm_sha256'] == hashlib.sha256(pcm).hexdigest()
    assert receipt['single_callback_frames'] == receipt['batch_callback_frames'] == 1
    with wave.open(str(tmp_path / 'audio.wav'), 'rb') as saved:
        assert (saved.getnchannels(), saved.getsampwidth(), saved.getframerate(), saved.getnframes()) == (2, 2, 22050, 2)
        assert saved.readframes(2) == pcm


def test_empty_captured_audio_is_measured_as_silence(tmp_path):
    receipt = HOST.write_audio_capture(tmp_path, b'', 44100, {'single_callback_frames': 0, 'batch_callback_frames': 0})
    assert receipt['sample_count'] == receipt['peak'] == receipt['rms'] == 0


@pytest.mark.parametrize('rate', [0, float('nan'), float('inf')])
def test_invalid_native_audio_rate_cannot_produce_a_success_receipt(tmp_path, rate):
    with pytest.raises(ValueError):
        HOST.write_audio_capture(tmp_path, b'', rate, {})


def feedback_policy():
    names={'input_buttons':[4,1],'mode':[7,1],'stage':[8,1],'player_x':[10,1],
           'player_y':[11,1],'player_jump':[14,1],'player_win':[16,1],
           'player_die':[17,1],'keys_left':[18,1],'ingame_status':[19,1],'anim':[28,2]}
    return {'format':'fdisbull-publication-controller-1','kind':'miniplanets-stage1-1',
            'rom_sha256':'a'*64,'max_logic_steps':2000,'post_goal_host_frames':120,
            'publication':{'memory_id':2,'base':0x700,'slots':4,'stride':48,
                           'sequence':0,'version':1,'epoch':2,'fields':names}}


@pytest.mark.parametrize('key,value', [('max_logic_steps',True),('max_logic_steps',5001),
    ('post_goal_host_frames',1001),('kind','arbitrary-eval'),('rom_sha256','unknown')])
def test_feedback_policy_is_finite_and_hash_bound(key,value):
    policy=feedback_policy();policy[key]=value
    with pytest.raises(ValueError):HOST.validate_feedback_policy(policy)


@pytest.mark.parametrize('key,value', [('base',2048),('slots',True),('stride',1024),
                                     ('sequence',False),('version',True),('memory_id',0)])
def test_feedback_cannot_read_an_unbounded_or_wrong_memory_surface(key,value):
    policy=feedback_policy();policy['publication'][key]=value
    with pytest.raises(ValueError):HOST.validate_feedback_policy(policy)


@pytest.mark.parametrize('conflict', ['patches','inputs','system','rom_sha256'])
def test_feedback_refuses_ram_mutation_or_competing_controller_authority(conflict):
    values={'system':'nes','rom_sha256':'a'*64,'inputs':[],'patches':[],
            'buttons':dict.fromkeys(['RIGHT','LEFT','UP','DOWN','A','START'])}
    values[conflict]={'patches':[{'frame':1}],'inputs':[{'start':1}],
                      'system':'genesis','rom_sha256':'b'*64}[conflict]
    with pytest.raises(ValueError):HOST.validate_feedback_session(feedback_policy(),**values)


def publication(number,**updates):
    policy=feedback_policy();raw=bytearray(192);at=(number%4)*48
    raw[at]=2;raw[at+1]=1;raw[at+2:at+4]=number.to_bytes(2,'little')
    state={'mode':1,'stage':0,'player_x':0,'player_y':0,'player_jump':0,
           'player_win':0,'player_die':0,'keys_left':1,'input_buttons':0,'anim':0,
           'ingame_status':0,**updates}
    for name,(offset,width) in policy['publication']['fields'].items():
        raw[at+offset:at+offset+width]=state[name].to_bytes(width,'little')
    return raw


def test_feedback_uses_completed_menu_and_landing_guards_before_movement():
    controller=HOST.PublicationController(feedback_policy())
    controller.observe(publication(1,mode=0,anim=84),1);assert controller.mask==0
    controller.observe(publication(2,mode=0,anim=85),2);assert controller.mask==64
    controller.observe(publication(3,mode=8,input_buttons=64),3);assert controller.mask==0
    controller.observe(publication(4,mode=8,input_buttons=0),4);assert controller.mask==64
    controller.observe(publication(5,player_jump=16,input_buttons=64),5);assert controller.mask==0
    controller.observe(publication(6),6);assert controller.mask==4
    controller.observe(publication(7,player_y=171,input_buttons=4),7);assert controller.mask==0
    controller.observe(publication(8,player_y=170,input_buttons=4),8);assert controller.mask==0
    controller.observe(publication(9,player_y=170,input_buttons=0),9);assert controller.mask==1


def test_feedback_rejects_partial_slots_and_stops_on_death_without_resetting_ram():
    controller=HOST.PublicationController(feedback_policy());raw=publication(1)
    raw[48]=1;controller.observe(raw,1)
    assert controller.steps==0 and controller.mask==0
    controller.observe(publication(1,player_die=1),2)
    assert controller.stop_frame==2 and not controller.completed
    assert controller.result()['reason']=='player death observed'


def test_feedback_goal_is_explicit_and_after_goal_only_neutral_buttons_are_sent():
    controller=HOST.PublicationController(feedback_policy())
    controller.observe(publication(1,player_win=1,keys_left=0),50)
    assert controller.completed and controller.mask==0 and controller.stop_frame==170
    controller.observe(publication(2,player_win=2,keys_left=0),51)
    assert controller.mask==0 and controller.result()['goal_epoch']==1


@pytest.mark.parametrize('tail', [None, 1500])
def test_feedback_preserves_goal_and_records_next_stage_before_stopping(tail):
    policy=feedback_policy();policy['post_goal_host_frames']=600
    if tail is not None:policy['post_transition_host_frames']=tail
    controller=HOST.PublicationController(policy)
    controller.observe(publication(1,player_win=1,keys_left=0),100)
    controller.observe(publication(2,stage=1,player_jump=16),500)
    transition=controller.result()['next_stage_transition']
    assert transition['epoch']==2 and transition['observed']['stage']==1
    assert controller.completed and controller.mask==0 and controller.stop_frame==(508 if tail is None else 500+tail)
    if tail is not None:assert controller.result()['post_transition_host_frames']==tail


@pytest.mark.parametrize('tail', [-1, 5001, True, '1500'])
def test_extended_feedback_observation_tail_has_a_finite_host_bound(tail):
    policy=feedback_policy();policy['post_transition_host_frames']=tail
    with pytest.raises(ValueError):HOST.validate_feedback_policy(policy)


def test_feedback_step_budget_is_a_recorded_dnf():
    policy=feedback_policy();policy['max_logic_steps']=1
    controller=HOST.PublicationController(policy)
    controller.observe(publication(1,mode=0),1);controller.observe(publication(2,mode=0),2)
    assert controller.stop_frame==1 and controller.steps==1
    assert controller.result()['reason']=='logical-step budget exhausted'
