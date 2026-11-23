"""Strict bounded source-raster state for instrumented checkpoint format 3.

This record owns a sampled prefix separately from its retained complete image.
Validation never queries a machine, samples a row, or adopts an owner.
"""
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from copy import deepcopy
import hashlib

from .dosbox_rpc import DebuggerError


FORMAT = 'fdisbull-instrumented-qemu-state-3'
MODEL = 'qemu-vga-chain4-scanline-v1'
MODE13_PROFILE = 'dosbox-mode13'
MODE13_MODEL = 'qemu-vga-chain4-dosbox-mode13-v1'
VIDEO_MODELS = frozenset({MODEL, MODE13_MODEL})
ROW_BYTES = 960
HEIGHT = 200
RGB_BYTES = ROW_BYTES * HEIGHT
I64_MAX = (1 << 63) - 1
U64_MAX = (1 << 64) - 1
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
_FIELDS = frozenset({'info', 'device-path', 'console-index',
    'configuration-generation', 'timing-generation', 'period-ns', 'line-period-ns',
    'dac-8bit', 'frame-start-ns', 'timer-pending', 'timer-expire-ns',
    'partial-rows', 'partial-rgb-base64', 'partial-sha256', 'rgb-base64'})
_INFO = frozenset({'api-version', 'model', 'state', 'epoch', 'virtual-ns',
    'stream-generation', 'frame-sequence', 'aborted-frames', 'in-progress', 'rows-sampled'})
_FRAME = frozenset({'frame-id', 'stream-generation', 'epoch', 'configuration-generation',
    'timing-generation', 'width', 'height', 'stride', 'pixel-format', 'dac-conversion',
    'dac-8bit', 'frame-start-ns', 'period-ns', 'line-period-ns', 'first-sample-ns',
    'last-sample-ns', 'completed-ns', 'pixel-sha256', 'rows'})
_SOURCE = ('configuration-generation', 'timing-generation', 'period-ns', 'line-period-ns')
_CACHES = ('_video_frame_token', '_video_frame_last',
           '_video_frame_probe_samples', '_video_frame_owned_rgb')


def _require(value, message):
    if not value:
        raise ValueError('Invalid source-video checkpoint: ' + message)


def _integer(value, minimum=0, maximum=I64_MAX):
    return type(value) is int and minimum <= value <= maximum


def _text(value, maximum, *, empty=False):
    if type(value) is not str or '\0' in value:
        return False
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        return False
    return int(not empty) <= size <= maximum


