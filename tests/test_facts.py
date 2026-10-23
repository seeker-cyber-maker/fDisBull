"""Derived indexes survive migration/restart and remain isolated across versions."""
import json
import sqlite3

from fdisbull.cli import respond
from fdisbull.project import Project


def _raw(tmp_path, code=bytes.fromhex('9090c3')):
    path=tmp_path/'code.bin'
    path.write_bytes(code)
    return Project.create(tmp_path/'code.fdb',path,arch='x86',bits=32,base=0x1000)


def test_all_straight_lines_persist_and_old_projects_explicitly_backfill(tmp_path):
    with _raw(tmp_path) as p:
        p.analyze()
        assert [(r['source'],r['target']) for r in p.xrefs('0x1000',direction='from')] == [('0x1000','0x1001')]
        original=p.versions()
        p.annotate('0x1000','entry_observed',kind='name')
        # Simulate pre-0.5 indexes on the exact existing bytes and annotations.
        with p.transaction(True):
            p.db.execute("DELETE FROM xrefs WHERE kind='fallthrough'")
            p.db.execute('DROP TABLE memory_refs')
            p.db.execute('DROP TABLE analysis_facts_revision')
            p.db.execute("UPDATE metadata SET value='3' WHERE key='schema'")
        path=p.path
    with Project(path) as p:
        assert p.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0]=='4'
        # Read-only CFG can expose old omissions before explicit refresh.
        before=p.db.total_changes
        assert len(p.cfg('0x1000')['nodes'])==3
        assert p.db.total_changes==before
        result=p.refresh_facts()
        assert result['instructions_indexed']==3
        assert result['fallthrough_sources_added']==2
        assert p.refresh_facts()['fallthrough_sources_added']==0
        assert p.versions()==original
        assert p.disassembly()['instructions'][0]['name']=='entry_observed'
        assert all(edge['provenance']=='stored' for edge in p.cfg('0x1000')['edges'])


def test_memory_index_retracts_on_representation_and_preserves_parent(tmp_path):
    # mov dword [0x1020],eax; ret; trailing memory
    with _raw(tmp_path,bytes.fromhex('a320100000c3')+bytes(32)) as p:
        p.analyze()
        facts=p.db.execute('SELECT source,detail FROM memory_refs WHERE version=1').fetchall()
        assert any(json.loads(r['detail']).get('may_write') for r in facts)
        before=p.db.total_changes
        p.memory_accesses('0x1021',access='write')
        assert p.db.total_changes==before
        p.patch('0x1000','90')
        assert p.db.execute('SELECT count(*) FROM memory_refs WHERE version=2').fetchone()[0]==0
        assert p.db.execute('SELECT count(*) FROM memory_refs WHERE version=1').fetchone()[0]==len(facts)
        p.represent('0x1000','byte',version=1,defer=True)
        assert p.db.execute('SELECT count(*) FROM memory_refs WHERE version=1').fetchone()[0]==0
        assert p.db.execute('SELECT count(*) FROM analysis_facts_revision WHERE version=1').fetchone()[0]==1


def test_public_new_commands_and_render_sidecar_protection(tmp_path):
    with _raw(tmp_path) as p:
        p.analyze()
        path=str(p.path)
    for method,params in [('cfg',{'address':'0x1000','highlights':['0x1001']}),
                          ('memory-accesses',{'address':'0x1020','access':'write'}),
                          ('refresh-facts',{})]:
        result=respond({'method':method,'params':{'project':path,**params}})
        assert result['ok'],result
    response=respond({'method':'render-cfg','params':{'project':path,'address':'0x1000','output':path+'-wal'}})
    assert not response['ok'] and 'overwrite' in response['error']['message']
