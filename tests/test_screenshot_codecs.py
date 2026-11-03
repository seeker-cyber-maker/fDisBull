"""Wire bounds, exact compiled encoders and optional real native screenshot path."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.screenshot_codecs import decode_screenshot, validate_encoding


ROOT = Path(__file__).resolve().parents[1]


def wire(payload, **metadata):
    return dict(width=2, height=2, format='png', png_base64=base64.b64encode(payload).decode(),
                sha256=hashlib.sha256(payload).hexdigest(), **metadata)


def png(image):
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def raw_wire(pixels=bytes([12, 34, 56, 255]) * 4):
    zstd = pytest.importorskip('zstandard')
    data = zstd.ZstdCompressor(level=1).compress(pixels)
    return dict(format='rgba-zstd', encoding='rgba-zstd', width=2, height=2,
                frame_id=19, mode_id=4, captured_ticks=52, source='last_completed_guest_frame',
                pixel_format='RGBA8', stride=8, uncompressed_bytes=16,
                raw_sha256=hashlib.sha256(pixels).hexdigest(),
                sha256=hashlib.sha256(data).hexdigest(), data_base64=base64.b64encode(data).decode())


def test_indexed_png_stays_indexed_and_exact():
    image = Image.new('P', (2, 2))
    image.putpalette([12, 34, 56] + [0] * 765)
    payload = png(image)
    reply = wire(payload, encoding='png-indexed', frame_id=19)
    data, metadata = decode_screenshot(reply)
    assert data == payload and metadata['frame_id'] == 19 and metadata['encoding'] == 'png-indexed'
    assert 'png_base64' in reply and 'png_base64' not in metadata
    with Image.open(io.BytesIO(data)) as restored:
        assert restored.mode == 'P' and restored.convert('RGB').getpixel((0, 0)) == (12, 34, 56)


def test_raw_zstd_pixel_identity_and_distinct_artifact_hash():
    reply = raw_wire()
    data, metadata = decode_screenshot(reply)
    with Image.open(io.BytesIO(data)) as restored:
        assert restored.convert('RGBA').tobytes() == bytes([12, 34, 56, 255]) * 4
    assert metadata['sha256'] == hashlib.sha256(data).hexdigest()
    assert metadata['sha256'] != reply['sha256']
    assert metadata['transport']['sha256'] == reply['sha256']
    assert metadata['transport']['raw_sha256'] == reply['raw_sha256']
    assert metadata['transport']['compressed_bytes'] == len(base64.b64decode(reply['data_base64']))
    assert metadata['format'] == 'png' and metadata['encoding'] == 'png'
    for field in ('frame_id', 'mode_id', 'captured_ticks', 'source'):
        assert metadata[field] == reply[field]
    assert 'data_base64' not in metadata


@pytest.mark.parametrize('changes,message', [
    ({'width': True}, 'dimensions'), ({'width': 0}, 'dimensions'),
    ({'width': 4096, 'height': 4096}, 'dimensions'),
    ({'stride': 7}, 'layout'), ({'stride': True}, 'layout'),
    ({'uncompressed_bytes': 15}, 'layout'), ({'pixel_format': 'BGRA8'}, 'layout'),
    ({'raw_sha256': '0' * 64}, 'pixel identity'), ({'sha256': '0' * 64}, 'hash'),
    ({'data_base64': 'not base64!'}, 'payload'),
])
def test_raw_wire_rejects_bad_dimensions_layout_and_hash(changes, message):
    reply = raw_wire()
    reply.update(changes)
    with pytest.raises(DebuggerError, match=message):
        decode_screenshot(reply)


@pytest.mark.parametrize('kind', ['trailing', 'wrong_size', 'unknown_size'])
def test_raw_wire_rejects_trailing_and_unbounded_frames(kind):
    zstd = pytest.importorskip('zstandard')
    reply = raw_wire()
    data = base64.b64decode(reply['data_base64'])
    if kind == 'trailing':
        data += b'unexpected'
    else:
        data = zstd.ZstdCompressor(write_content_size=kind != 'unknown_size').compress(
            bytes(1024) if kind == 'wrong_size' else bytes(16))
    reply.update(data_base64=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
    with pytest.raises(DebuggerError, match='Zstandard'):
        decode_screenshot(reply)


def test_png_signature_hash_and_dimensions():
    reply = wire(png(Image.new('RGBA', (2, 2))))
    data, metadata = decode_screenshot(reply)
    assert metadata['sha256'] == hashlib.sha256(data).hexdigest()
    with pytest.raises(DebuggerError, match='hash'):
        decode_screenshot({**reply, 'sha256': '0' * 64})
    with pytest.raises(DebuggerError, match='dimensions differ'):
        decode_screenshot({**reply, 'width': 3})


def test_codec_negotiation_requires_capability_and_optional_decoder(monkeypatch):
    validate_encoding('png', {})  # Old backends keep the existing default.
    with pytest.raises(DebuggerError, match='advertise'):
        validate_encoding('png-indexed', {})
    with pytest.raises(ValueError, match='encoding'):
        validate_encoding('jpeg', {})
    import builtins
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == 'zstandard':
            raise ImportError('test missing optional dependency')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', missing)
    with pytest.raises(DebuggerError, match='optional'):
        validate_encoding('rgba-zstd', {'video': {'screenshot_encodings': ['rgba-zstd']}})


def test_public_capture_validates_encoding_without_a_live_rpc():
    from fdisbull.debugger import DebugSession

    class CaptureAdapter:
        screenshot = DebugSession.screenshot

    adapter = CaptureAdapter()
    with pytest.raises(ValueError, match='encoding'):
        adapter.screenshot(encoding='jpeg')
    with pytest.raises(DebuggerError, match='advertise'):
        adapter.screenshot(encoding='png-indexed')


@pytest.fixture(params=['experimental/dosbox-x/headless-agent.patch',
                        'experimental/dosbox-x/layers/headless-agent.patch'])
def compiled_encoder(request, tmp_path):
    compiler = shutil.which('c++')
    if not compiler:
        pytest.skip('C++ compiler required for actual source encoder check')
    path = ROOT / request.param
    if not path.is_file():
        pytest.skip('Native source patches are separate from tool-only archives')
    lines = path.read_text().splitlines()
    start = lines.index('+static void PngU32(std::vector<std::uint8_t>* out, std::uint32_t value)')
    end = lines.index('+static JsonValue SignedNumber(const std::int32_t value)', start)
    assert all(line.startswith('+') for line in lines[start:end])
    implementation = '\n'.join(line[1:] for line in lines[start:end])
    prefix = r'''
#include <cstdint>
#include <vector>
#include <string>
#include <unordered_map>
#include <fstream>
#include <cassert>
#include <zlib.h>
#if defined(C_DOSBOX_AGENT_ZSTD)
#include <zstd.h>
#endif
struct FrameSnapshot {
    std::uint32_t width=0, height=0;
    std::vector<std::uint8_t> rgba;
};
'''
    suffix = r'''
int main(int argc, char** argv) {
    assert(argc==2);
    std::string root=argv[1];
    FrameSnapshot frame; frame.height=1;
    std::vector<std::uint8_t> encoded;
    std::string fallback;
    std::uint32_t colors=0;
    assert(!EncodeFramePng(frame,&encoded));
    assert(!EncodeFrameIndexedPng(frame,&encoded,&colors,&fallback));
    for (unsigned count : {1u,256u,257u}) {
        frame.width=count; frame.rgba.clear();
        for(unsigned n=0;n<count;++n) {
            frame.rgba.push_back(n&255); frame.rgba.push_back((n>>8)&255);
            frame.rgba.push_back(53); frame.rgba.push_back(255);
        }
        assert(EncodeFrameIndexedPng(frame,&encoded,&colors,&fallback));
        assert((count<=256 && colors==count && fallback.empty()) ||
               (count>256 && colors==0 && fallback=="more_than_256_colors"));
        std::ofstream out(root+"/colors-"+std::to_string(count)+".png",std::ios::binary);
        out.write(reinterpret_cast<const char*>(encoded.data()),encoded.size());
    }
    frame.width=1; frame.rgba={12,34,56,127};
    assert(EncodeFrameIndexedPng(frame,&encoded,&colors,&fallback));
    assert(colors==0 && fallback=="nonopaque_frame");
    std::ofstream alpha(root+"/alpha.png",std::ios::binary);
    alpha.write(reinterpret_cast<const char*>(encoded.data()),encoded.size());
    frame.rgba={1,2,3,255};
    assert(EncodeFrameIndexedPng(frame,&encoded,&colors,&fallback));
    frame.rgba={3,2,1,255}; // Same index, different palette on the next frame.
    assert(EncodeFrameIndexedPng(frame,&encoded,&colors,&fallback));
    std::ofstream changed(root+"/palette-change.png",std::ios::binary);
    changed.write(reinterpret_cast<const char*>(encoded.data()),encoded.size());
#if defined(C_DOSBOX_AGENT_ZSTD)
    assert(EncodeFrameZstd(frame,&encoded));
    std::vector<std::uint8_t> restored(4);
    assert(ZSTD_decompress(restored.data(),restored.size(),encoded.data(),encoded.size())==4);
    assert(restored==frame.rgba);
#endif
    frame.rgba.pop_back();
    assert(!EncodeFrameIndexedPng(frame,&encoded,&colors,&fallback));
#if defined(C_DOSBOX_AGENT_ZSTD)
    assert(!EncodeFrameZstd(frame,&encoded));
#endif
}
'''
    source = tmp_path / 'encoder.cpp'
    source.write_text(prefix + implementation + suffix)
    command = [compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror', str(source), '-lz']
    zstd_flags = subprocess.run(['pkg-config', '--cflags', '--libs', 'libzstd'], capture_output=True, text=True) if shutil.which('pkg-config') else None
    for use_zstd in ([False, True] if zstd_flags and zstd_flags.returncode == 0 else [False]):
        binary = tmp_path / ('encoder-zstd' if use_zstd else 'encoder')
        flags = ['-DC_DOSBOX_AGENT_ZSTD=1', *shlex.split(zstd_flags.stdout)] if use_zstd else []
        subprocess.run([*command, *flags, '-o', str(binary)], check=True, capture_output=True, text=True)
        subprocess.run([str(binary), str(tmp_path)], check=True, capture_output=True, text=True)
    return tmp_path


def test_compiled_palette_boundaries_alpha_fallback_and_palette_refresh(compiled_encoder):
    for count in (1, 256, 257):
        with Image.open(compiled_encoder / f'colors-{count}.png') as image:
            assert image.mode == ('P' if count <= 256 else 'RGBA')
            assert image.convert('RGBA').tobytes() == bytes(channel for n in range(count) for channel in (n & 255, n >> 8, 53, 255))
    with Image.open(compiled_encoder / 'alpha.png') as image:
        assert image.convert('RGBA').getpixel((0, 0)) == (12, 34, 56, 127)
    with Image.open(compiled_encoder / 'palette-change.png') as image:
        assert image.convert('RGBA').getpixel((0, 0)) == (3, 2, 1, 255)


def test_real_codec_rpc_and_persisted_screenshot_artifacts(tmp_path):
    executable = os.environ.get('FDISBULL_DOSBOX')
    if not executable:
        pytest.skip('Set FDISBULL_DOSBOX for real native codec path')
    target = tmp_path / 'SCREEN.COM'
    target.write_bytes(bytes.fromhex('b81300cd10ebfe'))
    original = target.read_bytes()
    database = tmp_path / 'screen.fdb'
    artifacts = []
    with Project.create(database, target, image='com') as project:
        with project.debugger(executable, tmp_path) as debug:
            encodings = debug.rpc.capabilities['video'].get('screenshot_encodings', [])
            assert 'png-indexed' in encodings
            debug.run(guest_ms=80, timeout_ms=5000, fast_forward=True)
            before = debug.registers()
            baseline = debug.call('video.screenshot')
            expected, _ = decode_screenshot(baseline)
            with Image.open(io.BytesIO(expected)) as image:
                pixels = image.convert('RGBA').tobytes()
            for encoding in encodings:
                reply = debug.call('video.screenshot', {'encoding': encoding, 'measure': True})
                assert type(reply['encode_us']) is int and reply['encode_us'] >= 0
                assert {k: reply[k] for k in ('frame_id', 'mode_id', 'captured_ticks')} == {k: baseline[k] for k in ('frame_id', 'mode_id', 'captured_ticks')}
                encoded, _ = decode_screenshot(reply)
                with Image.open(io.BytesIO(encoded)) as image:
                    assert image.convert('RGBA').tobytes() == pixels
                frame = debug.screenshot(encoding + '.png', hooks=False, encoding=encoding)
                artifacts.append(frame)
                path = tmp_path / (encoding + '.png')
                project.debug_export(frame['artifact'], path)
                with Image.open(path) as image:
                    assert image.convert('RGBA').tobytes() == pixels
            with pytest.raises(DebuggerError):
                debug.call('video.screenshot', {'encoding': 'jpeg'})
            with pytest.raises(DebuggerError):
                debug.call('video.screenshot', {'encoding': 'png', 'measure': 'yes'})
            assert debug.registers() == before
    with Project(database) as reopened:
        for frame in artifacts:
            output = tmp_path / ('reopened-' + frame['name'])
            reopened.debug_export(frame['artifact'], output)
            assert hashlib.sha256(output.read_bytes()).hexdigest() == frame['sha256']
    assert target.read_bytes() == original
