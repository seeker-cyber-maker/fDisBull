import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.console_udc import compile_console_rom, write_console_rom, validate_console_program
from fdisbull.roms import inspect_rom


def program():
    return {'format':'fdisbull-il-1','role':'uil',
        'variables':{'$x':{'type':'u8','initial':250}, '$ticks':{'type':'u16','initial':65534},
                     '$copy':{'type':'u16','initial':0}}, 'resources':{},
        'body':[{'id':'x','op':'add','var':'$x','value':1},
                {'id':'ticks','op':'add','var':'$ticks','value':1},
                {'id':'copy','op':'set','var':'$copy','value':{'var':'$ticks'}},
                {'id':'decrement','op':'subtract','var':'$copy','value':1}]}


@pytest.mark.parametrize('target',['nes','genesis'])
def test_same_contract_distinct_native_roms(target):
    p = program()
    result = compile_console_rom(p,target=target,display_variable='$x')
    m = result['manifest']
    assert m['target']==target and m['rom_sha256']==hashlib.sha256(result['rom']).hexdigest()
    assert inspect_rom(result['rom'])['valid']
    assert not m['executed']
    for info in m['variables'].values():
        assert info['width'] in (8,16)
        assert info['width']!=16 or info['address']%2==0


@pytest.mark.parametrize('change', ['signed','mixed','buttons','resource','unsupported','literal_bit'])
def test_refuses_unimplemented_semantics(change):
    p = program()
    if change=='signed':p['variables']['$x']['type']='i8';p['variables']['$x']['initial']=1
    elif change=='mixed':p['body'][0]['value']={'var':'$ticks'}
    elif change=='buttons':
        p['variables']['$buttons']={'type':'u8','initial':0};p['body'][0]['var']='$buttons'
    elif change=='resource':p['resources']={'hello':{'kind':'text','text':'hello'}}
    elif change=='unsupported':p['body']=[{'id':'guard','op':'require','condition':{'op':'eq','left':1,'right':1}}]
    else:p['body']=[{'id':'bit','op':'if','condition':{'op':'bit_test','value':{'var':'$x'},'bit':8},'then':[],'else':[]}]
    with pytest.raises(ValueError):validate_console_program(p)


def test_new_private_output_and_public_cli(tmp_path):
    out=tmp_path/'nes'
    receipt=write_console_rom(program(),target='nes',output=out,display_variable='$x')
    assert (out/'program.nes').read_bytes()[:4]==b'NES\x1a'
    assert json.loads((out/'manifest.json').read_text())['rom_sha256']==receipt['rom_sha256']
    with pytest.raises(ValueError,match='new'):write_console_rom(program(),target='nes',output=out)
    checkout=tmp_path/'checkout';checkout.mkdir();(checkout/'.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError,match='outside Git'):write_console_rom(program(),target='genesis',output=checkout/'output')
    source=tmp_path/'program.json';source.write_text(json.dumps(program()))
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    proc=subprocess.run([sys.executable,'-m','fdisbull','console-udc',str(source),'--target','genesis','--output',str(tmp_path/'genesis')],env=env,capture_output=True,text=True,check=True)
    result=json.loads(proc.stdout)
    assert result['ok'] and result['result']['target']=='genesis'
