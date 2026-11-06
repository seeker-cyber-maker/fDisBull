import gzip
import hashlib
import importlib.util
import json
import lzma
import io
import tarfile
from pathlib import Path
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('chat_ci_inputs', Path(__file__).parents[1] / 'scripts/ci/prepare-chat-inputs.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_base_stream_preserves_uncompressed_identity_and_budget(tmp_path):
    payload = b'guest base\0' * 30
    source = tmp_path / 'base.gz'
    source.write_bytes(gzip.compress(payload))
    output = tmp_path / 'base.xz'
    result = module.compress_base(source, output)
    assert result == {'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}
    assert lzma.decompress(output.read_bytes()) == payload
    with pytest.raises(ValueError, match='exceeds'):
        module.compress_base(source, tmp_path / 'too-large.xz', max_size=len(payload) - 1)


def test_wheel_pins_normalize_and_reject_duplicates(tmp_path):
    def make(filename, name, version):
        with zipfile.ZipFile(tmp_path / filename, 'w') as wheel:
            wheel.writestr('x.dist-info/METADATA', f'Name: {name}\nVersion: {version}\n')
    make('first.whl', 'Tree_Sitter', '0.25.2')
    assert module.wheel_pins(tmp_path) == {'tree-sitter': '0.25.2'}
    make('second.whl', 'tree-sitter', '0.25.2')
    with pytest.raises(ValueError, match='duplicate'):
        module.wheel_pins(tmp_path)


def test_only_rejects_missing_and_ambiguous(tmp_path):
    with pytest.raises(ValueError, match='exactly one'):
        module.only([], 'input')
    a = tmp_path / 'a'; b = tmp_path / 'b'
    a.write_bytes(b'a'); b.write_bytes(b'b')
    assert module.only([a], 'input') == a
    with pytest.raises(ValueError, match='exactly one'):
        module.only([a, b], 'input')


def test_source_companion_bound_to_legacy_manifest(tmp_path):
    companion = tmp_path / 'source.tar'
    companion.write_bytes(b'original source bytes')
    manifest = {'source_commit': 'a'*40, 'source_companion': companion.name,
                'source_companion_sha256': module.identity(companion)['sha256']}
    archive = tmp_path / 'offline.tar.gz'
    content = json.dumps(manifest).encode()
    with tarfile.open(archive, 'w:gz') as tar:
        info = tarfile.TarInfo('kit/manifest.json'); info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    module.verify_source_companion(archive, companion, 'a'*40)
    companion.write_bytes(b'changed')
    with pytest.raises(ValueError, match='does not match'):
        module.verify_source_companion(archive, companion, 'a'*40)


def test_full_windows_base_requires_verified_pe32_and_exact_bytes(tmp_path):
    image = tmp_path / 'native-evidence/pe/windows-runtime.cpio.gz'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'windows runtime')
    receipt = image.parent / 'retained-base-preparation.json'
    receipt.write_text(json.dumps({'os_capabilities': ['wine64', 'pe32']}))
    manifest = {'retained_base': {'windows_runtime': {'path': 'native-evidence/pe/windows-runtime.cpio.gz', **module.identity(image)}}}
    assert module.full_windows_base(manifest, tmp_path) == image
    receipt.write_text(json.dumps({'os_capabilities': ['wine64']}))
    with pytest.raises(ValueError, match='PE32'):
        module.full_windows_base(manifest, tmp_path)
    receipt.write_text(json.dumps({'os_capabilities': ['wine64', 'pe32']}))
    image.write_bytes(b'changed')
    with pytest.raises(ValueError, match='missing or changed'):
        module.full_windows_base(manifest, tmp_path)
    with pytest.raises(ValueError, match='full Windows runtime'):
        module.full_windows_base({}, tmp_path)


def test_firmware_inputs_exclude_qemu_nsis_bitmap_and_pass_kit_destination_guard(tmp_path):
    builder_spec = importlib.util.spec_from_file_location(
        'chatkit', Path(__file__).parents[1] / 'scripts/build_chat_offline_kit.py'
    )
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)

    firmware_dir = tmp_path / 'native-evidence/pe/firmware'
    firmware_dir.mkdir(parents=True)
    entries = []
    for name in ('bios-256k.bin', 'vgabios-stdvga.bin', 'kvmvapic.bin', 'qemu-nsis.bmp'):
        p = firmware_dir / name
        p.write_bytes(b'firmware-data')
        entries.append({'path': f'native-evidence/pe/firmware/{name}', **module.identity(p)})
    staged = module.firmware_inputs({'firmware': entries}, tmp_path)
    destinations = [item['destination'] for item in staged]
    assert 'native/qemu/share/qemu/qemu-nsis.bmp' not in destinations
    assert destinations == [
        'native/qemu/share/qemu/bios-256k.bin',
        'native/qemu/share/qemu/vgabios-stdvga.bin',
        'native/qemu/share/qemu/kvmvapic.bin',
    ]
    for dest in destinations:
        assert str(builder.destination(dest)) == dest
    with pytest.raises(ValueError, match='required QEMU runtime firmware'):
        module.firmware_inputs({'firmware': [entries[0]]}, tmp_path)

