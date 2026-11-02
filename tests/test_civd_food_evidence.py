"""Check that the shipped experiment records bind the actual shared definitions."""
import hashlib
import json
from pathlib import Path

from fdisbull.project import Project
from fdisbull.stock_flow import maintenance_contract, maintenance_module
from fdisbull.strategy_z import screen_catalog
from fdisbull.udc_layers import digest, register_contract
from fdisbull.udc_blueprint import validate_module_uil


ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidence/civd-food-swaps'


def test_shared_contract_is_the_persisted_and_executed_definition(tmp_path):
    document=json.loads((EVIDENCE/'shared-uil.json').read_text())
    contract=document['contract']
    assert {k:v for k,v in contract.items() if k!='author'}==maintenance_contract()
    source=tmp_path/'authored.bin';source.write_bytes(b'\x90'*32)
    with Project.create(tmp_path/'evidence.fdb',source,arch='x86',bits=16,base=0x1000) as p:
        registered=register_contract(p,contract)
        assert registered['id']==document['contract_id']
        assert maintenance_module(registered['id'])==document['module_uil']
        assert digest(document['module_uil'])==document['module_uil_sha256']
        validate_module_uil(p,document['module_uil'])


def test_sanitized_matrix_is_complete_and_keeps_qualification_boundaries():
    raw=(EVIDENCE/'verification.json').read_text();r=json.loads(raw)
    assert not any(x in raw for x in ('/Users/','/Volumes/','code_hex','bytes_hex'))
    editions={'474.01','474.03','474.05'}
    assert {(m['host'],m['backing']) for m in r['matrix']}=={(a,b) for a in editions for b in editions}
    assert all(m['invocations']==2018 and m['mismatches']==0 and m['original_bytes_unchanged'] for m in r['matrix'])
    assert r['total_selected_invocations']==18162 and r['total_original_dosbox_invocations']==6054
    assert len(r['negative_controls'])==6 and all(x['rejected'] for x in r['negative_controls'])
    assert r['originals_unchanged'] and not r['whole_game_replacement']
    assert r['native_ui_screens_visited']==0 and not r['oracle']['whole_game']
    assert all(x['version']==1 for x in r['restart'])
    assert len(r['snippet_links'])==6
    assert all(x['document']['adapters']['source_layout']!=x['document']['adapters']['target_layout']
               or x['document']['sources']!=x['document']['targets'] for x in r['snippet_links'])


def test_source_inventory_matches_packaged_screen_families():
    r=json.loads((EVIDENCE/'source-ui-inventory.json').read_text())
    path=ROOT/'src/fdisbull/data/civd-z-screen-families.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==r['screen_catalog_sha256']
    catalog=screen_catalog();ids={x['id'] for x in catalog['families']}
    assert len(ids)==r['families']==38 and r['native_screens_visited']==0
    for e in r['editions']:
        assert len(e['files'])==44 and len(e['anchors'])==98
        assert not e['missing_anchors'] and e['unparsed_sites']==e['unclassified_sites']==0
        assert {a['scene'] for a in e['anchors']}==ids
    assert [e['ui_site_count'] for e in r['editions']]==[360,361,361]
