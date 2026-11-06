"""Public CLI/JSON seams using authored PNG and KINT data, never game assets."""
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image
import pytest

from fdisbull.cli import main, respond
from fdisbull.decoder_modules import analyze_input, builtin_registry, lift_input
from fdisbull.media import extract_media, inspect_media


def atlas():
    # Distinct RGBA pixels expose accidental resampling, compositing or flips.
    image = Image.new('RGBA', (160, 200))
    image.putdata([(x % 256, y % 256, (x + 3 * y) % 256, 128 + (x % 128))
                   for y in range(200) for x in range(160)])
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def ke_image(code=struct.pack('<I', 0x214)):
    header = bytearray(512)
    struct.pack_into('<Q', header, 0, 0x0123456789abcdef)
    header[0xd0:0xd6] = b'KINT6\0'
    struct.pack_into('<4Q', header, 0xe0, 512 + len(code), 8, 1024, 2048)
    return bytes(header) + code


def test_new_media_and_processor_are_discoverable_without_a_project():
    media = respond({'method': 'media-modules'}, default_project='/missing.fdb')
    assert media['ok']
    assert {'kint6-ke', 'sherlock7-images', 'kint6-user-buttons',
            'kint6-user-overlays'} <= {m['name'] for m in media['result']['modules']}
    assert 'fdisbull.kint6' in {m['identity'] for m in builtin_registry().catalog()}
    capabilities = respond({'method': 'capabilities'})
    assert capabilities['ok']
    listed = {m['id']: m for m in capabilities['result']['capabilities']}
    assert listed['decode.kint6']['requires'] == []
    assert listed['media.sherlock7-atlas']['requires'] == ['Pillow']
    assert listed['decode.kint6']['runtime_validation'] == 'not_run'


def test_png_inspect_cli_and_json_exact_pixel_extraction(tmp_path, capsys):
    source = tmp_path / 'authored.png'
    original = atlas()
    source.write_bytes(original)
    assert main(['media-inspect', str(source), '--adapter', 'sherlock7-images']) == 0
    report = json.loads(capsys.readouterr().out)['result']
    assert report['inputs'][0]['sha256'] == hashlib.sha256(original).hexdigest()
    assert report['input_executed'] is False
    selected = next(m for m in report['members'] if m['role'] == 'puzzle-item')
    assert selected['offset'] is None  # Pixel coordinates are not compressed file offsets.
    reply = respond({'method': 'media-extract', 'params': {
        'path': str(source), 'output': str(tmp_path / 'out'),
        'adapter': 'sherlock7-images', 'member': selected['name']}},
        default_project='/missing.fdb')
    assert reply['ok'], reply
    receipt = reply['result']
    emitted = tmp_path / 'out' / receipt['extracted']['path']
    with Image.open(io.BytesIO(original)) as decoded, Image.open(emitted) as crop:
        rect = selected['pixel_rect']
        expected = decoded.convert('RGBA').crop((rect['x'], rect['y'],
                                                rect['x'] + rect['width'],
                                                rect['y'] + rect['height']))
        assert crop.convert('RGBA').tobytes() == expected.tobytes()
    assert json.loads((tmp_path / 'out/media-manifest.json').read_text()) == receipt
    assert emitted.stat().st_mode & 0o777 == 0o600
    assert source.read_bytes() == original


def test_png_bulk_export_aggregate_budget_and_private_paths(tmp_path):
    source = tmp_path / 'authored.png'
    source.write_bytes(atlas())
    report = inspect_media(source, adapter='sherlock7-images')
    total = sum(m['size'] for m in report['members'])
    with pytest.raises(ValueError, match='budget'):
        extract_media(source, tmp_path / 'too-small', adapter='sherlock7-images',
                      member='all', max_output_bytes=total - 1)
    assert not (tmp_path / 'too-small').exists()
    receipt = extract_media(source, tmp_path / 'all', adapter='sherlock7-images',
                            member='all', max_output_bytes=total)
    assert len(receipt['extracted']) == len(report['members'])
    assert sum((tmp_path / 'all' / m['path']).stat().st_size
               for m in receipt['extracted']) == total
    for name in ('../escape', 'missing', '/absolute'):
        with pytest.raises(ValueError, match='Unknown member'):
            extract_media(source, tmp_path / 'bad', adapter='sherlock7-images', member=name)
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / '.git').write_text('gitdir: somewhere')
    with pytest.raises(ValueError, match='inside_git'):
        extract_media(source, repo / 'out', adapter='sherlock7-images', member='all')


def test_ke_media_uses_header_validator_and_keeps_runtime_memory_virtual(tmp_path):
    source = tmp_path / 'authored.ke'
    original = ke_image()
    source.write_bytes(original)
    report = inspect_media(source, adapter='kint6-ke')
    assert [(m['name'], m['offset'], m['size']) for m in report['members']] == [
        ('header', 0, 512), ('body', 512, 4)]
    receipt = extract_media(source, tmp_path / 'ke-body', adapter='kint6-ke', member='body')
    assert (tmp_path / 'ke-body' / receipt['extracted']['path']).read_bytes() == original[512:]
    assert [s['name'] for s in report['container']['sections']] == ['CODE', 'ZERO', 'STACK', 'HEAP']
    assert all(s['file_offset'] is None for s in report['container']['sections'][1:])
    assert source.read_bytes() == original
    with pytest.raises(ValueError):
        inspect_media(source, adapter='kint6-ke', number=0)
    source.write_bytes(original[:-1])
    with pytest.raises(ValueError):
        inspect_media(source, adapter='kint6-ke')


def test_kint_module_cli_json_snapshot_and_budget(tmp_path, capsys):
    source = tmp_path / 'authored.ke'
    source.write_bytes(ke_image(struct.pack('<II', 0x294, 0x214)))  # NOP; TERM
    opened = builtin_registry().open('fdisbull.kint6', source)
    expected = analyze_input(opened)
    assert expected['complete'] and expected['runtime_execution'] is False
    assert [i['facts']['mnemonic'] for i in expected['instructions']] == ['nop', 'term']
    assert main(['module-analyze', 'fdisbull.kint6', str(source), '--max-instructions', '10']) == 0
    assert json.loads(capsys.readouterr().out)['result']['snapshot'] == opened.identity
    limited = respond({'method': 'module-analyze', 'params': {
        'module': 'fdisbull.kint6', 'path': str(source), 'max_instructions': 1}},
        default_project='/missing.fdb')
    assert limited['ok'] and not limited['result']['complete']
    assert limited['result']['issues'][-1]['kind'] == 'instruction_budget'
    with pytest.raises(ValueError, match='qualified lifter'):
        lift_input(opened, initial_state={})
    state = tmp_path / 'state.json'
    state.write_text('{}')
    assert main(['module-lift', 'fdisbull.kint6', str(source),
                 '--state-file', str(state)]) == 1
    refusal = json.loads(capsys.readouterr().out)
    assert refusal['ok'] is False
    assert refusal['error']['type'] == 'ValueError'
    assert 'qualified lifter' in refusal['error']['message']
    metadata = opened.source
    metadata['sections'][0]['size_bytes'] = 0
    assert opened.source['sections'][0]['size_bytes'] == 520
    source.write_bytes(ke_image())
    changed = builtin_registry().open('fdisbull.kint6', source)
    assert changed.identity != opened.identity
    source.unlink()
    assert analyze_input(opened) == expected
