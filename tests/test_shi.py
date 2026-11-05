"""Authored planar vectors only; no original Sherlock images or captures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from fdisbull.cli import respond
from fdisbull.media import extract_media, inspect_media
from fdisbull.shi import decode_shi, encode_shi


def authored_shi():
    # Independently authored records, not output from the encoder under test.
    header = b'\x04\x00\x01\x00\x20\x00\x20\x00'
    source = bytearray((header + bytes(512)) * 46)
    # First row: 0..15 twice. Four planes, four bytes per plane, MSB first.
    source[8:24] = bytes.fromhex('55 55 55 55 33 33 33 33 0f 0f 0f 0f 00 ff 00 ff')
    # Second row: color 8. Last row: 15..0 twice, distinguishing row order.
    source[24:40] = bytes(12) + b'\xff' * 4
    source[504:520] = bytes.fromhex('aa aa aa aa cc cc cc cc f0 f0 f0 f0 ff 00 ff 00')
    source[528:1040] = b'\xff' * 512  # Image 1 is solid color 15.
    source[-1] = 1  # Last pixel of image 45 has only plane 3 set.
    expected = [bytes(range(16)) * 2 + bytes([8]) * 32 + bytes(29 * 32)
                + bytes(range(15, -1, -1)) * 2,
                bytes([15]) * 1024] + [bytes(1024)] * 43 + [bytes(1023) + b'\x08']
    return bytes(source), tuple(expected)


def test_independent_planar_vectors_and_exact_round_trip():
    source, expected = authored_shi()
    decoded = decode_shi(source)
    assert decoded == expected
    assert encode_shi(expected) == source
    assert encode_shi(decoded) == source
    assert all(isinstance(pixels, bytes) for pixels in decoded)
    mutable_source = bytearray(source)
    assert decode_shi(memoryview(mutable_source)) == expected
    assert mutable_source == source
    assert encode_shi([bytearray(pixels) for pixels in expected]) == source


@pytest.mark.parametrize('data', [None, 'shi', b'', bytes(23919), bytes(23921)])
def test_wrong_type_size_and_trailing_bytes_refused(data):
    with pytest.raises(ValueError, match='SHI profile'):
        decode_shi(data)


@pytest.mark.parametrize('image_id,header_byte', [(0, 0), (1, 2), (23, 4), (45, 6)])
def test_every_record_header_is_validated(image_id, header_byte):
    source = bytearray(authored_shi()[0])
    source[image_id * 520 + header_byte] ^= 1
    with pytest.raises(ValueError, match=f'header at image {image_id}'):
        decode_shi(source)


@pytest.mark.parametrize('images', [
    None, [], [bytes(1024)] * 45, [bytes(1024)] * 47,
    [bytes(1023)] + [bytes(1024)] * 45,
    [bytes(1024)] * 45 + [bytes(1025)],
    [bytes(1024)] * 45 + [bytes(1023) + b'\x10'],
    [bytes(1024)] * 45 + [bytes(1023) + b'\xff'],
    [bytes(1024)] * 45 + [[0] * 1024],
])
def test_encoder_refuses_incomplete_or_lossy_inputs(images):
    with pytest.raises(ValueError):
        encode_shi(images)


def test_inventory_ids_source_ranges_palette_and_mask_roles(tmp_path):
    data, expected = authored_shi()
    source = tmp_path / 'authored.shi'
    source.write_bytes(data)
    result = inspect_media(source, adapter='sherlock-shi')
    assert result['input_executed'] is False
    assert result['qualification'] == 'structural-only'
    assert result['inputs'] == [dict(role='container', size=23920,
                                     sha256=hashlib.sha256(data).hexdigest())]
    assert result['extract_all_member'] == 'all'
    assert result['image_count'] == 46
    for image_id, member in enumerate(result['members']):
        assert member['image_id'] == image_id
        assert member['name'] == f'image-{image_id:02d}'
        assert member['offset'] == image_id * 520
        assert member['size'] == 520
        assert member['payload_offset'] == image_id * 520 + 8
        assert member['payload_size'] == 512
        assert member['sha256'] == hashlib.sha256(data[image_id*520:(image_id+1)*520]).hexdigest()
        assert member['pixels_sha256'] == hashlib.sha256(expected[image_id]).hexdigest()
    members = result['members']
    assert (members[35]['row'], members[35]['item']) == (5, 5)
    assert members[36]['role'] == 'empty-tile'
    assert [members[i]['role'] for i in range(37, 45)] == ['mask', 'ink'] * 4
    assert [(p['mask_id'], p['ink_id']) for p in result['compositing']['pairs']] == [
        (37, 38), (39, 40), (41, 42), (43, 44)]
    assert result['compositing']['operation'] == '(destination & mask) | ink'
    assert result['palette']['embedded'] is False
    assert result['palette']['colors'][9] == [0, 0, 255]
    assert members[45]['role'] == 'separator'
    assert '"pixels":' not in json.dumps(result)


def test_all_pngs_preserve_indices_palette_provenance_and_private_outputs(tmp_path):
    data, expected = authored_shi()
    source = tmp_path / 'authored.shi'
    source.write_bytes(data)
    output = tmp_path / 'images'
    receipt = extract_media(source, output, adapter='sherlock-shi', member='all')
    assert json.loads((output / 'media-manifest.json').read_text()) == receipt
    assert receipt['extracted']['format'] == 'indexed-png'
    assert len(receipt['extracted']['images']) == 46
    assert output.stat().st_mode & 0o777 == 0o700
    assert len(list(output.iterdir())) == 47
    for item in receipt['extracted']['images']:
        image_id = item['image_id']
        path = output / item['path']
        png = path.read_bytes()
        assert path.name == f'image-{image_id:02d}.png'
        assert item['source_member'] == f'image-{image_id:02d}'
        assert item['sha256'] == hashlib.sha256(png).hexdigest()
        assert item['size'] == len(png)
        assert path.stat().st_mode & 0o777 == 0o600
        assert png[24:26] == b'\x04\x03'  # Four bits, indexed PNG color type.
        with Image.open(path) as image:
            assert image.size == (32, 32) and image.mode == 'P'
            assert image.tobytes() == expected[image_id]
            assert image.getpalette() == [c for color in receipt['palette']['colors'] for c in color]
            assert 'transparency' not in image.info
    assert (output / 'media-manifest.json').stat().st_mode & 0o777 == 0o600
    assert source.read_bytes() == data
    with pytest.raises(FileExistsError):
        extract_media(source, output, adapter='sherlock-shi', member='all')
    png_bytes = sum(item['size'] for item in receipt['extracted']['images'])
    with pytest.raises(ValueError, match='output budget'):
        extract_media(source, tmp_path / 'too-small', adapter='sherlock-shi', member='all',
                      max_output_bytes=png_bytes - 1)
    assert not (tmp_path / 'too-small').exists()


def test_single_record_json_extraction_and_invalid_selections(tmp_path):
    source = tmp_path / 'authored.shi'
    source.write_bytes(authored_shi()[0])
    output = tmp_path / 'one'
    response = respond({'method': 'media-extract', 'params': dict(
        path=str(source), output=str(output), adapter='sherlock-shi', member='image-37')},
        default_project='/missing.fdb')
    assert response['ok'], response
    assert sorted(p.name for p in output.iterdir()) == ['image-37.png', 'media-manifest.json']
    assert response['result']['extracted']['images'][0]['image_id'] == 37
    for member in ('../escape', 'image-46', 'image-0', 0, None):
        with pytest.raises(ValueError, match='Unknown member'):
            extract_media(source, tmp_path / 'invalid', adapter='sherlock-shi', member=member)
    for params in (dict(number=0), dict(volume_root=str(tmp_path))):
        with pytest.raises(ValueError, match='AGI resource parameters'):
            inspect_media(source, adapter='sherlock-shi', **params)
    assert not (tmp_path / 'invalid').exists()


def test_shi_source_and_output_boundaries(tmp_path):
    source = tmp_path / 'authored.shi'
    data = authored_shi()[0]
    source.write_bytes(data + b'\x00')
    with pytest.raises(ValueError, match='size limit'):
        inspect_media(source, adapter='sherlock-shi')
    source.write_bytes(data)
    link = tmp_path / 'source-link'
    link.symlink_to(source)
    with pytest.raises(ValueError, match='symlink'):
        inspect_media(link, adapter='sherlock-shi')
    repo = tmp_path / 'repo'
    repo.mkdir(mode=0o700)
    (repo / '.git').write_text('gitdir: unused')
    with pytest.raises(ValueError, match='inside_git'):
        extract_media(source, repo / 'images', adapter='sherlock-shi', member='all')
    assert not (repo / 'images').exists()


def test_fresh_cli_inventory_and_all_png_extraction_outside_checkout(tmp_path):
    source = tmp_path / 'authored.shi'
    source.write_bytes(authored_shi()[0])
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    def invoke(arguments):
        completed = subprocess.run([sys.executable, '-m', 'fdisbull', *arguments],
            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15)
        assert completed.returncode == 0, completed.stderr + completed.stdout
        response = json.loads(completed.stdout)
        assert response['ok'], response
        return response['result']
    inventory = invoke(['media-inspect', str(source), '--adapter', 'sherlock-shi'])
    assert inventory['members'][45]['offset'] == 23400
    result = invoke(['media-extract', str(source), str(tmp_path / 'export'),
                     '--adapter', 'sherlock-shi', '--member', 'all',
                     '--max-payload-bytes', '65536'])
    assert len(result['extracted']['images']) == 46
    assert (tmp_path / 'export/image-45.png').is_file()
