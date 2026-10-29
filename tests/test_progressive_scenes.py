import sqlite3
import threading
from contextlib import contextmanager
from copy import deepcopy

import pytest

from fdisbull.progressive_scenes import ProgressiveSceneProjectMixin, ProgressiveSceneSessionMixin, resource_inventory
from fdisbull.scene_bundles import identity


class Project(ProgressiveSceneProjectMixin):
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.meta = dict(source_sha256='source', format='MZ', arch='x86', bits=16)
    def version(self, version=None):
        if version not in (None, 1): return {'id':version, 'sha256':'other'}
        return {'id':1, 'sha256':'mapped'}
    @contextmanager
    def transaction(self, write=False):
        with self.db: yield
    def debug_scene_info(self, scene, *, version=None):
        if scene != 'rev1' or version != 1: raise ValueError('unknown scene')
        return {'id':'rev1', 'definition':{'objects':[{'id':'object1'}]}}


class Scene:
    def __init__(self, session, revision): self.session, self.revision = session, revision
    def check(self, target):
        self.session.checks += 1
        return {'status':self.session.status, 'complete':self.session.complete, 'check':self.session.checks, 'object_id':target}
    def act(self, target, **options):
        self.session.inputs.append(target)
        return {'status':'observed'}


class Session(ProgressiveSceneSessionMixin):
    def __init__(self, project):
        self.project, self.version = project, {'id':1}
        self.status, self.complete, self.checks, self.inputs = 'matched', True, 0, []
    def scene(self, revision): return Scene(self, revision)


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path/'resources'; root.mkdir()
    (root/'GAME.EXE').write_bytes(b'executable')
    (root/'logic').mkdir(); (root/'logic'/'room').write_bytes(b'room one')
    project = Project(tmp_path/'project.db')
    action = dict(name='open', kind='scene', scene_revision='rev1', object_id='object1',
                  dependencies=[dict(name='room logic', status='resolved', evidence=['capture'])], evidence=['capture'])
    doc = dict(format='fdisbull-progressive-workflow-1', source=identity(project,1),
               inventory=resource_inventory(root,engine='AGI',profile='edition',adapter='v1'),
               research=[dict(context='room',question='other exit',status='unknown',evidence=[])], actions=[action])
    return project, root, doc


def test_w1_inventory_binds_full_tree_and_rejects_drift(fixture):
    p, root, doc = fixture
    saved = p.debug_save_workflow('game',doc,resource_root=root)
    session = Session(p); handle = session.workflow(saved['id'],resource_root=root)
    (root/'logic'/'room').write_bytes(b'room changed')
    with pytest.raises(ValueError, match='drift'): handle.act('open')
    assert session.inputs == []


def test_runtime_layer_changes_require_separate_qualification(fixture):
    p,root,doc=fixture
    saved=p.debug_save_workflow('game',doc,resource_root=root)
    session=Session(p);active=[];session.layers=lambda:{'active':list(active)}
    handle=session.workflow(saved['id'],resource_root=root)
    handle.act('open');assert len(session.inputs)==1
    active.append('unqualified execution overlay')
    with pytest.raises(ValueError,match='outside this original-byte workflow'):
        handle.act('open')
    assert len(session.inputs)==1
    active.clear();handle.act('open');assert len(session.inputs)==2


def test_w2_restart_and_immutable_parent_chain(fixture, tmp_path):
    p, root, doc = fixture
    one = p.debug_save_workflow('game',doc,resource_root=root)
    doc['research'][0]['status'] = 'resolved'
    two = p.debug_save_workflow('game',doc,resource_root=root,parent=one['id'])
    with pytest.raises(ValueError, match='parent'): p.debug_save_workflow('game',doc,resource_root=root,parent=one['id'])
    p.db.close(); p = Project(tmp_path/'project.db')
    assert p.debug_workflow_info(one['id'])['definition']['research'][0]['status'] == 'unknown'
    assert p.debug_workflow_info('game')['id'] == two['id']


def test_w3_unknown_dependency_blocks_only_affected_action(fixture):
    p, root, doc = fixture
    blocked = deepcopy(doc['actions'][0]); blocked['name'] = 'other'; blocked['dependencies'][0]['status'] = 'unknown'
    doc['actions'].append(blocked)
    h = Session(p).workflow(p.debug_save_workflow('game',doc,resource_root=root)['id'],resource_root=root)
    assert h.observe('other')['unresolved_dependencies'][0]['name'] == 'room logic'
    with pytest.raises(ValueError, match='Unresolved'): h.act('other')
    assert h.act('open')['result']['status'] == 'observed'


