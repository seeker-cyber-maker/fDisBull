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
 s=Fake([{'x':0,'y':0,'stop':True},{'x':1,'y':0,'stop':False},{'x':2,'y':0,'stop':True}],{'pending_events':0,'owned_keys':0})
 r=call(s);assert not r['ok'] and not r['complete']

def test_existing_input(monkeypatch):
 s=Fake([{'x':1,'y':0,'stop':True}],{'pending_events':1,'owned_keys':1})
 r=call(s);assert not r['ok'] and not r['complete'] and not s.closed

def test_bad_stop_reference_rejected_before_input():
 from fdisbull.input_macros import expand_macro
 definition={'format':'fdisbull-macro-set-1','name':'moves','macros':{'start':{'steps':[{'op':'keyboard.key-down','key':'left','as':'hold'}],'outputs':{'lease':'$hold.lease'}},'stop':{'parameters':{'lease':{'type':'input-lease'}},'steps':[{'op':'keyboard.key-up','lease':'$args.lease'}]}}}
 class Planned(Fake):
  def _macro_plan(self,ms,name,args):return {'id':'m','sha256':'h'},expand_macro(definition,name,args)
 s=Planned([{'x':0,'y':0,'stop':True}],{'pending_events':0,'owned_keys':0})
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

@pytest.mark.parametrize('keyboard',[
 {'pending_events':1,'owned_keys':0},
 {'pending_events':0,'owned_keys':1},
 {},
])
def test_non_arrived_requires_neutral_input_without_mutation(keyboard):
 class Tracking(Fake):
  def __init__(self):super().__init__([{'x':0,'y':0,'stop':True}],keyboard);self.macros=[];self.runs=0
  def macro(self,*args,**kwargs):self.macros.append(args);return {'ok':True}
  def run(self,**kwargs):self.runs+=1;return super().run(**kwargs)
 s=Tracking(); result=call(s)
 assert not result['ok'] and not result['complete']
 assert s.macros==[] and s.runs==0 and not s.closed
 assert not result['cleanup']['attempted']


def test_non_arrived_keyboard_query_failure_does_not_start():
 class Broken(Fake):
  def __init__(self):super().__init__([{'x':0,'y':0,'stop':True}],{});self.macros=[]
  def keyboard_state(self):raise RuntimeError('unavailable')
  def macro(self,*a,**kw):self.macros.append(a);return {'ok':True}
 s=Broken();result=call(s)
 assert not result['ok'] and not result['cleanup']['attempted'] and not s.macros and not s.closed

@pytest.mark.parametrize('keyboard',[
 {'pending_events':None,'owned_keys':0}, {'pending_events':0,'owned_keys':None},
 {'pending_events':False,'owned_keys':0}, {'pending_events':0,'owned_keys':False},
 {'pending_events':-1,'owned_keys':0}, {'pending_events':'','owned_keys':0},
])
def test_invalid_keyboard_counts_fail_before_start(keyboard):
 class Tracking(Fake):
  def __init__(self):super().__init__([{'x':0,'y':0,'stop':True}],keyboard);self.macros=[]
  def macro(self,*a,**kw):self.macros.append(a);return {'ok':True}
 s=Tracking();r=call(s)
 assert not r['ok'] and not r['cleanup']['attempted'] and not s.macros and not s.closed

def test_invalid_cleanup_counts_cannot_confirm_stop():
 class BadCleanup(Fake):
  def __init__(self):super().__init__([{'x':0,'y':0,'stop':True},{'x':1,'y':0,'stop':True},{'x':1,'y':0,'stop':True}],{});self.n=0
  def keyboard_state(self):
   self.n+=1
   return {'keyboard':{'pending_events':0,'owned_keys':0} if self.n==1 else {'pending_events':None,'owned_keys':0}}
 s=BadCleanup();r=call(s)
 assert not r['ok'] and not r['cleanup']['settled']
