"""Terminal protocol contracts; native qualification is a separate acceptance."""
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull import dinopark_terminal as terminal
from fdisbull.dinopark_z import ZService
from fdisbull.dinopark_scenes import EXPECTED_EXE


def patterns():
    result = {}
    for name in ('newgame','save'):
        result.update(json.loads((Path(terminal.__file__).with_name('data') /
                     f'dinopark-e55-{name}.json').read_text())['scenes'])
    return result


def image_for(view, profiles):
    image = Image.new('RGB',(320,200),(0,0,0))
    names = {'live':['office'], 'menu':['game_menu'], 'confirm':['game_menu','quit_confirm'],
             'save':['game_menu','quit_save'], 'title':['title_menu','title_exit'], 'black':[]}[view]
    for name in names:
        for sample in {**profiles,**terminal.PATTERNS}[name]['samples']:
            image.putpixel((sample['x'],sample['y']),tuple(sample['rgb']))
    return image


class Native:
    metadata = {'source_sha256':EXPECTED_EXE,'runtime_load_segment':0x824,
                'entry_registers':{'segments':{'ds':'0x0814','es':'0x0814'}}}
    rpc = SimpleNamespace(capabilities={'lifecycle':{'dos_guest_exit':True}})
    run_id = 'native-boundary'

    def __init__(self):
        self.view='live'; self.revision=1; self.calls=[]; self.inputs=[]
        self.destination=None; self.remaining=0; self.exit_delay=1
        self.exit_psp='0x0814'; self.terminated=False

    def call(self, method, params=None):
        self.calls.append(method)
        if method=='session.status':
            return {'session_id':'same-native','state':'exited' if self.terminated else 'stopped',
                    'state_revision':self.revision,'last_stop':{'kind':'pause'}}
        assert method=='input.mouse.move'
        self.revision+=1
        return {'accepted':True}

    def registers(self): return {'state_revision':self.revision}

    def keyboard_press(self,key,**kw):
        assert key=='escape'
        self.inputs.append(('key',key))
        self.destination='menu' if self.view=='live' else 'live';self.remaining=1
        return {'accepted':True,'delivery':'queued'}

    def click(self,x,y,**kw):
        self.inputs.append(('click',x,y))
        choices={('menu',160,170):'live',('menu',189,138):'confirm',('confirm',148,106):'menu',
                 ('confirm',175,106):'save',('save',148,115):'title',('title',221,160):'exited'}
        self.destination=choices[(self.view,x,y)]
        self.remaining=self.exit_delay if self.destination=='exited' else 1
        return {'accepted':True,'delivery':'queued'}

    def run(self,**kw):
        self.calls.append('execution.run');self.revision+=1
        if self.destination:
            self.remaining-=1
            if self.remaining<=0:
                self.view=self.destination;self.destination=None
                if self.view=='exited':
                    self.terminated=True
                    return {'outcome':'guest_exit','session':{'session_id':'same-native','state':'exited',
                            'state_revision':self.revision,'stop_reason':{'kind':'guest_exit','guest_exit':{
                            'psp':self.exit_psp,'parent_psp':'0x0701','requested_exit_code':0,'resident':False,
                            'source':'DOS_Terminate','stage':'after-process-cleanup'}}}}
            elif self.destination=='exited': self.view='black'
        return {'outcome':'guest_time','hook_hits':[]}


def harness(tmp_path,monkeypatch):
    native=Native();profile=patterns();events=[]
    text=SimpleNamespace(debug=native,current='office',patterns=profile,event=events.append,
                         project=None,vegasaurus_extinct=False)
    def describe():
        assert native.view=='live'
        return 'The original office.'
    text.describe=describe
    def capture(project,debug,name):
        assert not native.terminated,'freed-target screenshot attempted'
        return {'artifact':'stored-frame'},image_for(native.view,profile)
    monkeypatch.setattr(terminal,'take_frame',capture)
    service=ZService(tmp_path,io.StringIO(),io.StringIO());service.text=text
    return service,native,events


def request(service, value):
    before=len(service.writer.getvalue())
    service.reader=io.StringIO(json.dumps(value)+'\n')
    with pytest.raises(EOFError): service.command()
    return json.loads(service.writer.getvalue()[before:])


def act(service,verb,target):
    obs=service.observe();assert obs['complete']
    return request(service,{'op':'act','action':{'verb':verb,'target':target,'item':None,'context_token':obs['context']['token']}})


