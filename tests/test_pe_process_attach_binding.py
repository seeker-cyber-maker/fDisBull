"""Binding-only negatives using a sealed native full-leaf packet.

Boundary/selection receipts below are explicitly synthetic test envelopes. The
retained instructions, memory evolution and MODULE view are unchanged native
observations. These tests do not create a new native execution claim.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.pe_process_attach_binding import bind_process_attach, _rows
from fdisbull.runtime_loader_analysis import _cells


@pytest.fixture(scope='module')
def packet():
    selected = os.environ.get('FDISBULL_PROCESS_ATTACH_BINDING_PACKETS')
    if not selected:
        pytest.skip('Select sealed full process_attach binding packets')
    rows = json.loads(Path(selected).read_text())
    row = rows[0]
    documents = []
    for prefix in ('capsule', 'module_capsule'):
        raw = Path(row[prefix + '_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row[prefix + '_sha256']
        documents.append(json.loads(raw))
    return tuple(documents)


def _bound(packet):
    full, module = deepcopy(packet)
    run = full['run']; first, last = (full['module_span'][k] for k in ('first_step', 'last_step'))
    full_ref, before_ref, after_ref, tail_ref, selected_ref, main_ref = [
        {'artifact': 'unit-' + name} for name in ('full', 'before', 'after', 'tail', 'selected', 'main')]
    module_ref = full['module_span']['artifact']
    documents = {full_ref['artifact']: full, module_ref['artifact']: module,
        before_ref['artifact']: {'registers': deepcopy(full['entry']), 'memory': deepcopy(full['entry_memory'])},
        after_ref['artifact']: {'registers': deepcopy(full['exit']), 'memory': deepcopy(full['exit_memory'])},
        main_ref['artifact']: {}}
    entry = _cells(full['entry_memory'], maximum=16384, range_limit=256)
    state = dict(entry)
    for step in full['steps'][:last + 1]:
        for access in step['accesses']:
            if access['kind'] == 'write':
                a = int(access['address'], 16)
                state.update({a + k: b for k, b in enumerate(bytes.fromhex(access['after_hex']))})
    tail = {'steps': deepcopy(full['steps'][last + 1:]), 'exit': deepcopy(full['exit']),
        'entry_memory': _rows(state), 'derived_from': {'artifact': full_ref,
            'first_step': last + 1, 'last_step': len(full['steps']) - 1}}
    documents[tail_ref['artifact']] = tail
    node, wm = (int(full['selection'][k], 16) for k in ('node', 'modref'))
    base = full['subject_module']['base']
    source = {'source_sha256': full['loader_module']['source_sha256'], 'symbol': 'process_attach.part.0'}
    documents[selected_ref['artifact']] = {'format': 'fdisbull-wine-process-attach-selection-1',
        'run': run, 'source': source, 'module': deepcopy(full['loader_module']), 'selected': True,
        'registers': deepcopy(full['entry']), 'node': hex(node), 'modref': hex(wm),
        'node_module_pointer': hex(wm + 0xa0), 'base_pointer_address': hex(wm + 0x30),
        'base_pointer_hex': bytes(entry[wm + 0x30 + k] for k in range(8)).hex()}
    report = {'loader_process_attach': full_ref,
        'loader_process_attach_boundaries': {'entry_snapshot': before_ref, 'exit_snapshot': after_ref},
        'loader_process_attach_selection': {'source': source, 'candidates': [selected_ref],
            'entry_address': full['entry']['rip']}, 'loader_selection': {'source': source},
        'recovery': {'entry': main_ref}}
    receipts = {}
    for ref, kind, sequence in ((selected_ref, 'loader-process-attach-selection', 1),
        (before_ref, 'loader-frame-snapshot', 2), (module_ref, 'wine-loader-dispatch-capsule', 3),
        (full_ref, 'wine-process-attach', 4), (tail_ref, 'wine-loader-interval', 5),
        (after_ref, 'loader-frame-snapshot', 6), (main_ref, 'loader-frame-snapshot', 7)):
        receipts[ref['artifact']] = {**ref, 'kind': kind, 'sequence': sequence,
            'run': run, 'version': 1}
    return {'report': report, 'run': run, 'exe_image': {'sha256': full['controller_source_sha256']},
        'dll_image': {'sha256': full['subject_source_sha256'], 'base': base, 'module': full['subject_module']},
        'documents': documents, 'receipts': receipts,
        'protected': {r['role']: (int(r['address'], 16), r['length']) for r in full['protected_ranges']},
        'capsules': [{'artifact': module_ref['artifact'], 'capsule': module}],
        'intervals': [{'artifact': tail_ref['artifact'], 'interval': tail,
                       'boundaries': {'exit_snapshot': after_ref}}]}


def _call(bound):
    return bind_process_attach(**bound)


def _event_pair(bound, inside):
    full = bound['documents']['unit-full']; index = full['module_span']['first_step'] + 2 if inside else 0
    events = [full['steps'][index]['event']]
    if inside:
        events.append(bound['capsules'][0]['capsule']['steps'][2]['event'])
    return events


def test_real_instruction_and_ram_views_bind_without_reexecution(packet):
    bound = _bound(packet); result = _call(bound)
    assert result['artifact'] == 'unit-full'


@pytest.mark.parametrize('inside', [False, True])
@pytest.mark.parametrize('mutation', ['stage', 'context', 'source-bool', 'runtime-pc', 'completion', 'layers', 'generation', 'relocation'])
def test_native_identity_cannot_be_relabelled_even_inside_a_summary(packet, inside, mutation):
    bound = _bound(packet)
    for event in _event_pair(bound, inside):
        if mutation == 'stage': event['observation']['registers_stage'] = 'after-instruction'
        elif mutation == 'context': event['identity']['context'] = 'machine'
        elif mutation == 'source-bool': event['identity']['source_version'] = True
        elif mutation == 'runtime-pc': event['identity']['runtime_address'] = '0x1234'
        elif mutation == 'completion': event['observation']['instruction_completed'] = False
        elif mutation == 'layers': event['active_layers'] = ['unproved-layer']
        elif mutation == 'generation': event['layer_generation'] = 1
        else: event['native_address'] = event['address']
    with pytest.raises(ValueError, match='native instruction identity'):
        _call(bound)


@pytest.mark.parametrize('which', ['entry_memory', 'exit_memory'])
def test_module_memory_receipts_must_join_the_evolving_outer_state(packet, which):
    bound = _bound(packet); module = bound['capsules'][0]['capsule']
    row = module[which][0]
    row['hex'] = f'{bytes.fromhex(row["hex"])[0] ^ 1:02x}' + row['hex'][2:]
    with pytest.raises(ValueError, match='boundary metadata or stack bytes differ'):
        _call(bound)


def test_exact_code_read_digest_cannot_be_replaced(packet):
    bound = _bound(packet); bound['documents']['unit-full']['steps'][0]['code_read']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='native byte read'):
        _call(bound)


def test_shadow_module_generation_at_the_same_base_is_not_a_unique_owner(packet):
    bound = _bound(packet); full = bound['documents']['unit-full']
    stale = deepcopy(full['loader_module']); stale['generation'] += 1
    full['modules_after']['modules'].append(stale)
    with pytest.raises(ValueError, match='module generation'):
        _call(bound)


def test_per_step_protected_snapshot_cannot_hide_an_unreported_change(packet):
    bound = _bound(packet); row = bound['documents']['unit-full']['steps'][0]['protected_after'][0]
    row['hex'] = f'{bytes.fromhex(row["hex"])[0] ^ 1:02x}' + row['hex'][2:]
    with pytest.raises(ValueError, match='protected-memory boundary'):
        _call(bound)
