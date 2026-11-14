"""Bounded stopped physical readback for an existing DESQview task identity.

The source mapper separately checks original-source bytes. This certificate
compares every captured byte, including any source relocation operands.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import math
import time
from types import SimpleNamespace

from .memory_search_runtime import _snapshot, _mapping, _paused, _read

FORMAT = 'fdisbull-desqview-physical-readback-1'
SCOPE = ('two-pass stopped physical/linear equality for this captured snapshot under the supplied '
         'DESQview identity; no continuous residency, execution or allocation-lifetime proof')
MAX_BYTES = 1024 * 1024
MAX_PAGES = 256
MAX_SECONDS = 10


class DesqviewPhysicalError(ValueError):
    """Same-identity physical proof is unavailable; no physical claim is added."""


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


@contextmanager
def _observation_budget(session):
    """One finite observer budget, independent of an unexported run timeout."""
    from .runtime_desqview import DesqviewProviderError
    owner = session.vm
    bound = time.monotonic() + MAX_SECONDS
    missing = object()

    def inherited():
        values = [getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                  getattr(owner, 'operation_deadline', None),
                  *[getattr(channel, 'operation_deadline', None) for channel in
                    (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None]]
        result = []
        for value in values:
            if value is None:
                continue
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError('DESQview physical inherited deadline must be finite')
            result.append(value)
        return result

    bound = min([bound, *inherited()])
    wait = bound-time.monotonic()
    if wait <= 0:
        raise TimeoutError('DESQview physical inherited host deadline expired before admission')
    if not owner.lock.acquire(timeout=wait):
        raise TimeoutError('DESQview physical observer deadline expired waiting for the machine')
    previous_vm = missing
    previous_channels = []
    installed = False
    try:
        if session.vm is not owner:
            raise DesqviewProviderError('DESQview physical owner changed during lock admission')
        bound = min([bound, *inherited()])
        if time.monotonic() >= bound:
            raise TimeoutError('DESQview physical inherited host deadline expired before observation')
        previous_vm = getattr(owner, 'operation_deadline', missing)
        for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)):
            if channel is not None:
                previous_channels.append((channel, getattr(channel, 'operation_deadline', missing)))
        installed = True
        owner.operation_deadline = bound
        for channel, _ in previous_channels:
            channel.operation_deadline = bound
        yield
    finally:
        if installed:
            if previous_vm is missing:
                del owner.operation_deadline
            else:
                owner.operation_deadline = previous_vm
            for channel, previous in previous_channels:
                if previous is missing:
                    if hasattr(channel, 'operation_deadline'):
                        del channel.operation_deadline
                else:
                    channel.operation_deadline = previous
            for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)):
                if channel is not None and all(channel is not prior for prior, _ in previous_channels):
                    # A debugger admitted lazily inherited the temporary VM
                    # bound; return it to the VM's previous outer allowance.
                    channel.operation_deadline = None if previous_vm is missing else previous_vm
        owner.lock.release()


def qualify(provider, snapshot_artifact, native_identity):
    from . import runtime_desqview as dv

    session = provider.session
    if not hasattr(session, 'vm') or not hasattr(session, 'project'):
        raise dv.DesqviewProviderError('Physical DESQview qualification requires its owned native project')
    with _observation_budget(session):
        owner, process = session.vm, session.vm.process
        run, epoch = session.run_id, getattr(session, '_runtime_epoch', None)
        expected_native = deepcopy(native_identity)
        expected_task = None
        selected = session.project.version(session.version['id'])
        source_sha = session.project.source_sha256(selected['id'])

        inherited_deadline = None

        def remaining():
            nonlocal inherited_deadline
            limits = [getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                      getattr(owner, 'operation_deadline', None),
                      *[getattr(channel, 'operation_deadline', None) for channel in
                        (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None]]
            for value in limits:
                if value is None:
                    continue
                try:
                    valid = type(value) in (int, float) and math.isfinite(value)
                except OverflowError:
                    valid = False
                if not valid:
                    raise ValueError('DESQview physical inherited deadline must be finite')
                inherited_deadline = value if inherited_deadline is None else min(inherited_deadline, value)
            if inherited_deadline is not None and time.monotonic() >= inherited_deadline:
                raise TimeoutError('DESQview physical inherited host deadline expired')
            check = getattr(session, '_remaining', None)
            if callable(check):
                check()  # Inherit the caller's absolute deadline; never reset it.

        def own():
            remaining()
            dv._require(session.vm is owner and session.vm.process is process and process is not None
                and session.run_id == run and getattr(session, '_runtime_epoch', None) == epoch
                and not getattr(session, 'closed', False), 'DESQview physical owner/run/epoch changed')
            dv._require(session.version['id'] == selected['id'] and
                session.project.version(selected['id'])['sha256'] == selected['sha256'] and
                session.project.source_sha256(selected['id']) == source_sha,
                'DESQview physical source/version identity changed')

        own()
        before = _paused(session)
        dv._cpu(before)
        dv._require(provider.current_identity() == expected_native,
                    'DESQview physical supplied native identity differs')
        own()

        def task_identity(context):
            matches = session.project.db.execute('''SELECT id FROM runtime_mapping_tasks
                WHERE run=? AND external_id=? AND ended IS NULL LIMIT 2''',
                (run, context.get('task_id'))).fetchall()
            dv._require(len(matches) == 1, 'DESQview physical snapshot task is foreign or inactive')
            task = session.project._mapping_task(matches[0]['id'], active=True)
            expected = dict(run=run, external_id=context.get('task_id'), source_sha256=source_sha,
                            version=selected['id'], version_sha256=selected['sha256'], capture_epoch=epoch)
            dv._require(all(task.get(key) == value for key, value in expected.items()) and
                task.get('automatic_tracking', {}).get('identity', {}).get('provider') == 'source-qualified-desqview'
                and task['automatic_tracking']['identity'].get('native') == expected_native,
                'DESQview physical snapshot task/provider identity differs')
            return task

        def stable():
            own()
            after = _paused(session)
            dv._cpu(after)
            dv._require(after == before, 'DESQview physical observation changed CPU stop')
            dv._require(provider.current_identity() == expected_native and native_identity == expected_native,
                        'DESQview physical native identity changed during readback')
            if expected_task is not None:
                dv._require(task_identity(context) == expected_task,
                            'DESQview physical task identity changed during readback')
            own()

        def unavailable(message):
            # A coincident owner/task/CPU drift must not be hidden behind an
            # optional physical-only failure in the tracker's recovery route.
            stable()
            raise DesqviewPhysicalError(message)

        size_row = session.project.db.execute('SELECT fdb_length(data) FROM debug_artifacts WHERE id=?',
                                              (snapshot_artifact,)).fetchone()
        if size_row is not None and (type(size_row[0]) is not int or not 1 <= size_row[0] <= MAX_BYTES):
            unavailable('DESQview physical snapshot exceeds its 1 MiB bound')
        try:
            row, data, metadata = _snapshot(session.project, snapshot_artifact)
        except (ValueError, KeyError, TypeError) as error:
            raise dv.DesqviewProviderError('DESQview physical snapshot identity is invalid') from error
        context = metadata['snapshot']['context']
        expected = dict(source_sha256=source_sha, version_id=selected['id'],
            version_sha256=selected['sha256'], run_id=run, capture_epoch=epoch, address_space='linear')
        dv._require(row['run'] == run and all(context.get(key) == value for key, value in expected.items())
            and session.metadata.get('source_sha256') == source_sha,
            'DESQview physical snapshot source/run/version/epoch differs')
        expected_task = task_identity(context)
        snapshot_rowid = session.project.db.execute('SELECT rowid FROM debug_artifacts WHERE id=?',
                                                   (snapshot_artifact,)).fetchone()[0]
        dv._require(snapshot_rowid > expected_task['snapshot_floor'],
                    'DESQview physical snapshot predates its task incarnation')
        capture = metadata.get('capture', {})
        dv._require(capture.get('before') == before,
                    'DESQview physical snapshot belongs to a different CPU stop')
        if (getattr(session, '_layer_active', None) or getattr(session, '_dos_task_monitor', None)
                or context.get('qemu_memory_view') is not None):
            unavailable('DESQview physical readback requires the unlayered base memory view')
        region = context.get('region', {})
        start, length = region.get('start'), region.get('length')
        if (type(start) is not int or type(length) is not int or length != len(data)
                or not 0 <= start < start+length <= 2**32 or not 1 <= length <= MAX_BYTES):
            unavailable('DESQview physical snapshot range exceeds its bounded extent')
        mapping, pages = capture.get('mapping'), capture.get('pages')
        if (type(mapping) is not dict or mapping.get('kind') != 'observed-386-pages'
                or type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES
                or mapping.get('page_count') != len(pages)
                or mapping.get('pages_sha256') != _sha(_encoded(pages))
                or context.get('mapping_id') != _sha(_encoded(mapping))):
            unavailable('DESQview physical snapshot has no bounded sealed page mapping')
        state = before['address_state']
        try:
            controls = {key: dv._number(state.get('control', {}).get(key)) for key in ('CR0', 'CR3', 'CR4', 'EFER')}
        except dv.DesqviewProviderError:
            unavailable('DESQview physical readback requires complete legacy paging controls')
        if (state.get('a20') is not True or state.get('paging') is not True
                or state.get('paging_mode') != 'legacy-32'
                or controls['CR0'] & 0x80000001 != 0x80000001
                or controls['CR3'] & 0xfe7 or controls['CR4'] & 0x20 or controls['EFER'] & 0x500):
            unavailable('DESQview physical readback requires A20-enabled non-PAE legacy 4-KiB paging')
        configuration = getattr(owner, 'machine_configuration', {})
        memory_mib = configuration.get('memory_mib')
        if type(memory_mib) is not int or not 1 <= memory_mib <= 0xffffffff:
            unavailable('DESQview physical RAM configuration is unknown')
        ram_end = min(memory_mib << 20, 0xc0000000)

        def ram(address, count):
            return (type(address) is int and type(count) is int and 0 < count <= MAX_BYTES
                and (0 <= address < address+count <= 0xa0000
                     or 0x100000 <= address < address+count <= ram_end))

        def physical(address, count, *, space):
            remaining()
            if space == 'physical':
                if not ram(address, count):
                    unavailable('DESQview physical readback is outside configured conventional/extended RAM')
            elif space != 'virtual' or not start <= address < address+count <= start+length:
                unavailable('DESQview linear readback exceeds its captured extent')
            # Native I/O, short reads and timeouts intentionally propagate.
            return session._stopped().memory(address, count, space=space)

        bounded = SimpleNamespace(vm=owner, _stopped=lambda: SimpleNamespace(memory=physical))

        def observed_mapping():
            remaining()
            try:
                value = _mapping(bounded, start, length, 'linear', before)
            except ValueError as error:
                if str(error).startswith('Memory snapshot has an unqualified mapping:'):
                    unavailable('DESQview physical page mapping is unsupported or not present')
                raise
            if value != (mapping, pages):
                unavailable('DESQview physical page mapping changed since capture')

        ranges = []
        cursor = start
        by_page = {}
        for page in pages:
            try:
                linear_page = int(page['linear'], 16)
                physical_page = int(page['physical'], 16)
            except (KeyError, TypeError, ValueError):
                unavailable('DESQview physical page address is invalid')
            if (linear_page in by_page or linear_page & 4095 or physical_page & 4095
                    or not 0 <= linear_page < 2**32 or not 0 <= physical_page < 2**32):
                unavailable('DESQview physical page mapping is duplicate, unaligned or out of range')
            by_page[linear_page] = page
        while cursor < start+length:
            page = by_page.get(cursor & ~4095)
            if page is None:
                unavailable('DESQview physical snapshot page coverage is incomplete')
            count = min(start+length-cursor, 4096-(cursor & 4095))
            address = int(page['physical'], 16)+(cursor & 4095)
            if not ram(address, count):
                unavailable('DESQview physical target is outside configured conventional/extended RAM')
            offset = cursor-start
            ranges.append(dict(linear_start=cursor, physical_start=address, length=count,
                               sha256=_sha(data[offset:offset+count])))
            cursor += count
        for _ in range(2):
            observed_mapping()  # Each call gets a fresh page-table cache.
            remaining()
            linear = _read(bounded, start, length, 'linear')
            if linear != data:
                unavailable('DESQview linear bytes changed since snapshot capture')
            for extent in ranges:
                remaining()
                value = _read(bounded, extent['physical_start'], extent['length'], 'physical')
                offset = extent['linear_start']-start
                if value != data[offset:offset+extent['length']]:
                    unavailable('DESQview physical/linear snapshot bytes disagree')
            observed_mapping()
            stable()
        # Detect artifact substitution as well as a changing live observation.
        try:
            final_row, final_data, final_metadata = _snapshot(session.project, snapshot_artifact)
        except (ValueError, KeyError, TypeError) as error:
            raise dv.DesqviewProviderError('DESQview physical snapshot changed during readback') from error
        dv._require(final_row['sha256'] == row['sha256'] and final_data == data and final_metadata == metadata,
                    'DESQview physical snapshot changed during readback')
        stable()
        return dict(format=FORMAT, qualified=True, snapshot=snapshot_artifact, snapshot_sha256=row['sha256'],
            mapping_id=context['mapping_id'], context_sha256=_sha(_encoded(context)),
            native_identity_sha256=_sha(_encoded(expected_native)), ranges=ranges,
            verification_scope=SCOPE, passes=2)
