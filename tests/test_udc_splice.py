"""Generic derived artifacts; all fixture bytes are authored in this test."""
import hashlib
import json

import pytest

from fdisbull.udc_splice import build_splice, emit_splice


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest(source=b'0123456789'):
    return {'format': 'fdisbull-udc-splice-1', 'source_sha256': sha(source),
            'patches': [{'offset': 2, 'expected_sha256': sha(b'23'), 'replace_hex': b'AB'.hex()}],
            'appended': [{'bytes_hex': b'END'.hex(), 'sha256': sha(b'END')}],
            'max_output_bytes': 64}


def test_build_preserves_every_undeclared_byte_and_binds_receipt():
    source = b'0123456789'
    output, receipt = build_splice(source, manifest(source))
    assert source == b'0123456789' and output == b'01AB456789END'
    assert receipt['source_sha256'] == sha(source)
    assert receipt['output_sha256'] == sha(output)
    assert receipt['source_byte_identity'] is False
    assert [(r['offset'], r['size']) for r in receipt['unchanged_spans']] == [(0, 2), (4, 6)]
    assert receipt['appended'][0]['offset'] == len(source)
    assert receipt['semantics'] == 'byte derivation only; behavior requires separate qualification'


def test_empty_selection_is_byte_identical():
    doc = manifest(); doc['patches'] = []; doc['appended'] = []
    output, receipt = build_splice(b'0123456789', doc)
    assert output == b'0123456789' and receipt['source_byte_identity']


@pytest.mark.parametrize('change,match', [
    (lambda d: d.update(source_sha256='0' * 64), 'source.*hash'),
    (lambda d: d['patches'][0].update(expected_sha256='0' * 64), 'patch.*hash'),
    (lambda d: d['appended'][0].update(sha256='0' * 64), 'append.*hash'),
    (lambda d: d['patches'][0].update(offset=9), 'bounds'),
    (lambda d: d['patches'][0].update(offset=True), 'offset'),
    (lambda d: d['patches'][0].update(replace_hex='A'), 'hex'),
    (lambda d: d['patches'][0].update(replace_hex='00 01'), 'hex'),
    (lambda d: d.update(max_output_bytes=12), 'output.*budget'),
    (lambda d: d.update(max_output_bytes=True), 'max_output_bytes'),
    (lambda d: d.update(unknown='ignored?'), 'fields'),
    (lambda d: d['patches'][0].update(unknown=1), 'fields'),
])
def test_bad_selection_refuses_before_creating_output(tmp_path, change, match):
    doc = manifest(); change(doc)
    target = tmp_path / 'new'
    with pytest.raises(ValueError, match=match):
        emit_splice(b'0123456789', doc, target)
    assert not target.exists()


def test_overlapping_patches_refused_and_order_is_normalized():
    doc = manifest()
    doc['patches'].append({'offset': 3, 'expected_sha256': sha(b'34'), 'replace_hex': '5859'})
    with pytest.raises(ValueError, match='overlap'):
        build_splice(b'0123456789', doc)
    doc['patches'][1] = {'offset': 7, 'expected_sha256': sha(b'78'), 'replace_hex': '5859'}
    output, receipt = build_splice(b'0123456789', doc)
    doc['patches'].reverse()
    assert build_splice(b'0123456789', doc) == (output, receipt)
    assert output == b'01AB456XY9END'


def test_emit_readback_receipt_and_no_overwrite(tmp_path):
    target = tmp_path / 'new'
    receipt = emit_splice(b'0123456789', manifest(), target, output_name='TEST.COM')
    assert (target / 'TEST.COM').read_bytes() == b'01AB456789END'
    retained = json.loads((target / 'splice-receipt.json').read_text())
    assert retained['readback_verified'] is True
    assert retained['output_sha256'] == receipt['output_sha256']
    before = sorted((p.name, p.read_bytes()) for p in target.iterdir())
    with pytest.raises(ValueError, match='new'):
        emit_splice(b'0123456789', manifest(), target, output_name='TEST.COM')
    assert sorted((p.name, p.read_bytes()) for p in target.iterdir()) == before


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'sub/name', r'sub\name',
                                'splice-receipt.json', 'SPLICE-RECEIPT.JSON',
                                '.git', '.GIT', 'NUL', 'bad.'])
def test_output_name_cannot_escape_or_collide(tmp_path, name):
    with pytest.raises(ValueError, match='name'):
        emit_splice(b'0123456789', manifest(), tmp_path / 'new', output_name=name)
    assert not (tmp_path / 'new').exists()


def test_repository_output_is_refused(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir(); (repo / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='Git'):
        emit_splice(b'0123456789', manifest(), repo / 'new')
    assert not (repo / 'new').exists()


def test_readback_failure_cleans_only_this_new_output(tmp_path, monkeypatch):
    from pathlib import Path
    read = Path.read_bytes
    def corrupt(path):
        return b'changed' if path.name == 'PROGRAM.COM' else read(path)
    monkeypatch.setattr(Path, 'read_bytes', corrupt)
    with pytest.raises(ValueError, match='readback'):
        emit_splice(b'0123456789', manifest(), tmp_path / 'new')
    assert not (tmp_path / 'new').exists()


def test_source_must_be_immutable_bytes():
    with pytest.raises(ValueError, match='immutable'):
        build_splice(bytearray(b'0123456789'), manifest())
