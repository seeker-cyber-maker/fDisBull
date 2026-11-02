#!/usr/bin/env python3
"""Actual FCEUmm two-selection smoke qualification with synthetic games."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory, compile_console_rom
from fdisbull.nes_multicart import build_multicart


def authored(marker):
    prg=bytearray(32768)
    prg[:13]=bytes([0xa9,marker,0x85,0,0xa9,0x80,0x8d,0x00,0x20,0x4c,9,0x80,0])
    prg[0x100:0x103]=bytes([0xe6,1,0x40])  # NMI increments independent RAM byte
    prg[-6:]=b'\x00\x81\x00\x80\x00\x81'
    return b'NES\x1a'+bytes([2,1,0,0])+bytes(8)+prg+bytes(8192)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--core',required=True);args=ap.parse_args()
    core=Path(args.core).resolve(); corehash=hashlib.sha256(core.read_bytes()).hexdigest()
    if corehash != '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60':
        raise ValueError('Core is not the expected pinned FCEUmm identity')
    output=_private_directory(args.output);output.mkdir()
    games=[]
    for i in (1,2):
        p=output/f'authored-{i}.nes';p.write_bytes(authored(0x10*i));games.append(p)
    m=build_multicart(games,output=output/'multicart',authored_compatible=True)
    (output/'watch.json').write_text(json.dumps([{'name':'marker','offset':0,'length':2}]))
    results={}
    for i,button in ((1,'A'),(2,'B')):
        (output/f'inputs-{i}.json').write_text(json.dumps([{'start':50,'end':55,'buttons':[button]}]))
        cmd=[sys.executable,str(ROOT/'scripts/check_console_udc.py'),'--core',str(core),'--rom',str(output/'multicart/program.nes'),'--system','nes','--frames','100','--watch',str(output/'watch.json'),'--inputs',str(output/f'inputs-{i}.json'),'--frame-images','30,80','--output',str(output/f'run-{i}')]
        subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=90)
        trace=json.loads((output/f'run-{i}/ram_trace.json').read_text());values=[bytes.fromhex(x['raw']['marker']) for x in trace['frames']]
        if values[-1][0]!=i*0x10 or values[-1][1]<5:raise AssertionError(f'{button} launch or NMI failed: {values[-1].hex()}')
        receipt=json.loads((output/f'run-{i}/receipt.json').read_text())
        results[button]={'observed_marker':values[-1][0], 'nmi_count':values[-1][1], 'core_sha256':receipt['core_sha256'], 'trace_sha256':receipt['ram_trace_sha256']}
    # Exercise an emulator reset while game one is running, then select game two.
    host_source=(ROOT/'scripts/check_console_udc.py').read_text()
    needle='        lib.retro_run()\n'
    if host_source.count(needle)!=1:raise ValueError('unexpected host reset integration point')
    host_source=host_source.replace(needle,'        if i == 110: lib.retro_reset()\n'+needle)
    reset_host=output/'reset-host.py';reset_host.write_text(host_source)
    reset_inputs=output/'reset-inputs.json';reset_inputs.write_text(json.dumps([
        {'start':50,'end':55,'buttons':['A']}, {'start':160,'end':165,'buttons':['B']}]))
    subprocess.run([sys.executable,str(reset_host),'--core',str(core),'--rom',str(output/'multicart/program.nes'),
                    '--system','nes','--frames','210','--watch',str(output/'watch.json'),
                    '--inputs',str(reset_inputs),'--frame-images','30,140','--output',str(output/'reset-run')],
                   check=True,capture_output=True,text=True,timeout=90)
    reset_rows=json.loads((output/'reset-run/ram_trace.json').read_text())['frames']
    before=bytes.fromhex(reset_rows[100]['raw']['marker'])[0]
    after=bytes.fromhex(reset_rows[-1]['raw']['marker'])[0]
    if (before,after)!=(0x10,0x20):raise AssertionError('FCEUmm reset did not return to menu')
    reset_receipt=json.loads((output/'reset-run/receipt.json').read_text())
    images=reset_receipt['frame_images']
    if images[0]['rgb_sha256'] != images[1]['rgb_sha256']:
        raise AssertionError('reset did not restore the original menu pixels')
    # Fresh generated UIL games, each compared to standalone over 100 ticks.
    document={'format':'fdisbull-il-1','role':'uil','variables':{
        '$buttons':{'type':'u8','initial':0},'$x':{'type':'u8','initial':3},
        '$ticks':{'type':'u16','initial':0},'$copy':{'type':'u16','initial':0}},
        'resources':{},'body':[
          {'id':'x','op':'if','condition':{'op':'bit_test','value':{'var':'$buttons'},'bit':0},
           'then':[{'id':'inc','op':'add','var':'$x','value':1}],'else':[]},
          {'id':'tick','op':'add','var':'$ticks','value':1},
          {'id':'copy','op':'set','var':'$copy','value':{'var':'$ticks'}}]}
    uil=[]
    for i in (1,2):
        document['variables']['$x']['initial']=3*i
        program=compile_console_rom(document,target='nes',display_variable='$x')
        p=output/f'uil-{i}.nes';p.write_bytes(program['rom']);uil.append(p)
    uilcart=build_multicart(uil,output=output/'uil-multicart',authored_compatible=True)
    (output/'uil-watch.json').write_text(json.dumps([{'name':'state','offset':768,'length':7}]))
    def run_uil(name, rom, inputs):
        schedule=output/f'{name}-inputs.json';schedule.write_text(json.dumps(inputs))
        cmd=[sys.executable,str(ROOT/'scripts/check_console_udc.py'),'--core',str(core),
             '--rom',str(rom),'--system','nes','--frames','210','--watch',str(output/'uil-watch.json'),
             '--inputs',str(schedule),'--output',str(output/name)]
        subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=90)
        return json.loads((output/name/'ram_trace.json').read_text())['frames']
    def state(row):
        raw=bytes.fromhex(row['raw']['state'])
        return int.from_bytes(raw[4:6],'little'),raw[0],int.from_bytes(raw[2:4],'little'),raw[6]
    comparison={}
    for i,key in ((1,'A'),(2,'B')):
        launch=[{'start':50,'end':55,'buttons':[key]}]
        left=run_uil(f'uil-{i}-standalone-cal',uil[i-1],[])
        right=run_uil(f'uil-{i}-multicart-cal',output/'uil-multicart/program.nes',launch)
        start1=next(x['frame'] for x in left if state(x)[0]==1)
        start2=next(x['frame'] for x in right if state(x)[0]==1)
        def controls(start):
            return [{'start':start+10,'end':start+30,'buttons':['RIGHT']},
                    {'start':start+50,'end':start+65,'buttons':['RIGHT']}]
        left=run_uil(f'uil-{i}-standalone',uil[i-1],controls(start1))
        right=run_uil(f'uil-{i}-multicart',output/'uil-multicart/program.nes',launch+controls(start2))
        lhs={state(x)[0]:state(x)[1:] for x in left if 1<=state(x)[0]<=100}
        rhs={state(x)[0]:state(x)[1:] for x in right if 1<=state(x)[0]<=100}
        if len(lhs)!=100 or lhs!=rhs:raise AssertionError(f'UIL state/controller mismatch game {i}')
        comparison[key]={'matched_ticks':100,'fields':['buttons','copy','x'],
                         'standalone_first_tick_frame':start1,'multicart_first_tick_frame':start2}
    summary={'format':'fdisbull-nes-multicart-native-check-1','status':'passed','cartridge_sha256':m['rom_sha256'],'selection':results,'fceumm_reset_then_reselect':{'before':before,'after':after},'uil_standalone_comparison':comparison,'uil_cartridge_sha256':uilcart['rom_sha256'],'scope':'synthetic NROM programs on pinned FCEUmm; hardware and general game compatibility unverified'}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(output/'summary.json')

if __name__=='__main__':main()