def title(service):
    assert act(service,'open','terminal-menu')['status']=='success'
    assert act(service,'quit','terminal-park')['status']=='accepted'
    assert act(service,'confirm','terminal-quit')['status']=='accepted'
    assert act(service,'decline','terminal-save')['status']=='success'
    assert service.observe()['context']['id']=='terminal.title'


def test_named_menu_cancellation_and_resumption_share_the_same_guest(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch)
    assert any(o['label']=='game menu' for o in service.observe()['objects'])
    assert act(service,'open','terminal-menu')['status']=='success'
    assert service.observe()['context']['id']=='terminal.menu'
    assert act(service,'quit','terminal-park')['effects']=='partial'
    assert act(service,'cancel','terminal-quit')['status']=='success'
    assert act(service,'resume','terminal-park')['status']=='success'
    assert service.observe()['context']['id']=='office'
    assert len(native.inputs)==4 and not service.recovery_required


def test_quit_to_title_and_delayed_dos_exit_never_repeat_input(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch);title(service)
    native.exit_delay=6
    result=act(service,'exit','terminal-dos')
    assert result['status']=='accepted' and service.terminal.phase=='transition'
    inputs=deepcopy(native.inputs)
    assert [o['verbs'] for o in service.observe()['objects']]==[['continue']]
    assert act(service,'continue','terminal-transition')['status']=='success'
    assert native.inputs==inputs
    assert service.terminal.exit['psp']=='0x0814'
    before=list(native.calls)
    obs=service.observe()
    assert obs['complete'] and obs['context']['id']=='terminal.exited' and obs['objects']==[]
    assert native.calls==before,'post-exit observation contacted disposed target'


def test_stale_token_and_wrong_scene_actions_send_no_control(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch)
    old=service.observe()['context']['token']
    act(service,'open','terminal-menu');sent=len(native.inputs)
    result=request(service,{'op':'act','action':{'verb':'quit','target':'terminal-park','item':None,'context_token':old}})
    assert result['status']=='rejected'
    assert act(service,'exit','terminal-dos')['status']=='rejected'
    assert len(native.inputs)==sent


def test_changed_pending_revision_cannot_advance_or_repeat_control(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch);title(service);native.exit_delay=99
    act(service,'exit','terminal-dos');sent=len(native.inputs)
    native.revision+=1
    assert service.observe()['complete'] is False
    assert len(native.inputs)==sent


def test_wait_budget_is_shared_and_expiry_preserves_a_live_recovery_hold(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch);title(service);native.exit_delay=99
    act(service,'exit','terminal-dos');sent=len(native.inputs)
    for _ in range(5):
        if service.recovery_required: break
        act(service,'continue','terminal-transition')
    assert service.recovery_required and not native.terminated
    assert service.pending is None and len(native.inputs)==sent
    assert service.terminal.pending['guest_ms']==20000
    assert request(service,{'op':'act','action':{}})['status']=='rejected'


def test_unsupported_lifecycle_is_refused_before_exit_click(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch);title(service)
    native.rpc=SimpleNamespace(capabilities={});sent=len(native.inputs)
    assert act(service,'exit','terminal-dos')['status']=='rejected'
    assert len(native.inputs)==sent and service.terminal.phase=='title'


def test_foreign_process_exit_cannot_become_a_dos_completion(tmp_path,monkeypatch):
    service,native,_=harness(tmp_path,monkeypatch);title(service);native.exit_psp='0x9999'
    result=act(service,'exit','terminal-dos')
    assert not result['complete'] and result['effects']=='unknown'
    assert service.recovery_required and service.terminal.exit is None


def test_specific_prompts_take_precedence_over_underlying_menu(tmp_path,monkeypatch):
    service,_,_=harness(tmp_path,monkeypatch);engine=terminal.TerminalScenes(service.text)
    for name in ('live','menu','confirm','save','title'):
        assert engine._classify(image_for(name,service.text.patterns))==name
    image=image_for('confirm',service.text.patterns)
    for p in terminal.PATTERNS['quit_save']['samples']: image.putpixel((p['x'],p['y']),tuple(p['rgb']))
    with pytest.raises(RuntimeError,match='Ambiguous'): engine._classify(image)
    assert engine._classify(image_for('black',service.text.patterns)) is None
