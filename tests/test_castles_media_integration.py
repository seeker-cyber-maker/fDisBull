"""Authored public format/intake contracts; no target game payloads."""
import hashlib
import json
import struct

import pytest

from fdisbull.cli import main, respond
from fdisbull.format_registry import format_catalog, identify_file
from fdisbull.intake import intake_inventory


def authored_mve_header(chunk_bytes=0, chunk_type=2):
    # Published Interplay container signature/constants, not a movie payload.
    return b'Interplay MVE File\x1a\0' + struct.pack('<3H2H', 0x1a, 0x100, 0x1133,
                                                    chunk_bytes, chunk_type)


def test_mve_header_catalog_and_independent_decode_boundary(tmp_path):
    source = tmp_path / 'not-a-suffix'
    source.write_bytes(authored_mve_header())
    result = identify_file(source)['identification']
    assert result['format_id'] == 'interplay-mve'
    assert result['recognized'] and result['header_valid']
    assert result['full_decode'] is False and result['native_runtime_tested'] is False
    assert any(m['module_id'] == 'mve' for m in result['decoder_modules'])
    assert result['metadata']['header_bytes'] == 26
    assert result['metadata']['first_chunk_type'] == 2


@pytest.mark.parametrize('data', [authored_mve_header()[:22],
    authored_mve_header(chunk_bytes=1), authored_mve_header(chunk_type=99),
    b'Interplay MVE File\x1a\0' + bytes(10)])
def test_mve_recognized_invalid_is_not_a_codec_success(tmp_path, data):
    source = tmp_path / 'bad.mve'
    source.write_bytes(data)
    result = identify_file(source)['identification']
    assert result['format_id'] == 'interplay-mve'
    assert result['recognized'] and not result['header_valid']
    assert result['full_decode'] is False


def test_headerless_slb_stays_explicit_context_candidate(tmp_path):
    root = tmp_path / 'castles2-original'
    root.mkdir()
    source = root / 'SND123.SLB'
    source.write_bytes(bytes(24))
    result = intake_inventory([root], catalog_path=tmp_path / 'formats.sqlite')
    assert result['complete']
    entry = result['files'][0]
    assert not entry['identification']['recognized']
    candidate = next(h for h in entry['candidate_profiles']
                     if h['format_id'] == 'context-castles2-slb')
    assert candidate['qualification'] == 'context-candidate-only'
    assert {m['module_id'] for m in candidate['decoder_modules']} == {
        'format-headers', 'castles2-slb', 'castles2-slb-playback'}
    assert result['recovery_queue']


def test_new_media_adapters_are_projectless_and_discoverable(capsys):
    result = respond({'method': 'media-modules'}, default_project='/missing.fdb')
    assert result['ok']
    modules = {m['name'] for m in result['result']['modules']}
    assert {'mve', 'castles2-slb', 'castles2-slb-playback'} <= modules
    assert 'mve-frame' in respond({'method': 'help'})['result']['methods']
    assert main(['media-inspect', '/missing', '--adapter', 'mve']) == 1
    response = json.loads(capsys.readouterr().out)
    assert not response['ok']


def authored_slb(selector=11):
    # Two variants share a key; original hash starts at slot1, then reaches slot2.
    pcm = bytes([0, 64, 128, 255]) * 3
    return (pcm + bytes(12) + struct.pack('<III', 1, 0, 8)
            + struct.pack('<III', 1, 8, 4) + struct.pack('<III', selector, 3, 12))


def test_slb_selected_export_keeps_pcm_and_separate_device_timing(tmp_path, capsys):
    import wave
    source = tmp_path / 'library'
    source.write_bytes(authored_slb())
    original = source.read_bytes()
    output = tmp_path / 'selected'
    assert main(['media-decode', str(source), str(output), '--adapter', 'castles2-slb',
                 '--slot', '2', '--playback-profile', 'castles2-ail-sb-mono-v1']) == 0
    result = json.loads(capsys.readouterr().out)['result']
    assert int(result['selection']['slot'], 0) == 2
    assert result['selection']['time_constant'] == 166
    assert result['selection']['ideal_device_rate'] == {'numerator': 100000, 'denominator': 9}
    assert not result['native_runtime_tested'] and not result['executables_modified']
    with wave.open(str(output / 'samples.wav'), 'rb') as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (1, 1, 11111)
        assert reader.getnframes() == 4
        assert reader.readframes(4) == bytes([0, 64, 128, 255])
    persisted = json.loads((output / 'decode-manifest.json').read_text())
    assert persisted['selection']['slot'] == 2
    assert persisted['source'] == result['source']
    assert persisted['outputs'] == result['outputs']
    assert source.read_bytes() == original
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / 'samples.wav').stat().st_mode & 0o777 == 0o600
    duplicate = respond({'method': 'media-decode', 'params': dict(path=str(source),
        output=str(output), adapter='castles2-slb', slot=2,
        playback_profile='castles2-ail-sb-mono-v1')})
    assert not duplicate['ok']


@pytest.mark.parametrize('options', [dict(slot=0), dict(slot=True), dict(slot=-1),
    dict(slot=3), dict(slot=2), dict(slot=2, playback_profile='unknown'),
    dict(slot=2, playback_profile='castles2-ail-sb-mono-v1', sample_rate=11000),
    dict(slot=2, playback_profile='castles2-ail-sb-mono-v1', channels=1),
    dict(slot=2, playback_profile='castles2-ail-sb-mono-v1', max_output_bytes=47)])
def test_slb_export_refuses_unbound_or_ambiguous_adapters(tmp_path, options):
    source = tmp_path / 'library'
    source.write_bytes(authored_slb())
    output = tmp_path / 'refused'
    result = respond({'method': 'media-decode', 'params': dict(path=str(source),
        output=str(output), adapter='castles2-slb', **options)})
    assert not result['ok']
    assert not output.exists()


def test_slb_playback_inspector_does_not_claim_current_native_run(tmp_path):
    source = tmp_path / 'library'
    source.write_bytes(authored_slb(22))
    result = respond({'method': 'media-inspect', 'params': dict(path=str(source),
        adapter='castles2-slb-playback')}, default_project='/missing.fdb')
    assert result['ok']
    playback = result['result']
    assert playback['time_constant'] == 211
    assert playback['ideal_device_rate'] == {'numerator': 200000, 'denominator': 9}
    assert playback['wave_sample_rate'] == 22222
    assert not playback['native_runtime_tested']
    source.write_bytes(authored_slb(5))
    result = respond({'method': 'media-inspect', 'params': dict(path=str(source),
        adapter='castles2-slb-playback')})
    assert not result['ok']
