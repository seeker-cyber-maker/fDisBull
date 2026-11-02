"""Persistence/restart, patch isolation and public indexed-UIL entry points."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.common_uil import digest
from fdisbull.project import Project
from fdisbull.cli import respond


def package():
    fn={'variables':[{'type':'u16'}],'constants':[{'type':'u16'}],
        'inputs':[0],'outputs':[0],'max_steps':20,
        'body':[{'op':'set','dst':0,'value':{'op':'add','type':'u16','args':[{'var':0},{'const':0}]}}]}
    program={'format':'fdisbull-common-uil-1','capabilities':['core.scalar@1'],
             'imports':[],'functions':[fn],'entry':0}
    presentation={'format':'fdisbull-uil-presentation-1','program_sha256':digest(program),
                  'functions':[{'initial':['0'],'constants':['1']}],'resources':[],
                  'names':{'result':{'function':0,'slot':0}}}
    plan={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(program),
          'bindings':[],'ownership':'copy-in-copy-out','max_call_depth':32}
    return {'format':'fdisbull-common-uil-package-1','program':program,'presentation':presentation,
            'catalog':{'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]},'orchestration':plan}


def project(tmp_path):
    source=tmp_path/'owned.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    return Project.create(tmp_path/'analysis.fdb',source,image='com')


def test_restart_retains_prior_packages_and_source_version_after_patch(tmp_path):
    original=package()
    with project(tmp_path) as p:
        first=p.store_uil_package('counter',original)
        second_doc=deepcopy(original);second_doc['presentation']['functions'][0]['constants'][0]='2'
        second=p.store_uil_package('counter',second_doc,parent=first['id'])
        with pytest.raises(ValueError,match='parent'):
            p.store_uil_package('counter',original,parent=first['id'])
        p.patch(p.regions(1)[0].start,'90',label='unrelated source byte child')
    with Project(tmp_path/'analysis.fdb') as p:
        loaded=p.uil_package_info(first['id'],full=True)
        assert loaded['document']['package']==original and loaded['version']==1
        assert p.uil_package_info(second['id'])['parent']==first['id']
        assert [r['id'] for r in p.uil_packages()]==[first['id'],second['id']]
        assert p.version(2)['sha256']!=p.version(1)['sha256']
        assert (tmp_path/'owned.com').read_bytes()==bytes.fromhex('b8004ccd21')
        assert p.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        p.db.execute('UPDATE common_uil_packages SET document=? WHERE id=?',('{}',first['id']))
        with pytest.raises((ValueError,KeyError)):
            p.uil_package_info(first['id'],full=True)


def test_failed_registration_does_not_commit_outer_transaction(tmp_path):
    with project(tmp_path) as p:
        first=p.store_uil_package('counter',package())
        p.db.execute('BEGIN')
        p.db.execute('INSERT INTO metadata(key,value) VALUES (?,?)',('test-uncommitted','true'))
        with pytest.raises(ValueError,match='parent'):
            p.store_uil_package('counter',package(),parent='uil:'+'0'*64)
        assert p.db.in_transaction
        assert len(p.uil_packages())==1 and p.uil_packages()[0]['id']==first['id']
        p.db.rollback()
        assert p.db.execute('SELECT 1 FROM metadata WHERE key=?',('test-uncommitted',)).fetchone() is None


def test_json_methods_preserve_indices_instead_of_hex_address_formatting():
    pkg=package()
    response=respond({'method':'uil-check','params':{'package':pkg}})
    assert response['ok'] and response['result']['status']=='valid'
    result=respond({'method':'uil-run','params':{k:pkg[k] for k in ('program','presentation','catalog','orchestration')}|{'inputs':[65535]}})
    assert result['ok'] and result['result']['outputs']==[0]
    bad=respond({'method':'uil-run','params':{'program':pkg['program'],'presentation':pkg['presentation'],'inputs':[True]}})
    assert not bad['ok']
    # Presentation debug metadata uses a zero-based slot; generic address
    # formatting must not silently convert it into a hexadecimal string.
    response=respond({'method':'uil-fold','params':{'program':pkg['program'],'function':0,'semantic_id':'semantic:'+'a'*64}})
    assert response['result']['recovery']['function']==0


def test_real_cli_check_run_store_and_readback(tmp_path):
    pkg=package();root=Path(__file__).parents[1]
    files={}
    for key,value in pkg.items():
        if key=='format':continue
        f=tmp_path/(key+'.json');f.write_text(json.dumps(value));files[key]=str(f)
    bundle=tmp_path/'package.json';bundle.write_text(json.dumps(pkg))
    argsfile=tmp_path/'inputs.json';argsfile.write_text('[65535]')
    env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
    def cli(*args):
        r=subprocess.run([sys.executable,'-m','fdisbull',*args],env=env,cwd=tmp_path,
                         capture_output=True,text=True,timeout=20)
        assert r.returncode==0,r.stdout+r.stderr
        return json.loads(r.stdout)
    assert cli('uil-check',str(bundle))['status']=='valid'
    assert cli('uil-run',files['program'],'--presentation',files['presentation'],'--inputs',str(argsfile))['outputs']==[0]
    with project(tmp_path):pass
    stored=cli('uil-store',str(tmp_path/'analysis.fdb'),'counter',str(bundle))
    info=cli('uil-info',str(tmp_path/'analysis.fdb'),stored['id'],'--full')
    assert info['document']['package']['presentation']['names']['result']['slot']==0
    assert cli('uil-list',str(tmp_path/'analysis.fdb'))[0]['id']==stored['id']