def test_w4_fresh_scene_checks_and_blocked_input(fixture):
    p, root, doc = fixture
    s = Session(p); h = s.workflow(p.debug_save_workflow('game',doc,resource_root=root)['id'],resource_root=root)
    assert h.observe('open')['observation']['check'] == 1
    s.status = 'blocked'
    with pytest.raises(ValueError, match='Fresh scene'): h.act('open')
    assert s.checks == 2 and not s.inputs


def test_w5_pinned_revision_and_adopt_between_actions(fixture):
    p, root, doc = fixture
    one = p.debug_save_workflow('game',doc,resource_root=root)
    s = Session(p); h = s.workflow(one['id'],resource_root=root)
    doc['research'][0]['question'] = 'changed'
    two = p.debug_save_workflow('game',doc,resource_root=root,parent=one['id'])
    def callback(contract, scene, observation):
        with pytest.raises(ValueError, match='during an action'): h.adopt(two['id'])
        return 'done'
    assert h.execute('open',callback)['workflow_revision'] == one['id']
    assert h.adopt(two['id'])['id'] == two['id']
    assert h.act('open')['workflow_revision'] == two['id']


def test_w6_inventory_addition_and_symlink_rejected(fixture):
    p, root, doc = fixture
    (root/'new').write_bytes(b'new')
    with pytest.raises(ValueError, match='differs'): p.debug_save_workflow('game',doc,resource_root=root)
    (root/'link').symlink_to(root/'new')
    with pytest.raises(ValueError, match='symlink'): resource_inventory(root,engine='AGI',profile='x',adapter='v1')


def test_w7_source_scene_and_object_are_qualified(fixture):
    p, root, doc = fixture
    doc['actions'][0]['object_id'] = 'not-real'
    with pytest.raises(ValueError, match='object identity'): p.debug_save_workflow('game',doc,resource_root=root)
    doc['actions'][0]['object_id'] = 'object1'; doc['source']['mapped_sha256'] = 'different'
    with pytest.raises(ValueError, match='source identity'): p.debug_save_workflow('game',doc,resource_root=root)


def test_w8_external_kind_requires_explicit_callback(fixture):
    p, root, doc = fixture
    doc['actions'][0].update(kind='assisted-travel', object_id=None)
    s = Session(p); h = s.workflow(p.debug_save_workflow('game',doc,resource_root=root)['id'],resource_root=root)
    with pytest.raises(ValueError, match='requires execute'): h.act('open')
    receipt = h.execute('open',lambda contract, scene, observation: {'travel':'verified'})
    assert receipt['result'] == {'travel':'verified'} and not s.inputs


def test_failed_callback_has_durable_receipt_and_no_rollback_claim(fixture):
    p, root, doc = fixture
    saved = p.debug_save_workflow('game', doc, resource_root=root)
    s = Session(p); h = s.workflow(saved['id'], resource_root=root)
    def fail_after_input(contract, scene, observation):
        s.inputs.append('already sent')
        raise RuntimeError('outcome unavailable')
    with pytest.raises(RuntimeError, match='outcome unavailable'): h.execute('open', fail_after_input)
    receipts = p.debug_workflow_receipts(saved['id'])
    assert [r['status'] for r in receipts] == ['started', 'failed']
    assert receipts[1]['attempt'] == receipts[0]['attempt']
    assert receipts[1]['observation']['complete'] is True
    assert receipts[1]['error']['message'] == 'outcome unavailable'
    assert s.inputs == ['already sent']


def test_matched_but_incomplete_never_dispatches(fixture):
    p, root, doc = fixture
    s = Session(p); s.complete = False
    h = s.workflow(p.debug_save_workflow('game',doc,resource_root=root)['id'],resource_root=root)
    with pytest.raises(ValueError,match='match completely'): h.act('open')
    assert s.inputs == []
    assert p.debug_workflow_receipts('game')[-1]['status'] == 'failed'


