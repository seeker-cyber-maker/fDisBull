"""Synthetic-only acceptance and refusal tests for the Kyra debug controller.

These tests DO NOT qualify a ScummVM native build or original DOS behavior.
"""
import base64
import hashlib
import importlib.util
import sys
import json
import types

import pytest

from fdisbull.scummvm_rpc import ScummVMError
from fdisbull.project import Project
from fdisbull.model import Image, Region, Seed
from fdisbull.scummvm_kyra import (_manifest, _REQUIRED, ScummVMKyraSession,
                                      validate_kyra_hello, validate_kyra_state)


def hello(game_id='kyra1', **overrides):
    data = {'engine': 'kyra', 'protocol': 'fdisbull-scummvm-agent',
            'protocol_version': 1, 'bridge_version': 1,
            'profile': 'kyra-emc2-v1',
            'capabilities': sorted(_REQUIRED | {'input.status', 'watch.add', 'watch.remove'}),
            'variant': {'recognized_detection': True, 'game_id': game_id}}
    data.update(overrides)
    return data


def state(game_id='kyra1', *, ip_word=3, name='GEMCUT.EMC', generation=1):
    return {'game_id':game_id, 'phase':'before_opcode', 'guest_ms':100,
            'frame_revision':2, 'script':{'name':name, 'generation':generation,
                                         'data_words':50, 'loaded_data_sha256':'a'*64},
            'ip_word':ip_word,'game':{'room':7} if game_id=='kyra1' else
            {'level':1,'block':73,'direction':2},'registers':[0,1,2]}


def test_hello_accepts_only_real_kyra_emc2_profile():
    assert validate_kyra_hello(hello(),game_id='kyra1')['game_id']=='kyra1'
    assert validate_kyra_hello(hello('lol'),game_id='lol')['game_id']=='lol'
    for invalid in [hello(engine='gob'), hello(profile='gob-inter-v3'),
                    hello(protocol_version=0), hello(capabilities=['state.get']),
                    hello(variant={'recognized_detection':False,'game_id':'kyra1'})]:
        with pytest.raises(ScummVMError):
            validate_kyra_hello(invalid,game_id='kyra1')
    with pytest.raises((ValueError, ScummVMError)):
        validate_kyra_hello(hello(),game_id='eob')


def test_state_uses_data_words_not_file_bytes_and_keeps_profiles_distinct():
    good=state()
    assert validate_kyra_state(good,'kyra1')==good
    for change in [dict(ip_word=50),dict(ip_word=-1),dict(phase='arbitrary'),
                   dict(guest_ms=-1),dict(frame_revision=True),dict(script=None)]:
        bad={**good,**change}
        with pytest.raises(ScummVMError):validate_kyra_state(bad,'kyra1')
    other=state('lol')
    assert validate_kyra_state(other,'lol')['game']['block']==73
    with pytest.raises(ScummVMError):validate_kyra_state(other,'kyra1')
    idle={**good,'phase':'idle','script':None,'ip_word':None}
    assert validate_kyra_state(idle,'kyra1')['script'] is None


def test_manifest_streams_hash_and_refuses_symlink_and_changed_input(tmp_path):
    (tmp_path/'folder').mkdir()
    (tmp_path/'folder'/'DATA.PAK').write_bytes(b'PAK-TEST')
    items=_manifest(tmp_path)
    assert items==[{'path':'folder/DATA.PAK','size':8,
                    'sha256':hashlib.sha256(b'PAK-TEST').hexdigest()}]
    (tmp_path/'link').symlink_to('folder/DATA.PAK')
    with pytest.raises(ValueError,match='symlinks'): _manifest(tmp_path)


class FakeRPC:
    hello_response=hello()
    source_state=state()
    frames=bytes([5,10,15])*12
    instances=[]

    def __init__(self,executable,game_dir,*,engine,game_id,runtime_parent,boot_timeout_ms,on_spawn):
        self.game_id=game_id
        self.hello=hello(game_id)
        self.process=types.SimpleNamespace(pid=45678)
        self.capabilities={'features':list(self.hello['capabilities']), 'virtual_time':True}
        self.calls=[]
        self.closed=False
        self.selected=state(game_id)
        self.__class__.instances.append(self)

    def call(self,op,params=None,*,timeout_ms=10000):
        self.calls.append((op,params))
        if op=='state.get':return self.selected
        if op=='step':
            self.selected={**self.selected, 'ip_word':self.selected['ip_word']+params['count'],
                           'guest_ms':self.selected['guest_ms']+4}
            return {'stop':{'reason':'step','instructions':params['count']}}
        if op=='run':
            self.selected={**self.selected,'ip_word':self.selected['ip_word']+1,
                           'guest_ms':self.selected['guest_ms']+20}
            return {'stop':{'reason':'budget','instructions':1}}
        if op in ('break.add','break.remove','watch.add','watch.remove','trace.start','trace.stop','quit'):
            return {'ok':True}
        if op=='trace.get':
            return {'entries':[{'script':'GEMCUT.EMC','word_offset':3,'opcode':3}]}
        if op=='frame.get':
            return {'width':4,'height':3,'revision':2,'pixel_format':'rgb24',
                    'mode_id':4,'rgb24_base64':base64.b64encode(self.frames).decode()}
        if op=='input':return {'queued':2}
        if op=='input.status':return {'pending':2,'held_keycodes':[],'leases':[]}
        raise AssertionError('unexpected fake RPC '+op)

    def close(self): self.closed=True


