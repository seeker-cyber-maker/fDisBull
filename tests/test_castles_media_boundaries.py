"""Independent public-boundary checks for authored Castles resource fixtures."""
from pathlib import Path
import json
import struct
import wave

import pytest

from fdisbull.castles2_audio import bind_slb_playback, decode_slb
from fdisbull.castles2_media import decode_slb_media
from fdisbull.cli import main, respond
from fdisbull.format_registry import format_catalog, identify_file
from fdisbull.intake import intake_inventory


PROFILE = 'castles2-ail-sb-mono-v1'


def library(selector=11):
    # Probe order for key2 is slot1 (146mod5), then slot2, then empty slot3.
    # Directory order differs from payload order, so preserving slot IDs matters.
    samples = b'\x00\x80\xff' + b'\x20\x40\x60\x80\xa0'
    rows = [(0, 0, 0), (2, 3, 5), (2, 0, 3), (0, 0, 0), (0, 0, 0)]
    return samples + b''.join(struct.pack('<III', *r) for r in rows) + struct.pack('<III', selector, 5, len(samples))


def private(tmp_path):
    root = tmp_path / 'owned'
    root.mkdir(mode=0o700)
    return root


def test_structural_slot_order_is_distinct_from_payload_and_hash_order(tmp_path):
    source = tmp_path / 'headerless'
    source.write_bytes(library())
    result = respond({'method': 'media-inspect', 'params': {
        'path': str(source), 'adapter': 'castles2-slb'}})
    assert result['ok']
    report = result['result']
    assert not report['full_audio_decode'] and not report['native_runtime_tested']
    decoded = decode_slb(source.read_bytes())
    assert decoded.lookup_slots(2) == (1, 2)
    assert decoded.sample(1) == bytes([32, 64, 96, 128, 160])
    assert decoded.sample(2) == bytes([0, 128, 255])


@pytest.mark.parametrize('selector,constant,rate,num,den', [
    (11, 166, 11111, 100000, 9), (22, 211, 22222, 200000, 9),
])
def test_wave_integer_clock_does_not_overwrite_exact_device_fraction(tmp_path, selector, constant, rate, num, den):
    root = private(tmp_path)
    source = root / 'source'
    source.write_bytes(library(selector))
    result = decode_slb_media(source, root / 'out', slot=1, playback_profile=PROFILE)
    selection = result['selection']
    assert selection['time_constant'] == constant
    assert selection['ideal_device_rate'] == {'numerator': num, 'denominator': den}
    assert selection['wave_sample_rate'] == rate
    assert selection['ideal_device_duration_seconds'] != selection['wave_duration_seconds']
    with wave.open(str(root / 'out/samples.wav')) as wav:
        assert wav.getframerate() == rate
        assert wav.readframes(5) == bytes([32, 64, 96, 128, 160])
    assert not selection['native_runtime_tested']
    assert not result['native_runtime_tested']


@pytest.mark.parametrize('selector', [0, 1, 10, 12, 21, 23, 11025, 22050, 0xffffffff])
def test_opaque_footer_can_inspect_but_cannot_acquire_a_guessed_rate(tmp_path, selector):
    root = private(tmp_path)
    source = root / 'source'
    source.write_bytes(library(selector))
    result = respond({'method': 'media-inspect', 'params': {
        'path': str(source), 'adapter': 'castles2-slb'}})
    assert result['ok']
    rejected = respond({'method': 'media-inspect', 'params': {
        'path': str(source), 'adapter': 'castles2-slb-playback'}})
    assert not rejected['ok']
    with pytest.raises(ValueError, match='selector'):
        decode_slb_media(source, root / 'out', slot=1, playback_profile=PROFILE)
    assert not (root / 'out').exists()


@pytest.mark.parametrize('options', [dict(sample_rate=0), dict(channels=False),
    dict(index=0), dict(palette_path='other.pic'), dict(palette_index=1),
    dict(palette_policy='replicate6'), dict(max_output_bytes=1024),
    dict(max_output_bytes=64.0), dict(max_output_bytes=True)])
