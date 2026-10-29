"""Qualify the story harness and one recovered action against private DOS Zork.

Supply an extracted, licensed R88 directory. Output includes private source,
checkpoints, text, screenshots and databases; keep the entire output out of Git.
Run with a Python containing fDisBull's native dependencies. Jericho runs in
the separately selected worker Python. No original game file is modified.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import time

from fdisbull.project import Project
from fdisbull.zork import ZorkSession, NamedZorkHarness
from fdisbull.interaction_il import execute_il, change_role
from fdisbull.il_recovery import save_il, load_il
from fdisbull.zmachine import inspect_story
from fdisbull.zork_recovery import recover_mailbox, state_from_ram


def read(session, address, size):
    result=session.call('memory.read',{'address':{'space':'linear','offset':f'0x{address:08X}'},'length':size})
    raw=base64.b64decode(result['data_base64'],validate=True)
    if len(raw)!=size:raise RuntimeError('Incomplete guest memory')
    return raw


def screen(session):
    bda=read(session,0x449,60);raw=read(session,0xb8000,4000)
    if (bda[0],int.from_bytes(bda[1:3],'little'),bda[25],bda[59],int.from_bytes(bda[5:7],'little'))!=(3,80,0,24,0):
        raise RuntimeError('Unqualified DOS display mode')
    lines=[raw[i:i+160:2].decode('cp437').rstrip() for i in range(0,4000,160)]
    col,row=bda[7],bda[8]
    if row>=25 or col>=80:raise RuntimeError('Invalid BIOS cursor')
    return {'lines':lines,'text':'\n'.join(lines).rstrip(),'status':lines[0],
            'prompt':lines[row]=='>' and col==1 and not any(lines[row+1:]),
            'sha256':hashlib.sha256(raw).hexdigest()}


def prompt(session):
    previous=None
    for _ in range(30):
        run=session.run(guest_ms=300,timeout_ms=5000,fast_forward=True)
        if run['outcome']!='guest_time':raise RuntimeError('Preserved guest stop: '+run['outcome'])
        view=screen(session);keys=session.keyboard_state()['keyboard']
        current=view['sha256'] if view['prompt'] and not keys['pending_events'] and not keys['owned_keys'] else None
        if current and previous==current:return view
        previous=current
    raise RuntimeError('DOS prompt not qualified within budget')


def response(before,after,command):
    # Attribute only the surviving new screen suffix; stale or scrolled echoes
    # refuse comparison. A complete interpreter transcript is a different seam.
    old=before['lines'][1:];new=after['lines'][1:]
    while old and not old[-1]:old.pop()
    if old and old[-1]=='>':old.pop()
    while old and not old[-1]:old.pop()
    overlap=next((n for n in range(min(len(old),len(new)),0,-1) if old[-n:]==new[:n] and any(old[-n:])),0)
    fresh=new[overlap:]
    marker='>'+command
    if not overlap or marker not in fresh:raise RuntimeError('Response attribution unavailable')
    result=fresh[fresh.index(marker)+1:]
    while result and not result[-1]:result.pop()
    if result and result[-1]=='>':result.pop()
    return '\n'.join(result).strip()


def normalized(text):return ' '.join(text.split())
def il_text(result):return ''.join(e['resource_data']['text'] for e in result['events'] if e['op']=='text')
def scalar(regs,name):return int(regs['general'].get(name,regs['segments'].get(name)),16)&65535


def verify(game_dir,backend,worker_python,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    source=Path(game_dir).resolve(strict=True);game=output/'private-game';game.mkdir();(game/'DATA').mkdir()
    identities={}
    for name in ('_ZORK1.COM','DATA/ZORK1.DAT','SETUP.INF'):
        data=(source/name).read_bytes();(game/name).write_bytes(data);identities[name]=hashlib.sha256(data).hexdigest()
    if identities['_ZORK1.COM']!='2a6f366349be71ef4a164e3fc9c31a4a3d8c24ee6ddac93ed345c993c3562514':
        raise ValueError('Unqualified DOS interpreter')
    story=game/'DATA/ZORK1.DAT';info=inspect_story(story);recovered=recover_mailbox(story);doc=recovered['il']
    result={'format':'fdisbull-zork-qualification-1','identities':identities,'backend_sha256':hashlib.sha256(Path(backend).read_bytes()).hexdigest(),
            'scope':recovered['z'],'native':{},'comparisons':[]}
    def flush(): (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    started=time.monotonic();db=output/'private.fdb'
    with Project.create(db,game/'_ZORK1.COM',image='com') as project:
        for address in ('1000:2bdd','1000:178c','1000:19df'):
            project.analyze(start=address,max_instructions=2000)
        project.attach_file(story,name='story',kind='z_machine_story')
        udl=save_il(project,'mailbox',doc);uil=save_il(project,'mailbox',change_role(doc,'uil'),parent=udl['id'])
        result['revisions']={'udl':udl['id'],'uil':uil['id']}
        with project.debugger(backend,game,version=1) as dos:
            # Observe the first page read so the resident resource base is derived.
            bp=dos.breakpoint('1000:2bdd');stop=dos.run(timeout_ms=5000,fast_forward=True)
            if stop['outcome']!='breakpoint':raise RuntimeError('Story page read not reached')
            regs=dos.registers();base=scalar(regs,'ds')*16+scalar(regs,'edx')
            if read(dos,base,512)!=story.read_bytes()[:512]:raise RuntimeError('Story mapping not established')
            dos.delete_breakpoint(bp['breakpoint_id'])
            opening=prompt(dos);checkpoint=dos.save_state('opening.sav')
            shot=dos.screenshot('opening.png');project.debug_export(shot['artifact'],output/'opening.png')
            bp=dos.breakpoint('1000:178c');dos.keyboard_type('open mailbox\n')
            for _ in range(64):
                stop=dos.run(guest_ms=3000,timeout_ms=5000,fast_forward=True)
                if stop['outcome']!='breakpoint':raise RuntimeError('Action writer not reached')
                regs=dos.registers()
                if scalar(regs,'eax')==160 and scalar(regs,'ebx')==11:break
            else:raise RuntimeError('Action writer search budget exhausted')
            before=state_from_ram(read(dos,base,info['static_memory']))
            predicted=execute_il(doc,before)
            if not predicted['complete']:raise RuntimeError('Recovery qualification refused: '+str(predicted))
            dos.delete_breakpoint(bp['breakpoint_id'])
            watch=dos.call('breakpoints.create',{'kind':'w','once':False,'address':{'space':'linear','offset':f'0x{base+0x886:08X}'}})
            witnesses=[]
            for index in range(2):
                if index==0:stop=dos.run(guest_ms=3000,timeout_ms=5000,fast_forward=True)
                else:
                    trace=dos.trace('mailbox-writers.trace.json',count=256,timeout_ms=5000,fast_forward=True)
                    project.debug_export(trace['artifact'],output/'mailbox-writers.trace.json')
                    stop=trace['metadata']['run']
                if stop['outcome']!='breakpoint':raise RuntimeError('Required attribute watch not reached')
                regs=dos.registers();parts=read(dos,scalar(regs,'ds')*16+0x5de,4)
                next_pc=int.from_bytes(parts[:2],'little')*512+int.from_bytes(parts[2:],'little')
                expected_offset=(0x80a3,0x80a6)[index]
                if next_pc!=expected_offset+3:raise RuntimeError('Virtual PC disagrees with recovered source')
                witnesses.append({'source_offset':expected_offset,'next_virtual_pc':next_pc,'pc_parts_hex':parts.hex(),
                                  'source_bytes':story.read_bytes()[expected_offset:next_pc].hex(),
                                  'stop':stop,'registers':regs,'object_bytes':read(dos,base+0x885,9).hex()})
            dos.call('breakpoints.delete',{'breakpoint_id':watch['breakpoint_id']})
            first=prompt(dos);native_first=response(opening,first,'open mailbox')
            after=state_from_ram(read(dos,base,info['static_memory']))
            result['comparisons'].append({'case':'first-open','state_equal':predicted['state']==after,
                                          'text_equal':normalized(il_text(predicted))==normalized(native_first)})
            repeated_prediction=execute_il(doc,after);dos.keyboard_type('open mailbox\n');repeated=prompt(dos)
            native_repeat=response(first,repeated,'open mailbox');repeated_state=state_from_ram(read(dos,base,info['static_memory']))
            result['comparisons'].append({'case':'repeated-open','state_equal':repeated_prediction['state']==repeated_state,
                                          'text_equal':normalized(il_text(repeated_prediction))==normalized(native_repeat)})
            result['native'].update(base=base,before=before,after=after,witnesses=witnesses,first=native_first,repeated=native_repeat)
            shot=dos.screenshot('mailbox.png');project.debug_export(shot['artifact'],output/'mailbox.png')
            dos.load_state(checkpoint['artifact']);restored=prompt(dos);dos.keyboard_type('open mailbox\n');restored_after=prompt(dos)
            result['native']['same_session_checkpoint_response_equal']=normalized(response(restored,restored_after,'open mailbox'))==normalized(native_first)
        # A fresh process initializes its original interpreter before restore.
        # Cold restore at COM entry previously failed and is not our recipe.
        with project.debugger(backend,game,version=1) as dos:
            prompt(dos);dos.load_state(checkpoint['artifact']);restored=prompt(dos)
            dos.keyboard_type('open mailbox\n');restored_after=prompt(dos)
            result['native']['warm_fresh_session_checkpoint_response_equal']=normalized(response(restored,restored_after,'open mailbox'))==normalized(native_first)
        with ZorkSession(story,python=worker_python) as session:
            result['worker_identity']=session.identity
            session.save_checkpoint(output/'worker-checkpoint.json')
            one=session.command('open mailbox')
            session.save_checkpoint(output/'worker-after-first.json')
            first_worker_state=json.loads((output/'worker-after-first.json').read_text())['payload']['state']
            mapped_worker_state=state_from_ram(base64.b64decode(first_worker_state[0],validate=True))
            result['comparisons'].append({'case':'frotz-state-vs-dos','state_equal':mapped_worker_state==after})
            two=session.command('open mailbox')
            result['comparisons'].extend([{'case':'frotz-first-vs-dos','text_equal':normalized(one['observation'])==normalized(native_first)},
                                           {'case':'frotz-repeat-vs-dos','text_equal':normalized(two['observation'])==normalized(native_repeat)}])
        with ZorkSession(story,python=worker_python,expected=result['worker_identity']) as session:
            session.restore_checkpoint(output/'worker-checkpoint.json')
            restored=session.command('open mailbox')
            result['worker_fresh_checkpoint_response_equal']=restored['observation']==one['observation']
            session.save_checkpoint(output/'worker-restored-after-first.json')
            restored_worker_state=json.loads((output/'worker-restored-after-first.json').read_text())['payload']['state']
            result['worker_fresh_checkpoint_all_components_equal']=restored_worker_state==first_worker_state
            # Actual named-action refusal and single-use token, without hidden state.
            session.reset();harness=NamedZorkHarness(session,{'opening':{'match':'West of House','actions':{'open_mailbox':{'command':'open mailbox','expect':native_first}}}})
            view=harness.observe('opening');action=harness.act('opening','open_mailbox',view['token'])
            result['named_action']=action['outcome']
        (output/'recovered.udl.json').write_text(json.dumps(doc,indent=2)+'\n')
        (output/'recovered.uil.json').write_text(json.dumps(change_role(doc,'uil'),indent=2)+'\n')
    with Project(db) as project:
        result['database_restart_verified']=load_il(project,udl['id'])['document']==doc and load_il(project,uil['id'])['document']==change_role(doc,'uil')
    result['udl_uil_behavior_equal']=execute_il(doc,before)==execute_il(change_role(doc,'uil'),before)
    for name,digest in identities.items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Original input changed')
        if hashlib.sha256((game/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Private game input changed')
    result['inputs_unchanged']=True;result['elapsed_seconds']=round(time.monotonic()-started,3)
    result['passed']=(all(all(v is True for k,v in row.items() if k.endswith('_equal')) for row in result['comparisons'])
                      and result['native']['same_session_checkpoint_response_equal']
                      and result['native']['warm_fresh_session_checkpoint_response_equal']
                      and result['worker_fresh_checkpoint_response_equal'] and result['database_restart_verified']
                      and result['worker_fresh_checkpoint_all_components_equal']
                      and result['udl_uil_behavior_equal'] and result['named_action']=='expected')
    flush()
    if not result['passed']:raise RuntimeError('Qualification failed; inspect retained evidence')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('game-dir','backend','worker-python','output'):parser.add_argument('--'+arg,required=True)
    args=parser.parse_args()
    result=verify(args.game_dir,args.backend,args.worker_python,args.output)
    print(json.dumps({'passed':result['passed'],'elapsed_seconds':result['elapsed_seconds']}))
