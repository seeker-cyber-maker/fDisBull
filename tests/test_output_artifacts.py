import base64
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from fdisbull.output_artifacts import ArtifactError, OutputArtifactStore


def store(tmp_path, **options):
    return OutputArtifactStore(tmp_path / 'artifacts', **options)


def test_roundtrip_restart_unicode_range_and_pointer(tmp_path):
    s = store(tmp_path); raw = json.dumps({'a/b':{'~': ['café', 12]}}, ensure_ascii=False).encode()
    meta = s.put_stream([raw[:5], raw[5:]])
    assert meta == s.info(meta['id']) == store(tmp_path).info(meta['id'])
    pieces = [s.read(meta['id'], i, 1) for i in range(len(raw))]
    assert b''.join(base64.b64decode(p['data_base64']) for p in pieces) == raw
    assert pieces[-1]['eof'] and not pieces[-1]['whole_complete']
    assert s.read(meta['id'], 0, len(raw))['whole_complete']
    assert s.select(meta['id'], '/a~1b/~0/0')['value'] == 'café'
    limited = s.select(meta['id'], '', 2)
    assert not limited['complete'] and 'value' not in limited
    for pointer in ('not-a-pointer', '/a~2b', '/a~1b/~0/01'):
        with pytest.raises(ArtifactError): s.select(meta['id'], pointer)


def test_quotas_errors_and_stale_files(tmp_path):
    s = store(tmp_path, max_artifact_bytes=8, max_store_bytes=12)
    with pytest.raises(ArtifactError, match='artifact_too_large'): s.put_stream([b'"12345678"'])
    assert not list(s.root.glob('.partial-*'))
    s.put_stream([b'"12345"'])
    (s.root / '.partial-stale').write_bytes(b'x'*4); (s.root / '.partial-stale').chmod(0o600)
    with pytest.raises(ArtifactError, match='quota_exceeded'): s.put_stream([b'null'])
    with pytest.raises(ArtifactError, match='invalid_json'): store(tmp_path).put_stream([b'{invalid'])
    assert not list(s.root.glob('.partial-*')) == []  # stale file is never deleted


def test_corruption_and_no_clobber_export(tmp_path):
    s = store(tmp_path); m = s.put_stream([b'{"x":1}']); target = tmp_path / 'export.json'
    assert s.export(m['id'], target)['complete'] and target.read_bytes() == b'{"x":1}'
    assert target.stat().st_mode & 0o077 == 0
    with pytest.raises(ArtifactError, match='already_exists'): s.export(m['id'], target)
    (s.root / m['id']).write_bytes(b'{"x":2}')
    with pytest.raises(ArtifactError, match='integrity_error'): s.info(m['id'])
    with pytest.raises(ArtifactError, match='integrity_error'): s.read(m['id'])
    with pytest.raises(ArtifactError, match='integrity_error'): s.export(m['id'], tmp_path/'bad')


def test_paths_privacy_id_validation_and_git(tmp_path):
    insecure = tmp_path/'insecure'; insecure.mkdir(mode=0o755); insecure.chmod(0o755)
    with pytest.raises(ArtifactError, match='not_private'): OutputArtifactStore(insecure)
    assert insecure.stat().st_mode & 0o777 == 0o755
    s = store(tmp_path)
    for ident in ('../foo', 'out-'+'A'*64, 'out-'+'0'*63):
        with pytest.raises(ArtifactError, match='invalid_id'): s.info(ident)
    link=tmp_path/'link'; link.symlink_to(s.root, target_is_directory=True)
    with pytest.raises(ArtifactError, match='unsafe_path'): OutputArtifactStore(link)
    repo=tmp_path/'repo';repo.mkdir();(repo/'.git').mkdir()
    with pytest.raises(ArtifactError, match='inside_git'): OutputArtifactStore(repo/'outputs')
    ident=s.put_stream([b'[]'])['id']
    with pytest.raises(ArtifactError, match='inside_git'):s.export(ident,repo/'output.json')


def _put(root, q):
    try:q.put(OutputArtifactStore(root).put_stream([b'{"same":true}']))
    except Exception as e:q.put(str(e))


def test_concurrent_dedup(tmp_path):
    root=str(tmp_path/'store'); OutputArtifactStore(root)
    ctx=multiprocessing.get_context('spawn');q=ctx.Queue()
    procs=[ctx.Process(target=_put,args=(root,q)) for _ in range(4)]
    for p in procs:p.start()
    results=[q.get(timeout=15) for _ in procs]
    for p in procs:p.join(15); assert p.exitcode==0
    assert all(isinstance(x,dict) for x in results)
    assert len({x['id'] for x in results})==1
    assert len(list(Path(root).glob('out-*')))==1


def test_generator_failure_removes_partial_without_error_content(tmp_path):
    s = store(tmp_path)
    def chunks():
        yield b'{'
        raise RuntimeError('sensitive content')
    with pytest.raises(ArtifactError) as error: s.put_stream(chunks())
    assert error.value.code == 'io_error' and 'sensitive' not in str(error.value)
    assert not list(s.root.glob('.partial-*'))


def test_replaced_store_directory_is_refused(tmp_path):
    s = store(tmp_path); s.root.rename(tmp_path/'old')
    s.root.symlink_to(tmp_path/'old', target_is_directory=True)
    with pytest.raises(ArtifactError, match='unsafe_path'): s.put_stream([b'null'])


def test_empty_chunk_stream_is_bounded(tmp_path):
    s = store(tmp_path)
    with pytest.raises(ArtifactError, match='stream_budget'):
        s.put_stream(b'' for _ in range(65537))
    assert not list(s.root.glob('.partial-*'))


def test_read_ranges_and_invalid_json_are_refused(tmp_path):
    s=store(tmp_path); ident=s.put_stream([b'null'])['id']
    for offset,length in ((-1,1),(5,1),(0,8193),(0,0),(True,1)):
        with pytest.raises(ArtifactError, match='invalid_range'): s.read(ident,offset,length)
    for raw in (b'\xff', b'NaN', b'{"x":1,"x":2}'):
        with pytest.raises(ArtifactError, match='invalid_json'): s.put_stream([raw])


@pytest.mark.parametrize('missing', ['fcntl', 'getuid'])
def test_unsupported_platform_fails_before_creating_store(tmp_path, monkeypatch, missing):
    import fdisbull.output_artifacts as module
    if missing == 'fcntl': monkeypatch.setattr(module, 'fcntl', None)
    else: monkeypatch.setattr(module.os, 'getuid', None)
    root = tmp_path / 'not-created'
    with pytest.raises(ArtifactError) as error: OutputArtifactStore(root)
    assert error.value.code == 'platform_unsupported'
    assert not root.exists()
