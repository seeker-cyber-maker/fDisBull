import base64
import json
import os
from pathlib import Path
import subprocess
import sys

from fdisbull.cli import main, respond
from fdisbull.output_limits import OutputPolicy, output_policy_context
from test_output_limits import program


def test_cli_spills_then_fresh_process_selects_without_execution(tmp_path):
    source=tmp_path/'program.json';source.write_text(json.dumps(program()))
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1')
    prefix=[sys.executable,'-m','fdisbull','--output-artifact-dir',str(tmp_path/'outputs'),'--max-output-bytes','4096']
    run=subprocess.run([*prefix,'il-run',str(source)],text=True,capture_output=True,env=env,cwd=tmp_path,timeout=10)
    assert run.returncode==0 and len(run.stdout.encode())<=4096
    result=json.loads(run.stdout);assert result['execution']['complete'] is True and not result['complete']
    artifact=result['artifact']['id']
    selected=subprocess.run([*prefix,'output-select',artifact,'/state'],text=True,capture_output=True,env=env,cwd=tmp_path,timeout=10)
    assert selected.returncode==0 and json.loads(selected.stdout)['result']['value']=={'$money':200}
    partial=subprocess.run([*prefix,'output-select',artifact,'/events'],text=True,capture_output=True,env=env,cwd=tmp_path,timeout=10)
    body=json.loads(partial.stdout)['result'];assert body['complete'] is False and 'value' not in body
    chunk=subprocess.run([*prefix,'output-read',artifact,'--length','32'],text=True,capture_output=True,env=env,cwd=tmp_path,timeout=10)
    part=json.loads(chunk.stdout)['result']
    assert base64.b64decode(part['data_base64']).startswith(b'{"complete":true')
    assert part['range_complete'] and not part['whole_complete']


def test_unavailable_storage_has_distinct_exit_without_rewriting_execution(tmp_path,capsys):
    source=tmp_path/'program.json';source.write_text(json.dumps(program()))
    repo=tmp_path/'repo';repo.mkdir();(repo/'.git').mkdir()
    assert main(['--output-artifact-dir',str(repo/'outputs'),'--max-output-bytes','4096','il-run',str(source)])==2
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='output_unavailable' and result['execution']['complete'] is True
    assert result['retry_safe'] is False


def test_bounded_selection_and_projectless_retrieval(tmp_path):
    policy=OutputPolicy(4096,artifact_dir=tmp_path/'outputs')
    ident=policy.store().put_stream([json.dumps({'text':'\u263a'*4000}).encode()])['id']
    with output_policy_context(policy):
        result=respond({'method':'output-select','params':{'artifact':ident,'pointer':'/text'}},default_project='/nonexistent')
        assert result['ok'] and result['result']['complete'] is False
        assert 'value' not in result['result'] and 'format' not in result['result']
        too_big=respond({'method':'output-read','params':{'artifact':ident,'length':8192}})
        assert not too_big['ok']


def test_blank_backend_command_is_clean_usage_error(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root/'player'))
    for value in ('','   '):
        p=subprocess.run([sys.executable,'-m','fdisbull_player','--backend-command',value],env=env,cwd=tmp_path,text=True,capture_output=True,timeout=5)
        assert p.returncode==2 and 'must not be blank' in p.stderr and 'Traceback' not in p.stderr


def test_server_bounds_each_line_and_continues_with_a_selective_query(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root/'src'),FDISBULL_OUTPUT_ARTIFACT_DIR=str(tmp_path/'outputs'))
    requests=[{'id':'large','method':'agent-skill'},
              {'id':'small','method':'agent-skill','params':{'index':True}}]
    p=subprocess.run([sys.executable,'-m','fdisbull','--max-output-bytes','4096','serve'],
                     input=''.join(json.dumps(x)+'\n' for x in requests),text=True,
                     capture_output=True,env=env,cwd=tmp_path,timeout=10)
    lines=p.stdout.splitlines(keepends=True)
    assert p.returncode==0 and len(lines)==2 and all(len(x.encode())<=4096 for x in lines)
    large,small=map(json.loads,lines)
    assert large['id']=='large' and large['result']['status']=='artifact_required'
    assert small['id']=='small' and small['result']['format']=='fdisbull-skill-index-1'


def test_invalid_configuration_refuses_before_a_mutation(tmp_path,monkeypatch,capsys):
    from fdisbull.project import Project
    binary=tmp_path/'GAME.COM';binary.write_bytes(bytes.fromhex('b8004ccd21'))
    project=tmp_path/'private.fdb'
    with Project.create(project,binary,image='com'):pass
    request={'method':'patch','params':{'project':str(project),'address':'1000:0100','data':'90'}}
    monkeypatch.setenv('FDISBULL_MAX_OUTPUT_BYTES','invalid')
    assert main(['request',json.dumps(request)])==1
    assert json.loads(capsys.readouterr().out)['status']=='refused'
    with Project(project) as p:assert p.db.execute('SELECT COUNT(*) FROM versions').fetchone()[0]==1


def test_json_emitter_uses_lf_with_a_translating_text_stream(monkeypatch):
    import io
    from fdisbull.cli import emit
    raw=io.BytesIO();stream=io.TextIOWrapper(raw,encoding='ascii',newline='\r\n')
    monkeypatch.setattr(sys,'stdout',stream)
    value={'text':'X'*(4096-len('{"text":""}')-1)}
    with output_policy_context(OutputPolicy(4096)):emit(value)
    assert len(raw.getvalue())==4096 and raw.getvalue().endswith(b'\n')
    assert not raw.getvalue().endswith(b'\r\n')
