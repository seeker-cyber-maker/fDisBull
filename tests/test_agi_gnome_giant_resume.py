"""Synthetic-only resume admission tests; no original bytes or native guest.

The saved-state blob and backend below are deliberately nonexecutable authored
data. Every debugger boundary is replaced; SQLite admission and backup are real.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from examples.agi import build_gnome_giant_scene as exporter
from examples.agi import resume_gnome_giant as module


def authored_state():
    return {
        'room':36, 'score':14,
        'ego':{'x':88, 'y':131, 'direction':0, 'drawn':True},
        'ego_width':6, 'ego_view':0, 'step_size':1, 'swimming':0,
        'player_control':1, 'in_water':False, 'dead':False,
        'ignore_blocks':False,
        'quest_variables':{'84':0, '66':0, '86':0},
        'quest_flags':{'21':False, '22':False, '84':False, '85':False,
                       '102':True, '104':False, '169':False, '205':False},
        'inventory_locations':{'2':0, '5':0, '8':255, '15':0,
                               '16':0, '21':255, '24':0},
        'chest_carried':False, 'key_carried':False, 'clover_carried':True,
        'diamonds_carried':False, 'bag_carried':False,
        'shield_carried':True, 'mushroom_carried':False,
    }


@pytest.fixture
def case(tmp_path):
    # macOS temporary roots may use a /var -> /private/var alias. Saved native
    # metadata requires the same canonical game directory as the live request.
    root=tmp_path.resolve()
    source=root/'source';game=root/'game';donor=root/'donor'
    for path in (source,game,donor):path.mkdir()
    manifest={}
    for number,name in enumerate(('AGI','OBJECT')+tuple(f'authored-{n:02}' for n in range(22))):
        raw=f'AUTHORED NON-GAME INPUT {number}'.encode()
        manifest[name]=sha256(raw).hexdigest()
        (source/name).write_bytes(raw);(game/name).write_bytes(raw)
    backend=root/'backend'
    backend.write_bytes(b'AUTHORED NONEXECUTABLE BACKEND')
    blob=b'AUTHORED NONNATIVE SAVED STATE'
    checkpoint_sha=sha256(blob).hexdigest()
    metadata={'format':'dosbox-x-native', 'disk_restore':False,
              'code_layers':{'active':[], 'ram_base':{}, 'ram_applied':{}},
              'game_dir':str(game),
              'emulator_sha256':sha256(backend.read_bytes()).hexdigest()}
    project=donor/'authored.fdb'
    with closing(sqlite3.connect(project)) as db:
        db.executescript('''
            CREATE TABLE debug_runs(id TEXT,version INTEGER);
            CREATE TABLE debug_artifacts(
                id TEXT,name TEXT,kind TEXT,sha256 TEXT,metadata TEXT,data BLOB,run TEXT);
        ''')
        db.execute('INSERT INTO debug_runs VALUES (?,?)',('authored-run',1))
        db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                   ('authored-checkpoint','quest-start.sav','state',checkpoint_sha,
                    json.dumps(metadata),blob,'authored-run'))
        db.commit()
    capture=donor/'source-capture.json';result=donor/'source-result.json'
    capture.write_text(json.dumps({
        'runtime':{'policy':'physical','fresh_game':True,'interventions':[]},
        'source':{'agi_sha256':manifest['AGI'],'object_sha256':manifest['OBJECT']},
        'observations':{'quest-start':{'state':authored_state(),'guest_ms':100}},
    }))
    result.write_text(json.dumps({
        'source_manifest':manifest,'backend_sha256':metadata['emulator_sha256'],
        'private_checkpoints':[{'path':'quest-start.sav','sha256':checkpoint_sha,
                                'guest_ms':100,'loaded':False}],
        'normal_leprechaun_complete':True,
        'post_teardown_source_unchanged':True,'post_teardown_copy_unchanged':True,
    }))
    output=root/'output'
    args=['--source',str(source),'--backend',str(backend),'--project',str(project),
          '--artifact','authored-checkpoint','--source-capture',str(capture),
          '--source-result',str(result),'--output',str(output)]
    return SimpleNamespace(root=root,source=source,game=game,backend=backend,
        project=project,capture=capture,result=result,output=output,args=args,
        metadata=metadata,blob=blob,agi_sha256=manifest['AGI'])


def input_bytes(case):
    paths=[*case.source.iterdir(),*case.game.iterdir(),
           case.project,case.capture,case.result,case.backend]
    return {path:path.read_bytes() for path in paths}


def assert_inputs_preserved(before):
    assert all(path.read_bytes()==raw for path,raw in before.items())


def block_native_creation(monkeypatch):
    attempts=[]
    def forbidden(*args,**kwargs):
        attempts.append((args,kwargs))
        raise AssertionError('Authored admission refusal reached native debugger creation')
    monkeypatch.setattr(module,'Project',forbidden)
    return attempts


def test_first_execution_error_survives_later_teardown_and_retains_incomplete_receipt(case,monkeypatch):
    primary=RuntimeError('authored original execution failure')
    teardown=OSError('authored later teardown failure')
    calls=[]

    class AuthoredDebugger:
        def __enter__(self):return self
        def __exit__(self,*args):raise teardown
        def run(self,**kwargs):
            calls.append(('run',kwargs))
            raise primary

    class AuthoredProject:
        def __init__(self,path):
            copied=Path(path)
            assert copied==case.output/'private-copy.fdb'
            with closing(sqlite3.connect(copied.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
                assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                assert db.execute('SELECT data FROM debug_artifacts').fetchone()[0]==case.blob
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def debugger(self,backend,game,**kwargs):
            assert (backend,game)==(case.backend,case.game)
            assert kwargs=={'version':1,'fair_play':True}
            return AuthoredDebugger()

    monkeypatch.setattr(module,'Project',AuthoredProject)
    monkeypatch.setattr(module,'PROFILES',{'kq1':('AGI','AGI',case.agi_sha256,())})
    before=input_bytes(case)
    with pytest.raises(RuntimeError,match='authored original execution failure') as raised:
        module.main(case.args)
    assert raised.value is primary
    assert len(calls)==1  # The stub failed once; no execution replay was requested.
    report=json.loads((case.output/'diagnostic.private.json').read_text())
    assert report['error']=={'type':'RuntimeError','message':str(primary)}
    assert report['complete'] is False and report['restored_quest_complete'] is False
    assert report['fresh_game'] is False and report['checkpoint_loads_attempted']==0
    assert report['persistence_errors']==[{'operation':'native teardown',
        'type':'OSError','message':str(teardown)}]
    assert all(report[key] is True for key in ('source_post_manifest_matches',
        'game_copy_post_manifest_matches','original_db_unchanged','donor_capture_unchanged',
        'donor_result_unchanged','backend_unchanged','frozen_hashes_unchanged'))
    assert not (case.output/'capture.private.json').exists()
    assert not (case.output/'native-origin.private.json').exists()
    assert_inputs_preserved(before)


@pytest.mark.parametrize('fault',['layers','derivation','format','disk_restore'])
def test_unsupported_checkpoint_metadata_is_refused_before_output_or_native_creation(case,monkeypatch,fault):
    metadata=deepcopy(case.metadata)
    if fault=='layers':metadata['code_layers']['active']=['authored-layer']
    elif fault=='derivation':metadata['derivation']={'authored':True}
    elif fault=='format':metadata['format']='unsupported-authored-format'
    else:metadata['disk_restore']=True
    with closing(sqlite3.connect(case.project)) as db:
        db.execute('UPDATE debug_artifacts SET metadata=?',(json.dumps(metadata),))
        db.commit()
    attempts=block_native_creation(monkeypatch);before=input_bytes(case)
    with pytest.raises(RuntimeError,match='unsupported layers, derivation or disk restoration'):
        module.main(case.args)
    assert not attempts and not case.output.exists()
    assert_inputs_preserved(before)


def test_existing_output_is_refused_without_altering_receipts_or_inputs(case,monkeypatch):
    case.output.mkdir()
    receipt=case.output/'diagnostic.private.json'
    original=b'AUTHORED PREEXISTING RECEIPT: PRESERVE EXACTLY\n'
    receipt.write_bytes(original)
    attempts=block_native_creation(monkeypatch);before=input_bytes(case)
    with pytest.raises(RuntimeError,match='Output already exists or is a symlink'):
        module.main(case.args)
    assert not attempts and receipt.read_bytes()==original
    assert list(case.output.iterdir())==[receipt]
    assert_inputs_preserved(before)


def test_authored_checkpoint_projection_matches_exporter_40_field_contract():
    expected={
        'room':36,'score':14,'x':88,'y':131,'direction':0,
        'ego_width':6,'ego_view':0,'step_size':1,'swimming':0,'player_control':1,
        'drawn':True,'in_water':False,'dead':False,'ignore_blocks':False,
        'wrong_stage':0,'door_state':0,'giant_state':0,
        'room_callback':False,'room_name_prompt':False,'key_taken':False,
        'door_scored':False,'shield_active':True,'chest_taken':False,
        'chest_callback':False,'sleep_scored':False,'gnome_key_ready':False,
        'chest_carried':False,'inventory_2':0,'key_carried':False,'inventory_5':0,
        'clover_carried':True,'inventory_8':255,'diamonds_carried':False,'inventory_15':0,
        'bag_carried':False,'inventory_16':0,'shield_carried':True,'inventory_21':255,
        'mushroom_carried':False,'inventory_24':0,
    }
    raw=authored_state()
    assert module.project_quest_start(raw)==expected==exporter.project_state(raw)
    assert len(expected)==40 and set(expected)==set(exporter.FIELDS)
    assert all(type(expected[key]) is int for key in exporter.BYTE_FIELDS)
    assert all(type(expected[key]) is bool for key in exporter.BOOL_FIELDS)
