"""Bind one full native process_attach invocation to its retained MODULE view.

This checks evidence provenance and byte/context joins. The separate semantic
verifier must still execute and prove the source-bound instructions.
"""
from copy import deepcopy
import hashlib

from .runtime_loader_analysis import (_reference, _number, _cells,
    _require_loader_boundary_overlap, _require_protected_memory_join)
from .debug_semantics import PE_TRACE_SEMANTICS
from .wine_arch import validate_context


def bind_process_attach(report, *, run, exe_image, dll_image, documents, receipts,
                        protected, capsules, intervals):
    def doc(ref, kind=None):
        return _reference(ref, documents, receipts, kind)
    def sequence(ref):
        doc(ref)
        return receipts[ref['artifact']]['sequence']
    def same_module(a, b):
        return all(a.get(k) == b.get(k) for k in ('name', 'base', 'size', 'bits', 'generation'))
    def memory(rows):
        return _cells(rows, maximum=16384, range_limit=256)
    reference = report['loader_process_attach']
    full = doc(reference, 'wine-process-attach')
    endpoints = report['loader_process_attach_boundaries']
    before = doc(endpoints['entry_snapshot'], 'loader-frame-snapshot')
    after = doc(endpoints['exit_snapshot'], 'loader-frame-snapshot')
    dispatcher = capsules[0]
    module = dispatcher['capsule']
    validate_context(full['entry'], 64); validate_context(full['exit'], 64)
    thread = full['entry'].get('thread')
    if type(thread) is not int or not 0 < thread <= 0xffffffff or full['exit'].get('thread') != thread:
        raise ValueError('Full process_attach lacks its exact native thread identity')
    if (full.get('format') != 'fdisbull-wine-process-attach-1'
            or full.get('status') != 'complete' or full.get('run') != run
            or full.get('semantics') != PE_TRACE_SEMANTICS
            or full.get('controller_source_sha256') != exe_image['sha256']
            or full.get('subject_source_sha256') != dll_image['sha256']
            or not same_module(full['subject_module'], dll_image['module'])
            or full['loader_module'] != module['loader_module']
            or full['entry'] != before['registers'] or full['exit'] != after['registers']):
        raise ValueError('Full process_attach source, ownership or boundary context differs')
    if not (sequence(endpoints['entry_snapshot']) < receipts[dispatcher['artifact']]['sequence']
            < sequence(reference) < sequence(endpoints['exit_snapshot'])
            < sequence(report['recovery']['entry'])):
        raise ValueError('Full process_attach contradicts its native journal chronology')
    declared = {r['role']: (_number(r['address']), r['length']) for r in full['protected_ranges']}
    if len(declared) != len(full['protected_ranges']) or declared != protected:
        raise ValueError('Full process_attach omits complete protected source ranges')
    owned = {a for start, length in protected.values() for a in range(start, start + length)}
    steps = full['steps']; span = full['module_span']
    first, last = span['first_step'], span['last_step']
    if (not isinstance(steps, list) or not 1 <= len(steps) <= 2048
            or type(first) is not int or type(last) is not int
            or not 0 < first <= last < len(steps) - 1
            or doc(span['artifact'], 'wine-loader-dispatch-capsule') != module
            or span['artifact']['artifact'] != dispatcher['artifact']
            or steps[first:last + 1] != module['steps']):
        raise ValueError('Full process_attach MODULE view differs from its exact retained span')
    if (full['callback_spans'] != [s | {'first_step': first+s['first_step'],
                                      'last_step': first+s['last_step']} for s in module['callback_spans']]
            or full['code_versions'][1:] != [e | {'after_step': first+e['after_step']}
                                             for e in module['code_versions'][1:]]):
        raise ValueError('Full process_attach callback or code-version evidence differs')
    # Selection is an actual stopped invocation, not a caller-selected WM value.
    selection = report['loader_process_attach_selection']
    if selection['source'] != report['loader_selection']['source']:
        raise ValueError('Full process_attach selected another Wine source')
    candidates = selection['candidates']
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 256:
        raise ValueError('Bounded actual process_attach selection is required')
    selected = []; previous = -1
    for ref in candidates:
        candidate = doc(ref, 'loader-process-attach-selection')
        order = sequence(ref)
        if (candidate.get('format') != 'fdisbull-wine-process-attach-selection-1'
                or candidate['run'] != run or candidate['source'] != selection['source']
                or not same_module(candidate['module'], full['loader_module'])
                or not previous < order < sequence(endpoints['entry_snapshot'])
                or candidate['registers']['rip'] != selection['entry_address']):
            raise ValueError('Full process_attach selection lacks its native source/context chronology')
        node = _number(candidate['node']); wm = _number(candidate['modref'])
        raw = bytes.fromhex(candidate['base_pointer_hex'])
        if (node != _number(candidate['registers']['general']['rcx'])
                or _number(candidate['node_module_pointer']) != wm + 0xa0
                or _number(candidate['base_pointer_address']) != wm + 0x30 or len(raw) != 8
                or type(candidate['selected']) is not bool
                or candidate['selected'] != (int.from_bytes(raw, 'little') == _number(dll_image['base']))):
            raise ValueError('Full process_attach DDAG selection differs from its observed pointer chain')
        if candidate['selected']: selected.append((ref, candidate))
        previous = order
    if len(selected) != 1 or selected[0][0] != candidates[-1] or selected[0][1]['registers'] != full['entry']:
        raise ValueError('Full process_attach does not enter its unique selected DDAG invocation')
    entry = memory(full['entry_memory']); exit_ = memory(full['exit_memory'])
    candidate = selected[0][1]; node = _number(candidate['node']); wm = _number(candidate['modref'])
    def word(a):
        return int.from_bytes(bytes(entry[a+k] for k in range(8)), 'little')
    if (word(node) != wm+0xa0 or word(wm+0x30) != _number(dll_image['base'])
            or full['selection'] != {'dll_base': dll_image['base'], 'modref': hex(wm),
                                     'node': hex(node), 'reserved': full['entry']['general']['rdx']}):
        raise ValueError('Full process_attach entry RAM differs from selected source DDAG metadata')
    for state in (full['modules_before'], full['modules_after']):
        for expected in (full['loader_module'], dll_image['module']):
            owners = [m for m in state['modules'] if _number(m['base']) == _number(expected['base'])]
            if len(owners) != 1 or not same_module(owners[0], expected):
                raise ValueError('Full process_attach changes source module generation')
    for rows, expected, label in ((before['memory'], entry, 'full entry'),
                                  (after['memory'], exit_, 'full return')):
        _require_loader_boundary_overlap(rows, full['entry_memory'] if label == 'full entry' else full['exit_memory'])
        _require_protected_memory_join(rows, expected, owned, label)
    # The old caller tail must be an exact suffix of this single execution.
    tail = intervals[0]['interval']; derivation = tail.get('derived_from', {})
    if (derivation != {'artifact': reference, 'first_step': last+1, 'last_step': len(steps)-1}
            or tail['steps'] != steps[last+1:] or tail['exit'] != full['exit']
            or intervals[0]['boundaries']['exit_snapshot'] != endpoints['exit_snapshot']
            or not sequence(reference) < receipts[intervals[0]['artifact']]['sequence']
            < sequence(endpoints['exit_snapshot'])):
        raise ValueError('Caller tail is not the exact unreexecuted full process_attach suffix')
    state = dict(entry)
    for i, step in enumerate(steps):
        event = step['event']
        validate_context(event['registers'], 64); validate_context(step['after'], 64)
        identity, observation = event['identity'], event['observation']
        if (event.get('project_address') is not None or identity.get('project_address') is not None
                or type(identity.get('source_version')) is not int or identity['source_version'] != 1
                or identity.get('context') != 'flat'
                or identity.get('runtime_address') != event['address']
                or event['registers']['rip'] != event['address']
                or observation.get('registers_stage') != 'before-instruction'
                or observation.get('instruction_completed') is not True
                or event['registers'].get('thread') != thread or step['after'].get('thread') != thread
                or event.get('active_layers') != [] or type(event.get('layer_generation')) is not int
                or event['layer_generation'] != 0 or 'native_address' in event or 'native_bytes' in event):
            raise ValueError('Full process_attach rewrites its completed native instruction identity')
        read = step['code_read']; raw = bytes.fromhex(read['hex'])
        executed = bytes.fromhex(event.get('execution_bytes', event['bytes']))
        address = _number(event['address'])
        owners = [m for m in full['modules_before']['modules'] if _number(m['base']) <= address
                  and address + len(executed) <= _number(m['base']) + m['size']]
        if (not 1 <= len(executed) <= len(raw) <= 15 or read['address'] != event['address']
                or not raw.startswith(executed) or event['bytes'] != executed.hex()
                or event.get('ram_bytes') != executed.hex()
                or hashlib.sha256(raw).hexdigest() != read['sha256']
                or len(owners) != 1 or not same_module(read['module'], owners[0])
                or not any(same_module(owners[0], owner) for owner in (full['loader_module'], dll_image['module']))):
            raise ValueError('Full process_attach loses its exact native byte read or module owner')
        expected = full['entry'] if i == 0 else steps[i-1]['after']
        if event['registers'] != expected:
            raise ValueError('Full process_attach loses its continuous native context')
        _require_protected_memory_join(step['protected_before'], state, owned, 'full per-step entry')
        if i == first:
            _require_loader_boundary_overlap(_rows(state), module['entry_memory'])
        for access in step['accesses']:
            a = _number(access['address']); width = access['width']
            if bytes(state[a+k] for k in range(width)) != bytes.fromhex(access['before_hex']):
                raise ValueError('Full process_attach access loses the evolving native RAM state')
        for access in step['accesses']:
            if access['kind'] == 'write':
                a = _number(access['address'])
                state.update({a+k:b for k,b in enumerate(bytes.fromhex(access['after_hex']))})
        for access in step['accesses']:
            a = _number(access['address']); width = access['width']
            if bytes(state[a+k] for k in range(width)) != bytes.fromhex(access['after_hex']):
                raise ValueError('Full process_attach post-access RAM differs')
        _require_protected_memory_join(step['protected_after'], state, owned, 'full per-step exit')
        if i == last:
            _require_loader_boundary_overlap(_rows(state), module['exit_memory'])
            _require_loader_boundary_overlap(tail['entry_memory'], _rows(state))
    if state != exit_ or steps[-1]['after'] != full['exit']:
        raise ValueError('Full process_attach final RAM/context differs from its retained accesses')
    return {'artifact': reference['artifact'], 'capsule': full,
            'boundaries': deepcopy(endpoints), 'dispatcher_artifact': dispatcher['artifact'],
            'selection_artifact': selected[0][0]['artifact'],
            'scope': 'Provenance joins only; source-bound full-leaf instruction semantics require reverification'}


def _rows(cells):
    rows = []
    for a, b in sorted(cells.items()):
        if rows and _number(rows[-1]['address']) + len(rows[-1]['hex'])//2 == a:
            rows[-1]['hex'] += f'{b:02x}'
        else:
            rows.append({'address': hex(a), 'hex': f'{b:02x}'})
    return rows
