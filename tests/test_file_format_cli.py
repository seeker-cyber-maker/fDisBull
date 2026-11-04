"""Public discovery, persistent metadata and media-budget CLI integration."""
import json
import sqlite3

from fdisbull.cli import main, respond


def test_format_discovery_and_file_identification_need_no_project(tmp_path, capsys):
    catalog = tmp_path / 'formats.sqlite'
    assert main(['--max-output-bytes', '1048576', 'format-modules', '--catalog', str(catalog)]) == 0
    discovered = json.loads(capsys.readouterr().out)
    assert discovered['ok']
    result = discovered['result']
    assert result['format'] == 'fdisbull-format-modules-1'
    assert not result['contains_file_payloads'] and not result['dynamic_plugins_loaded']
    assert {'smacker', 'dos-mz', 'roq', 'vdx'} <= {r['format_id'] for r in result['formats']}
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT count(*) FROM format_definitions').fetchone()[0] == len(result['formats'])
    source = tmp_path / 'misleading.exe'
    source.write_bytes(b'PRIVATE_SOURCE_SENTINEL_without_any_supported_header')
    assert main(['file-identify', str(source), '--catalog', str(catalog), '--max-binary-bytes', '64']) == 0
    found = json.loads(capsys.readouterr().out)
    assert found['ok']
    assert found['result']['identification']['status'] == 'unknown'
    assert not found['result']['input_executed']
    assert b'PRIVATE_SOURCE_SENTINEL' not in catalog.read_bytes()
    response = respond({'method': 'format-modules'}, default_project='/nonexistent.fdb')
    assert response['ok']
    methods = respond({'method': 'help'})['result']['methods']
    assert {'format-modules', 'file-identify', 'smk-frame', 'intake-inventory'} <= set(methods)


def test_media_inspector_rejects_malformed_smk_without_creating_project(tmp_path, capsys):
    source = tmp_path / 'movie'
    source.write_bytes(b'SMK2')
    assert main(['media-inspect', str(source), '--adapter', 'smacker']) == 1
    reply = json.loads(capsys.readouterr().out)
    assert not reply['ok']
    assert 'SMK2' in reply['error']['message']


def test_movie_budget_is_distinct_from_global_json_budget(monkeypatch, capsys):
    import fdisbull.smacker as smacker
    observed = {}

    def bounded_frame(path, output, **options):
        observed.update(path=path, output=output, **options)
        return {'qualification': 'routing-only', 'input_executed': False}

    monkeypatch.setattr(smacker, 'frame_smk', bounded_frame)
    assert main(['smk-frame', 'source', 'new-output', '--max-movie-bytes', '12345', '--keep-frames', '8']) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    assert observed['max_output_bytes'] == 12345
    assert observed['keep_frames'] == 8
    assert observed['path'] == 'source' and observed['output'] == 'new-output'


def test_single_and_batch_intake_cli_use_the_same_projectless_kernel(tmp_path,capsys):
    game=tmp_path/'game';game.mkdir();(game/'song.mid').write_bytes(b'MThd'+bytes([0,0,0,6,0,0,0,1,0,96]))
    catalog=tmp_path/'formats.sqlite'
    assert main(['intake-inventory',str(game),'--catalog',str(catalog)])==0
    one=json.loads(capsys.readouterr().out)['result']
    other=tmp_path/'other';other.mkdir();(other/'opaque.xyz').write_bytes(b'unknown')
    assert main(['intake-inventory',str(game),str(other),'--catalog',str(catalog)])==0
    batch=json.loads(capsys.readouterr().out)['result']
    assert one['format']==batch['format']=='fdisbull-intake-inventory-1'
    assert one['files'][0]['source']==batch['files'][0]['source']
    assert one['files'][0]['identification']==batch['files'][0]['identification']
    assert batch['complete'] and batch['summary']['files_reported']==2
    assert any(r['reason']=='unknown-format' for r in batch['recovery_queue'])
    assert not batch['executables_modified'] and not batch['full_media_decode']