def test_ambiguous_adapters_and_manifest_budget_refuse_without_publication(tmp_path, options):
    root = private(tmp_path)
    source = root / 'source'
    source.write_bytes(library())
    with pytest.raises(ValueError):
        decode_slb_media(source, root / 'out', slot=1, playback_profile=PROFILE, **options)
    assert not (root / 'out').exists()
    assert source.read_bytes() == library()


def test_source_change_refuses_selected_wav_publication(tmp_path, monkeypatch):
    from fdisbull import castles2_media
    root = private(tmp_path)
    source = root / 'source'
    source.write_bytes(library())
    calls = []
    original = castles2_media._snapshot
    def snapshot(path, limit):
        data = original(path, limit)
        calls.append(None)
        return data if len(calls) == 1 else data + b'changed'
    monkeypatch.setattr(castles2_media, '_snapshot', snapshot)
    with pytest.raises(ValueError, match='Source changed'):
        decode_slb_media(source, root / 'out', slot=1, playback_profile=PROFILE)
    assert not (root / 'out').exists()


def test_export_refuses_source_link_or_git_parent(tmp_path):
    root = private(tmp_path)
    source = root / 'source'
    source.write_bytes(library())
    alias = root / 'alias'
    alias.symlink_to(source)
    with pytest.raises(ValueError, match='symlink'):
        decode_slb_media(alias, root / 'out', slot=1, playback_profile=PROFILE)
    (root / '.git').write_text('gitdir: /elsewhere\n')
    with pytest.raises(ValueError):
        decode_slb_media(source, root / 'out', slot=1, playback_profile=PROFILE)
    assert not (root / 'out').exists()


def test_header_recognition_does_not_claim_old_codec_or_media_success(tmp_path):
    source = tmp_path / 'unknown-codec.mve'
    source.write_bytes(b'Interplay MVE File\x1a\0' + struct.pack('<3H', 0x1a, 0x100, 0x1133)
                      + struct.pack('<HH', 4, 2) + struct.pack('<HBB', 0, 17, 0))
    header = identify_file(source)['identification']
    assert header['format_id'] == 'interplay-mve' and header['header_valid']
    assert not header['full_decode']
    full = respond({'method': 'media-inspect', 'params': {'path': str(source), 'adapter': 'mve'}})
    assert not full['ok']


def test_context_only_slb_stays_in_recovery_after_single_and_batch_intake(tmp_path):
    root = tmp_path / 'castles2'
    root.mkdir()
    source = root / 'SND001.SLB'
    source.write_bytes(library())
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'plain.txt').write_text('Authored text')
    catalog = tmp_path / 'catalog.sqlite'
    single = intake_inventory([root], catalog_path=catalog)
    batch = intake_inventory([root, other], catalog_path=catalog)
    assert single['complete'] and batch['complete']
    assert single['files'][0]['identification'] == batch['files'][0]['identification']
    assert single['files'][0]['candidate_profiles'] == batch['files'][0]['candidate_profiles']
    assert any(r['reason'] == 'unknown-format' for r in single['recovery_queue'])
    db = format_catalog(catalog_path=catalog)
    modules = {r['module_id']: r for r in db['modules']}
    assert modules['mve']['implemented']
    assert modules['castles2-slb-playback']['implemented']
    assert all('native' not in c for c in modules['castles2-slb']['capabilities'])


def test_cli_decimal_slot_keeps_original_slot_identity(tmp_path, capsys):
    root = private(tmp_path)
    source = root / 'source'
    source.write_bytes(library())
    output = root / 'out'
    assert main(['media-decode', str(source), str(output), '--adapter', 'castles2-slb',
                 '--slot', '1', '--playback-profile', PROFILE]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['ok']
    persisted = json.loads((output / 'decode-manifest.json').read_text())
    assert persisted['selection']['slot'] == 1
    assert persisted['selection']['samples'] == 5
    assert not persisted['native_runtime_tested']
