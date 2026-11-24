"""Capture-only paged LE evidence. No process lifetime or binding is inferred."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
from functools import partial
from .qemu_machine import machine_trace_operation

from iced_x86 import Decoder

from .qemu_le_translation import parse_hmp, translate_linear, observe_descriptor, require_executable_walks
from .qemu_paged_le_match import match
from .qemu_dos_source_admission import _source, _integer
from .qemu_runtime_capture import _qemu_input_hashes

ADMISSION = 'paged-le-stopped-capture-v1'
MAX_WITNESS_BYTES = 2 * 1024 * 1024
MAX_WITNESS_ROWS = 8192


def _ram_limits(configuration):
    """Bounds for ordinary low memory and the optional launch-verified high bank."""
    from .qemu_ram import low_ram_end, high_ram_end

    total = configuration['memory_mib']
    if type(total) is not int or not 16 <= total <= 8192:
        raise ValueError('Invalid captured guest RAM configuration')
    return low_ram_end(configuration), high_ram_end(configuration)


def _ram_extent(address, length, ram_end, high_end=None):
    return (
        type(address) is int
        and type(length) is int
        and length > 0
        and (
            0 <= address < address + length <= 0xA0000
            or 0x100000 <= address < address + length <= ram_end
            or high_end is not None and 2**32 <= address < address + length <= high_end
        )
    )


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _producer():
    root = Path(__file__).parent
    return {
        n: _sha((root / n).read_bytes())
        for n in (
            'qemu_paged_le_capture.py',
            'qemu_paged_le_match.py',
            'qemu_dos_le_match.py',
            'qemu_le_translation.py',
            'qemu_dos_source_admission.py',
            'qemu_ram.py',
            'dos_memory.py',
            'le.py',
        )
    }


_PRE_EXTENDED_TRANSLATION = '61ff7f0bde924f6cc741dfcbf94a7ddde2ae561c6ebadb7df84fdcf072b31f38'


def _compatible_producer(recorded, current, *, tracking=False):
    """Accept only exact manifests for current and retained supported producers."""
    if recorded == current:
        return True
    # Retain the CMPXCHG producer as an exact complete manifest.
    cmpxchg = dict(current)
    cmpxchg.update({
        'qemu_le_translation.py': '4491743cf9a05dd0ed49b4c06ff529fe748666b48584ea06e699c33273d80225',
        'qemu_paged_le_capture.py': 'bedf72206421088ecaaadebaa0b96b69caeb0d7dbcbb7fef13448b368bc7efc5',
    })
    if recorded == cmpxchg:
        return True
    # Retain the dirty-overlay producer as an exact complete manifest.
    overlay = dict(current)
    overlay.update({
        'qemu_le_translation.py': 'ea9c38415d4cf1d9a3ec1cad12a3057bb43200b251bec89bac12e5aaa2cf3624',
        'qemu_paged_le_capture.py': 'deace5bf098d1511943a48d2d93e5328683976bbb681eefae3b341aecea22a3f',
    })
    if recorded == overlay:
        return True
    # Preserve the immediately preceding physical64 producer exactly. Its
    # native paging allowances cover only its two already qualified images.
    physical64 = dict(current)
    physical64.update({
        'qemu_le_translation.py': '264bd620cf88d782d2a5dbb5650b014b1b257400f3cdae30e8868d3a0a29cb44',
        'qemu_paged_le_capture.py': '2581302612566a4c03bbc8df8d1280a33d6eb4eb782fa7f4e7adf168ae4bbc19',
    })
    if recorded == physical64:
        return True
    # Preserve the exact pre-physical64 producer, including tracking variants.
    pre_physical64 = dict(current)
    pre_physical64.update({
        'qemu_le_translation.py': 'd25de015b988de444bd70bf53dfd4be64e3ed8651373748b05d679ba6f8c536f',
        'qemu_paged_le_capture.py': '497050af45d0361b56db8015e68ad9503f6983c726afa9e6bb2eac53230a6fba',
    })
    if tracking:
        pre_physical64['qemu_paged_le_tracking.py'] = '8319d44440b59bb8bfe954af36618ab768342dfdd64cd9fe2863e413063347af'
    if recorded == pre_physical64:
        return True
    previous = dict(current)
    previous.update({
        'qemu_le_translation.py': '6e40403e81266323e8e96a978a3c73764b7bc337724880835bc968206ea13ee6',
        'qemu_paged_le_capture.py': '33e589a44d2e2a8be59c4bd46f814d213cbf7883009b3cd6ef0dfaafe7ae8d44',
    })
    if tracking:
        previous.update({
            'qemu_paged_le_observation.py': 'e67420f21005435602945c25ed8aa586a04e34d6d18958786bfb82814dba3243',
            'qemu_paged_le_tracking.py': '5e25bb801f0f78a6d3c9eb5ceeccae63341435632d9dab51c124e8a547e2048c',
        })
    if recorded == previous:
        return True
    extended = dict(current)
    extended.pop('qemu_ram.py', None)
    extended.update({
        'qemu_le_translation.py': 'b96f47b9cdcd226e85a21d3d1ec760d47225a0f202597489f90df1668887ccb4',
        'qemu_paged_le_capture.py': '48d5d2cf273e84fa4dd83a95f7847352eeb32ae4441bea7a88b562a7b349472a',
        'qemu_dos_source_admission.py': '44bc7dbb7c10aa9b52d592a86e8053e5d93975c16c25bb723e2537094b519e58',
    })
    if tracking:
        extended.update({
            'qemu_machine.py': 'dd9ab60db3d67f955573dce4a10cdf5ce99711c6539c4499b6a101c85049c44c',
            'qemu_dos_le_binding.py': 'a2a61a1bf573267a846fcb9b47c99d3e0fbb14d3dfd7f33418aaae75cd7e90c2',
            'qemu_paged_le_observation.py': '5ba7074e4ff62f68452cb72c6f6ae1afd70f86c79cf49c2d215cf916a902d37b',
            'qemu_paged_le_tracking.py': 'aec5a489ade007dc3e5a1a230b4beef54020f60188857a2a94c89bdd07225e57',
        })
    if recorded == extended:
        return True
    legacy = dict(extended)
    legacy['qemu_le_translation.py'] = _PRE_EXTENDED_TRANSLATION
    legacy['qemu_paged_le_capture.py'] = '5d9200b640fc26ea48034aac3d004de9edf85ee0bbeb3bc69829a77eff19ced6'
    if tracking:
        legacy['qemu_paged_le_observation.py'] = '342b6b8e06c17deb280c32fa74621d1463043dd586a844dd0a711b579f5aa265'
        legacy['qemu_paged_le_tracking.py'] = '56e5313387d1a84ce008ac3bb60922efa4b5a72d5123364983ab73efd937cd71'
    return recorded == legacy


def _supports_extended_walks(recorded):
    return recorded.get('qemu_le_translation.py') != _PRE_EXTENDED_TRANSLATION


def _supports_high_ram(recorded, current):
    return recorded == current or (
        recorded.get('qemu_le_translation.py') in (
            '4491743cf9a05dd0ed49b4c06ff529fe748666b48584ea06e699c33273d80225',
            'ea9c38415d4cf1d9a3ec1cad12a3057bb43200b251bec89bac12e5aaa2cf3624',
            '264bd620cf88d782d2a5dbb5650b014b1b257400f3cdae30e8868d3a0a29cb44',
            'd25de015b988de444bd70bf53dfd4be64e3ed8651373748b05d679ba6f8c536f',
            '6e40403e81266323e8e96a978a3c73764b7bc337724880835bc968206ea13ee6')
        and _compatible_producer(recorded, current, tracking='qemu_paged_le_tracking.py' in current)
    )


def _supports_pse36(recorded, current, image_hash):
    # A historical producer may only use images that it itself admitted.
    from .qemu_le_translation import QEMU_TCG_QUALIFIED_IMAGE, QEMU_TCG_PHYSICAL64_IMAGE, QEMU_TCG_OVERLAY_WRITE_IMAGE, QEMU_TCG_CMPXCHG_IMAGE
    if recorded == current:
        return True
    if not _compatible_producer(recorded, current, tracking='qemu_paged_le_tracking.py' in current):
        return False
    translation = recorded.get('qemu_le_translation.py')
    if translation == '4491743cf9a05dd0ed49b4c06ff529fe748666b48584ea06e699c33273d80225':
        return image_hash in (QEMU_TCG_QUALIFIED_IMAGE, QEMU_TCG_PHYSICAL64_IMAGE, QEMU_TCG_OVERLAY_WRITE_IMAGE, QEMU_TCG_CMPXCHG_IMAGE)
    if translation == 'ea9c38415d4cf1d9a3ec1cad12a3057bb43200b251bec89bac12e5aaa2cf3624':
        return image_hash in (QEMU_TCG_QUALIFIED_IMAGE, QEMU_TCG_PHYSICAL64_IMAGE, QEMU_TCG_OVERLAY_WRITE_IMAGE)
    if translation == '264bd620cf88d782d2a5dbb5650b014b1b257400f3cdae30e8868d3a0a29cb44':
        return image_hash in (QEMU_TCG_QUALIFIED_IMAGE, QEMU_TCG_PHYSICAL64_IMAGE)
    return (translation == 'd25de015b988de444bd70bf53dfd4be64e3ed8651373748b05d679ba6f8c536f'
            and image_hash == QEMU_TCG_QUALIFIED_IMAGE)


def _replay_qemu_image(recorded, current, image_hash):
    """Do not give historical producers new native-image allowances."""
    from .qemu_le_translation import QEMU_TCG_OVERLAY_WRITE_IMAGE, QEMU_TCG_CMPXCHG_IMAGE, QEMU_TCG_ATOMIC_BATCH_IMAGE
    if recorded != current and image_hash == QEMU_TCG_ATOMIC_BATCH_IMAGE:
        return None
    if (recorded != current and image_hash == QEMU_TCG_CMPXCHG_IMAGE
            and not _supports_pse36(recorded, current, image_hash)):
        return None
    if (recorded != current and image_hash == QEMU_TCG_OVERLAY_WRITE_IMAGE
            and not _supports_pse36(recorded, current, image_hash)):
        return None
    return image_hash


def _pse36(configuration, image_hash):
    from .qemu_le_translation import QEMU_TCG_QUALIFIED_IMAGES

    return _ram_limits(configuration)[1] is not None and image_hash in QEMU_TCG_QUALIFIED_IMAGES


def _cpu(registers, context):
    state = registers['address_state']
    cs = state['segments']['cs']
    if (
        registers['cpu_mode'] != 'protected'
        or state['code_bits'] != 32
        or state['machine_vcpus'] != 1
        or state['register_context_match'] is not True
        or type(state['paging']) is not bool
        or state['a20'] is not True
    ):
        raise ValueError('Paged LE capture requires one stopped protected32 CPU with A20')
    if any(
        _integer(state['control'][key.upper()]) != context[key]
        for key in ('cr0', 'cr3', 'cr4', 'efer')
    ) or state['paging'] != bool(context['cr0'] & 0x80000000):
        raise ValueError('HMP and stopped CPU controls differ')
    cpu = dict(
        mode='protected',
        bits=32,
        cs=_integer(cs['selector']),
        ip=_integer(registers['instruction_pointer']),
        cs_base=_integer(cs['base']),
        cs_limit=_integer(cs['limit']),
        cs_attributes=_integer(cs['attributes']),
    )
    if (
        _integer(registers['registers']['cs']) != cpu['cs']
        or _integer(registers['linear_pc']) != cpu['cs_base'] + cpu['ip']
    ):
        raise ValueError('Paged LE CS context differs')
    return cpu


def _file_backed(image, object_index, offset, length):
    end = offset + length
    covered = offset
    pages = (p for p in image.metadata['le']['pages'] if p['object'] == object_index)
    for page in sorted(pages, key=lambda p: p['object_offset']):
        if page['object_offset'] <= covered < page['object_offset'] + page['file_size']:
            covered = min(end, page['object_offset'] + page['file_size'])
    return covered == end


def _backing(walks):
    return [dict(physical_address=hex(w['physical']), length=w['length']) for w in walks]


def _interpret(image, cpu, context, read, *, observed_walks=None):
    descriptor = observe_descriptor(context, cpu['cs'], read)
    result = match(image, cpu, descriptor, read)
    if result is None:
        raise ValueError('Current instruction has no bounded LE source match')
    evidence = result['identity_evidence']
    placement = evidence['runtime_code_base']
    index = evidence['code_object']
    obj = next(o for o in image.metadata['le']['objects'] if o['index'] == index)
    region = next(r for r in image.regions if r.start == obj['virtual_address'])
    offset = cpu['cs_base'] + cpu['ip'] - placement
    if not 0 <= offset < obj['virtual_size']:
        raise ValueError('Invalid matched instruction offset')
    available = min(15, cpu['cs_limit'] - cpu['ip'] + 1, len(region.data) - offset)
    raw = read(cpu['cs_base'] + cpu['ip'], available)
    ins = Decoder(32, raw, ip=cpu['ip']).decode()
    source = Decoder(
        32, region.data[offset : offset + available], ip=obj['virtual_address'] + offset
    ).decode()
    if ins.is_invalid or source.is_invalid or source.len != ins.len:
        raise ValueError('Current source instruction shape differs')
    size = ins.len
    if observed_walks is not None:
        require_executable_walks(observed_walks[cpu['cs_base'] + cpu['ip'], available], size)
    if not _file_backed(image, index, offset, size):
        raise ValueError('Current instruction is not fully file backed')
    placements = {index: placement}
    for proof in evidence['object_proofs']:
        placements[proof['object_index']] = proof.get(
            'runtime_base', proof.get('descriptor', {}).get('base')
        )
    expected = bytearray(region.data[offset : offset + size])
    touched = set()
    for fix in image.metadata['le']['fixups']:
        low, high = fix['source_offset'], fix['source_offset'] + fix['width']
        if fix['source_object'] != index or low >= offset + size or high <= offset:
            continue
        if fix.get('duplicate_of') is not None:
            continue
        positions = set(range(low, high))
        target = placements.get(fix['target_object'])
        if (
            low < offset
            or high > offset + size
            or touched & positions
            or fix['source_type'] != 'offset32'
            or fix['width'] != 4
            or fix.get('addend') is not None
            or target is None
        ):
            raise ValueError('Current instruction has unsupported or unproved fixup')
        touched |= positions
        value = target + fix['target_offset']
        if not 0 <= value < 2**32:
            raise ValueError('Fixup exceeds 32 bits')
        expected[low - offset : high - offset] = value.to_bytes(4, 'little')
    if raw[:size] != expected:
        raise ValueError('Current source instruction or full fixup differs')
    return dict(
        descriptor=descriptor,
        match=result,
        instruction_size=size,
        placements=[
            dict(
                object_index=k,
                runtime_base=v,
                bits=next(o['bits'] for o in image.metadata['le']['objects'] if o['index'] == k),
            )
            for k, v in sorted(placements.items())
        ],
        source_location=dict(
            source_view='embedded-le',
            application_source_sha256=image.metadata['le']['application_source_sha256'],
            object_id='le:' + str(index),
            object_index=index,
            object_offset=offset,
            preferred_address=obj['virtual_address'] + offset,
        ),
    )


def _capture_extent(image, cpu, interpretation, start, length):
    """Bind a requested span to the uniquely matched executable object and CS."""
    if (
        type(start) is not int
        or type(length) is not int
        or not 1 <= length <= 65536
        or not 0 <= start < start + length <= 2**32
    ):
        raise ValueError('Invalid LE capture extent')
    selector_offset = start - cpu['cs_base']
    if selector_offset < 0 or selector_offset + length - 1 > cpu['cs_limit']:
        raise ValueError('LE capture exceeds the observed code selector')
    index = interpretation['match']['identity_evidence']['code_object']
    obj = next(o for o in image.metadata['le']['objects'] if o['index'] == index)
    candidates = [p for p in interpretation['placements'] if p['object_index'] == index]
    if (
        len(candidates) != 1
        or candidates[0]['bits'] != 32
        or not obj['executable']
        or not candidates[0]['runtime_base'] <= start
        or start + length > candidates[0]['runtime_base'] + obj['virtual_size']
    ):
        raise ValueError('LE capture exceeds the admitted executable object')
    offset = start - candidates[0]['runtime_base']
    if not _file_backed(image, index, offset, length):
        raise ValueError('LE capture is not fully file backed')
    return (
        dict(
            source_view='embedded-le',
            application_source_sha256=image.metadata['le']['application_source_sha256'],
            object_id='le:' + str(index),
            object_index=index,
            object_offset=offset,
            preferred_address=obj['virtual_address'] + offset,
        ),
        selector_offset,
    )


def _check_decoded_span(observation, raw, start, selector_offset):
    decoded = Decoder(32, raw, ip=selector_offset).decode()
    instructions = observation['instructions']
    if instructions:
        first = instructions[0]
        if (
            decoded.is_invalid
            or first['size'] != decoded.len
            or first['bytes'] != raw[: decoded.len].hex()
            or int(first['runtime_address'], 16) != start
        ):
            raise ValueError('Captured decoded instruction differs from observed bytes')
    elif not decoded.is_invalid:
        raise ValueError('Captured decoded instruction is missing')
    return 0 if decoded.is_invalid else decoded.len


def qualify(session, observed):
    """Return an independently replayable capture, or None if unsupported."""
    try:
        return _qualify(session, observed)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, StopIteration):
        return None


@partial(machine_trace_operation, label="Translated LE code capture", default_timeout_ms=10000)
def _qualify(session, observed):
    from .le import load_runtime_le_carrier
    from .project import now

    if (
        observed['space'] != 'linear'
        or observed['view'] not in ('ram', 'execute')
        or observed['active_layers']
        or getattr(session, '_dos_task_monitor', None)
        or getattr(session, '_dos_task_binding', None)
    ):
        return None
    process = session._process
    if (
        not process
        or process['state'] != 'active'
        or process.get('machine_closed')
        or process['capture_epoch'] != session._runtime_epoch
    ):
        return None
    if session.closed or session.vm.process is None or session.vm.process.poll() is not None:
        return None
    saved_process = deepcopy(process)
    producer = _producer()
    source, identity = _source(session, None)
    image = load_runtime_le_carrier(source)
    registers = session.registers()
    hmp = session.vm.qmp.call(
        'human-monitor-command', {'command-line': 'info registers'}, timeout_ms=session._remaining()
    )
    context = parse_hmp(hmp)
    cpu = _cpu(registers, context)
    remote = session._stopped()
    reads = {}
    linear_reads = {}
    memory_mib = session.vm.machine_configuration['memory_mib']
    ram_end, high_end = _ram_limits(session.vm.machine_configuration)
    inputs = _qemu_input_hashes(session.metadata['runtime_inputs'])
    if hasattr(session.vm, 'inputs') and _qemu_input_hashes(session.vm.inputs) != inputs:
        raise ValueError('Paged LE native input identity differs')
    if (_ram_limits(session.metadata['machine_configuration']) != (ram_end, high_end)
            or session.metadata['machine_configuration']['memory_mib'] != memory_mib):
        raise ValueError('Guest RAM configuration differs from run metadata')
    retained_bytes = 0
    walk_count = 0

    def physical(a, n):
        nonlocal retained_bytes
        if not _ram_extent(a, n, ram_end, high_end):
            raise ValueError('Paged LE witness is outside RAM')
        key = (a, n)
        if key not in reads:
            if len(reads) >= MAX_WITNESS_ROWS or retained_bytes + n > MAX_WITNESS_BYTES:
                raise ValueError('Paged LE physical witness budget exceeded')
            retained_bytes += n
        value = remote.memory(a, n, space='physical', timeout_ms=session._remaining())
        if len(value) != n or key in reads and reads[key] != value:
            raise ValueError('Physical witness changed')
        reads[key] = value
        return value

    def virtual(a, n):
        return remote.memory(a, n, space='virtual', timeout_ms=session._remaining())

    def read(a, n):
        nonlocal walk_count
        key = (a, n)
        if type(a) is not int or type(n) is not int or n <= 0:
            raise ValueError('Invalid linear witness')
        expected_walks = ((a & 4095) + n + 4095) // 4096
        if key not in linear_reads and (
            len(linear_reads) >= MAX_WITNESS_ROWS or walk_count + expected_walks > MAX_WITNESS_ROWS
        ):
            raise ValueError('Paged LE walk witness budget exceeded')
        data, walks = translate_linear(context, a, n, physical, virtual,
                                       qemu_image_sha256=inputs.get('qemu_image'), high_ram_end=high_end,
                                       pse36=_pse36(session.vm.machine_configuration, inputs.get('qemu_image')))
        if key in linear_reads and linear_reads[key] != walks:
            raise ValueError('Page walks changed')
        if key not in linear_reads:
            walk_count += len(walks)
        linear_reads[key] = walks
        return data

    interpretation = _interpret(image, cpu, context, read, observed_walks=linear_reads)
    start = int(observed['runtime_address'], 16)
    length = observed['length']
    raw = bytes.fromhex(observed['hex'])
    location, selector_offset = _capture_extent(image, cpu, interpretation, start, length)
    data = read(start, length)
    walks = linear_reads[start, length]
    instruction_size = _check_decoded_span(observed, raw, start, selector_offset)
    require_executable_walks(walks, instruction_size)
    if (
        len(raw) != length
        or data != raw
        or _sha(raw) != observed['sha256']
        or observed['backing'] != _backing(walks)
    ):
        raise ValueError('Capture extent or native backing differs')
    for (a, n), walks_before in list(linear_reads.items()):
        _, walks_after = translate_linear(context, a, n, physical, virtual,
                                          qemu_image_sha256=inputs.get('qemu_image'), high_ram_end=high_end,
                                       pse36=_pse36(session.vm.machine_configuration, inputs.get('qemu_image')))
        if walks_after != walks_before:
            raise ValueError('Page walks changed during capture')
    for (a, n), b in list(reads.items()):
        if remote.memory(a, n, space='physical', timeout_ms=session._remaining()) != b:
            raise ValueError('Physical witness changed during capture')
    if (
        session.registers() != registers
        or parse_hmp(
            session.vm.qmp.call(
                'human-monitor-command',
                {'command-line': 'info registers'},
                timeout_ms=session._remaining(),
            )
        )
        != context
        or session._process is not process
        or process != saved_process
        or session._runtime_epoch != process['capture_epoch']
        or _source(session, None)[1] != identity
        or _producer() != producer
        or _ram_limits(session.vm.machine_configuration) != (ram_end, high_end)
        or _ram_limits(session.metadata['machine_configuration']) != (ram_end, high_end)
        or session.vm.machine_configuration['memory_mib'] != memory_mib
        or session.metadata['machine_configuration']['memory_mib'] != memory_mib
        or _qemu_input_hashes(session.metadata['runtime_inputs']) != inputs
        or hasattr(session.vm, 'inputs') and _qemu_input_hashes(session.vm.inputs) != inputs
    ):
        raise ValueError('CPU or process changed during capture')
    inputs = _qemu_input_hashes(session.metadata['runtime_inputs'])
    ident = dict(
        run=session.run_id,
        source_version=identity['version'],
        source_version_sha256=identity['version_sha256'],
        source_sha256=identity['source_sha256'],
        arch=session.project.arch,
        bits=session.project.bits,
        cpu_mode='protected',
        captured_at=now(),
        backend='qemu-dos',
        backend_sha256=inputs.get('qemu_image'),
        runtime_inputs=inputs,
        layer_hashes={},
        process_epoch=process['capture_epoch'],
    )
    return {
        **observed,
        'format': 'fdisbull-runtime-code-1',
        'qemu_paged_le_source_admission': ADMISSION,
        'identity': ident,
        'capture_registers': registers,
        'execution_proven': False,
        'paged_le_capture': dict(
            producer=producer,
            context=context,
            interpretation=interpretation,
            capture_location=location,
            memory_mib=memory_mib,
            **({'high_ram_end': high_end} if high_end is not None else {}),
            physical_reads=[
                dict(address=a, length=n, hex=b.hex()) for (a, n), b in sorted(reads.items())
            ],
            linear_walks=[
                dict(address=a, length=n, walks=w) for (a, n), w in sorted(linear_reads.items())
            ],
        ),
    }


def validate(project, observation, run_metadata, *, run, version):
    """Replay every page walk, descriptor and source/fixup proof from retained evidence."""
    from .le import load_runtime_le_carrier

    try:
        current_producer = _producer()
        proof = observation['paged_le_capture']
        ident = observation['identity']
        selected = project.version(version)
        if (
            observation.get('format') != 'fdisbull-runtime-code-1'
            or observation.get('qemu_paged_le_source_admission') != ADMISSION
            or observation.get('space') != 'linear'
            or observation.get('view') not in ('ram', 'execute')
            or observation.get('active_layers') != []
            or observation.get('execution_proven') is not False
            or observation.get('project_address') is not None
            or ident['run'] != run
            or ident['source_version'] != version
            or ident['source_version_sha256'] != selected['sha256']
            or ident['source_sha256'] != project.meta['source_sha256']
            or ident['arch'] != project.arch
            or ident['bits'] != project.bits
            or ident['backend'] != 'qemu-dos'
            or ident['cpu_mode'] != 'protected'
            or ident['layer_hashes'] != {}
            or run_metadata['backend'] != 'qemu-dos'
            or run_metadata['source_sha256'] != ident['source_sha256']
            or run_metadata['version_sha256'] != ident['source_version_sha256']
            or ident['runtime_inputs'] != _qemu_input_hashes(run_metadata['runtime_inputs'])
            or ident['backend_sha256'] != ident['runtime_inputs']['qemu_image']
            or not isinstance(ident['process_epoch'], str)
            or not ident['process_epoch'].startswith(run + ':process:')
            or not ident['process_epoch'][len(run + ':process:') :].isdigit()
            or int(ident['process_epoch'][len(run + ':process:') :]) < 1
            or not _compatible_producer(proof['producer'], current_producer)
        ):
            raise ValueError('Paged LE capture identity differs')
        session = SimpleNamespace(project=project, version=selected, metadata=run_metadata)
        source, identity = _source(session, ident['source_sha256'])
        image = load_runtime_le_carrier(source)
        context = proof['context']
        cpu = _cpu(observation['capture_registers'], context)
        ram_end, high_end = _ram_limits(run_metadata['machine_configuration'])
        if high_end is not None and not _supports_high_ram(proof['producer'], current_producer):
            raise ValueError('Retained producer cannot attest high physical RAM')
        if proof.get('high_ram_end') != high_end:
            raise ValueError('Retained high RAM extent differs from run metadata')
        if run_metadata['machine_configuration']['memory_mib'] != proof['memory_mib']:
            raise ValueError('Retained guest RAM configuration differs from run metadata')
        if (
            not isinstance(proof['physical_reads'], list)
            or len(proof['physical_reads']) > MAX_WITNESS_ROWS
            or not isinstance(proof['linear_walks'], list)
            or len(proof['linear_walks']) > MAX_WITNESS_ROWS
        ):
            raise ValueError('Paged capture witness row budget exceeded')
        reads = {}
        retained_bytes = 0
        for row in proof['physical_reads']:
            a, n = row['address'], row['length']
            if (
                not _ram_extent(a, n, ram_end, high_end)
                or (a, n) in reads
                or retained_bytes + n > MAX_WITNESS_BYTES
                or not isinstance(row['hex'], str)
                or len(row['hex']) != 2 * n
            ):
                raise ValueError('Invalid retained physical witness')
            data = bytes.fromhex(row['hex'])
            if len(data) != n:
                raise ValueError('Invalid retained physical witness')
            reads[a, n] = data
            retained_bytes += n
        if (
            any(not isinstance(row.get('walks'), list) for row in proof['linear_walks'])
            or sum(len(row['walks']) for row in proof['linear_walks']) > MAX_WITNESS_ROWS
        ):
            raise ValueError('Paged capture page walk budget exceeded')
        walks = {(row['address'], row['length']): row['walks'] for row in proof['linear_walks']}
        if len(walks) != len(proof['linear_walks']):
            raise ValueError('Duplicate page walk')
        used = set()
        used_walks = set()

        def physical(a, n):
            key = (a, n)
            if key not in reads:
                raise ValueError('Incomplete physical witness')
            used.add(key)
            return reads[key]

        def read(a, n):
            data, actual = translate_linear(context, a, n, physical,
                                            qemu_image_sha256=_replay_qemu_image(proof['producer'], current_producer, ident['runtime_inputs'].get('qemu_image')), high_ram_end=high_end,
                                            pse36=_supports_pse36(proof['producer'], current_producer, ident['runtime_inputs'].get('qemu_image')) and _pse36(run_metadata['machine_configuration'], ident['runtime_inputs'].get('qemu_image')))
            if not _supports_extended_walks(proof['producer']) and any('page_size' in walk for walk in actual):
                raise ValueError('Legacy producer cannot attest an extended page walk')
            if walks.get((a, n)) != actual:
                raise ValueError('Retained page walk differs')
            used_walks.add((a, n))
            return data

        interpretation = _interpret(image, cpu, context, read, observed_walks=walks)
        start = int(observation['runtime_address'], 16)
        length = observation['length']
        location, selector_offset = _capture_extent(image, cpu, interpretation, start, length)
        raw = read(start, length)
        instruction_size = _check_decoded_span(observation, raw, start, selector_offset)
        require_executable_walks(walks[start, length], instruction_size)
        if (
            raw.hex() != observation['hex']
            or _sha(raw) != observation['sha256']
            or observation['backing'] != _backing(walks[start, length])
            or location != proof['capture_location']
            or interpretation != proof['interpretation']
            or used != set(reads)
            or used_walks != set(walks)
        ):
            raise ValueError('Paged LE replay differs')
        recipe = dict(
            source_sha256=identity['source_sha256'],
            application_source_sha256=image.metadata['le']['application_source_sha256'],
            placements=interpretation['placements'],
        )
        remaining = instruction_size
        segments = []
        for walk in walks[start, length]:
            if not remaining:
                break
            count = min(remaining, walk['length'])
            segments.append({**walk, 'length': count})
            remaining -= count
        return dict(
            image=image,
            recipe=recipe,
            source_location=location,
            raw=raw,
            cpu=cpu,
            selector_offset=selector_offset,
            address_translation=dict(
                paging=bool(context['cr0'] & 0x80000000),
                selector_table=interpretation['descriptor']['table'],
                ldtr_selector=context['ldtr']['selector'],
                instruction_segments=segments,
            ),
        )
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError, StopIteration) as error:
        raise ValueError('Malformed paged LE capture') from error
