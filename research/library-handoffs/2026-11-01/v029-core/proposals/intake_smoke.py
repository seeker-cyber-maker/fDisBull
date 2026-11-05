"""Offline installed-core and player smoke; no original game or emulator required."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import subprocess
import sys


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    results = {'python': sys.version, 'versions': {p: md.version(p) for p in ('fdisbull','fdisbull-player','capstone','iced-x86','lief','Pillow','z3-solver')}, 'commands': []}
    def cmd(module, args, name, stdin=None):
        command=[sys.executable,'-m',module,*map(str,args)]
        proc=subprocess.run(command,input=stdin,text=True,capture_output=True,timeout=30,cwd=output)
        (output/(name+'.stdout')).write_text(proc.stdout)
        (output/(name+'.stderr')).write_text(proc.stderr)
        results['commands'].append({'name':name,'command':command,'exit':proc.returncode})
        if proc.returncode: raise RuntimeError(f'{name} failed: {proc.stderr}')
        return proc.stdout
    binary=output/'authored_arithmetic.raw'
    binary.write_bytes(bytes.fromhex('b8 07 00 05 05 00 c3'))
    project=output/'authored_arithmetic.fdb'
    cmd('fdisbull',['import',binary,project,'--arch','x86','--bits','16','--base','0x100','--entry','0x100'],'static_import')
    cmd('fdisbull',['analyze',project,'--max-instructions','20'],'static_analyze')
    listing=cmd('fdisbull',['disasm',project,'--address','0x100','--lines','3'],'static_disasm')
    for mnemonic in ('mov','add','ret'):
        assert mnemonic in listing.lower(), mnemonic
    from fdisbull_player import LocalRuntime, Player
    p={'format':'fdisbull-text-slice-1','state':{'position':0},
       'context':{'id':'test','title':'Intake test','description':'Authored installation check.'},
       'objects':[{'id':'east','label':'east','aliases':[],'description':'Test direction.','verbs':['go']}],
       'inventory':[],'partial':True,
       'actions':[{'verb':'go','target':'east','item':None,'steps':[{'effects':[{'op':'add','key':'position','value':1}],'ticks':1}],'message':'Moved east.'}]}
    runtime=LocalRuntime(p)
    assert Player(runtime).execute('go east')=='Success: Moved east.'
    assert runtime.state['position']==1
    scenario=output/'player_fixture.json';scenario.write_text(json.dumps(p,indent=2)+'\n')
    text=cmd('fdisbull_player',['--package',scenario],'player_cli','go east\nquit\n')
    assert 'Success: Moved east.' in text
    import capstone,iced_x86,lief,z3
    from PIL import Image
    dec=list(capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_16).disasm(binary.read_bytes(),0x100))
    assert [i.mnemonic for i in dec]==['mov','add','ret']
    assert len(list(iced_x86.Decoder(16,binary.read_bytes())))==3
    assert lief.parse('/bin/true') is not None
    img=Image.new('RGB',(2,2));img.save(output/'image_smoke.png')
    with Image.open(output/'image_smoke.png') as reopened:assert reopened.size==(2,2)
    x=z3.BitVec('x',8);s=z3.Solver();s.add(x+1!=1+x);assert s.check()==z3.unsat
    s=z3.Solver();s.add(x+1!=x);assert s.check()==z3.sat
    results.update(status='passed',static_instruction_count=3,player_position=runtime.state['position'],original_cpu_executed=False,native_dos_backend_executed=False,ghidra_executed=False,full_suite_run=False)
    (output/'smoke_results.json').write_text(json.dumps(results,indent=2)+'\n')
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.output.resolve()),indent=2))
