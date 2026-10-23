import pytest

from fdisbull.cli import respond
from fdisbull.project import Project
from test_managed import managed_fixture


def test_managed_path_api_and_method_token_resolution(tmp_path):
    path=tmp_path/'assembly.dll';path.write_bytes(managed_fixture())
    result=respond({'method':'managed','params':{'path':str(path)}})
    assert result['ok'] and result['result']['managed'],result
    assert result['result']['methods'][0]['full_name']=='ALD.Controller::Main'
    result=respond({'method':'managed','params':{'path':str(path),'token':'0x06000001','max_instructions':2}})
    assert result['ok'] and result['result']['budget_exhausted'],result
    assert result['result']['instructions'][0]['mnemonic']=='ldstr'
    bound=respond({'method':'managed','params':{'path':str(path)}},default_project=str(tmp_path/'absent.fdb'))
    assert bound['ok'] and bound['result']['managed'],bound


def test_project_retains_managed_source_and_refuses_native_il_analysis(tmp_path):
    path=tmp_path/'assembly.exe';path.write_bytes(managed_fixture())
    dbpath=tmp_path/'managed.fdb'
    with Project.create(dbpath,path) as p:
        assert p.information('header')['header']['managed']['il_only']
        with pytest.raises(ValueError,match='managed command'):
            p.analyze()
        assert p.managed('0x06000002')['instructions'][0]['mnemonic']=='ldc.i4.s'
    path.unlink()
    result=respond({'method':'managed','params':{'project':str(dbpath),'token':'0x06000001'}})
    assert result['ok'] and result['result']['complete'],result
    assert any(r.get('name')=='ALD.Controller::Answer' for r in result['result']['token_references'])


def test_public_locate_and_decoder_check(tmp_path):
    path=tmp_path/'bytes.bin';path.write_bytes(bytes.fromhex('b82a000000c3'))
    project=tmp_path/'bytes.fdb'
    with Project.create(project,path,arch='x86',base=0x1000) as p:
        p.analyze()
    result=respond({'method':'locate','params':{'project':str(project),'address':'0x1004'}})
    assert result['ok'] and result['result']['instructions'][0]['position']=='end'
    result=respond({'method':'decoder-check','params':{'data':'0f0dc0','bits':64}})
    assert result['ok'] and result['result']['hardware_observed'] is False
    assert result['result']['candidates'][0]['comparison']['status']=='validity_disagreement'
    bound=respond({'method':'decoder-check','params':{'data':'90','bits':64}},default_project=str(project))
    assert bound['ok'],bound
