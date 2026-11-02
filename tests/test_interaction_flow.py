from copy import deepcopy

import pytest

from fdisbull.interaction_il import ILInvalid, change_role, execute_il, validate_il


def program():
    return {'format': 'fdisbull-il-2', 'role': 'udl',
            'variables': {'$x': {'type': 'u8', 'initial': 0}},
            'resources': {'t': {'kind': 'text', 'text': 'hello'}},
            'evidence': {'source': {'sha256': 'a' * 64}}, 'entry': 'start',
            'continuations': {
                'start': {'body': [{'id': 'set', 'op': 'set', 'var': '$x', 'value': 1}],
                          'transfer': {'op': 'if', 'condition': {'op': 'eq', 'left': {'var': '$x'}, 'right': 1}, 'then': 'call', 'else': 'end'}},
                'call': {'body': [], 'transfer': {'op': 'call', 'target': 'shared', 'resume': 'again'}},
                'again': {'body': [], 'transfer': {'op': 'call', 'target': 'shared', 'resume': 'end'}},
                'shared': {'body': [{'id': 'add', 'op': 'add', 'var': '$x', 'value': 1, 'evidence': ['source']}], 'transfer': {'op': 'return'}},
                'end': {'body': [{'id': 'text', 'op': 'text', 'resource': 't'}], 'transfer': {'op': 'return'}}}}


def test_shared_calls_and_role_copy():
    p = program(); assert validate_il(p)
    other = change_role(p, 'uil'); assert p['role'] == 'udl' and other['role'] == 'uil'
    r = execute_il(other)
    assert r['state'] == {'$x': 3}
    assert r['visited'] == ['start', 'set', 'call', 'shared', 'add', 'again', 'shared', 'add', 'end', 'text']
    assert r['control_trace'][2] == {'continuation': 'shared', 'call_stack': ['again']}
    assert r['control'] == {'continuation': 'end', 'call_stack': [], 'stop': 'return'}
    assert r['events'][0]['resource_data']['text'] == 'hello' and r['evidence'] == p['evidence']


def test_stop_in_callee_preserves_stack():
    p = program(); p['continuations']['shared']['transfer'] = {'op': 'stop'}
    r = execute_il(p)
    assert r['state'] == {'$x': 2}
    assert r['control'] == {'continuation': 'shared', 'call_stack': ['again'], 'stop': 'stop'}
    assert 'again' not in r['visited']


@pytest.mark.parametrize('mutation', ['target', 'id', 'opaque', 'condition'])
def test_invalid_or_opaque_unreachable_is_refused(mutation):
    p = program(); p['continuations']['unused'] = {'body': [], 'transfer': {'op': 'return'}}
    if mutation == 'target': p['continuations']['unused']['transfer'] = {'op': 'goto', 'target': 'missing'}
    if mutation == 'id': p['continuations']['unused']['body'] = [{'id': 'start', 'op': 'text', 'resource': 't'}]
    if mutation == 'opaque': p['continuations']['unused']['body'] = [{'id': 'o', 'op': 'opaque', 'reason': 'unknown'}]
    if mutation == 'condition': p['continuations']['unused']['transfer'] = {'op': 'if', 'condition': {'op': 'bad'}, 'then': 'end', 'else': 'end'}
    if mutation != 'opaque':
        with pytest.raises(ILInvalid): validate_il(p)
    else: assert validate_il(p)
    r = execute_il(p, {'$x': 9})
    assert r['status'] == 'refused' and r['state'] == {'$x': 9} and r['events'] == [] and r['visited'] == []


def test_loop_and_recursive_call_refuse_atomically():
    p = program(); p['continuations']['shared']['transfer'] = {'op': 'goto', 'target': 'shared'}
    r = execute_il(p, {'$x': 5}, max_steps=12)
    assert r['status'] == 'refused' and r['state'] == {'$x': 5} and r['events'] == []
    p['continuations']['shared']['transfer'] = {'op': 'call', 'target': 'shared', 'resume': 'end'}
    r = execute_il(p, {'$x': 5}, max_call_depth=2)
    assert r['status'] == 'refused' and 'depth' in r['error'] and r['state'] == {'$x': 5}


def test_host_event_pending_and_capability_preflight():
    p = program(); p['resources']['g'] = {'kind': 'graphic', 'uri': 'g'}
    p['continuations']['end']['body'].append({'id': 'g', 'op': 'load_graphic', 'resource': 'g', 'x': 0, 'y': 0})
    assert execute_il(p)['status'] == 'refused'
    r = execute_il(p, capabilities=['graphics'])
    assert r['status'] == 'pending_host' and r['state'] == {'$x': 0} and r['proposed_state'] == {'$x': 3}


def test_goto_and_alternate_branch():
    p = program()
    p['continuations']['start']['body'][0]['value'] = 0
    p['continuations']['start']['transfer']['else'] = 'jump'
    p['continuations']['jump'] = {'body': [], 'transfer': {'op': 'goto', 'target': 'end'}}
    r = execute_il(p)
    assert r['visited'] == ['start', 'set', 'jump', 'end', 'text']
    assert r['state'] == {'$x': 0}


def test_malformed_unreachable_block_reports_invalid():
    p = program()
    p['continuations']['unused'] = {'body': [{'id': 'bad', 'op': []}], 'transfer': {'op': 'return'}}
    with pytest.raises(ILInvalid): validate_il(p)


def test_null_resume_global_stop_and_unexpected_return():
    p = program()
    p['continuations']['call']['transfer']['resume'] = None
    p['continuations']['shared']['transfer'] = {'op': 'stop'}
    r = execute_il(p)
    assert r['state'] == {'$x': 2}
    assert r['control'] == {'continuation': 'shared', 'call_stack': [None], 'stop': 'stop'}
    assert r['control_trace'][-1]['call_stack'] == [None]
    p['continuations']['shared']['transfer'] = {'op': 'return'}
    r = execute_il(p, {'$x': 7})
    assert r['status'] == 'refused' and r['error'] == 'unexpected return without continuation'
    assert r['state'] == {'$x': 7} and r['events'] == [] and r['visited'] == []
