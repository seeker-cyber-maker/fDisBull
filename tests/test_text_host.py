import json
import queue
import socket
import threading

import pytest
import fdisbull.text_host as module


def config():
    return {'format':'fdisbull-text-host-1', 'project':'project.fdb', 'backend':'debugger',
            'game_dir':'game', 'projection':'view', 'state':'saved-state', 'version':1,
            'bindings':[{'name':'actor','address':123,'length':4,'expected_hex':'00','provenance':'test'}],
            'port':0,'timeout_ms':2000}


class Backend:
    def observe(self): return {'complete':True,'context':{'id':'r','token':'t','title':'Room','description':''},'objects':[],'inventory':[],'coverage':{'partial':True}}
    def act(self, request): return {'status':'incomplete','complete':False,'message':'Unavailable.'}


from fdisbull.spatial import SpatialSessionMixin


class Session(SpatialSessionMixin):
    def __init__(self, trace, fail=False): self.trace=trace; self.fail=fail
    def __enter__(self): self.trace.append('session enter'); return self
    def __exit__(self,*args): self.trace.append('session exit')
    def _event(self, operation, evidence): self.trace.append(('event',operation,evidence))
    def load_state(self,state): self.trace.append(('state',state))
    def bind_runtime_memory(self,*args,**kwargs):
        self.trace.append(('bind',args,kwargs))
        if self.fail: raise ValueError('private binding failure')
    def run(self, **kwargs):
        self.trace.append(('run', kwargs))
        return {'outcome':'guest_time','guest_elapsed_ms':100,'hook_hits':[]}
    def text_projection(self,*args): self.trace.append(('projection',args)); return Backend()


def fake_project(trace, fail=False):
    class Project:
        def __init__(self,path): trace.append(('project',path))
        def __enter__(self): trace.append('project enter'); return self
        def __exit__(self,*args): trace.append('project exit')
        def debugger(self,*args,**kwargs): trace.append(('debugger',args,kwargs)); return Session(trace,fail)
    return Project


def test_binding_failure_closes_session_and_project_before_listening(monkeypatch):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace,True)); endpoints=[]
    with pytest.raises(ValueError,match='private binding failure'):
        module.host(config(),on_listen=endpoints.append)
    assert not endpoints and trace[-2:] == ['session exit','project exit']
    assert ('state','saved-state') in trace


def test_real_loopback_roundtrip_and_cleanup(monkeypatch):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace)); endpoints=queue.Queue(); results=queue.Queue()
    def run():
        try: results.put(module.host(config(),on_listen=endpoints.put))
        except Exception as exc: results.put(exc)
    thread=threading.Thread(target=run); thread.start()
    endpoint=endpoints.get(timeout=3)
    assert endpoint['host']=='127.0.0.1'
    with socket.create_connection((endpoint['host'],endpoint['port']),timeout=2) as sock:
        sock.sendall(b'{"op":"observe"}\n')
        with sock.makefile('r',encoding='utf-8') as reader:
            assert json.loads(reader.readline())['context']['title']=='Room'
    thread.join(timeout=3)
    assert not thread.is_alive() and results.get()['status']=='disconnected'
    assert trace[-2:]==['session exit','project exit']
    assert trace.index(('state','saved-state')) < next(i for i,x in enumerate(trace) if isinstance(x,tuple) and x[0]=='bind')


def test_invalid_config_fails_before_project_open(monkeypatch):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace))
    bad=config(); bad['port']=70000
    with pytest.raises(ValueError): module.host(bad)
    assert trace==[]


def test_explicit_preparation_runs_after_bindings_before_listening(monkeypatch):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace)); cfg=config(); cfg['prepare_guest_ms']=100
    cfg['timeout_ms']=1; endpoints=[]
    result=module.host(cfg,on_listen=endpoints.append)
    assert result['status']=='accept_timeout'
    assert endpoints[0]['preparation']=={'requested_guest_ms':100,'guest_elapsed_ms':100,'outcome':'guest_time'}
    call=('run',{'guest_ms':100,'timeout_ms':1,'fast_forward':True,'stop_on_hook':True})
    assert call in trace
    assert next(i for i,x in enumerate(trace) if isinstance(x,tuple) and x[0]=='bind') < trace.index(call)
    assert trace.index(call) < next(i for i,x in enumerate(trace) if isinstance(x,tuple) and x[0]=='projection')


@pytest.mark.parametrize('result', [
    {'outcome':'breakpoint','guest_elapsed_ms':20,'hook_hits':[]},
    {'outcome':'guest_time','guest_elapsed_ms':100,'hook_hits':[{'private':'hit'}]},
    {'outcome':'guest_time','guest_elapsed_ms':99,'hook_hits':[]},
])
def test_interrupted_preparation_never_listens_or_resumes(monkeypatch,result):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace))
    def stopped(self, **kwargs):
        trace.append(('run',kwargs)); return result
    monkeypatch.setattr(Session,'run',stopped)
    cfg=config(); cfg['prepare_guest_ms']=100; endpoints=[]
    with pytest.raises(ValueError,match='preparation stopped'):
        module.host(cfg,on_listen=endpoints.append)
    assert not endpoints and sum(isinstance(x,tuple) and x[0]=='run' for x in trace)==1
    assert trace[-2:]==['session exit','project exit']


def test_invalid_preparation_fails_before_project_open(monkeypatch):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace))
    cfg=config(); cfg['prepare_guest_ms']=10001
    with pytest.raises(ValueError,match='preparation'):
        module.host(cfg)
    assert trace==[]


def test_invalid_checkpoint_preparation_fails_before_project_open(monkeypatch):
    trace=[]; monkeypatch.setattr(module,'Project',fake_project(trace))
    cfg=config(); cfg['checkpoint_prepare_guest_ms']=0
    with pytest.raises(ValueError,match='checkpoint preparation'):
        module.host(cfg)
    assert trace==[]
