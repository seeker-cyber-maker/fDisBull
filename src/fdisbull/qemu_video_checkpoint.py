"""Strict bounded source-raster state for instrumented checkpoints.

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
OVERLAP_PROFILE = 'dosbox-mode13-overlap'
OVERLAP_MODEL = 'qemu-vga-chain4-dosbox-mode13-overlap-v1'
LATCH_PROFILE = 'vga-unchained-latch'
LATCH_MODEL = 'qemu-vga-unchained-320x200-latch-v1'
VGA480_PROFILE = 'vga-640x480'
VGA480_MODEL = 'qemu-vga-640x480-scanline-v1'
VGA480_SYNC_PROFILE = 'vga-640x480-sync'
VGA480_SYNC_MODEL = 'qemu-vga-640x480-sync-v1'
VGA480_FLIP_PROFILE = 'vga-640x480-flip'
VGA480_FLIP_MODEL = 'qemu-vga-640x480-flip-v1'
VGA480_PAN_PROFILE = 'vga-640x480-pan'
VGA480_PAN_MODEL = 'qemu-vga-640x480-pan-v1'
VGA480_XY_PROFILE = 'vga-640x480-xy'
VGA480_XY_MODEL = 'qemu-vga-640x480-xy-v1'
VGA480_PALETTE_PROFILE = 'vga-640x480-palette'
VGA480_PALETTE_MODEL = 'qemu-vga-640x480-palette-v1'
VBE101_FLIP_ROM = 'fdisbull-vgabios-vbe101-flip.bin'
VBE101_XY_ROM = 'fdisbull-vgabios-vbe101-xy.bin'
VBE101_PALETTE_ROM = 'fdisbull-vgabios-vbe101-palette.bin'
VBE101_PAN_MODELS = (VGA480_PAN_MODEL, VGA480_XY_MODEL, VGA480_PALETTE_MODEL)
VBE101_PAN_PROFILES = (VGA480_PAN_PROFILE, VGA480_XY_PROFILE, VGA480_PALETTE_PROFILE)
VBE101_ORIGIN_FIELD = 'vbe101-origin-bytes'
VBE101_PITCH_FIELD = 'vbe101-pitch-bytes'
VBE101_PEL_FIELD = 'vbe101-pel'
VBE101_VIEWPORT_FIELDS = (VBE101_ORIGIN_FIELD, VBE101_PITCH_FIELD, VBE101_PEL_FIELD)
VGA480_MODELS = (VGA480_MODEL, VGA480_SYNC_MODEL, VGA480_FLIP_MODEL, *VBE101_PAN_MODELS)
VGA480_LAYOUTS = ('vga-mode12', 'vbe-banked-101')
VIDEO_SOURCE_PROFILES = {
    MODE13_PROFILE: (MODE13_MODEL, 'VGA.x-fdisbull-mode13-phase=on'),
    OVERLAP_PROFILE: (OVERLAP_MODEL, 'VGA.x-fdisbull-mode13-overlap=on'),
    LATCH_PROFILE: (LATCH_MODEL, 'VGA.x-fdisbull-unchained-latch=on'),
    VGA480_PROFILE: (VGA480_MODEL, 'VGA.x-fdisbull-vga480=on'),
    VGA480_SYNC_PROFILE: (VGA480_SYNC_MODEL, 'VGA.x-fdisbull-vbe101-sync=on'),
    VGA480_FLIP_PROFILE: (VGA480_FLIP_MODEL, 'VGA.x-fdisbull-vbe101-flip=on'),
    VGA480_PAN_PROFILE: (VGA480_PAN_MODEL, 'VGA.x-fdisbull-vbe101-pan=on'),
    VGA480_XY_PROFILE: (VGA480_XY_MODEL, 'VGA.x-fdisbull-vbe101-xy=on'),
    VGA480_PALETTE_PROFILE: (VGA480_PALETTE_MODEL, 'VGA.x-fdisbull-vbe101-palette=on'),
}
MODE13_MODELS = (MODE13_MODEL, OVERLAP_MODEL)
VIDEO_MODELS = frozenset((*MODE13_MODELS, MODEL, LATCH_MODEL, *VGA480_MODELS))
DEFAULT_FRAME_SIZE = (320, 200)
VGA480_FRAME_SIZE = (640, 480)
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
_LATCH_INFO = frozenset({'page-latch-offset-ns', 'awaiting-page-latch', 'pending-page-latch'})
_OVERLAP_INFO = frozenset({'reapply-overlap', 'overlap-next-new-ns', 'overlap-next-retained-ns'})
_MODE13_LINES = 449
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
    profile = configuration.get('video_source_profile')
    return VIDEO_SOURCE_PROFILES[profile][0] if type(profile) is str and profile in VIDEO_SOURCE_PROFILES else MODEL


def video_frame_size(model):
    return VGA480_FRAME_SIZE if model in VGA480_MODELS else DEFAULT_FRAME_SIZE


def video_vm_size(vm):
    return video_frame_size(video_model(getattr(vm, 'machine_configuration', {})))


def video_period_valid(model, period, line):
    height = video_frame_size(model)[1]
    physical_rows = height if model in VGA480_MODELS else height * 2
    return line >= 4 and period >= physical_rows * line and period % line == 0


def validate_scanout_info(info):
    expected = info['model'] in VGA480_MODELS and info['state'] in ('observing', 'stopped')
    _require(('scanout-layout' in info) == expected, 'scanout layout presence')
    if expected:
        _require(info['scanout-layout'] in VGA480_LAYOUTS, 'scanout layout')
    return {'scanout-layout'} if expected else set()


def validate_frame_scanout(frame, info):
    expected = info['model'] in VGA480_MODELS
    _require(('scanout-layout' in frame) == expected, 'complete scanout layout presence')
    if expected:
        _require(frame['scanout-layout'] in VGA480_LAYOUTS
                 and frame['scanout-layout'] == info.get('scanout-layout'), 'complete scanout layout')
    _require(valid_vbe101_frame_fields(frame, info['model'], info.get('scanout-layout')),
             'complete VBE 101h display start or viewport')


def valid_vbe101_origin(origin):
    width = VGA480_FRAME_SIZE[0]
    return _integer(origin, maximum=12000 * width) and origin % width == 0


def valid_vbe101_pitch(pitch, *, short_pitch=False):
    minimum = 8 if short_pitch else VGA480_FRAME_SIZE[0]
    return _integer(pitch, minimum, 8184) and pitch % 8 == 0


def valid_vbe101_viewport(origin, pitch, pel, *, programmed=False, short_pitch=False):
    if (not valid_vbe101_pitch(pitch, short_pitch=short_pitch)
            or not _integer(origin) or origin % 4 or not _integer(pel, 0, 3)):
        return False
    row, x = divmod(origin, pitch)
    width = VGA480_FRAME_SIZE[0]
    if pitch < width:
        return row <= 12000 and x == pel == 0
    return row <= 12000 and x + width + (pel if programmed else 0) <= pitch


def vbe101_frame_fields(model, layout):
    if layout == 'vbe-banked-101':
        if model in VBE101_PAN_MODELS:
            return VBE101_VIEWPORT_FIELDS
        if model == VGA480_FLIP_MODEL:
            return (VBE101_ORIGIN_FIELD,)
    return ()


def valid_vbe101_frame_fields(frame, model, layout):
    expected = vbe101_frame_fields(model, layout)
    if tuple(key for key in VBE101_VIEWPORT_FIELDS if key in frame) != expected:
        return False
    if model in VBE101_PAN_MODELS and expected:
        return valid_vbe101_viewport(*(frame[key] for key in expected),
                                     short_pitch=model == VGA480_PALETTE_MODEL)
    return not expected or valid_vbe101_origin(frame[VBE101_ORIGIN_FIELD])


def vbe101_frame_metadata(frame):
    return {key.replace('-', '_'): frame[key] for key in VBE101_VIEWPORT_FIELDS if key in frame}


def valid_vbe101_frame_metadata(metadata, model, layout):
    native = {key: metadata[key.replace('-', '_')] for key in VBE101_VIEWPORT_FIELDS
              if key.replace('-', '_') in metadata}
    return valid_vbe101_frame_fields(native, model, layout)


def validate_video_source_profile(profile, clock, retrace):
    if profile is not None and (type(profile) is not str or profile not in VIDEO_SOURCE_PROFILES
                                or clock != 'virtual' or retrace != 'precise'):
        choices = ', '.join(VIDEO_SOURCE_PROFILES)
        raise ValueError(f'Source video timing requires one of {choices}, virtual clock and precise retrace')


def validate_mode_setup(info):
    setup = info.get('mode-setup')
    if info.get('model') not in MODE13_MODELS:
        _require('mode-setup' not in info, 'unexpected mode setup on standard model')
    elif 'mode-setup' in info:
        fields = {'committed-ns', 'configuration-generation', 'timing-generation'}
        if info['model'] == OVERLAP_MODEL and type(setup) is dict and 'same-mode-reapply' in setup:
            _require(setup['same-mode-reapply'] is True, 'mode reapply marker')
            fields.add('same-mode-reapply')
        _require(type(setup) is dict and set(setup) == fields
            and _integer(setup['committed-ns']) and setup['committed-ns'] <= info['virtual-ns']
            and all(_integer(setup[k], 1, U64_MAX)
                    for k in ('configuration-generation', 'timing-generation')), 'effective mode setup')
    else:
        _require(info.get('state') in ('idle', 'invalidated'), 'missing effective mode setup')
    return setup


def _first_setup_raster(setup, period):
    first = setup['committed-ns'] + period - setup['committed-ns'] % period
    _require(_integer(first), 'raster setup boundary')
    return first


def raster_source_phase(info, start, period, source):
    if info['model'] not in MODE13_MODELS:
        return 0
    setup = validate_mode_setup(info)
    _require(setup is not None and all(setup[k] == source[k]
        for k in ('configuration-generation', 'timing-generation')), 'raster setup generation')
    first = _first_setup_raster(setup, period)
    _require(start >= first, 'raster precedes effective mode setup')
    if setup.get('same-mode-reapply'):
        return int(start != first + period)
    return int(start != first)


def validate_latch_info(info):
    """Verify the fields that identify the next timer boundary on this stream."""
    expected = set()
    if info['model'] == LATCH_MODEL and info['state'] in ('observing', 'stopped'):
        expected.add('page-latch-offset-ns')
        _require(_integer(info.get('page-latch-offset-ns'), 1), 'page latch offset')
        if info['state'] == 'observing':
            expected.add('awaiting-page-latch')
            awaiting = info.get('awaiting-page-latch')
            _require(type(awaiting) is bool and (not awaiting or info['rows-sampled'] == 0),
                     'page latch phase')
            if not awaiting:
                expected.add('pending-page-latch')
                validate_page_latch(info.get('pending-page-latch'), info,
                                    upper=info['virtual-ns'])
    _require(_LATCH_INFO.intersection(info) == expected, 'page latch stream fields')
    return expected


def latch_offset(info, period, line):
    offset = info['page-latch-offset-ns']
    _require(400 * line <= offset < period and offset % line == 0, 'page latch timing')
    return offset


def latch_deadline(info, start, period, line):
    intended = start - period + latch_offset(info, period, line)
    _require(_integer(intended) and intended > info['start-ns'], 'page latch target')
    return intended


def validate_page_latch(stamp, info, *, upper, intended=None, generation=1):
    _require(type(stamp) is dict and set(stamp) == {
                'origin-bytes', 'configuration-generation', 'intended-ns', 'actual-ns'},
             'page latch stamp fields')
    width, height = DEFAULT_FRAME_SIZE
    _require(_integer(stamp['origin-bytes'], maximum=(256 * 1024 - width * height))
             and stamp['origin-bytes'] % 4 == 0, 'page latch origin')
    _require(_integer(stamp['configuration-generation'], generation, U64_MAX),
             'page latch generation')
    target, actual = stamp['intended-ns'], stamp['actual-ns']
    lower = info.get('start-ns')
    _require(_integer(lower) and _integer(target) and _integer(actual) and lower < target <= actual <= upper
             and (intended is None or target == intended), 'page latch time')


def validate_frame_latch(frame, info):
    if info['model'] != LATCH_MODEL:
        _require('page-latch' not in frame, 'unexpected complete page latch')
        return
    line = frame['line-period-ns']
    target = latch_deadline(info, frame['frame-start-ns'], frame['period-ns'], line)
    validate_page_latch(frame.get('page-latch'), info, intended=target,
                        upper=min(target + line, frame['first-sample-ns']) - 1,
                        generation=frame['configuration-generation'])


def _overlap_stamp(stamp, info):
    _require(type(stamp) is dict and set(stamp) == {
        'new-first-ns', 'retained-first-ns', 'line-period-ns'}, 'reapply overlap stamp')
    first, retained, line = (stamp[k] for k in ('new-first-ns', 'retained-first-ns', 'line-period-ns'))
    _require(_integer(first) and _integer(retained) and _integer(line, 4)
             and retained == first + line * 17773 // 31778, 'reapply overlap offset')
    setup = validate_mode_setup(info)
    start = first - line // 4
    period = _MODE13_LINES * line
    _require(_integer(period, 1) and setup is not None and setup.get('same-mode-reapply') is True
             and _integer(info.get('start-ns')) and info['start-ns'] < start
             and start == _first_setup_raster(setup, period), 'reapply overlap raster origin')
    return start, line


def validate_reapply_info(info):
    fields = _OVERLAP_INFO.intersection(info)
    if fields:
        _require(fields == _OVERLAP_INFO and info['model'] == OVERLAP_MODEL
                 and info['state'] == 'observing' and 'frame' not in info,
                 'reapply overlap stream fields')
        stamp = info['reapply-overlap']
        _, line = _overlap_stamp(stamp, info)
        rows = info['rows-sampled']
        new, retained = info['overlap-next-new-ns'], info['overlap-next-retained-ns']
        new_row = stamp['new-first-ns'] + rows * line
        _require(_integer(new) and _integer(retained)
                 and retained == stamp['retained-first-ns'] + rows * line
                 and (new == new_row or new == new_row + line and new_row <= info['virtual-ns'])
                 and info.get('next-deadline-ns') == min(new, retained), 'reapply overlap timers')
    return fields


def raster_row_timing(info, source, schedule):
    """Return physical parity, first drawn row time and drawn row spacing."""
    start, period, line = (source[k] for k in ('frame-start-ns', 'period-ns', 'line-period-ns'))
    phase = raster_source_phase(info, start, period, source)
    overlap = (info['model'] == OVERLAP_MODEL and
               info['mode-setup'].get('same-mode-reapply') is True and
               start == _first_setup_raster(info['mode-setup'], period))
    _require(('reapply-overlap' in schedule) == overlap, 'reapply overlap schedule presence')
    if overlap:
        stamp = schedule['reapply-overlap']
        _require(_overlap_stamp(stamp, info) == (start, line) and period == _MODE13_LINES * line,
                 'reapply overlap timing descriptor')
        return phase, stamp['retained-first-ns'], line
    if info['model'] in VGA480_MODELS:
        return phase, _deadline(start + line // 4, line, 0), line
    return phase, _deadline(start + line // 4 + phase * line, line * 2, 0), line * 2


def raster_row_slack(line, schedule):
    overlap = schedule.get('reapply-overlap')
    if overlap is None:
        return line
    return line + overlap['new-first-ns'] - overlap['retained-first-ns']


def _deadline(first, spacing, row):
    value = first + spacing * row
    _require(_integer(value), 'row deadline overflow')
    return value


def _rows(rows, count, first, spacing, slack, stopped):
    _require(type(rows) is list and len(rows) == count, 'row prefix extent')
    for number, row in enumerate(rows):
        _require(type(row) is dict and set(row) == {'row', 'intended-ns', 'actual-ns'}, 'row fields')
        _require(type(row['row']) is int and row['row'] == number, 'row order')
        intended, actual = row['intended-ns'], row['actual-ns']
        _require(_integer(intended) and _integer(actual)
            and intended == _deadline(first, spacing, number)
            and intended <= actual <= stopped and actual - intended < slack, 'row time or stop boundary')


def _frame(frame, info, source):
    phased = info['model'] in MODE13_MODELS
    fields = _FRAME | {'source-phase'} if phased else _FRAME
    if info['model'] == LATCH_MODEL:
        fields = fields | {'page-latch'}
    if info['model'] in VGA480_MODELS:
        fields = fields | {'scanout-layout'}
    fields = fields.union(vbe101_frame_fields(info['model'], info.get('scanout-layout')))
    if type(frame) is dict and info['model'] == OVERLAP_MODEL and 'reapply-overlap' in frame:
        fields = fields | {'reapply-overlap'}
    _require(type(frame) is dict and set(frame) == fields, 'complete frame fields')
    for key in ('frame-id', 'stream-generation', 'epoch', 'configuration-generation', 'timing-generation'):
        _require(_integer(frame[key], 1, U64_MAX), 'complete frame identity')
    _require(frame['frame-id'] == info['frame-sequence']
        and frame['stream-generation'] == info['stream-generation'] and frame['epoch'] == info['epoch'],
        'complete frame ownership')
    width, height = video_frame_size(info['model'])
    _require(all(type(frame[k]) is int and frame[k] == value for k, value in
        (('width', width), ('height', height), ('stride', width * 3)))
        and frame['pixel-format'] == 'RGB888'
        and frame['dac-conversion'] == 'replicate-6-to-8-v1'
        and type(frame['dac-8bit']) is bool, 'complete frame geometry or color format')
    _require(all(frame[k] == source[k] for k in (*_SOURCE, 'dac-8bit')), 'complete frame source descriptor')
    for key in ('frame-start-ns', 'period-ns', 'line-period-ns', 'first-sample-ns',
                'last-sample-ns', 'completed-ns'):
        _require(_integer(frame[key]), 'complete frame time')
    start, period, line = (frame[k] for k in ('frame-start-ns', 'period-ns', 'line-period-ns'))
    _require(start > info['start-ns'] and start % period == 0, 'complete frame phase')
    phase, first, spacing = raster_row_timing(info, frame, frame)
    if phased:
        _require(_integer(frame['source-phase'], 0, 1) and frame['source-phase'] == phase, 'complete source phase')
    _rows(frame['rows'], height, first, spacing, raster_row_slack(line, frame),
          info.get('stop-ns', info['virtual-ns']))
    validate_frame_latch(frame, info)
    validate_frame_scanout(frame, info)
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
    if 'mode-setup' in info and info['model'] in MODE13_MODELS:
        fields.add('mode-setup')
    _require(type(info['api-version']) is int and info['api-version'] == 1 and type(info['model']) is str
        and info['model'] in VIDEO_MODELS,
        'stream API or model')
    _require(_integer(info['epoch'], 1, U64_MAX) and info['epoch'] == epoch
        and _integer(info['virtual-ns']) and info['virtual-ns'] == virtual_ns, 'stream clock')
    setup = validate_mode_setup(info)
    for key in ('stream-generation', 'frame-sequence', 'aborted-frames'):
        _require(_integer(info[key], 0, U64_MAX), 'stream counter')
    rows = info['rows-sampled']
    width, height = video_frame_size(info['model'])
    row_bytes = width * 3
    _require(_integer(rows, 0, height - 1) and type(info['in-progress']) is bool
        and info['in-progress'] == bool(rows), 'stream row progress')
    fields.update(validate_latch_info(info))
    fields.update(validate_reapply_info(info))
    fields.update(validate_scanout_info(info))
    _require(set(info) == fields, 'canonical stream fields')
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
            and video_period_valid(info['model'], period, line), 'source timing')
        if info['model'] == LATCH_MODEL:
            latch_offset(info, period, line)
        if setup is not None:
            _require(all(setup[k] == record[k]
                for k in ('configuration-generation', 'timing-generation')), 'stream setup generation')
    if state == 'observing':
        start = record['frame-start-ns']
        intended, expiry = info['next-deadline-ns'], record['timer-expire-ns']
        _require(start > info['start-ns'] and start % period == 0 and _integer(intended), 'pending raster phase')
        _, first, spacing = raster_row_timing(info, record, info)
        expected = _deadline(first, spacing, rows)
        if info['model'] == LATCH_MODEL:
            target = latch_deadline(info, start, period, line)
            if info['awaiting-page-latch']:
                expected = target
            else:
                validate_page_latch(info['pending-page-latch'], info, intended=target,
                    upper=min(virtual_ns, target + line - 1, first - 1),
                    generation=record['configuration-generation'])
        elif 'reapply-overlap' in info:
            expected = min(info['overlap-next-new-ns'], expected)
        _require(intended == expected, 'pending raster phase')
        # Deferral arms T+1 without changing D. A timer-disabled step may then
        # advance the stopped clock, so a retained expiry need not equal N+1.
        _require(record['timer-pending'] is True and expiry >= 0
            and (expiry == intended or expiry > intended and expiry - 1 <= virtual_ns),
            'actual timer phase')
        _rows(record['partial-rows'], rows, first, spacing, raster_row_slack(line, info), virtual_ns)
    else:
        _require(rows == 0 and record['partial-rows'] == [] and type(record['partial-rows']) is list
            and record['frame-start-ns'] == 0 and record['timer-pending'] is False
            and record['timer-expire-ns'] == -1, 'inactive raster progress or timer')
    _pixels(record['partial-rgb-base64'], rows * row_bytes, record['partial-sha256'])
    if 'frame' in info:
        _frame(info['frame'], info, record)
        if 'pending-page-latch' in info:
            _require(info['pending-page-latch']['configuration-generation']
                     >= info['frame']['page-latch']['configuration-generation'],
                     'page latch generation regressed')
        if state == 'observing':
            _require(record['frame-start-ns'] == info['frame']['frame-start-ns'] + period,
                'next raster after complete image')
        _pixels(record['rgb-base64'], height * row_bytes, info['frame']['pixel-sha256'])
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
