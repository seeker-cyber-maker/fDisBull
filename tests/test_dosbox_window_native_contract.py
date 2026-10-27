"""Compile an extracted window guard against SDL stubs, not a native GUI test."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('patch', [
    'experimental/dosbox-x/headless-agent.patch',
    'experimental/dosbox-x/layers/headless-agent.patch',
])
def test_native_window_readiness_guard_with_sdl_stubs(tmp_path, patch):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('C++ compiler required for isolated source guard check')
    lines = (ROOT / patch).read_text().splitlines()
    start = lines.index('+bool AGENT_ValidateWindow(std::string* error)')
    end = lines.index('+}', start) + 1
    assert all(line.startswith('+') for line in lines[start:end])
    guard = '\n'.join(line[1:] for line in lines[start:end])
    assert any('+    if (!AGENT_ValidateWindow(&window_error))' in line for line in lines)
    source = r'''
#include <string>
#include <cstring>
#include <cassert>
#define C_SDL2 1
#define SDL_INIT_VIDEO 1
#define SDL_WINDOW_SHOWN 2
#define SDL_WINDOW_HIDDEN 4
#define SDL_WINDOW_MINIMIZED 8
struct Window { unsigned flags; };
struct { Window* window; } sdl;
bool session=true, headless=false, initialized=true;
const char* driver="x11";
bool AGENT_IsSession() { return session; }
bool AGENT_IsHeadless() { return headless; }
unsigned SDL_WasInit(unsigned) { return initialized ? SDL_INIT_VIDEO : 0; }
const char* SDL_GetCurrentVideoDriver() { return driver; }
unsigned SDL_GetWindowFlags(Window* w) { return w->flags; }
''' + guard + r'''
int main() {
    std::string error;
    Window visible = { SDL_WINDOW_SHOWN };
    Window hidden = { SDL_WINDOW_HIDDEN };
    Window minimized = { SDL_WINDOW_SHOWN | SDL_WINDOW_MINIMIZED };
    sdl.window = &visible;
    assert(AGENT_ValidateWindow(&error));
    driver = "offscreen"; assert(!AGENT_ValidateWindow(&error));
    driver = "dummy"; assert(!AGENT_ValidateWindow(&error));
    driver = nullptr; assert(!AGENT_ValidateWindow(&error));
    driver = ""; assert(!AGENT_ValidateWindow(&error));
    driver = "x11"; sdl.window = nullptr; assert(!AGENT_ValidateWindow(&error));
    sdl.window = &hidden; assert(!AGENT_ValidateWindow(&error));
    sdl.window = &minimized; assert(!AGENT_ValidateWindow(&error));
    sdl.window = &visible; initialized = false; assert(!AGENT_ValidateWindow(&error));
    headless = true; assert(AGENT_ValidateWindow(&error));
}
'''
    file = tmp_path/'window_guard.cpp'
    file.write_text(source)
    binary = tmp_path/'window_guard'
    subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror', str(file), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
