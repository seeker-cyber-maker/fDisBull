"""Real i686/PE32 checks using the established authored Win32 adapter fixture.

The x64 fixture and expectations remain unchanged. Select an explicit offline
guest with FDISBULL_WIN32_VM_CLIENT and its i686 compiler with
FDISBULL_WIN32_CC; a native Windows host may instead supply an i686 compiler.
These tests exercise actual Win32/GDI callbacks, not physical hardware input or
the recovered Snake logic. Compilation, replay inputs, and outputs are retained
under pytest's temporary directory for a caller to seal privately.
"""
from importlib.resources import files
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import uuid

import pytest

import test_memory_win32 as shared


VM = os.environ.get('FDISBULL_WIN32_VM_CLIENT')
CC = os.environ.get('FDISBULL_WIN32_CC') or shutil.which('i686-w64-mingw32-gcc')
pytestmark = pytest.mark.skipif(
    not VM and not (sys.platform == 'win32' and CC),
    reason='requires actual Win32 APIs and an i686 compiler or an explicit offline guest')


class RecordingClient:
    """Retain the authored boundary inputs and actual guest responses."""

    def __init__(self, client, directory):
        self.client, self.directory = client, directory
        self.records = []

    def record(self, operation, **values):
        self.records.append({'operation': operation, **values})
        (self.directory / 'native-i686-receipt.json').write_text(json.dumps({
            'schema': 'fdisbull-authored-win32-i686-tests-v1',
            'scope': 'Actual PE32/GDI adapter callbacks; authored fixture, no original game assets',
            'records': self.records,
        }, indent=2) + '\n')

    def put(self, job, name, data, **kwargs):
        result = self.client.put(job, name, data, **kwargs)
        (self.directory / name).write_bytes(data)
        self.record('put', job=job, name=name, bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest())
        return result

    def get(self, job, name):
        data = self.client.get(job, name)
        (self.directory / name).write_bytes(data)
        self.record('get', job=job, name=name, bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest())
        return data

    def run(self, job, arguments, **kwargs):
        result = self.client.run(job, arguments, **kwargs)
        self.record('run', job=job, argv=arguments, **result)
        return result


class I686Adapter(shared.Adapter):
    def __init__(self, directory):
        self.directory, self.client = directory, None
        self.job = 'win32-i686-unit-' + uuid.uuid4().hex[:12]
        if VM:
            spec = importlib.util.spec_from_file_location('fdb_unit_i686_guest', VM)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.client = RecordingClient(module.Client(), directory)
        source = {'memory-runtime.h': shared.HEADER.encode(),
                  'memory-host-config.h': shared.CONFIG.encode(), 'stub.c': shared.STUB.encode()}
        for name in ('memory-desktop.h', 'memory-desktop.c', 'memory-win32.c'):
            source[name] = files('fdisbull').joinpath('native_runtime/' + name).read_bytes()
        for name, data in source.items():
            (directory / name).write_bytes(data)
            if self.client:
                self.client.put(self.job, name, data)
        self.compile(['memory-win32.c', 'memory-desktop.c', 'stub.c'], 'adapter.exe')

    def compile(self, sources, output):
        arguments = ['-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', '-mwindows',
                     *sources, '-o', output, '-luser32', '-lgdi32']
        if self.client:
            # Official split MinGW packages may expose only a versioned driver
            # until update-alternatives has run. Use that declared real compiler
            # without installing packages or altering the guest's system paths.
            compiler = CC or 'i686-w64-mingw32-gcc'
            built = self.client.run(self.job, [
                'python3', '-c',
                'import subprocess,sys;sys.exit(subprocess.call(sys.argv[1:]))',
                compiler, *arguments], timeout=180)
            assert not built['timed_out'] and built['exit_code'] == 0, built
            image = self.client.get(self.job, output)
        else:
            built = subprocess.run([CC, *arguments], cwd=self.directory,
                                   capture_output=True, text=True, timeout=180)
            assert built.returncode == 0, built.stdout + built.stderr
            image = (self.directory / output).read_bytes()
        assert image[:2] == b'MZ'
        pe = struct.unpack_from('<I', image, 0x3c)[0]
        assert image[pe:pe + 4] == b'PE\0\0'
        assert struct.unpack_from('<H', image, pe + 4)[0] == 0x14c, 'i686 machine required'
        assert struct.unpack_from('<H', image, pe + 24)[0] == 0x10b, 'PE32 required'
        assert struct.unpack_from('<H', image, pe + 24 + 68)[0] == 2, 'native GUI subsystem required'


@pytest.fixture(scope='module')
def adapter(tmp_path_factory):
    return I686Adapter(tmp_path_factory.mktemp('win32-i686-adapter'))


@pytest.fixture(scope='module')
def lifecycle(adapter):
    source = shared.LIFECYCLE.encode()
    (adapter.directory / 'lifecycle.c').write_bytes(source)
    if adapter.client:
        adapter.client.put(adapter.job, 'lifecycle.c', source)
    adapter.compile(['lifecycle.c', 'memory-desktop.c', 'stub.c'], 'lifecycle.exe')
    if adapter.client:
        ran = adapter.client.run(adapter.job, ['wine', 'lifecycle.exe', 'lifecycle.out'], timeout=120)
        assert not ran['timed_out'] and ran['exit_code'] == 0, ran
        data = adapter.client.get(adapter.job, 'lifecycle.out')
    else:
        ran = subprocess.run([str(adapter.directory / 'lifecycle.exe'), 'lifecycle.out'],
                             cwd=adapter.directory, capture_output=True, text=True, timeout=120)
        assert ran.returncode == 0, ran.stdout + ran.stderr
        data = (adapter.directory / 'lifecycle.out').read_bytes()
    assert len(data) == 24 * 4
    return struct.unpack('<24I', data)


def test_real_gdi_palette_origin_letterbox_and_fractional_fit(adapter):
    shared.test_real_gdi_palette_origin_letterbox_and_fractional_fit(adapter)


def test_real_wndproc_physical_keys_modifiers_focus_and_terminal_snapshot(adapter):
    shared.test_real_wndproc_physical_keys_modifiers_focus_and_terminal_snapshot(adapter)


def test_real_pointer_capture_buttons_focus_release_and_native_selector(adapter):
    shared.test_real_pointer_capture_buttons_focus_release_and_native_selector(adapter)


def test_native_timer_and_prefix_replacement_retain_frame(adapter):
    shared.test_native_timer_and_prefix_replacement_retain_frame(adapter)


def test_native_coordinate_carrier_refuses_overflow_instead_of_wrapping(adapter):
    shared.test_native_coordinate_carrier_refuses_overflow_instead_of_wrapping(adapter)


def test_minimize_and_restore_preserve_the_last_valid_native_viewport(lifecycle):
    shared.test_minimize_and_restore_preserve_the_last_valid_native_viewport(lifecycle)


def test_tracking_maximize_and_programmatic_resize_preserve_native_view_budget(lifecycle):
    shared.test_tracking_maximize_and_programmatic_resize_preserve_native_view_budget(lifecycle)
