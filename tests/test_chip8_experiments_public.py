"""Public CHIP-8 comparative trial dispatch."""
from types import SimpleNamespace
import pytest
from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace


def _route():return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[{'op':'registers'}]}


def test_chip8_experiment_json_forwards_complete_arguments(tmp_path):
    calls=[];workspace=DebugWorkspace()
    def method(name):
        def invoke(**kw):calls.append((name,kw));return {'method':name}
        return invoke
    owner=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),**{n:method(n) for n in
        ('controls','save_experiment','restore_experiment','compare_experiment')})
    workspace.sessions['chip8']=owner
    cases=[('debug-controls',{}),('debug-save-experiment',{'name':'x.json','script':_route(),'observations':[{'address':0x300,'length':1}],'timeout_ms':400}),
           ('debug-restore-experiment',{'experiment':'e','timeout_ms':400}),('debug-compare-experiment',{'experiment':'e','layers':['l'],'timeout_ms':400})]
    try:
        for method_name,params in cases:
            reply=respond({'method':method_name,'params':{'project':str(tmp_path),'run':'chip8',**params}},debugger=workspace)
            assert reply['ok'],reply
        assert [x[0] for x in calls]==['controls','save_experiment','restore_experiment','compare_experiment']
        assert calls[1][1]==cases[1][1] and calls[3][1]==cases[3][1]
    finally:workspace.sessions.clear()


from test_chip8_experiments import Subject, project


def test_trial_preflight_refuses_unsupported_trace_before_any_step(project):
    from fdisbull.chip8_experiments import _script
    session=Subject(project,'trial-public-preflight');writes=[]
    session.step=lambda **kwargs:writes.append(kwargs)
    with pytest.raises(ValueError):
        _script({'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
            {'op':'step'},{'op':'trace','count':1}]},session)
    assert not writes and not session.loads


@pytest.mark.parametrize('blocked',['profile','transaction'])
def test_trial_save_profile_and_transaction_preflight(project,blocked):
    session=Subject(project,'trial-public-'+blocked)
    if blocked=='profile':session.identity['cpu_subset']='fdisbull-chip8-frames-5'
    before=project.db.execute('select count(*) from debug_artifacts').fetchone()[0]
    if blocked=='transaction':
        with project.transaction(True):
            with pytest.raises(ValueError):session.save_experiment('bad.json',script=_route())
    else:
        with pytest.raises(ValueError):session.save_experiment('bad.json',script=_route())
    assert project.db.execute('select count(*) from debug_artifacts').fetchone()[0]==before and not session.loads


@pytest.mark.parametrize('kind',['format','script','sidecar'])
def test_project_experiment_info_export_and_tamper_guards(project,tmp_path,kind):
    import hashlib,json
    session=Subject(project,'trial-public-'+kind)
    saved=session.save_experiment('public.json',script=_route(),observations=[{'address':0x300,'length':1}])
    info=project.debug_experiment_info(saved['artifact'])
    assert info['format']=='fdisbull-chip8-experiment-1' and info['checkpoint']['artifact']==saved['checkpoint']['artifact']
    destination=tmp_path/'trial-export.json';project.debug_export(saved['artifact'],destination)
    assert json.loads(destination.read_text())['format']=='fdisbull-chip8-experiment-1'
    if kind=='sidecar':
        with project.transaction(True):project.db.execute('update debug_artifacts set metadata=? where id=?',('{}',saved['checkpoint']['artifact']))
    else:
        row=project.db.execute('select data from debug_artifacts where id=?',(saved['artifact'],)).fetchone()
        doc=json.loads(bytes(row['data']))
        if kind=='format':doc['format']='fdisbull-chip8-experiment-unknown'
        else:doc['script_sha256']='0'*64
        raw=json.dumps(doc,sort_keys=True,separators=(',',':')).encode()
        with project.transaction(True):project.db.execute('update debug_artifacts set data=?,sha256=? where id=?',(raw,hashlib.sha256(raw).hexdigest(),saved['artifact']))
    with pytest.raises(ValueError):project.debug_experiment_info(saved['artifact'])
