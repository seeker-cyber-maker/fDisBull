"""Execute exact source-fence transitions with controlled stop-state stubs.

These probes compile hash-checked production helpers and the actual tail of
the main-loop stop ordering. They do not build QEMU, emit a GDB stop packet,
exercise a device, or qualify scanline/input/legacy behavior.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'native/qemu-video-frame-fence'
SOURCE = 'system/fdisbull-video-frame.c'


def _section(patch, path):
    marker = f'diff --git a/{path} b/{path}\n'
    return patch.decode().split(marker, 1)[1].split('diff --git ', 1)[0]


def _package(path):
    manifest = json.loads((path / 'source-manifest.json').read_text())
    patch = (path / manifest['patch']).read_bytes()
    assert hashlib.sha256(patch).hexdigest() == manifest['patch_sha256']
    return manifest, patch


def _apply(base, section):
    """Apply only an exact matching unified source hunk, without shell/git."""
    original = base.decode().splitlines(keepends=True)
    lines = section.splitlines(keepends=True)
    result, cursor, i = [], 0, 0
    while i < len(lines):
        match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[i])
        if not match:
            i += 1
            continue
        old_count = int(match[2] or 1)
        new_count = int(match[4] or 1)
        offset = int(match[1]) - (1 if old_count else 0)
        assert cursor <= offset <= len(original)
        result.extend(original[cursor:offset])
        cursor = offset
        consumed = added = 0
        i += 1
        while i < len(lines) and not lines[i].startswith('@@ '):
            line = lines[i]
            assert line and line[0] in ' +-'
            if line[0] in ' -':
                assert cursor < len(original) and original[cursor] == line[1:]
                cursor += 1
                consumed += 1
            if line[0] in ' +':
                result.append(line[1:])
                added += 1
            i += 1
        assert (consumed, added) == (old_count, new_count)
    return ''.join(result + original[cursor:]).encode()


def _function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    for end in range(brace, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if depth == 0:
            return source[start:end + 1]
    raise AssertionError('Unterminated production function: ' + signature)


def production_fragments():
    old_manifest, old_patch = _package(ROOT / 'native/qemu-video-frame')
    manifest, patch = _package(PACKAGE)
    assert manifest['prerequisite_patch_sha256'] == old_manifest['patch_sha256']
    old_section = _section(old_patch, SOURCE)
    base = ''.join(line[1:] for line in old_section.splitlines(keepends=True)
                   if line.startswith('+') and not line.startswith('+++')).encode()
    old_record = next(item for item in old_manifest['files'] if item['path'] == SOURCE)
    record = next(item for item in manifest['files'] if item['path'] == SOURCE)
    assert hashlib.sha256(base).hexdigest() == old_record['patched_sha256']
    assert old_record['patched_sha256'] == record['base_sha256']
    source_bytes = _apply(base, _section(patch, SOURCE))
    assert hashlib.sha256(source_bytes).hexdigest() == record['patched_sha256']
    source = source_bytes.decode()
    state = source.split('/* Source-probe fence state begins: these are the production state helpers. */\n', 1)[1]
    state = state.split('/* Source-probe fence state ends. */', 1)[0]
    functions = '\n\n'.join(_function(source, signature) for signature in (
        'static void video_fence_retire(const char *reason)',
        'void fdisbull_video_frame_clock_retire(const char *reason)',
        'static void video_fence_request_stop(void)',
        'static void video_fence_abort(const char *reason)',
        'bool fdisbull_video_frame_checkpoint_safe(Error **errp)',
        'void fdisbull_video_frame_handle_stop_request(void)',
        'static void video_vm_state_change(void *opaque, bool running, RunState state)',
    ))
    runstate = ''.join(line[1:] for line in _section(patch, 'system/runstate.c').splitlines(keepends=True)
                       if line.startswith((' ', '+')) and not line.startswith('+++'))
    tail = runstate[runstate.index('    if (qemu_vmstop_requested(&r)) {'):]
    tail = tail[:tail.index('    return false;') + len('    return false;')]
    assert tail.count('fdisbull_video_frame_handle_stop_request();') == 1
    return state, functions, tail


@pytest.fixture(scope='module')
def source_probe(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('A C compiler is required for source-fence probes')
    state, functions, tail = production_fragments()
    source = _PREFIX + state + _STUBS + functions + '\n' + _INVALIDATE + '\n'
    source += 'static bool finish_main_loop(void) {\n    RunState r;\n' + tail + '\n}\n'
    source += _CASES
    directory = tmp_path_factory.mktemp('video-fence-source')
    path, binary = directory / 'probe.c', directory / 'probe'
    path.write_text(source)
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-Wno-unused-parameter', str(path), '-o', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return binary


CASES = (
    'identity_exact', 'identity_generation', 'identity_epoch',
    'identity_configuration', 'identity_timing', 'identity_old_frame',
    'identity_skip_frame', 'identity_wrap', 'identity_released',
    'identity_not_armed', 'identity_null', 'cancel_unfinished',
    'cancel_completed', 'cancel_aborted', 'cancel_pending_refused',
    'no_owner_release_refused', 'first_stop_wins', 'own_stop',
    'prior_debug_stop', 'pending_generic_stop', 'abort_running',
    'abort_stopped', 'abort_reason_sticky', 'debug_armed_preserved',
    'checkpoint_block_release', 'no_cpu_thread_pending',
    'ordinary_after_release', 'busy_vm_state_inert',
    'retire_armed', 'retire_completed_pending', 'retire_completed_owned',
    'retire_aborted_pending', 'retire_idempotent',
    'same_epoch_source_reset_aborts',
)


@pytest.mark.parametrize('case', CASES)
def test_exact_native_fence_source_transition(source_probe, case):
    result = subprocess.run([str(source_probe), case], capture_output=True,
                            text=True, timeout=3)
    assert result.returncode == 0, (case, result.stdout, result.stderr)


_PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef struct FdisbullVideoFrame {
    uint64_t frame_id, stream_generation, epoch;
    uint64_t configuration_generation, timing_generation;
} FdisbullVideoFrame;
typedef struct Error { int code; } Error;
typedef enum RunState {
    RUN_STATE_PRELAUNCH, RUN_STATE_PAUSED, RUN_STATE_DEBUG,
    RUN_STATE_RUNNING, RUN_STATE_SHUTDOWN
} RunState;
#define QEMU_CLOCK_VIRTUAL 0
'''

_STUBS = r'''
static RunState running_state = RUN_STATE_RUNNING, queued_state = RUN_STATE_DEBUG;
static bool busy, queued_stop, has_cpu = true;
static int64_t now_ns = 111;
static unsigned cpu_stop_calls, cpu_stop_effects, notifications, vm_stops;
static unsigned invalidations, errors;
static Error error;
static struct { char *token; void *console; } video = { "stream", (void *)1 };
static bool bql_locked(void) { return true; }
static bool runstate_is_running(void) { return running_state == RUN_STATE_RUNNING; }
static bool runstate_check(RunState state) { return running_state == state; }
static bool fdisbull_instrumented_checkpoint_busy(void) { return busy; }
static int64_t qemu_clock_get_ns(int clock) { (void)clock; return now_ns; }
static void cpu_stop_current(void) { ++cpu_stop_calls; cpu_stop_effects += has_cpu; }
static void qemu_notify_event(void) { ++notifications; }
static char *g_strdup(const char *value) {
    size_t length = strlen(value) + 1;
    char *result = malloc(length);
    assert(result);
    memcpy(result, value, length);
    return result;
}
static void error_setg(Error **out, const char *message, ...) {
    (void)message; ++errors; if (out) *out = &error;
}
static void video_vm_state_change(void *, bool, RunState);
static void fdisbull_video_frame_invalidate(void *, const char *);
static int vm_stop(RunState state) {
    ++vm_stops;
    if (runstate_is_running()) {
        running_state = state;
        video_vm_state_change(NULL, false, state);
    }
    return 0;
}
static bool qemu_vmstop_requested(RunState *state) {
    if (!queued_stop) return false;
    queued_stop = false; *state = queued_state; return true;
}
'''

_INVALIDATE = r'''
static void fdisbull_video_frame_invalidate(void *console, const char *reason) {
    assert(console == video.console);
    ++invalidations;
    video_fence_abort(reason);
}
'''

_CASES = r'''
static void arm(void) {
    memset(&video_fence, 0, sizeof(video_fence));
    video_fence.state = VIDEO_FENCE_ARMED;
    video_fence.token = "fence";
    video_fence.stream_token = "stream";
    video_fence.generation = 7;
    video_fence.epoch = 9;
    video_fence.configuration_generation = 31;
    video_fence.timing_generation = 21;
    video_fence.baseline = 41;
    video_fence.baseline_rows = 117;
    video_fence.armed_ns = 100;
}

static void terminal(VideoFenceState state) {
    arm();
    video_fence.state = state;
    video_fence.stop_pending = true;
}

int main(int argc, char **argv) {
    assert(argc == 2);
    const char *which = argv[1];
    arm();
    if (!strncmp(which, "identity_", 9)) {
        FdisbullVideoFrame frame = { 42, 7, 9, 31, 21 };
        bool expected = !strcmp(which, "identity_exact");
        if (!strcmp(which, "identity_generation")) frame.stream_generation = 8;
        if (!strcmp(which, "identity_epoch")) frame.epoch = 10;
        if (!strcmp(which, "identity_configuration")) frame.configuration_generation = 32;
        if (!strcmp(which, "identity_timing")) frame.timing_generation = 22;
        if (!strcmp(which, "identity_old_frame")) frame.frame_id = 41;
        if (!strcmp(which, "identity_skip_frame")) frame.frame_id = 43;
        if (!strcmp(which, "identity_wrap")) {
            video_fence.baseline = UINT64_MAX; frame.frame_id = 0;
        }
        if (!strcmp(which, "identity_released")) video_fence.released = true;
        if (!strcmp(which, "identity_not_armed")) video_fence.state = VIDEO_FENCE_COMPLETED;
        assert(video_fence_is_next_frame(!strcmp(which, "identity_null") ? NULL : &frame) == expected);
    } else if (!strcmp(which, "cancel_unfinished")) {
        assert(fdisbull_video_frame_fence_blocks_control());
        assert(video_fence_release() && video_fence_release());
        assert(video_fence.state == VIDEO_FENCE_CANCELLED && video_fence.released);
        assert(!video_fence.has_stop_ns && !video_fence.stop_consumed);
        assert(!fdisbull_video_frame_fence_blocks_control() && !video_fence.frame);
        assert(video_fence.baseline_rows == 117 && video_fence.baseline == 41);
    } else if (!strcmp(which, "cancel_completed") || !strcmp(which, "cancel_aborted")) {
        bool completed = !strcmp(which, "cancel_completed");
        FdisbullVideoFrame frame = { 42, 7, 9, 31, 21 };
        terminal(completed ? VIDEO_FENCE_COMPLETED : VIDEO_FENCE_ABORTED);
        video_fence.frame = completed ? &frame : NULL;
        video_fence.reason = completed ? NULL : "source-abort";
        video_fence_record_stopped(111, true);
        assert(fdisbull_video_frame_fence_blocks_control());
        assert(video_fence_release() && video_fence_release());
        assert(video_fence.state == (completed ? VIDEO_FENCE_COMPLETED : VIDEO_FENCE_ABORTED));
        assert(video_fence.frame == (completed ? &frame : NULL));
        assert(video_fence.stop_ns == 111 && video_fence.stop_consumed && video_fence.released);
        assert(video_fence.baseline_rows == 117 && !fdisbull_video_frame_stop_pending());
        if (!completed) assert(!strcmp(video_fence.reason, "source-abort"));
    } else if (!strcmp(which, "cancel_pending_refused")) {
        terminal(VIDEO_FENCE_COMPLETED);
        unsigned char before[sizeof(video_fence)];
        memcpy(before, &video_fence, sizeof(before));
        assert(!video_fence_release());
        assert(!memcmp(before, &video_fence, sizeof(before)));
    } else if (!strcmp(which, "no_owner_release_refused")) {
        memset(&video_fence, 0, sizeof(video_fence));
        assert(!video_fence_release() && !fdisbull_video_frame_fence_blocks_control());
    } else if (!strcmp(which, "first_stop_wins")) {
        terminal(VIDEO_FENCE_COMPLETED);
        video_fence_record_stopped(111, false);
        video_fence_record_stopped(999, true);
        assert(video_fence.stop_ns == 111 && !video_fence.stop_consumed);
        assert(!video_fence.stop_pending && video_fence.has_stop_ns);
    } else if (!strcmp(which, "own_stop")) {
        terminal(VIDEO_FENCE_COMPLETED);
        fdisbull_video_frame_handle_stop_request();
        fdisbull_video_frame_handle_stop_request();
        assert(vm_stops == 1 && running_state == RUN_STATE_PAUSED);
        assert(video_fence.stop_consumed && video_fence.stop_ns == 111);
        assert(!video_fence.stop_pending && !video_fence.stopping);
    } else if (!strcmp(which, "prior_debug_stop")) {
        terminal(VIDEO_FENCE_COMPLETED);
        vm_stop(RUN_STATE_DEBUG);
        now_ns = 999;
        fdisbull_video_frame_handle_stop_request();
        assert(vm_stops == 1 && running_state == RUN_STATE_DEBUG);
        assert(!video_fence.stop_consumed && video_fence.stop_ns == 111);
    } else if (!strcmp(which, "pending_generic_stop")) {
        terminal(VIDEO_FENCE_COMPLETED);
        queued_stop = true;
        assert(!finish_main_loop());
        assert(vm_stops == 1 && running_state == RUN_STATE_DEBUG);
        assert(!video_fence.stop_consumed && !video_fence.stop_pending);
    } else if (!strcmp(which, "abort_running")) {
        video_fence_abort("configuration-changed");
        assert(video_fence.state == VIDEO_FENCE_ABORTED && !video_fence.frame);
        assert(video_fence.stop_pending && cpu_stop_calls == 1 && notifications == 1);
        now_ns = 222;
        assert(!finish_main_loop());
        assert(video_fence.stop_consumed && video_fence.stop_ns == 222);
        assert(!strcmp(video_fence.reason, "configuration-changed"));
    } else if (!strcmp(which, "abort_stopped")) {
        running_state = RUN_STATE_DEBUG;
        video_fence_abort("source-invalidated");
        assert(video_fence.state == VIDEO_FENCE_ABORTED && video_fence.stop_ns == 111);
        assert(!video_fence.stop_consumed && !video_fence.stop_pending);
        assert(cpu_stop_calls == 0 && notifications == 0 && vm_stops == 0);
    } else if (!strcmp(which, "abort_reason_sticky")) {
        video_fence_abort("first");
        video_fence_abort("second");
        assert(!strcmp(video_fence.reason, "first"));
        assert(cpu_stop_calls == 1 && notifications == 1);
    } else if (!strcmp(which, "debug_armed_preserved")) {
        vm_stop(RUN_STATE_DEBUG);
        assert(video_fence.state == VIDEO_FENCE_ARMED && !video_fence.released);
        assert(!video_fence.has_stop_ns && !video_fence.stop_pending);
        assert(invalidations == 0);
    } else if (!strcmp(which, "checkpoint_block_release")) {
        Error *err = NULL;
        assert(!fdisbull_video_frame_checkpoint_safe(&err) && err && errors == 1);
        assert(video_fence_release());
        assert(fdisbull_video_frame_checkpoint_safe(&err) && errors == 1);
    } else if (!strcmp(which, "no_cpu_thread_pending")) {
        terminal(VIDEO_FENCE_COMPLETED);
        video_fence.stop_pending = false;
        has_cpu = false;
        video_fence_request_stop();
        assert(fdisbull_video_frame_stop_pending());
        assert(cpu_stop_calls == 1 && cpu_stop_effects == 0 && notifications == 1);
        assert(!finish_main_loop());
        assert(video_fence.stop_consumed && vm_stops == 1);
    } else if (!strcmp(which, "ordinary_after_release")) {
        terminal(VIDEO_FENCE_COMPLETED);
        assert(!finish_main_loop());
        assert(video_fence_release());
        running_state = RUN_STATE_RUNNING;
        now_ns = 999;
        assert(!finish_main_loop());
        assert(running_state == RUN_STATE_RUNNING && vm_stops == 1);
        assert(video_fence.stop_ns == 111 && video_fence.stop_consumed);
    } else if (!strcmp(which, "busy_vm_state_inert")) {
        terminal(VIDEO_FENCE_COMPLETED);
        busy = true;
        vm_stop(RUN_STATE_DEBUG);
        assert(video_fence.stop_pending && !video_fence.has_stop_ns);
        assert(!video_fence.stop_consumed && invalidations == 0);
    } else if (!strcmp(which, "retire_armed")) {
        fdisbull_video_frame_clock_retire("native-clock-invalidated");
        assert(video_fence.retired && video_fence.released);
        assert(video_fence.state == VIDEO_FENCE_ABORTED);
        assert(!strcmp(video_fence.reason, "native-clock-invalidated"));
        assert(video_fence.epoch == 9 && video_fence.generation == 7);
        assert(!video_fence.has_stop_ns && !video_fence.stop_consumed);
        assert(!fdisbull_video_frame_stop_pending());
        assert(!fdisbull_video_frame_fence_blocks_control());
        assert(!finish_main_loop() && vm_stops == 0 && invalidations == 1);
        assert(cpu_stop_calls == 0 && notifications == 0);
    } else if (!strcmp(which, "retire_completed_pending")) {
        terminal(VIDEO_FENCE_COMPLETED);
        FdisbullVideoFrame frame = { 42, 7, 9, 31, 21 };
        video_fence.frame = &frame;
        fdisbull_video_frame_clock_retire("native-clock-restored");
        assert(video_fence.retired && video_fence.released);
        assert(video_fence.state == VIDEO_FENCE_COMPLETED && video_fence.frame == &frame);
        assert(!video_fence.has_stop_ns && !video_fence.stop_consumed);
        assert(!video_fence.stop_pending && !video_fence.stopping);
        video_fence_record_stopped(999, true);
        video_fence_request_stop();
        assert(!video_fence.has_stop_ns && !video_fence.stop_consumed);
        assert(!finish_main_loop() && vm_stops == 0);
        assert(cpu_stop_calls == 0 && notifications == 0);
    } else if (!strcmp(which, "retire_completed_owned")) {
        terminal(VIDEO_FENCE_COMPLETED);
        video_fence_record_stopped(111, true);
        fdisbull_video_frame_clock_retire("native-clock-invalidated");
        now_ns = 999;
        video_fence_record_stopped(now_ns, false);
        assert(video_fence.retired && !fdisbull_video_frame_fence_blocks_control());
        assert(video_fence.stop_ns == 111 && video_fence.stop_consumed);
        assert(video_fence.epoch == 9 && !finish_main_loop() && vm_stops == 0);
    } else if (!strcmp(which, "retire_aborted_pending")) {
        video_fence_abort("first-source-failure");
        assert(video_fence.stop_pending && !video_fence.has_stop_ns);
        fdisbull_video_frame_clock_retire("native-clock-restored");
        assert(!strcmp(video_fence.reason, "first-source-failure"));
        assert(video_fence.retired && video_fence.released);
        assert(!video_fence.has_stop_ns && !video_fence.stop_consumed);
        assert(!finish_main_loop() && vm_stops == 0);
    } else if (!strcmp(which, "retire_idempotent")) {
        video_fence_retire("first-clock-retirement");
        unsigned char before[sizeof(video_fence)];
        memcpy(before, &video_fence, sizeof(before));
        video_fence_retire("second-clock-retirement");
        assert(!memcmp(before, &video_fence, sizeof(before)));
        assert(!video_fence_release());
    } else if (!strcmp(which, "same_epoch_source_reset_aborts")) {
        fdisbull_video_frame_invalidate(video.console, "native-reset");
        assert(!video_fence.retired && !video_fence.released);
        assert(video_fence.state == VIDEO_FENCE_ABORTED && video_fence.stop_pending);
        assert(!strcmp(video_fence.reason, "native-reset"));
        assert(!finish_main_loop() && video_fence.stop_consumed && vm_stops == 1);
    } else {
        assert(!"Unknown authored source case");
    }
    return 0;
}
'''
