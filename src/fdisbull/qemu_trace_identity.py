"""Reconstruct the initial DOS source binding for native trace consumers.

The runtime hash describes observed relocated bytes. A source-site hash uses
the immutable project's relocation base and DOS's exact startup writes, so an
ordinary MZ operand relocation does not split the same site across launches.
Neither identity establishes behavior equivalence or continued ownership.
"""
from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
import hashlib
import json
import re

from iced_x86 import Decoder


CAPTURE_FORMAT = 'fdisbull-qemu-dos-capture-1'
SOURCE_SCOPE = 'initial verified DOS module'
_MAX_SOURCE = 64 * 1024 * 1024
_MAPPING_FIELDS = ('static_base', 'runtime_base', 'module_size', 'load_segment',
                   'delta', 'entry_linear', 'stack_linear', 'file_offset',
                   'relocated_module_sha256', 'loader_writes')
_PROCESS_LIFECYCLE = frozenset(('state', 'termination', 'capture_epoch',
                              'machine_closed', 'persistence_error'))
_MAPPING_LIFECYCLE = frozenset(('status', 'live', 'live_ranges'))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _integer(value, name, maximum=0xffff):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'Native DOS {name} must be an integer in 0..{maximum}')
    return value


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def load_trace_binding(project, version_id, metadata):
    """Return independently derived launch identity and runtime/project bytes.

    Lifecycle status, live ranges and the current capture epoch are deliberately
    separate from launch identity. The storage adapter binds this identity to
    the ordered original ``dos-process-entry`` receipt before trusting a trace.
    """
    # Keep this local: the process collector also calls this helper.
    from .dos import load_com, load_mz
    from .qemu_dos_process import relocated_source

    selected = project.version(version_id)
    if (type(metadata) is not dict or metadata.get('backend') != 'qemu-dos'
            or metadata.get('runtime_profile') != 'dos-exec-load-only-v1'
            or project.meta['format'] not in ('COM', 'MZ') or selected['parent'] is not None):
        raise ValueError('Native source traces require an original DOS EXEC COM/MZ binding')
    if (metadata.get('source_sha256') != project.meta['source_sha256']
            or metadata.get('version_sha256') != selected['sha256']):
        raise ValueError('Native DOS launch source/version identity differs from its project')
    process = metadata.get('process')
    if type(process) is not dict or type(process.get('source_mapping')) is not dict:
        raise ValueError('Native source trace requires its DOS process source mapping')
    entry = process.get('entry')
    if type(entry) is not dict or set(entry) != {'cs', 'ip', 'ss', 'sp', 'ax'}:
        raise ValueError('Native source trace requires its original DOS entry registers')
    entry = {key: _integer(value, 'entry ' + key) for key, value in entry.items()}
    psp = _integer(process.get('psp_segment'), 'PSP')
    parent = _integer(process.get('parent_psp_segment'), 'parent PSP')
    if not psp or not parent or psp == parent:
        raise ValueError('Native DOS child and parent PSP identities must differ')
    epoch = process.get('capture_epoch')
    if type(epoch) is not str or not epoch or len(epoch) > 128:
        raise ValueError('Native DOS process requires a bounded capture epoch')
    row = project.db.execute('SELECT fdb_length(source_bytes) FROM binary_info WHERE version=?',
                             (selected['id'],)).fetchone()
    if row is None or type(row[0]) is not int or not 0 < row[0] <= _MAX_SOURCE:
        raise ValueError('Native trace original source bytes are unavailable or exceed 64 MiB')
    source = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',
                                      (selected['id'],)).fetchone()[0])
    if len(source) != row[0] or _sha(source) != metadata['source_sha256']:
        raise ValueError('Native trace original source failed its content identity check')
    dos = project._document(selected['id']).get('dos')
    if type(dos) is not dict or dos.get('secondary_format'):
        raise ValueError('Native source traces require an unambiguous classic DOS image')
    static_segment = _integer(dos.get('load_segment'), 'static load segment')
    image = (load_com if project.meta['format'] == 'COM' else load_mz)(
        source, load_segment=static_segment, entry=dos.get('selected_entry'))
    derived_dos = image.metadata['dos']
    for key in ('header_fields', 'header_size', 'declared_file_size', 'module_size',
                'image_base', 'relocations'):
        if _json(dos.get(key)) != _json(derived_dos[key]):
            raise ValueError('Native DOS retained loader metadata differs from original source: ' + key)
    regions = project.regions(selected['id'])
    if (project.digest(regions) != selected['sha256']
            or project.digest(image.regions) != selected['sha256']):
        raise ValueError('Native trace project bytes differ from their original image identity')
    report = dict(child_psp=psp, entry_cs=entry['cs'], entry_ip=entry['ip'],
                  stack_ss=entry['ss'], stack_sp=entry['sp'],
                  raw_stack_sp=(entry['sp'] - 2) & 0xffff, initial_ax=entry['ax'])
    expected, derived = relocated_source(source, derived_dos, project.meta['format'], report)
    mapping = process['source_mapping']
    for key in _MAPPING_FIELDS:
        if _json(mapping.get(key)) != _json(derived[key]):
            raise ValueError('Native DOS source mapping differs from its original load: ' + key)
    for key, value in (('source_sha256', metadata['source_sha256']),
                       ('expected_module_sha256', _sha(expected)),
                       ('observed_module_sha256', _sha(expected))):
        if mapping.get(key) != value:
            raise ValueError('Native DOS source mapping differs from its verified bytes: ' + key)
        derived[key] = value
    allocation = process.get('allocation')
    fields = ('mcb_segment', 'segment', 'owner_psp', 'paragraphs', 'start', 'end')
    if type(allocation) is not dict or any(key not in allocation for key in fields):
        raise ValueError('Native DOS launch requires its initial allocation identity')
    allocation = {key: _integer(allocation[key], 'allocation ' + key, 0x100000) for key in fields}
    if (allocation['segment'] != psp or allocation['owner_psp'] != psp
            or allocation['mcb_segment'] != psp - 1
            or allocation['start'] != psp * 16
            or allocation['end'] != (psp + allocation['paragraphs']) * 16
            or not allocation['start'] <= derived['runtime_base']
            or derived['runtime_base'] + len(expected) > allocation['end']
            or not allocation['start'] <= derived['stack_linear'] <= allocation['end']):
        raise ValueError('Native DOS source or stack is outside its initial owned allocation')
    canonical = bytearray(image.regions[0].data[:derived['module_size']])
    for write in derived['loader_writes']:
        offset = write['module_offset']
        replacement = bytes.fromhex(write['after_hex'])
        canonical[offset:offset + len(replacement)] = replacement
    identity = dict(backend='qemu-dos', runtime_profile=metadata['runtime_profile'],
        source_sha256=metadata['source_sha256'], version_sha256=selected['sha256'],
        version=selected['id'], psp_segment=psp, parent_psp_segment=parent,
        entry=entry, allocation=allocation, source_mapping=deepcopy(derived))
    # Retain all initial evidence, including command-tail/FCB/entry snapshots
    # and prepared disk provenance. Only explicit live lifecycle fields may
    # differ after capture; adding a new field does not silently exempt it.
    immutable_process = {key: deepcopy(value) for key, value in process.items()
                         if key not in _PROCESS_LIFECYCLE and key != 'source_mapping'}
    immutable_process['source_mapping'] = {
        key: deepcopy(value) for key, value in mapping.items() if key not in _MAPPING_LIFECYCLE}
    identity['process'] = immutable_process
    identity['launch_metadata'] = {key: deepcopy(value) for key, value in metadata.items()
        if key not in ('process', 'runtime_inputs', 'capabilities', 'qemu_pid')}
    inputs = metadata.get('runtime_inputs', {})
    if type(inputs) is not dict or len(inputs) > 32:
        raise ValueError('Native DOS runtime input identities are malformed')
    identity['runtime_inputs'] = {}
    for name, item in inputs.items():
        if (type(item) is not dict or type(item.get('sha256')) is not str
                or re.fullmatch('[0-9a-f]{64}', item['sha256']) is None):
            raise ValueError('Native DOS runtime input lacks its content identity')
        identity['runtime_inputs'][name] = {'sha256': item['sha256']}
    return dict(identity=identity, expected_bytes=expected, project_bytes=bytes(canonical),
                mapping=deepcopy(derived), capture_epoch=epoch,
                relocation_offsets=sorted({item['file_offset'] - derived_dos['header_size']
                                           for item in derived_dos['relocations']}))


