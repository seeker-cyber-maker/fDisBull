"""CHIP-8 selected-undo public routing and preflight."""
from types import SimpleNamespace
import pytest
from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.debug_script import validate_script


def _script(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}


def test_delta_script_grammar_and_partial_resume_preflight():
    start={'op':'delta-start','ranges':[{'address':0x300,'length':1}],'registers':['v0','pc']}
    assert validate_script(_script(start))==[start]
    with pytest.raises(ValueError,match='partial.resume|partial resume'):
        validate_script(_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},
            {'op':'delta-rewind','policy':{'allow_partial_resume':True}}))


def test_delta_json_route_forwards_registers(tmp_path):
    calls=[];workspace=DebugWorkspace()
    def start(**kwargs):calls.append(kwargs);return {'registers':kwargs['registers']}
    workspace.sessions['chip8']=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),cpu_delta_start=start)
    args={'ranges':[{'address':0x300,'length':1}],'registers':['v0','pc'],'timeout_ms':400}
    try:
        reply=respond({'method':'debug-delta-start','params':{'project':str(tmp_path),'run':'chip8',**args}},debugger=workspace)
        assert reply['ok'] and reply['result']['registers']==['v0','pc'],reply
        assert calls==[args]
    finally:workspace.sessions.clear()


from fdisbull.debug_script import execute_script
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session


class RoutedChip8Delta(MachineDebugSession):
    backend_name='qemu-chip8'
    _delta_registers=frozenset(['i','pc']+[f'v{x:x}' for x in range(16)])
    _delta_max_bytes=256*1024**2
    @property
    def script_operations(self):
        return {'write-memory','delta-start','delta-record','delta-rewind','delta-status','delta-recover'}
    def cpu_delta_start(self,ranges,*,registers=None,max_steps=16,max_bytes=67108864,timeout_ms=60000):
        self.calls.append(('start',ranges,registers));return {'anchor':{'artifact':'a'}}
    def cpu_delta_record(self,count=1,timeout_ms=10000):
        self.calls.append(('record',count));return self.record_receipt
    def cpu_delta_rewind(self,count=1,*,policy=None,timeout_ms=60000):
        self.calls.append(('rewind',count,policy));return {'partial_restored':True}
    def write_memory(self,*args,**kwargs):self.writes.append((args,kwargs));return {'written':True}


def _routed(project,tmp_path):
    session,peer=stopped_session(project,tmp_path);session.__class__=RoutedChip8Delta
    session.metadata['backend']='qemu-chip8';session.capabilities['selected_cpu_ram_undo']=True
    session.calls=[];session.writes=[]
    return session,peer


@pytest.mark.parametrize('bad',[
    {'op':'delta-start','ranges':[{'address':4096,'length':1}]},
    {'op':'delta-start','ranges':[{'address':4095,'length':2}]},
    {'op':'delta-start','ranges':[{'address':0x300,'length':2},{'address':0x301,'length':1}]},
    {'op':'delta-start','ranges':[{'address':0,'length':4097}]},
    {'op':'delta-start','ranges':[{'address':0x300,'length':1}],'registers':['sp']},
    {'op':'delta-start','ranges':[{'address':0x300,'length':1}],'registers':['stack0']},
    {'op':'delta-start','ranges':[{'address':0x300,'length':1}],'registers':['v0','v0']},
    {'op':'delta-start','ranges':[{'address':0x300,'length':1}],'max_bytes':256*1024**2+1},
    {'op':'delta-rewind','policy':{'preserve_memory':[{'address':4095,'length':2}]}},
    {'op':'delta-rewind','policy':{'allow_partial_resume':True}},
])
def test_invalid_known_chip8_delta_script_refuses_before_prior_write(raw_project,tmp_path,bad):
    session,peer=_routed(raw_project,tmp_path)
    try:
        with pytest.raises(ValueError):
            execute_script(session,_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},bad))
        assert not session.writes and not session.calls and not peer.calls
    finally:session.close()


@pytest.mark.parametrize('blocked',['capability','transaction'])
def test_chip8_delta_script_capability_and_transaction_refuse_before_prior_write(raw_project,tmp_path,blocked):
    session,peer=_routed(raw_project,tmp_path)
    try:
        if blocked=='capability':
            session.capabilities['selected_cpu_ram_undo']=False
            with pytest.raises(ValueError):execute_script(session,_script(
                {'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},
                {'op':'delta-start','ranges':[{'address':0x300,'length':1}]}))
        else:
            with raw_project.transaction(True):
                with pytest.raises(ValueError):execute_script(session,_script(
                    {'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},
                    {'op':'delta-start','ranges':[{'address':0x300,'length':1}]}))
        assert not session.writes and not session.calls and not peer.calls
    finally:session.close()


@pytest.mark.parametrize('outcome,recorded',[('interrupted',1),('context_changed',1),('completed',2)])
def test_incomplete_chip8_delta_script_preserves_receipt_and_stops(raw_project,tmp_path,outcome,recorded):
    session,peer=_routed(raw_project,tmp_path)
    receipt={'outcome':outcome,'requested_count':3,'recorded_count':recorded,
             'records':[{'artifact':'one'}],'stop':{'outcome':'breakpoint'}}
    session.record_receipt=receipt
    try:
        report=execute_script(session,_script({'op':'delta-record','count':3},
            {'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'}))
        assert not report['ok'] and report['completed_steps']==0
        assert report['steps'][0]['result']==receipt and session.calls==[('record',3)]
        assert not session.writes and not peer.calls
    finally:session.close()
