"""Independent authored envelopes; no original game files or captured bytes."""
import hashlib
import json
from pathlib import Path
import struct

import pytest

from fdisbull.cli import main, respond
from fdisbull.media import inspect_media, extract_media, media_modules


def mz():
    # 32-byte header + four bytes in the declared image (36 bytes total).
    # All 14 words are explicitly authored: no relocation records, CS:IP 0:0.
    return struct.pack('<14H', 0x5a4d, 36, 1, 0, 2, 0, 0, 0, 0, 0, 0, 0, 28, 0) + bytes(4) + b'CODE' + b'opaque-tail'


def test_catalog_and_public_cli_need_no_project(capsys):
    report = respond({'method': 'media-modules'}, default_project='/missing.fdb')
    assert report['ok']
    modules = {item['name']: item for item in report['result']['modules']}
    assert set(modules) == {'mz-envelope', 'agi-v2', 'gog-inno', 'agi-picture', 'avi-capture',
                            'westwood-pak', 'westwood-cps', 'westwood-wsa', 'westwood-emc2'}
    assert media_modules() == report['result']
    assert main(['media-modules']) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    methods = respond({'method': 'help'})['result']['methods']
    assert all(n in methods for n in ('media-modules', 'media-inspect', 'media-extract'))


def test_mz_exact_ranges_and_private_extraction(tmp_path):
    source = tmp_path / 'authored'
    original = mz()
    source.write_bytes(original)
    result = inspect_media(source, adapter='mz-envelope')
    assert [(m['name'], m['offset'], m['size']) for m in result['members']] == [
        ('header', 0, 32), ('module', 32, 4), ('tail', 36, 11)]
    assert result['qualification'] == 'structural-only'
    assert result['inputs'] == [{'role': 'container', 'size': 47, 'sha256': hashlib.sha256(original).hexdigest()}]
    out = tmp_path / 'private'
    receipt = extract_media(source, out, adapter='mz-envelope', member='tail')
    assert (out / 'payload.bin').read_bytes() == b'opaque-tail'
    assert receipt['extracted']['sha256'] == hashlib.sha256(b'opaque-tail').hexdigest()
    assert json.loads((out / 'media-manifest.json').read_text()) == receipt
    assert out.stat().st_mode & 0o777 == 0o700
    assert (out / 'payload.bin').stat().st_mode & 0o777 == 0o600
    assert b'opaque-tail' not in (out / 'media-manifest.json').read_bytes()
    assert source.read_bytes() == original
    with pytest.raises(FileExistsError):
        extract_media(source, out, adapter='mz-envelope', member='tail')


def test_cli_and_json_inventory_and_extraction(tmp_path, capsys):
    source = tmp_path / 'authored'
    source.write_bytes(mz())
    assert main(['media-inspect', str(source), '--adapter', 'mz-envelope']) == 0
    assert json.loads(capsys.readouterr().out)['result']['adapter'] == 'mz-envelope'
    response = respond({'method': 'media-extract', 'params': dict(path=str(source),
        output=str(tmp_path / 'export'), adapter='mz-envelope', member='module')}, default_project='/missing.fdb')
    assert response['ok'], response
    assert (tmp_path / 'export/payload.bin').read_bytes() == b'CODE'


@pytest.mark.parametrize('data', [b'', b'MZ', b'not MZ', mz()[:35],
    mz()[:2] + b'\xff\xff' + mz()[4:]])
def test_malformed_and_truncated_mz_refused(tmp_path, data):
    source = tmp_path / 'authored'
    source.write_bytes(data)
    with pytest.raises(ValueError):
        inspect_media(source, adapter='mz-envelope')


def test_secondary_and_invalid_relocations_refused(tmp_path):
    # Independent existing PE fixture is explicitly outside this adapter.
    from fixtures_formats import pe64
    source = tmp_path / 'authored'
    source.write_bytes(pe64())
    with pytest.raises(ValueError):
        inspect_media(source, adapter='mz-envelope')
    data = bytearray(mz())
    struct.pack_into('<H', data, 6, 1)
    struct.pack_into('<HH', data, 28, 4, 0)  # Fixup points beyond four-byte module.
    source.write_bytes(data)
    with pytest.raises(ValueError, match='relocation'):
        inspect_media(source, adapter='mz-envelope')


