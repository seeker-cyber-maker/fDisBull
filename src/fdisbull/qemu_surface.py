"""Stopped QEMU display surfaces, without inventing guest frame boundaries."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
from pathlib import Path
import uuid

from .dosbox_rpc import DebuggerError


class QemuSurfaceMixin:
    def capture_surface(self, name='machine-surface.png', *, max_bytes=None):
        """Retain one PNG and its stopped clock/CPU bracket.

        A QMP screendump refreshes a display surface. The capture identity is an
        observation ID, not a VGA frame number, vertical blank or drawing fence.
        In particular a program may be stopped halfway through updating VRAM.
        """
        from PIL import Image
        from .debugger import _file_name

        _file_name(name)
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 16 * 1024**2):
            raise ValueError('Surface PNG max_bytes must be an integer in 1..16777216')
        if self.project is None:
            raise ValueError('Display capture requires a project-bound machine')
        if self.project.db.in_transaction:
            raise ValueError('Display capture requires a project outside a caller-owned transaction')
        if 'screendump' not in getattr(self.vm, 'qmp_commands', ()):
            raise ValueError('Selected QEMU executable does not provide screendump')
        self._stopped()
        before_clock = self.clock_observe()
        before_cpu = self.registers()
        capture_id = uuid.uuid4().hex
        path = Path(self.vm.temporary.name) / ('surface-' + capture_id + '.ppm')
        try:
            self.vm.qmp.call('screendump', {'filename': str(path)})
            if not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024 * 1024:
                raise DebuggerError('QEMU display surface is missing or exceeds 64 MiB')
            with Image.open(path) as image:
                width, height = image.size
                if image.format != 'PPM' or not 1 <= width <= 8192 or not 1 <= height <= 8192:
                    raise DebuggerError('QEMU returned an unsupported display surface')
                output = io.BytesIO()
                image.convert('RGB').save(output, format='PNG')
            after_cpu = self.registers()
            after_clock = self.clock_observe()
        finally:
            path.unlink(missing_ok=True)
        if before_cpu != after_cpu:
            self.vm.close()
            raise DebuggerError('Selected CPU changed across the stopped display capture')
        if (before_clock['epoch'] != after_clock['epoch']
                or before_clock['counter'] != after_clock['counter']
                or before_clock.get('virtual_ns') != after_clock.get('virtual_ns')):
            self.vm.close()
            raise DebuggerError('Observed machine clock changed across the stopped display capture')
        data = output.getvalue()
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError('Surface PNG exceeds its image byte budget before artifact publication')
        metadata = dict(
            context='machine', source='qemu_display_surface',
            capture='QEMU stored display surface', capture_id=capture_id,
            run=self.run_id, width=width, height=height,
            sha256=hashlib.sha256(data).hexdigest(), stopped=True,
            completed_guest_frame=None, guest_frame_id=None,
            clocks=dict(before=before_clock, after=after_clock),
            registers=deepcopy(before_cpu), selected_cpu_unchanged=True,
            clock_stability=('virtual_clock_and_instruction_counter_unchanged' if
                             before_clock.get('virtual_ns') is not None else
                             'instruction_counter_unchanged' if
                             before_clock['counter']['state']=='observed' else 'not_observable'),
            scope=('Observed with all vCPUs stopped under the owned machine lock; '
                   'selected CPU and clock bracket. No completed guest frame, '
                   'frame freshness, UI readiness or input-consumption claim.'))
        artifact = self._artifact(name, 'screenshot', data, metadata)
        self._event('machine-capture-surface', dict(
            artifact=artifact['artifact'], capture_id=capture_id,
            sha256=metadata['sha256'], source=metadata['source'],
            completed_guest_frame=None))
        return artifact
