"""Explicit adapter for the Sarien-derived position/priority scene kernel.

This module never builds or discovers a library, launches a guest, or completes
a QEMU effect. Callers supply an exact library identity and complete scene
inputs. The kernel's upstream provenance/license accompany sarien_scene.c.
"""
from __future__ import annotations

from copy import deepcopy
import ctypes as C
from hashlib import sha256
from pathlib import Path
import re


WIDTH, HEIGHT = 160, 168
ANIMATED, DRAWN, IGNORE_OBJECTS, IGNORE_BLOCKS = 1, 2, 4, 8
ON_WATER, ON_LAND, IGNORE_HORIZON, FIXED_PRIORITY = 16, 32, 64, 128
ACTOR_FIELDS = ('id', 'x', 'y', 'prev_x', 'prev_y', 'width', 'height',
                'flags', 'priority')


class SceneInputError(ValueError):
    """An explicit scene input or native-library contract was rejected."""


class _Actor(C.Structure):
    _fields_ = [(name, C.c_int32 if index < 7 else C.c_uint32)
                for index, name in enumerate(ACTOR_FIELDS)]


class _Placement(C.Structure):
    _fields_ = [(name, C.c_int32 if index < 3 else C.c_uint32)
                for index, name in enumerate(('status', 'x', 'y', 'priority',
                                             'attempts', 'ego_trigger', 'ego_water'))]


class _Blit(C.Structure):
    _fields_ = [('written_pixels', C.c_uint32), ('hidden', C.c_uint32)]


def _integer(value, name, *, unsigned=False):
    minimum, maximum = (0, 2**32 - 1) if unsigned else (-2**31, 2**31 - 1)
    if type(value) is not int or not minimum <= value <= maximum:
        raise SceneInputError(f'{name} is outside its native integer type')
    return value


def _bytes(value, size, name):
    if type(value) is not bytes or len(value) != size:
        raise SceneInputError(f'{name} requires exactly {size} immutable bytes')
    return (C.c_uint8 * size).from_buffer_copy(value)


def _actors(values):
    if type(values) is not list or not 1 <= len(values) <= 16:
        raise SceneInputError('A scene requires 1..16 explicit actor records')
    rows = []
    for row in values:
        if type(row) is not dict or set(row) != set(ACTOR_FIELDS):
            raise SceneInputError('Actor fields differ from the scene ABI')
        rows.append(_Actor(*(_integer(row[name], name, unsigned=index >= 7)
                             for index, name in enumerate(ACTOR_FIELDS))))
    return (_Actor * len(rows))(*rows)


