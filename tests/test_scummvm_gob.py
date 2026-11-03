"""Gob wrapper public behavior; native cases require explicit private inputs.

The executable peer below is a protocol test double, never runtime evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import textwrap

from PIL import Image
import pytest

from fdisbull.project import Project
from fdisbull.scummvm_gob import ScummVMGobSession, _fnv1a64, _script_end, _unpack_member
from fdisbull.scummvm_rpc import ScummVMError


SCRIPT=bytes(range(128))+b'\x30\x40\x50\x60'


def bridge(tmp_path, *, scenario='normal'):
    path=tmp_path/'gob-peer.py'
    path.write_text(textwrap.dedent('''\
        #!/usr/bin/env python3
        import base64, json, os, socket
        sock=socket.socket(fileno=int(os.environ['FDISBULL_SCUMMVM_FD']))
        stream=sock.makefile('rwb',buffering=0)
        scenario=SCENARIO
        script=SCRIPT
        def fnv(data):
            result=14695981039346656037
            for value in data:result=((result^value)*1099511628211)&((1<<64)-1)
            return format(result,'016x')
        arena=bytearray(14000)
        offset,guest,pending=128,0,0
        active=False
        for line in stream:
            q=json.loads(line);op=q['op'];r={'id':q['id'],'ok':True}
            if op=='hello':r.update(engine='gob',protocol='fdisbull-scummvm-agent',
                protocol_version=1,bridge_version=1,profile='gob-inter-v3',virtual_clock=True,
                variant={'game_id':'lit','detected_language':'us','detected_platform':'pc','recognized_detection':True},
                capabilities=['state','frame','run','step','memory.read','memory.write','script.read',
                              'input.status','trace.start','pause','hotspots.events'])
            elif op=='state.get':
                r['state']=dict(engine='gob',script=dict(name='TEST.TOT',generation=1,size=len(script),
                    fnv1a64=fnv(script),offset_origin='tot_file_start',raw_header_included=True,
                    source={'kind':'loose','container':'TEST.TOT','member':'TEST.TOT'}),
                    offset=offset,phase='before_opcode',family='func',opcode=script[offset],
                    guest_ms=guest,instructions=offset-128,frame_revision=1,
                    variables={'size':len(arena),'arena':'variables','endian':'little'},hotspots=[])
                if scenario=='agi_state':r['state']={'room':1,'vars':[0]*256,'flags':[False]*256}
            elif op=='memory.read':
                data=arena[q['offset']:q['offset']+q['length']]
                r.update(hex=data.hex(),size=len(arena),arena='variables',endian='little')
                if scenario=='short_memory':r['hex']=''
                if scenario=='big_memory':r['endian']='big'
            elif op=='memory.write':
                start=q['offset'];data=bytes.fromhex(q['data_hex'])
                if arena[start:start+len(data)].hex()!=q['expected_hex']:
                    r.update(ok=False,error='expected_mismatch',message='stale bytes')
                else:arena[start:start+len(data)]=data
            elif op=='script.read':
                r.update(current_hex=script[q['offset']:q['offset']+q['length']].hex(),generation=1)
                if scenario=='wrong_generation':r['generation']=2
            elif op=='frame.get':r.update(width=2,height=2,format='rgb24',revision=1,guest_ms=guest,
                data_base64=base64.b64encode(bytes(range(12))).decode(),
                display={'input_space':'committed_frame_pixels','scroll_offset_x':0,'scroll_offset_y':0})
            elif op=='input':pending+=1;r['queued']=1
            elif op=='input.status':r.update(pending=pending,held_keycodes=[],leases=[],guest_ms=guest)
            elif op in ('run','step'):
                pending=0;offset=min(131,offset+1);guest+=q.get('max_guest_ms',1)
                r['stop']=dict(reason='step' if op=='step' else 'guest_budget' if 'max_guest_ms' in q else 'budget',
                    instructions=1,script='TEST.TOT',generation=1,offset=offset,guest_ms=guest)
            elif op=='trace.get':r.update(entries=[dict(script='TEST.TOT',generation=1,offset=128,
                family='func',phase='start',event_id=1,depth=0,opcode=48)],truncated=False)
            elif op=='hotspots.events':r.update(entries=[{'dispatch_id':1,'id':7}],dispatches=1,truncated=False)
            stream.write((json.dumps(r)+'\\n').encode())
            if op=='quit':break
    ''').replace('SCENARIO',repr(scenario)).replace('SCRIPT',repr(SCRIPT)))
    path.chmod(0o700)
    return path


def project_fixture(tmp_path):
    game=tmp_path/'game'
    game.mkdir()
    (game/'lost.exe').write_bytes(b'\x90\xc3')
    (game/'TEST.TOT').write_bytes(SCRIPT)
    project=Project.create(tmp_path/'gob.fdb',game/'lost.exe',arch='x86',bits=16,base=0)
    return project,game


def test_gob_source_bound_context_typed_aliases_and_assisted_writes(tmp_path):
    project,game=project_fixture(tmp_path)
    with project,ScummVMGobSession(project,bridge(tmp_path),game,language='us',platform='dos') as session:
        state=session.engine_state()
        assert state['backend']=='scummvm-gob' and state['position']['offset_origin']=='tot_file_start'
        assert state['current_script']['generation']==1
        assert 'vars' not in state and 'flags' not in state
        assert session.context('gob-vm') is session
        with pytest.raises(ValueError):session.context('agi-vm')
        written=session.write_variable(13,-1,width=1,signed=True,expected=0)
        assert written['assisted_state'] and not written['reachability_verified']
        assert session.read_variable(13,signed=True)['value']==-1
        assert session.read_variable(13)['value']==255
        session.write_variable(14,0x12345678,width=4,expected=0)
        assert session.read_variable(14,width=2)['value']==0x5678
        assert session.read_variable(15,width=2)['value']==0x3456
        assert session.read_variable(17)['value']==0x12
        assert session.write_engine_state('i8',13,127,expected=-1)['after']==127
        for value in (-129,128):
            with pytest.raises(ValueError,match='width'):session.write_variable(13,value,signed=True)
        with pytest.raises(ValueError,match='precondition'):session.write_variable(13,1,expected=99)
        assert session.read_variable(13)['value']==127
        with pytest.raises(ValueError,match='arena'):session.read_variable(14000)
        with pytest.raises(ValueError,match='little endian'):session.read_variable(0,endian='big')
        source=session.resource('TEST.TOT',128,1,generation=1)
        assert source['source']['loaded_sha256']==hashlib.sha256(SCRIPT).hexdigest()
        assert source['source']['bytes_verified'] and source['current_hex']=='30'
        point=session.breakpoint({'script':'TEST.TOT','generation':1,'offset':128})
        assert point['bytes_verified']
        watch=session.watchpoint('u32',13,access='rw')
        assert watch['length']==4 and watch['all_writes_covered'] is False
        session.delete_breakpoint(point['breakpoint_id']);session.delete_watchpoint(watch['watchpoint_id'])
        with pytest.raises(ValueError,match='generation'):session.code({'script':'TEST.TOT','generation':2,'offset':128})
        assert session.run(guest_ms=25)['guest_elapsed_ms']==25
        assert session.step()['completed']
        trace=session.trace(count=1)
        assert trace['metadata']['backend']=='scummvm-gob'
        for method,args in ((session.save_state,()),(session.load_state,('none',)),
                            (session.patch_resource,()),(session.run_until_cycle,())):
            with pytest.raises(ValueError):method(*args)


def test_gob_real_png_persists_after_close_reopen_and_input_receipt_is_only_queued(tmp_path):
    project,game=project_fixture(tmp_path)
    with project,ScummVMGobSession(project,bridge(tmp_path),game) as session:
        first=session.frame_probe([[1,1]])
        assert first['samples'][0]['rgb']==[9,10,11]
        assert session.keyboard_type('x')['consumed'] is False
        with pytest.raises(ValueError,match='frame differs'):
            session.click(0,0,frame_id=first['frame_id'])
        assert session.click(0,0)['consumed'] is False
        image=session.screenshot()
        assert image['metadata']['backend']=='scummvm-gob'
        assert session.keyboard_state()['backend']=='scummvm-gob'
        assert image['metadata']['display']['input_space']=='committed_frame_pixels'
        dispatched=session.hotspot_events()
        assert dispatched['dispatches']==1 and dispatched['truncated'] is False
        assert 'completion remains separately observed' in dispatched['scope']
    with Project(tmp_path/'gob.fdb') as reopened:
        reopened.debug_export(image['artifact'],tmp_path/'stored.png')
        with Image.open(tmp_path/'stored.png') as png:
            assert png.size==(2,2) and png.getpixel((1,1))==(9,10,11)
    with Project(tmp_path/'gob.fdb') as reopened,ScummVMGobSession(reopened,bridge(tmp_path),game) as restarted:
        assert restarted.read_variable(13)['value']==0
        assert restarted.resource('TEST.TOT',128,1)['current_hex']=='30'


@pytest.mark.parametrize('scenario,operation,match',[
    ('agi_state','launch','typed VM state'),('short_memory','read','incomplete'),
    ('big_memory','read','arena identity'),
    ('wrong_generation','launch','changed')])
def test_gob_rejects_invalid_engine_state_bytes_and_generation(tmp_path,scenario,operation,match):
    project,game=project_fixture(tmp_path)
    with project:
        if operation=='launch':
            with pytest.raises(ScummVMError,match=match):
                ScummVMGobSession(project,bridge(tmp_path,scenario=scenario),game)
            return
        with ScummVMGobSession(project,bridge(tmp_path,scenario=scenario),game) as session:
            with pytest.raises(ScummVMError,match=match):
                session.read_variable(0) if operation=='read' else session.resource()


def test_gob_changed_source_and_symlink_inputs_refused(tmp_path):
    project,game=project_fixture(tmp_path)
    executable=bridge(tmp_path)
    with project:
        with ScummVMGobSession(project,executable,game) as session:
            (game/'TEST.TOT').write_bytes(b'changed')
            with pytest.raises(ScummVMError,match='resources changed'):session.engine_state()
            assert session.closed
        (game/'linked').symlink_to(game/'lost.exe')
        with pytest.raises(ValueError,match='symbolic'):ScummVMGobSession(project,executable,game)


def test_gob_project_patch_is_a_separate_version_and_cannot_enter_runtime(tmp_path):
    project,game=project_fixture(tmp_path)
    with project:
        project.patch(0,'58',label='separate static version')
        with pytest.raises(ValueError,match='original project version'):
            ScummVMGobSession(project,bridge(tmp_path),game,version=2)
        with ScummVMGobSession(project,bridge(tmp_path),game,version=1) as session:
            assert session.resource(offset=128,length=1)['current_hex']=='30'
        assert (game/'lost.exe').read_bytes()==b'\x90\xc3'


def test_gob_hook_capability_is_declared_in_metadata_and_every_status(tmp_path):
    project,game=project_fixture(tmp_path)
    with project,ScummVMGobSession(project,bridge(tmp_path),game) as session:
        assert type(session).native_hooks_available is False
        assert session.metadata['native_hooks_available'] is False
        assert session.status()['native_hooks_available'] is False
        session._run_active=True
        try:
            assert session.status()['native_hooks_available'] is False
        finally:
            session._run_active=False
        session._guest_exited=True
        try:
            assert session.status()['native_hooks_available'] is False
        finally:
            session._guest_exited=False
        before=session.engine_state()['instructions']
        with pytest.raises(ValueError,match='hooks are unavailable'):
            session.run(stop_on_hook=True)
        assert session.engine_state()['instructions']==before


def test_gob_duplicate_controls_share_native_ownership_and_typed_range_identity(tmp_path):
    project,game=project_fixture(tmp_path)
    with project,ScummVMGobSession(project,bridge(tmp_path),game) as session:
        address={'script':'TEST.TOT','generation':1,'offset':128}
        first=session.breakpoint(address)
        second=session.breakpoint({**address,'family':''},view='execute')
        assert second['breakpoint_id']==first['breakpoint_id']
        assert len(session._breakpoints)==1
        session.delete_breakpoint(second['breakpoint_id'])
        with pytest.raises(ValueError,match='Unknown'):
            session.delete_breakpoint(first['breakpoint_id'])
        first_watch=session.watchpoint('u32',13,access='rw')
        signed_alias=session.watchpoint('i32',13,access='rw')
        raw_alias=session.watchpoint('variable',13,length=4,access='rw')
        assert first_watch['watchpoint_id']==signed_alias['watchpoint_id']==raw_alias['watchpoint_id']
        distinct=[session.watchpoint('i16',13,access='rw'),
                  session.watchpoint('u32',13,access='r'),
                  session.watchpoint('u32',14,access='rw')]
        assert len({first_watch['watchpoint_id'],*(item['watchpoint_id'] for item in distinct)})==4
        session.delete_watchpoint(signed_alias['watchpoint_id'])
        with pytest.raises(ValueError,match='Unknown'):
            session.delete_watchpoint(raw_alias['watchpoint_id'])
        assert len(session._watches)==3


def test_gob_duplicate_registration_still_revalidates_backend_and_source(tmp_path,monkeypatch):
    project,game=project_fixture(tmp_path)
    with project,ScummVMGobSession(project,bridge(tmp_path),game) as session:
        address={'script':'TEST.TOT','generation':1,'offset':128}
        first=session.breakpoint(address)
        call=session._call
        refused=[]
        def refuse_registration(op,params=None,**options):
            if op=='break.add':
                refused.append(op)
                raise ScummVMError('Current loaded source identity changed')
            return call(op,params,**options)
        monkeypatch.setattr(session,'_call',refuse_registration)
        with pytest.raises(ScummVMError,match='source identity changed'):
            session.breakpoint(address)
        assert refused==['break.add']
        assert list(session._breakpoints)==[first['breakpoint_id']]
        with pytest.raises(ValueError,match='generation'):
            session.breakpoint({**address,'generation':2})


def test_gob_independent_single_chunk_decoder_known_literals_and_backreference():
    # Three literals ABC, then an LZSS dictionary match at the prior ring entry.
    packed=(6).to_bytes(4,'little')+bytes.fromhex('07414243ee f0')
    assert _unpack_member(packed,1)==b'ABCABC'
    assert _fnv1a64(b'hello')=='a430d84680aabd0b'
    with pytest.raises(ValueError,match='Truncated'):_unpack_member(packed[:-1],1)
    with pytest.raises(ValueError,match='16 MiB'):_unpack_member((2**25).to_bytes(4,'little'),1)


def test_gob_loaded_script_prefix_is_independent_of_full_member_text_and_resource_tables():
    payload=bytearray(240)
    payload[48:52]=(200).to_bytes(4,'little')
    payload[52:56]=(160).to_bytes(4,'little')
    assert _script_end(payload)==160
    payload[52:56]=(0xffffffff).to_bytes(4,'little')
    assert _script_end(payload)==200
    payload[48:52]=bytes(4)
    assert _script_end(payload)==240
    payload[48:52]=(80).to_bytes(4,'little')
    with pytest.raises(ValueError,match='header'):_script_end(payload)


@pytest.mark.skipif(not (os.environ.get('FDISBULL_GOB_NATIVE') and os.environ.get('FDISBULL_LOSTTIME_EN_DIR')),
                    reason='set explicit Gob runtime and private English Lost in Time directory')
def test_native_losttime_gob_source_typed_arena_step_and_stored_frame(tmp_path):
    game=Path(os.environ['FDISBULL_LOSTTIME_EN_DIR'])
    executable=Path(os.environ['FDISBULL_GOB_NATIVE'])
    source=game/'lost.exe'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    project=Project.create(tmp_path/'native-gob.fdb',source)
    with project,ScummVMGobSession(project,executable,game,game_id='lit',language='us',platform='dos') as session:
        state=session.engine_state()
        assert state['backend']=='scummvm-gob' and state['variables']['size']>=13436
        source_record=session.resource(offset=0,length=128)
        assert source_record['source']['bytes_verified']
        assert len(source_record['source']['loaded_sha256'])==64
        camera=session.read_variable(13435,signed=True)
        assert -128<=camera['value']<=127
        assert session.step(timeout_ms=10000)['steps']
        artifact=session.screenshot('native-gob.png')
        assert artifact['metadata']['backend']=='scummvm-gob'
        assert artifact['metadata']['width']>=320
    with Project(tmp_path/'native-gob.fdb') as reopened:
        reopened.debug_export(artifact['artifact'],tmp_path/'native-gob.png')
        with Image.open(tmp_path/'native-gob.png') as image:
            image.verify()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


@pytest.mark.skipif(not (os.environ.get('FDISBULL_GOB_NATIVE') and os.environ.get('FDISBULL_LOSTTIME_EN_DIR')),
                    reason='set explicit Gob runtime and private English Lost in Time directory')
def test_native_losttime_guarded_integer_aliases_and_native_trace(tmp_path):
    game=Path(os.environ['FDISBULL_LOSTTIME_EN_DIR'])
    project=Project.create(tmp_path/'native-aliases.fdb',game/'lost.exe')
    with project,ScummVMGobSession(project,os.environ['FDISBULL_GOB_NATIVE'],game,
                                  language='us',platform='dos') as session:
        assert session.rpc.hello['variant']['extra']=='v1.10'
        offset=session.engine_state()['variables']['size']-8
        original=session.read_variable(offset,width=4)['value']
        try:
            session.write_variable(offset,0x12345678,width=4,expected=original)
            assert session.read_variable(offset+1,width=2)['value']==0x3456
            session.write_variable(offset,-1,width=1,signed=True,expected=0x78)
            assert session.read_variable(offset)['value']==255
            assert session.read_variable(offset,signed=True)['value']==-1
            before=session.read_variable(offset,width=4)['value']
            with pytest.raises(ValueError,match='precondition'):
                session.write_variable(offset,0,width=4,expected=before^1)
            assert session.read_variable(offset,width=4)['value']==before
            for value in (-129,128):
                with pytest.raises(ValueError,match='width'):
                    session.write_variable(offset,value,signed=True)
        finally:
            session.write_variable(offset,original,width=4)
        assert session.read_variable(offset,width=4)['value']==original
        trace=session.trace(count=8,timeout_ms=10000)
        report=json.loads(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                            (trace['artifact'],)).fetchone()[0])
        assert report['events']
        assert {event['family'] for event in report['events']} <= {'func','draw','gob'}
        assert all(event['original_source']['bytes_verified'] for event in report['events'])
        starts={event['dispatch_id'] for event in report['events'] if event.get('event')=='start'}
        completed={event['dispatch_id'] for event in report['events'] if event.get('event')=='complete'}
        assert completed and starts
        # Tracing starts after boot paused inside a pending dispatch. A
        # completion lacking a captured start is retained, never fabricated.
        assert all(type(identifier) is int for identifier in starts|completed)


@pytest.mark.skipif(not (os.environ.get('FDISBULL_GOB_NATIVE') and os.environ.get('FDISBULL_LOSTTIME_EN_DIR')),
                    reason='set explicit Gob runtime and private English Lost in Time directory')
def test_native_losttime_duplicate_controls_keep_one_id_and_delete_once(tmp_path):
    game=Path(os.environ['FDISBULL_LOSTTIME_EN_DIR'])
    project=Project.create(tmp_path/'native-control-ownership.fdb',game/'lost.exe')
    with project,ScummVMGobSession(project,os.environ['FDISBULL_GOB_NATIVE'],game,
                                  language='us',platform='dos') as session:
        assert session.native_hooks_available is False
        assert session.status()['native_hooks_available'] is False
        state=session.engine_state()
        address={'script':state['script']['name'],'generation':state['script']['generation'],
                 'offset':state['offset'],'family':state['family']}
        first=session.breakpoint(address)
        second=session.breakpoint(dict(address))
        assert first['breakpoint_id']==second['breakpoint_id']
        assert session.rpc.call('break.add',address)['count']==1
        session.delete_breakpoint(first['breakpoint_id'])
        with pytest.raises(ValueError,match='Unknown'):
            session.delete_breakpoint(second['breakpoint_id'])
        assert session.rpc.call('break.remove',address)['count']==0
        first_watch=session.watchpoint('u32',13,access='rw')
        second_watch=session.watchpoint('i32',13,access='rw')
        assert first_watch['watchpoint_id']==second_watch['watchpoint_id']
        watch={'offset':13,'length':4,'access':'rw'}
        assert session.rpc.call('watch.add',watch)['count']==1
        session.delete_watchpoint(second_watch['watchpoint_id'])
        with pytest.raises(ValueError,match='Unknown'):
            session.delete_watchpoint(first_watch['watchpoint_id'])
        assert session.rpc.call('watch.remove',watch)['count']==0
        result=session.run(max_instructions=1,timeout_ms=10000)
        assert result['outcome']=='budget' and result['executed']==1