@pytest.fixture
def session(tmp_path,monkeypatch):
    import fdisbull.scummvm_kyra as mod
    FakeRPC.instances.clear()
    monkeypatch.setattr(mod,'ScummVMRPC',FakeRPC)
    game=tmp_path/'game';game.mkdir()
    # Raw x86 fixture is author-created, not a shipped game program.
    owner=game/'GAME.EXE';owner.write_bytes(b'\x90\x90\xc3'+bytes(20))
    dbfile=tmp_path/'experiment.fdb'
    if importlib.util.find_spec('lief') is None:
        # Only this synthetic fixture needs a raw image loader; no LIEF APIs used.
        monkeypatch.setitem(sys.modules,'lief',types.ModuleType('lief'))
    tool=tmp_path/'patched-scummvm';tool.write_bytes(b'#!/bin/sh\nexit 1\n');tool.chmod(0o700)
    raw=owner.read_bytes()
    image=Image('raw','x86',16,0x1000,[Region('raw',0x1000,raw,True)],
                [Seed(0x1000,'entry','entry')],
                {'source_sha256':hashlib.sha256(raw).hexdigest(),
                 'file_mappings':[{'virtual_address':0x1000,'file_offset':0,'file_size':len(raw)}]},
                source_bytes=raw)
    with Project._create_image(dbfile,owner.name,image,
            loader_options={'arch':'x86','bits':16,'base':0x1000,'entry':0x1000}) as project:
        with ScummVMKyraSession(project,tool,game,game_id='kyra1') as debug:
            yield debug,FakeRPC.instances[-1],project,owner


def test_session_persists_real_project_identity_and_vm_context(session):
    debug,rpc,project,owner=session
    engine=debug.engine_state()
    assert engine['game']['room']==7
    assert engine['position']['offset']==6
    assert engine['position']['offset_origin']=='decoded_DATA_chunk'
    assert engine['loaded_script_original_bytes_verified'] is False
    assert debug.status()['state']=='stopped'
    assert debug.contexts()['selected']=='kyra-emc2'
    assert debug.metadata['original_x86_executed'] is False


def test_native_control_scaffold_records_guards_and_budgeted_steps(session,tmp_path):
    debug,rpc,project,owner=session
    addr={'script':'GEMCUT.EMC','generation':1,'offset':6,'loaded_data_sha256':'a'*64}
    first=debug.breakpoint(addr)
    assert debug.breakpoint(addr)['breakpoint_id']==first['breakpoint_id']
    with pytest.raises(ValueError,match='align'):
        debug.breakpoint({**addr,'offset':7})
    with pytest.raises(ValueError,match='Stale'):
        debug.breakpoint({**addr,'generation':2})
    wp=debug.watchpoint('register',2)
    assert wp['all_native_writes_covered'] is False
    step=debug.step(2)
    assert step['completed'] and step['before']['word_offset']==3
    result=debug.run(max_instructions=3)
    assert result['outcome']=='budget' and result['executed']==1
    assert result['guest_elapsed_ms']==20
    debug.delete_breakpoint(first['breakpoint_id'])
    debug.delete_watchpoint(wp['watchpoint_id'])
    with pytest.raises(ValueError,match='Unknown'):
        debug.delete_breakpoint(first['breakpoint_id'])


def test_frame_is_true_rgb_and_inputs_are_only_queued(session,tmp_path):
    debug,rpc,project,owner=session
    frame=debug.frame_probe([[0,0],[3,2]])
    assert frame['pixels'][0]['rgb']==[5,10,15]
    saved=debug.screenshot('kyra.png')
    name=tmp_path/'frame.png';project.debug_export(saved['artifact'],name)
    assert name.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    identity=frame['frame']['frame_id']
    with pytest.raises(ValueError,match='Stale'):
        debug.click(0,0,frame_id='bad')
    with pytest.raises(ValueError,match='outside'):
        debug.click(4,0)
    input_receipt=debug.click(2,2,frame_id=identity)
    assert input_receipt['queued']==2 and input_receipt['consumed'] is False
    assert debug.keyboard_press('enter')['consumed'] is False
    assert debug.keyboard_type('x')['queued']==2


def test_trace_artifact_and_unqualified_mutations_refused(session,tmp_path):
    debug,rpc,project,owner=session
    tr=debug.trace(count=3)
    assert tr['event_count']==1
    path=tmp_path/'trace.json';project.debug_export(tr['artifact'],path)
    assert json.loads(path.read_text())['events'][0]['opcode']==3
    for fn,args in [(debug.write_engine_state,('register',0,1)),
                    (debug.save_state,()),(debug.patch_resource,())]:
        with pytest.raises(ValueError):fn(*args)


def test_source_drift_rejected_before_any_additional_engine_rpc(session):
    debug,rpc,project,owner=session
    before=len(rpc.calls)
    owner.write_bytes(owner.read_bytes()+b'changed')
    with pytest.raises(ScummVMError,match='manifest changed'):
        debug.engine_state()
    assert len(rpc.calls)==before