class SarienScene:
    """Load one explicitly identified ABI-1 library for many scene operations."""

    def __init__(self, library, *, expected_sha256):
        if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
            raise SceneInputError('An exact expected library SHA-256 is required')
        self.path = Path(library).expanduser().resolve(strict=True)
        if not self.path.is_file() or self.path.stat().st_size > 64 * 1024**2:
            raise SceneInputError('The explicit scene library is not a bounded file')
        self.binary_sha256 = sha256(self.path.read_bytes()).hexdigest()
        if self.binary_sha256 != expected_sha256:
            raise SceneInputError('Scene library identity differs')
        self._lib = C.CDLL(str(self.path))
        self._lib.agi_scene_abi_version.argtypes = []
        self._lib.agi_scene_abi_version.restype = C.c_uint32
        if self._lib.agi_scene_abi_version() != 1:
            raise SceneInputError('Unsupported scene library ABI')
        byte_pointer = C.POINTER(C.c_uint8)
        self._lib.agi_scene_place.argtypes = [
            byte_pointer, C.c_size_t, byte_pointer, C.c_size_t, C.c_int32,
            C.POINTER(_Actor), C.c_size_t, C.c_uint32, C.c_uint32,
            C.POINTER(_Placement)]
        self._lib.agi_scene_place.restype = C.c_int
        self._lib.agi_scene_blit.argtypes = [
            byte_pointer, byte_pointer, C.c_size_t, byte_pointer, C.c_size_t,
            C.c_int32, C.c_int32, C.c_uint32, C.c_uint32, C.c_uint32,
            C.c_uint32, C.POINTER(_Blit)]
        self._lib.agi_scene_blit.restype = C.c_int

    def place(self, priority, bands, *, horizon, actors, target_id, max_attempts=4096):
        """Plan one placement; budget exhaustion returns the original pose."""
        plane = _bytes(priority, WIDTH * HEIGHT, 'priority plane')
        table = _bytes(bands, HEIGHT, 'priority bands')
        rows = _actors(actors)
        output = _Placement()
        status = self._lib.agi_scene_place(
            plane, len(plane), table, len(table), _integer(horizon, 'horizon'),
            rows, len(rows), _integer(target_id, 'target_id', unsigned=True),
            _integer(max_attempts, 'max_attempts', unsigned=True), C.byref(output))
        if status not in (0, 1) or output.status != status:
            raise SceneInputError('Native placement rejected the scene inputs')
        return {'status': 'ok' if status == 0 else 'budget_exhausted',
                'x': output.x, 'y': output.y, 'priority': output.priority,
                'attempts': output.attempts, 'ego_trigger': bool(output.ego_trigger),
                'ego_water': bool(output.ego_water)}

    def blit(self, visual, priority, cel, *, x, baseline, width, height,
             transparent, actor_priority):
        """Compose an already oriented cel into copies of the supplied planes."""
        screen = _bytes(visual, WIDTH * HEIGHT, 'visual plane')
        control = _bytes(priority, WIDTH * HEIGHT, 'priority plane')
        width = _integer(width, 'width', unsigned=True)
        height = _integer(height, 'height', unsigned=True)
        if not 1 <= width <= WIDTH or not 1 <= height <= HEIGHT:
            raise SceneInputError('Cel dimensions exceed the scene canvas')
        pixels = _bytes(cel, width * height, 'cel')
        output = _Blit()
        status = self._lib.agi_scene_blit(
            screen, control, len(screen), pixels, len(pixels),
            _integer(x, 'x'), _integer(baseline, 'baseline'), width, height,
            _integer(transparent, 'transparent', unsigned=True),
            _integer(actor_priority, 'actor_priority', unsigned=True), C.byref(output))
        if status != 0:
            raise SceneInputError('Native compositor rejected the scene inputs')
        return {'visual': bytes(screen), 'priority': bytes(control),
                'written_pixels': output.written_pixels, 'hidden': bool(output.hidden)}

    def preview(self, visual, priority, bands, *, horizon, actors, layers,
                max_attempts=4096):
        """Resolve and compose a caller-ordered batch in a detached scene model.

        Each layer has actor_id, cel (already oriented bytes), and transparent.
        Successful placements become drawn peers for subsequent placements in
        this preview. This explicit authored order is not an interpreter sprite
        list, and the result does not commit a pending QEMU draw.
        """
        _actors(actors)
        if type(layers) is not list or not 1 <= len(layers) <= 16:
            raise SceneInputError('A preview requires 1..16 explicit layers')
        identifiers = []
        for layer in layers:
            if type(layer) is not dict or set(layer) != {'actor_id', 'cel', 'transparent'}:
                raise SceneInputError('Preview layer fields differ')
            identifiers.append(_integer(layer['actor_id'], 'actor_id', unsigned=True))
        if len(identifiers) != len(set(identifiers)):
            raise SceneInputError('Duplicate preview actor')
        original_actors, working = deepcopy(actors), deepcopy(actors)
        screen, control, steps = visual, priority, []
        for layer in layers:
            target = next((row for row in working if row['id'] == layer['actor_id']), None)
            if target is None:
                raise SceneInputError('Preview actor is absent from scene context')
            placement = self.place(control, bands, horizon=horizon, actors=working,
                                   target_id=target['id'], max_attempts=max_attempts)
            steps.append({'actor_id': target['id'], 'placement': placement})
            if placement['status'] != 'ok':
                return {'status': 'budget_exhausted', 'visual': visual, 'priority': priority,
                        'actors': original_actors, 'steps': steps,
                        'native_draw_committed': False, 'presentation_established': False}
            composed = self.blit(
                screen, control, layer['cel'], x=placement['x'], baseline=placement['y'],
                width=target['width'], height=target['height'],
                transparent=layer['transparent'], actor_priority=placement['priority'])
            target.update(x=placement['x'], y=placement['y'], prev_x=placement['x'],
                          prev_y=placement['y'], priority=placement['priority'],
                          flags=target['flags'] | DRAWN)
            screen, control = composed['visual'], composed['priority']
            steps[-1]['composition'] = {key: composed[key] for key in ('written_pixels', 'hidden')}
        return {'status': 'preview_complete', 'visual': screen, 'priority': control,
                'actors': working, 'steps': steps,
                'native_draw_committed': False, 'presentation_established': False}
