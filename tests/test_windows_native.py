"""Opt-in real I386 original-process, scene/input and spectator qualification.

Requires a separately prepared matching offline runtime and the compiled
authored selftest32.c program. All generated evidence belongs outside Git.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.request

import pytest

from fdisbull.project import Project
from fdisbull.scenes import SceneError
from fdisbull.windows_ui import WindowsCaptureUnavailable


def qualify_windows_program(output,*,qemu,kernel,runtime,fixture,expected_bits=32):
    import lief
    from PIL import Image
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    game=output/'game';game.mkdir()
    original=Path(fixture).resolve(strict=True);original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    source=game/original.name;shutil.copyfile(original,source)
    image=lief.PE.parse(str(source));base=image.optional_header.imagebase
    assert str(image.header.machine)==('MACHINE_TYPES.I386' if expected_bits==32 else 'MACHINE_TYPES.AMD64')
    exports={e.name:base+e.address for e in image.get_export().entries}
    assert {'checkpoint','increment','counter','keys','clicks','last_key'}<=exports.keys()
    receipt={'format':'fdisbull-windows-native-scene-1','status':'running','bits':expected_bits,
             'fixture_sha256':original_hash,'checks':[],'exports':{k:hex(v) for k,v in exports.items()},
             'assistance':[],'full_VM_snapshot_positive_test':False,'host_input_injected':False}
    started=time.monotonic();session=None;trace=None;final=None
    def mark(name,**evidence):
        receipt['checks'].append({'check':name,**evidence});receipt['elapsed_seconds']=time.monotonic()-started
        (output/'qualification.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({'stage':name,'elapsed_seconds':receipt['elapsed_seconds'],**evidence}),flush=True)
    def get(url,**kwargs):
        with urllib.request.urlopen(urllib.request.Request(url,**kwargs),timeout=3) as response:
            return response.status,response.read()
    database=output/'native.fdb'
    try:
        with Project.create(database,source) as project:
            assert project.bits==expected_bits
            checkpoint=exports['checkpoint'];counter=exports['counter']
            project.analyze(start=checkpoint,max_instructions=128)
            static=project.disassembly(address=checkpoint,version=1,lines=5)['instructions']
            mark('compiled-source-and-static-entry-qualified',entry=hex(project.meta['entry']))
            with project.debugger(qemu,game,backend='wine-qemu',kernel=kernel,initramfs=runtime,
                                  version=1,window=True,memory_mib=8192,boot_timeout_ms=600000) as session:
                read=lambda address:int.from_bytes(bytes.fromhex(session.memory(address,length=4)['hex']),'little')
                state=lambda:{name:read(exports[name]) for name in ('counter','keys','clicks','last_key')}
                entry=session.registers()
                ip='eip' if expected_bits==32 else 'rip'
                assert entry['project_address']==hex(project.meta['entry']) and ip in entry
                assert ('rip' if expected_bits==32 else 'eip') not in entry
                assert session.rpc.capabilities['bits']==expected_bits
                receipt['runtime_inputs']=session.metadata['runtime_inputs']
                receipt['guest_runtime']=session.metadata['guest_runtime']
                receipt['qemu_command']=session.rpc.command
                mark('actual-original-entry-context',registers=entry,qemu_pid=session.rpc.process.pid)
                with pytest.raises(WindowsCaptureUnavailable) as unavailable:session.screenshot('entry-no-window.png')
                assert unavailable.value.capture_receipt['reason']=='no-visible-client-window'
                live=session.status()
                assert live['state']=='stopped' and session.rpc.process.poll() is None
                assert session.registers()['project_address']==entry['project_address']
                mark('entry-without-hwnd-capture-unavailable-and-debugger-still-live',
                     capture=unavailable.value.capture_receipt)
                bp=session.breakpoint(checkpoint);assert bp['bytes_verified']
                arrived=session.run(timeout_ms=60000)
                assert arrived['outcome']=='breakpoint',arrived
                assert session.registers()['project_address']==hex(checkpoint)
                assert state()=={'counter':7,'keys':0,'clicks':0,'last_key':0}
                before=session.screenshot('before.png',hooks=False)
                assert (before['metadata']['width'],before['metadata']['height'])==(320,200)
                assert session.frame_probe([[40,56]])['samples'][0]['rgb']==[224,160,32]
                mark('checkpoint-before-input-and-original-orange-frame',state=state(),breakpoint=bp)
                # Positive native state round trip, distinct from the pending/
                # held-key refusal checks below. The write is diagnostic and
                # is undone by restoring the captured machine state.
                snapshot=session.save_state('pe32-positive.sav')
                session.write_memory(counter,'29000000',expected_hex='07000000')
                assert read(counter)==41
                restored=session.load_state(snapshot['artifact'])
                assert restored['state']=='stopped' and state()=={'counter':7,'keys':0,'clicks':0,'last_key':0}
                assert session.registers()['project_address']==hex(checkpoint)
                receipt['full_VM_snapshot_positive_test']=True
                receipt['assistance'].append('Guarded counter edit 7->41 was undone by native state restore.')
                mark('positive-native-save-guarded-mutation-and-restore',snapshot=snapshot,restored=restored)

                with pytest.raises(ValueError,match='expected bytes'):
                    session.write_memory(counter,'29000000',expected_hex='08000000')
                session.write_memory(counter,'29000000',expected_hex='07000000');assert read(counter)==41
                session.write_memory(counter,'07000000',expected_hex='29000000');assert read(counter)==7
                receipt['assistance'].append('Declared guarded counter edit 7->41->7; readback restored before physical input cases.')
                stepped=session.step(count=1,timeout_ms=20000);assert stepped['completed'] and stepped['count']==1
                trace=session.trace('checkpoint-trace.json',count=3,timeout_ms=20000)
                assert trace['metadata']['complete'] and trace['metadata']['event_count']==3
                mark('guarded-memory-refusal-edit-restoration-and-actual-instruction-completion')

                queued=session.keyboard_press('right',hold_ms=40,gap_ms=40)
                assert queued['queued']==2 and queued['application_consumption_verified'] is False
                inputs=session.keyboard_state();assert inputs['pending']==2
                capture=session.rpc.capture
                def forbidden_capture(*args,**kwargs):raise AssertionError('Input guard reached bulk VM capture')
                session.rpc.capture=forbidden_capture
                try:
                    with pytest.raises(ValueError,match='empty input queue'):session.save_state('pending-refuses.sav')
                finally:session.rpc.capture=capture
                arrived=session.run(timeout_ms=30000)
                assert arrived['outcome']=='breakpoint',arrived
                assert state()=={'counter':8,'keys':1,'clicks':0,'last_key':0x27}
                session.delete_breakpoint(bp['breakpoint_id'])
                mark('physical-right-key-committed-and-execution-breakpoint-rearmed',state=state())

                frame=session.screenshot('ready-for-scenes.png',hooks=False)
                yes={'constant':True}
                ref={'address':hex(counter),'type':'u32'}
                outcome=lambda value:{'compare':{'left':{'memory':ref},'op':'eq','right':value}}
                ready=lambda n:{'memory':{'address':hex(counter),'length':4,'hex':n.to_bytes(4,'little').hex()}}
                objects=[]
                for name,area,point,action,value in [
                    ('counter.click',[32,48,192,112],[64,96],{'kind':'click','hold_ms':40},8),
                    ('counter.right',[0,0,16,16],[8,8],{'kind':'press','key':'right','hold_ms':40,'gap_ms':40},9)]:
                    objects.append({'name':name,'context':{'state':'authored Windows increment','triggers':['ordinary key or mouse release']},
                                    'area':{'rect':area},'point':point,'visible':yes,'enabled':yes,'ready':ready(value),
                                    'action':action,'outcome':outcome(value+1),'outcome_phase':'state','guest_ms':20000,'timeout_ms':30000})
                document={'format':'fdisbull-scene-1','width':320,'height':200,'mode_id':frame['metadata']['mode_id'],
                          'reference':frame['artifact'],'context':{'state':'native authored Windows client','triggers':['ordinary program startup']},
                          'match':{'pixels':{'samples':[{'x':0,'y':0,'rgb':[24,40,64]}]}},'objects':objects}
                scene=project.debug_save_scene('native-windows-actions',document)
                try:clicked=session.scene(scene['id']).act('counter.click')
                except SceneError as interrupted:
                    # Every unexpected stop remains a failure. In particular,
                    # a first-chance Wine helper AV must never be hidden by
                    # automatically forwarding it or replaying this click.
                    mark('named-click-interruption-retained-without-replay',
                         interruption=interrupted.result,disposition='Fail acceptance; preserve native stop')
                    raise
                assert clicked['complete'] and clicked['status']=='matched' and read(counter)==9 and read(exports['clicks'])==1
                assert clicked['time_basis']=='host' and 'guest_elapsed_ms' not in clicked
                keyed=session.scene(scene['id']).act('counter.right')
                assert keyed['complete'] and keyed['status']=='matched' and read(counter)==10 and read(exports['keys'])==2
                mark('named-click-and-keyboard-scenes-committed',state=state(),scene_revision=scene['id'],
                     click_observation=clicked['observation'],keyboard_observation=keyed['observation'])
                if expected_bits==32:
                    paused=session.status();helper=paused['pause_helper']
                    assert paused['stop_reason']['kind']=='slice'
                    assert helper['mechanism']=='observed-target32-ntdll-export'
                    assert helper['verified_breakpoint'] and not helper['pending']
                    assert paused['stop_reason']['thread']==helper['thread']
                    assert int(paused['stop_reason']['address'],16)==int(helper['breakpoint'],16)
                    assert 0<int(helper['module_base'],16)<1<<32
                    assert 0<int(helper['entry'],16)<1<<32 and helper['module_generation']>0
                    mark('timed-slice-verified-owned-target32-remote-breakpoint',pause_helper=helper)

                lease=session.keyboard_key_down('right')['lease']
                advanced=session.scene_advance(slice_ms=250,timeout_ms=5000);assert advanced['outcome']=='slice'
                held=session.keyboard_state()
                assert held['held'] and held['owned_leases'] and read(counter)==10
                with pytest.raises(ValueError,match='owned lease'):session.keyboard_key_down('right')
                session.rpc.capture=forbidden_capture
                try:
                    with pytest.raises(ValueError,match='released keys'):session.save_state('held-refuses.sav')
                finally:session.rpc.capture=capture
                session.keyboard_key_up(lease)
                for _ in range(20):
                    assert session.scene_advance(slice_ms=100,timeout_ms=5000)['outcome']=='slice'
                    if read(counter)==11:break
                assert read(counter)==11 and read(exports['keys'])==3
                released=session.keyboard_state();assert not released['held'] and not released['owned_leases']
                mark('held-physical-key-make-and-release-committed',state=state())

                watch=session.breakpoint(counter,access='w',length=4)
                session.keyboard_press('right',hold_ms=40,gap_ms=40)
                watched=session.run(timeout_ms=30000)
                assert watched['outcome']=='watchpoint',watched
                assert read(counter)==11
                access=watched['session']['stop_reason']['access_facts']
                assert any(r['write'] and r['length']==4 for r in access['ranges'])
                session.delete_breakpoint(watch['breakpoint_id'])
                completed=session.step(count=1,timeout_ms=20000);assert completed['completed']
                assert read(counter)==12
                assert session.scene_advance(slice_ms=250,timeout_ms=5000)['outcome']=='slice'
                assert state()=={'counter':12,'keys':4,'clicks':1,'last_key':0x27}
                mark('real-data-watch-before-store-and-single-step-commit',state=state(),access_facts=access)

                typed=session.keyboard_type('ab',hold_ms=40,gap_ms=40)
                assert typed['queued']==4
                observed=session.wait({'keys':{'kind':'memory','address':exports['keys'],'length':4}},
                                      {'observation':'keys','equals':'06000000'},active_ms=5000,timeout_ms=20000,
                                      timeout_screenshot=None)
                assert observed['complete'],observed
                assert state()=={'counter':13,'keys':6,'clicks':1,'last_key':0x42}
                modified=session.keyboard_press('c',modifiers=('ctrl','shift'),hold_ms=40,gap_ms=40)
                assert modified['queued']==6
                observed=session.wait({'keys':{'kind':'memory','address':exports['keys'],'length':4}},
                                      {'observation':'keys','equals':'09000000'},active_ms=5000,timeout_ms=20000,
                                      timeout_screenshot=None)
                assert observed['complete'],observed
                assert state()=={'counter':13,'keys':9,'clicks':1,'last_key':0x11}
                assert not session.keyboard_state()['held']
                mark('typed-ab-absolute-offsets-and-multiple-modifier-keyups-committed',state=state())

                dot=session.dot_mode();assert dot['enabled'] and dot['view_only'] and dot['host_input_capture'] is False
                # UI reads must not dispatch another command into the guest.
                sequence=session.rpc.sequence;url=dot['viewer_url']
                status,page=get(url);assert status==200 and b'Host keyboard and mouse are never forwarded' in page
                status,png=get(url+'frame.png');assert status==200 and png.startswith(b'\x89PNG')
                with pytest.raises(urllib.error.HTTPError) as denied:
                    get(url+'keyboard',data=b'right',method='POST')
                assert denied.value.code==405 and session.rpc.sequence==sequence
                assert '-display' in session.rpc.command and session.rpc.command[session.rpc.command.index('-display')+1]=='none'
                mark('actual-dot-mode-http-serves-only-retained-capture-and-refuses-control',
                     native_rpc_sequence_unchanged=True,host_input_capture=False)
                final=session.screenshot('final.png',hooks=False)
                assert session.frame_probe([[40,56]])['samples'][0]['rgb']==[32,192,96]
                receipt['final_state']=state();receipt['run']=session.run_id
                assert project.disassembly(address=checkpoint,version=1,lines=5)['instructions']==static
                for file in ('boot.log','qemu.log'):
                    path=Path(session.rpc.temporary.name)/file
                    if path.exists():shutil.copyfile(path,output/('guest-'+file))
            assert session.rpc.process.poll() is not None
            mark('owned-vm-and-spectator-closed-and-reaped')
        with Project(database) as reopened:
            reopened.debug_export(final['artifact'],output/'final.png')
            reopened.debug_export(trace['artifact'],output/'checkpoint-trace.json')
            actual=Image.open(output/'final.png');assert actual.size==(320,200) and actual.getpixel((40,56))==(32,192,96)
            events=json.loads((output/'checkpoint-trace.json').read_text())['events']
            expected_ip='eip' if expected_bits==32 else 'rip'
            assert len(events)==3 and all(expected_ip in e['registers'] for e in events)
        assert hashlib.sha256(original.read_bytes()).hexdigest()==original_hash
        assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
        receipt['status']='passed';mark('offline-project-reopen-png-and-trace-export-original-unchanged')
        return receipt
    except Exception as error:
        receipt.update(status='failed',error_type=type(error).__name__,error=str(error))
        if session is not None:receipt['owned_process_reaped']=session.rpc.process.poll() is not None
        mark('failure')
        raise


def test_real_pe32_original_process_shared_input_scenes_and_dot_mode(tmp_path):
    names=('FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL','FDISBULL_PE_INITRAMFS','FDISBULL_PE32_FIXTURE')
    missing=[name for name in names if not os.environ.get(name)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_WINDOWS')=='1':pytest.fail('Missing real Windows inputs: '+', '.join(missing))
        pytest.skip('Requires explicit matching Windows runtime and authored I386 fixture')
    qemu,kernel,runtime,fixture=[os.environ[name] for name in names]
    result=qualify_windows_program(tmp_path,qemu=qemu,kernel=kernel,runtime=runtime,fixture=fixture)
    assert result['status']=='passed'
