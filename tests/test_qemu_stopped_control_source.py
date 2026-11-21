"""Exercise the exact native admission module with controlled external stubs.

Every production byte comes from the hash-checked patch. The harness supplies
deterministic monitor objects, CPU/address-space views and controller receipts.
It does not build QEMU, execute its real monitor/GDB handlers, exercise a guest
or establish whole-machine, raster, input or legacy parity.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'native/qemu-stopped-control'
SOURCE = 'system/fdisbull-stopped-control.c'


def _patch_section(path):
    manifest = json.loads((PACKAGE / 'source-manifest.json').read_text())
    patch = (PACKAGE / manifest['patch']).read_bytes()
    assert hashlib.sha256(patch).hexdigest() == manifest['patch_sha256']
    marker = f'diff --git a/{path} b/{path}\n'
    section = patch.decode().split(marker, 1)[1].split('diff --git ', 1)[0]
    record = next(item for item in manifest['files'] if item['path'] == path)
    return section, record


def _new_source(path):
    section, record = _patch_section(path)
    assert '--- /dev/null\n' in section
    source = ''.join(line[1:] for line in section.splitlines(keepends=True)
                     if line.startswith('+') and not line.startswith('+++'))
    assert record['base_sha256'] is None
    assert hashlib.sha256(source.encode()).hexdigest() == record['patched_sha256']
    return source


def _full_context_source(path):
    section, record = _patch_section(path)
    lines = section.splitlines(keepends=True)
    hunks = [index for index, line in enumerate(lines) if line.startswith('@@ ')]
    assert len(hunks) == 1
    content = lines[hunks[0] + 1:]
    assert all(line[0] in ' +-' for line in content)
    before = ''.join(line[1:] for line in content if line[0] in ' -')
    after = ''.join(line[1:] for line in content if line[0] in ' +')
    assert hashlib.sha256(before.encode()).hexdigest() == record['base_sha256']
    assert hashlib.sha256(after.encode()).hexdigest() == record['patched_sha256']
    return after


def _function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    for end in range(brace, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if depth == 0:
            return source[start:end + 1]
    raise AssertionError('Unterminated production function: ' + signature)


def test_generic_gdb_user_mode_excludes_system_control(tmp_path):
    """Preprocess the exact complete generic C; no user-mode QEMU build claim."""
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('A C preprocessor is required for the user-mode guard probe')
    source = _full_context_source('gdbstub/gdbstub.c')
    include = tmp_path / 'include'
    for name in re.findall(r'^#include "([^"]+)"', source, re.MULTILINE):
        target = include / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('')
    system_header = include / 'system/fdisbull-stopped-control.h'
    system_header.write_text('#error System-only stopped-control header reached user mode\n')
    path, output = tmp_path / 'gdbstub.c', tmp_path / 'user.c'
    path.write_text(source)
    command = [compiler, '-std=c11', '-E', '-P', '-DCONFIG_USER_ONLY',
               '-I', str(include), str(path), '-o', str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    user_source = output.read_text()
    assert 'gdb_handle_packet' in user_source
    assert 'fdisbull_stopped_control' not in user_source
    assert 'gdb_target_stopped_control_physical' not in user_source
    # Positive control: the same production source retains every hook in system mode.
    system_header.write_text('')
    command.remove('-DCONFIG_USER_ONLY')
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    system_source = output.read_text()
    for name in ('gdb_enter', 'gdb_leave', 'reject'):
        assert 'fdisbull_stopped_control_' + name in system_source
    assert 'gdb_target_stopped_control_physical' in system_source


def test_non_system_shared_qmp_hooks_link(tmp_path):
    """Link actual stubs and header, without claiming a storage-daemon build."""
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('A C compiler is required for the non-system hook link probe')
    include = tmp_path / 'include'
    (include / 'qemu').mkdir(parents=True)
    (include / 'system').mkdir()
    (include / 'qemu/osdep.h').write_text('#include <stdbool.h>\n#include <stddef.h>\n')
    (include / 'qemu/typedefs.h').write_text('typedef struct QObject QObject;\ntypedef struct CPUState CPUState;\n')
    (include / 'system/fdisbull-stopped-control.h').write_text(_new_source('include/system/fdisbull-stopped-control.h'))
    source, caller, binary = tmp_path / 'stubs.c', tmp_path / 'caller.c', tmp_path / 'probe'
    source.write_text(_new_source('stubs/fdisbull-stopped-control.c'))
    caller.write_text('''#include "qemu/osdep.h"
#include "system/fdisbull-stopped-control.h"
int main(void) {
    fdisbull_stopped_control_qmp_received(NULL);
    fdisbull_stopped_control_qmp_enter(NULL);
    fdisbull_stopped_control_qmp_leave();
    fdisbull_stopped_control_channel("closed", false);
    return 0;
}
''')
    command = [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
               '-Wno-unused-parameter', '-I', str(include), str(source),
               str(caller), '-o', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)


@pytest.fixture(scope='module')
def pending_probe(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('A C compiler is required for the nonconsuming pending probe')
    section, _ = _patch_section('system/runstate.c')
    added = ''.join(line[1:] for line in section.splitlines(keepends=True)
                    if line.startswith('+') and not line.startswith('+++'))
    function = _function(added, 'bool fdisbull_stopped_control_system_pending(void)')
    prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
enum { RUN_STATE_PAUSED, RUN_STATE_RUNNING, RUN_STATE__MAX };
enum { SHUTDOWN_CAUSE_NONE = 0, QEMU_WAKEUP_REASON_NONE = 0 };
static int vmstop_requested = RUN_STATE__MAX;
static int reset_requested, shutdown_requested, powerdown_requested;
static int debug_requested, suspend_requested, wakeup_reason;
static bool vmstop_lock; static unsigned locks, unlocks;
static bool bql_locked(void) { return true; }
static void qemu_mutex_lock(bool *lock) { assert(!*lock); *lock = true; ++locks; }
static void qemu_mutex_unlock(bool *lock) { assert(*lock); *lock = false; ++unlocks; }
#define qatomic_read(pointer) (*(pointer))
'''
    cases = r'''
int main(int argc, char **argv) {
    assert(argc == 2); int which = atoi(argv[1]);
    int *flags[] = {&vmstop_requested, &reset_requested, &shutdown_requested,
        &powerdown_requested, &debug_requested, &suspend_requested, &wakeup_reason};
    assert(which >= 0 && which <= 7);
    if (which) *flags[which - 1] = which == 1 ? RUN_STATE_PAUSED : 1;
    int before[7];
    for (unsigned i = 0; i < 7; ++i) before[i] = *flags[i];
    assert(fdisbull_stopped_control_system_pending() == (which != 0));
    assert(fdisbull_stopped_control_system_pending() == (which != 0));
    for (unsigned i = 0; i < 7; ++i) assert(before[i] == *flags[i]);
    assert(locks == 2 && unlocks == 2 && !vmstop_lock);
    return 0;
}
'''
    directory = tmp_path_factory.mktemp('stopped-control-pending')
    source, binary = directory / 'probe.c', directory / 'probe'
    source.write_text(prefix + function + '\n' + cases)
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               str(source), '-o', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return binary


@pytest.mark.parametrize('flag', range(8))
def test_actual_pending_predicate_does_not_consume(pending_probe, flag):
    result = subprocess.run([str(pending_probe), str(flag)], capture_output=True,
                            text=True, timeout=3)
    assert result.returncode == 0, (flag, result.stdout, result.stderr)


@pytest.fixture(scope='module')
def source_probe(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('A C compiler is required for native admission source probes')
    production = _new_source(SOURCE)
    # Only include directives are replaced. All declarations, predicates and
    # production transitions below the includes are compiled unchanged.
    production = '\n'.join(line for line in production.splitlines()
                           if not line.startswith('#include ')) + '\n'
    directory = tmp_path_factory.mktemp('stopped-control-source')
    source, binary = directory / 'probe.c', directory / 'probe'
    source.write_text(_STUBS + production + _CASES)
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-Wno-unused-parameter', str(source), '-o', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return binary


CASES = (
    'tokens', 'memory_grammar', 'features_grammar', 'qmp_grammar',
    'breakpoint_bootstrap', 'breakpoint_wrong_type', 'breakpoint_after_arm',
    'arm_identity', 'arm_requires_dispatcher', 'arm_requires_only_cpu',
    'arm_once', 'query_unarmed_inert', 'query_wrong_token_inert', 'retired_query_uses_bound_epoch',
    'generation_before_effect', 'generation_same_byte',
    'generation_partial_failure', 'generation_overflow',
    'unknown_queued_before_arm', 'unknown_qmp_after_arm', 'oob_retires',
    'unknown_gdb_before_arm', 'unknown_gdb_after_arm', 'raw_interrupt_before_arm',
    'mode_suffix_retires', 'unknown_hmp_after_arm', 'reason_first_wins',
    'channel_close_before_arm', 'channel_open_after_arm',
    'prearm_lifetime_allowed', 'armed_lifetime_retires',
    'bootstrap_overlap', 'nested_hmp_explicit', 'nested_hmp_wrong_context',
    'busy_qmp', 'busy_gdb', 'busy_hmp', 'sync_active_before_yield',
    'ram_gap', 'ram_readonly', 'ram_nonvolatile', 'ram_device', 'ram_rom',
    'ram_romd', 'ram_iommu', 'ram_protected', 'ram_guestmemfd',
    'ram_not_ram', 'ram_sections', 'ram_section_oversize', 'ram_section_zero',
    'physical_stopped_cpu_required', 'virtual_bootstrap', 'virtual_after_arm',
    'virtual_paging', 'virtual_custom_debug', 'virtual_non_x86',
    'virtual_bad_asidx', 'virtual_translation_failure', 'virtual_page_crossing',
    'boundary_pending', 'boundary_running', 'boundary_cpu_stop',
    'boundary_replay', 'boundary_migration', 'boundary_checkpoint',
    'boundary_dump', 'boundary_clock_budget', 'boundary_display_fence',
    'boundary_video_fence', 'boundary_video_pending', 'boundary_keys_active',
    'boundary_clock_version', 'boundary_clock_epoch', 'boundary_clock_support',
    'boundary_clock_running', 'boundary_clock_pending', 'boundary_input_epoch',
    'boundary_input_state', 'boundary_input_count', 'boundary_input_token',
    'boundary_input_timing', 'boundary_input_reason', 'boundary_input_descriptor',
    'boundary_keys_epoch', 'boundary_keys_invalid', 'boundary_keys_held',
    'boundary_keys_foreign', 'boundary_keys_modifier', 'boundary_keys_fifo',
    'boundary_keys_fifo_command', 'boundary_keys_write_command',
    'boundary_keys_output', 'boundary_keys_pending', 'boundary_keys_throttle',
    'boundary_keys_scan', 'boundary_keys_disabled',
)


@pytest.mark.parametrize('case', CASES)
def test_exact_stopped_control_source(source_probe, case):
    result = subprocess.run([str(source_probe), case], capture_output=True,
                            text=True, timeout=3)
    assert result.returncode == 0, (case, result.stdout, result.stderr)


_STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define G_N_ELEMENTS(a) (sizeof(a) / sizeof((a)[0]))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define g_new0(Type, count) ((Type *)calloc((count), sizeof(Type)))
#define g_autoptr(Type) Type *
typedef size_t gsize;
typedef struct { bool locked; } QemuMutex;
typedef struct { char bytes[37]; } QemuUUID;
#define UUID_STR_LEN 37
static unsigned scope_locks, uuid_generations;
static bool g_once_init_enter(gsize *value) { return !*value; }
static void g_once_init_leave(gsize *value, gsize result) { *value = result; }
static void qemu_mutex_init(QemuMutex *lock) { lock->locked = false; }
static void qemu_mutex_lock(QemuMutex *lock) {
    assert(!lock->locked); lock->locked = true; ++scope_locks;
}
static void qemu_mutex_unlock(QemuMutex *lock) {
    assert(lock->locked && scope_locks); lock->locked = false; --scope_locks;
}
static void qemu_uuid_generate(QemuUUID *uuid) {
    ++uuid_generations;
    strcpy(uuid->bytes, "17a42ed0-a233-415d-9668-7bbb2213dcff");
}
static void qemu_uuid_unparse(const QemuUUID *uuid, char *out) {
    strcpy(out, uuid->bytes);
}
static size_t g_strlcpy(char *out, const char *in, size_t size) {
    size_t n = strlen(in);
    if (size) { size_t amount = MIN(n, size - 1); memcpy(out, in, amount); out[amount] = 0; }
    return n;
}
static char *g_strdup(const char *value) {
    char *copy = malloc(strlen(value) + 1); assert(copy); strcpy(copy, value); return copy;
}

enum { TYPE_QDict = 1, TYPE_QString, TYPE_QNum };
typedef struct QObject { int type; } QObject;
typedef struct QDictEntry { const char *key; QObject *value; } QDictEntry;
typedef struct QDict { QObject base; size_t count; QDictEntry entries[16]; } QDict;
typedef struct QString { QObject base; const char *value; } QString;
typedef struct QNum { QObject base; bool is_uint; uint64_t value; } QNum;
static void *qcast(QObject *obj, int type) { return obj && obj->type == type ? obj : NULL; }
#define qobject_to(Type, obj) ((Type *)qcast((obj), TYPE_##Type))
static QObject *qdict_get(const QDict *dict, const char *key) {
    for (size_t i = 0; dict && i < dict->count; ++i) {
        if (!strcmp(dict->entries[i].key, key)) return dict->entries[i].value;
    }
    return NULL;
}
static const char *qdict_get_try_str(const QDict *dict, const char *key) {
    QString *value = qobject_to(QString, qdict_get(dict, key));
    return value ? value->value : NULL;
}
static const QDictEntry *qdict_first(const QDict *dict) { return dict->count ? dict->entries : NULL; }
static const QDictEntry *qdict_next(const QDict *dict, const QDictEntry *entry) {
    return entry + 1 < dict->entries + dict->count ? entry + 1 : NULL;
}
static const char *qdict_entry_key(const QDictEntry *entry) { return entry->key; }
static size_t qdict_size(const QDict *dict) { return dict->count; }
static bool qnum_get_try_uint(QNum *number, uint64_t *out) {
    if (!number->is_uint) return false;
    *out = number->value; return true;
}
static QString strings[100]; static unsigned string_count;
static QNum numbers[30]; static unsigned number_count;
static QObject *string(const char *value) {
    assert(string_count < G_N_ELEMENTS(strings));
    QString *out = &strings[string_count++];
    *out = (QString){{TYPE_QString}, value}; return &out->base;
}
static QObject *number(uint64_t value, bool is_uint) {
    assert(number_count < G_N_ELEMENTS(numbers));
    QNum *out = &numbers[number_count++];
    *out = (QNum){{TYPE_QNum}, is_uint, value}; return &out->base;
}
static void put(QDict *dict, const char *key, QObject *value) {
    assert(dict->count < G_N_ELEMENTS(dict->entries));
    dict->entries[dict->count++] = (QDictEntry){key, value};
}
static QDict request, arguments;
static QObject *command(const char *name) {
    request = (QDict){{TYPE_QDict}, 0, {{0}}};
    arguments = (QDict){{TYPE_QDict}, 0, {{0}}};
    string_count = number_count = 0;
    put(&request, "execute", string(name));
    put(&request, "arguments", &arguments.base);
    return &request.base;
}

typedef __int128 Int128;
static bool int128_gt(Int128 a, Int128 b) { return a > b; }
static bool int128_le(Int128 a, Int128 b) { return a <= b; }
static Int128 int128_zero(void) { return 0; }
static Int128 int128_make64(uint64_t a) { return a; }
static uint64_t int128_get64(Int128 a) { return (uint64_t)a; }
typedef struct MemoryRegion {
    bool ram, device, rom, romd, iommu, protected, guestmemfd;
} MemoryRegion;
typedef struct MemoryRegionSection {
    MemoryRegion *mr;
    uint64_t offset_within_address_space;
    Int128 size;
    bool readonly, nonvolatile;
} MemoryRegionSection;
typedef struct AddressSpace { MemoryRegion *root; } AddressSpace;
typedef struct Map { uint64_t start, length; MemoryRegion region; bool readonly, nonvolatile; } Map;
static MemoryRegion physical_root, virtual_root;
static AddressSpace address_space_memory = {&physical_root}, virtual_as = {&virtual_root};
static Map maps[4]; static size_t map_count;
static unsigned region_refs, region_reads;
static int invalid_section;
static bool bql_locked(void) { return true; }
static MemoryRegionSection memory_region_find(MemoryRegion *root, uint64_t address, uint64_t length) {
    assert(!scope_locks); ++region_reads;
    for (size_t i = 0; i < map_count; ++i) {
        Map *map = &maps[i];
        if (address >= map->start && address - map->start < map->length) {
            uint64_t size = MIN(length, map->length - (address - map->start));
            ++region_refs;
            return (MemoryRegionSection){&map->region, address,
                invalid_section == 1 ? (Int128)length + 1 : invalid_section == 2 ? 0 : size,
                map->readonly, map->nonvolatile};
        }
    }
    return (MemoryRegionSection){0};
}
static void memory_region_unref(MemoryRegion *region) { assert(region_refs); --region_refs; }
static bool memory_region_is_ram(MemoryRegion *mr) { return mr->ram; }
static bool memory_region_is_ram_device(MemoryRegion *mr) { return mr->device; }
static bool memory_region_is_rom(MemoryRegion *mr) { return mr->rom; }
static bool memory_region_is_romd(MemoryRegion *mr) { return mr->romd; }
static bool memory_region_is_iommu(MemoryRegion *mr) { return mr->iommu; }
static bool memory_region_is_protected(MemoryRegion *mr) { return mr->protected; }
static bool memory_region_has_guest_memfd(MemoryRegion *mr) { return mr->guestmemfd; }

typedef uint64_t hwaddr;
typedef struct MemTxAttrs { int index; } MemTxAttrs;
typedef struct CPUState CPUState;
typedef struct SysemuCPUOps { bool (*get_paging_enabled)(const CPUState *); } SysemuCPUOps;
typedef struct CPUClass { void *memory_rw_debug; const SysemuCPUOps *sysemu_ops; } CPUClass;
struct CPUState { bool stopped, stop; int num_ases; CPUClass *cc; const char *kind; CPUState *next; };
static CPUState processor, extra_cpu, *cpus = &processor;
static bool paging;
static bool get_paging_enabled(const CPUState *cpu) { return paging; }
static SysemuCPUOps sysemu_ops = {get_paging_enabled};
static CPUClass cpu_class = {NULL, &sysemu_ops};
#define CPU_FOREACH(cpu) for ((cpu) = cpus; (cpu); (cpu) = (cpu)->next)
#define OBJECT(cpu) ((void *)(cpu))
static void *object_dynamic_cast(void *object, const char *name) {
    CPUState *cpu = object; return !strcmp(cpu->kind, name) ? object : NULL;
}
static void (*sync_callback)(void);
static unsigned synchronizations;
static void cpu_synchronize_state(CPUState *cpu) {
    assert(!scope_locks); ++synchronizations;
    if (sync_callback) sync_callback();
}
static int translation_index;
static bool translation_fails;
static uint64_t translation_bias;
static hwaddr cpu_get_phys_page_attrs_debug(CPUState *cpu, uint64_t address, MemTxAttrs *attrs) {
    assert(!scope_locks); attrs->index = translation_index;
    return translation_fails ? (hwaddr)-1 : address + translation_bias;
}
static int cpu_asidx_from_attrs(CPUState *cpu, MemTxAttrs attrs) { return attrs.index; }
static AddressSpace *cpu_get_address_space(CPUState *cpu, int index) { return index ? NULL : &virtual_as; }

typedef struct Error { int code; } Error;
static Error error_value; static unsigned error_count;
static void error_setg(Error **errp, const char *message, ...) {
    ++error_count; if (errp) *errp = &error_value;
}
typedef enum { RUN_STATE_PRELAUNCH, RUN_STATE_DEBUG, RUN_STATE_PAUSED, RUN_STATE_RUNNING } RunState;
static RunState run_state = RUN_STATE_DEBUG;
static bool runstate_check(RunState state) { return run_state == state; }
enum { REPLAY_MODE_NONE, REPLAY_MODE_RECORD };
static int replay_mode;
static bool migration_busy, checkpoint_busy, dump_busy, system_pending;
static bool clock_budget, display_fence, video_fence, video_pending, keys_active;
static bool migration_is_running(void) { return migration_busy; }
static bool fdisbull_instrumented_checkpoint_busy(void) { return checkpoint_busy; }
static bool qemu_system_dump_in_progress(void) { return dump_busy; }
static bool fdisbull_stopped_control_system_pending(void) { return system_pending; }
static bool fdisbull_clock_budget_active(void) { return clock_budget; }
static bool fdisbull_display_frame_fence_blocks_control(void) { return display_fence; }
static bool fdisbull_video_frame_fence_blocks_control(void) { return video_fence; }
static bool fdisbull_video_frame_stop_pending(void) { return video_pending; }
static bool fdisbull_frame_keys_active(void) { return keys_active; }
typedef struct FdisbullClockInfo {
    int api_version; uint64_t epoch; bool budget_supported, running, pending_stop;
} FdisbullClockInfo;
enum { FDISBULL_INPUT_STATE_IDLE, FDISBULL_INPUT_STATE_COMPLETED };
typedef struct FdisbullInputInfo {
    uint64_t epoch, event_count; int state; char *token, *reason;
    bool has_start_ns, has_deadline_ns, has_terminal_ns, has_dispatch_ns;
    void *retrace, *press, *typing, *click, *motion;
} FdisbullInputInfo;
typedef struct FdisbullFrameKeysInfo {
    uint64_t epoch; uint32_t modifier_mask; int64_t fifo_count;
    uint8_t controller_status, controller_mode, controller_pending;
    bool valid, active, scan_enabled;
    void *held, *foreign_held;
    int64_t fifo_command_pointer, write_command, throttle_deadline_ns;
} FdisbullFrameKeysInfo;
static FdisbullClockInfo clock_info;
static FdisbullInputInfo input_info;
static FdisbullFrameKeysInfo keys_info;
static unsigned clock_reads;
static FdisbullClockInfo *qmp_x_fdisbull_query_clock(Error **errp) {
    assert(!scope_locks); ++clock_reads;
    FdisbullClockInfo *out = g_new0(FdisbullClockInfo, 1); *out = clock_info; return out;
}
static FdisbullInputInfo *qmp_x_fdisbull_query_input(Error **errp) {
    assert(!scope_locks);
    FdisbullInputInfo *out = g_new0(FdisbullInputInfo, 1); *out = input_info; return out;
}
static FdisbullFrameKeysInfo *qmp_x_fdisbull_query_frame_keys(Error **errp) {
    assert(!scope_locks);
    FdisbullFrameKeysInfo *out = g_new0(FdisbullFrameKeysInfo, 1); *out = keys_info; return out;
}
typedef enum { FDISBULL_STOPPED_CONTROL_STATE_ARMED, FDISBULL_STOPPED_CONTROL_STATE_RETIRED } FdisbullStoppedControlState;
typedef struct FdisbullStoppedControlInfo {
    int api_version; char *model, *process_id, *token, *reason;
    uint64_t generation, epoch; FdisbullStoppedControlState state; bool busy;
} FdisbullStoppedControlInfo;
'''


_CASES = r'''
static const char *token = "0123456789abcdef0123456789abcdef";
static void setup(void) {
    processor = (CPUState){true, false, 1, &cpu_class, "x86_64-cpu", NULL};
    clock_info = (FdisbullClockInfo){1, 99, true, false, false};
    input_info.epoch = 99;
    keys_info.epoch = 99; keys_info.valid = keys_info.scan_enabled = true;
    keys_info.fifo_command_pointer = keys_info.write_command = keys_info.throttle_deadline_ns = -1;
    maps[0] = (Map){0, 0x100000, {true, false, false, false, false, false, false}, false, false};
    map_count = 1;
}
static FdisbullStoppedControlInfo *arm(void) {
    Error *err = NULL;
    QObject *req = command("x-fdisbull-arm-stopped-control");
    put(&arguments, "token", string(token));
    fdisbull_stopped_control_qmp_received(req);
    fdisbull_stopped_control_qmp_enter(req);
    FdisbullStoppedControlInfo *info = qmp_x_fdisbull_arm_stopped_control(token, &err);
    fdisbull_stopped_control_qmp_leave();
    return info;
}
static void gdb(const char *packet, bool physical) {
    fdisbull_stopped_control_gdb_enter(packet, &processor, physical);
    fdisbull_stopped_control_gdb_leave();
}
static void sync_assert_active(void) {
    assert(control.gdb_active == 1 && !scope_locks);
    fdisbull_stopped_control_qmp_received(command("system_reset"));
}
static void assert_retired(const char *reason) {
    assert(control.armed && control.retired && control.tainted);
    assert(!strcmp(control.reason, reason));
}
static bool choose(const char *which, const char *name) { return !strcmp(which, name); }

int main(int argc, char **argv) {
    assert(argc == 2); const char *which = argv[1]; setup();
    if (choose(which, "tokens")) {
        assert(control_token(token));
        assert(!control_token(NULL)); assert(!control_token(""));
        assert(!control_token("0123456789abcdef0123456789abcde"));
        assert(!control_token("0123456789abcdef0123456789abcdef0"));
        assert(!control_token("0123456789Abcdef0123456789abcdef"));
        assert(!control_token("0123456789abcdef0123456789abcdeg"));
    } else if (choose(which, "memory_grammar")) {
        static const char *const good[] = {"m0,1", "m10,800", "mFFFFFFFFFFFFFFFF,1", "M22be4,1:01", "M0,2:00FF"};
        static const char *const bad[] = {"", "m", "m0,0", "m0,801", "m,1", "m0,", "m0,1x", "m0,1;", "mffffffffffffffff,2", "m10000000000000000,1", "m0,10000000000000000", "M0,1:", "M0,1:0", "M0,1:0000", "M0,1:gg", "M0,1:00;", "X0,1:00", "m-1,1", "m0x1,1"};
        uint64_t address, length;
        for (size_t i = 0; i < G_N_ELEMENTS(good); ++i) assert(control_memory_packet(good[i], &address, &length));
        for (size_t i = 0; i < G_N_ELEMENTS(bad); ++i) assert(!control_memory_packet(bad[i], &address, &length));
    } else if (choose(which, "features_grammar")) {
        assert(control_features_packet("qXfer:features:read:target.xml:0,1000"));
        assert(control_features_packet("qXfer:features:read:i386-32bit.xml:ffff,1"));
        static const char *const bad[] = {"qXfer:features:read:other.xml:0,1", "qXfer:features:read:target.xml:0,0", "qXfer:features:read:target.xml:0,1001", "qXfer:features:read:target.xml:ffff,2", "qXfer:features:read:target.xml:0,1suffix", "qXfer:features:read:target.xml:10000000000000000,1"};
        for (size_t i = 0; i < G_N_ELEMENTS(bad); ++i) assert(!control_features_packet(bad[i]));
    } else if (choose(which, "qmp_grammar")) {
        assert(!control_qmp_allowed(NULL, false));
        QObject *req = command("query-status"); assert(control_qmp_allowed(req, true));
        put(&arguments, "unexpected", string("value")); assert(!control_qmp_allowed(req, true));
        req = command("human-monitor-command"); put(&arguments, "command-line", string("info registers")); assert(control_qmp_allowed(req, true));
        arguments.entries[0].value = string("info registers; stop"); assert(!control_qmp_allowed(req, false));
        req = command("x-fdisbull-query-stopped-control"); put(&arguments, "token", string("ffffffffffffffffffffffffffffffff")); assert(control_qmp_allowed(req, true));
        req = command("x-fdisbull-arm-stopped-control"); put(&arguments, "token", string(token)); assert(control_qmp_allowed(req, false)); assert(!control_qmp_allowed(req, true));
        req = command("cont"); assert(control_qmp_allowed(req, false)); assert(!control_qmp_allowed(req, true));
        req = command("x-fdisbull-arm-video-frame");
        put(&arguments, "token", string("fence")); put(&arguments, "stream-token", string("stream"));
        put(&arguments, "expected-stream-generation", number(UINT64_MAX, true));
        put(&arguments, "expected-frame-sequence", number(2, true)); put(&arguments, "expected-epoch", number(3, true));
        assert(control_qmp_allowed(req, false)); arguments.entries[2].value = number(1, false); assert(!control_qmp_allowed(req, false));
        req = command("query-status"); request.entries[1].value = string("not an object"); assert(!control_qmp_allowed(req, false));
    } else if (choose(which, "breakpoint_bootstrap")) {
        gdb("Z1,22be4,1", false); gdb("z1,22be4,1", false);
        assert(!control.tainted && !control.generation && synchronizations == 2);
    } else if (choose(which, "breakpoint_wrong_type")) {
        gdb("Z0,22be4,1", false); assert(control.tainted && !arm());
    } else if (choose(which, "breakpoint_after_arm")) {
        assert(arm()); gdb("Z1,22be4,1", false); assert_retired("unsupported-gdb-control");
    } else if (choose(which, "arm_identity")) {
        FdisbullStoppedControlInfo *info = arm(); assert(info);
        assert(info->api_version == 1 && !strcmp(info->model, "qemu-stopped-control-v1"));
        assert(!strcmp(info->process_id, "17a42ed0-a233-415d-9668-7bbb2213dcff"));
        assert(!strcmp(info->token, token) && info->generation == 0 && info->epoch == 99);
        assert(!info->busy && !info->reason && info->state == FDISBULL_STOPPED_CONTROL_STATE_ARMED);
        assert(uuid_generations == 1);
    } else if (choose(which, "arm_requires_dispatcher")) {
        Error *err = NULL; assert(!qmp_x_fdisbull_arm_stopped_control(token, &err)); assert(err && !control.armed);
    } else if (choose(which, "arm_requires_only_cpu")) {
        extra_cpu = processor; processor.next = &extra_cpu; assert(!arm() && !control.armed);
    } else if (choose(which, "arm_once")) {
        assert(arm()); assert(!arm()); assert_retired("unsupported-qmp-control");
    } else if (choose(which, "query_unarmed_inert")) {
        Error *err = NULL;
        assert(!qmp_x_fdisbull_query_stopped_control(token, &err));
        assert(err && !control.armed && !control.retired && !control.tainted);
    } else if (choose(which, "query_wrong_token_inert")) {
        assert(arm()); Error *err = NULL;
        assert(!qmp_x_fdisbull_query_stopped_control("ffffffffffffffffffffffffffffffff", &err));
        assert(err && !control.retired && !control.tainted && control.generation == 0);
    } else if (choose(which, "retired_query_uses_bound_epoch")) {
        assert(arm()); fdisbull_stopped_control_lifetime("clock-retired");
        clock_info.epoch = 100; unsigned reads = clock_reads;
        FdisbullStoppedControlInfo *info = qmp_x_fdisbull_query_stopped_control(token, NULL);
        assert(info && info->epoch == 99 && clock_reads == reads);
        assert(info->state == FDISBULL_STOPPED_CONTROL_STATE_RETIRED && !strcmp(info->reason, "clock-retired"));
    } else if (choose(which, "generation_before_effect") || choose(which, "generation_same_byte") || choose(which, "generation_partial_failure")) {
        assert(arm()); unsigned simulated_effects = 0; unsigned char bytes[2] = {0xaa, 0xbb};
        fdisbull_stopped_control_gdb_enter("M10,2:aabb", &processor, true);
        assert(control.generation == 1 && control.gdb_active == 1 && !simulated_effects);
        if (choose(which, "generation_partial_failure")) { bytes[0] = 0xaa; simulated_effects = 1; }
        else { bytes[0] = 0xaa; bytes[1] = 0xbb; simulated_effects = 2; }
        fdisbull_stopped_control_gdb_leave();
        assert(bytes[0] == 0xaa && bytes[1] == 0xbb && simulated_effects);
        assert(control.generation == 1 && !control.retired && !control.gdb_active);
        if (choose(which, "generation_same_byte")) { gdb("M10,2:aabb", true); assert(control.generation == 2); }
    } else if (choose(which, "generation_overflow")) {
        assert(arm()); control.generation = UINT64_MAX; gdb("M10,1:01", true);
        assert(control.generation == UINT64_MAX); assert_retired("generation-exhausted");
    } else if (choose(which, "unknown_queued_before_arm")) {
        fdisbull_stopped_control_qmp_received(command("system_reset")); assert(!arm());
        assert(control.tainted && !control.armed && !control.retired);
    } else if (choose(which, "unknown_qmp_after_arm") || choose(which, "oob_retires")) {
        assert(arm()); QObject *req = command("query-status");
        if (choose(which, "oob_retires")) put(&request, "exec-oob", string("query-status"));
        else req = command("system_reset");
        fdisbull_stopped_control_qmp_received(req); assert_retired("unsupported-qmp-control");
    } else if (choose(which, "unknown_gdb_before_arm")) {
        gdb("P0=01", true); assert(control.tainted && !control.retired && !arm());
    } else if (choose(which, "raw_interrupt_before_arm")) {
        fdisbull_stopped_control_reject("gdb-raw-interrupt");
        assert(control.tainted && !control.retired && !arm());
    } else if (choose(which, "mode_suffix_retires")) {
        assert(arm()); gdb("Qqemu.PhyMemMode:1suffix", true); assert_retired("unsupported-gdb-control");
    } else if (choose(which, "unknown_gdb_after_arm")) {
        assert(arm()); gdb("P0=01", true); assert_retired("unsupported-gdb-control");
    } else if (choose(which, "unknown_hmp_after_arm")) {
        assert(arm()); fdisbull_stopped_control_hmp_enter("info registers ", false);
        assert_retired("unsupported-hmp-control"); fdisbull_stopped_control_hmp_leave();
    } else if (choose(which, "reason_first_wins")) {
        assert(arm()); char reason[200]; memset(reason, 'r', sizeof(reason) - 1); reason[199] = 0;
        fdisbull_stopped_control_reject(reason); fdisbull_stopped_control_reject("later");
        assert(strlen(control.reason) == 128 && !strncmp(control.reason, reason, 128));
    } else if (choose(which, "channel_close_before_arm")) {
        fdisbull_stopped_control_channel("closed", false); assert(!arm() && control.tainted);
    } else if (choose(which, "channel_open_after_arm")) {
        fdisbull_stopped_control_channel("initial-open", true); assert(arm());
        fdisbull_stopped_control_channel("second-open", true); assert_retired("second-open");
    } else if (choose(which, "prearm_lifetime_allowed")) {
        fdisbull_stopped_control_lifetime("bootstrap-reset"); assert(arm());
    } else if (choose(which, "armed_lifetime_retires")) {
        assert(arm()); fdisbull_stopped_control_lifetime("runstate"); assert_retired("runstate");
    } else if (choose(which, "bootstrap_overlap")) {
        fdisbull_stopped_control_qmp_enter(command("query-status")); gdb("g", true);
        fdisbull_stopped_control_qmp_leave(); assert(control.tainted && !arm());
    } else if (choose(which, "nested_hmp_explicit") || choose(which, "nested_hmp_wrong_context")) {
        QObject *req = command("human-monitor-command"); put(&arguments, "command-line", string("info registers"));
        fdisbull_stopped_control_qmp_enter(req);
        fdisbull_stopped_control_hmp_enter("info registers", choose(which, "nested_hmp_explicit"));
        fdisbull_stopped_control_hmp_leave(); fdisbull_stopped_control_qmp_leave();
        assert(control.tainted == choose(which, "nested_hmp_wrong_context"));
    } else if (choose(which, "busy_qmp") || choose(which, "busy_gdb") || choose(which, "busy_hmp")) {
        assert(arm()); fdisbull_stopped_control_qmp_enter(command("query-status"));
        if (choose(which, "busy_qmp")) fdisbull_stopped_control_qmp_enter(&request.base);
        if (choose(which, "busy_gdb")) fdisbull_stopped_control_gdb_enter("m10,1", &processor, true);
        if (choose(which, "busy_hmp")) fdisbull_stopped_control_hmp_enter("info registers", true);
        assert(qmp_x_fdisbull_query_stopped_control(token, NULL)->busy);
        if (choose(which, "busy_qmp")) fdisbull_stopped_control_qmp_leave();
        if (choose(which, "busy_gdb")) fdisbull_stopped_control_gdb_leave();
        if (choose(which, "busy_hmp")) fdisbull_stopped_control_hmp_leave();
        assert(!qmp_x_fdisbull_query_stopped_control(token, NULL)->busy);
        fdisbull_stopped_control_qmp_leave();
    } else if (choose(which, "sync_active_before_yield")) {
        sync_callback = sync_assert_active; gdb("M22be4,1:01", false);
        assert(synchronizations == 1 && control.tainted && !control.gdb_active && !arm());
    } else if (!strncmp(which, "ram_", 4)) {
        assert(arm());
        if (choose(which, "ram_gap")) maps[0].length = 0x11;
        else if (choose(which, "ram_readonly")) maps[0].readonly = true;
        else if (choose(which, "ram_nonvolatile")) maps[0].nonvolatile = true;
        else if (choose(which, "ram_device")) maps[0].region.device = true;
        else if (choose(which, "ram_rom")) maps[0].region.rom = true;
        else if (choose(which, "ram_romd")) maps[0].region.romd = true;
        else if (choose(which, "ram_iommu")) maps[0].region.iommu = true;
        else if (choose(which, "ram_protected")) maps[0].region.protected = true;
        else if (choose(which, "ram_guestmemfd")) maps[0].region.guestmemfd = true;
        else if (choose(which, "ram_not_ram")) maps[0].region.ram = false;
        else if (choose(which, "ram_section_oversize")) invalid_section = 1;
        else if (choose(which, "ram_section_zero")) invalid_section = 2;
        else if (choose(which, "ram_sections")) {
            maps[1] = maps[0]; maps[0].length = 0x11; maps[1].start = 0x11; map_count = 2;
        } else assert(false);
        gdb("M10,2:0102", true); assert(!region_refs);
        if (choose(which, "ram_sections")) assert(!control.retired && control.generation == 1 && region_reads == 2);
        else { assert_retired("unsupported-gdb-control"); assert(control.generation == 0); }
    } else if (choose(which, "physical_stopped_cpu_required")) {
        assert(arm()); processor.stopped = false; gdb("M10,1:01", true); assert_retired("unsupported-gdb-control");
    } else if (!strncmp(which, "virtual_", 8)) {
        if (choose(which, "virtual_after_arm")) assert(arm());
        else if (choose(which, "virtual_paging")) paging = true;
        else if (choose(which, "virtual_custom_debug")) cpu_class.memory_rw_debug = &processor;
        else if (choose(which, "virtual_non_x86")) processor.kind = "arm-cpu";
        else if (choose(which, "virtual_bad_asidx")) translation_index = 1;
        else if (choose(which, "virtual_translation_failure")) translation_fails = true;
        else if (!choose(which, "virtual_bootstrap") && !choose(which, "virtual_page_crossing")) assert(false);
        gdb(choose(which, "virtual_page_crossing") ? "Mfff,2:0102" : "M22be4,1:01", false);
        if (choose(which, "virtual_bootstrap") || choose(which, "virtual_page_crossing")) {
            assert(!control.tainted && !control.generation && synchronizations == 1);
            assert(region_reads == (choose(which, "virtual_page_crossing") ? 2U : 1U));
        } else assert(control.tainted && !control.generation);
        assert(!region_refs);
    } else if (!strncmp(which, "boundary_", 9)) {
        if (choose(which, "boundary_pending")) system_pending = true;
        else if (choose(which, "boundary_running")) run_state = RUN_STATE_RUNNING;
        else if (choose(which, "boundary_cpu_stop")) processor.stop = true;
        else if (choose(which, "boundary_replay")) replay_mode = REPLAY_MODE_RECORD;
        else if (choose(which, "boundary_migration")) migration_busy = true;
        else if (choose(which, "boundary_checkpoint")) checkpoint_busy = true;
        else if (choose(which, "boundary_dump")) dump_busy = true;
        else if (choose(which, "boundary_clock_budget")) clock_budget = true;
        else if (choose(which, "boundary_display_fence")) display_fence = true;
        else if (choose(which, "boundary_video_fence")) video_fence = true;
        else if (choose(which, "boundary_video_pending")) video_pending = true;
        else if (choose(which, "boundary_keys_active")) keys_active = true;
        else if (choose(which, "boundary_clock_version")) clock_info.api_version = 2;
        else if (choose(which, "boundary_clock_epoch")) clock_info.epoch = 0;
        else if (choose(which, "boundary_clock_support")) clock_info.budget_supported = false;
        else if (choose(which, "boundary_clock_running")) clock_info.running = true;
        else if (choose(which, "boundary_clock_pending")) clock_info.pending_stop = true;
        else if (choose(which, "boundary_input_epoch")) input_info.epoch = 98;
        else if (choose(which, "boundary_input_state")) input_info.state = FDISBULL_INPUT_STATE_COMPLETED;
        else if (choose(which, "boundary_input_count")) input_info.event_count = 1;
        else if (choose(which, "boundary_input_token")) input_info.token = "old";
        else if (choose(which, "boundary_input_timing")) input_info.has_terminal_ns = true;
        else if (choose(which, "boundary_input_reason")) input_info.reason = "old";
        else if (choose(which, "boundary_input_descriptor")) input_info.press = &processor;
        else if (choose(which, "boundary_keys_epoch")) keys_info.epoch = 98;
        else if (choose(which, "boundary_keys_invalid")) keys_info.valid = false;
        else if (choose(which, "boundary_keys_held")) keys_info.held = &processor;
        else if (choose(which, "boundary_keys_foreign")) keys_info.foreign_held = &processor;
        else if (choose(which, "boundary_keys_modifier")) keys_info.modifier_mask = 1;
        else if (choose(which, "boundary_keys_fifo")) keys_info.fifo_count = 1;
        else if (choose(which, "boundary_keys_fifo_command")) keys_info.fifo_command_pointer = 0;
        else if (choose(which, "boundary_keys_write_command")) keys_info.write_command = 0;
        else if (choose(which, "boundary_keys_output")) keys_info.controller_status = 1;
        else if (choose(which, "boundary_keys_pending")) keys_info.controller_pending = true;
        else if (choose(which, "boundary_keys_throttle")) keys_info.throttle_deadline_ns = 0;
        else if (choose(which, "boundary_keys_scan")) keys_info.scan_enabled = false;
        else if (choose(which, "boundary_keys_disabled")) keys_info.controller_mode = 0x10;
        else assert(false);
        assert(!arm() && !control.armed && error_count);
    } else { fprintf(stderr, "Unknown case: %s\n", which); return 2; }
    assert(!scope_locks && !region_refs && !control.qmp_active && !control.gdb_active && !control.hmp_active);
    return 0;
}
'''
