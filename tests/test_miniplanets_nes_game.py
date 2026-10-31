"""Wire-format checks; actual native core qualification is a separate script."""
import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
SPEC=importlib.util.spec_from_file_location('miniplanets_nes_checker',SCRIPTS/'check_miniplanets_nes_game.py')
CHECK=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def test_native_state_encoding_preserves_target_width_signedness_and_offsets():
    layout={'signed':{'offset':1,'length':2,'element_bits':16,'signed':True,'array_length':1},
            'bytes':{'offset':4,'length':2,'element_bits':8,'signed':False,'array_length':2},
            'wide':{'offset':6,'length':4,'element_bits':32,'signed':False,'array_length':1}}
    state={'signed':-32768,'bytes':[0,255],'wide':0x12345678}
    encoded=CHECK.encode_state(state,layout)
    assert encoded==bytes.fromhex('0000800000ff78563412')
    assert CHECK.decode_state(encoded,layout)==state


PUB={'slots':4,'stride':48,'sequence':0,'version':1,'epoch':2,'hv_count_offset':41,
     'fields':{'input_buttons':[4,1],'score':[24,4],'sound_busy_input':[45,1],'input_frame':[46,2]},
     'hv_recording':{'stride':64,'max_words':32,'byte_order':'big'}}


def row(number,sequence,score=0):
    raw=bytearray(194);slot=number%4;at=slot*48
    raw[at]=sequence;raw[at+1]=1;raw[at+2:at+4]=number.to_bytes(2,'little')
    raw[at+4]=16;raw[at+24:at+28]=score.to_bytes(4,'little')
    raw[at+41]=2;raw[at+45]=1;raw[at+46:at+48]=(number+100).to_bytes(2,'little')
    hv=bytearray(256);hv[slot*64:slot*64+4]=bytes.fromhex('1234abcd')
    return {'frame':number,'raw':{'publication':raw.hex(),'publication_hv':hv.hex()}}


def test_odd_in_progress_slot_never_becomes_a_completed_state_or_hv_recording():
    result=CHECK.publication_records({'frames':[row(1,1,0xDEADBEEF),row(1,2,0x12345678),row(1,2,0x12345678)]},
                                     {'publication':PUB})
    assert len(result)==1
    assert result[0]['fields']=={'input_buttons':16,'score':0x12345678,'sound_busy_input':1,'input_frame':101}
    assert result[0]['hv']==[0x1234,0xABCD]


def test_missing_completed_epoch_is_a_ring_overrun_not_a_new_baseline():
    with pytest.raises(AssertionError,match='overrun'):
        CHECK.publication_records({'frames':[row(1,2),row(6,2)]},{'publication':PUB})


@pytest.mark.parametrize('runtime_fault', [0, 3])
def test_sampled_nmi_frame_is_checked_against_its_own_scheduled_input(runtime_fault):
    pytest.importorskip('pycparser')
    from fdisbull.game_il import author_program
    program=author_program('''typedef unsigned char u8;u8 input_buttons;u8 x;
        void game_boot(void){x=0;}void game_frame(void){x=input_buttons;}''')
    pub={**PUB,'fields':{'input_buttons':[4,1],'x':[10,1],
                        'sound_busy_input':[45,1],'input_frame':[46,2]}}
    initial=bytearray(194);packet=bytearray(194);at=48
    packet[at]=2;packet[at+1]=1;packet[at+2:at+4]=(1).to_bytes(2,'little')
    packet[at+4]=16;packet[at+10]=16;packet[at+46:at+48]=(10).to_bytes(2,'little')
    controls=[(9).to_bytes(2,'little')+bytes(36),(10).to_bytes(2,'little')+bytes(36)]
    initial_control=bytearray(controls[0]);initial_control[29]=255
    initialized_control=bytearray(controls[1]);initialized_control[29]=runtime_fault
    controls=[bytes(initial_control),bytes(initialized_control)]
    rows=[{'frame':i,'input_mask':mask,'raw':{'debug':controls[i].hex(),
           'publication':raw.hex(),'publication_hv':bytes(256).hex()}}
          for i,(raw,mask) in enumerate([(initial,0),(packet,1<<8)])]
    receipt={'input_map':{'UP':4,'DOWN':5,'LEFT':6,'RIGHT':7,'A':8,'B':0,'START':3,'SELECT':2}}
    if runtime_fault:
        with pytest.raises(AssertionError,match='native runtime fault3'):
            CHECK.shadow_publications(program,b'',{'publication':pub},receipt,{'frames':rows})
        return
    report,_=CHECK.shadow_publications(program,b'',{'publication':pub},receipt,{'frames':rows})
    assert report['completed_projection_ticks_checked']==1
    assert report['independent_controller_checks']==1 and not report['controller_mapping_gaps']
    assert report['controller_lag_from_sampled_nmi_host_frame']==0
    assert report['initialized_runtime_fault_free']


def test_completed_state_agreement_cannot_hide_duplicate_scheduler_input_frames():
    pytest.importorskip('pycparser')
    from fdisbull.game_il import author_program
    program=author_program('''typedef unsigned char u8;u8 input_buttons;
        void game_boot(void){}void game_frame(void){}''')
    pub={**PUB,'fields':{'input_buttons':[4,1],'sound_busy_input':[45,1],'input_frame':[46,2]}}
    rows=[]
    for number in (1,2):
        raw=bytearray(194);at=(number%4)*48
        raw[at]=2;raw[at+1]=1;raw[at+2:at+4]=number.to_bytes(2,'little')
        raw[at+46:at+48]=(10).to_bytes(2,'little')
        rows.append({'frame':number-1,'input_mask':0,'raw':{
            'debug':((10).to_bytes(2,'little')+bytes(36)).hex(),
            'publication':raw.hex(),'publication_hv':bytes(256).hex()}})
    receipt={'input_map':{'UP':4,'DOWN':5,'LEFT':6,'RIGHT':7,'A':8,'B':0,'START':3,'SELECT':2}}
    with pytest.raises(AssertionError,match='scheduler reused'):
        CHECK.shadow_publications(program,b'',{'publication':pub},receipt,{'frames':rows})
