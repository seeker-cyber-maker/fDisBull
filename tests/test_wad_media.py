"""Public WAD media routing using authored lumps only."""
import struct
from pathlib import Path
import pytest
from fdisbull.media import inspect_media, extract_media


def wad(lumps):
    body = bytearray(); directory = bytearray()
    for name, data in lumps:
        directory.extend(struct.pack('<II8s', 12 + len(body), len(data), name.encode().ljust(8, b'\0')))
        body.extend(data)
    return struct.pack('<4sII', b'PWAD', len(lumps), 12 + len(body)) + body + directory


def test_occurrences_remain_distinct_and_raw_export_preserves_authored_bytes(tmp_path):
    source = tmp_path / 'authored.wad'
    raw = wad([('CUSTOM', b'first authored lump'), ('CUSTOM', b'second authored lump')])
    source.write_bytes(raw)
    report = inspect_media(source, adapter='doom-wad')
    assert report['lump_count'] == 2 and report['duplicate_names'] == {'CUSTOM': 2}
    assert not report['input_executed']
    assert [m['id'] for m in report['members']] == ['lump:0', 'lump:1']
    with pytest.raises(ValueError, match='ambiguous'):
        extract_media(source, tmp_path / 'ambiguous', adapter='doom-wad', member='name:CUSTOM')
    assert not (tmp_path / 'ambiguous').exists()
    result = extract_media(source, tmp_path / 'out', adapter='doom-wad', member='all', wad_mode='raw')
    assert result['lump_count'] == 2
    assert any(p.read_bytes() == b'first authored lump' for p in (tmp_path / 'out').rglob('*.lmp'))
    assert any(p.read_bytes() == b'second authored lump' for p in (tmp_path / 'out').rglob('*.lmp'))
    assert source.read_bytes() == raw
    with pytest.raises(FileExistsError):
        extract_media(source, tmp_path / 'out', adapter='doom-wad', member='all')


def test_authored_patch_keeps_opaque_palette_255_separate_from_empty_pixels():
    from fdisbull.wad_codecs import decode_patch
    # One column, three rows; only row one is covered by the post.
    data = struct.pack('<HHhhI', 1, 3, 0, 0, 12) + bytes([1, 1, 0, 255, 0, 255])
    image = decode_patch(data)
    assert (image.width, image.height) == (1, 3)
    assert image.indices == bytes([0, 255, 0])
    assert image.opacity == bytes([0, 255, 0])


def test_authored_dmx_preserves_declared_samples_and_reports_playback_trim_separately():
    import io
    import wave
    from fdisbull.wad_codecs import decode_dmx, pcm_wav, WadDecodeError
    samples = bytes(range(64))
    metadata, decoded = decode_dmx(struct.pack('<HHI', 3, 11025, 64) + samples + b'X')
    assert decoded == samples
    assert metadata['trailing_bytes'] == 1 and metadata['dmx_playback_slice'] == [16, 48]
    with wave.open(io.BytesIO(pcm_wav(decoded, metadata['sample_rate'])), 'rb') as stream:
        assert stream.getnchannels() == stream.getsampwidth() == 1
        assert stream.getframerate() == 11025
        assert stream.readframes(64) == samples
    with pytest.raises(WadDecodeError, match='extent'):
        decode_dmx(struct.pack('<HHI', 3, 11025, 65) + samples)
