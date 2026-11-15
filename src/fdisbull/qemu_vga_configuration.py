"""Passive identities for a declared, conservative native VGA configuration.

A generation records tracked mutation boundaries, including A -> B -> A.
A raw fingerprint records only equal values. Neither identifies a guest BIOS
mode, a completed guest frame, nor a mapping from image pixels to a DOS cursor.
The historical stamp is the configuration observed at a renderer publication;
QEMU can retain an older surface when a transient mode cannot be rendered.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .dosbox_rpc import DebuggerError
from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
from .qemu_display import DISPLAY_COMMANDS, _native_display
from .qemu_retrace import (RETRACE_COMMANDS, _configuration as precise_configuration,
                           _device, _remaining)


VGA_CONFIGURATION_COMMANDS = frozenset({'x-fdisbull-query-vga-configuration'})
VGA_CONFIGURATION_MODEL = 'qemu-vga-configuration-fdisbull-v1'
_MAX_U64 = (1 << 64) - 1
_MAX_NS = (1 << 63) - 1
_ARRAYS = {'sequencer': (8, 255), 'sequencer-vbe': (8, 255),
           'graphics': (16, 255), 'crtc': (256, 255),
           'attribute-controls': (5, 255), 'vbe': (10, 65535)}
_BYTES = frozenset({'misc-output', 'feature-control'})
_U32 = frozenset({'vbe-start-address', 'vbe-line-offset', 'vbe-bank-mask',
                  'vram-size', 'vbe-size', 'vbe-size-mask'})
_BOOLS = frozenset({'display-enabled', 'dac-8bit', 'big-endian-framebuffer'})
_RAW_FIELDS = frozenset(_ARRAYS) | _BYTES | _U32 | _BOOLS | {'bank-offset'}
_IDENTITY = ('api-version', 'model', 'epoch', 'device', 'device-type', 'console', 'head')
_SNAPSHOT_FIELDS = frozenset(_IDENTITY) | {'virtual-ns', 'configuration-generation', 'raw'}
_DISPLAY_FIELDS = frozenset({'api-version', 'epoch', 'state', 'virtual-ns', 'period-ns',
    'updates', 'token', 'start-ns', 'stop-ns', 'update-id', 'published-ns', 'width', 'height'})


def validate_vga_configuration_parameters(*, timeout_ms=1000, allow_references=False):
    """Reject the full direct signature or visible script values before I/O."""
    if allow_references and isinstance(timeout_ms, str) and timeout_ms.startswith('$'):
        return
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('VGA configuration timeout_ms must be an integer in 1..600000')


def _integer(value, minimum=0, maximum=_MAX_NS):
    return type(value) is int and minimum <= value <= maximum


def validate_vga_configuration_snapshot(value, *, epoch, virtual_ns, device, previous=None):
    """Validate one snapshot without modifying a live or historical frontier."""
    if (type(value) is not dict or set(value) != _SNAPSHOT_FIELDS
            or type(value['api-version']) is not int or value['api-version'] != 1
            or value['model'] != VGA_CONFIGURATION_MODEL
            or not _integer(value['epoch'], 1, _MAX_U64) or value['epoch'] != epoch
            or not _integer(value['virtual-ns']) or value['virtual-ns'] != virtual_ns
            or not _device(value['device']) or value['device-type'] != 'VGA'
            or type(value['console']) is not int or value['console'] != 0
            or type(value['head']) is not int or value['head'] != 0
            or not _integer(value['configuration-generation'], 1, _MAX_U64)
            or any(value[key] != device[key] for key in ('device', 'device-type', 'console', 'head'))):
        raise ValueError('Invalid native VGA configuration identity or clock')
    raw = value['raw']
    if type(raw) is not dict or set(raw) != _RAW_FIELDS:
        raise ValueError('Invalid native VGA configuration raw fields')
    for name, (length, maximum) in _ARRAYS.items():
        array = raw[name]
        if type(array) is not list or len(array) != length or any(
                not _integer(item, 0, maximum) for item in array):
            raise ValueError('Invalid native VGA configuration array: ' + name)
    if (any(not _integer(raw[name], 0, 255) for name in _BYTES)
            or any(not _integer(raw[name], 0, (1 << 32) - 1) for name in _U32)
            or any(type(raw[name]) is not bool for name in _BOOLS)
            or not _integer(raw['bank-offset'], -(1 << 31), (1 << 31) - 1)):
        raise ValueError('Invalid native VGA configuration scalar fields')
    if previous is not None:
        if (any(value[key] != previous[key] for key in _IDENTITY)
                or value['virtual-ns'] < previous['virtual-ns']
                or value['configuration-generation'] < previous['configuration-generation']):
            raise ValueError('Native VGA configuration identity changed or regressed')
        if (value['configuration-generation'] == previous['configuration-generation']
                and raw != previous['raw']):
            raise ValueError('Native VGA configuration changed under one generation')
    return deepcopy(value)


def _public_configuration(native):
    # Hash the declared values, not native struct padding or a guessed mode.
    encoded = json.dumps(native['raw'], sort_keys=True, separators=(',', ':'),
                         ensure_ascii=True).encode('ascii')
    return dict(native_epoch=native['epoch'], observed_ns=native['virtual-ns'],
        model=native['model'], device=native['device'], device_type=native['device-type'],
        console=native['console'], head=native['head'],
        configuration_generation=native['configuration-generation'],
        configuration_sha256=hashlib.sha256(encoded).hexdigest(), raw=deepcopy(native['raw']))


class QemuVgaConfigurationMixin:
    def vga_configuration_observe(self, *, timeout_ms=1000):
        """Observe current VGA configuration and its frozen publication stamp.

        Missing publication is valid. The optional historical stamp is never
        synthesized from current registers. The operation performs only native
        reads and persists one receipt under its shared absolute host deadline.
        """
        validate_vga_configuration_parameters(timeout_ms=timeout_ms)
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('VGA configuration requires a project outside a caller-owned transaction')
        commands = VGA_CONFIGURATION_COMMANDS | DISPLAY_COMMANDS | RETRACE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
        if not commands <= getattr(self.vm, 'qmp_commands', frozenset()):
            raise ValueError('VGA configuration requires its native extension and virtual/precise profiles')
        precise_configuration(self.vm)
        admitted = getattr(self.vm, 'native_retrace_admission', None)
        if type(admitted) is not dict:
            self.vm.close()
            raise DebuggerError('Owned-machine native VGA admission is missing')
        _remaining(self, label='VGA configuration')

        before = after = raw = result = None
        received = False
        stage = 'before-clock'
        try:
            before = self._clock_snapshot()
            stage = 'configuration-query'
            raw = self.vm.qmp.call('x-fdisbull-query-vga-configuration')
            received = True
            if (type(raw) is not dict or not {'display', 'current'} <= raw.keys()
                    or set(raw) - {'display', 'current', 'published'}):
                raise DebuggerError('Invalid native VGA configuration observation fields')
            if type(raw['display']) is dict and set(raw['display']) - _DISPLAY_FIELDS:
                raise DebuggerError('Unexpected native VGA configuration display fields')
            display = _native_display(self.vm, raw['display'], before,
                                      token=getattr(self.vm, '_display_token', None))
            epoch = before['virtual_clock']['native']['epoch']
            try:
                prior_current = getattr(self.vm, '_vga_configuration_last', None)
                current = validate_vga_configuration_snapshot(raw['current'], epoch=epoch,
                    virtual_ns=before['virtual_ns'], device=admitted,
                    previous=prior_current)
                if current['epoch'] != admitted['epoch']:
                    raise ValueError('Native VGA configuration lost its admitted epoch')
                if bool(display['updates']) != ('published' in raw):
                    raise ValueError('Native VGA publication configuration is missing or invented')
                published = None
                if display['updates']:
                    prior = getattr(self.vm, '_vga_publication_last', None)
                    published = validate_vga_configuration_snapshot(raw['published'], epoch=epoch,
                        virtual_ns=display['published-ns'], device=current,
                        previous=prior['snapshot'] if prior is not None else None)
                    if published['configuration-generation'] > current['configuration-generation']:
                        raise ValueError('Native VGA publication configuration is ahead of current state')
                    if (published['configuration-generation'] == current['configuration-generation']
                            and published['raw'] != current['raw']):
                        raise ValueError('Native VGA publication contradicts its current generation')
                    if prior_current is not None:
                        delta_time = published['virtual-ns'] - prior_current['virtual-ns']
                        delta_generation = (published['configuration-generation'] -
                                            prior_current['configuration-generation'])
                        if delta_generation == 0 and published['raw'] != prior_current['raw']:
                            raise ValueError('Native VGA publication contradicts an observed current configuration')
                        # Equal virtual time provides no order: a paused QOM
                        # write can change configuration without running a CPU.
                        if delta_time * delta_generation < 0:
                            raise ValueError('Native VGA publication configuration contradicts observed time order')
                    if prior is not None:
                        identity = (display['token'], display['update-id'])
                        if identity == prior['identity'] and published != prior['snapshot']:
                            raise ValueError('Native VGA configuration stamp changed under one publication')
            except (ValueError, KeyError) as error:
                raise DebuggerError(str(error)) from error
            stage = 'after-clock'
            after = self._clock_snapshot()
            if (any(before[key] != after[key] for key in ('run', 'epoch', 'counter', 'virtual_ns'))
                    or epoch != after['virtual_clock']['native']['epoch']
                    or before['sequence'] >= after['sequence']):
                raise DebuggerError('Machine clock changed across the stopped VGA configuration observation')
            result = dict(format='fdisbull-vga-configuration-1', context='machine', run=self.run_id,
                epoch=before['epoch'], native_epoch=epoch, clock_domain='QEMU_CLOCK_VIRTUAL',
                current=_public_configuration(current),
                published=_public_configuration(published) if published is not None else None,
                display=self._display_receipt(display, before),
                configuration_matches=(published['configuration-generation'] ==
                    current['configuration-generation']) if published is not None else None,
                publication_configuration_semantics='configuration_observed_at_publication',
                raster_coherence=None, completed_guest_frame=None, guest_frame_id=None,
                cursor_mapping=None, clocks=dict(before=before, after=after), native=deepcopy(raw),
                scope=('Conservative stored VGA configuration and configuration observed at a retained '
                       'renderer publication. Equal raw fingerprints do not establish generation '
                       'identity. Configuration equality does not prove raster coherence, guest '
                       'mode identity, completed drawing, cursor mapping or input readiness.'))
            stage = 'persistence'
            _remaining(self, label='VGA configuration')
            self._event('machine-vga-configuration-observe', result)
            _remaining(self, label='VGA configuration')
            # Current and historical observations have distinct bounded frontiers.
            # Reading an older publication must never replace the live frontier.
            self.vm._vga_configuration_last = deepcopy(current)
            if published is not None:
                self.vm._vga_publication_last = dict(identity=(display['token'], display['update-id']),
                    snapshot=deepcopy(published))
            return result
        except BaseException as error:
            self.vm.close()
            if getattr(error, 'result', None) is None:
                error.result = deepcopy(result) if result is not None else dict(
                    format='fdisbull-vga-configuration-error-1', run=self.run_id, stage=stage,
                    clocks=dict(before=deepcopy(before), after=deepcopy(after)),
                    native=deepcopy(raw), native_received=received)
            raise
