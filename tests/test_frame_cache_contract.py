"""Run the actual patched capture function with bounded source-cache fixtures.

This is a compiled source contract, not a native renderer integration test.
The separately authored retrace fixture exercises the real native path.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("patch", [
    "experimental/dosbox-x/headless-agent.patch",
    "experimental/dosbox-x/layers/headless-agent.patch",
])
def test_completed_source_cache_extent_and_pixel_conversion(tmp_path, patch, request):
    patch_file = ROOT / patch
    if not patch_file.is_file():
        message = "Native source patches are separate from tool-only source archives"
        if request.config.getoption('--require-native', default=False):
            pytest.fail(message + "; run required acceptance from the repository")
        pytest.skip(message)
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("C++ compiler required for extracted capture-function check")
    lines = patch_file.read_text().splitlines()
    start = lines.index("+static void CaptureCompletedAgentFrame()")
    end = lines.index("+}", start) + 1
    assert all(line.startswith("+") for line in lines[start:end])
    capture = "\n".join(line[1:] for line in lines[start:end])
    source = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

struct FrameSnapshot {
    std::vector<std::uint8_t> rgba;
    std::uint32_t width = 0, height = 0, source_bpp = 0;
    std::uint64_t frame_id = 0, mode_id = 0, captured_ticks = 0;
    bool double_width = false, double_height = false;
};
struct PaletteColor { std::uint8_t red, green, blue; };
struct Render {
    struct { std::size_t width, height; unsigned int bpp; bool dblw, dblh; } src;
    struct {
        std::size_t inLine, outLine, cachePitch;
        std::uint8_t* cacheRead;
    } scale;
    struct { PaletteColor rgb[256]; } pal;
} render;
std::uint8_t cache[128];
std::uint8_t* scalerSourceCacheBuffer = cache;
unsigned int scalerSourceCacheBufferSize = sizeof(cache);
const std::size_t max_agent_frame_bytes = 16u * 1024u * 1024u;
bool agent_frame_capture_enabled = true, agent_frame_valid = false;
bool agent_frame_step_armed = false, agent_frame_step_completed = false;
std::uint64_t agent_frame_sequence = 0, agent_mode_sequence = 9, PIC_Ticks = 41;
FrameSnapshot agent_frame;

void reset_source() {
    render = Render();
    render.src.width = 2; render.src.height = 2; render.src.bpp = 8;
    render.scale.cachePitch = 4;
    render.scale.cacheRead = cache + 8;
    render.pal.rgb[1] = {12, 34, 56};
    render.pal.rgb[2] = {78, 90, 123};
    std::memset(cache, 0, sizeof(cache));
    cache[0] = 1; cache[1] = 2; cache[4] = 2; cache[5] = 1;
    scalerSourceCacheBuffer = cache;
    scalerSourceCacheBufferSize = sizeof(cache);
    agent_frame_capture_enabled = true;
    agent_frame_valid = false;
    agent_frame_step_armed = false;
    agent_frame_step_completed = false;
    agent_frame = FrameSnapshot();
}
void pixel(std::size_t n, unsigned r, unsigned g, unsigned b) {
    assert(agent_frame.rgba.at(n * 4) == r);
    assert(agent_frame.rgba.at(n * 4 + 1) == g);
    assert(agent_frame.rgba.at(n * 4 + 2) == b);
    assert(agent_frame.rgba.at(n * 4 + 3) == 255);
}
''' + capture + r'''

int main() {
    // A simple linear scaler can complete the source cache while leaving both
    // counters at zero. This is the discriminating old-guard regression.
    reset_source();
    CaptureCompletedAgentFrame();
    assert(agent_frame_valid);
    assert(agent_frame.frame_id == 1 && agent_frame.mode_id == 9);
    assert(agent_frame.captured_ticks == 41);
    assert(agent_frame.width == 2 && agent_frame.height == 2);
    assert(agent_frame.source_bpp == 8 && agent_frame.rgba.size() == 16);
    pixel(0, 12, 34, 56); pixel(1, 78, 90, 123);
    pixel(2, 78, 90, 123); pixel(3, 12, 34, 56);

    // Random simple scalers advance output rows; that is not input completion.
    // Unchanged rows may advance both counters. Both complete extents work.
    for (unsigned variant = 0; variant != 2; ++variant) {
        render.scale.inLine = variant ? 2 : 0;
        render.scale.outLine = 2;
        ++PIC_Ticks;
        CaptureCompletedAgentFrame();
        assert(agent_frame_valid && agent_frame.frame_id == 2 + variant);
        assert(agent_frame.captured_ticks == PIC_Ticks);
    }

    // Palette-only changes must refresh pixels even with the same source bytes.
    render.pal.rgb[1] = {200, 100, 50};
    CaptureCompletedAgentFrame();
    assert(agent_frame.frame_id == 4);
    pixel(0, 200, 100, 50);

    // A partial cursor, cursor beyond the declared frame, or unrelated cursor
    // must never promote source bytes to a new frame, even if inLine says full.
    std::uint8_t unrelated[8] = {};
    const auto previous = agent_frame.rgba;
    for (auto cursor : {cache, cache + 4, cache + 9, unrelated,
                       static_cast<std::uint8_t*>(nullptr)}) {
        render.scale.cacheRead = cursor;
        CaptureCompletedAgentFrame();
        assert(agent_frame.frame_id == 4 && agent_frame.rgba == previous);
    }

    // A fresh invalidated epoch cannot use a partial cache to become valid.
    reset_source();
    render.scale.inLine = 2;
    render.scale.cacheRead = cache + 4;
    CaptureCompletedAgentFrame();
    assert(!agent_frame_valid);

    // The complete extent may equal the full allocation: one-past-end is valid.
    reset_source();
    render.scale.cachePitch = 64;
    render.scale.cacheRead = cache + sizeof(cache);
    cache[64] = 2; cache[65] = 1;
    CaptureCompletedAgentFrame();
    assert(agent_frame_valid);
    pixel(2, 78, 90, 123);

    // Reject dimensions/pitch/format before computing an out-of-bounds extent.
    for (unsigned invalid = 0; invalid != 5; ++invalid) {
        reset_source();
        if (invalid == 0) render.scale.cachePitch = 65;
        if (invalid == 1) render.scale.cachePitch = 1;
        if (invalid == 2) render.src.bpp = 24;
        if (invalid == 3) render.src.width = max_agent_frame_bytes;
        if (invalid == 4) render.src.height = max_agent_frame_bytes;
        const auto sequence = agent_frame_sequence;
        CaptureCompletedAgentFrame();
        assert(!agent_frame_valid && agent_frame_sequence == sequence);
    }

    // Exercise the existing color conversions under a complete, bounded cache.
    for (const unsigned bpp : {15u, 16u, 32u}) {
        reset_source();
        render.src.width = 1; render.src.height = 1; render.src.bpp = bpp;
        render.scale.cachePitch = bpp == 32 ? 4 : 2;
        render.scale.cacheRead = cache + render.scale.cachePitch;
        if (bpp == 32) {
            const std::uint32_t color = 0x123456;
            std::memcpy(cache, &color, sizeof(color));
        } else {
            const std::uint16_t color = bpp == 15 ? 0x7c1f : 0xf81f;
            std::memcpy(cache, &color, sizeof(color));
        }
        CaptureCompletedAgentFrame();
        assert(agent_frame_valid && agent_frame.source_bpp == bpp);
        if (bpp == 32) pixel(0, 0x12, 0x34, 0x56);
        else pixel(0, 255, 0, 255);
    }

    for (unsigned disabled = 0; disabled != 4; ++disabled) {
        reset_source();
        if (disabled == 0) agent_frame_capture_enabled = false;
        if (disabled == 1) scalerSourceCacheBuffer = nullptr;
        if (disabled == 2) render.src.width = 0;
        if (disabled == 3) render.src.height = 0;
        const auto sequence = agent_frame_sequence;
        CaptureCompletedAgentFrame();
        assert(!agent_frame_valid && agent_frame_sequence == sequence);
    }

    // A requested frame step is signalled only after complete source pixels
    // exist. A partial cache must not release a waiter for a real frame.
    reset_source();
    agent_frame_step_armed = true;
    render.scale.cacheRead = cache + 4;
    const auto before_step = agent_frame_sequence;
    CaptureCompletedAgentFrame();
    assert(!agent_frame_step_completed && agent_frame_sequence == before_step);
    render.scale.cacheRead = cache + 8;
    CaptureCompletedAgentFrame();
    assert(agent_frame_valid && agent_frame_step_completed);
    assert(agent_frame_sequence == before_step + 1);
}
'''
    cpp = tmp_path / "frame_cache_contract.cpp"
    cpp.write_text(source)
    binary = tmp_path / "frame_cache_contract"
    subprocess.run([
        compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
        str(cpp), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
