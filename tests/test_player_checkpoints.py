import copy
import io
import json
import sqlite3
import threading
from contextlib import contextmanager
from types import SimpleNamespace

from fdisbull import player_checkpoints
from fdisbull.text_projection import serve_stream
from native_fixture import prepare_native_fixture


class Project:
    def __init__(self,path):
        self.db=sqlite3.connect(path); self.db.row_factory=sqlite3.Row
        self.meta={'source_sha256':'source','format':'MZ','arch':'x86','bits':16}
    def version(self,version=None): return {'id':1,'sha256':'mapped'}
    @contextmanager
    def transaction(self,write=False):
        with self.db: yield
    def debug_text_projection_info(self,name,version=None):
        return {'id':'projection','sha256':'projection-hash','definition':{'workflow_revision':'workflow'}}
    def _experiment_document(self,artifact,version):
        row=self.db.execute('SELECT body FROM fake_experiments WHERE id=?',(artifact,)).fetchone()
        if not row: raise ValueError('missing experiment')
        return json.loads(row['body'])


class Session:
    def __init__(self,project):
        self.project=project; self.version={'id':1}; self.metadata={'source_sha256':'source',
            'version_sha256':'mapped','emulator_sha256':'emulator','runtime_load_segment':1,'runtime_profile':'profile'}
        self.state=0; self.epoch=0; self.stopped=False; self.witness='aa'; self.drift=False
        self._runtime_names={'actor':'binding'}
        self._runtime_bindings={'binding':{'name':'actor','address':100,'length':8,'expected_hex':'aa',
                                            'mask_hex':'ff','provenance':{'method':'test'}}}
        project.db.execute('CREATE TABLE IF NOT EXISTS fake_experiments (id TEXT PRIMARY KEY, body TEXT)')
    def call(self,op): return {'state':'stopped'}
    def runtime_memory(self,name,**kwargs): return {'witness_hex':self.witness}
    def save_experiment(self,name,script):
        ident='experiment-'+str(self.state)
        self.project.db.execute('INSERT OR REPLACE INTO fake_experiments VALUES (?,?)',(ident,json.dumps({'state':self.state})))
        return {'artifact':ident}
    def restore_experiment(self,ident):
        self.state=self.project._experiment_document(ident,1)['state']; self.epoch+=1
        self._runtime_names={}; self._runtime_bindings={}
    def bind_runtime_memory(self,**recipe):
        self._runtime_names[recipe['name']]='new'; self._runtime_bindings['new']=recipe
        return {'witness_hex':'aa'}
    def run(self,**kwargs):
        if self.stopped: return {'outcome':'breakpoint','guest_elapsed_ms':1,'hook_hits':[]}
        if self.drift: self.witness='ab'
        return {'outcome':'guest_time','guest_elapsed_ms':kwargs['guest_ms'],'hook_hits':[]}


class Handle:
    def __init__(self,session):
        self.session=session; self.info={'id':'projection'}; self.lock=threading.RLock(); self.secret=b'old'
        self.workflow=SimpleNamespace(revision='workflow',info={'sha256':'wf-hash',
            'definition':{'inventory':{'sha256':'resources'}}},_fresh=lambda:None)
    def _read(self): return None if getattr(self,'_checkpoint_failed',False) else {'complete':True}


def test_slot_history_and_restart_restore(tmp_path):
    path=tmp_path/'private.sqlite'; p=Project(path); s=Session(p); h=Handle(s)
    assert player_checkpoints.load(h)=={'status':'missing','complete':True}
    s.state=10; a=player_checkpoints.save(h); s.state=20; b=player_checkpoints.save(h)
    assert a['complete'] and b['complete'] and a['checkpoint']!=b['checkpoint']
    p.db.close(); p=Project(path); s=Session(p); h=Handle(s)
    restored=player_checkpoints.load(h)
    assert restored['status']=='restored' and s.state==20 and h.secret!=b'old'
    assert restored['preparation']=={'requested_guest_ms':100,'guest_elapsed_ms':100}
    assert player_checkpoints.load(h,a['checkpoint'])['status']=='restored' and s.state==10
    assert p.db.execute('SELECT count(*) FROM player_checkpoints').fetchone()[0]==2


def test_hex_shaped_slot_takes_precedence_over_opaque_checkpoint_id(tmp_path):
    p=Project(tmp_path/'private.sqlite'); s=Session(p); h=Handle(s)
    slot='a'+'0'*31
    s.state=42
    saved=player_checkpoints.save(h,slot)
    assert saved['complete'] and saved['slot']==slot
    s.state=0
    restored=player_checkpoints.load(h,slot)
    assert restored['status']=='restored' and s.state==42
    # Checkpoint IDs remain accepted directly even when they also match slot syntax.
    s.state=0
    assert player_checkpoints.load(h,saved['checkpoint'])['status']=='restored' and s.state==42