def qualify_instruction(binding, linear_address, observed_bytes, *, segment, offset):
    """Qualify one stopped real-mode observation, or return an explicit boundary.

    Ordinary data writes elsewhere in the module do not invalidate this site.
    Relocations overlapping an opcode or instruction boundary are conservative:
    a changed decode or partially included relocation word cannot be a source
    site, even if DOS correctly applied the declared fixup.
    """
    result = dict(qualified=False, project_address=None, context=None,
                  source_instruction_sha256=None, instruction_size=None, reason=None)

    def boundary(reason):
        return dict(result, reason=reason)

    if (type(linear_address) is not int or type(segment) is not int or type(offset) is not int
            or not 0 <= segment <= 0xffff or not 0 <= offset <= 0xffff
            or linear_address != segment * 16 + offset):
        return boundary('Observation is not an unwrapped 16-bit real-mode CS:IP')
    if not isinstance(observed_bytes, bytes) or not 1 <= len(observed_bytes) <= 15:
        return boundary('Instruction lookahead is unavailable or exceeds 15 bytes')
    mapping = binding['mapping']
    relative = linear_address - mapping['runtime_base']
    if not 0 <= relative < mapping['module_size']:
        return boundary('PC is outside the initial verified DOS module')
    instruction = Decoder(16, observed_bytes, ip=offset).decode()
    if instruction.is_invalid:
        return boundary('Observed instruction could not be decoded')
    result['instruction_size'] = instruction.len
    end = relative + instruction.len
    if end > mapping['module_size']:
        return boundary('Instruction extends outside the initial verified DOS module')
    if observed_bytes[:instruction.len] != binding['expected_bytes'][relative:end]:
        return boundary('Instruction bytes differ from the verified DOS load')
    relocations = binding['relocation_offsets']
    for boundary_offset in (relative - 1, end - 1):
        index = bisect_left(relocations, boundary_offset)
        if index < len(relocations) and relocations[index] == boundary_offset:
            return boundary('A DOS relocation straddles this decoded instruction')
    canonical = binding['project_bytes'][relative:end]
    source = Decoder(16, canonical, ip=offset).decode()
    if source.is_invalid or source.len != instruction.len or source.code != instruction.code:
        return boundary('DOS relocation changes the instruction decode')
    project_address = mapping['static_base'] + relative
    projected_cs, remainder = divmod(project_address - offset, 16)
    if remainder or not 0 <= projected_cs <= 0xffff:
        return boundary('Observed CS:IP has no unwrapped project source context')
    return dict(result, qualified=True, project_address=project_address,
                context=f'real:{projected_cs:04x}', source_instruction_sha256=_sha(canonical))
