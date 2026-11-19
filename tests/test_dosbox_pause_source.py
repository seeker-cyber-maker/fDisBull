"""Execute the actual loop guards with state stubs, not a DOSBox runtime test.

The extraction ends at PIC_RunQueue: a guard moved below that boundary cannot
protect these probes. The stub side effects represent forbidden PIC/timer or
decoder work after a stop, without pretending to emulate those components.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ('experimental/dosbox-x', 'experimental/dosbox-x/layers')


def normal_loop_fragments(package):
    patch = (package/'headless-agent.patch').read_bytes()
    manifest = json.loads((package/'source-manifest.json').read_text())
    assert hashlib.sha256(patch).hexdigest() == manifest['patch_sha256']
    section = patch.decode().split('diff --git a/src/dosbox.cpp b/src/dosbox.cpp\n', 1)[1]
    section = section.split('\ndiff --git ', 1)[0]
    source = '\n'.join(line[1:] for line in section.splitlines()
                       if line.startswith((' ', '+')) and not line.startswith('+++'))
    start = source.index('        while (1) {')
    pic_marker = '            if (PIC_RunQueue()) {\n'
    pic = source.index(pic_marker, start)
    decoder = source.index('                /* now is the time to check for the NMI', pic)
    return source[start:pic], source[pic+len(pic_marker):decoder]


@pytest.fixture(scope='module', params=PATCHES, ids=('stable', 'layers'))
def pause_source_probe(request, tmp_path_factory):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('C++ compiler required for the isolated pause source probe')
    before_pic, after_pic = normal_loop_fragments(ROOT/request.param)
    source = _STUBS + '\nstatic unsigned before_pic() {\n' + before_pic + r'''
        ++pic_calls;
        ++ticks;
        --ticks_remain;
        return 1;
    }
}
static unsigned after_pic() {
''' + after_pic + r'''
    ++decoder_calls;
    return 1;
}
''' + _CASES
    directory = tmp_path_factory.mktemp('dosbox-pause-source')
    path = directory/'pause.cpp'
    path.write_text(source)
    binary = directory/'pause'
    result = subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                             str(path), '-o', str(binary)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    return binary


_STUBS = r'''
#include <cassert>
#include <cstddef>
#include <cstring>
#define C_DEBUG 1
#define C_DOSBOX_AGENT 1
static bool agent_session = true, debugging = false, runwatch = false;
static bool exit_requested = false, frame_stop = false, pump_pause = false;
static unsigned pic_calls = 0, decoder_calls = 0, debugger_entries = 0;
static unsigned exit_checks = 0, ticks = 12345, ticks_remain = 17;
bool IsDebuggerActive() { return debugging; }
bool IsDebuggerRunwatch() { return runwatch; }
void DEBUG_EnableDebugger() {
    ++debugger_entries;
    debugging = true;
    runwatch = false;
    exit_requested = true;
    frame_stop = false;
}
bool DEBUG_ExitLoop() {
    ++exit_checks;
    const bool result = exit_requested;
    exit_requested = false;
    return result;
}
namespace dosbox_agent {
bool AGENT_IsSession() { return agent_session; }
bool AGENT_FrameStepStopRequested() { return frame_stop; }
std::size_t AGENT_BridgePump() {
    if (!pump_pause) return 0;
    DEBUG_EnableDebugger();
    pump_pause = false;
    return 1;
}
}
'''


_CASES = r'''
static void stopped_before_pic() {
    assert(before_pic() == 0);
    assert(pic_calls == 0 && decoder_calls == 0);
    assert(ticks == 12345 && ticks_remain == 17);
    assert(!exit_requested);
}
int main(int argc, char** argv) {
    assert(argc == 2);
    if (!std::strcmp(argv[1], "ordinary_pause")) {
        pump_pause = true;
        stopped_before_pic();
        assert(debugger_entries == 1 && exit_checks == 1);
    } else if (!std::strcmp(argv[1], "consumed_exit")) {
        debugging = true;
        // The persistent stop, not an already-consumed one-shot flag, fences
        // the outer normal loop after nested work returns.
        exit_requested = false;
        stopped_before_pic();
        assert(debugger_entries == 0 && exit_checks == 1);
    } else if (!std::strcmp(argv[1], "step_cleared_exit")) {
        debugging = true;
        // DEBUG_AgentStep executes its instruction directly, clears exitLoop,
        // and remains stopped. No additional PIC/timer work is authorized.
        exit_requested = false;
        stopped_before_pic();
    } else if (!std::strcmp(argv[1], "continue_or_step_over")) {
        debugging = false;
        exit_requested = true;
        assert(before_pic() == 1 && pic_calls == 1);
        // Leave the existing post-decoder exit check to consume a stale flag;
        // callback-safe Continue must still reach the normal decoder path.
        assert(exit_requested && exit_checks == 0);
    } else if (!std::strcmp(argv[1], "runwatch")) {
        debugging = true;
        runwatch = true;
        assert(before_pic() == 1 && pic_calls == 1 && exit_checks == 0);
    } else if (!std::strcmp(argv[1], "non_agent")) {
        agent_session = false;
        debugging = true;
        assert(before_pic() == 1 && pic_calls == 1 && exit_checks == 0);
    } else if (!std::strcmp(argv[1], "frame_before_pic")) {
        frame_stop = true;
        stopped_before_pic();
        assert(debugger_entries == 1 && exit_checks == 1);
    } else if (!std::strcmp(argv[1], "frame_after_pic")) {
        frame_stop = true;
        assert(after_pic() == 0 && decoder_calls == 0);
        assert(debugger_entries == 1 && exit_checks == 1 && !exit_requested);
    } else if (!std::strcmp(argv[1], "running_after_pic")) {
        assert(after_pic() == 1 && decoder_calls == 1 && exit_checks == 0);
    } else {
        assert(false);
    }
}
'''


@pytest.mark.parametrize('case', (
    'ordinary_pause', 'consumed_exit', 'step_cleared_exit', 'continue_or_step_over',
    'runwatch', 'non_agent', 'frame_before_pic', 'frame_after_pic', 'running_after_pic',
))
def test_paused_agent_handoff_precedes_pic_and_preserves_running_paths(pause_source_probe, case):
    result = subprocess.run([str(pause_source_probe), case], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stdout+result.stderr