def test_explicit_id_selector_bypasses_colliding_hex_slot(tmp_path,monkeypatch):
    from types import SimpleNamespace
    p=Project(tmp_path/'private.sqlite'); s=Session(p); h=Handle(s)
    ids=iter(['a'*32,'c'*32,'b'*32,'d'*32,'e'*32,'f'*32])
    monkeypatch.setattr(player_checkpoints.uuid,'uuid4',lambda:SimpleNamespace(hex=next(ids)))
    s.state=11
    first=player_checkpoints.save(h)
    assert first['complete']
    # Saving at a slot named after the first opaque ID deliberately shadows it.
    s.state=22
    shadow=player_checkpoints.save(h,first['checkpoint'])
    assert shadow['complete'] and shadow['checkpoint']!=first['checkpoint']
    assert player_checkpoints.load(h,first['checkpoint'])['status']=='restored' and s.state==22
    assert player_checkpoints.load(h,'id:'+first['checkpoint'])['status']=='restored' and s.state==11


def test_corrupt_incompatible_and_stopped_restores_never_claim_success(tmp_path):
    p=Project(tmp_path/'private.sqlite'); s=Session(p); h=Handle(s)
    saved=player_checkpoints.save(h); assert saved['complete']
    s.metadata['emulator_sha256']='changed'
    assert player_checkpoints.load(h)['status']=='incomplete' and s.epoch==0 and h._checkpoint_failed
    assert player_checkpoints.load(h,'nonexistent')['status']=='incomplete'
    s.metadata['emulator_sha256']='emulator'
    s.stopped=True
    assert player_checkpoints.load(h)['status']=='incomplete' and h._checkpoint_failed and s.epoch==1
    assert player_checkpoints.save(h)['status']=='incomplete'
    s.stopped=False
    assert player_checkpoints.load(h)['status']=='restored' and not h._checkpoint_failed
    p.db.execute("UPDATE player_checkpoints SET document='{}' WHERE id=?",(saved['checkpoint'],))
    assert player_checkpoints.load(h)['status']=='incomplete'
    assert 'changed' not in json.dumps(player_checkpoints.load(h))


def test_wire_dispatches_checkpoint_operations_without_private_exceptions():
    class Backend:
        def save(self,slot): return {'status':'saved','complete':True,'slot':slot,'checkpoint':'opaque'}
        def load(self,checkpoint): return {'status':'restored','complete':True,'checkpoint':checkpoint}
    output=io.StringIO()
    serve_stream(Backend(),io.StringIO('{"op":"save","slot":"live"}\n{"op":"load","checkpoint":"opaque"}\n'),output)
    assert [json.loads(x)['status'] for x in output.getvalue().splitlines()]==['saved','restored']


def test_restore_refuses_witness_changed_during_preparation_before_projection_read(tmp_path):
    p=Project(tmp_path/'private.sqlite'); s=Session(p); h=Handle(s)
    assert player_checkpoints.save(h)['status']=='saved'
    reads=[]
    h._read=lambda: reads.append('read') or {'complete':True}
    s.drift=True
    assert player_checkpoints.load(h)=={'status':'incomplete','complete':False}
    assert reads==[] and h._checkpoint_failed and s._player_checkpoint_failed
    assert player_checkpoints.save(h)['status']=='incomplete'


def test_native_experiment_restores_across_project_restart(tmp_path,monkeypatch):
    import os
    import pytest
    from fdisbull.project import Project as RealProject
    from test_dos_loader import mz_file
    backend=os.environ.get('FDISBULL_DOSBOX')
    if not backend: pytest.skip('FDISBULL_DOSBOX required')
    game=tmp_path/'game'; game.mkdir(); binary=game/'LOOP.EXE'
    binary.write_bytes(mz_file(b'\xeb\xfe'+bytes(510),ss=0,sp=0x200))
    path=tmp_path/'private.fdb'
    monkeypatch.setattr(player_checkpoints,'_compatibility',lambda h:{'fixture':'native'})
    def handle(session):
        h=SimpleNamespace(session=session,lock=threading.RLock(),secret=b'old')
        h._read=lambda: None if getattr(h,'_checkpoint_failed',False) else {'complete':True}
        return h
    with RealProject.create(path,binary) as p, p.debugger(backend,game) as d:
        prepare_native_fixture(d)
        d.bind_runtime_memory('actor',d.runtime_load*16+0x20,length=4,expected_hex='00',provenance={'method':'synthetic'})
        d.breakpoint('1000:0030',access='w')
        h=handle(d); saved=player_checkpoints.save(h)
        assert saved['complete'], [tuple(row) for row in p.db.execute('SELECT detail FROM player_checkpoint_events')]
    with RealProject(path) as p, p.debugger(backend,game) as d:
        h=handle(d); result=player_checkpoints.load(h)
        assert result['status']=='restored', [tuple(x) for x in p.db.execute('SELECT detail FROM player_checkpoint_events')]
        assert len(d.controls()['breakpoints'])==1
        assert d.runtime_memory('actor',offset=0,length=1)['hex']=='00'
        assert result['preparation']['guest_elapsed_ms']>=100 and h.secret!=b'old'
