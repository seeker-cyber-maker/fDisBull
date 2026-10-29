#!/usr/bin/env python3
"""Exercise the genuinely installed offline kit with an authored DOS program."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import struct
import tempfile

from fdisbull.project import Project
from fdisbull.proofs import check_equivalence


def verify(kit):
    kit=Path(kit).resolve()
    import fdisbull
    import z3
    manifest=json.loads((kit/'manifest.json').read_text())
    expected=manifest['wheels']['fdisbull']['version']
    if manifest['wheels']['fdisbull-player']['version'] != expected:raise ValueError('Kit package versions differ')
    if importlib.metadata.version('fdisbull') != expected or importlib.metadata.version('fdisbull-player') != expected:raise ValueError('Wrong installed fDisBull or player')
    import fdisbull_player
    if 'site-packages' not in str(Path(fdisbull_player.__file__)):raise ValueError('Expected installed player, not source injection')
    if 'site-packages' not in str(Path(fdisbull.__file__)):raise ValueError('Expected installed package, not source injection')
    spec={'format':'fdisbull-proof-1','scope':'authored 8-bit offline installation acceptance','variables':{'x':8},'assumptions':[],
          'left':{'op':'add','args':[{'var':'x'},{'const':1,'width':8}]},'right':{'var':'x'}}
    counterexample=check_equivalence(spec)
    if counterexample['status']!='counterexample':raise ValueError('Genuine solver counterexample missing')
    spec['right']=spec['left'];equivalence=check_equivalence(spec)
    if equivalence['status']!='equivalent_under_assumptions':raise ValueError('Solver equivalence missing')
    # Set VGA mode 13, read one BIOS character, store its ASCII byte, then loop.
    code=bytes.fromhex('b81300cd100e1f30e4cd16a20001ebfe')+bytes(1024)
    header=bytearray(32);header[:2]=b'MZ';size=32+len(code)
    fields=[size%512,(size+511)//512,0,2,0,0xffff,0,0x400,0,0,0,0x1c,0]
    struct.pack_into('<13H',header,2,*fields)
    with tempfile.TemporaryDirectory(prefix='fdisbull-offline-acceptance-') as temporary:
        root=Path(temporary);program=root/'KEY.EXE';program.write_bytes(header+code);project_path=root/'private.fdb'
        # Genuine installed independent player: one model turn, no save command,
        # then a fresh runtime automatically resumes the persisted effect.
        from fdisbull_player import LiveSession, LocalRuntime
        package={'format':'fdisbull-text-slice-1','state':{'count':0},
                 'context':{'id':'room','title':'Authored room','description':'Offline acceptance fixture.'},
                 'objects':[{'id':'lever','label':'lever','aliases':[],'description':'An authored lever.','verbs':['press']}],
                 'actions':[{'verb':'press','target':'lever','item':None,
                             'steps':[{'ticks':1,'effects':[{'op':'add','key':'count','value':1}]}],
                             'message':'Lever pressed.'}]}
        turn=LiveSession(LocalRuntime(package,root/'player-saves')).run_turn(['press lever'])
        resumed=LocalRuntime(package,root/'player-saves')
        second=LiveSession(resumed).run_turn(['look'])
        if (turn.get('status')!='complete' or turn['checkpoint'].get('status')!='saved' or
                second['restore'].get('status')!='restored' or second['checkpoint'].get('status')!='saved' or
                resumed.state['count']!=1 or resumed.tick!=1):
            raise ValueError('Installed player automatic turn save/resume failed')
        with Project.create(project_path,program) as project,project.debugger(kit/'bin/dosbox',root) as session:
            session.run(guest_ms=100,timeout_ms=5000,fast_forward=True)
            state=session.save_state('before.sav')
            session.keyboard.press('a');session.run(guest_ms=250,timeout_ms=5000,fast_forward=True)
            if session.memory('1000:0100',length=1)['hex']!='61':raise ValueError('Guest keyboard consumption failed')
            screenshot=session.screenshot('native.png',hooks=False)
            session.load_state(state['artifact'])
            if session.memory('1000:0100',length=1)['hex']!='00':raise ValueError('Native restore failed')
            session.keyboard.press('b');session.run(guest_ms=250,timeout_ms=5000,fast_forward=True)
            if session.memory('1000:0100',length=1)['hex']!='62':raise ValueError('Post-restore keyboard failed')
            output={'package_version':importlib.metadata.version('fdisbull'),'player_version':importlib.metadata.version('fdisbull-player'),'solver_version':z3.get_version_string(),
                    'python_version':platform.python_version(),'platform':platform.system(),'machine':platform.machine(),
                    'counterexample':counterexample['status'],'equivalence':equivalence['status'],
                    'keyboard':True,'memory':True,'native_restore':True,'player_live_resume':True,
                    'screenshot_sha256':screenshot['sha256'],
                    'backend_sha256':hashlib.sha256((kit/'bin/dosbox-x').read_bytes()).hexdigest()}
        with Project(project_path) as reopened:
            if not reopened.debug_artifacts()['artifacts']:raise ValueError('Artifacts did not survive restart')
            output['project_restart']=True
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kit',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=verify(args.kit);Path(args.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
