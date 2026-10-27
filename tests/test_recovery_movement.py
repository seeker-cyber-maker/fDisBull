import pytest
import fdisbull.movement as m
from types import SimpleNamespace
class Handle:
 info={'definition':{'navigation':{}}}
 def navigation_check(self,p): return {'classification':'clear' if p in ([0,0],[1,0]) else 'blocked','manifest_sha256':'hash'}
class Fake(m.MovementSessionMixin):
 run_id='r';version={'id':1};closed=False;rpc=SimpleNamespace(capabilities={'timing':{'fast_forward':True}})
 def __init__(self, samples,keyboard):self.samples=iter(samples);self.kb=keyboard
 def _macro_plan(self,*a):return {'id':'m','sha256':'h'},{'script':{'steps':[{'op':'keyboard.press'}]}}
 def scene(self,*a):return Handle()
 def macro(self,*a,**k):return {'ok':True}
 def run(self,**k):return {'outcome':'guest_time','guest_elapsed_ms':1,'hook_hits':[]}
 def keyboard_state(self):return {'keyboard':self.kb}
 def screenshot(self,*a,**k):return {'artifact':'s','metadata':{}}
 def _event(self,*a):pass
 def _artifact(self,*a):return {'artifact':'r'}
 def close(self):self.closed=True
@pytest.fixture(autouse=True)
def observations(monkeypatch):
 monkeypatch.setattr(m,'capture_observations',lambda s,o: {'complete':True,'values':next(s.samples)})
def call(s):
 return s.move('m',start={'name':'start'},stop={'name':'stop'},observations={'x':{'status':'x'},'y':{'status':'y'},'stop':{'status':'stop'}},until={'field':'x','op':'ge','value':1},settle={'field':'stop','op':'eq','value':True},progress={'fields':['x'],'samples':2},scene='map',position={'x':'x','y':'y'},target=[1,0],timeout_ms=1000)


def test_drift(monkeypatch):
 s=Fake([{'x':0,'y':0,'stop':True},{'x':1,'y':0,'stop':False},{'x':2,'y':0,'stop':True}],{'pending_events':[],'owned_keys':[]})
 r=call(s);assert not r['ok'] and not r['complete']

def test_existing_input(monkeypatch):
 s=Fake([{'x':1,'y':0,'stop':True}],{'pending_events':['press'],'owned_keys':['left']})
 r=call(s);assert not r['ok'] and not r['complete'] and not s.closed

def test_bad_stop_reference_rejected_before_input():
 from fdisbull.input_macros import expand_macro
 definition={'format':'fdisbull-macro-set-1','name':'moves','macros':{'start':{'steps':[{'op':'keyboard.key-down','key':'left','as':'hold'}],'outputs':{'lease':'$hold.lease'}},'stop':{'parameters':{'lease':{'type':'input-lease'}},'steps':[{'op':'keyboard.key-up','lease':'$args.lease'}]}}}
 class Planned(Fake):
  def _macro_plan(self,ms,name,args):return {'id':'m','sha256':'h'},expand_macro(definition,name,args)
 s=Planned([{'x':0,'y':0,'stop':True}],{'pending_events':[],'owned_keys':[]})
 with pytest.raises(ValueError,match='start output'):
  s.move('m',start={'name':'start'},stop={'name':'stop','args':{'lease':'$start.outputs.missing'}},observations={'x':{'status':'x'},'y':{'status':'y'},'stop':{'status':'stop'}},until={'field':'x','op':'ge','value':1},settle={'field':'stop','op':'eq','value':True},progress={'fields':['x'],'samples':2},timeout_ms=1000)

def test_already_arrived_keyboard_failure_is_not_success():
 class Broken(Fake):
  def keyboard_state(self):raise RuntimeError('keyboard unavailable')
 s=Broken([{'x':1,'y':0,'stop':True}],{})
 r=call(s);assert not r['ok'] and not r['complete']

def test_already_arrived_missing_keyboard_fields_is_not_success():
 class Broken(Fake):
  def keyboard_state(self):return {'keyboard':{}}
 s=Broken([{'x':1,'y':0,'stop':True}],{})
 r=call(s);assert not r['ok'] and not r['complete']
