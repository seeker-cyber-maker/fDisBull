import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('chat_parts', Path(__file__).parents[1] / 'scripts/chat_offline_parts.py')
parts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parts)


def test_parts_round_trip_and_tamper_detection(tmp_path):
    source = tmp_path / 'archive.zip'; source.write_bytes(b'0123456789abc')
    directory = tmp_path / 'parts'; directory.mkdir()
    manifest = parts.split(source, directory, 5)
    assert [p['size'] for p in manifest['parts']] == [5, 5, 3]
    output = tmp_path / 'restored.zip'
    parts.reassemble(directory, output)
    assert output.read_bytes() == source.read_bytes()
    (directory / 'part-000002').write_bytes(b'wrong')
    with pytest.raises(ValueError, match='changed part'):
        parts.reassemble(directory, tmp_path / 'bad.zip')
    assert not (tmp_path / 'bad.zip').exists()
    (directory / 'part-000002').unlink()
    with pytest.raises(ValueError, match='Missing'):
        parts.reassemble(directory, tmp_path / 'missing.zip')


def test_parts_reject_unsafe_manifest_and_chunk_size(tmp_path):
    source = tmp_path / 'archive'; source.write_bytes(b'abcdefgh')
    directory = tmp_path / 'parts'; directory.mkdir()
    with pytest.raises(ValueError, match='part size'):
        parts.split(source, directory, parts.MAX_PART + 1)
    parts.split(source, directory, 3)
    file = directory / 'manifest.json'; manifest = json.loads(file.read_text())
    manifest['parts'][0]['name'] = '../escape'
    file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Invalid part identity'):
        parts.reassemble(directory, tmp_path / 'result')
