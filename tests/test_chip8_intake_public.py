"""Public G0 exact-identity intake without network, execution or target fixtures."""
import hashlib
import json
from pathlib import Path
import pytest
from fdisbull.chip8 import PROFILE
from fdisbull.cli import main,respond
from fdisbull.project import Project


@pytest.fixture
def authored(tmp_path,monkeypatch):
    store=tmp_path/'objects';monkeypatch.setenv('FDISBULL_TARGET_STORE',str(store))
    raw=bytes.fromhex('6001 1200')+b'\x7f'
    source=tmp_path/'source.ch8';source.write_bytes(raw)
    entry={'key':'sample','title':'Authored sample','author':'Fixture author','platform':'chip8',
           'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
           'git_blob_sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
    manifest={'source_repo':'https://example.invalid/authored','source_commit':'1'*40,
              'source_license':'authored fixture declaration','source_metadata_blob_sha':'2'*40,'programs':[entry]}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest,sort_keys=True))
    return {'source':source,'bytes':raw,'entry':entry,'manifest':manifest,'path':path,
            'pin':hashlib.sha256(path.read_bytes()).hexdigest(),'store':store}


def _params(fixture,project,source=None):
    return {'project':str(project),'path':str(source or fixture['source']),
            'manifest_path':str(fixture['path']),'manifest_sha256':fixture['pin'],'member':'sample'}


def _intake(fixture,project,source=None):
    reply=respond({'method':'chip8-intake','params':_params(fixture,project,source)})
    assert reply['ok'],reply
    return reply['result']


def test_json_and_cli_exact_intake_cold_reopen_and_alias_identity(authored,tmp_path,capsys):
    alias=tmp_path/'another-name.ch8';alias.write_bytes(authored['bytes'])
    one=_intake(authored,tmp_path/'one.fdb');two=_intake(authored,tmp_path/'two.fdb',alias)
    assert one['format']==two['format']=='fdisbull-chip8-conversion-intake-1'
    assert one['gate']==two['gate']=='G0' and one['status']==two['status']=='exact-identity-verified'
    assert one['intake_sha256']==two['intake_sha256']
    result=respond({'method':'chip8-intake-info','params':{'project':str(tmp_path/'one.fdb'),
        'expected_manifest_sha256':authored['pin'],'expected_intake_sha256':one['intake_sha256']}})
    assert result['ok'] and result['result']['intake_sha256']==one['intake_sha256'],result
    with Project(tmp_path/'one.fdb') as project:
        assert project.chip8_intake_info(expected_manifest_sha256=authored['pin'],
            expected_intake_sha256=one['intake_sha256'])['intake_sha256']==one['intake_sha256']
        assert project.source_info()['verified'] and project.regions(1)[0].data==authored['bytes']
    assert main(['chip8-intake',str(authored['source']),str(tmp_path/'cli.fdb'),'--manifest-path',str(authored['path']),
                 '--manifest-sha256',authored['pin'],'--member','sample','--profile',PROFILE])==0
    cli=json.loads(capsys.readouterr().out)
    assert cli['ok'] and cli['result']['intake_sha256']==one['intake_sha256']
    assert main(['chip8-intake-info',str(tmp_path/'cli.fdb'),'--expected-manifest-sha256',authored['pin'],
                 '--expected-intake-sha256',one['intake_sha256']])==0
    info=json.loads(capsys.readouterr().out);assert info['ok'] and info['result']['intake_sha256']==one['intake_sha256']
    assert authored['source'].read_bytes()==alias.read_bytes()==authored['bytes']


@pytest.mark.parametrize('bad',['bytes','pin','member','profile','duplicate','platform'])
def test_bad_identity_never_publishes_project_or_store(authored,tmp_path,bad):
    params=_params(authored,tmp_path/'refused.fdb')
    if bad=='bytes':authored['source'].write_bytes(b'\x60\x02\x12\x00\x7f')
    elif bad=='pin':params['manifest_sha256']='0'*64
    elif bad=='member':params['member']='not-listed'
    elif bad=='profile':params['profile']='xo-chip'
    else:
        doc=authored['manifest']
        if bad=='duplicate':doc['programs'].append(dict(doc['programs'][0]))
        else:doc['programs'][0]['platform']='schip'
        authored['path'].write_text(json.dumps(doc,sort_keys=True))
        params['manifest_sha256']=hashlib.sha256(authored['path'].read_bytes()).hexdigest()
    reply=respond({'method':'chip8-intake','params':params})
    assert not reply['ok'],reply
    assert not (tmp_path/'refused.fdb').exists()
    assert not authored['store'].exists() or not list(authored['store'].iterdir())


@pytest.mark.parametrize('omitted',['path','project','manifest_path','manifest_sha256','member'])
def test_json_missing_required_argument_fails_without_output(authored,tmp_path,omitted):
    params=_params(authored,tmp_path/'missing.fdb');params.pop(omitted)
    reply=respond({'method':'chip8-intake','params':params})
    assert not reply['ok'] and not (tmp_path/'missing.fdb').exists()


def test_offline_info_rejects_wrong_expected_pins_without_changing_project(authored,tmp_path):
    database=tmp_path/'check.fdb';saved=_intake(authored,database)
    with Project(database) as project:
        before=project.source_info(),project.regions(1)[0].data
        for kw in ({'expected_manifest_sha256':'0'*64},{'expected_intake_sha256':'f'*64}):
            with pytest.raises(ValueError):project.chip8_intake_info(**kw)
        assert (project.source_info(),project.regions(1)[0].data)==before
    assert authored['source'].read_bytes()==authored['bytes'] and saved['status']=='exact-identity-verified'


def test_cli_omitted_profile_uses_default(authored,tmp_path,capsys):
    database=tmp_path/'default.fdb'
    assert main(['chip8-intake',str(authored['source']),str(database),'--manifest-path',str(authored['path']),
                 '--manifest-sha256',authored['pin'],'--member','sample'])==0
    reply=json.loads(capsys.readouterr().out)
    assert reply['ok'] and reply['result']['profile']['id']==PROFILE
    with Project(database) as project:
        assert project.chip8_intake_info()['status']=='exact-identity-verified'


def test_json_unexpected_loader_override_refuses_before_publication(authored,tmp_path):
    database=tmp_path/'override.fdb';params=_params(authored,database);params['base']=0
    reply=respond({'method':'chip8-intake','params':params})
    assert not reply['ok'] and not database.exists()
    assert not authored['store'].exists() or not list(authored['store'].iterdir())
    assert authored['source'].read_bytes()==authored['bytes']
