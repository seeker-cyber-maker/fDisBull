"""Compile the shipped mouse adapter against mode/driver/event collaborators.

This proves queue admission, coordinate/ownership and delayed release contracts;
it does not replace native DOS extender or game-consumption acceptance.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _added_block(lines, start, end):
    first = lines.index(start)
    last = lines.index(end, first) + 1
    assert all(line.startswith('+') for line in lines[first:last])
    return '\n'.join(line[1:] for line in lines[first:last])


@pytest.mark.parametrize('directory', ['experimental/dosbox-x', 'experimental/dosbox-x/layers'])
def test_builtin_mouse_queues_in_protected_mode_without_real_mode_memory_access(tmp_path, directory, request):
    patch = ROOT / directory / 'headless-agent.patch'
    if not patch.is_file():
        message = 'Native source patches are separate from tool-only source archives'
        if request.config.getoption('--require-native', default=False):
            pytest.fail(message + '; run required acceptance from the repository')
        pytest.skip(message)
    compiler = shutil.which('c++')
    if compiler is None:
        pytest.skip('C++ compiler required for the isolated native adapter contract')
    lines = patch.read_text().splitlines()
    state = _added_block(lines, '+struct AgentMouseState {', '+};')
    mouse = lines[lines.index('+++ b/src/ints/mouse.cpp'):]
    adapter = _added_block(mouse, '+namespace dosbox_agent {', '+} // namespace dosbox_agent')
    source = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
#include <algorithm>
using Bitu = unsigned;
using pic_tickindex_t = double;
struct { bool pmode = false; } cpu;
bool vm = false, dos_kernel_disabled = false, en_int33 = true;
bool pc98 = false, useps2callback = false, aux = false;
int mode;
int* CurMode = &mode;
constexpr unsigned VM = 0x20000;
#define GETFLAG(flag) ((flag) == VM && vm)
#define IS_PC98_ARCH pc98
#define MOUSE_BUTTONS 3
#define MOUSE_HAS_MOVED 1
unsigned agent_builtin_int33_vector = 0x12345678;
unsigned physical_vector = agent_builtin_int33_vector;
unsigned real_reads = 0, physical_reads = 0;
bool AllowINT33RMAccess() { return !dos_kernel_disabled && (!cpu.pmode || GETFLAG(VM)); }
unsigned real_readd(unsigned, unsigned) { ++real_reads; assert(!cpu.pmode || vm); return physical_vector; }
unsigned phys_readd(unsigned address) { ++physical_reads; assert(address == 0x33u * 4); return physical_vector; }
int KEYBOARD_AUX_Active() { return aux; }
struct Mouse {
    float x = 0, y = 0;
    int min_x = 0, max_x = 639, min_y = 0, max_y = 199;
    int max_screen_x = 639, max_screen_y = 199;
    unsigned buttons = 0;
} mouse;
#define POS_X static_cast<int>(mouse.x)
#define POS_Y static_cast<int>(mouse.y)
std::vector<unsigned> queued;
void Mouse_AddEvent(unsigned event) { queued.push_back(event); }
void Mouse_ButtonPressed(std::uint8_t button) { mouse.buttons |= 1u << button; queued.push_back(2); }
void Mouse_ButtonReleased(std::uint8_t button) { mouse.buttons &= ~(1u << button); queued.push_back(4); }
struct Event { void (*callback)(Bitu); double due; Bitu value; };
std::vector<Event> scheduled;
double guest_ms = 0;
void PIC_RemoveSpecificEvents(void (*callback)(Bitu), Bitu value) {
    scheduled.erase(std::remove_if(scheduled.begin(), scheduled.end(),
        [=](const Event& e) { return e.callback == callback && e.value == value; }), scheduled.end());
}
void PIC_RemoveEvents(void (*callback)(Bitu)) {
    scheduled.erase(std::remove_if(scheduled.begin(), scheduled.end(),
        [=](const Event& e) { return e.callback == callback; }), scheduled.end());
}
void PIC_AddEvent(void (*callback)(Bitu), double delay, Bitu value) {
    scheduled.push_back({callback, guest_ms + delay, value});
}
void advance(double ms) {
    guest_ms += ms;
    for (auto i = scheduled.begin(); i != scheduled.end();) {
        if (i->due <= guest_ms) { const auto event = *i; i = scheduled.erase(i); event.callback(event.value); }
        else ++i;
    }
}
namespace dosbox_agent {
''' + state + '\n}\n' + adapter + r'''
int main() {
    using namespace dosbox_agent;
    std::string error;
    AgentMouseState observed;
    assert(AGENT_MouseGetState(&observed, &error));
    cpu.pmode = true;
    assert(AGENT_MouseMoveAbsolute(160, 99, 320, 200, &observed, &error));
    assert(observed.x == 320 && observed.y == 99);
    assert(real_reads == 0 && physical_reads > 0);
    assert(queued.size() == 1);
    assert(AGENT_MouseClickAbsolute(319, 199, 320, 200, 0, 50, &observed, &error));
    assert(observed.x == 639 && observed.y == 199 && observed.buttons == 1);
    assert(observed.owned_buttons == 1 && observed.release_pending);
    assert(!AGENT_MouseClickAbsolute(0, 0, 320, 200, 0, 50, &observed, &error));
    assert(AGENT_MouseGetState(&observed, &error) && observed.release_pending);
    advance(49); assert(mouse.buttons == 1);
    advance(1); assert(mouse.buttons == 0);
    assert(AGENT_MouseGetState(&observed, &error) && !observed.release_pending);
    assert(!AGENT_MouseMoveAbsolute(320, 0, 320, 200, &observed, &error));
    physical_vector ^= 1; assert(!AGENT_MouseGetState(&observed, &error)); physical_vector ^= 1;
    dos_kernel_disabled = true; assert(!AGENT_MouseGetState(&observed, &error)); dos_kernel_disabled = false;
    en_int33 = false; assert(!AGENT_MouseGetState(&observed, &error)); en_int33 = true;
    aux = true; assert(!AGENT_MouseGetState(&observed, &error)); aux = false;
    useps2callback = true; assert(!AGENT_MouseGetState(&observed, &error)); useps2callback = false;
    pc98 = true; assert(!AGENT_MouseGetState(&observed, &error)); pc98 = false;
    CurMode = nullptr; assert(!AGENT_MouseGetState(&observed, &error)); CurMode = &mode;
    mouse.min_x = 20; mouse.max_x = 19; assert(!AGENT_MouseGetState(&observed, &error));
    mouse.min_x = 0; mouse.max_x = 639;
    mouse.buttons = 2; assert(!AGENT_MouseButton(1, true, &observed, &error)); mouse.buttons = 0;
    vm = true; assert(AGENT_MouseButton(0, true, &observed, &error));
    AGENT_MouseResetInput(); assert(mouse.buttons == 0 && scheduled.empty());
    vm = false; cpu.pmode = false; assert(AGENT_MouseGetState(&observed, &error));
    assert(real_reads == 0);
}
'''
    file = tmp_path / 'protected_mouse.cpp'
    file.write_text(source)
    binary = tmp_path / 'protected_mouse'
    subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror', str(file), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
