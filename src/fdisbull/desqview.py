"""DESQview service facts and an authored cooperative guest probe.

The API version is the kernel's binary major/minor pair, not the product label
or packed BCD.  For example, the supplied DV/X 2.1 kernel reports 2.71.  Probe
reports describe guest-reported values; parsing alone never proves freshness.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import struct


REFERENCE = 'https://fd.lod.bz/rbil/interrup/quarterdeck/'
QUARTERDECK_REFERENCE = 'https://ftpmirror1.infania.net/pub/simtelnet/msdos/qtrdeck/qw_sep92.zip'
REPORT_SIZE = 64
MAX_YIELDS = 4096

# name, inputs, outputs, minimum kernel version, effect
SERVICES = {
    0x1000: ('pause', {}, {}, '1.00', 'Yield the remainder of this task time slice; not a host sleep or a timing guarantee.'),
    0x101a: ('other_stack', {}, {}, '1.00', 'Switch to the task internal stack; this is not BEGINC.'),
    0x101b: ('begin_critical', {}, {}, '1.00', 'Increment the task critical nesting; pair every call with ENDC.'),
    0x101c: ('end_critical', {}, {}, '1.00', 'Decrement the task critical nesting; unmatched calls are not a safe yield.'),
    0x1022: ('get_version', {'bx': 'zero for query'}, {'bx': 'TopView compatibility version: BL=major, BH=minor'}, '1.00',
             'TopView compatibility query; DESQview 2.00+ returns 0A01h. Not the DESQview kernel or product version.'),
    0x1024: ('get_virtual_screen', {'bx': 'window handle segment; zero selects default'},
             {'es:di': 'virtual screen pointer', 'cx': 'buffer bytes', 'dl': '0=text, 1=graphics'}, '1.00',
             'Return a task-relative virtual buffer; do not assume physical B8000 or permanent ownership.'),
    0x1025: ('user_stack', {}, {}, '1.00', 'Restore the user stack paired with OSTACK.'),
    0x1117: ('assert_mapping', {'bx': 'zero=query; nonzero=requested mapping context'},
             {'bx': 'previous/current mapping context', 'ax': 'zero on query in inspected kernels'}, '2.20',
             'BX=0 observes; BX!=0 changes mapping and can invalidate pointers.'),
    0xde07: ('application_number', {}, {'ax': 'current menu program number'}, '2.00',
             'A program-number hint, not a unique task lifetime or allocation identity.'),
    0xde13: ('critical_count', {}, {'bx': 'critical-section nesting count'}, '2.20',
             'Observe critical nesting; does not acquire a lock.'),
    0xde17: ('assert_mapping', {'bx': 'zero=query; nonzero=requested mapping context'},
             {'bx': 'previous/current mapping context', 'ax': 'zero on query in inspected kernels'}, '2.26',
             'Do not issue DE17 to an older kernel; use 1117 for 2.20 through 2.25.'),
}


def _word(registers, name):
    value = registers.get(name)
    if type(value) is int and 0 <= value <= 65535:
        return value
    if name in ('ax', 'bx', 'cx', 'dx'):
        high, low = (registers.get(name[0] + part) for part in ('h', 'l'))
        if type(high) is int and type(low) is int and 0 <= high <= 255 and 0 <= low <= 255:
            return high * 256 + low
    return None


def describe_interrupt(vector, registers):
    """Recognize complete selectors, without declaring a live handler present."""
    ax, bx = _word(registers, 'ax'), _word(registers, 'bx')
    ah = ax >> 8 if ax is not None else registers.get('ah')
    if vector == 0x21:
        if (ax, _word(registers, 'cx'), _word(registers, 'dx')) != (0x2b01, 0x4445, 0x5351):
            return None
        name, inputs, outputs, minimum, effect = ('installation_check',
            {'ax': '2B01h', 'cx': '4445h (DE)', 'dx': '5351h (SQ)'},
            {'al': 'FFh=absent; otherwise DESQview present', 'bx': 'binary major/minor kernel version if present'},
            '1.00', 'Invalid DOS date when DESQview is absent; no DESQview INT15 call before this guard.')
    elif vector == 0x15 and ax in SERVICES:
        if ax == 0x1022 and bx != 0:
            return None
        name, inputs, outputs, minimum, effect = SERVICES[ax]
    elif vector == 0x10 and ah in (0xfe, 0xff):
        name, inputs, outputs, minimum, effect = (
            'virtual_video_address' if ah == 0xfe else 'video_buffer_update',
            {'es:di': 'caller video pointer'}, {'es:di': 'virtual video pointer'} if ah == 0xfe else {},
            '1.00', 'DESQview/TopView video cooperation; presence and installed handler must be verified.')
    else:
        return None
    result = dict(vector=hex(vector), function=hex(ax) if ax is not None else hex(ah << 8),
                  family='desqview', known=True, name=name, minimum_version=minimum,
                  inputs={key: dict(role=role, value=_word(registers,key)) for key,role in inputs.items()},
                  outputs=deepcopy(outputs), memory_effects=[], memory_effects_complete=False,
                  terminates=False, runtime_observed=False, handler_verified=False, outcome='unknown',
                  source=REFERENCE + 'index.html', effect=effect,
                  evidence='documented API selector; original-kernel slice checks are separate evidence',
                  assumptions=['A known selector is not proof the DESQview interrupt handler is installed.',
                               'Kernel API version and current mapping must be observed before invoking a service.',
                               'Unspecified register preservation and complete memory effects remain unmodeled.'])
    if ax in (0x1117, 0xde17):
        result['mapping_operation'] = 'query' if bx == 0 else 'set' if bx is not None else 'unknown'
    return result


def service_catalog():
    return [describe_interrupt(0x21, dict(ax=0x2b01,cx=0x4445,dx=0x5351))] + [
        describe_interrupt(0x15, dict(ax=selector, bx=0)) for selector in SERVICES] + [
        describe_interrupt(0x10, dict(ah=ah)) for ah in (0xfe,0xff)]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_report(data):
    if type(data) is not bytes or len(data) != REPORT_SIZE or data[:8] != b'FDVAPI01':
        raise ValueError('DESQview report requires exactly 64 bytes and the FDVAPI01 signature')
    size, status, version = struct.unpack_from('<3H', data, 8)
    detection = data[14]
    selector, mapping, app, segment, offset, length = struct.unpack_from('<6H', data, 16)
    screen_type = data[28]
    requested, completed, flags = struct.unpack_from('<3H', data, 30)
    ticks_before, ticks_after, balance = struct.unpack_from('<IIH', data, 52)
    if size != REPORT_SIZE or status not in (0,1,2) or data[15] or data[29] or any(data[62:64]) or balance:
        raise ValueError('Incomplete or inconsistent DESQview probe report')
    if not 0 <= completed <= requested <= MAX_YIELDS:
        raise ValueError('Invalid bounded DESQview pause counts')
    present = detection != 0xff
    supported = present and version >> 8 >= 2
    expected_status = 0 if supported else 2 if present else 1
    expected_selector = (0xde17 if version >= 0x021a else 0x1117 if version >= 0x0214 else 0) if supported else 0
    expected_flags = 0x3d | (2 if expected_selector else 0) if supported else 0x10
    if status != expected_status or flags != expected_flags or selector != expected_selector:
        raise ValueError('DESQview report disagrees with its presence/version guard')
    if supported:
        if completed != requested or screen_type not in (0,1) or app > 255:
            raise ValueError('Incomplete DESQview cooperation or invalid screen/task result')
        if not expected_selector and mapping:
            raise ValueError('Unexpected mapping value before the ASSERTMAP version gate')
    elif any(data[16:30]) or completed or ticks_before or ticks_after or (not present and version):
        raise ValueError('Absent/unsupported DESQview report claims an unexecuted API result')
    return dict(format='fdisbull-desqview-report-1', sha256=_sha(data), length=len(data),
                status={0:'complete',1:'absent',2:'unsupported-kernel'}[status], complete=True,
                desqview=dict(present=present, kernel_version=f'{version >> 8}.{version & 255:02d}' if present else None,
                              raw_version_bx=hex(version), detection_al=hex(detection), product_version='not_inferred'),
                mapping=dict(selector=hex(selector) if selector else None, handle=hex(mapping) if selector else None,
                             queried=bool(selector), changed=False, lifetime='not_established'),
                application=dict(number=app if supported else None, identity_strength='menu number only; reusable'),
                screen=dict(segment=hex(segment), offset=hex(offset), length=length,
                            kind={0:'text',1:'graphics'}.get(screen_type) if supported else None,
                            linear_address=hex(segment * 16 + offset) if supported else None,
                            address_scope='guest-reported task-relative pointer; mapping/freshness required before reads'),
                cooperation=dict(requested_yields=requested, returned_yields=completed,
                                 critical_balance=balance, critical_scope='short metadata queries only; no DOS I/O or waits'),
                nonce=data[36:52].hex(), ticks=dict(before=ticks_before, after=ticks_after),
                evidence='guest-reported API results; producer, task lifetime and freshness not established by parsing',
                native_execution_validation='not_established_by_report')


def probe_bytes(*, mode='file', yields=0, nonce=None):
    if mode not in ('file','breakpoint') or type(yields) is not int or not 0 <= yields <= MAX_YIELDS:
        raise ValueError('DESQview probe requires file/breakpoint mode and 0..4096 yields')
    if nonce is None:
        nonce = '00' * 16
    if not isinstance(nonce,str) or len(nonce) != 32:
        raise ValueError('DESQview nonce must be 16 hexadecimal bytes')
    try:
        nonce_bytes = bytes.fromhex(nonce)
    except ValueError:
        raise ValueError('Invalid DESQview nonce') from None
    if len(nonce_bytes) != 16:
        raise ValueError('Invalid DESQview nonce')
    root = files('fdisbull').joinpath('data')
    asset = json.loads(root.joinpath('desqview-probe.json').read_text())
    source = root.joinpath('FdisbullDesqviewProbe.txt').read_bytes()
    program = bytearray.fromhex(asset['program_hex'])
    if (_sha(source) != asset['source_sha256'] or _sha(program) != asset['program_sha256']
            or asset['format'] != 'fdisbull-desqview-probe-1' or len(program) > 0xff00):
        raise ValueError('Packaged DESQview probe source/byte identity mismatch')
    report_offset = asset['report_com_offset']
    if type(report_offset) is not int or type(asset['report_length']) is not int or asset['report_length'] != REPORT_SIZE:
        raise ValueError('Invalid packaged DESQview report extent')
    report = report_offset - 0x100
    if report < 0 or report + REPORT_SIZE != len(program) or program[report:report+8] != b'FDVAPI01':
        raise ValueError('Invalid packaged DESQview report extent')
    ready, release = asset['ready_com_offset'], asset['release_com_offset']
    if (type(ready) is not int or type(release) is not int
            or not 0x100 <= ready < report_offset - 6 or release != report_offset - 1
            or program[release - 0x100] != 0
            or program[ready - 0x100:ready - 0x100 + 6] != b'\x2e\x80\x3e' + struct.pack('<H', release) + b'\x00'):
        raise ValueError('Invalid packaged DESQview ready/release endpoints')
    mode_offset = asset['mode_file_offset']
    if type(mode_offset) is not int or not 0 <= mode_offset < report or program[mode_offset] != 0:
        raise ValueError('Invalid packaged DESQview mode offset')
    program[mode_offset] = 1 if mode == 'file' else 0
    struct.pack_into('<H', program, report + 30, yields)
    program[report + 36:report + 52] = nonce_bytes
    return bytes(program), {key:value for key,value in asset.items() if key != 'program_hex'}


def write_probe(output, *, mode='file', yields=0, nonce=None):
    program, asset = probe_bytes(mode=mode, yields=yields, nonce=nonce)
    selected = Path(output).expanduser().resolve()
    if selected.exists():
        if not selected.is_file() or selected.stat().st_size != len(program) or selected.read_bytes() != program:
            raise ValueError('DESQview helper output already exists with different bytes')
        written = False
    else:
        with selected.open('xb') as stream:
            stream.write(program)
        written = True
    return dict(format='fdisbull-desqview-probe-export-1', output=str(selected), written=written,
                sha256=_sha(program), length=len(program), source_sha256=asset['source_sha256'],
                mode=mode, yields=yields, execution='not_run', minimum_cpu='80286',
                report=dict(length=REPORT_SIZE, com_offset=asset['report_com_offset'],
                            ready_com_offset=asset['ready_com_offset'], release_com_offset=asset['release_com_offset'],
                            location='FDVAPI.BIN' if mode == 'file' else 'CS:report offset at the report-ready breakpoint',
                            release='Guarded change of release byte from 0 to 1, then resume'),
                scope='Presence-gated bounded yields and short paired critical metadata queries; never a scheduler replacement.')


def inspect_module(path, *, expected_type=None, expected_version=None):
    """Inspect a raw DESQview module using its own loader contract.

    Older modules have no universal byte magic. A caller-supplied type name is
    required to qualify their descriptor; a plausible leading word alone is
    not a format identification. The exported offsets remain module-relative.
    """
    from .qemm_runtime import _file
    selected, data = _file(path, 4 * 1024 * 1024, 'DESQview module')
    if expected_version is not None and (type(expected_version) is not int or not 0 <= expected_version <= 65535):
        raise ValueError('Expected interface version must be an unsigned 16-bit integer')
    if expected_type is not None:
        if not isinstance(expected_type,str) or not 1 <= len(expected_type) <= 64 or any(not 32 <= ord(ch) < 127 for ch in expected_type):
            raise ValueError('Expected module type must be 1..64 printable ASCII characters')
    elif expected_version is not None:
        raise ValueError('An expected interface version requires its caller type descriptor')
    result = dict(format='fdisbull-desqview-module-1', path=str(selected), sha256=_sha(data), length=len(data),
                  recognized=False, generation=None, entry=None, descriptor=None,
                  dos_device_header=False, launchable_as_dos_program=False, executed=False,
                  address_scope='raw module-relative offsets; runtime segment and relocation are loader state',
                  evidence='bounded structural inspection using contracts observed in original DESQview loaders',
                  limitations=['Recognition does not establish successful initialization or complete ABI compatibility.',
                               'Do not launch a DVR as a COM, MZ program or DOS SYS driver.',
                               'Export table contents, relocation and later callbacks need separate evidence.'])
    if len(data) >= 8 and data[4:8] == b'DVdx':
        if expected_type is not None:
            raise ValueError('Caller type descriptors apply to the older module format, not DVdx')
        jump = (3 + struct.unpack_from('<h',data,1)[0]) & 65535 if data[0] == 0xe9 else None
        if jump is not None and jump >= len(data):
            raise ValueError('DVdx initial jump leaves the supplied module')
        result.update(recognized=True, generation='DVdx', entry=dict(offset=0, initial_jump=jump),
                      initialization=dict(load_offset=0, context_pointer='far pointer at SS:[SP+4] on stage-one entry',
                                          returns='RETF to loader',
                                          returned_context_words={'0':'ordering key', '2':'retained paragraph count; zero rejects/unloads', '4':'next entry offset'}))
    elif expected_type is not None:
        name = expected_type.encode('ascii')
        descriptor = struct.unpack_from('<H',data)[0] if len(data) >= 2 else 0
        table_word = descriptor + 2 + len(name)
        if descriptor < 2 or table_word + 2 >= len(data):
            raise ValueError('Older DESQview descriptor or initialization entry is outside the module')
        version = struct.unpack_from('<H',data,descriptor)[0]
        if data[descriptor + 2:table_word] != name:
            raise ValueError('DESQview module type differs from the caller descriptor')
        exports = struct.unpack_from('<H',data,table_word)[0]
        if exports + 2 > len(data):
            raise ValueError('DESQview module export/patch table is outside the module')
        result.update(recognized=True, generation='caller-type-descriptor',
                      entry=dict(offset=table_word + 2, role='initialization after the descriptor'),
                      descriptor=dict(offset=descriptor, interface_version=hex(version), type=expected_type,
                                      export_table_offset=exports, caller_expected_version=expected_version,
                                      version_compatible=(version ^ expected_version) <= 0xf if expected_version is not None else None),
                      initialization=dict(first_word='descriptor offset, not an entry point',
                                          type_encoding='caller-sized ASCII, not NUL-terminated',
                                          calling_convention='requires the matching original loader state'))
    else:
        result['reason'] = 'No DVdx signature; older formats require the caller type descriptor'
    return result