def _hash(value):
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _pixels(value, size, digest=None):
    _require(type(value) is str and len(value) == 4 * ((size + 2) // 3), 'pixel encoding extent')
    try:
        data = b64decode(value, validate=True)
    except (ValueError, Base64Error) as error:
        raise ValueError('Invalid source-video checkpoint: pixel encoding') from error
    _require(len(data) == size and b64encode(data).decode('ascii') == value, 'canonical pixel encoding')
    if digest is not None:
        _require(_hash(digest) and hashlib.sha256(data).hexdigest() == digest, 'pixel digest')


def video_model(configuration):
    return MODE13_MODEL if configuration.get('video_source_profile') == MODE13_PROFILE else MODEL


def validate_video_source_profile(profile, clock, retrace):
    if profile is not None and (profile != MODE13_PROFILE or clock != 'virtual' or retrace != 'precise'):
        raise ValueError('DOSBox mode 13h source timing requires dosbox-mode13, virtual clock and precise retrace')


def validate_mode_setup(info):
    setup = info.get('mode-setup')
    if info.get('model') == MODEL:
        _require('mode-setup' not in info, 'unexpected mode setup on standard model')
    elif 'mode-setup' in info:
        _require(type(setup) is dict and set(setup) == {
                'committed-ns', 'configuration-generation', 'timing-generation'}
            and _integer(setup['committed-ns']) and setup['committed-ns'] <= info['virtual-ns']
            and all(_integer(setup[k], 1, U64_MAX)
                    for k in ('configuration-generation', 'timing-generation')), 'effective mode setup')
    else:
        _require(info.get('state') in ('idle', 'invalidated'), 'missing effective mode setup')
    return setup


def raster_source_phase(info, start, period, source):
    if info['model'] == MODEL:
        return 0
    setup = validate_mode_setup(info)
    _require(setup is not None and all(setup[k] == source[k]
        for k in ('configuration-generation', 'timing-generation')), 'raster setup generation')
    first = setup['committed-ns'] + period - setup['committed-ns'] % period
    _require(_integer(first) and start >= first, 'raster precedes effective mode setup')
    return int(start != first)


def _deadline(start, line, row, phase):
    value = start + line // 4 + (2 * row + phase) * line
    _require(_integer(value), 'row deadline overflow')
    return value


def _rows(rows, count, start, line, stopped, phase):
    _require(type(rows) is list and len(rows) == count, 'row prefix extent')
    for number, row in enumerate(rows):
        _require(type(row) is dict and set(row) == {'row', 'intended-ns', 'actual-ns'}, 'row fields')
        _require(type(row['row']) is int and row['row'] == number, 'row order')
        intended, actual = row['intended-ns'], row['actual-ns']
        _require(_integer(intended) and _integer(actual)
            and intended == _deadline(start, line, number, phase)
            and intended <= actual <= stopped and actual - intended < line, 'row time or stop boundary')


def _frame(frame, info, source):
    phased = info['model'] == MODE13_MODEL
    fields = _FRAME | {'source-phase'} if phased else _FRAME
    _require(type(frame) is dict and set(frame) == fields, 'complete frame fields')
    for key in ('frame-id', 'stream-generation', 'epoch', 'configuration-generation', 'timing-generation'):
        _require(_integer(frame[key], 1, U64_MAX), 'complete frame identity')
    _require(frame['frame-id'] == info['frame-sequence']
        and frame['stream-generation'] == info['stream-generation'] and frame['epoch'] == info['epoch'],
        'complete frame ownership')
    _require(all(type(frame[k]) is int and frame[k] == value for k, value in
        (('width', 320), ('height', HEIGHT), ('stride', ROW_BYTES)))
        and frame['pixel-format'] == 'RGB888'
        and frame['dac-conversion'] == 'replicate-6-to-8-v1'
        and type(frame['dac-8bit']) is bool, 'complete frame geometry or color format')
    _require(all(frame[k] == source[k] for k in (*_SOURCE, 'dac-8bit')), 'complete frame source descriptor')
    for key in ('frame-start-ns', 'period-ns', 'line-period-ns', 'first-sample-ns',
                'last-sample-ns', 'completed-ns'):
        _require(_integer(frame[key]), 'complete frame time')
    start, period, line = (frame[k] for k in ('frame-start-ns', 'period-ns', 'line-period-ns'))
    _require(start > info['start-ns'] and start % period == 0, 'complete frame phase')
    phase = raster_source_phase(info, start, period, source)
    if phased:
        _require(_integer(frame['source-phase'], 0, 1) and frame['source-phase'] == phase, 'complete source phase')
    _rows(frame['rows'], HEIGHT, start, line, info.get('stop-ns', info['virtual-ns']), phase)
    _require(frame['first-sample-ns'] == frame['rows'][0]['actual-ns']
        and frame['last-sample-ns'] == frame['completed-ns'] == frame['rows'][-1]['actual-ns'],
        'complete frame sample endpoints')
    _require(_hash(frame['pixel-sha256']), 'complete frame digest')


def validate_video_checkpoint(record, *, epoch, virtual_ns):
    """Return a detached strict record, rejecting malformed data before import."""
    _require(type(record) is dict and set(record) == _FIELDS, 'record fields')
    _require(_integer(epoch, 1, U64_MAX) and _integer(virtual_ns), 'enclosing clock')
    info = record['info']
    _require(type(info) is dict and _INFO <= set(info), 'stream fields')
    state = info['state']
    _require(type(state) is str and state in ('idle', 'observing', 'stopped', 'invalidated'), 'stream state')
    fields = set(_INFO)
    if state != 'idle':
        fields.update(('token', 'device', 'start-ns'))
    if state == 'observing':
        fields.add('next-deadline-ns')
    elif state == 'stopped':
        fields.add('stop-ns')
    elif state == 'invalidated':
        fields.add('reason')
    if 'frame' in info and state in ('observing', 'stopped'):
        fields.add('frame')
    if 'mode-setup' in info and info['model'] == MODE13_MODEL:
        fields.add('mode-setup')
    _require(set(info) == fields, 'canonical stream fields')
    _require(type(info['api-version']) is int and info['api-version'] == 1 and type(info['model']) is str
        and info['model'] in VIDEO_MODELS,
        'stream API or model')
    _require(_integer(info['epoch'], 1, U64_MAX) and info['epoch'] == epoch
        and _integer(info['virtual-ns']) and info['virtual-ns'] == virtual_ns, 'stream clock')
    setup = validate_mode_setup(info)
    for key in ('stream-generation', 'frame-sequence', 'aborted-frames'):
        _require(_integer(info[key], 0, U64_MAX), 'stream counter')
    rows = info['rows-sampled']
    _require(_integer(rows, 0, HEIGHT - 1) and type(info['in-progress']) is bool
        and info['in-progress'] == bool(rows), 'stream row progress')
    _require(type(record['console-index']) is int and record['console-index'] == 0
        and type(record['dac-8bit']) is bool and type(record['timer-pending']) is bool,
        'console or Boolean field')
    for key in _SOURCE:
        _require(_integer(record[key], 0, U64_MAX if key.endswith('generation') else I64_MAX),
            'source descriptor type')
    _require(_integer(record['frame-start-ns']) and _integer(record['timer-expire-ns'], -1),
        'pending raster time')
    if state == 'idle':
        _require(record['device-path'] == '' and type(record['device-path']) is str
            and not any(info[k] for k in ('stream-generation', 'frame-sequence', 'aborted-frames')),
            'idle identity')
    else:
        _require(info['stream-generation'] > 0 and _text(info['token'], 128)
            and _text(info['device'], 1024) and _text(record['device-path'], 1024)
            and record['device-path'] == info['device']
            and _integer(info['start-ns']) and info['start-ns'] <= virtual_ns, 'source owner')
    if state == 'invalidated':
        _require(_text(info['reason'], 1024), 'invalidation reason')
    if state == 'stopped':
        _require(_integer(info['stop-ns']) and info['start-ns'] <= info['stop-ns'] <= virtual_ns,
            'stream stop interval')
    if state in ('idle', 'invalidated'):
        _require(not any(record[k] for k in _SOURCE) and record['dac-8bit'] is False,
            'inactive source descriptor')
    else:
        period, line = record['period-ns'], record['line-period-ns']
        _require(record['configuration-generation'] > 0 and record['timing-generation'] > 0
            and line >= 4 and period >= 400 * line and period % line == 0, 'source timing')
        if setup is not None:
            _require(all(setup[k] == record[k]
                for k in ('configuration-generation', 'timing-generation')), 'stream setup generation')
    if state == 'observing':
        start = record['frame-start-ns']
        intended, expiry = info['next-deadline-ns'], record['timer-expire-ns']
        phase = raster_source_phase(info, start, period, record)
        _require(start > info['start-ns'] and start % period == 0
            and _integer(intended) and intended == _deadline(start, line, rows, phase), 'pending raster phase')
        # Deferral arms T+1 without changing D. A timer-disabled step may then
        # advance the stopped clock, so a retained expiry need not equal N+1.
        _require(record['timer-pending'] is True and expiry >= 0
            and (expiry == intended or expiry > intended and expiry - 1 <= virtual_ns),
            'actual timer phase')
        _rows(record['partial-rows'], rows, start, line, virtual_ns, phase)
    else:
        _require(rows == 0 and record['partial-rows'] == [] and type(record['partial-rows']) is list
            and record['frame-start-ns'] == 0 and record['timer-pending'] is False
            and record['timer-expire-ns'] == -1, 'inactive raster progress or timer')
    _pixels(record['partial-rgb-base64'], rows * ROW_BYTES, record['partial-sha256'])
    if 'frame' in info:
        _frame(info['frame'], info, record)
        if state == 'observing':
            _require(record['frame-start-ns'] == info['frame']['frame-start-ns'] + period,
                'next raster after complete image')
        _pixels(record['rgb-base64'], RGB_BYTES, info['frame']['pixel-sha256'])
    else:
        _pixels(record['rgb-base64'], 0)
    return deepcopy(record)


def logical_video_checkpoint(record):
    """Normalize only the owner identities deliberately recreated by import."""
    result = deepcopy(record)
    result['info'].pop('epoch', None)
    result['info'].pop('token', None)
    if 'frame' in result['info']:
        result['info']['frame'].pop('epoch', None)
    return result


def clear_video_checkpoint_caches(vm):
    for name in _CACHES:
        vm.__dict__.pop(name, None)


def restored_video_info(record, raw, *, epoch, token):
    """Verify a fresh native query without publishing any host owner or pixels."""
    expected = deepcopy(record['info'])
    expected['epoch'] = epoch
    if expected['state'] == 'idle':
        if token is not None:
            raise DebuggerError('Idle restored source video unexpectedly owns a token')
    else:
        if not _text(token, 128) or token == expected['token']:
            raise DebuggerError('Restored source video reused or lacks a fresh token')
        expected['token'] = token
    if 'frame' in expected:
        expected['frame']['epoch'] = epoch
    candidate = dict(record, info=raw)
    validate_video_checkpoint(candidate, epoch=epoch, virtual_ns=expected['virtual-ns'])
    if raw != expected:
        raise DebuggerError('Restored source video metadata differs from its checkpoint')
    return deepcopy(raw)