def test_agi_existing_reader_reused_with_provenance(tmp_path, monkeypatch):
    import fdisbull.agi_picture as agi
    directory = tmp_path / 'PICDIR'
    # Resource zero: volume 2, absolute offset 7; payload begins at byte 12.
    directory.write_bytes(b'\x20\x00\x07\xff\xff\xff')
    (tmp_path / 'VOL.2').write_bytes(b'padding' + b'\x12\x34\x02\x03\x00' + b'XYZ')
    original = agi.extract_v2_resource
    calls = []
    def recording(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(agi, 'extract_v2_resource', recording)
    result = extract_media(directory, tmp_path / 'out', adapter='agi-v2', member='resource', volume_root=tmp_path, number=0)
    assert len(calls) == 1
    assert result['members'] == [dict(name='resource', input_role='volume-2', offset=12,
                                    size=3, sha256=hashlib.sha256(b'XYZ').hexdigest())]
    assert (tmp_path / 'out/payload.bin').read_bytes() == b'XYZ'
    assert len(result['inputs']) == 2
    with pytest.raises(ValueError, match='absent'):
        inspect_media(directory, adapter='agi-v2', volume_root=tmp_path, number=1)
    (tmp_path / 'VOL.2').write_bytes(b'padding' + b'\x12\x34\x02\x04\x00' + b'XYZ')
    with pytest.raises(ValueError, match='Truncated'):
        inspect_media(directory, adapter='agi-v2', volume_root=tmp_path, number=0)


@pytest.mark.parametrize('payload', [b'', b'\x12\x34\x03\x00\x00', b'\x00\x00\x02\x00\x00'])
def test_bad_agi_headers(tmp_path, payload):
    directory = tmp_path / 'PICDIR'
    directory.write_bytes(b'\x20\x00\x00')
    (tmp_path / 'VOL.2').write_bytes(payload)
    with pytest.raises(ValueError):
        inspect_media(directory, adapter='agi-v2', volume_root=tmp_path, number=0)


def test_no_tail_unknown_adapter_and_output_budget(tmp_path):
    source = tmp_path / 'authored'
    source.write_bytes(mz()[:36])
    assert [m['name'] for m in inspect_media(source, adapter='mz-envelope')['members']] == ['header', 'module']
    for params in [dict(adapter='lzexe'), dict(adapter='mz-envelope', number=0)]:
        with pytest.raises(ValueError):
            inspect_media(source, **params)
    for params in [dict(member='tail'), dict(member='../escape'), dict(member='module', max_output_bytes=3),
                   dict(member='module', max_output_bytes=True)]:
        with pytest.raises(ValueError):
            extract_media(source, tmp_path / 'out', adapter='mz-envelope', **params)
    assert not (tmp_path / 'out').exists()


def test_input_and_output_path_limits(tmp_path, monkeypatch):
    import fdisbull.media as module
    source = tmp_path / 'authored'
    source.write_bytes(mz())
    monkeypatch.setattr(module, 'MAX_SOURCE', 10)
    with pytest.raises(ValueError, match='size limit'):
        inspect_media(source, adapter='mz-envelope')
    monkeypatch.setattr(module, 'MAX_SOURCE', 64 * 1024 * 1024)
    link = tmp_path / 'link'
    link.symlink_to(source)
    with pytest.raises(ValueError, match='symlink'):
        inspect_media(link, adapter='mz-envelope')
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / '.git').write_text('gitdir: anywhere')
    with pytest.raises(ValueError, match='inside_git'):
        extract_media(source, repo / 'out', adapter='mz-envelope', member='module')
    parent_link = tmp_path / 'parent-link'
    parent_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='unsafe_path'):
        extract_media(source, parent_link / 'out', adapter='mz-envelope', member='module')
    public = tmp_path / 'public'
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(ValueError, match='not_private'):
        extract_media(source, public / 'out', adapter='mz-envelope', member='module')


def test_resource_ambiguity_and_directory_bounds(tmp_path):
    directory = tmp_path / 'PICDIR'
    directory.write_bytes(bytes(769))
    with pytest.raises(ValueError):
        inspect_media(directory, adapter='agi-v2', volume_root=tmp_path, number=0)
    directory.write_bytes(b'\x20\x00\x00')
    (tmp_path / 'VOL.2').write_bytes(b'\x12\x34\x02\x00\x00')
    (tmp_path / 'vol.2').write_bytes(b'\x12\x34\x02\x00\x00')
    with pytest.raises(ValueError, match='ambiguous'):
        inspect_media(directory, adapter='agi-v2', volume_root=tmp_path, number=0)


def test_agi_directory_home_expansion(tmp_path, monkeypatch):
    directory = tmp_path / 'PICDIR'
    directory.write_bytes(b'\x00\x00\x00')
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00\x01\x00Q')
    original = Path.expanduser
    def authored_home(path):
        return directory if str(path) == '~/PICDIR' else original(path)
    monkeypatch.setattr(Path, 'expanduser', authored_home)
    result = inspect_media('~/PICDIR', adapter='agi-v2', volume_root=tmp_path, number=0)
    assert result['members'][0]['size'] == 1
    assert result['members'][0]['sha256'] == hashlib.sha256(b'Q').hexdigest()


@pytest.mark.parametrize('limit,global_limit,member,expected_ok', [
    (None, None, 'module', True),
    (4, 4096, 'module', True),
    (3, 4096, 'module', False),
    (1048576, 4096, 'tail', False),
    (0, None, 'module', False),
    (67108865, None, 'module', False),
])
def test_fresh_cli_extraction_payload_budget(tmp_path, limit, global_limit, member, expected_ok):
    import os
    import subprocess
    import sys
    source = tmp_path / 'authored'
    source.write_bytes(mz()[:36] + bytes(1048577))
    output = tmp_path / 'extracted'
    command = [sys.executable, '-m', 'fdisbull']
    if global_limit is not None:
        command += ['--max-output-bytes', str(global_limit)]
    command += ['media-extract', str(source), str(output), '--adapter', 'mz-envelope', '--member', member]
    if limit is not None:
        command += ['--max-payload-bytes', str(limit)]
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    response = json.loads(result.stdout)
    assert response.get('ok') is expected_ok, (result.returncode, response, result.stderr)
    assert result.returncode == (0 if expected_ok else 1)
    if global_limit is not None:
        assert len(result.stdout.encode()) <= global_limit
    if expected_ok:
        assert (output / 'payload.bin').read_bytes() == b'CODE'
    else:
        assert not output.exists()
        assert 'output budget' in response['error']['message'] or 'max_output_bytes' in response['error']['message']


def test_fresh_cli_global_reply_budget_stays_independent(tmp_path):
    import os
    import subprocess
    import sys
    source = tmp_path / 'authored'; source.write_bytes(mz())
    output = tmp_path / 'out'
    command = [sys.executable, '-m', 'fdisbull', '--max-output-bytes', '3',
               'media-extract', str(source), str(output), '--adapter', 'mz-envelope',
               '--member', 'module', '--max-payload-bytes', '4']
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run(command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert 'inline output budget' in json.loads(result.stdout)['error']
    assert not output.exists()