def test_two_handles_serialize_action_and_adoption(fixture):
    p, root, doc = fixture
    one = p.debug_save_workflow('game',doc,resource_root=root)
    doc['research'][0]['question'] = 'new question'
    two = p.debug_save_workflow('game',doc,resource_root=root,parent=one['id'])
    s = Session(p); h1 = s.workflow(one['id'],resource_root=root); h2 = s.workflow(one['id'],resource_root=root)
    entered = threading.Event(); release = threading.Event(); adopted = threading.Event(); failures = []
    def callback(contract, scene, observation):
        entered.set()
        if not release.wait(3): raise RuntimeError('test timed out')
        return 'done'
    def run():
        try: h1.execute('open',callback)
        except Exception as e: failures.append(e)
    def adopt():
        try: h2.adopt(two['id']); adopted.set()
        except Exception as e: failures.append(e)
    first = threading.Thread(target=run); first.start(); assert entered.wait(3)
    second = threading.Thread(target=adopt); second.start()
    assert not adopted.wait(0.1)
    release.set(); first.join(3); second.join(3)
    assert not first.is_alive() and not second.is_alive() and not failures and adopted.is_set()
    s.status = 'blocked'
    with pytest.raises(ValueError,match='Fresh scene'): h2.act('open')
    assert p.debug_workflow_receipts('game')[-1]['workflow_revision'] == two['id']


def test_inventory_validation_rejects_bad_manifest_and_empty_dependency(fixture):
    p, root, doc = fixture
    for path in ('../escape', 'logic//room', '/absolute'):
        bad = deepcopy(doc); bad['inventory']['files'][0]['path'] = path
        with pytest.raises(ValueError,match='canonical'): p.debug_save_workflow('game',bad,resource_root=root)
    bad = deepcopy(doc); bad['inventory']['files'].append(deepcopy(bad['inventory']['files'][0]))
    with pytest.raises(ValueError,match='Duplicate'): p.debug_save_workflow('game',bad,resource_root=root)
    bad = deepcopy(doc); bad['inventory']['files'][0]['sha256'] = 'a' * 63
    with pytest.raises(ValueError,match='SHA-256'): p.debug_save_workflow('game',bad,resource_root=root)
    bad = deepcopy(doc); bad['actions'][0]['dependencies'][0].update(status='unknown',evidence=[])
    with pytest.raises(ValueError,match='Dependency requires evidence'): p.debug_save_workflow('game',bad,resource_root=root)


def test_real_project_restart_and_resource_drift(tmp_path):
    from fdisbull.project import Project as ActualProject
    from test_dos_loader import mz_file
    Base = ActualProject if issubclass(ActualProject, ProgressiveSceneProjectMixin) else type('Base', (ProgressiveSceneProjectMixin, ActualProject), {})
    class RealProject(Base):
        def debug_scene_info(self, scene, *, version=None):
            if scene != 'scene-id' or version != 1: raise ValueError('Unknown scene')
            return {'id':'scene-id', 'definition':{'objects':[{'id':'button-id'}]}}
    root = tmp_path/'game'; root.mkdir()
    binary = root/'GAME.EXE'; binary.write_bytes(mz_file(bytes.fromhex('ebfe') + bytes(1024),ss=0,sp=0x400))
    resource = root/'LOGIC.0'; resource.write_bytes(b'original')
    path = tmp_path/'game.fdb'
    with RealProject.create(path,binary) as p:
        doc = dict(format='fdisbull-progressive-workflow-1', source=identity(p,1),
                   inventory=resource_inventory(root,engine='AGI',profile='edition',adapter='v1'), research=[],
                   actions=[dict(name='open',kind='scene',scene_revision='scene-id',object_id='button-id',
                                 dependencies=[],evidence=['screenshot'])])
        saved = p.debug_save_workflow('game',doc,resource_root=root)
        s = Session(p); h = s.workflow(saved['id'],resource_root=root)
        with pytest.raises(RuntimeError,match='after input'):
            h.execute('open',lambda *args: (_ for _ in ()).throw(RuntimeError('after input')))
    with RealProject(path) as p:
        assert p.debug_workflow_info('game')['id'] == saved['id']
        assert p.debug_workflow_receipts('game')[-1]['error']['message'] == 'after input'
        resource.write_bytes(b'changed')
        s = Session(p); h = s.workflow(saved['id'],resource_root=root)
        with pytest.raises(ValueError,match='drift'): h.act('open')
        assert not s.inputs and p.debug_workflow_receipts('game')[-1]['status'] == 'failed'


def test_callback_returning_incomplete_does_not_claim_action_success(fixture):
    p, root, doc = fixture
    saved = p.debug_save_workflow('game',doc,resource_root=root)
    handle = Session(p).workflow(saved['id'],resource_root=root)
    observed = {'ok':False, 'complete':False, 'status':'stopped'}
    result = handle.execute('open',lambda contract, scene, before: observed)
    receipt = p.debug_workflow_receipts('game')[-1]
    assert result['result'] == observed
    assert receipt['status'] == 'returned' and receipt['result'] == observed
