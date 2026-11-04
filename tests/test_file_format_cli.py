"""Public discovery, persistent metadata and media-budget CLI integration."""
import json
import sqlite3

from fdisbull.cli import main, respond


def test_format_discovery_and_file_identification_need_no_project(tmp_path, capsys):
    catalog = tmp_path / 'formats.sqlite'
    assert main(['format-modules', '--catalog', str(catalog)]) == 0
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
    assert {'format-modules', 'file-identify', 'smk-frame'} <= set(methods)


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
